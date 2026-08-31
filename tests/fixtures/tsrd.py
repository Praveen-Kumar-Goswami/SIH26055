"""Tiny synthetic TSRD-style pulse-train writer for offline tests."""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np


def write_tsrd_fixture(
    path: Path,
    *,
    mode: str = "stare",
    collection_time_s: float = 0.01,
) -> Path:
    """Write a few PDWs using the published PulseTrain HDF5 layout.

    Columns: ToA us, Centre Frequency MHz, Pulse Width us, AoA deg, Amplitude dB.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    # Pulse 0: 3.0 GHz, TOA=0, PW=500 us, -30 dB, label 1  (demo band 1)
    # Pulse 1: 3.5 GHz, TOA=800 us, PW=400 us (crosses 1 ms bin), -30 dB, label 1
    # Pulse 2: 0.5 GHz, TOA=0, PW=200 us, clipped by demo_2_18, label 2
    # Pulse 3: 10.0 GHz, TOA=2000 us, PW=0, -20 dB, label 3
    # Pulse 4: 10.0 GHz, TOA=2500 us, PW=100 us, amplitude NaN, quarantined, label 3
    data = np.array(
        [
            [0.0, 3000.0, 500.0, 10.0, -30.0],
            [800.0, 3500.0, 400.0, 11.0, -30.0],
            [0.0, 500.0, 200.0, 0.0, -40.0],
            [2000.0, 10000.0, 0.0, -5.0, -20.0],
            [2500.0, 10000.0, 100.0, -5.0, np.nan],
        ],
        dtype=np.float32,
    )
    labels = np.array([1, 1, 2, 3, 3], dtype=np.int8)
    names = np.array(
        [b"ToA", b"Centre Frequency", b"Pulse Width", b"AoA", b"Amplitude"],
        dtype="S",
    )
    with h5py.File(path, "w") as handle:
        handle.create_dataset("data", data=data, compression="gzip")
        handle.create_dataset("labels", data=labels, compression="gzip")
        meta = handle.create_group("metadata")
        meta.create_dataset("feature_names", data=names)
        meta.attrs["type"] = "synthetic"
        meta.attrs["collection_time_s"] = collection_time_s
        meta.attrs["description"] = f"tiny {mode} fixture"
        meta.attrs["num_pulses"] = int(data.shape[0])
        rx = meta.create_group("receiver")
        rx.attrs["mode"] = mode
    return path
