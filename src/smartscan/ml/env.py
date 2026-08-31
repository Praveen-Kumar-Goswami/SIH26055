"""Gymnasium wrapper around the Stage 2 receiver. Policy sees features only."""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

from smartscan.config import SimulateConfig, TrainConfig, load_yaml, project_root
from smartscan.ml.actions import command_from_policy_action, n_actions
from smartscan.ml.features import (
    FeatureBuilder,
    ObservationNormalizer,
    compose_observation,
    observation_size,
)
from smartscan.ml.forecast import HorizonForecaster
from smartscan.ml.novelty import assess_threat
from smartscan.ml.observable import ObservableTransition, transition_from_decision
from smartscan.ml.predictor import RecencyPredictor
from smartscan.ml.reward import (
    RewardCalculator,
    is_coverage_visit,
    is_first_hit_on_visit,
    recent_same_band_no_hit,
    stamp_decision_reward,
)
from smartscan.ml.runner import constant_schedule
from smartscan.receiver.detector import load_receiver_config
from smartscan.receiver.logs import DecisionLog, ObservationLog, ReceiverRun
from smartscan.receiver.scanner import ReceiverEngine
from smartscan.rf.environment import simulate
from smartscan.types import ORACLE_INFO_PREFIX, GroundTruth, ReceiverConfig, SmartScanError

try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError:  # pragma: no cover
    gym = None  # type: ignore[assignment]
    spaces = None  # type: ignore[assignment]


def _receiver(cfg: TrainConfig) -> ReceiverConfig:
    payload = dict(load_yaml(project_root() / cfg.receiver_config))
    payload["dwell_bins"] = list(cfg.dwell_bins)
    payload["noise_power_w"] = float(cfg.noise_power_w)
    return load_receiver_config(payload)


def episode_catalog(cfg: TrainConfig, split: str = "train") -> list[tuple[str, int]]:
    """Frozen (scenario, seed) pairs for a split. Empty → single sparse fallback."""

    if split == "val":
        specs = cfg.val_scenarios
    elif split == "test":
        specs = cfg.test_scenarios
    else:
        specs = cfg.train_scenarios
    pairs = [(item.scenario_id, int(seed)) for item in specs for seed in item.seeds]
    return pairs


