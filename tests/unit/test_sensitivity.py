from __future__ import annotations

import numpy as np
import pytest

from smartscan.metrics.sensitivity import (
    analytic_sensitivity_curve,
    analytic_snr_db_at_target_pd,
    interpolate_snr_db,
    rho_to_receiver_input_dbm,
    run_sensitivity_sweep,
)
from smartscan.receiver.detector import analytic_pd, noise_power_w
from smartscan.types import ReceiverConfig, SmartScanError


def test_sensitivity_matches_analytic_and_is_monotone() -> None:
    m_samples = 8
    pfa = 1e-3
    low = analytic_snr_db_at_target_pd(0.50, m_samples=m_samples, pfa_design=pfa)
    high = analytic_snr_db_at_target_pd(0.90, m_samples=m_samples, pfa_design=pfa)
    assert high > low
    looser = analytic_snr_db_at_target_pd(0.90, m_samples=m_samples, pfa_design=0.01)
    assert looser < high
    rho = 10.0 ** (high / 10.0)
    assert analytic_pd(rho, m_samples, pfa) == pytest.approx(0.90, abs=5e-4)
    curve = analytic_sensitivity_curve(target_pd=0.90, m_samples=m_samples, pfa_design=pfa)
    assert curve.snr_db_at_target == pytest.approx(high, abs=1e-6)
    analytic_vals = [point.pd_analytic for point in curve.points]
    assert analytic_vals == sorted(analytic_vals)


def test_physical_mode_reports_dbm() -> None:
    cfg = ReceiverConfig(
        receiver_ibw_hz=1e8,
        scan_span_hz=16e9,
        noise_mode="physical",
        temperature_k=290.0,
        noise_figure_db=3.0,
    )
    curve = analytic_sensitivity_curve(
        target_pd=0.90, m_samples=8, pfa_design=1e-3, receiver_config=cfg
    )
    assert curve.receiver_input_dbm is not None
    rho = 10.0 ** (curve.snr_db_at_target / 10.0)
    expected = rho_to_receiver_input_dbm(rho, cfg)
    assert curve.receiver_input_dbm == pytest.approx(expected)
    noise = noise_power_w(cfg)
    assert expected == pytest.approx(10.0 * np.log10(rho * noise * 1000.0))


def test_monte_carlo_curve_near_analytic() -> None:
    grid = (-2.0, 2.0, 6.0, 10.0, 14.0)
    curve = run_sensitivity_sweep(
        target_pd=0.90,
        m_samples=8,
        pfa_design=1e-3,
        seed=12345,
        n_trials=400,
        snr_db_grid=grid,
        monte_carlo=True,
    )
    hats = [point.pd_hat for point in curve.points]
    assert all(item is not None for item in hats)
    assert hats == sorted(hats)  # isotonic accumulate
    analytic = analytic_snr_db_at_target_pd(0.90, m_samples=8, pfa_design=1e-3)
    assert abs(curve.snr_db_at_target - analytic) < 1.5


def test_sensitivity_rejects_bad_target() -> None:
    with pytest.raises(SmartScanError):
        analytic_snr_db_at_target_pd(1e-6, m_samples=8, pfa_design=1e-3)
    with pytest.raises(SmartScanError):
        interpolate_snr_db(np.array([0.0, 1.0]), np.array([0.1, 0.2]), 0.9)
    with pytest.raises(SmartScanError):
        run_sensitivity_sweep(m_samples=0, monte_carlo=False, n_trials=0)
    with pytest.raises(SmartScanError):
        analytic_snr_db_at_target_pd(1.5, m_samples=8, pfa_design=1e-3)
    with pytest.raises(SmartScanError):
        interpolate_snr_db(np.array([0.0, 1.0, 2.0]), np.array([0.1, 0.2]), 0.5)
    assert interpolate_snr_db(np.array([1.0, 2.0]), np.array([0.95, 0.99]), 0.90) == pytest.approx(1.0)
    cfg = ReceiverConfig(receiver_ibw_hz=1e8, scan_span_hz=16e9, noise_power_w=1.0)
    with pytest.raises(SmartScanError):
        rho_to_receiver_input_dbm(0.0, cfg)
    with pytest.raises(SmartScanError):
        run_sensitivity_sweep(m_samples=8, n_trials=0, monte_carlo=True)
