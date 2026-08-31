from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from smartscan.cli import main
from smartscan.rf.environment import simulate
from smartscan.rf.io import load_ground_truth, save_ground_truth
from smartscan.types import SmartScanError

SCENARIOS = ("sparse", "dense", "agile_threat", "edge_zero")


@pytest.mark.parametrize("scenario_id", SCENARIOS)
def test_builtin_scenarios_validate(scenario_id: str, tmp_path: Path) -> None:
    truth = simulate(
        {
            "seed": 42,
            "dt_s": 0.001,
            "duration_s": 0.4,
            "band_plan_id": "demo_2_18",
            "scenario_id": scenario_id,
        }
    )
    if scenario_id == "edge_zero":
        assert not truth.occupied.any()
        assert np.allclose(truth.signal_power_w, 0)
        assert len(truth.events) == 0
    else:
        assert truth.occupied.any()
    if scenario_id == "agile_threat":
        ids = {record.emitter_id for record in truth.events.records()}
        assert "late_unseen" in ids
        weights = {
            record.emitter_id: record.threat_weight for record in truth.events.records()
        }
        assert weights.get("late_unseen") == 5.0
        late = [r for r in truth.events.records() if r.emitter_id == "late_unseen"]
        assert late and late[0].start_step >= truth.n_steps // 2
    path = tmp_path / f"{scenario_id}.npz"
    save_ground_truth(truth, path)
    loaded = load_ground_truth(path)
    assert np.array_equal(loaded.occupied, truth.occupied)


def test_conflicting_emitter_ids() -> None:
    with pytest.raises(SmartScanError, match="Conflicting"):
        simulate(
            {
                "seed": 0,
                "dt_s": 0.001,
                "duration_s": 0.01,
                "band_plan_id": "demo_2_18",
                "scenario_id": "sparse",
                "emitters": [
                    {"kind": "continuous", "emitter_id": "dup", "frequency_hz": 3.5e9, "power_w": 1.0},
                    {"kind": "continuous", "emitter_id": "dup", "frequency_hz": 4.5e9, "power_w": 1.0},
                ],
            }
        )


def test_cli_simulate_and_inspect(tmp_path: Path) -> None:
    out = tmp_path / "stage1_demo.npz"
    code = main(
        [
            "simulate",
            "--config",
            "configs/demo.yaml",
            "--output",
            str(out),
        ]
    )
    assert code == 0
    assert out.is_file()
    assert main(["inspect-ground-truth", str(out)]) == 0


def test_cli_wise() -> None:
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "wise_synthetic.csv"
    assert main(["validate-wise", "--input", str(fixture)]) == 0


def test_cli_import_turing(tsrd_stare_path: Path, tmp_path: Path) -> None:
    out = tmp_path / "tsrd.npz"
    assert (
        main(
            [
                "import-turing",
                "--input",
                str(tsrd_stare_path),
                "--band-plan",
                "demo_2_18",
                "--output",
                str(out),
                "--duration",
                "0.01",
            ]
        )
        == 0
    )
    loaded = load_ground_truth(out)
    assert loaded.provenance.source == "tsrd"
