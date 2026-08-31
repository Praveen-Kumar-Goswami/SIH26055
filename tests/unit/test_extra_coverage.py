from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from pydantic import ValidationError

from smartscan.data.turing import import_turing, load_pulse_train
from smartscan.rf.bands import frequency_to_band
from smartscan.rf.emitters import CircularScanEmitter, OnOffGate, SectorScanEmitter
from smartscan.rf.environment import per_band_activity, simulate
from smartscan.rf.events import extract_runs
from smartscan.rf.io import inspect_summary, load_ground_truth, save_ground_truth
from smartscan.types import EventRecord, EventTable, SmartScanError


def test_inspect_and_missing_file(tmp_path: Path) -> None:
    truth = simulate(
        {
            "seed": 0,
            "dt_s": 0.001,
            "duration_s": 0.05,
            "band_plan_id": "demo_2_18",
            "scenario_id": "sparse",
        }
    )
    path = tmp_path / "gt.npz"
    save_ground_truth(truth, path)
    loaded = load_ground_truth(path)
    summary = inspect_summary(loaded)
    assert summary["n_steps"] == 50
    assert summary["n_events"] == len(loaded.events)
    with pytest.raises(SmartScanError, match="not found"):
        load_ground_truth(tmp_path / "missing.npz")


def test_fingerprint_mismatch(tmp_path: Path) -> None:
    truth = simulate(
        {
            "seed": 1,
            "dt_s": 0.001,
            "duration_s": 0.02,
            "band_plan_id": "demo_2_18",
            "scenario_id": "edge_zero",
        }
    )
    path = tmp_path / "gt.npz"
    save_ground_truth(truth, path)
    loaded = load_ground_truth(path)
    loaded.content_fingerprint = "deadbeef"
    # Re-save with tampered stored fingerprint inside? load recomputes from arrays.
    # Corrupt by flipping occupancy after save is not in file. Instead rewrite meta.
    save_ground_truth(loaded, path)
    # stored fingerprint is deadbeef but arrays recompute differently
    with pytest.raises(SmartScanError, match="content_fingerprint mismatch"):
        load_ground_truth(path, verify_fingerprint=True)


def test_event_table_from_frame_and_copy() -> None:
    record = EventRecord(
        event_id="e",
        emitter_id="a",
        band=0,
        start_step=0,
        end_step=3,
        source="test",
        threat_weight=None,
    )
    table = EventTable([record])
    table2 = EventTable(table)
    table3 = EventTable(table.frame)
    assert len(table2) == 1
    assert len(table3) == 1
    assert table.canonical_records()[0]["event_id"] == "e"


def test_extract_runs_empty() -> None:
    assert extract_runs(np.array([], dtype=bool)) == []


def test_nonfinite_frequency() -> None:
    from smartscan.rf.bands import named_band_plan

    plan = named_band_plan("demo_2_18")
    with pytest.raises(SmartScanError, match="finite"):
        frequency_to_band(float("nan"), plan)


def test_per_band_activity() -> None:
    occupied = np.zeros((10, 2), dtype=bool)
    occupied[:4, 0] = True
    rows = per_band_activity(occupied)
    assert rows[0]["occupied_steps"] == 4
    assert rows[1]["occupied_steps"] == 0


def test_invalid_gates_and_beamwidth() -> None:
    with pytest.raises((SmartScanError, ValidationError)):
        OnOffGate(kind="periodic", period_steps=10, on_steps=20)
    with pytest.raises((SmartScanError, ValidationError)):
        OnOffGate(kind="windows", windows=())
    with pytest.raises((SmartScanError, ValidationError)):
        SectorScanEmitter(
            emitter_id="s",
            frequency_hz=3.5e9,
            power_w=1.0,
            scan_period_s=0.1,
            theta_min_deg=0.0,
            theta_max_deg=0.0,
            beamwidth_deg=5.0,
        )
    emitter = CircularScanEmitter(
        emitter_id="c",
        frequency_hz=3.5e9,
        power_w=1.0,
        scan_period_s=0.1,
        beamwidth_deg=400.0,
    )
    from smartscan.rf.bands import named_band_plan

    with pytest.raises(SmartScanError, match="beamwidth"):
        emitter.render(10, named_band_plan("demo_2_18"), 0.001)


def test_negative_toa_dropped(tmp_path: Path) -> None:
    import h5py

    path = tmp_path / "neg.h5"
    data = np.array([[-10.0, 3000.0, 100.0, 0.0, -30.0]], dtype=np.float32)
    with h5py.File(path, "w") as handle:
        handle.create_dataset("data", data=data)
        handle.create_dataset("labels", data=np.array([1], dtype=np.int8))
        meta = handle.create_group("metadata")
        meta.attrs["collection_time_s"] = 0.01
        rx = meta.create_group("receiver")
        rx.attrs["mode"] = "stare"
    truth = import_turing(path, band_plan_id="demo_2_18", dt_s=0.001, duration_s=0.01)
    assert truth.provenance.dropped_counts["dropped_negative_time"] == 1


def test_official_pulsetrain_load(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:

    path = tmp_path / "x.h5"
    path.write_bytes(b"not-used")

    class Loaded:
        def __init__(self) -> None:
            self.data = np.array([[0.0, 4000.0, 50.0, 0.0, -10.0]], dtype=np.float64)
            self.labels = np.array([4])
            self.metadata = SimpleNamespace(
                feature_names=["ToA", "Centre Frequency", "Pulse Width", "AoA", "Amplitude"],
                receiver={"mode": "stare"},
                collection_time_s=0.005,
            )

    class PulseTrain:
        @classmethod
        def load(cls, load_path: Path) -> Loaded:
            del load_path
            return Loaded()

    monkeypatch.setitem(
        __import__("sys").modules,
        "turing_deinterleaving_challenge",
        SimpleNamespace(PulseTrain=PulseTrain),
    )
    loaded = load_pulse_train(path)
    assert loaded.loader == "PulseTrain.load"
    assert loaded.data.shape[0] == 1


def test_wise_records_wrapper_and_tsv(tmp_path: Path) -> None:
    from smartscan.data.wise import validate_wise

    json_path = tmp_path / "w.json"
    json_path.write_text(
        '{"records": [{"source_record_id": "A", "emitter_family": "x",'
        ' "frequency_min_hz": 2.5e9, "frequency_max_hz": 2.6e9}]}',
        encoding="utf-8",
    )
    assert validate_wise(json_path).ok
    tsv = tmp_path / "w.tsv"
    tsv.write_text(
        "source_record_id\temitter_family\tfrequency_min_hz\tfrequency_max_hz\n"
        "B\ty\t2500000000\t2600000000\n",
        encoding="utf-8",
    )
    assert validate_wise(tsv).ok
    with pytest.raises(SmartScanError):
        validate_wise(tmp_path / "w.bin")
