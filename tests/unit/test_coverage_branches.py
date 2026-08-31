from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from smartscan.data.turing import (
    PulseTrainArrays,
    _feature_names_from_metadata,
    _infer_n_steps,
    _metadata_to_dict,
    _resolve_mode,
    _split_columns,
    db_to_linear_power,
    import_turing,
)
from smartscan.data.wise import WiseRecord, _normalize_row, validate_wise
from smartscan.rf.emitters import ContinuousEmitter, emitter_from_dict
from smartscan.rf.environment import simulate
from smartscan.rf.io import load_ground_truth, save_ground_truth
from smartscan.types import SmartScanError


def test_wise_record_edge_cases() -> None:
    with pytest.raises((SmartScanError, ValidationError), match="nonempty"):
        WiseRecord(
            source_record_id=" ",
            emitter_family="x",
            frequency_min_hz=2.5e9,
            frequency_max_hz=2.6e9,
        )
    with pytest.raises((SmartScanError, ValidationError), match="must exceed"):
        WiseRecord(
            source_record_id="a",
            emitter_family="x",
            frequency_min_hz=2.6e9,
            frequency_max_hz=2.5e9,
        )
    with pytest.raises((SmartScanError, ValidationError), match="finite and positive"):
        WiseRecord(
            source_record_id="a",
            emitter_family="x",
            frequency_min_hz=2.5e9,
            frequency_max_hz=2.6e9,
            pri_s=-1.0,
        )
    with pytest.raises((SmartScanError, ValidationError), match="PRI and PRF"):
        WiseRecord(
            source_record_id="a",
            emitter_family="x",
            frequency_min_hz=2.5e9,
            frequency_max_hz=2.6e9,
            pri_s=0.001,
            prf_hz=50.0,
        )
    with pytest.raises((SmartScanError, ValidationError), match="public_threat"):
        WiseRecord(
            source_record_id="a",
            emitter_family="x",
            frequency_min_hz=2.5e9,
            frequency_max_hz=2.6e9,
            public_threat_priority=-2.0,
        )


def test_wise_json_and_missing_fields(tmp_path: Path) -> None:
    bad_list = tmp_path / "x.json"
    bad_list.write_text('{"nope": 1}', encoding="utf-8")
    with pytest.raises(SmartScanError, match="list of records"):
        validate_wise(bad_list)
    not_obj = tmp_path / "y.json"
    not_obj.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(SmartScanError, match="objects"):
        validate_wise(not_obj)
    with pytest.raises(SmartScanError, match="Missing required"):
        _normalize_row({"source_record_id": "a"})
    row = _normalize_row(
        {
            "source_record_id": "a",
            "emitter_family": "x",
            "frequency_min_hz": 2.5e9,
            "frequency_max_hz": 2.6e9,
            "pri_s": "",
            "ignored": 1,
        }
    )
    assert row["pri_s"] is None


def test_turing_helpers() -> None:
    with pytest.raises(SmartScanError, match="Unknown amplitude"):
        db_to_linear_power(-10.0, "bogus")  # type: ignore[arg-type]
    with pytest.raises(SmartScanError, match="shape"):
        _split_columns(
            PulseTrainArrays(
                data=np.zeros((3, 2)),
                labels=None,
                feature_names=[],
                metadata={},
                loader="t",
            )
        )
    loaded = PulseTrainArrays(
        data=np.zeros((2, 5)),
        labels=np.array([1]),
        feature_names=[],
        metadata={},
        loader="t",
    )
    with pytest.raises(SmartScanError, match="labels length"):
        _split_columns(loaded)
    ok = PulseTrainArrays(
        data=np.zeros((2, 5)),
        labels=None,
        feature_names=["ToA", "Centre Frequency", "Pulse Width", "AoA", "Amplitude"],
        metadata={},
        loader="t",
    )
    toa, *_rest = _split_columns(ok)
    assert toa.shape == (2,)
    assert _infer_n_steps(np.array([]), np.array([]), 0.001, None, {}) == 1
    assert _infer_n_steps(np.array([2500.0]), np.array([0.0]), 0.001, None, {}) == 3
    assert _resolve_mode({"description": "scan receiver"}, "auto") == "scan"
    assert _resolve_mode({"receiver_mode": "stare"}, "auto") == "stare"
    assert _metadata_to_dict(None) == {}
    assert _metadata_to_dict({"a": 1})["a"] == 1

    class Dump:
        __slots__ = ()

        def model_dump(self) -> dict[str, int]:
            return {"k": 1}

    assert _metadata_to_dict(Dump())["k"] == 1
    assert "repr" in _metadata_to_dict(object())
    names = _feature_names_from_metadata({"feature_names": [b"ToA", b"Centre Frequency"]}, 5)
    assert names[0] == "ToA"
    arr_names = _feature_names_from_metadata(
        {"feature_names": np.array([b"ToA", b"Centre Frequency"], dtype="S")}, 5
    )
    assert arr_names[0] == "ToA"
    assert _feature_names_from_metadata({"feature_names": 123}, 5)[0] == "toa_us"


