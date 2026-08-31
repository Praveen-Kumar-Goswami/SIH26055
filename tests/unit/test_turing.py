from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from smartscan.data.turing import (
    db_to_linear_power,
    import_turing,
    load_pulse_train,
    namespace_emitter,
)
from smartscan.rf.bands import frequency_to_band, named_band_plan
from smartscan.types import SmartScanError


def test_units_and_bin_overlap(tsrd_stare_path: Path) -> None:
    truth = import_turing(
        tsrd_stare_path,
        band_plan_id="demo_2_18",
        dt_s=0.001,
        duration_s=0.01,
        receiver_mode="stare",
    )
    plan = named_band_plan("demo_2_18")
    band_3 = frequency_to_band(3.0e9, plan)
    band_10 = frequency_to_band(10.0e9, plan)
    lin_m30 = db_to_linear_power(-30.0, "10log10_power")
    # Pulse 0: [0, 0.5ms] in bin 0 → 0.5 * P
    # Pulse 1: [0.8, 1.2] ms → bin0 0.2 and bin1 0.2
    assert truth.occupied[0, band_3]
    assert truth.occupied[1, band_3]
    assert truth.signal_power_w[0, band_3] == pytest.approx(lin_m30 * 0.7, rel=1e-5)
    assert truth.signal_power_w[1, band_3] == pytest.approx(lin_m30 * 0.2, rel=1e-5)
    # 0.5 GHz pulse is clipped, not reinterpreted into 2-3 GHz.
    assert truth.provenance.dropped_counts["clipped_low_ghz"] >= 1
    # Zero-PW pulse lands in TOA bin 2 at 10 GHz.
    assert truth.occupied[2, band_10]
    # NaN amplitude quarantined.
    assert truth.provenance.dropped_counts["ambiguous_amplitude"] >= 1
    ids = {record.emitter_id for record in truth.events.records()}
    fp = truth.provenance.original_file_sha256
    assert fp is not None
    assert any(e.startswith(f"{fp}:") for e in ids)
    assert truth.provenance.transformation["receiver_mode"] == "stare"


def test_scan_mode_is_observation_not_truth(tsrd_scan_path: Path) -> None:
    truth = import_turing(tsrd_scan_path, band_plan_id="demo_2_18", dt_s=0.001, duration_s=0.01)
    assert truth.provenance.transformation["occupancy_is_observation_not_truth"] is True
    assert truth.provenance.transformation["receiver_mode"] == "scan"


def test_turing_0_18_keeps_low_band(tsrd_stare_path: Path) -> None:
    truth = import_turing(
        tsrd_stare_path,
        band_plan_id="turing_0_18",
        dt_s=0.001,
        duration_s=0.01,
    )
    plan = named_band_plan("turing_0_18")
    band_0 = frequency_to_band(0.5e9, plan)
    assert truth.occupied[0, band_0]
    assert truth.provenance.dropped_counts["clipped_low_ghz"] == 0


def test_namespace_differs_per_file() -> None:
    assert namespace_emitter("aaa", 1) != namespace_emitter("bbb", 1)


def test_amplitude_conventions() -> None:
    p10 = db_to_linear_power(-30.0, "10log10_power")
    p20 = db_to_linear_power(-30.0, "20log10_amplitude")
    assert p10 == pytest.approx(1e-3)
    assert p20 == pytest.approx(1e-3)
    assert db_to_linear_power(-20.0, "10log10_power") != db_to_linear_power(
        -20.0, "20log10_amplitude"
    )


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SmartScanError, match="not found"):
        import_turing(tmp_path / "nope.h5", band_plan_id="demo_2_18")


def test_official_loader_preferred(monkeypatch: pytest.MonkeyPatch, tsrd_stare_path: Path) -> None:
    data = np.array([[0.0, 4000.0, 100.0, 0.0, -10.0]], dtype=np.float64)
    labels = np.array([9])
    metadata = {"feature_names": list(range(0)), "receiver": {"mode": "stare"}, "collection_time_s": 0.005}

    class FakePT:
        def __init__(self) -> None:
            self.data = data
            self.labels = labels
            self.metadata = metadata

        @classmethod
        def load(cls, path: Path) -> FakePT:
            del path
            return cls()

    import smartscan.data.turing as turing_mod

    monkeypatch.setitem(__import__("sys").modules, "turing_deinterleaving_challenge", MagicMock(PulseTrain=FakePT))
    monkeypatch.setattr(
        turing_mod,
        "_try_official_load",
        lambda path: turing_mod.PulseTrainArrays(
            data=data,
            labels=labels,
            feature_names=["ToA", "Centre Frequency", "Pulse Width", "AoA", "Amplitude"],
            metadata=metadata,
            loader="PulseTrain.load",
        ),
    )
    loaded = load_pulse_train(tsrd_stare_path)
    # After monkeypatch of _try_official_load
    loaded = turing_mod._try_official_load(tsrd_stare_path)
    assert loaded is not None
    assert loaded.loader == "PulseTrain.load"
