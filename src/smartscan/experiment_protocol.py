"""Authoritative evaluation-protocol contract.

Train/val/dev-test disjointness lives in ``smartscan.ml.protocol``.
This module names frozen and live *evaluation* protocols so AIR from one
protocol is never ranked against AIR from another.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

from smartscan.config import project_root
from smartscan.metrics.schemas import METRIC_SCHEMA_VERSION
from smartscan.ml.strategy_registry import (
    HELD_OUT_BASELINE_STRATEGIES,
    PUBLIC_STRATEGIES,
    TOTAL_PUBLIC_STRATEGIES,
)
from smartscan.types import SmartScanError, sha256_file

PROTOCOL_V2_FROZEN_GATE = "v2_frozen_gate"
PROTOCOL_V3_RESEARCH = "v3_research"
PROTOCOL_V4_RESEARCH = "v4_research"
PROTOCOL_LIVE_SESSION = "live_session"
PROTOCOL_LEGACY_UNKNOWN = "legacy_unknown"

CROSS_PROTOCOL_MESSAGE = (
    "These results originate from different experimental protocols and "
    "cannot be interpreted as a direct performance comparison."
)

SOURCE_LIVE_RUN = "LIVE RUN"
SOURCE_RECORDED_PROTOCOL = "RECORDED PROTOCOL"
SOURCE_FROZEN_GATE = "FROZEN GATE"

NOT_RECORDED = "Not recorded"
ORACLE_EVALUATOR_LABEL = "Evaluator-only upper reference"

GATE_EVIDENCE_BUNDLE_RELPATH = "artifacts/models/scheduler_full"
ACTIVE_MODEL_BUNDLE_RELPATH = "artifacts/models/scheduler_v4"
V3_BUNDLE_RELPATH = "artifacts/models/scheduler_v3"

_COMPARABLE_FIELDS: tuple[str, ...] = (
    "protocol_id",
    "scenario_manifest_relpath",
    "scenario_seeds",
    "episode_duration_s",
    "dt_s",
    "band_plan",
    "receiver_config_relpath",
    "noise_power_w",
    "metric_schema_version",
)


@dataclass(frozen=True)
class ExperimentProtocol:
    """One evaluation protocol. Historical IDs are stable; files are not rewritten."""

    protocol_id: str
    display_name: str
    purpose: str
    model_bundle_version: str
    model_bundle_relpath: str | None
    evidence_relpath: str | None
    scenario_manifest_relpath: str | None
    scenario_seeds: tuple[int, ...]
    episode_duration_s: float
    dt_s: float
    band_plan: str
    receiver_config_relpath: str
    noise_power_w: float
    strategy_ids: tuple[str, ...]
    missing_strategy_ids: tuple[str, ...]
    metric_schema_version: str
    created_at: str
    is_frozen: bool
    is_official_gate: bool
    selector_label: str
    metric_source: str

    def fingerprint_field(self, name: str, root: Path | None = None) -> str | None:
        base = root or project_root()
        if name == "model_bundle_fingerprint":
            rel = self.model_bundle_relpath
            if not rel:
                return None
            checksums = base / rel / "checksums.json"
            if not checksums.is_file():
                return None
            payload = json.loads(checksums.read_text(encoding="utf-8"))
            raw = payload.get("content_fingerprint")
            return str(raw) if raw else None
        if name == "scenario_manifest_fingerprint":
            rel = self.scenario_manifest_relpath
            if not rel:
                return None
            path = base / rel
            if not path.is_file():
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
            raw = payload.get("content_fingerprint")
            if raw:
                return str(raw)
            return sha256_file(path)
        if name == "receiver_config_fingerprint":
            path = base / self.receiver_config_relpath
            if not path.is_file():
                return None
            return sha256_file(path)
        if name == "benchmark_config_fingerprint":
            return None
        return None

    def as_banner(self) -> dict[str, str]:
        seeds = self.scenario_seeds
        if not seeds:
            seed_text = "session seed"
        elif seeds[0] == seeds[-1]:
            seed_text = str(seeds[0])
        else:
            seed_text = f"{seeds[0]}–{seeds[-1]}"
        bundle = f"SmartScanScheduler {self.model_bundle_version}"
        return {
            "protocol": self.protocol_id,
            "bundle": bundle,
            "seeds": seed_text,
            "episode": f"{self.episode_duration_s:g} s",
            "purpose": self.purpose,
            "source": self.metric_source,
        }


class _SharedProtocolFields(TypedDict):
    dt_s: float
    band_plan: str
    receiver_config_relpath: str
    noise_power_w: float
    strategy_ids: tuple[str, ...]
    missing_strategy_ids: tuple[str, ...]
    metric_schema_version: str


def _recorded_strategy_ids() -> tuple[str, ...]:
    if TOTAL_PUBLIC_STRATEGIES != 7:
        raise SmartScanError("PUBLIC_STRATEGIES must contain exactly seven ids.")
    return tuple(list(HELD_OUT_BASELINE_STRATEGIES) + ["ppo"])


def registered_protocols() -> dict[str, ExperimentProtocol]:
    recorded = _recorded_strategy_ids()
    missing = tuple(name for name in PUBLIC_STRATEGIES if name not in recorded)
    common: _SharedProtocolFields = {
        "dt_s": 0.001,
        "band_plan": "demo_2_18",
        "receiver_config_relpath": "configs/receiver.yaml",
        "noise_power_w": 1.0e-13,
        "strategy_ids": recorded,
        "missing_strategy_ids": missing,
        "metric_schema_version": METRIC_SCHEMA_VERSION,
    }
    v2 = ExperimentProtocol(
        protocol_id=PROTOCOL_V2_FROZEN_GATE,
        display_name="Frozen held-out — v2",
        purpose="official frozen performance gate (historical)",
        model_bundle_version="v2",
        model_bundle_relpath=GATE_EVIDENCE_BUNDLE_RELPATH,
        evidence_relpath="artifacts/models/held_out_gate.json",
        scenario_manifest_relpath="configs/held_out_manifest.json",
        scenario_seeds=tuple(range(1000, 1030)),
        episode_duration_s=0.4,
        created_at="2026-08-30",
        is_frozen=True,
        is_official_gate=True,
        selector_label="Frozen held-out — v2",
        metric_source=SOURCE_FROZEN_GATE,
        **common,
    )
    v3 = ExperimentProtocol(
        protocol_id=PROTOCOL_V3_RESEARCH,
        display_name="Research test — v3",
        purpose="research evaluation",
        model_bundle_version="v3",
        model_bundle_relpath=V3_BUNDLE_RELPATH,
        evidence_relpath="artifacts/ml_improve/fresh_test_gate.json",
        scenario_manifest_relpath="configs/fresh_test_manifest.json",
        scenario_seeds=tuple(range(8000, 8008)),
        episode_duration_s=0.2,
        created_at="2026-08-31",
        is_frozen=True,
        is_official_gate=False,
        selector_label="Research test — v3",
        metric_source=SOURCE_RECORDED_PROTOCOL,
        **common,
    )
    v4 = ExperimentProtocol(
        protocol_id=PROTOCOL_V4_RESEARCH,
        display_name="Research test — v4",
        purpose="research evaluation",
        model_bundle_version="v4",
        model_bundle_relpath=ACTIVE_MODEL_BUNDLE_RELPATH,
        evidence_relpath="artifacts/ml_improve/fresh_test_v4_gate.json",
        scenario_manifest_relpath="configs/fresh_test_v4_manifest.json",
        scenario_seeds=tuple(range(9000, 9008)),
        episode_duration_s=0.2,
        created_at="2026-08-31",
        is_frozen=True,
        is_official_gate=False,
        selector_label="Research test — v4",
        metric_source=SOURCE_RECORDED_PROTOCOL,
        **common,
    )
    live = ExperimentProtocol(
        protocol_id=PROTOCOL_LIVE_SESSION,
        display_name="Current session",
        purpose="operator live run or recorded demo replay",
        model_bundle_version="v4",
        model_bundle_relpath=ACTIVE_MODEL_BUNDLE_RELPATH,
        evidence_relpath=None,
        scenario_manifest_relpath=None,
        scenario_seeds=(),
        episode_duration_s=0.0,
        created_at="session",
        is_frozen=False,
        is_official_gate=False,
        selector_label="Current session",
        metric_source=SOURCE_LIVE_RUN,
        dt_s=0.001,
        band_plan="demo_2_18",
        receiver_config_relpath="configs/receiver.yaml",
        noise_power_w=1.0e-13,
        strategy_ids=tuple(PUBLIC_STRATEGIES),
        missing_strategy_ids=(),
        metric_schema_version=METRIC_SCHEMA_VERSION,
    )
    return {
        PROTOCOL_V2_FROZEN_GATE: v2,
        PROTOCOL_V3_RESEARCH: v3,
        PROTOCOL_V4_RESEARCH: v4,
        PROTOCOL_LIVE_SESSION: live,
    }


def get_protocol(protocol_id: str) -> ExperimentProtocol:
    catalog = registered_protocols()
    if protocol_id == PROTOCOL_LEGACY_UNKNOWN:
        raise SmartScanError(
            "protocol_id=legacy_unknown cannot be used for paired comparison."
        )
    proto = catalog.get(protocol_id)
    if proto is None:
        raise SmartScanError(f"Unknown experiment protocol {protocol_id!r}.")
    return proto


def official_gate_protocol() -> ExperimentProtocol:
    return get_protocol(PROTOCOL_V2_FROZEN_GATE)


def live_session_protocol() -> ExperimentProtocol:
    return get_protocol(PROTOCOL_LIVE_SESSION)


def selector_options() -> tuple[tuple[str, str], ...]:
    catalog = registered_protocols()
    order = (
        PROTOCOL_LIVE_SESSION,
        PROTOCOL_V2_FROZEN_GATE,
        PROTOCOL_V3_RESEARCH,
        PROTOCOL_V4_RESEARCH,
    )
    return tuple((catalog[key].selector_label, key) for key in order)


def protocols_comparable(left: ExperimentProtocol, right: ExperimentProtocol) -> tuple[bool, str]:
    if left.protocol_id == PROTOCOL_LIVE_SESSION and right.protocol_id == PROTOCOL_LIVE_SESSION:
        return True, ""
    for field in _COMPARABLE_FIELDS:
        if getattr(left, field) != getattr(right, field):
            return False, CROSS_PROTOCOL_MESSAGE
    return True, ""


def require_comparable_protocols(left: ExperimentProtocol, right: ExperimentProtocol) -> None:
    ok, message = protocols_comparable(left, right)
    if not ok:
        raise SmartScanError(message)


def require_same_protocol_id(left: str, right: str) -> None:
    if str(left) != str(right):
        raise SmartScanError(CROSS_PROTOCOL_MESSAGE)


def generation_from_bundle_path(model_dir: str | Path | None) -> str:
    text = str(model_dir or "").replace("\\", "/").lower()
    if "scheduler_v4" in text:
        return "v4"
    if "scheduler_v3" in text:
        return "v3"
    if "scheduler_full" in text:
        return "v2"
    if not text:
        return "v4"
    return "v2"


def generation_from_model_version(model_version: str | None, *, path: str | Path | None = None) -> str:
    tagged = generation_from_bundle_path(path)
    if path and ("scheduler_v4" in str(path).replace("\\", "/").lower() or "scheduler_v3" in str(path).replace("\\", "/").lower() or "scheduler_full" in str(path).replace("\\", "/").lower()):
        return tagged
    raw = str(model_version or "")
    if raw.startswith("4.") or "v4" in raw.lower():
        return "v4"
    if raw.startswith("3.") or "v3" in raw.lower():
        return "v3"
    if raw.startswith("2.") or "v2" in raw.lower():
        return "v2"
    if path:
        return tagged
    return "v2"


def infer_protocol_id(
    *,
    seed: int | None,
    duration_s: float | None,
    explicit: str | None = None,
    for_new_write: bool = False,
) -> str:
    """Infer a protocol id only when seed set and duration match a frozen protocol."""

    if explicit:
        return str(explicit)
    if seed is None or duration_s is None:
        return PROTOCOL_LIVE_SESSION if for_new_write else PROTOCOL_LEGACY_UNKNOWN
    duration = float(duration_s)
    seed_i = int(seed)
    for proto in registered_protocols().values():
        if proto.protocol_id == PROTOCOL_LIVE_SESSION:
            continue
        if seed_i not in proto.scenario_seeds:
            continue
        if abs(duration - float(proto.episode_duration_s)) > 1e-9:
            return PROTOCOL_LEGACY_UNKNOWN
        return proto.protocol_id
    return PROTOCOL_LIVE_SESSION


def load_protocol_air_means(protocol_id: str, *, root: Path | None = None) -> dict[str, Any]:
    proto = get_protocol(protocol_id)
    base = root or project_root()
    if proto.evidence_relpath is None:
        return {
            "available": False,
            "air": {},
            "oracle_air": None,
            "gate_passed": False,
            "n_rows": None,
            "path": None,
            "protocol": proto,
        }
    path = base / proto.evidence_relpath
    if not path.is_file():
        return {
            "available": False,
            "air": {},
            "oracle_air": None,
            "gate_passed": False,
            "n_rows": None,
            "path": str(path),
            "protocol": proto,
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    air = dict((payload.get("comparisons") or {}).get("air_means") or {})
    oracle = air.pop("oracle-ceiling", None)
    if oracle is None:
        oracle = air.pop("oracle", None)
    return {
        "available": True,
        "air": air,
        "oracle_air": None if oracle is None else float(oracle),
        "gate_passed": bool(payload.get("performance_gate_passed")),
        "n_rows": payload.get("n_rows"),
        "path": str(path),
        "protocol": proto,
        "reasons": list(payload.get("reasons") or []),
    }


def format_air_cell(protocol: ExperimentProtocol, strategy: str, raw: Any) -> str:
    if strategy in protocol.missing_strategy_ids:
        return NOT_RECORDED
    if raw is None:
        return "Not available"
    return f"{float(raw):.2f}"


def protocol_air_table(protocol_id: str, *, root: Path | None = None) -> dict[str, list[str]]:
    loaded = load_protocol_air_means(protocol_id, root=root)
    proto: ExperimentProtocol = loaded["protocol"]
    air = loaded["air"] if loaded["available"] else {}
    rows: dict[str, list[str]] = {
        "strategy": [],
        "air": [],
        "source": [],
        "protocol": [],
    }
    for name in PUBLIC_STRATEGIES:
        rows["strategy"].append(name)
        rows["protocol"].append(proto.protocol_id)
        rows["source"].append(proto.metric_source)
        if not loaded["available"] and name not in proto.missing_strategy_ids:
            rows["air"].append("Not available")
        else:
            rows["air"].append(format_air_cell(proto, name, air.get(name)))
    return rows


def inspect_bundle_dir(model_dir: str | Path) -> dict[str, Any]:
    dest = Path(model_dir)
    payload: dict[str, Any] = {
        "path": str(dest),
        "present": dest.is_dir(),
        "generation": generation_from_bundle_path(dest),
    }
    if not dest.is_dir():
        payload["ok"] = False
        payload["error"] = "bundle directory missing"
        return payload
    try:
        from smartscan.ml.bundle import verify_checksums

        checksums = verify_checksums(dest)
        manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
        payload.update(
            {
                "ok": True,
                "content_fingerprint": checksums.get("content_fingerprint"),
                "model_version": manifest.get("model_version"),
                "registered_name": manifest.get("registered_name") or "SmartScanScheduler",
                "has_ppo": bool(manifest.get("has_ppo")),
                "has_predictor": bool(manifest.get("has_predictor")),
                "normalizer_size": (manifest.get("feature_schema") or {}).get("size"),
            }
        )
    except (OSError, SmartScanError, json.JSONDecodeError, KeyError) as exc:
        payload.update({"ok": False, "error": str(exc)})
    return payload


def assert_bundle_generation(model_dir: str | Path, expected: str) -> dict[str, Any]:
    info = inspect_bundle_dir(model_dir)
    got = str(info.get("generation") or "")
    if got != expected:
        raise SmartScanError(
            f"Bundle at {model_dir} resolved as {got}, expected {expected}."
        )
    if not info.get("ok"):
        raise SmartScanError(str(info.get("error") or f"Cannot load bundle {model_dir}"))
    return info


def assert_distinct_bundle_fingerprints(infos: list[dict[str, Any]]) -> None:
    fps = [str(item.get("content_fingerprint") or "") for item in infos if item.get("ok")]
    if len(fps) != len(set(fps)):
        raise SmartScanError("Two scheduler bundles share a content fingerprint.")


def known_bundle_fingerprint_map(root: Path | None = None) -> dict[str, str]:
    """generation -> content fingerprint for bundles present on disk."""

    base = root or project_root()
    mapping: dict[str, str] = {}
    for rel, generation in (
        (GATE_EVIDENCE_BUNDLE_RELPATH, "v2"),
        (V3_BUNDLE_RELPATH, "v3"),
        (ACTIVE_MODEL_BUNDLE_RELPATH, "v4"),
    ):
        info = inspect_bundle_dir(base / rel)
        fp = info.get("content_fingerprint")
        if info.get("ok") and fp:
            mapping[generation] = str(fp)
    return mapping


def check_run_bundle_linkage(
    *,
    model_version: str | None,
    bundle_fingerprint: str | None,
    fingerprints: dict[str, str] | None = None,
) -> str | None:
    """Return an error if a run's model version disagrees with its bundle fingerprint."""

    if not bundle_fingerprint:
        return None
    mapping = fingerprints if fingerprints is not None else known_bundle_fingerprint_map()
    inverse = {fp: gen for gen, fp in mapping.items()}
    found = inverse.get(str(bundle_fingerprint))
    if found is None:
        return None
    declared = str(model_version or "").lower()
    if not declared:
        return None
    if declared in {"v2", "v3", "v4"} and declared != found:
        return (
            f"run references model bundle {declared} but artifact fingerprint equals {found}"
        )
    return None


