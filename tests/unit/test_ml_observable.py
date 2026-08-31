from __future__ import annotations

import numpy as np
import pytest

from smartscan.ml.actions import decode_action, encode_action, n_actions
from smartscan.ml.calibrate import IsotonicCalibrator
from smartscan.ml.features import FeatureBuilder
from smartscan.ml.observable import ExplodingOracle, ObservableTransition, assert_no_oracle_payload
from smartscan.ml.predictor import expected_time_to_hit, survival_nll
from smartscan.ml.reward import RewardCalculator, recent_same_band_no_hit
from smartscan.types import SmartScanError, is_evaluator_only_key


def _tr(**kwargs: object) -> ObservableTransition:
    payload: dict[str, object] = {
        "decision_id": "d0",
        "start_step": 0,
        "tune_end_step": 1,
        "end_step": 9,
        "target_band": 3,
        "dwell_steps": 8,
        "hit": True,
        "measured_snr_db": 6.0,
        "n_steps": 200,
        "n_bands": 16,
        "dt_s": 0.001,
        "settled_band_before": None,
        "last_target_band": None,
    }
    payload.update(kwargs)
    return ObservableTransition(**payload)  # type: ignore[arg-type]


def test_oracle_keys_and_exploding_object() -> None:
    assert is_evaluator_only_key("occupied")
    assert is_evaluator_only_key("oracle_truth_fingerprint")
    assert not is_evaluator_only_key("hit")
    boom = ExplodingOracle()
    with pytest.raises(RuntimeError, match="oracle leak"):
        _ = boom.occupied
    with pytest.raises(SmartScanError):
        assert_no_oracle_payload({"oracle_events": 1}, where="info")
    assert_no_oracle_payload({"hit": True}, where="info")
    _ = boom.__class__
    assert _tr().elapsed_fraction >= 0.0
    assert _tr().remaining_horizon_steps >= 0


def test_feature_builder_ignores_exploding_truth() -> None:
    builder = FeatureBuilder(n_bands=16, dt_s=0.001, dwell_bins=(1, 2, 4, 8, 16))
    truth = ExplodingOracle()
    history = [_tr(end_step=9, hit=True), _tr(decision_id="d1", start_step=9, tune_end_step=9, end_step=17, target_band=3, hit=False)]
    for item in history:
        builder.observe(item)
    vec = builder.vector(
        step=17, n_steps=200, settled_band=3, last_target_band=3, last_dwell_steps=8
    )
    assert vec.dtype == np.float32
    assert np.all(np.isfinite(vec))
    with pytest.raises(RuntimeError):
        _ = truth.events
    with pytest.raises(SmartScanError):
        FeatureBuilder(n_bands=0, dt_s=0.001, dwell_bins=(8,))
    builder.reset()
    with pytest.raises(SmartScanError):
        builder.observe(_tr(n_bands=4, target_band=99))



def test_causality_future_rows_do_not_change_past_features() -> None:
    builder = FeatureBuilder(n_bands=16, dt_s=0.001, dwell_bins=(1, 2, 4, 8, 16))
    past = [_tr(), _tr(decision_id="d1", start_step=9, tune_end_step=9, end_step=17, target_band=1, hit=False)]
    for item in past:
        builder.observe(item)
    snap = builder.snapshot()
    v1 = snap.vector(step=17, n_steps=200, settled_band=1, last_target_band=1, last_dwell_steps=8)
    future = _tr(decision_id="d2", start_step=17, tune_end_step=18, end_step=26, target_band=8, hit=True)
    builder.observe(future)
    v2 = snap.vector(step=17, n_steps=200, settled_band=1, last_target_band=1, last_dwell_steps=8)
    assert np.allclose(v1, v2)


def test_unvisited_bands_are_masked_not_zero_hits() -> None:
    builder = FeatureBuilder(n_bands=4, dt_s=0.001, dwell_bins=(4, 8))
    builder.observe(_tr(n_bands=4, target_band=1, hit=True))
    vec = builder.vector(step=9, n_steps=50, settled_band=1, last_target_band=1, last_dwell_steps=8)
    # per-band block is 18 fields; band 0 visit mask is index 1
    assert vec[1] == pytest.approx(1.0)  # unvisited mask
    assert vec[18 + 1] == pytest.approx(0.0)  # band 1 visited


def test_reward_uses_only_observable_terms() -> None:
    calc = RewardCalculator()
    br = calc.compute(
        _tr(),
        p_hit=0.7,
        novelty=0.2,
        uncertainty=0.1,
        assessed_threat=1.0,
        recent_same_band_no_hit=False,
        low_confidence_hit=False,
    )
    assert np.isfinite(br.reward)
    assert br.reward_hit == pytest.approx(1.0)
    assert recent_same_band_no_hit([_tr(hit=False, target_band=3)], 3) is True


def test_action_codec() -> None:
    bins = (1, 2, 4, 8, 16)
    assert n_actions(16, bins) == 80
    band, dwell = decode_action(8 * 5 + 3, 16, bins)
    assert band == 8 and dwell == 8
    assert encode_action(8, 8, 16, bins) == 8 * 5 + 3
    with pytest.raises(SmartScanError):
        decode_action(99, 2, (1, 2))


def test_survival_golden_cases() -> None:
    h = np.array([0.2, 0.3, 0.4], dtype=np.float64)
    hit0 = float(survival_nll(h, 0))
    hit1 = float(survival_nll(h, 1))
    hit2 = float(survival_nll(h, 2))
    cens = float(survival_nll(h, None))
    assert np.isfinite([hit0, hit1, hit2, cens]).all()
    # Hit at bin 0 is -log(h0); censor is -sum log(1-h)
    assert hit0 == pytest.approx(-np.log(0.2))
    assert cens == pytest.approx(-np.sum(np.log(1.0 - h)))
    with pytest.raises(SmartScanError):
        survival_nll(h, 9)
    t_hat, mass = expected_time_to_hit(h, np.array([0.1, 0.2, 0.3]))
    assert 0.1 <= t_hat <= 0.3
    assert 0.0 < mass <= 1.0 + 1e-9


def test_isotonic_is_monotonic() -> None:
    p = np.linspace(0.1, 0.9, 20)
    y = (p > 0.5).astype(np.float64)
    cal = IsotonicCalibrator.fit(p, y)
    out = cal.predict(p)
    assert np.all(np.diff(out) >= -1e-9)
    assert np.all((out >= 0.0) & (out <= 1.0))