class SmartScanEnv(gym.Env if gym is not None else object):  # type: ignore[misc]
    """Discrete(K*L) band+dwell env. Observation is a finite float32 Box."""

    metadata: ClassVar[dict[str, Any]] = {"render_modes": []}
    action_space: Any
    observation_space: Any

    def __init__(
        self,
        cfg: TrainConfig,
        *,
        scenario_id: str | None = None,
        scenario_seed: int | None = None,
        receiver_seed: int | None = None,
        normalizer: ObservationNormalizer | None = None,
        predictor: Any | None = None,
        record_forecast: bool = True,
        freeze_obs_stats: bool = False,
        split: str = "train",
    ) -> None:
        if gym is None or spaces is None:
            raise SmartScanError("gymnasium is required for SmartScanEnv.")
        self.cfg = cfg
        self.receiver = _receiver(cfg)
        self.dwell_bins = tuple(int(x) for x in cfg.dwell_bins)
        self._scenario_id = scenario_id or (
            cfg.train_scenarios[0].scenario_id if cfg.train_scenarios else "sparse"
        )
        self._scenario_seed = int(scenario_seed if scenario_seed is not None else cfg.seed)
        self._receiver_seed = int(receiver_seed if receiver_seed is not None else cfg.seed)
        plan_n = observation_size_for(cfg)
        self._n_bands = plan_n[0]
        size = plan_n[1]
        self._action_layout = str(getattr(cfg, "action_layout", "discrete")).strip().lower()
        if self._action_layout == "multidiscrete":
            self.action_space = spaces.MultiDiscrete(
                [self._n_bands, max(1, len(self.dwell_bins))]
            )
        else:
            self.action_space = spaces.Discrete(n_actions(self._n_bands, self.dwell_bins))
        self.observation_space = spaces.Box(low=-10.0, high=10.0, shape=(size,), dtype=np.float32)
        self.normalizer = normalizer or ObservationNormalizer(size=size)
        self._obs_stats_checkpoint = self.normalizer.state_dict()
        self.reward_calc = RewardCalculator(cfg.reward)
        self.predictor = predictor
        self.record_forecast = bool(record_forecast)
        self.freeze_obs_stats = bool(freeze_obs_stats)
        self.split = str(split)
        self._catalog = self._build_catalog()
        self._full_catalog = list(self._catalog)
        self._episode_i = 0
        self._engine: ReceiverEngine | None = None
        self._builder: FeatureBuilder | None = None
        self._truth: GroundTruth | None = None
        self._obs_rows: list[Any] = []
        self._dec_rows: list[Any] = []
        self._history: list[ObservableTransition] = []
        self._decision_index = 0
        self._last_dwell: int | None = None
        self._horizon_logged = False
        self._public = {int(b): 2.0 for b in cfg.public_priorities}

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)
        if not self.freeze_obs_stats:
            self.normalizer = ObservationNormalizer.from_state(
                {
                    "size": self._obs_stats_checkpoint["size"],
                    "clip": self._obs_stats_checkpoint["clip"],
                    "count": self._obs_stats_checkpoint["count"],
                    "mean": np.asarray(self._obs_stats_checkpoint["mean"]).copy(),
                    "m2": np.asarray(self._obs_stats_checkpoint["m2"]).copy(),
                }
            )
        opts = options or {}
        scenario_id, scenario_seed, receiver_seed = self._resolve_episode(seed, opts)
        sim = SimulateConfig(
            seed=scenario_seed,
            dt_s=self.cfg.dt_s,
            duration_s=self.cfg.duration_s,
            band_plan_id=self.cfg.band_plan_id,
            scenario_id=scenario_id,
        )
        self._truth = simulate(sim)
        if self._truth.band_plan.n_bands != self._n_bands:
            raise SmartScanError("BandPlan n_bands does not match the frozen observation space.")
        self._engine = ReceiverEngine(
            truth=self._truth, config=self.receiver, receiver_seed=receiver_seed
        )
        self._builder = FeatureBuilder(
            n_bands=self._n_bands,
            dt_s=self.cfg.dt_s,
            dwell_bins=self.dwell_bins,
            ewma_alpha=self.cfg.ewma_alpha,
            tune_latency_steps=self.receiver.tune_latency_steps,
            ablate_periodicity=self.cfg.ablate_periodicity,
            ablate_novelty=self.cfg.ablate_novelty,
            public_priorities=self._public,
        )
        self._obs_rows = []
        self._dec_rows = []
        self._history = []
        self._decision_index = 0
        self._last_dwell = None
        self._horizon_logged = False
        obs = self._observe_vector()
        return obs, {}

    def _resolve_episode(self, seed: int | None, opts: dict[str, Any]) -> tuple[str, int, int]:
        if "scenario_id" in opts or "scenario_seed" in opts:
            sid = str(opts.get("scenario_id", self._scenario_id))
            sseed = int(opts.get("scenario_seed", seed if seed is not None else self._scenario_seed))
            rseed = int(opts.get("receiver_seed", sseed))
            return sid, sseed, rseed
        if self._catalog:
            if self.split == "train" and "scenario_id" not in opts:
                catalog = self._active_catalog()
                idx = self._episode_i % max(len(catalog), 1)
                self._episode_i += 1
                sid, sseed = catalog[idx]
                rseed = int(opts.get("receiver_seed", sseed))
                return sid, int(sseed), rseed
            if seed is None:
                idx = self._episode_i % len(self._catalog)
                self._episode_i += 1
            else:
                idx = int(seed) % len(self._catalog)
            sid, sseed = self._catalog[idx]
            rseed = int(opts.get("receiver_seed", sseed))
            return sid, int(sseed), rseed
        sid = self._scenario_id
        sseed = int(seed if seed is not None else self._scenario_seed)
        rseed = int(opts.get("receiver_seed", seed if seed is not None else self._receiver_seed))
        return sid, sseed, rseed

    def _build_catalog(self) -> list[tuple[str, int]]:
        pairs = episode_catalog(self.cfg, self.split)
        if bool(getattr(self.cfg, "balanced_family_sampling", False)):
            return _interleave_by_family(pairs)
        return pairs

    def _active_catalog(self) -> list[tuple[str, int]]:
        stages = list(getattr(self.cfg, "curriculum_families", None) or [])
        bounds = list(getattr(self.cfg, "curriculum_episode_boundaries", None) or [])
        if not stages:
            return self._full_catalog or self._catalog
        stage = 0
        for boundary in bounds:
            if self._episode_i >= int(boundary):
                stage += 1
        stage = min(stage, len(stages) - 1)
        allowed = {str(name) for name in stages[stage]}
        filtered = [(fam, seed) for fam, seed in self._full_catalog if fam in allowed]
        return filtered or self._full_catalog or self._catalog

    def _observe_vector(self) -> np.ndarray:
        assert self._engine is not None and self._builder is not None
        raw = compose_observation(
            self._builder,
            step=self._engine.step,
            n_steps=self._engine.n_steps,
            settled_band=self._engine.settled_band,
            last_target_band=self._engine.last_target,
            last_dwell_steps=self._last_dwell,
            predictor=self.predictor,
            include_predictor_obs=bool(getattr(self.cfg, "include_predictor_obs", False)),
            include_action_history=int(getattr(self.cfg, "include_action_history", 0) or 0),
            default_dwell_steps=int(self.cfg.default_dwell_steps),
            include_neural_predictor_obs=bool(
                getattr(self.cfg, "include_neural_predictor_obs", False)
            ),
        )
        if not self.freeze_obs_stats:
            self.normalizer.update(raw)
        out = self.normalizer.transform(raw)
        if not np.all(np.isfinite(out)):
            raise SmartScanError("Observation contains NaN/Inf.")
        return np.asarray(out, dtype=np.float32)

    def step(self, action: int | np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        if self._engine is None or self._builder is None or self._truth is None:
            raise SmartScanError("env.reset() must be called before step().")
        command = command_from_policy_action(
            action,
            decision_index=self._decision_index,
            n_bands=self._n_bands,
            dwell_bins=self.dwell_bins,
            layout=self._action_layout,
        )
        pred = self.predictor or RecencyPredictor(
            n_bands=self._n_bands,
            horizon_s=float(self.cfg.horizon_steps) * self.cfg.dt_s,
        )
        fc = pred.forecast_next_intercept(
            self._builder,
            band=command.target_band,
            dwell_steps=command.dwell_steps,
            proposed_schedule=[(command.target_band, command.dwell_steps)],
            horizon_s=float(self.cfg.horizon_steps) * self.cfg.dt_s,
            pfa=float(self.receiver.pfa_design),
            dt_s=self.cfg.dt_s,
            step=self._engine.step,
            n_steps=self._engine.n_steps,
            settled_band=self._engine.settled_band,
            last_target_band=self._engine.last_target,
            last_dwell_steps=self._last_dwell,
        )
        if self.record_forecast and not self._horizon_logged:
            horizon = HorizonForecaster(
                n_rollouts=int(self.cfg.mc_rollouts),
                dt_s=self.cfg.dt_s,
                tune_latency_steps=self.receiver.tune_latency_steps,
                pfa=float(self.receiver.pfa_design),
            )

            hz = horizon.forecast(
                self._builder,
                schedule_fn=constant_schedule(int(command.target_band), int(command.dwell_steps)),
                predictor=pred,
                horizon_steps=self.cfg.horizon_steps,
                seed=self.cfg.seed + self._decision_index,
                n_steps=self._engine.n_steps,
                step=self._engine.step,
                settled_band=self._engine.settled_band,
                last_target_band=self._engine.last_target,
                last_dwell_steps=self._last_dwell,
                decision_index=self._decision_index,
            )
            self._horizon_forecast = hz
            self._horizon_logged = True
        result = self._engine.execute_command(command)
        self._obs_rows.extend(result.observations)
        terminated = result.incomplete or self._engine.done()
        truncated = False
        reward = 0.0
        info: dict[str, Any] = {}
        if result.decision is not None:
            settled_before = self._history[-1].target_band if self._history else None
            last_target = self._history[-1].target_band if self._history else None
            tr = transition_from_decision(
                result.decision,
                n_steps=self._engine.n_steps,
                n_bands=self._n_bands,
                dt_s=self.cfg.dt_s,
                settled_band_before=settled_before,
                last_target_band=last_target,
            )
            novelty = 0.0 if self.cfg.ablate_novelty else float(
                self._builder.novelty_est.score(
                    band=tr.target_band,
                    snr_db=tr.measured_snr_db,
                    time_s=float(tr.end_step) * self.cfg.dt_s,
                )
            )
            threat = 1.0 if self.cfg.ablate_priority else assess_threat(
                public_catalog_priority=self._public.get(tr.target_band),
                novelty=novelty,
            )
            low_conf = bool(result.decision.hit) and fc.p_hit_within_dwell < 0.2
            first_hit = is_first_hit_on_visit(self._history, tr)
            coverage = is_coverage_visit(
                self._history,
                tr.target_band,
                int(getattr(self.cfg.reward, "coverage_window", 16) or 16),
            )
            breakdown = self.reward_calc.compute(
                tr,
                p_hit=fc.p_hit_within_dwell,
                novelty=novelty,
                uncertainty=fc.uncertainty,
                assessed_threat=threat,
                recent_same_band_no_hit=recent_same_band_no_hit(self._history, tr.target_band),
                low_confidence_hit=low_conf,
                first_hit_on_visit=first_hit,
                coverage_visit=coverage,
            )
            stamped = stamp_decision_reward(result.decision, breakdown)
            stamped = stamped.model_copy(
                update={
                    "p_hit": fc.p_hit_within_dwell,
                    "p_active": fc.p_active,
                    "time_to_next_completed_intercept_s": fc.time_to_next_completed_intercept_s,
                    "forecast_horizon_s": fc.right_censor_horizon_s,
                    "uncertainty": fc.uncertainty,
                    "model_version": fc.model_version,
                }
            )
            self._dec_rows.append(stamped)
            self._history.append(tr)
            self._builder.observe(tr)
            self._last_dwell = tr.dwell_steps
            self._decision_index += 1
            reward = float(breakdown.reward)
        obs = self._observe_vector()
        if terminated:
            info[f"{ORACLE_INFO_PREFIX}truth_fingerprint"] = self._truth.content_fingerprint
            info[f"{ORACLE_INFO_PREFIX}n_events"] = len(self._truth.events)
        return obs, float(reward), bool(terminated), bool(truncated), info

    def receiver_run(self) -> ReceiverRun:
        if self._engine is None or self._truth is None:
            raise SmartScanError("No episode has been run.")
        obs = ObservationLog(
            rows=list(self._obs_rows),
            ground_truth_fingerprint=self._truth.content_fingerprint,
            receiver_config_hash=self._engine.config_hash,
            dt_s=self.cfg.dt_s,
        )
        dec = DecisionLog(
            rows=list(self._dec_rows),
            ground_truth_fingerprint=self._truth.content_fingerprint,
            receiver_config_hash=self._engine.config_hash,
            dt_s=self.cfg.dt_s,
            receiver_seed=self._engine.receiver_seed,
            n_incomplete_commands=self._engine.incomplete,
        )
        hz = getattr(self, "_horizon_forecast", None)
        if hz is not None:
            dec.predicted_interception_ratio = hz.predicted_interception_ratio
            dec.predicted_intercept_count = hz.predicted_intercept_count
            dec.predicted_opportunity_count = hz.predicted_opportunity_count
            dec.predicted_ratio_ci_low = hz.ci_low
            dec.predicted_ratio_ci_high = hz.ci_high
            dec.forecast_recorded_at_step = 0
            dec.forecast_horizon_steps = hz.horizon_steps
        obs.validate()
        dec.validate()
        return ReceiverRun(observations=obs, decisions=dec)

    def strip_oracle_info(self, info: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in info.items() if not str(k).startswith(ORACLE_INFO_PREFIX)}


def observation_size_for(cfg: TrainConfig) -> tuple[int, int]:
    from smartscan.rf.bands import named_band_plan

    n_bands = named_band_plan(cfg.band_plan_id).n_bands
    size = observation_size(
        n_bands,
        predictor_obs=bool(getattr(cfg, "include_predictor_obs", False)),
        action_history=int(getattr(cfg, "include_action_history", 0) or 0),
    )
    return n_bands, size


def _interleave_by_family(pairs: list[tuple[str, int]]) -> list[tuple[str, int]]:
    grouped: dict[str, list[tuple[str, int]]] = {}
    for family, seed in pairs:
        grouped.setdefault(family, []).append((family, seed))
    out: list[tuple[str, int]] = []
    index = 0
    while True:
        added = False
        for family in sorted(grouped):
            bucket = grouped[family]
            if index < len(bucket):
                out.append(bucket[index])
                added = True
        if not added:
            break
        index += 1
    return out
