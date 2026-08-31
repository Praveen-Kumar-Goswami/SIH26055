"""Band-plan primitives and half-open frequency mapping."""

from __future__ import annotations

import numpy as np

from smartscan.types import BandPlan, SmartScanError

GHZ = 1e9

DEMO_2_18_ID = "demo_2_18"
TURING_0_18_ID = "turing_0_18"

PROFILE_SPECS: dict[str, tuple[float, float, int]] = {
    # (low_hz, high_hz, n_bands) with 1 GHz bins
    DEMO_2_18_ID: (2 * GHZ, 18 * GHZ, 16),
    TURING_0_18_ID: (0.0, 18 * GHZ, 18),
}


def named_band_plan(profile_id: str) -> BandPlan:
    if profile_id not in PROFILE_SPECS:
        known = ", ".join(sorted(PROFILE_SPECS))
        raise SmartScanError(f"Unknown BandPlan profile {profile_id!r}. Known: {known}.")
    low_hz, high_hz, n_bands = PROFILE_SPECS[profile_id]
    edges = tuple(float(low_hz + k * GHZ) for k in range(n_bands + 1))
    if not np.isclose(edges[-1], high_hz):
        raise SmartScanError(f"Internal error: profile {profile_id} high edge mismatch.")
    names = tuple(_band_name(edges[k], edges[k + 1]) for k in range(n_bands))
    return BandPlan(
        band_edges_hz=edges,
        band_names=names,
        profile_id=profile_id,
        scan_span_hz=float(high_hz - low_hz),
    )


def _band_name(low_hz: float, high_hz: float) -> str:
    return f"{low_hz / GHZ:.0f}-{high_hz / GHZ:.0f}GHz"


def frequency_to_band(frequency_hz: float, band_plan: BandPlan) -> int:
    """Return band index for *frequency_hz* in half-open ``[low, high)``.

    The high edge of the plan (for example exactly 18 GHz) is out of range.
    """

    if not np.isfinite(frequency_hz):
        raise SmartScanError(f"Frequency must be finite, got {frequency_hz}.")
    edges = np.asarray(band_plan.band_edges_hz, dtype=np.float64)
    # searchsorted side='right' then minus one: interior low edges map into the
    # higher band so that [e[k], e[k+1]) is exclusive of e[k+1].
    index = int(np.searchsorted(edges, frequency_hz, side="right") - 1)
    if index < 0 or frequency_hz >= edges[-1] or index >= band_plan.n_bands:
        raise SmartScanError(
            f"Frequency {frequency_hz} Hz is outside BandPlan {band_plan.profile_id} "
            f"[{edges[0]}, {edges[-1]})."
        )
    return index


def frequency_to_band_or_none(frequency_hz: float, band_plan: BandPlan) -> int | None:
    try:
        return frequency_to_band(frequency_hz, band_plan)
    except SmartScanError:
        return None
