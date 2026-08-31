"""Generate Stage 1 demo GroundTruth and the Stage 6 matched replay bundle."""

from __future__ import annotations

from smartscan.cli import main as cli_main
from smartscan.config import project_root
from smartscan.dashboard.services import load_dashboard_config, prepare_demo_bundle


def main() -> int:
    config = project_root() / "configs" / "demo.yaml"
    output = project_root() / "artifacts" / "runs" / "stage1_demo.npz"
    status = cli_main(["simulate", "--config", str(config), "--output", str(output)])
    if status != 0:
        return status
    dash = load_dashboard_config()
    prepare_demo_bundle(dash, include_ppo=True)
    print("wrote artifacts/demo matched agile_threat bundle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
