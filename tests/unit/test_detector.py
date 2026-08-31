from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

from smartscan.receiver.detector import (
    analytic_pd,
    db_to_linear,
    detect,
    detection_threshold,
    equivalent_samples,
    linear_to_db,
    load_receiver_config,
    measured_snr_db,
    noise_power_w,
    noncentrality,
    physical_latency_steps,
    rho_from_power,
    sample_energy,
)
from smartscan.types import ReceiverConfig, SmartScanError


def test_threshold_matches_scipy() -> None:
    for m_samples in (1, 4, 8, 16, 64):
        for pfa in (1e-3, 1e-4, 0.01):
            got = detection_threshold(m_samples, pfa)
            expected = float(stats.gamma.ppf(1.0 - pfa, a=m_samples, scale=1.0))
            assert got == pytest.approx(expected, rel=0, abs=1e-12)


def test_analytic_pd_matches_ncx2() -> None:
    m_samples = 8
    pfa = 1e-3
    threshold = detection_threshold(m_samples, pfa)
    for rho in (0.0, 0.5, 1.0, 3.0, 10.0):
        got = analytic_pd(rho, m_samples, pfa)
        expected = float(stats.ncx2.sf(2.0 * threshold, df=2 * m_samples, nc=2.0 * m_samples * rho))
        assert got == pytest.approx(expected, rel=0, abs=1e-12)
    assert analytic_pd(0.0, m_samples, pfa) == pytest.approx(pfa, rel=0.05, abs=1e-4)


def test_pfa_monte_carlo_binomial_ci() -> None:
    """Predeclared: n=40000, M=8, pfa=1e-3, seed=12345. CI must contain pfa_design."""

    rng = np.random.default_rng(12345)
    dwell_steps = 8
    samples_per_step = 1
    m_samples = 8
    pfa = 1e-3
    n_trials = 40_000
    hits = 0
    zeros = np.zeros(dwell_steps)
    for _ in range(n_trials):
        energy = sample_energy(
            rng, zeros, samples_per_step=samples_per_step, dwell_steps=dwell_steps
        )
        if energy >= detection_threshold(m_samples, pfa):
            hits += 1
    ci = stats.binomtest(hits, n_trials).proportion_ci(confidence_level=0.95)
    assert ci.low <= pfa <= ci.high


def test_strong_signal_pd_approaches_analytic() -> None:
    rng = np.random.default_rng(7)
    dwell_steps = 8
    rho = 8.0
    m_samples = 8
    pfa = 1e-3
    expected = analytic_pd(rho, m_samples, pfa)
    n_trials = 8_000
    hits = 0
    rho_vec = np.full(dwell_steps, rho)
    for _ in range(n_trials):
        energy = sample_energy(rng, rho_vec, samples_per_step=1, dwell_steps=dwell_steps)
        if energy >= detection_threshold(m_samples, pfa):
            hits += 1
    estimate = hits / n_trials
    assert abs(estimate - expected) < 0.03
    assert expected > 0.9


def test_partial_dwell_noncentrality() -> None:
    rho = np.array([0.0, 0.0, 5.0, 5.0])
    nc = noncentrality(rho, samples_per_step=2)
    # 2 * sps * sum(rho) = 2*2*10 = 40, not 2*M*max(rho)
    assert nc == pytest.approx(40.0)
    m_samples = 2 * 4
    rho_eff = float(np.mean(rho))
    assert 2 * m_samples * rho_eff == pytest.approx(40.0)


def test_db_round_trip() -> None:
    for linear in (1e-12, 1e-3, 1.0, 20.0):
        assert db_to_linear(linear_to_db(linear)) == pytest.approx(linear, rel=1e-12)
    with pytest.raises(SmartScanError):
        linear_to_db(0.0)
    with pytest.raises(SmartScanError):
        db_to_linear(float("nan"))


def test_physical_noise_power() -> None:
    cfg = ReceiverConfig(
        receiver_ibw_hz=1e8,
        scan_span_hz=16e9,
        noise_mode="physical",
        temperature_k=290.0,
        noise_figure_db=3.0,
    )
    noise = noise_power_w(cfg)
    expected = 1.380649e-23 * 290.0 * 1e8 * (10 ** (3.0 / 10.0))
    assert noise == pytest.approx(expected, rel=1e-12)
    assert noise > 0


def test_physical_latency_rejects_non_integer() -> None:
    assert physical_latency_steps(0.001, 0.001) == 1
    with pytest.raises(SmartScanError, match="not an integer"):
        physical_latency_steps(0.0015, 0.001)


def test_normalized_noise_default_and_override() -> None:
    cfg = ReceiverConfig(receiver_ibw_hz=1e8, scan_span_hz=16e9)
    assert noise_power_w(cfg) == 1.0
    cfg2 = ReceiverConfig(receiver_ibw_hz=1e8, scan_span_hz=16e9, noise_power_w=2.5)
    assert noise_power_w(cfg2) == 2.5


def test_load_receiver_config_accepts_dict_and_model() -> None:
    cfg = ReceiverConfig(receiver_ibw_hz=1e8, scan_span_hz=16e9, dwell_bins=(1, 2, 4))
    assert load_receiver_config(cfg) is cfg
    loaded = load_receiver_config(
        {
            "receiver_ibw_hz": 1e8,
            "scan_span_hz": 16e9,
            "dwell_bins": [1, 2, 4, 8, 16],
        }
    )
    assert loaded.dwell_bins == (1, 2, 4, 8, 16)
    loaded_tuple = load_receiver_config(
        {
            "receiver_ibw_hz": 1e8,
            "scan_span_hz": 16e9,
            "dwell_bins": (1, 2),
        }
    )
    assert loaded_tuple.dwell_bins == (1, 2)


def test_detector_rejects_invalid_inputs() -> None:
    cfg = ReceiverConfig(receiver_ibw_hz=1e8, scan_span_hz=16e9)
    with pytest.raises(SmartScanError, match="dwell_steps must be positive"):
        equivalent_samples(cfg, 0)
    with pytest.raises(SmartScanError, match="M must be positive"):
        detection_threshold(0, 1e-3)
    with pytest.raises(SmartScanError, match="pfa_design"):
        detection_threshold(8, 0.0)
    rng = np.random.default_rng(0)
    with pytest.raises(SmartScanError, match="does not match"):
        sample_energy(rng, np.zeros(2), samples_per_step=1, dwell_steps=4)
    with pytest.raises(SmartScanError, match="nonnegative"):
        sample_energy(rng, np.array([-1.0, 0.0]), samples_per_step=1, dwell_steps=2)
    with pytest.raises(SmartScanError, match="noise_power_w"):
        rho_from_power(np.array([1.0]), 0.0)
    with pytest.raises(SmartScanError, match="noise_power_w"):
        rho_from_power(np.array([1.0]), float("nan"))
    assert np.allclose(rho_from_power(np.array([2.0, 4.0]), 2.0), [1.0, 2.0])
    assert measured_snr_db(1.0, 0) is None
    assert measured_snr_db(float("nan"), 8) is None
    assert measured_snr_db(4.0, 8) is None  # Z/M - 1 <= 0
    assert measured_snr_db(16.0, 8) == pytest.approx(linear_to_db(1.0))
    energy = sample_energy(rng, np.zeros(4), samples_per_step=1, dwell_steps=4)
    assert detect(energy, 4, 1e-3) in {True, False}


def test_nonfinite_threshold_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "smartscan.receiver.detector.stats.gamma.ppf",
        lambda *args, **kwargs: float("nan"),
    )
    with pytest.raises(SmartScanError, match="non-finite"):
        detection_threshold(8, 1e-3)
