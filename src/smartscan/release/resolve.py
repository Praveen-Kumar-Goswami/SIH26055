"""Resolve best-available deployable strategy. Never rename a fallback champion."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from smartscan.config import DashboardConfig, load_yaml, project_root
from smartscan.dashboard.services import load_performance_gate, model_bundle_dir
from smartscan.experiment_protocol import generation_from_bundle_path
from smartscan.types import SmartScanError

CHAMPION = "champion"
CANDIDATE = "candidate"
CTS = "contextual_thompson"
PPO = "ppo"
CTS_STRATEGY = "contextual-thompson"


@dataclass(frozen=True)
class ResolvedStrategy:
    requested: str
    strategy: str
    source: str
    model_dir: str | None
    model_name: str | None
    version: str | None
    note: str

    def lines(self) -> list[str]:
        return [
            f"resolved_strategy={self.strategy}",
            f"resolved_source={self.source}",
            f"resolved_model={self.model_name or '-'}",
            f"resolved_version={self.version or '-'}",
            f"resolved_note={self.note}",
        ]


def _normalize(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def _bundle_meta(model_dir: Path) -> tuple[str | None, str | None, bool]:
    manifest_path = model_dir / "manifest.json"
    if not manifest_path.is_file():
        return None, None, False
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None, False
    return (
        str(payload.get("registered_name") or "SmartScanScheduler"),
        str(payload.get("model_version") or payload.get("version") or ""),
        bool(payload.get("has_ppo")),
    )


def _try_bundle(model_dir: Path) -> object | None:
    if not model_dir.is_dir():
        return None
    from smartscan.ml.bundle import load_bundle

    try:
        return load_bundle(model_dir)
    except (OSError, SmartScanError, json.JSONDecodeError, KeyError):
        return None


def resolve_best_available(requested: str = "best-available") -> ResolvedStrategy:
    """Champion only if the frozen gate passed. Otherwise candidate bundle or CTS."""

    raw = requested.strip()
    name = _normalize(raw)
    if name not in {"best-available", "best", "bestavailable"}:
        from smartscan.ml.strategy_registry import canonicalize_strategy_id

        canonical = canonicalize_strategy_id(raw)
        return ResolvedStrategy(
            requested=raw,
            strategy=canonical,
            source="explicit",
            model_dir=os.environ.get("SMARTSCAN_MODEL_DIR"),
            model_name=None,
            version=None,
            note="explicit strategy; not resolved through best-available",
        )
    dash = DashboardConfig.model_validate(load_yaml(project_root() / "configs" / "dashboard.yaml"))
    gate = load_performance_gate()
    model_dir = model_bundle_dir(dash)
    bundle = _try_bundle(model_dir)
    name_m, _manifest_version, has_ppo = _bundle_meta(model_dir) if model_dir.is_dir() else (None, None, False)
    passed = bool(gate.get("performance_gate_passed"))
    if passed and bundle is not None and has_ppo:
        return ResolvedStrategy(
            requested=raw,
            strategy=PPO,
            source=CHAMPION,
            model_dir=str(model_dir),
            model_name=name_m or "SmartScanScheduler",
            version=generation_from_bundle_path(model_dir),
            note="performance_gate_passed=true; using champion PPO bundle",
        )
    if bundle is not None and has_ppo:
        return ResolvedStrategy(
            requested=raw,
            strategy=PPO,
            source=CANDIDATE,
            model_dir=str(model_dir),
            model_name=name_m or "SmartScanScheduler",
            version=generation_from_bundle_path(model_dir),
            note=(
                "performance_gate_passed=false; structurally valid candidate PPO. "
                f"resolved_model=SmartScanScheduler resolved_version={generation_from_bundle_path(model_dir)}. "
                "Not renamed champion. Official gate remains v2_frozen_gate failed."
            ),
        )
    return ResolvedStrategy(
        requested=raw,
        strategy=CTS_STRATEGY,
        source=CTS,
        model_dir=None,
        model_name=None,
        version=None,
        note="no valid PPO bundle; falling back to contextual-thompson (not champion)",
    )