def test_import_without_duration_and_late_pulse(tmp_path: Path) -> None:
    import h5py

    path = tmp_path / "late.h5"
    data = np.array([[50_000.0, 3000.0, 100.0, 0.0, -30.0]], dtype=np.float32)
    with h5py.File(path, "w") as handle:
        handle.create_dataset("data", data=data)
        handle.create_dataset("labels", data=np.array([1], dtype=np.int8))
        meta = handle.create_group("metadata")
        meta.attrs["collection_time_s"] = 0.01
        meta.attrs["description"] = "stare fixture"
        rx = meta.create_group("receiver")
        rx.attrs["type"] = "stare"
    truth = import_turing(path, band_plan_id="demo_2_18", dt_s=0.001)
    assert truth.n_steps == 10
    assert truth.provenance.dropped_counts["dropped_out_of_range"] >= 1


def test_emitter_validation_and_end_step() -> None:
    with pytest.raises((SmartScanError, ValidationError)):
        ContinuousEmitter(emitter_id="", frequency_hz=3.5e9, power_w=1.0)
    with pytest.raises((SmartScanError, ValidationError)):
        ContinuousEmitter(emitter_id="a", frequency_hz=3.5e9, power_w=1.0, start_step=-1)
    with pytest.raises((SmartScanError, ValidationError)):
        ContinuousEmitter(
            emitter_id="a", frequency_hz=3.5e9, power_w=1.0, start_step=5, end_step=2
        )
    with pytest.raises((SmartScanError, ValidationError)):
        ContinuousEmitter(
            emitter_id="a", frequency_hz=3.5e9, power_w=1.0, threat_weight=-1.0
        )
    emitter = emitter_from_dict(
        {
            "kind": "continuous",
            "emitter_id": "g",
            "frequency_hz": 3.5e9,
            "power_w": 1.0,
            "end_step": 4,
            "gate": {"kind": "always"},
        }
    )
    from smartscan.rf.bands import named_band_plan

    occ, _ = emitter.render(10, named_band_plan("demo_2_18"), 0.001)
    assert occ[4:].sum() == 0
    assert occ[:4].any()


def test_io_recompute_fingerprint_and_hdf5_suffix(tmp_path: Path) -> None:
    truth = simulate(
        {
            "seed": 0,
            "dt_s": 0.001,
            "duration_s": 0.02,
            "band_plan_id": "demo_2_18",
            "scenario_id": "edge_zero",
        }
    )
    truth.content_fingerprint = ""
    dest = tmp_path / "z.hdf5"
    leftover = dest.with_name(dest.name + ".writing")
    leftover.write_bytes(b"old")
    save_ground_truth(truth, dest)
    loaded = load_ground_truth(dest)
    assert loaded.content_fingerprint
    npz = tmp_path / "z.npz"
    writing = npz.with_name(npz.stem + ".writing.npz")
    writing.write_bytes(b"old")
    save_ground_truth(truth, npz)
    bogus = tmp_path / "bad.npz"
    np.savez(bogus, not_the_keys=np.array([1]))
    with pytest.raises(SmartScanError, match="missing keys"):
        load_ground_truth(bogus)
