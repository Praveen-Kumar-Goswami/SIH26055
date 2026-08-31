"""Environment doctor for Stages 1–7."""

from __future__ import annotations

import sys

from smartscan import GENERATOR_VERSION, SCHEMA_VERSION, __version__
from smartscan.config import project_root
from smartscan.dashboard.services import doctor_report


def main() -> int:
    root = project_root()
    print(f"smartscan {__version__} schema={SCHEMA_VERSION} generator={GENERATOR_VERSION}")
    print(f"python {sys.version.split()[0]}")
    print(f"project_root {root}")
    required = [
        root / "pyproject.toml",
        root / "configs" / "demo.yaml",
        root / "docs" / "SIH26055_BUILD_SPEC.md",
        root / "docs" / "BUILD_CONTRACT.md",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        print("missing:")
        for path in missing:
            print(f"  {path}")
        return 1
    print("stage1_paths_ok")
    report = doctor_report()
    print(f"ok={str(report['ok']).lower()}")
    for item in report["checks"]:
        print(f"  {item['name']} ok={str(item['ok']).lower()} {item['detail']}")
    from smartscan.release.resolve import resolve_best_available

    resolved = resolve_best_available("best-available")
    for line in resolved.lines():
        print(line)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
