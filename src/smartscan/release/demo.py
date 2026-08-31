"""Offline demo: load frozen matched runs and model. Never download or retrain."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from smartscan.config import project_root
from smartscan.dashboard.services import (
    demo_bundle_is_complete,
    demo_dir,
    load_dashboard_config,
    prepare_demo_bundle,
)
from smartscan.release.resolve import resolve_best_available
from smartscan.storage.db import StorageSettings, upgrade_database
from smartscan.types import sha256_file


def run_offline_demo(*, dest: Path | None = None, rebuild: bool = False) -> dict[str, Any]:
    settings = StorageSettings.from_env()
    settings.ensure_directories()
    upgrade_database(settings.domain_db_url)
    dash = load_dashboard_config()
    out = dest or demo_dir(dash)
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifest.json"
    resolved = resolve_best_available()
    rebuilt = False
    loaded: dict[str, Any] | None = None
    if manifest_path.is_file():
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            loaded = raw if isinstance(raw, dict) else None
        except json.JSONDecodeError:
            loaded = None
    if rebuild or loaded is None or not demo_bundle_is_complete(out):
        include_ppo = resolved.strategy == "ppo"
        manifest = prepare_demo_bundle(dash, dest=out, include_ppo=include_ppo)
        rebuilt = True
    else:
        manifest = loaded
    files: dict[str, str] = {}
    truth_path = out / "truth.npz"
    if truth_path.is_file():
        files["truth.npz"] = sha256_file(truth_path)
    checksums = None
    model_dir = project_root() / dash.model_dir
    checksums_path = model_dir / "checksums.json"
    if checksums_path.is_file():
        checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
    payload = {
        "offline": True,
        "retrained": False,
        "downloaded": False,
        "rebuilt_demo_runs": rebuilt,
        "demo_dir": str(out),
        "manifest": manifest,
        "file_sha256": files,
        "bundle_checksums": checksums,
        "resolved_strategy": resolved.strategy,
        "resolved_source": resolved.source,
        "resolved_model": resolved.model_name,
        "resolved_version": resolved.version,
        "note": resolved.note,
        "next": "python -m smartscan.cli dashboard",
    }
    merged = dict(manifest)
    merged["bundle_content_fingerprint"] = (checksums or {}).get("content_fingerprint")
    merged["file_sha256"] = dict(files)
    (out / "manifest.json").write_text(
        json.dumps(merged, indent=2, sort_keys=True), encoding="utf-8"
    )
    files["manifest.json"] = sha256_file(out / "manifest.json")
    payload["manifest"] = merged
    payload["file_sha256"] = files
    (out / "offline_status.json").write_text(
        json.dumps(
            {
                "offline": True,
                "retrained": False,
                "downloaded": False,
                "resolved_source": resolved.source,
                "truth_fingerprint": manifest.get("truth_fingerprint"),
                "bundle_content_fingerprint": (checksums or {}).get("content_fingerprint"),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return payload
