from __future__ import annotations

from pathlib import Path

from smartscan.cli import main
from smartscan.receiver.logs import diagnostic_counts, load_receiver_run, save_receiver_run
from smartscan.receiver.scanner import run_schedule
from smartscan.receiver.schedules import SequentialSchedule, UniformRandomSchedule
from smartscan.rf.environment import simulate
from smartscan.rf.io import save_ground_truth
from smartscan.types import ReceiverConfig


def _short_truth():
    return simulate(
        {
            "seed": 42,
            "dt_s": 0.001,
            "duration_s": 0.4,
            "band_plan_id": "demo_2_18",
            "scenario_id": "sparse",
        }
    )


def test_log_roundtrip_and_fingerprint(tmp_path: Path) -> None:
    truth = _short_truth()
    cfg = ReceiverConfig(receiver_ibw_hz=1e8, scan_span_hz=16e9, pfa_design=1e-3)
    run = run_schedule(truth, SequentialSchedule(8), cfg, receiver_seed=42)
    path = tmp_path / "stage2.npz"
    save_receiver_run(run, path)
    loaded = load_receiver_run(path)
    assert loaded.observations.ground_truth_fingerprint == truth.content_fingerprint
    assert loaded.artifact_sha256 == run.artifact_sha256
    assert [r.hit for r in loaded.decisions.rows] == [r.hit for r in run.decisions.rows]
    diag = diagnostic_counts(truth, loaded)
    assert diag["completed_dwells"] == len(loaded.decisions.rows)
    assert 0.0 <= diag["tuning_fraction"] <= 1.0


def test_random_schedule_seed_independent_of_receiver_seed() -> None:
    truth = _short_truth()
    cfg = ReceiverConfig(receiver_ibw_hz=1e8, scan_span_hz=16e9, pfa_design=0.15)
    a = run_schedule(truth, UniformRandomSchedule(seed=0), cfg, receiver_seed=1)
    b = run_schedule(truth, UniformRandomSchedule(seed=0), cfg, receiver_seed=2)
    assert [r.target_band for r in a.decisions.rows] == [r.target_band for r in b.decisions.rows]
    assert [r.dwell_steps for r in a.decisions.rows] == [r.dwell_steps for r in b.decisions.rows]
    assert [r.hit for r in a.decisions.rows] != [r.hit for r in b.decisions.rows]


def test_cli_receive(tmp_path: Path) -> None:
    truth = _short_truth()
    tpath = tmp_path / "truth.npz"
    save_ground_truth(truth, tpath)
    out = tmp_path / "stage2_seq.npz"
    code = main(
        [
            "receive",
            "--truth",
            str(tpath),
            "--strategy",
            "sequential",
            "--seed",
            "42",
            "--output",
            str(out),
            "--dwell",
            "8",
        ]
    )
    assert code == 0
    assert out.is_file()
    loaded = load_receiver_run(out)
    assert loaded.decisions.rows


def test_cli_receive_random_and_priority(tmp_path: Path) -> None:
    truth = _short_truth()
    tpath = tmp_path / "truth.npz"
    save_ground_truth(truth, tpath)
    random_out = tmp_path / "stage2_random.npz"
    assert (
        main(
            [
                "receive",
                "--truth",
                str(tpath),
                "--strategy",
                "random",
                "--seed",
                "42",
                "--schedule-seed",
                "7",
                "--output",
                str(random_out),
            ]
        )
        == 0
    )
    priority_out = tmp_path / "stage2_priority.npz"
    assert (
        main(
            [
                "receive",
                "--truth",
                str(tpath),
                "--strategy",
                "fixed-priority",
                "--seed",
                "42",
                "--priority",
                "8,4,10",
                "--dwell",
                "4",
                "--output",
                str(priority_out),
            ]
        )
        == 0
    )
    loaded = load_receiver_run(priority_out)
    bands = [row.target_band for row in loaded.decisions.rows]
    assert bands[:3] == [8, 4, 10]


def test_cli_receive_periodic_intercept_and_invalid(tmp_path: Path) -> None:
    from io import StringIO
    from unittest.mock import patch

    truth = _short_truth()
    tpath = tmp_path / "truth.npz"
    save_ground_truth(truth, tpath)
    out = tmp_path / "periodic.npz"
    assert (
        main(
            [
                "receive",
                "--truth",
                str(tpath),
                "--strategy",
                "periodic-intercept",
                "--seed",
                "42",
                "--output",
                str(out),
            ]
        )
        == 0
    )
    loaded = load_receiver_run(out)
    assert loaded.decisions.rows
    buf = StringIO()
    with patch("sys.stderr", buf):
        code = main(
            [
                "receive",
                "--truth",
                str(tpath),
                "--strategy",
                "nope-strategy",
                "--output",
                str(tmp_path / "bad.npz"),
            ]
        )
    assert code == 2
    assert "Unknown strategy" in buf.getvalue() or "Public strategies" in buf.getvalue()
