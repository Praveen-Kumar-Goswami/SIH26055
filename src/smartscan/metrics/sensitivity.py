"""Controlled single-band SNR sensitivity sweep.

This isolates the detector. It does not use a scheduler log.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from scipy import stats

from smartscan.metrics.schemas import SensitivityCurve, SensitivityPoint
from smartscan.receiver.detector import (
    analytic_pd,
    detection_threshold,
    linear_to_db,
    noise_power_w,
    sample_energy,
)
from smartscan.seeding import spawn_generator
from smartscan.types import ReceiverConfig, SmartScanError

DEFAULT_SNR_DB_GRID = tuple(float(x) for x in np.linspace(-5.0, 20.0, 51).tolist())


def analytic_snr_db_at_target_pd(
    target_pd: float,
    *,
    m_samples: int,
    pfa_design: float,
) -> float:
    """Log-space binary search for rho where analytic Pd equals *target_pd*."""

    if not (0.0 < target_pd < 1.0):
        raise SmartScanError("target_pd must be in (0, 1).")
    pfa_pd = analytic_pd(0.0, m_samples, pfa_design)
    if target_pd <= pfa_pd:
        raise SmartScanError(
            f"target_pd={target_pd} is not above H0 Pd≈{pfa_pd} at this pfa_design."
        )
    lo = 1e-12
    hi = 1e6
    for _ in range(80):
        mid = float(np.sqrt(lo * hi))
        pd_mid = analytic_pd(mid, m_samples, pfa_design)
        if pd_mid < target_pd:
            lo = mid
        else:
            hi = mid
    rho = float(np.sqrt(lo * hi))
    return linear_to_db(rho)


def interpolate_snr_db(snr_db: np.ndarray, pd: np.ndarray, target_pd: float) -> float:
    """Monotone interpolation of SNR dB at *target_pd*."""

    x = np.asarray(snr_db, dtype=np.float64)
    y = np.asarray(pd, dtype=np.float64)
    if x.size < 2 or x.size != y.size:
        raise SmartScanError("Sensitivity interpolation needs at least two aligned points.")
    order = np.argsort(x)
    x = x[order]
    y = np.maximum.accumulate(y[order])
    if float(y[-1]) < target_pd:
        raise SmartScanError(
            f"Sensitivity curve never reaches target Pd={target_pd}; max Pd={float(y[-1])}."
        )
    if float(y[0]) >= target_pd:
        return float(x[0])
    return float(np.interp(target_pd, y, x))


def rho_to_receiver_input_dbm(rho: float, config: ReceiverConfig) -> float:
    noise = noise_power_w(config)
    power_w = float(rho) * float(noise)
    if power_w <= 0.0:
        raise SmartScanError("Receiver-input power must be positive for dBm conversion.")
    return float(10.0 * np.log10(power_w * 1000.0))


def run_sensitivity_sweep(
    *,
    target_pd: float = 0.90,
    m_samples: int = 8,
    pfa_design: float = 1e-3,
    seed: int = 12345,
    n_trials: int = 2000,
    snr_db_grid: tuple[float, ...] | None = None,
    receiver_config: ReceiverConfig | None = None,
    monte_carlo: bool = True,
) -> SensitivityCurve:
    """Single-band controlled Pd vs SNR. Analytic curve always; MC optional."""

    if m_samples <= 0:
        raise SmartScanError("m_samples must be positive.")
    grid = snr_db_grid or DEFAULT_SNR_DB_GRID
    snr = np.asarray(grid, dtype=np.float64)
    analytic = np.array(
        [analytic_pd(float(10.0 ** (db / 10.0)), m_samples, pfa_design) for db in snr],
        dtype=np.float64,
    )
    if np.any(np.diff(analytic) < -1e-12):
        raise SmartScanError("Analytic Pd curve is not monotone in SNR.")

    pd_hat: np.ndarray | None = None
    ci_low: np.ndarray | None = None
    ci_high: np.ndarray | None = None
    if monte_carlo:
        pd_hat, ci_low, ci_high = _monte_carlo_curve(
            snr, m_samples=m_samples, pfa_design=pfa_design, seed=seed, n_trials=n_trials
        )
        pd_hat = np.maximum.accumulate(pd_hat)
        source = pd_hat
    else:
        source = analytic

    snr_at_target = interpolate_snr_db(snr, source, target_pd)
    analytic_target = analytic_snr_db_at_target_pd(
        target_pd, m_samples=m_samples, pfa_design=pfa_design
    )
    # Prefer analytic for the reported threshold; MC curve is stored for CIs.
    if not monte_carlo:
        snr_at_target = analytic_target
    else:
        # Keep MC interpolation but require it near analytic (caller tests tolerance).
        snr_at_target = float(snr_at_target)

    dbm: float | None = None
    noise_mode: Literal["normalized", "physical"] = "normalized"
    if receiver_config is not None and receiver_config.noise_mode == "physical":
        noise_mode = "physical"
        rho = 10.0 ** (analytic_target / 10.0)
        dbm = rho_to_receiver_input_dbm(rho, receiver_config)

    points: list[SensitivityPoint] = []
    for i, db in enumerate(snr.tolist()):
        points.append(
            SensitivityPoint(
                snr_db=float(db),
                pd_analytic=float(analytic[i]),
                pd_hat=None if pd_hat is None else float(pd_hat[i]),
                ci_low=None if ci_low is None else float(ci_low[i]),
                ci_high=None if ci_high is None else float(ci_high[i]),
            )
        )
    return SensitivityCurve(
        target_pd=float(target_pd),
        m_samples=int(m_samples),
        pfa_design=float(pfa_design),
        snr_db_at_target=float(analytic_target if not monte_carlo else snr_at_target),
        receiver_input_dbm=dbm,
        noise_mode=noise_mode,
        monotone=True,
        seed=None if not monte_carlo else int(seed),
        n_trials=None if not monte_carlo else int(n_trials),
        points=points,
    )


def analytic_sensitivity_curve(
    *,
    target_pd: float = 0.90,
    m_samples: int = 8,
    pfa_design: float = 1e-3,
    receiver_config: ReceiverConfig | None = None,
) -> SensitivityCurve:
    return run_sensitivity_sweep(
        target_pd=target_pd,
        m_samples=m_samples,
        pfa_design=pfa_design,
        monte_carlo=False,
        n_trials=0,
        receiver_config=receiver_config,
    )


def _monte_carlo_curve(
    snr_db: np.ndarray,
    *,
    m_samples: int,
    pfa_design: float,
    seed: int,
    n_trials: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if n_trials <= 0:
        raise SmartScanError("n_trials must be positive for a Monte Carlo sweep.")
    rng = spawn_generator(seed)
    threshold = detection_threshold(m_samples, pfa_design)
    pd_hat = np.empty(snr_db.size, dtype=np.float64)
    lo = np.empty(snr_db.size, dtype=np.float64)
    hi = np.empty(snr_db.size, dtype=np.float64)
    dwell_steps = int(m_samples)
    rho_vec = np.empty(dwell_steps, dtype=np.float64)
    for i, db in enumerate(snr_db.tolist()):
        rho = 10.0 ** (float(db) / 10.0)
        rho_vec.fill(rho)
        hits = 0
        for _ in range(n_trials):
            energy = sample_energy(
                rng, rho_vec, samples_per_step=1, dwell_steps=dwell_steps
            )
            if energy >= threshold:
                hits += 1
        pd_hat[i] = hits / float(n_trials)
        ci = stats.binomtest(hits, n_trials).proportion_ci(confidence_level=0.95)
        lo[i] = float(ci.low)
        hi[i] = float(ci.high)
    return pd_hat, lo, hi
