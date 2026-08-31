"""Run any Stage 5 policy through the Stage 2 receiver and stamp forecasts."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from smartscan.config import TrainConfig
from smartscan.metrics.engine import evaluate_strategy
from smartscan.ml.features import FeatureBuilder
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
from smartscan.receiver.logs import DecisionLog, ObservationLog, ReceiverRun
from smartscan.receiver.scanner import ReceiverEngine
from smartscan.types import DecisionRow, GroundTruth, ObservationRow, ReceiverConfig


def constant_schedule(band: int, dwell: int) -> Callable[[FeatureBuilder, int, int], tuple[int, int]]:
    def _inner(fb: FeatureBuilder, idx: int, t: int) -> tuple[int, int]:
        del fb, idx, t
        return int(band), int(dwell)

    return _inner


def run_policy_episode(
    truth: GroundTruth,
    schedule: Any,
    receiver: ReceiverConfig,
    *,
    cfg: TrainConfig,
    receiver_seed: int,
    predictor: Any | None = None,
    record_horizon: bool = True,
) -> ReceiverRun:
    engine = ReceiverEngine(truth=truth, config=receiver, receiver_seed=receiver_seed)
    dwell_bins = tuple(int(x) for x in cfg.dwell_bins)
    builder = FeatureBuilder(
        n_bands=truth.band_plan.n_bands,
        dt_s=truth.dt_s,
        dwell_bins=dwell_bins,
        ewma_alpha=cfg.ewma_alpha,
        tune_latency_steps=receiver.tune_latency_steps,
        ablate_periodicity=cfg.ablate_periodicity,
        ablate_novelty=cfg.ablate_novelty,
        public_priorities={int(b): 2.0 for b in cfg.public_priorities},
    )
    pred = predictor or RecencyPredictor(
        n_bands=truth.band_plan.n_bands,
        horizon_s=float(cfg.horizon_steps) * cfg.dt_s,
    )
    reward_calc = RewardCalculator(cfg.reward)
    observations: list[ObservationRow] = []
    decisions: list[DecisionRow] = []
    history: list[ObservableTransition] = []
    decision_index = 0
    last_dwell: int | None = None
    horizon_payload = None
    public = {int(b): 2.0 for b in cfg.public_priorities}

    while not engine.done():
        view = engine.schedule_view(decision_index, cfg.default_dwell_steps)
        try:
            command = schedule.next_command(view)
        except StopIteration:
            break
        if record_horizon and horizon_payload is None:
            horizon_payload = HorizonForecaster(
                n_rollouts=int(cfg.mc_rollouts),
                dt_s=cfg.dt_s,
                tune_latency_steps=receiver.tune_latency_steps,
                pfa=float(receiver.pfa_design),
            ).forecast(
                builder,
                schedule_fn=constant_schedule(int(command.target_band), int(command.dwell_steps)),
                predictor=pred,
                horizon_steps=cfg.horizon_steps,
                seed=cfg.seed,
                n_steps=engine.n_steps,
                step=engine.step,
                settled_band=engine.settled_band,
                last_target_band=engine.last_target,
                last_dwell_steps=last_dwell,
                decision_index=decision_index,
            )
        fc = pred.forecast_next_intercept(
            builder,
            band=command.target_band,
            dwell_steps=command.dwell_steps,
            proposed_schedule=[(command.target_band, command.dwell_steps)],
            horizon_s=float(cfg.horizon_steps) * cfg.dt_s,
            pfa=float(receiver.pfa_design),
            dt_s=cfg.dt_s,
            step=engine.step,
            n_steps=engine.n_steps,
            settled_band=engine.settled_band,
            last_target_band=engine.last_target,
            last_dwell_steps=last_dwell,
        )
        result = engine.execute_command(command)
        observations.extend(result.observations)
        if result.decision is not None:
            settled_before = history[-1].target_band if history else None
            last_target = history[-1].target_band if history else None
            tr = transition_from_decision(
                result.decision,
                n_steps=engine.n_steps,
                n_bands=engine.n_bands,
                dt_s=cfg.dt_s,
                settled_band_before=settled_before,
                last_target_band=last_target,
            )
            novelty = float(
                builder.novelty_est.score(
                    band=tr.target_band,
                    snr_db=tr.measured_snr_db,
                    time_s=float(tr.end_step) * cfg.dt_s,
                )
            )
            threat = assess_threat(
                public_catalog_priority=public.get(tr.target_band), novelty=novelty
            )
            breakdown = reward_calc.compute(
                tr,
                p_hit=fc.p_hit_within_dwell,
                novelty=novelty,
                uncertainty=fc.uncertainty,
                assessed_threat=threat,
                recent_same_band_no_hit=recent_same_band_no_hit(history, tr.target_band),
                low_confidence_hit=bool(tr.hit) and fc.p_hit_within_dwell < 0.2,
                first_hit_on_visit=is_first_hit_on_visit(history, tr),
                coverage_visit=is_coverage_visit(
                    history,
                    tr.target_band,
                    int(getattr(cfg.reward, "coverage_window", 16) or 16),
                ),
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
            decisions.append(stamped)
            builder.observe(tr)
            history.append(tr)
            last_dwell = tr.dwell_steps
            decision_index += 1
        if result.incomplete:
            break

    obs_log = ObservationLog(
        rows=observations,
        ground_truth_fingerprint=truth.content_fingerprint,
        receiver_config_hash=engine.config_hash,
        dt_s=truth.dt_s,
    )
    dec_log = DecisionLog(
        rows=decisions,
        ground_truth_fingerprint=truth.content_fingerprint,
        receiver_config_hash=engine.config_hash,
        dt_s=truth.dt_s,
        receiver_seed=receiver_seed,
        n_incomplete_commands=engine.incomplete,
    )
    if horizon_payload is not None:
        dec_log.predicted_interception_ratio = horizon_payload.predicted_interception_ratio
        dec_log.predicted_intercept_count = horizon_payload.predicted_intercept_count
        dec_log.predicted_opportunity_count = horizon_payload.predicted_opportunity_count
        dec_log.predicted_ratio_ci_low = horizon_payload.ci_low
        dec_log.predicted_ratio_ci_high = horizon_payload.ci_high
        dec_log.forecast_recorded_at_step = 0
        dec_log.forecast_horizon_steps = horizon_payload.horizon_steps
    obs_log.validate()
    dec_log.validate()
    return ReceiverRun(observations=obs_log, decisions=dec_log)


def evaluate_episode(
    truth: GroundTruth,
    run: ReceiverRun,
    receiver: ReceiverConfig,
) -> Any:
    return evaluate_strategy(truth, run.observations, run.decisions, receiver_config=receiver)
