from __future__ import annotations

from smartscan.cli import main
from smartscan.config import project_root


def test_collect_smoke(tmp_path) -> None:  # type: ignore[no-untyped-def]
    cfg = project_root() / "configs" / "train_smoke.yaml"
    out = tmp_path / "ds"
    rc = main(["collect", "--config", str(cfg), "--output", str(out)])
    assert rc == 0
    assert (out / "manifest.json").is_file()
    assert (out / "dataset.npz").is_file()


def test_cli_help_stage5() -> None:
    try:
        main(["evaluate", "--help"])
    except SystemExit as exc:
        assert exc.code == 0
