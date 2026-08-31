"""Optional Turing Synthetic Radar Dataset adapter.

The 70 GB corpus is never required for tests. Prefer
``turing_deinterleaving_challenge.PulseTrain.load`` when installed.
The HDF5 layout used as a fallback is the published PulseTrain.save format:
``/data`` (N, 5) float32, optional ``/labels``, ``/metadata`` group.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from smartscan.config import duration_to_steps
from smartscan.data.provenance import file_provenance
from smartscan.rf.bands import frequency_to_band_or_none, named_band_plan
from smartscan.rf.environment import ground_truth_from_arrays
from smartscan.rf.events import extract_runs
from smartscan.types import (
    BandPlan,
    EventRecord,
    GroundTruth,
    SmartScanError,
    array_digest,
    sha256_file,
)

PDW_COLUMNS = ("toa_us", "centre_frequency_mhz", "pulse_width_us", "aoa_deg", "amplitude_db")
FEATURE_ALIASES: dict[str, int] = {
    "toa": 0,
    "time of arrival": 0,
    "time_of_arrival": 0,
    "centre frequency": 1,
    "center frequency": 1,
    "centre_frequency": 1,
    "center_frequency": 1,
    "cf": 1,
    "frequency": 1,
    "pulse width": 2,
    "pulse_width": 2,
    "pw": 2,
    "aoa": 3,
    "angle of arrival": 3,
    "angle_of_arrival": 3,
    "amplitude": 4,
    "amp": 4,
    "power": 4,
}
CHUNK_ROWS = 50_000
AmplitudeConvention = Literal["10log10_power", "20log10_amplitude"]
DEFAULT_AMPLITUDE_CONVENTION: AmplitudeConvention = "10log10_power"


@dataclass
class PulseTrainArrays:
    data: np.ndarray
    labels: np.ndarray | None
    feature_names: list[str]
    metadata: dict[str, Any]
    loader: str


def import_turing(
    input_path: str | Path,
    *,
    band_plan_id: str,
    dt_s: float = 0.001,
    duration_s: float | None = None,
    receiver_mode: Literal["stare", "scan", "auto"] = "auto",
    amplitude_convention: AmplitudeConvention = DEFAULT_AMPLITUDE_CONVENTION,
    seed: int = 0,
) -> GroundTruth:
    """Convert a local TSRD pulse-train HDF5 file into GroundTruth.

    Default occupancy interpretation is stare-mode electromagnetic-environment
    truth. Scan-mode files are converted as observations: missing pulses are
    not treated as non-transmissions.
    """

    path = Path(input_path)
    if not path.is_file():
        raise SmartScanError(f"TSRD pulse-train file not found: {path}")
    band_plan = named_band_plan(band_plan_id)
    loaded = load_pulse_train(path)
    mode = _resolve_mode(loaded.metadata, receiver_mode)
    toa_us, cf_mhz, pw_us, aoa_deg, amp_db, labels = _split_columns(loaded)
    n_steps = _infer_n_steps(toa_us, pw_us, dt_s, duration_s, loaded.metadata)
    occupied, power, counts, emitter_occupancy = accumulate_pulses(
        toa_us=toa_us,
        cf_mhz=cf_mhz,
        pw_us=pw_us,
        amp_db=amp_db,
        labels=labels,
        n_steps=n_steps,
        dt_s=dt_s,
        band_plan=band_plan,
        amplitude_convention=amplitude_convention,
        file_fingerprint=sha256_file(path),
    )
    events = events_from_emitter_power(emitter_occupancy, source="tsrd")
    notes = [
        "TSRD models emitted electromagnetic-environment observations as PDWs, "
        "not this project's narrowband scanning receiver. Stage 2 must still apply "
        "the project receiver/detector to converted truth.",
        f"amplitude_convention={amplitude_convention} "
        "(TSRD Amplitude is published as dB; 10log10_power is the default because "
        "received amplitude is described as decreasing quadratically with range). "
        "Switch to 20log10_amplitude if dataset metadata later verifies voltage dB.",
    ]
    if band_plan_id == "demo_2_18" and counts.get("clipped_low_ghz", 0):
        notes.append(
            f"demo_2_18 dropped {counts['clipped_low_ghz']} pulses below 2 GHz; "
            "the 0-18 GHz source was not reinterpreted."
        )
    if mode == "scan":
        notes.append(
            "scan-mode occupancy is an observation log, not stare truth. "
            "Non-detections must not be interpreted as non-transmissions."
        )
    provenance = file_provenance(
        source="tsrd",
        path=path,
        extra={
            "loader": loaded.loader,
            "receiver_mode": mode,
            "band_plan_id": band_plan_id,
            "dt_s": dt_s,
            "amplitude_convention": amplitude_convention,
            "occupancy_is_observation_not_truth": mode == "scan",
            "feature_names": loaded.feature_names,
            "n_pulses": int(toa_us.size),
            "pulse_train_fingerprint": sha256_file(path),
        },
        notes=notes,
    )
    provenance.dropped_counts = counts
    provenance.dataset_version = str(loaded.metadata.get("dataset_version") or "") or None
    side = {
        "toa_us": toa_us.astype(np.float64, copy=False),
        "aoa_deg": aoa_deg.astype(np.float64, copy=False),
        "amp_db": amp_db.astype(np.float64, copy=False),
        "labels": labels,
    }
    provenance.transformation["pdw_side_digest"] = {key: array_digest(val) for key, val in side.items()}
    scenario_config = {
        "scenario_id": "tsrd_import",
        "band_plan_id": band_plan_id,
        "dt_s": dt_s,
        "duration_s": n_steps * dt_s,
        "seed": seed,
        "source_file": path.name,
        "receiver_mode": mode,
    }
    return ground_truth_from_arrays(
        occupied=occupied,
        signal_power_w=power,
        events=events,
        band_plan=band_plan,
        dt_s=dt_s,
        seed=seed,
        scenario_id="tsrd_import",
        scenario_config=scenario_config,
        provenance=provenance,
    )


def load_pulse_train(path: Path) -> PulseTrainArrays:
    official = _try_official_load(path)
    if official is not None:
        return official
    return _load_published_h5(path)


def _try_official_load(path: Path) -> PulseTrainArrays | None:
    try:
        from turing_deinterleaving_challenge import PulseTrain
    except ImportError:
        return None
    loaded = PulseTrain.load(path)
    data = np.asarray(loaded.data, dtype=np.float64)
    labels = None if loaded.labels is None else np.asarray(loaded.labels).reshape(-1)
    metadata = _metadata_to_dict(getattr(loaded, "metadata", {}))
    names = _feature_names_from_metadata(metadata, data.shape[1] if data.ndim == 2 else 5)
    return PulseTrainArrays(
        data=data, labels=labels, feature_names=names, metadata=metadata, loader="PulseTrain.load"
    )


def _load_published_h5(path: Path) -> PulseTrainArrays:
    import h5py

    with h5py.File(path, "r") as handle:
        if "data" not in handle:
            raise SmartScanError(
                f"{path} is not a PulseTrain HDF5 file (missing /data). "
                "Install turing-deinterleaving-challenge and use PulseTrain.load."
            )
        data = np.asarray(handle["data"][()], dtype=np.float64)
        labels = np.asarray(handle["labels"][()]).reshape(-1) if "labels" in handle else None
        metadata: dict[str, Any] = {}
        if "metadata" in handle:
            metadata = _read_h5_group(handle["metadata"])
    names = _feature_names_from_metadata(metadata, data.shape[1] if data.ndim == 2 else 5)
    return PulseTrainArrays(
        data=data,
        labels=labels,
        feature_names=names,
        metadata=metadata,
        loader="h5py_pulsetrain_layout",
    )


def accumulate_pulses(
    *,
    toa_us: np.ndarray,
    cf_mhz: np.ndarray,
    pw_us: np.ndarray,
    amp_db: np.ndarray,
    labels: np.ndarray,
    n_steps: int,
    dt_s: float,
    band_plan: BandPlan,
    amplitude_convention: AmplitudeConvention,
    file_fingerprint: str,
) -> tuple[np.ndarray, np.ndarray, dict[str, int], dict[str, np.ndarray]]:
    occupied = np.zeros((n_steps, band_plan.n_bands), dtype=bool)
    power = np.zeros((n_steps, band_plan.n_bands), dtype=np.float64)
    counts = {
        "dropped_out_of_range": 0,
        "clipped_low_ghz": 0,
        "ambiguous_amplitude": 0,
        "dropped_negative_time": 0,
        "accepted": 0,
    }
    emitter_power: dict[str, np.ndarray] = {}
    low_hz = band_plan.band_edges_hz[0]
    n = int(toa_us.size)
    for start in range(0, n, CHUNK_ROWS):
        sl = slice(start, min(n, start + CHUNK_ROWS))
        chunk = zip(
            toa_us[sl], cf_mhz[sl], pw_us[sl], amp_db[sl], labels[sl], strict=True
        )
        for toa, cf, pw, amp, label in chunk:
            if not np.isfinite(toa) or toa < 0:
                counts["dropped_negative_time"] += 1
                continue
            if not np.isfinite(amp) or not np.isfinite(cf) or not np.isfinite(pw):
                counts["ambiguous_amplitude"] += 1
                continue
            freq_hz = float(cf) * 1e6
            if freq_hz < low_hz:
                counts["clipped_low_ghz"] += 1
            band = frequency_to_band_or_none(freq_hz, band_plan)
            if band is None:
                counts["dropped_out_of_range"] += 1
                continue
            try:
                linear_power = db_to_linear_power(float(amp), amplitude_convention)
            except SmartScanError:
                counts["ambiguous_amplitude"] += 1
                continue
            toa_s = float(toa) * 1e-6
            pw_s = max(float(pw) * 1e-6, 0.0)
            emitter_id = namespace_emitter(file_fingerprint, label)
            if emitter_id not in emitter_power:
                emitter_power[emitter_id] = np.zeros(
                    (n_steps, band_plan.n_bands), dtype=np.float64
                )
            added = _deposit_pulse(
                power, occupied, band, toa_s, pw_s, linear_power, dt_s, n_steps
            )
            _deposit_pulse(
                emitter_power[emitter_id],
                occupied,
                band,
                toa_s,
                pw_s,
                linear_power,
                dt_s,
                n_steps,
            )
            if added:
                counts["accepted"] += 1
            else:
                counts["dropped_out_of_range"] += 1
    return occupied, power.astype(np.float32), counts, emitter_power


def db_to_linear_power(amp_db: float, convention: AmplitudeConvention) -> float:
    if not np.isfinite(amp_db):
        raise SmartScanError("Amplitude is non-finite.")
    if convention == "10log10_power":
        return float(10.0 ** (amp_db / 10.0))
    if convention == "20log10_amplitude":
        voltage_ratio = 10.0 ** (amp_db / 20.0)
        return float(voltage_ratio * voltage_ratio)
    raise SmartScanError(f"Unknown amplitude convention {convention!r}.")


def namespace_emitter(file_fingerprint: str, label: Any) -> str:
    return f"{file_fingerprint}:{label}"


def _deposit_pulse(
    power: np.ndarray,
    occupied: np.ndarray,
    band: int,
    toa_s: float,
    pw_s: float,
    linear_power: float,
    dt_s: float,
    n_steps: int,
) -> bool:
    if pw_s <= 0:
        start = toa_s
        stop = toa_s + dt_s
    else:
        start = toa_s
        stop = toa_s + pw_s
    first = int(np.floor(start / dt_s))
    last = int(np.floor((stop - 1e-18) / dt_s))
    deposited = False
    for step in range(first, last + 1):
        if step < 0 or step >= n_steps:
            continue
        bin_lo = step * dt_s
        bin_hi = (step + 1) * dt_s
        overlap = min(stop, bin_hi) - max(start, bin_lo)
        if overlap <= 0:
            continue
        power[step, band] += linear_power * (overlap / dt_s)
        occupied[step, band] = True
        deposited = True
    return deposited


def events_from_emitter_power(
    emitter_occupancy: dict[str, np.ndarray], *, source: str
) -> list[EventRecord]:
    records: list[EventRecord] = []
    for emitter_id, power in emitter_occupancy.items():
        occupied = np.asarray(power) > 0
        n_bands = occupied.shape[1]
        for band in range(n_bands):
            for start, end in extract_runs(occupied[:, band]):
                records.append(
                    EventRecord(
                        event_id=f"{emitter_id}:b{band}:{start}",
                        emitter_id=emitter_id,
                        band=band,
                        start_step=start,
                        end_step=end,
                        source=source,
                    )
                )
    return records


def _split_columns(
    loaded: PulseTrainArrays,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    data = np.asarray(loaded.data, dtype=np.float64)
    if data.ndim != 2 or data.shape[1] < 5:
        raise SmartScanError(f"PDW array must have shape (N, >=5), got {data.shape}.")
    index = _column_index(loaded.feature_names, data.shape[1])
    toa = data[:, index[0]]
    cf = data[:, index[1]]
    pw = data[:, index[2]]
    aoa = data[:, index[3]]
    amp = data[:, index[4]]
    if loaded.labels is None:
        labels = np.zeros(data.shape[0], dtype=np.int64)
    else:
        labels = np.asarray(loaded.labels).reshape(-1)
        if labels.shape[0] != data.shape[0]:
            raise SmartScanError("labels length does not match PDW rows.")
    return toa, cf, pw, aoa, amp, labels


def _column_index(feature_names: list[str], n_cols: int) -> list[int]:
    mapping = [-1, -1, -1, -1, -1]
    for i, name in enumerate(feature_names[:n_cols]):
        key = str(name).strip().lower()
        if key in FEATURE_ALIASES:
            mapping[FEATURE_ALIASES[key]] = i
    for expected, default in enumerate(range(5)):
        if mapping[expected] < 0:
            mapping[expected] = default
    return mapping


def _feature_names_from_metadata(metadata: dict[str, Any], n_cols: int) -> list[str]:
    names = metadata.get("feature_names")
    if names is None:
        return list(PDW_COLUMNS[:n_cols])
    if isinstance(names, np.ndarray):
        decoded = []
        for item in names:
            if isinstance(item, (bytes, np.bytes_)):
                decoded.append(item.decode("utf-8", errors="replace"))
            else:
                decoded.append(str(item))
        return decoded
    if isinstance(names, (list, tuple)):
        out = []
        for item in names:
            if isinstance(item, (bytes, np.bytes_)):
                out.append(item.decode("utf-8", errors="replace"))
            else:
                out.append(str(item))
        return out
    return list(PDW_COLUMNS[:n_cols])


def _infer_n_steps(
    toa_us: np.ndarray,
    pw_us: np.ndarray,
    dt_s: float,
    duration_s: float | None,
    metadata: dict[str, Any],
) -> int:
    if duration_s is not None:
        return duration_to_steps(duration_s, dt_s)
    collection = metadata.get("collection_time_s")
    if collection is not None and np.isfinite(float(collection)) and float(collection) > 0:
        return duration_to_steps(float(collection), dt_s)
    if toa_us.size == 0:
        return duration_to_steps(dt_s, dt_s)
    end_s = float(np.nanmax(toa_us * 1e-6 + np.clip(pw_us, 0, None) * 1e-6))
    duration = max(dt_s, (np.floor(end_s / dt_s) + 1) * dt_s)
    return duration_to_steps(duration, dt_s)


def _resolve_mode(metadata: dict[str, Any], requested: str) -> str:
    if requested in {"stare", "scan"}:
        return requested
    receiver = metadata.get("receiver") or {}
    for key in ("mode", "receiver_mode", "type"):
        if isinstance(receiver, dict) and key in receiver:
            value = str(receiver[key]).lower()
            if "scan" in value:
                return "scan"
            if "stare" in value:
                return "stare"
        if key in metadata:
            value = str(metadata[key]).lower()
            if "scan" in value:
                return "scan"
            if "stare" in value:
                return "stare"
    description = str(metadata.get("description") or "").lower()
    if "scan" in description and "stare" not in description:
        return "scan"
    return "stare"


def _metadata_to_dict(metadata: Any) -> dict[str, Any]:
    if metadata is None:
        return {}
    if isinstance(metadata, dict):
        return metadata
    if hasattr(metadata, "__dict__"):
        payload = {}
        for key, value in vars(metadata).items():
            payload[key] = value
        return payload
    dump = getattr(metadata, "model_dump", None)
    if callable(dump):
        return dict(dump())
    return {"repr": repr(metadata)}


def _read_h5_group(group: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in group.attrs.items():
        out[str(key)] = _h5_scalar(value)
    for key in group:
        item = group[key]
        if hasattr(item, "keys"):
            out[str(key)] = _read_h5_group(item)
        else:
            out[str(key)] = _h5_scalar(item[()])
    return out


def _h5_scalar(value: Any) -> Any:
    if isinstance(value, (bytes, np.bytes_)):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray) and value.dtype.kind in {"S", "U"}:
        return [ _h5_scalar(v) for v in value ]
    if isinstance(value, np.ndarray) and value.shape == ():
        return _h5_scalar(value.item())
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    return value
