"""Live PPO bundle vs official frozen-gate evidence. Never one generic 'model'."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from smartscan.config import DashboardConfig, load_yaml, project_root
from smartscan.experiment_protocol import (
    ACTIVE_MODEL_BUNDLE_RELPATH,
    GATE_EVIDENCE_BUNDLE_RELPATH,
    PROTOCOL_V2_FROZEN_GATE,
    generation_from_bundle_path,
    inspect_bundle_dir,
    official_gate_protocol,
)


def _dash(dash: DashboardConfig | None = None) -> DashboardConfig:
    if dash is not None:
        return dash
    dest = project_root() / "configs" / "dashboard.yaml"
    if dest.is_file():
        return DashboardConfig.model_validate(load_yaml(dest))
    return DashboardConfig()


def active_model_bundle_dir(dash: DashboardConfig | None = None) -> Path:
    """Directory of the PPO weights the dashboard executes (currently v4)."""

    override = os.environ.get("SMARTSCAN_MODEL_DIR")
    if override:
        return Path(override)
    cfg = _dash(dash)
    raw = Path(cfg.model_dir)
    if raw.is_absolute():
        return raw
    return project_root() / raw


def gate_evidence_bundle_dir() -> Path:
    """Historical SmartScanScheduler v2 bundle used only as frozen-gate evidence."""

    return project_root() / GATE_EVIDENCE_BUNDLE_RELPATH


def gate_evidence_path(dash: DashboardConfig | None = None) -> Path:
    cfg = _dash(dash)
    raw = Path(cfg.gate_path)
    if raw.is_absolute():
        return raw
    return project_root() / raw


def active_model_status(dash: DashboardConfig | None = None) -> dict[str, Any]:
    dest = active_model_bundle_dir(dash)
    info = inspect_bundle_dir(dest)
    generation = generation_from_bundle_path(dest)
    return {
        "role": "active_model_bundle",
        "path": str(dest),
        "generation": generation,
        "alias": "candidate",
        "research_status": "Candidate",
        "registered_name": info.get("registered_name") or "SmartScanScheduler",
        "model_version": info.get("model_version"),
        "content_fingerprint": info.get("content_fingerprint"),
        "ok": bool(info.get("ok")),
        "error": info.get("error"),
        "relpath_default": ACTIVE_MODEL_BUNDLE_RELPATH,
    }


def gate_evidence_status(dash: DashboardConfig | None = None) -> dict[str, Any]:
    proto = official_gate_protocol()
    dest = gate_evidence_bundle_dir()
    info = inspect_bundle_dir(dest)
    gate_file = gate_evidence_path(dash)
    passed = False
    found = gate_file.is_file()
    if found:
        import json

        payload = json.loads(gate_file.read_text(encoding="utf-8"))
        passed = bool(payload.get("performance_gate_passed"))
    return {
        "role": "gate_evidence_bundle",
        "protocol_id": PROTOCOL_V2_FROZEN_GATE,
        "path": str(dest),
        "generation": "v2",
        "alias": "champion" if passed else "candidate",
        "gate_status": "Passed" if passed else "Not Passed",
        "performance_gate_passed": passed,
        "gate_file": str(gate_file),
        "gate_file_found": found,
        "registered_name": info.get("registered_name") or "SmartScanScheduler",
        "model_version": info.get("model_version"),
        "content_fingerprint": info.get("content_fingerprint"),
        "ok": bool(info.get("ok")),
        "display_name": proto.display_name,
    }


def dashboard_identity(dash: DashboardConfig | None = None) -> dict[str, Any]:
    return {
        "active_model_bundle": active_model_status(dash),
        "gate_evidence_bundle": gate_evidence_status(dash),
        "champion_set": False,
    }
