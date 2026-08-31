"""Refuse final evidence if Stage 5 frozen configs were rewritten."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from smartscan.config import project_root
from smartscan.types import SmartScanError, content_fingerprint, sha256_file

FROZEN_PATH = "configs/frozen_hashes.json"


def load_frozen_record(root: Path | None = None) -> dict[str, Any]:
    dest = (root or project_root()) / FROZEN_PATH
    if not dest.is_file():
        raise SmartScanError(f"Missing frozen hash record: {dest}")
    payload: Any = json.loads(dest.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SmartScanError("frozen_hashes.json must be a JSON object.")
    return payload


def current_hashes(root: Path | None = None) -> dict[str, str]:
    base = root or project_root()
    manifest_path = base / "configs" / "held_out_manifest.json"
    bench_path = base / "configs" / "benchmark_final.yaml"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "held_out_manifest_sha256": sha256_file(manifest_path),
        "benchmark_final_yaml_sha256": sha256_file(bench_path),
        "held_out_manifest_content_fingerprint": content_fingerprint(
            {k: v for k, v in manifest.items() if k != "content_fingerprint"}
        ),
    }


def require_frozen_hashes(root: Path | None = None) -> dict[str, str]:
    """Raise if benchmark_final.yaml or held_out_manifest.json drifted from Stage 5."""

    record = load_frozen_record(root)
    now = current_hashes(root)
    mismatches: list[str] = []
    for key in (
        "held_out_manifest_sha256",
        "benchmark_final_yaml_sha256",
        "held_out_manifest_content_fingerprint",
    ):
        expected = str(record.get(key) or "")
        actual = now[key]
        if expected != actual:
            mismatches.append(f"{key}: expected {expected} got {actual}")
    if mismatches:
        raise SmartScanError(
            "Frozen Stage 5 benchmark/manifest hashes differ. "
            "Refusing final evidence. This invalidates prior held-out results. "
            + "; ".join(mismatches)
        )
    return now
