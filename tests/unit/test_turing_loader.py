from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest

from smartscan.data.turing import db_to_linear_power, import_turing, load_pulse_train
from smartscan.types import SmartScanError


def test_load_published_layout(tsrd_stare_path: Path) -> None:
    loaded = load_pulse_train(tsrd_stare_path)
    assert loaded.data.shape == (5, 5)
    assert loaded.labels is not None
    assert loaded.loader == "h5py_pulsetrain_layout"
    assert any("frequency" in n.lower() for n in loaded.feature_names)


def test_missing_data_group(tmp_path: Path) -> None:
    path = tmp_path / "bad.h5"
    with h5py.File(path, "w") as handle:
        handle.create_dataset("not_data", data=np.arange(3))
    with pytest.raises(SmartScanError, match="PulseTrain"):
        load_pulse_train(path)


def test_20log10_convention(tsrd_stare_path: Path) -> None:
    truth = import_turing(
        tsrd_stare_path,
        band_plan_id="demo_2_18",
        dt_s=0.001,
        duration_s=0.01,
        amplitude_convention="20log10_amplitude",
    )
    lin = db_to_linear_power(-30.0, "20log10_amplitude")
    assert lin == pytest.approx(1e-3)
    assert truth.provenance.transformation["amplitude_convention"] == "20log10_amplitude"


def test_nonfinite_db() -> None:
    with pytest.raises(SmartScanError):
        db_to_linear_power(float("nan"), "10log10_power")
