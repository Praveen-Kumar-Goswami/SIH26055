"""Pfa-controlled noncoherent energy detector.

Not CFAR: there are no reference cells or adaptive background estimation.
Internal calculations stay in linear units. dB appears only at report boundaries.
"""

from __future__ import annotations

import numpy as np
from scipy import stats

from smartscan.config import duration_to_steps
from smartscan.types import ReceiverConfig, SmartScanError, content_fingerprint

K_BOLTZMANN = 1.380649e-23
T0_STANDARD_K = 290.0


def receiver_config_hash(config: ReceiverConfig) -> str:
    return content_fingerprint(config.model_dump())


def load_receiver_config(data: dict[str, object] | ReceiverConfig) -> ReceiverConfig:
    if isinstance(data, ReceiverConfig):
        return data
    payload = dict(data)
    if "dwell_bins" in payload and isinstance(payload["dwell_bins"], list):
        payload["dwell_bins"] = tuple(int(x) for x in payload["dwell_bins"])
    return ReceiverConfig.model_validate(payload)


def physical_latency_steps(latency_s: float, dt_s: float) -> int:
    """Reject non-integer multiples of dt instead of silent rounding."""

    return duration_to_steps(latency_s, dt_s)


def noise_power_w(config: ReceiverConfig) -> float:
    if config.noise_mode == "physical":
        assert config.temperature_k is not None and config.noise_figure_db is not None
        noise_factor = db_to_linear(config.noise_figure_db)
        return float(K_BOLTZMANN * config.temperature_k * config.receiver_ibw_hz * noise_factor)
    if config.noise_power_w is not None:
        return float(config.noise_power_w)
    return 1.0


def equivalent_samples(config: ReceiverConfig, dwell_steps: int) -> int:
    if dwell_steps <= 0:
        raise SmartScanError("dwell_steps must be positive.")
    return int(config.samples_per_step) * int(dwell_steps)


def detection_threshold(m_samples: int, pfa_design: float) -> float:
    """Gamma PPF threshold for Z ~ Gamma(shape=M, scale=1) under H0."""

    if m_samples <= 0:
        raise SmartScanError("M must be positive.")
    if not (0.0 < pfa_design < 1.0):
        raise SmartScanError("pfa_design must be in (0, 1).")
    value = float(stats.gamma.ppf(1.0 - pfa_design, a=m_samples, scale=1.0))
    if not np.isfinite(value):
        raise SmartScanError("Detection threshold is non-finite.")
    return value


def noncentrality(rho: np.ndarray, samples_per_step: int) -> float:
    """nc = 2 * samples_per_step * sum(rho) over usable dwell steps."""

    total = float(np.sum(np.asarray(rho, dtype=np.float64)))
    return 2.0 * float(samples_per_step) * total


def analytic_pd(rho: float, m_samples: int, pfa_design: float) -> float:
    """Pd(rho) = SF_NCX2(2*threshold; df=2M, nc=2M*rho) for constant rho."""

    threshold = detection_threshold(m_samples, pfa_design)
    nc = 2.0 * m_samples * float(rho)
    return float(stats.ncx2.sf(2.0 * threshold, df=2 * m_samples, nc=nc))


def sample_energy(
    rng: np.random.Generator,
    rho: np.ndarray,
    *,
    samples_per_step: int,
    dwell_steps: int,
) -> float:
    """Sample completed-dwell energy Z.

    H0 (all rho=0): Z ~ Gamma(shape=M, scale=1)
    H1: 2Z ~ ncx2(df=2M, nc=2*sps*sum(rho)); Z = 0.5 * ncx2
    """

    rho_arr = np.asarray(rho, dtype=np.float64).reshape(-1)
    if rho_arr.size != dwell_steps:
        raise SmartScanError(
            f"rho length {rho_arr.size} does not match dwell_steps={dwell_steps}."
        )
    if np.any(~np.isfinite(rho_arr)) or np.any(rho_arr < 0):
        raise SmartScanError("rho must be finite and nonnegative.")
    m_samples = samples_per_step * dwell_steps
    if float(np.sum(rho_arr)) == 0.0:
        return float(rng.gamma(shape=m_samples, scale=1.0))
    nc = noncentrality(rho_arr, samples_per_step)
    chi = float(rng.noncentral_chisquare(df=2 * m_samples, nonc=nc))
    return 0.5 * chi


def detect(energy: float, m_samples: int, pfa_design: float) -> bool:
    return bool(energy >= detection_threshold(m_samples, pfa_design))


def measured_snr_db(energy: float, m_samples: int) -> float | None:
    """Estimate 10 log10(Z/M - 1). None when the estimate is non-positive."""

    if m_samples <= 0 or not np.isfinite(energy):
        return None
    snr_lin = float(energy) / float(m_samples) - 1.0
    if snr_lin <= 0.0:
        return None
    return linear_to_db(snr_lin)


def linear_to_db(linear: float) -> float:
    if not np.isfinite(linear) or linear <= 0.0:
        raise SmartScanError(f"linear_to_db requires positive finite input, got {linear}.")
    return float(10.0 * np.log10(linear))


def db_to_linear(db: float) -> float:
    if not np.isfinite(db):
        raise SmartScanError(f"db_to_linear requires finite input, got {db}.")
    return float(10.0 ** (db / 10.0))


def rho_from_power(signal_power_w: np.ndarray, noise: float) -> np.ndarray:
    if noise <= 0 or not np.isfinite(noise):
        raise SmartScanError(f"noise_power_w must be positive and finite, got {noise}.")
    rho = np.asarray(signal_power_w, dtype=np.float64) / noise
    return rho