def artifact_integrity_report(root: Path | None = None) -> dict[str, Any]:
    """Checksum known bundles and evidence files. Never deletes orphans."""

    base = root or project_root()
    missing: list[str] = []
    stale: list[str] = []
    duplicate: list[str] = []
    orphans: list[str] = []
    ok_bundles: list[dict[str, Any]] = []
    expected_files = [
        "artifacts/models/held_out_gate.json",
        "artifacts/ml_improve/fresh_test_gate.json",
        "artifacts/ml_improve/fresh_test_v4_gate.json",
        "configs/held_out_manifest.json",
        "configs/fresh_test_manifest.json",
        "configs/fresh_test_v4_manifest.json",
        "configs/receiver.yaml",
    ]
    for rel in expected_files:
        if not (base / rel).is_file():
            missing.append(rel)
    for rel, generation in (
        (GATE_EVIDENCE_BUNDLE_RELPATH, "v2"),
        (V3_BUNDLE_RELPATH, "v3"),
        (ACTIVE_MODEL_BUNDLE_RELPATH, "v4"),
    ):
        info = inspect_bundle_dir(base / rel)
        if not info.get("present"):
            missing.append(rel)
            continue
        if not info.get("ok"):
            stale.append(f"{rel}: {info.get('error')}")
            continue
        ok_bundles.append({"generation": generation, **info})
    try:
        assert_distinct_bundle_fingerprints(ok_bundles)
    except SmartScanError as exc:
        duplicate.append(str(exc))
    known = {
        "scheduler_full",
        "scheduler_v3",
        "scheduler_v4",
        "datasets",
        "predictor_full",
        "cts_full",
    }
    models_root = base / "artifacts" / "models"
    if models_root.is_dir():
        for child in models_root.iterdir():
            name = child.name
            if name in known or name.startswith("held_out") or name.endswith(".json"):
                continue
            orphans.append(str(child.relative_to(base)).replace("\\", "/"))
    demo_dir = base / "artifacts" / "demo"
    demo_ok = demo_dir.is_dir()
    if not demo_ok:
        missing.append("artifacts/demo")
    blocking = bool(missing or stale or duplicate)
    return {
        "ok": not blocking,
        "missing": missing,
        "stale": stale,
        "duplicate": duplicate,
        "orphans": orphans,
        "bundles": ok_bundles,
        "demo_present": demo_ok,
    }


