"""Legal synthetic PDW sample for the held-out pack (not the gated TSRD corpus)."""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np


def write_tiny_tsrd(path: Path, *, mode: str = "stare") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
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
        meta.attrs["collection_time_s"] = 0.01
        rx = meta.create_group("receiver")
        rx.attrs["mode"] = mode
    return path
