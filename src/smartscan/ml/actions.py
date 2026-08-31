"""Band × dwell action codec. Bundle is tied to exact BandPlan and dwell bins."""

from __future__ import annotations

from smartscan.types import ScanCommand, SmartScanError


def n_actions(n_bands: int, dwell_bins: tuple[int, ...]) -> int:
    if n_bands <= 0 or not dwell_bins:
        raise SmartScanError("Action space requires positive n_bands and nonempty dwell_bins.")
    return int(n_bands) * len(dwell_bins)


def decode_action(action: int, n_bands: int, dwell_bins: tuple[int, ...]) -> tuple[int, int]:
    """Return ``(band, dwell_steps)``. ``band = action // L``, ``dwell_bin = action % L``."""

    total = n_actions(n_bands, dwell_bins)
    value = int(action)
    if value < 0 or value >= total:
        raise SmartScanError(f"Action {value} is outside Discrete({total}).")
    length = len(dwell_bins)
    band = value // length
    dwell_bin = value % length
    return int(band), int(dwell_bins[dwell_bin])


def encode_action(band: int, dwell_steps: int, n_bands: int, dwell_bins: tuple[int, ...]) -> int:
    if band < 0 or band >= n_bands:
        raise SmartScanError(f"band {band} outside 0..{n_bands - 1}.")
    try:
        dwell_bin = list(dwell_bins).index(int(dwell_steps))
    except ValueError as exc:
        raise SmartScanError(
            f"dwell_steps={dwell_steps} is not in the frozen dwell_bins {dwell_bins}."
        ) from exc
    return int(band) * len(dwell_bins) + int(dwell_bin)


def command_from_action(
    action: int,
    *,
    decision_index: int,
    n_bands: int,
    dwell_bins: tuple[int, ...],
) -> ScanCommand:
    band, dwell = decode_action(action, n_bands, dwell_bins)
    return ScanCommand(
        decision_id=f"d{decision_index:05d}",
        target_band=band,
        dwell_steps=dwell,
    )


def decode_multidiscrete(
    action: object,
    n_bands: int,
    dwell_bins: tuple[int, ...],
) -> tuple[int, int]:
    """Map a MultiDiscrete [band_index, dwell_index] sample to (band, dwell_steps)."""

    import numpy as np

    arr = np.asarray(action).reshape(-1)
    if arr.size == 1:
        return decode_action(int(arr[0]), n_bands, dwell_bins)
    if arr.size < 2:
        raise SmartScanError("MultiDiscrete action must contain band and dwell indices.")
    band = int(arr[0])
    dwell_index = int(arr[1])
    if band < 0 or band >= int(n_bands):
        raise SmartScanError(f"band index {band} outside 0..{int(n_bands) - 1}.")
    if dwell_index < 0 or dwell_index >= len(dwell_bins):
        raise SmartScanError(
            f"dwell index {dwell_index} outside 0..{len(dwell_bins) - 1}."
        )
    return band, int(dwell_bins[dwell_index])


def command_from_policy_action(
    action: object,
    *,
    decision_index: int,
    n_bands: int,
    dwell_bins: tuple[int, ...],
    layout: str = "discrete",
) -> ScanCommand:
    kind = str(layout).strip().lower()
    if kind == "multidiscrete":
        band, dwell = decode_multidiscrete(action, n_bands, dwell_bins)
    else:
        import numpy as np

        band, dwell = decode_action(int(np.asarray(action).reshape(-1)[0]), n_bands, dwell_bins)
    assert_legal_band_dwell(band, dwell, n_bands, dwell_bins)
    return ScanCommand(
        decision_id=f"d{decision_index:05d}",
        target_band=band,
        dwell_steps=dwell,
    )


def assert_legal_band_dwell(
    band: int,
    dwell_steps: int,
    n_bands: int,
    dwell_bins: tuple[int, ...],
) -> None:
    if band < 0 or band >= int(n_bands):
        raise SmartScanError(f"Illegal target_band {band} for n_bands={n_bands}.")
    if int(dwell_steps) not in {int(x) for x in dwell_bins}:
        raise SmartScanError(
            f"Illegal dwell_steps={dwell_steps}; allowed {tuple(int(x) for x in dwell_bins)}."
        )


def logits_to_discrete_action(
    logits: object,
    n_bands: int,
    dwell_bins: tuple[int, ...],
) -> int:
    """Argmax Discrete or factorized MultiDiscrete logits; always returns a flat action."""

    import torch

    vec = torch.as_tensor(logits).reshape(-1)
    n_flat = n_actions(n_bands, dwell_bins)
    n_factor = int(n_bands) + len(dwell_bins)
    if int(vec.numel()) == n_flat:
        return int(torch.argmax(vec).item())
    if int(vec.numel()) == n_factor:
        band = int(torch.argmax(vec[: int(n_bands)]).item())
        dwell_index = int(torch.argmax(vec[int(n_bands) :]).item())
        return encode_action(band, int(dwell_bins[dwell_index]), n_bands, dwell_bins)
    raise SmartScanError(
        f"Unexpected action logit size {int(vec.numel())}; expected {n_flat} or {n_factor}."
    )
