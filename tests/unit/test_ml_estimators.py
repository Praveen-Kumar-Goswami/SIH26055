from __future__ import annotations

import pytest

from smartscan.ml.features import FeatureBuilder
from smartscan.ml.forecast import HorizonForecaster, naive_ratio_forecast
from smartscan.ml.novelty import AgilityEstimator, NoveltyEstimator
from smartscan.ml.periodicity import PeriodicityEstimator
from smartscan.ml.predictor import RecencyPredictor, derive_p_active
from smartscan.types import SmartScanError


def test_periodicity_recovers_regular_hits() -> None:
    est = PeriodicityEstimator(dt_s=0.001, max_period_s=2.0)
    period_s = 0.20
    for i in range(8):
        est.observe_hit(3, i * period_s)
    period, phase, conf = est.estimate(3, now_s=8 * period_s)
    assert period == pytest.approx(period_s, rel=0.15)
    assert conf > 0.2
    assert 0.0 <= phase <= period_s * 1.5


def test_agility_from_observable_hops_only() -> None:
    est = AgilityEstimator(n_bands=4)
    for band in (0, 1, 0, 1, 0, 1):
        est.observe_hit(band)
    scores = est.next_scores()
    assert scores.shape == (4,)
    # Last hit is band 1; observed hops from 1 are to 0, not to 2.
    assert scores[0] > scores[2]


def test_novelty_bounded() -> None:
    est = NoveltyEstimator(n_bands=8)
    for i in range(10):
        est.observe(band=0, hit=True, time_s=0.01 * i, snr_db=5.0)
    usual = est.score(band=0, snr_db=5.0, time_s=0.12)
    unusual = est.score(band=7, snr_db=20.0, time_s=5.0)
    assert 0.0 <= usual <= 1.0
    assert 0.0 <= unusual <= 1.0
    assert unusual >= usual


def test_p_active_distinct_from_p_hit() -> None:
    p_act, reason = derive_p_active(0.5, pd_operating=0.9, pfa=0.001)
    assert p_act is not None and reason is None
    assert p_act != 0.5
    none, why = derive_p_active(0.5, pd_operating=0.001, pfa=0.001)
    assert none is None
    assert why == "pd_operating_leq_pfa"


def test_horizon_forecast_deterministic_and_bounded() -> None:
    builder = FeatureBuilder(n_bands=8, dt_s=0.001, dwell_bins=(4, 8))
    pred = RecencyPredictor(n_bands=8, horizon_s=0.08)
    hz = HorizonForecaster(n_rollouts=16, dt_s=0.001, tune_latency_steps=1, pfa=0.001)

    def sched(fb: FeatureBuilder, idx: int, t: int) -> tuple[int, int]:
        del fb, t
        return idx % 8, 8

    a = hz.forecast(
        builder,
        schedule_fn=sched,
        predictor=pred,
        horizon_steps=40,
        seed=7,
        n_steps=200,
        step=0,
        settled_band=None,
        last_target_band=None,
        last_dwell_steps=None,
        decision_index=0,
    )
    b = hz.forecast(
        builder,
        schedule_fn=sched,
        predictor=pred,
        horizon_steps=40,
        seed=7,
        n_steps=200,
        step=0,
        settled_band=None,
        last_target_band=None,
        last_dwell_steps=None,
        decision_index=0,
    )
    assert a.predicted_interception_ratio == b.predicted_interception_ratio
    assert 0.0 <= a.predicted_interception_ratio <= 1.0
    naive = naive_ratio_forecast(8, 5)
    assert 0.0 <= naive <= 1.0
    assert naive_ratio_forecast(0, 5) == 0.0


def test_periodicity_autocorr_fallback_and_invalid_time() -> None:
    est = PeriodicityEstimator(dt_s=0.001, max_period_s=0.05)
    for i in range(6):
        est.observe_hit(0, float(i) * 0.2)
    period, phase, conf = est.estimate(0, now_s=1.4)
    assert period >= 0.0
    assert phase >= 0.0
    assert 0.0 <= conf <= 1.0
    empty = PeriodicityEstimator(dt_s=0.001)
    assert empty.estimate(3, now_s=1.0) == (0.0, 0.0, 0.0)
    with pytest.raises(SmartScanError):
        est.observe_hit(0, float("nan"))
