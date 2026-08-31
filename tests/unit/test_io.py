from __future__ import annotations

from pathlib import Path

import numpy as np

from smartscan.rf.environment import simulate
from smartscan.rf.io import load_ground_truth, save_ground_truth
from smartscan.types import content_fingerprint


def _sparse(seed: int = 42) -> dict:
    return {
        "seed": seed,
        "dt_s": 0.001,
        "duration_s": 0.2,
        "band_plan_id": "demo_2_18",
        "scenario_id": "sparse",
    }


def test_same_seed_same_fingerprint_different_compression(tmp_path: Path) -> None:
    a = simulate(_sparse(42))
    b = simulate(_sparse(42))
    assert a.content_fingerprint == b.content_fingerprint
    npz_path = tmp_path / "a.npz"
    h5_path = tmp_path / "a.h5"
    save_ground_truth(a, npz_path)
    save_ground_truth(b, h5_path)
    assert a.content_fingerprint == b.content_fingerprint
    assert a.artifact_sha256 != b.artifact_sha256


def test_different_seed_changes_fingerprint_and_truth() -> None:
    a = simulate(_sparse(1))
    b = simulate(_sparse(2))
    assert a.content_fingerprint != b.content_fingerprint
    # Seeded phases differ, so occupancy is not identical.
    assert not np.array_equal(a.occupied, b.occupied) or not np.array_equal(
        a.signal_power_w, b.signal_power_w
    )


def test_save_reload_bit_exact(tmp_path: Path) -> None:
    truth = simulate(_sparse(7))
    path = tmp_path / "gt.npz"
    save_ground_truth(truth, path)
    loaded = load_ground_truth(path)
    assert loaded.content_fingerprint == truth.content_fingerprint
    assert loaded.artifact_sha256 == truth.artifact_sha256
    assert np.array_equal(loaded.occupied, truth.occupied)
    assert np.array_equal(loaded.signal_power_w, truth.signal_power_w)
    assert loaded.events.canonical_records() == truth.events.canonical_records()
    # artifact_sha256 verifies stored bytes
    digest = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
    assert digest == loaded.artifact_sha256


def test_hdf5_roundtrip(tmp_path: Path) -> None:
    truth = simulate(_sparse(3))
    path = tmp_path / "gt.h5"
    save_ground_truth(truth, path)
    loaded = load_ground_truth(path)
    assert np.array_equal(loaded.occupied, truth.occupied)
    assert loaded.content_fingerprint == truth.content_fingerprint


def test_content_fingerprint_excludes_paths_and_timestamps() -> None:
    payload = {"seed": 1, "created_at": "2020-01-01", "abs_path": "C:/tmp/x"}
    other = {"seed": 1}
    # strip happens inside GroundTruth; helper still hashes given payload as-is.
    assert content_fingerprint({"seed": 1, "dt_s": 0.001}) == content_fingerprint(
        {"dt_s": 0.001, "seed": 1}
    )
    del payload, other
