from __future__ import annotations

from pathlib import Path

import numpy as np
from tests.unit.test_metrics import dec, logs_from_decisions, make_truth

from smartscan.cli import main
from smartscan.metrics.engine import load_metrics
from smartscan.receiver.logs import ReceiverRun, save_receiver_run
from smartscan.rf.io import save_ground_truth


def test_cli_metrics_and_sensitivity(tmp_path: Path) -> None:
    occupied = np.zeros((8, 1), dtype=bool)
    occupied[0:4, 0] = True
    truth = make_truth(occupied)
    obs, dlog = logs_from_decisions(
        truth, [dec("d0", start=0, tune_end=0, end=4, band=0, hit=True)]
    )
    tpath = tmp_path / "truth.npz"
    lpath = tmp_path / "run.npz"
    save_ground_truth(truth, tpath)
    save_receiver_run(ReceiverRun(observations=obs, decisions=dlog), lpath)
    out = tmp_path / "metrics.json"
    csv_out = tmp_path / "metrics.csv"
    assert (
        main(
            [
                "metrics",
                "--truth",
                str(tpath),
                "--log",
                str(lpath),
                "--output",
                str(out),
                "--csv",
                str(csv_out),
            ]
        )
        == 0
    )
    loaded = load_metrics(out)
    assert loaded.report.metrics["pd"].value == 1.0
    assert csv_out.is_file()
    sens = tmp_path / "sensitivity.json"
    assert (
        main(
            [
                "sensitivity",
                "--target-pd",
                "0.9",
                "--output",
                str(sens),
                "--analytic-only",
            ]
        )
        == 0
    )
    assert sens.is_file()
