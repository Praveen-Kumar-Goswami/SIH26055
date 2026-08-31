"""Horizon interception-ratio forecast from observable q_hit / hazards only."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from smartscan.ml.features import FeatureBuilder
from smartscan.ml.observable import ObservableTransition
from smartscan.seeding import spawn_generator
from smartscan.types import SmartScanError

ScheduleFn = Callable[[FeatureBuilder, int, int], tuple[int, int]]


@dataclass(frozen=True)
class HorizonForecast:
    predicted_interception_ratio: float
    predicted_intercept_count: float
    predicted_opportunity_count: float
    ci_low: float
    ci_high: float
    n_rollouts: int
    horizon_steps: int
    seed: int


def _clip01(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


class HorizonForecaster:
    """Monte Carlo rollouts of a proposed policy using the predictor, not GroundTruth."""

    def __init__(
        self,
        *,
        n_rollouts: int = 128,
        dt_s: float,
        tune_latency_steps: int,
        pfa: float = 1e-3,
    ) -> None:
        if n_rollouts <= 0:
            raise SmartScanError("n_rollouts must be positive.")
        self.n_rollouts = int(n_rollouts)
        self.dt_s = float(dt_s)
        self.tune_latency_steps = int(tune_latency_steps)
        self.pfa = float(pfa)

    def forecast(
        self,
        builder: FeatureBuilder,
        *,
        schedule_fn: ScheduleFn,
        predictor: Any,
        horizon_steps: int,
        seed: int,
        n_steps: int,
        step: int,
        settled_band: int | None,
        last_target_band: int | None,
        last_dwell_steps: int | None,
        decision_index: int,
    ) -> HorizonForecast:
        rng = spawn_generator(seed)
        intercepts: list[float] = []
        opportunities: list[float] = []
        ratios: list[float] = []
        horizon_s = float(horizon_steps) * self.dt_s
        for _ in range(self.n_rollouts):
            replica = builder.snapshot()
            t = int(step)
            settled = settled_band
            last_b = last_target_band
            last_d = last_dwell_steps
            n_hit = 0.0
            n_opp = 0.0
            idx = int(decision_index)
            while t < int(step) + int(horizon_steps) and t < int(n_steps):
                band, dwell = schedule_fn(replica, idx, t)
                fc = predictor.forecast_next_intercept(
                    replica,
                    band=band,
                    dwell_steps=dwell,
                    proposed_schedule=[(band, dwell)],
                    horizon_s=horizon_s,
                    pfa=self.pfa,
                    dt_s=self.dt_s,
                    step=t,
                    n_steps=n_steps,
                    settled_band=settled,
                    last_target_band=last_b,
                    last_dwell_steps=last_d,
                )
                hit = bool(rng.random() < fc.p_hit_within_dwell)
                n_hit += 1.0 if hit else 0.0
                n_opp += float(fc.p_active) if fc.p_active is not None else fc.p_hit_within_dwell
                tune = 0 if settled == band else self.tune_latency_steps
                end = t + int(tune) + int(dwell)
                fake = ObservableTransition(
                    decision_id=f"mc{idx:05d}",
                    start_step=t,
                    tune_end_step=t + int(tune),
                    end_step=end,
                    target_band=int(band),
                    dwell_steps=int(dwell),
                    hit=hit,
                    measured_snr_db=None,
                    n_steps=n_steps,
                    n_bands=replica.n_bands,
                    dt_s=self.dt_s,
                    settled_band_before=settled,
                    last_target_band=last_b,
                )
                replica.observe(fake)
                settled = int(band)
                last_b = int(band)
                last_d = int(dwell)
                t = end
                idx += 1
            intercepts.append(n_hit)
            opportunities.append(max(n_opp, 1e-6))
            ratios.append(_clip01(n_hit / max(n_opp, 1e-6)))
        arr = np.asarray(ratios, dtype=np.float64)
        mean_ratio = _clip01(float(np.mean(arr)))
        low = _clip01(float(np.quantile(arr, 0.05)))
        high = _clip01(float(np.quantile(arr, 0.95)))
        return HorizonForecast(
            predicted_interception_ratio=mean_ratio,
            predicted_intercept_count=float(np.mean(intercepts)),
            predicted_opportunity_count=float(np.mean(opportunities)),
            ci_low=min(low, high),
            ci_high=max(low, high),
            n_rollouts=self.n_rollouts,
            horizon_steps=int(horizon_steps),
            seed=int(seed),
        )


def naive_ratio_forecast(n_bands: int, horizon_commands: int) -> float:
    """Uniform-visit naive ratio used as the non-learned baseline."""

    if n_bands <= 0 or horizon_commands <= 0:
        return 0.0
    return _clip01(float(horizon_commands) / float(n_bands + horizon_commands))