__all__ = [
    "ACTIVE_MODEL_BUNDLE_RELPATH",
    "CROSS_PROTOCOL_MESSAGE",
    "ExperimentProtocol",
    "GATE_EVIDENCE_BUNDLE_RELPATH",
    "NOT_RECORDED",
    "ORACLE_EVALUATOR_LABEL",
    "PROTOCOL_LEGACY_UNKNOWN",
    "PROTOCOL_LIVE_SESSION",
    "PROTOCOL_V2_FROZEN_GATE",
    "PROTOCOL_V3_RESEARCH",
    "PROTOCOL_V4_RESEARCH",
    "SOURCE_FROZEN_GATE",
    "SOURCE_LIVE_RUN",
    "SOURCE_RECORDED_PROTOCOL",
    "TOTAL_PUBLIC_STRATEGIES",
    "artifact_integrity_report",
    "assert_bundle_generation",
    "assert_distinct_bundle_fingerprints",
    "check_run_bundle_linkage",
    "format_air_cell",
    "known_bundle_fingerprint_map",
    "generation_from_bundle_path",
    "generation_from_model_version",
    "get_protocol",
    "infer_protocol_id",
    "inspect_bundle_dir",
    "live_session_protocol",
    "load_protocol_air_means",
    "official_gate_protocol",
    "protocol_air_table",
    "protocols_comparable",
    "registered_protocols",
    "require_comparable_protocols",
    "require_same_protocol_id",
    "selector_options",
]
