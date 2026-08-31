"""Non-oracle baselines and PPO action wrapper. Oracle ceiling is evaluator-only."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from smartscan.ml.actions import decode_action, encode_action, n_actions
from smartscan.ml.periodicity import PeriodicityEstimator
from smartscan.ml.strategy_registry import (
    HELD_OUT_BASELINE_STRATEGIES,
    LIVE_STRATEGIES,
    PERIODIC_INTERCEPT_STRATEGY,
    PUBLIC_STRATEGIES,
    canonicalize_run_strategy,
)
from smartscan.receiver.schedules import (
    FixedPrioritySchedule,
    Schedule,
    ScheduleView,
    SequentialSchedule,
    UniformRandomSchedule,
)
from smartscan.seeding import spawn_generator
from smartscan.types import ScanCommand, SmartScanError

if TYPE_CHECKING:
    from smartscan.ml.features import FeatureBuilder

# Frozen held-out gate baselines. Not the full public UI set.
NON_ORACLE_STRATEGIES = HELD_OUT_BASELINE_STRATEGIES
ORACLE_STRATEGY = "oracle-ceiling"


class ReactiveSchedule:
    """Hit-recency with epsilon exploration of least-recently-visited bands."""

    def __init__(self, dwell_steps: int, seed: int, epsilon: float = 0.2) -> None:
        if dwell_steps <= 0:
            raise SmartScanError("ReactiveSchedule dwell_steps must be positive.")
        self.dwell_steps = int(dwell_steps)
        self.epsilon = float(epsilon)
        self._rng = spawn_generator(seed)
        self._last_visit: dict[int, int] = {}

    def next_command(self, view: ScheduleView) -> ScanCommand:
        if view.n_bands <= 0:
            raise SmartScanError("ScheduleView.n_bands must be positive.")
        dwell = self.dwell_steps if self.dwell_steps in view.dwell_bins else view.default_dwell_steps
        explore = bool(self._rng.random() < self.epsilon) or view.last_hit is not True
        if not explore and view.last_target_band is not None:
            band = int(view.last_target_band)
        else:
            ages = []
            for b in range(view.n_bands):
                ages.append((self._last_visit.get(b, -10_000), b))
            ages.sort()
            band = int(ages[0][1])
        self._last_visit[band] = int(view.step)
        return ScanCommand(
            decision_id=f"d{view.decision_index:05d}",
            target_band=band,
            dwell_steps=int(dwell),
        )


class PeriodicInterceptSchedule:
    """Search the span, then stare at the next estimated illumination.

    The SIH statement asks for an outlined method to intercept a periodic-scan
    emitter. This policy implements that outline from observable hits only:

    1. Visit every band once (rapid coverage of the full span).
    2. Estimate illumination period/phase from hit timestamps.
    3. When the next illumination falls inside the next dwell, stay on that band.
    4. Otherwise revisit the least-recently-scanned band.

    GroundTruth occupancy is never read.
    """

    CONF_MIN = 0.2

    def __init__(self, dwell_steps: int, seed: int = 0) -> None:
        if dwell_steps <= 0:
            raise SmartScanError("PeriodicInterceptSchedule dwell_steps must be positive.")
        self.dwell_steps = int(dwell_steps)
        self.seed = int(seed)
        self._estimator = PeriodicityEstimator(dt_s=0.001)
        self._visited: dict[int, int] = {}
        self._last_ingest_id: str | None = None
        self.last_period_s: float | None = None
        self.last_phase_s: float | None = None
        self.last_confidence: float | None = None
        self.last_mode: str = "search"

    def _ingest(self, view: ScheduleView) -> None:
        self._estimator.dt_s = float(view.dt_s)
        last_id = view.last_decision_id
        if last_id and last_id == self._last_ingest_id:
            return
        if view.last_target_band is not None:
            band = int(view.last_target_band)
            self._visited[band] = int(view.step)
            if view.last_hit is True and view.last_end_step is not None:
                time_s = float(view.last_end_step) * float(view.dt_s)
                self._estimator.observe_hit(band, time_s)
        if last_id:
            self._last_ingest_id = last_id

    def _dwell(self, view: ScheduleView, *, intercept: bool) -> int:
        dwells = tuple(int(x) for x in view.dwell_bins)
        if not dwells:
            raise SmartScanError("PeriodicInterceptSchedule requires nonempty dwell_bins.")
        if intercept and self.dwell_steps in dwells:
            return int(self.dwell_steps)
        if intercept:
            return int(max(dwells))
        return int(min(dwells))

    def next_command(self, view: ScheduleView) -> ScanCommand:
        if view.n_bands <= 0:
            raise SmartScanError("ScheduleView.n_bands must be positive.")
        self._ingest(view)
        now_s = float(view.step) * float(view.dt_s)
        intercept_dwell = self._dwell(view, intercept=True)
        search_dwell = self._dwell(view, intercept=False)
        horizon_s = float(intercept_dwell) * float(view.dt_s)
        unvisited = [band for band in range(view.n_bands) if band not in self._visited]
        # Cover the full span before staring — the statement's first priority.
        if unvisited:
            self.last_period_s = None
            self.last_phase_s = None
            self.last_confidence = None
            self.last_mode = "search"
            return ScanCommand(
                decision_id=f"d{view.decision_index:05d}",
                target_band=int(unvisited[0]),
                dwell_steps=search_dwell,
            )
        best_band: int | None = None
        best_score = -1.0
        best_period = None
        best_phase = None
        best_conf = None
        for band in range(view.n_bands):
            period, phase, conf = self._estimator.estimate(band, now_s)
            if conf < self.CONF_MIN or phase < 0.0:
                continue
            if phase <= horizon_s * 1.25:
                score = float(conf) / max(float(phase), float(view.dt_s))
                if score > best_score:
                    best_score = score
                    best_band = band
                    best_period = float(period)
                    best_phase = float(phase)
                    best_conf = float(conf)
        if best_band is not None:
            band = int(best_band)
            dwell = intercept_dwell
            self.last_period_s = best_period
            self.last_phase_s = best_phase
            self.last_confidence = best_conf
            self.last_mode = "intercept"
        else:
            ages = sorted((self._visited.get(band, -10_000), band) for band in range(view.n_bands))
            band = int(ages[0][1])
            dwell = search_dwell
            period, phase, conf = self._estimator.estimate(band, now_s)
            self.last_period_s = float(period) if period else None
            self.last_phase_s = float(phase) if phase else None
            self.last_confidence = float(conf) if conf else None
            self.last_mode = "fallback"
        return ScanCommand(
            decision_id=f"d{view.decision_index:05d}",
            target_band=band,
            dwell_steps=int(dwell),
        )


class ContextualThompsonSchedule:
    """LinTS over observable per-action features; updates from completed hit/miss only."""

    def __init__(
        self,
        *,
        n_bands: int,
        dwell_bins: tuple[int, ...],
        seed: int,
        feature_dim: int = 8,
        lambda0: float = 1.0,
    ) -> None:
        self.n_bands = int(n_bands)
        self.dwell_bins = tuple(int(x) for x in dwell_bins)
        self._rng = spawn_generator(seed)
        self.d = int(feature_dim)
        n_a = n_actions(self.n_bands, self.dwell_bins)
        self.A = [np.eye(self.d, dtype=np.float64) * float(lambda0) for _ in range(n_a)]
        self.b = [np.zeros(self.d, dtype=np.float64) for _ in range(n_a)]
        self._last_action: int | None = None
        self._last_x: np.ndarray | None = None
        self._last_view_step: int = -1

    def _context(self, view: ScheduleView, band: int, dwell: int) -> np.ndarray:
        x = np.zeros(self.d, dtype=np.float64)
        x[0] = 1.0
        x[1] = float(band) / float(max(view.n_bands, 1))
        x[2] = float(dwell) / float(max(max(view.dwell_bins), 1))
        x[3] = 0.0 if view.last_hit is None else (1.0 if view.last_hit else -1.0)
        x[4] = 0.0 if view.last_target_band is None else float(view.last_target_band == band)
        x[5] = float(view.step) / float(max(view.n_steps, 1))
        x[6] = 0.0 if view.last_measured_snr_db is None else float(view.last_measured_snr_db) / 20.0
        x[7] = 1.0 if view.settled_band == band else 0.0
        return x

    def _update_from_view(self, view: ScheduleView) -> None:
        if self._last_action is None or self._last_x is None:
            return
        if view.last_hit is None:
            return
        if view.decision_index == 0:
            return
        y = 1.0 if view.last_hit else 0.0
        a = self._last_action
        x = self._last_x
        self.A[a] = self.A[a] + np.outer(x, x)
        self.b[a] = self.b[a] + y * x

    def next_command(self, view: ScheduleView) -> ScanCommand:
        self._update_from_view(view)
        best_score = -1e18
        best_action = 0
        for band in range(view.n_bands):
            for dwell in view.dwell_bins:
                action = encode_action(band, int(dwell), view.n_bands, view.dwell_bins)
                x = self._context(view, band, int(dwell))
                try:
                    cov = np.linalg.inv(self.A[action])
                except np.linalg.LinAlgError:
                    cov = np.eye(self.d) * 0.1
                mean = cov @ self.b[action]
                theta = self._rng.multivariate_normal(mean, cov + 1e-6 * np.eye(self.d))
                score = float(x @ theta)
                if score > best_score:
                    best_score = score
                    best_action = action
                    self._last_x = x
        self._last_action = best_action
        band, dwell = decode_action(best_action, view.n_bands, view.dwell_bins)
        return ScanCommand(
            decision_id=f"d{view.decision_index:05d}",
            target_band=band,
            dwell_steps=dwell,
        )

    def state_dict(self) -> dict[str, object]:
        return {
            "A": [m.tolist() for m in self.A],
            "b": [v.tolist() for v in self.b],
            "n_bands": self.n_bands,
            "dwell_bins": list(self.dwell_bins),
            "d": self.d,
        }

    def load_state_dict(self, payload: dict[str, Any]) -> None:
        raw_a = payload["A"]
        raw_b = payload["b"]
        if not isinstance(raw_a, list) or not isinstance(raw_b, list):
            raise SmartScanError("Contextual Thompson state requires A and b lists.")
        self.A = [np.asarray(m, dtype=np.float64) for m in raw_a]
        self.b = [np.asarray(v, dtype=np.float64) for v in raw_b]


class OracleCeilingSchedule:
    """Evaluator-only unattainable ceiling. Never a deployable baseline."""

    def __init__(self, occupied: np.ndarray, dwell_steps: int, label: str = "unattainable") -> None:
        if label != "unattainable":
            raise SmartScanError("Oracle ceiling must be labeled unattainable.")
        self.occupied = np.asarray(occupied, dtype=bool)
        self.dwell_steps = int(dwell_steps)
        self.label = label

    def next_command(self, view: ScheduleView) -> ScanCommand:
        n_steps, n_bands = self.occupied.shape
        start = min(int(view.step), n_steps - 1)
        end = min(n_steps, start + self.dwell_steps)
        scores = self.occupied[start:end].sum(axis=0)
        band = int(np.argmax(scores))
        return ScanCommand(
            decision_id=f"d{view.decision_index:05d}",
            target_band=band,
            dwell_steps=self.dwell_steps,
        )


@dataclass
class PPOPolicySchedule:
    """Deterministic evaluation wrapper around a loaded SB3 policy."""

    n_bands: int
    dwell_bins: tuple[int, ...]
    builder: FeatureBuilder
    predict_fn: object
    last_dwell: int | None = None
    _seen_decision_id: str | None = None
    predictor: Any | None = None
    include_predictor_obs: bool = False
    include_action_history: int = 0
    default_dwell_steps: int = 8
    include_neural_predictor_obs: bool = False

    def next_command(self, view: ScheduleView) -> ScanCommand:
        if (
            view.last_end_step is not None
            and view.last_hit is not None
            and view.last_decision_id
            and view.last_decision_id != self._seen_decision_id
        ):
            from smartscan.ml.observable import ObservableTransition

            self.builder.observe(
                ObservableTransition(
                    decision_id=view.last_decision_id,
                    start_step=int(view.last_start_step or view.step),
                    tune_end_step=int(view.last_start_step or view.step)
                    + int(view.last_tune_cost_steps or 0),
                    end_step=int(view.last_end_step),
                    target_band=int(view.last_target_band or 0),
                    dwell_steps=int(view.last_dwell_steps or view.default_dwell_steps),
                    hit=bool(view.last_hit),
                    measured_snr_db=view.last_measured_snr_db,
                    n_steps=view.n_steps,
                    n_bands=view.n_bands,
                    dt_s=view.dt_s,
                    settled_band_before=view.settled_band,
                    last_target_band=view.last_target_band,
                )
            )
            self._seen_decision_id = view.last_decision_id
        from smartscan.ml.features import compose_observation

        vec = compose_observation(
            self.builder,
            step=view.step,
            n_steps=view.n_steps,
            settled_band=view.settled_band,
            last_target_band=view.last_target_band,
            last_dwell_steps=view.last_dwell_steps
            if view.last_dwell_steps is not None
            else self.last_dwell,
            predictor=self.predictor,
            include_predictor_obs=bool(self.include_predictor_obs),
            include_action_history=int(self.include_action_history or 0),
            default_dwell_steps=int(self.default_dwell_steps),
            include_neural_predictor_obs=bool(self.include_neural_predictor_obs),
        )
        action = int(self.predict_fn(vec))  # type: ignore[operator]
        band, dwell = decode_action(action, self.n_bands, self.dwell_bins)
        self.last_dwell = dwell
        return ScanCommand(
            decision_id=f"d{view.decision_index:05d}",
            target_band=band,
            dwell_steps=dwell,
        )


def make_policy(
    strategy: str,
    *,
    dwell_steps: int,
    schedule_seed: int = 0,
    band_order: tuple[int, ...] | None = None,
    n_bands: int = 16,
    dwell_bins: tuple[int, ...] = (1, 2, 4, 8, 16),
    occupied: np.ndarray | None = None,
    allow_oracle: bool = False,
    ppo_predict: object | None = None,
    feature_builder: FeatureBuilder | None = None,
    predictor: Any | None = None,
    include_predictor_obs: bool = False,
    include_action_history: int = 0,
    include_neural_predictor_obs: bool = False,
) -> Schedule:
    name = canonicalize_run_strategy(strategy, allow_oracle=True)
    if name == "sequential":
        return SequentialSchedule(dwell_steps=dwell_steps)
    if name == "random":
        return UniformRandomSchedule(seed=schedule_seed)
    if name == "fixed-priority":
        if not band_order:
            raise SmartScanError("fixed-priority requires a public band list.")
        return FixedPrioritySchedule(band_order=band_order, dwell_steps=dwell_steps)
    if name == "reactive":
        return ReactiveSchedule(dwell_steps=dwell_steps, seed=schedule_seed)
    if name == PERIODIC_INTERCEPT_STRATEGY:
        return PeriodicInterceptSchedule(dwell_steps=dwell_steps, seed=schedule_seed)
    if name == "contextual-thompson":
        return ContextualThompsonSchedule(
            n_bands=n_bands, dwell_bins=dwell_bins, seed=schedule_seed
        )
    if name == "ppo":
        if ppo_predict is None or feature_builder is None:
            raise SmartScanError("PPO policy requires a loaded bundle predict_fn and FeatureBuilder.")
        return PPOPolicySchedule(
            n_bands=n_bands,
            dwell_bins=dwell_bins,
            builder=feature_builder,
            predict_fn=ppo_predict,
            predictor=predictor,
            include_predictor_obs=bool(include_predictor_obs),
            include_action_history=int(include_action_history or 0),
            default_dwell_steps=int(dwell_steps),
            include_neural_predictor_obs=bool(include_neural_predictor_obs),
        )
    if name in {"oracle-ceiling", "oracle"}:
        if not allow_oracle:
            raise SmartScanError(
                "Oracle ceiling is evaluator-only and is not a deployable baseline."
            )
        if occupied is None:
            raise SmartScanError("Oracle ceiling requires evaluator occupancy.")
        return OracleCeilingSchedule(occupied=occupied, dwell_steps=dwell_steps)
    raise SmartScanError(f"Unknown strategy {strategy!r}.")


def construct_live_policy(
    strategy: str,
    *,
    dwell_steps: int,
    schedule_seed: int = 0,
    band_order: tuple[int, ...] | None = None,
    n_bands: int = 16,
    dwell_bins: tuple[int, ...] = (1, 2, 4, 8, 16),
    dt_s: float = 0.001,
    tune_latency_steps: int = 1,
    public_priorities: tuple[int, ...] | None = None,
    model_dir: Path | str | None = None,
    occupied: np.ndarray | None = None,
    allow_oracle: bool = False,
    ewma_alpha: float = 0.3,
) -> Schedule:
    """Build a public strategy. PPO loads the bundle from *model_dir* only when selected."""

    name = canonicalize_run_strategy(strategy, allow_oracle=True)
    if name not in PUBLIC_STRATEGIES and name != ORACLE_STRATEGY:
        raise SmartScanError(f"Unknown strategy {strategy!r}.")
    ppo_predict = None
    feature_builder = None
    if name == "ppo":
        if model_dir is None:
            raise SmartScanError(
                "PPO bundle not found. Select a baseline or run train-scheduler."
            )
        dest = Path(model_dir)
        if not dest.is_dir():
            raise SmartScanError(
                f"PPO bundle not found at {dest}. Select a baseline or run train-scheduler."
            )
        from smartscan.ml.bundle import load_bundle, ppo_predict_fn
        from smartscan.ml.features import FeatureBuilder

        bundle = load_bundle(dest)
        ppo_predict = ppo_predict_fn(bundle)
        cfg = bundle.config if isinstance(bundle.config, dict) else {}
        include_predictor_obs = bool(cfg.get("include_predictor_obs", False))
        include_action_history = int(cfg.get("include_action_history") or 0)
        include_neural_predictor_obs = bool(cfg.get("include_neural_predictor_obs", False))
        predictor = None
        if bundle.predictor is not None:
            from smartscan.ml.predictor import BuilderBackedHazardPredictor

            predictor = BuilderBackedHazardPredictor(bundle.predictor)
        prios = public_priorities if public_priorities is not None else ()
        feature_builder = FeatureBuilder(
            n_bands=n_bands,
            dt_s=float(dt_s),
            dwell_bins=tuple(int(x) for x in dwell_bins),
            ewma_alpha=float(cfg.get("ewma_alpha", ewma_alpha)),
            tune_latency_steps=int(tune_latency_steps),
            ablate_periodicity=bool(cfg.get("ablate_periodicity", False)),
            ablate_novelty=bool(cfg.get("ablate_novelty", False)),
            public_priorities={int(b): 2.0 for b in prios},
        )
    else:
        include_predictor_obs = False
        include_action_history = 0
        include_neural_predictor_obs = False
        predictor = None
    order = band_order if band_order is not None else public_priorities
    if name != "ppo" and name != ORACLE_STRATEGY and name not in LIVE_STRATEGIES:
        raise SmartScanError(f"Unknown strategy {strategy!r}.")
    return make_policy(
        name,
        dwell_steps=dwell_steps,
        schedule_seed=schedule_seed,
        band_order=order,
        n_bands=n_bands,
        dwell_bins=dwell_bins,
        occupied=occupied,
        allow_oracle=allow_oracle,
        ppo_predict=ppo_predict,
        feature_builder=feature_builder,
        predictor=predictor,
        include_predictor_obs=include_predictor_obs,
        include_action_history=include_action_history,
        include_neural_predictor_obs=include_neural_predictor_obs,
    )
