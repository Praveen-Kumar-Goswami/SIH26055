"""Deterministic GroundTruth save/reload (NPZ or HDF5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from smartscan.types import (
    SCHEMA_VERSION,
    BandPlan,
    EventRecord,
    EventTable,
    GroundTruth,
    Provenance,
    SmartScanError,
    sha256_file,
    strip_volatile,
)

NPZ_KEYS = ("occupied", "signal_power_w", "meta_utf8", "events_utf8")


def save_ground_truth(truth: GroundTruth, path: str | Path) -> GroundTruth:
    """Write compressed NPZ or HDF5. Fingerprint is independent of compression bytes."""

    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not truth.content_fingerprint:
        truth.content_fingerprint = truth.compute_content_fingerprint()
    suffix = dest.suffix.lower()
    if suffix in {".h5", ".hdf5"}:
        tmp = dest.with_name(dest.name + ".writing")
        if tmp.exists():
            tmp.unlink()
        _write_hdf5(truth, tmp)
    else:
        # numpy.savez_compressed appends .npz unless the name already ends with it.
        tmp = dest.with_name(dest.stem + ".writing.npz")
        if tmp.exists():
            tmp.unlink()
        _write_npz(truth, tmp)
    tmp.replace(dest)
    truth.artifact_sha256 = sha256_file(dest)
    return truth


def load_ground_truth(path: str | Path, *, verify_fingerprint: bool = True) -> GroundTruth:
    src = Path(path)
    if not src.is_file():
        raise SmartScanError(f"GroundTruth file not found: {src}")
    suffix = src.suffix.lower()
    if suffix in {".h5", ".hdf5"}:
        truth = _read_hdf5(src)
    else:
        truth = _read_npz(src)
    truth.artifact_sha256 = sha256_file(src)
    recomputed = truth.compute_content_fingerprint()
    if verify_fingerprint and recomputed != truth.content_fingerprint:
        raise SmartScanError(
            "content_fingerprint mismatch on load: stored "
            f"{truth.content_fingerprint} != recomputed {recomputed}."
        )
    return truth


def inspect_summary(truth: GroundTruth) -> dict[str, Any]:
    n_steps = truth.n_steps
    bands = []
    events_by_band = {band: 0 for band in range(truth.band_plan.n_bands)}
    for record in truth.events.records():
        events_by_band[record.band] = events_by_band.get(record.band, 0) + 1
    for band, name in enumerate(truth.band_plan.band_names):
        occ = int(truth.occupied[:, band].sum())
        bands.append(
            {
                "band": band,
                "name": name,
                "occupied_steps": occ,
                "occupied_fraction": occ / max(n_steps, 1),
                "event_count": events_by_band.get(band, 0),
                "mean_power_w": float(truth.signal_power_w[:, band].mean()),
            }
        )
    return {
        "schema_version": truth.schema_version,
        "generator_version": truth.generator_version,
        "profile_id": truth.band_plan.profile_id,
        "dt_s": truth.dt_s,
        "n_steps": truth.n_steps,
        "n_bands": truth.band_plan.n_bands,
        "seed": truth.seed,
        "n_events": len(truth.events),
        "content_fingerprint": truth.content_fingerprint,
        "artifact_sha256": truth.artifact_sha256,
        "bands": bands,
    }


def _meta_dict(truth: GroundTruth) -> dict[str, Any]:
    return {
        "schema_version": truth.schema_version,
        "generator_version": truth.generator_version,
        "seed": truth.seed,
        "dt_s": truth.dt_s,
        "n_steps": truth.n_steps,
        "band_plan": truth.band_plan.model_dump(),
        "scenario_config": strip_volatile(truth.scenario_config),
        "provenance": strip_volatile(truth.provenance.model_dump()),
        "content_fingerprint": truth.content_fingerprint,
    }


def _write_npz(truth: GroundTruth, path: Path) -> None:
    meta = json.dumps(_meta_dict(truth), sort_keys=True, separators=(",", ":")).encode("utf-8")
    events = json.dumps(truth.events.canonical_records(), sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    np.savez_compressed(
        path,
        occupied=np.asarray(truth.occupied, dtype=bool),
        signal_power_w=np.asarray(truth.signal_power_w, dtype=np.float32),
        meta_utf8=np.frombuffer(meta, dtype=np.uint8),
        events_utf8=np.frombuffer(events, dtype=np.uint8),
    )


def _read_npz(path: Path) -> GroundTruth:
    with np.load(path, allow_pickle=False) as payload:
        missing = [key for key in NPZ_KEYS if key not in payload]
        if missing:
            raise SmartScanError(f"NPZ missing keys {missing} in {path}.")
        occupied = np.asarray(payload["occupied"], dtype=bool)
        power = np.asarray(payload["signal_power_w"], dtype=np.float32)
        meta = json.loads(bytes(payload["meta_utf8"]).decode("utf-8"))
        events_raw = json.loads(bytes(payload["events_utf8"]).decode("utf-8"))
    return _assemble(occupied, power, meta, events_raw)


def _write_hdf5(truth: GroundTruth, path: Path) -> None:
    import h5py

    meta = json.dumps(_meta_dict(truth), sort_keys=True, separators=(",", ":"))
    events = json.dumps(truth.events.canonical_records(), sort_keys=True, separators=(",", ":"))
    with h5py.File(path, "w") as handle:
        handle.create_dataset("occupied", data=np.asarray(truth.occupied, dtype=bool), compression="gzip")
        handle.create_dataset(
            "signal_power_w",
            data=np.asarray(truth.signal_power_w, dtype=np.float32),
            compression="gzip",
        )
        handle.attrs["schema_version"] = SCHEMA_VERSION
        handle.create_dataset("meta_json", data=np.frombuffer(meta.encode("utf-8"), dtype=np.uint8))
        handle.create_dataset("events_json", data=np.frombuffer(events.encode("utf-8"), dtype=np.uint8))


def _read_hdf5(path: Path) -> GroundTruth:
    import h5py

    with h5py.File(path, "r") as handle:
        occupied = np.asarray(handle["occupied"][()], dtype=bool)
        power = np.asarray(handle["signal_power_w"][()], dtype=np.float32)
        meta = json.loads(bytes(handle["meta_json"][()]).decode("utf-8"))
        events_raw = json.loads(bytes(handle["events_json"][()]).decode("utf-8"))
    return _assemble(occupied, power, meta, events_raw)


def _assemble(
    occupied: np.ndarray,
    power: np.ndarray,
    meta: dict[str, Any],
    events_raw: list[dict[str, Any]],
) -> GroundTruth:
    band_plan = BandPlan.model_validate(meta["band_plan"])
    records = [EventRecord.model_validate(item) for item in events_raw]
    return GroundTruth(
        dt_s=float(meta["dt_s"]),
        n_steps=int(meta["n_steps"]),
        band_plan=band_plan,
        occupied=occupied,
        signal_power_w=power,
        events=EventTable(records),
        provenance=Provenance.model_validate(meta.get("provenance") or {"source": "unknown"}),
        content_fingerprint=str(meta["content_fingerprint"]),
        artifact_sha256=None,
        scenario_config=meta.get("scenario_config") or {},
        seed=int(meta["seed"]),
        generator_version=str(meta.get("generator_version", "")),
        schema_version=str(meta.get("schema_version", SCHEMA_VERSION)),
    )
