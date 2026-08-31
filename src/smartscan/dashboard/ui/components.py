"""Reusable presentation fragments. No scientific formulas."""

from __future__ import annotations

from typing import Any

from smartscan.dashboard.ui.help import HELP_TEXT
from smartscan.ml.strategy_registry import PUBLIC_STRATEGIES, STRATEGY_REGISTRY


def status_chip(label: str, value: str, *, warn: bool = False) -> str:
    kind = " is-warn" if warn else ""
    return (
        f'<div class="ss-status{kind}"><span>{_esc(label)}</span>'
        f"<strong>{_esc(value)}</strong></div>"
    )


def command_bar_html(
    *,
    scenario: str,
    strategy: str,
    seed: str,
    run_status: str,
    active_version: str,
    active_alias: str,
    research_status: str,
    gate_protocol: str,
    gate_status: str,
    lede: str,
) -> str:
    warn_alias = "candidate" in active_alias.lower()
    warn_gate = "not" in gate_status.lower() or "fail" in gate_status.lower()
    return f"""
<div class="ss-cmd">
  <div class="ss-cmd-brand">
    <div class="brand">SMARTSCAN</div>
    <div class="sub">Electronic Warfare Spectrum Intelligence Prototype</div>
  </div>
  <div class="ss-cmd-group">
    <p class="ss-cmd-kicker">Current run</p>
    <div class="ss-chip-row">
      {status_chip("Scenario", scenario)}
      {status_chip("Strategy", strategy)}
      {status_chip("Seed", seed)}
      {status_chip("Run status", run_status)}
    </div>
  </div>
  <div class="ss-cmd-group">
    <p class="ss-cmd-kicker">Active PPO model</p>
    <div class="ss-chip-row">
      {status_chip("Version", active_version, warn=warn_alias)}
      {status_chip("Alias", active_alias, warn=warn_alias)}
      {status_chip("Research status", research_status, warn=warn_alias)}
    </div>
  </div>
  <div class="ss-cmd-group">
    <p class="ss-cmd-kicker">Official frozen gate</p>
    <div class="ss-chip-row">
      {status_chip("Protocol", gate_protocol, warn=warn_gate)}
      {status_chip("Gate", gate_status, warn=warn_gate)}
    </div>
  </div>
</div>
<p class="ss-lede">{_esc(lede)}</p>
"""


def rank_bars(rows: list[tuple[str, float]], *, caption: str) -> str:
    if not rows:
        return f'<div class="ss-card">{_esc(caption)}: Not available</div>'
    peak = max((abs(value) for _, value in rows), default=1.0) or 1.0
    parts = [f'<div class="ss-card"><p class="ss-kicker">{_esc(caption)}</p>']
    for name, value in rows:
        width = max(2, int(round(100.0 * abs(value) / peak)))
        parts.append(
            f'<div style="display:grid;grid-template-columns:4.5rem 1fr 3.2rem;'
            f'gap:0.4rem;align-items:center;margin:0.28rem 0">'
            f"<span>{_esc(name)}</span>"
            f'<div class="ss-bar"><i style="width:{width}%"></i></div>'
            f"<span>{value:.2f}</span></div>"
        )
    parts.append("</div>")
    return "".join(parts)


def frozen_air_cards(air_means: dict[str, Any], *, protocol_id: str = "v2_frozen_gate") -> str:
    """One chip per public strategy. Missing protocol members stay Not recorded."""

    from smartscan.experiment_protocol import format_air_cell, get_protocol

    proto = get_protocol(protocol_id)
    chips = []
    for key in PUBLIC_STRATEGIES:
        label = str(STRATEGY_REGISTRY[key]["display_name"])
        if key == "ppo":
            label = f"PPO {proto.model_bundle_version} ({proto.protocol_id})"
        text = format_air_cell(proto, key, air_means.get(key))
        chips.append(
            status_chip(
                f"{label} AIR",
                text,
                warn=key == "ppo" or text in {"Not recorded", "Not available"},
            )
        )
    return '<div class="ss-chip-row">' + "".join(chips) + "</div>"


def lineage_flow_html() -> str:
    nodes = (
        "Scenario",
        "GroundTruth",
        "Receiver observations",
        "Feature pipeline",
        "Predictor / Scheduler",
        "Decision Log",
        "Metrics",
        "SQLite",
        "MLflow",
        "Dashboard",
    )
    parts = ['<div class="ss-lineage">']
    for i, name in enumerate(nodes):
        parts.append(f"<span>{_esc(name)}</span>")
        if i < len(nodes) - 1:
            parts.append("<span>↓</span>")
    parts.append("</div>")
    return "".join(parts)


def display_metric(value: float | None, *, digits: int = 3) -> str:
    if value is None:
        return "Not available"
    return f"{value:.{digits}f}"


def human_error(exc: BaseException | str) -> tuple[str, str]:
    """Return (headline, technical detail). Never hide the original text."""

    detail = str(exc)
    lowered = detail.lower()
    if "bundle" in lowered and ("not found" in lowered or "load" in lowered or "checksum" in lowered):
        return "Model bundle could not be loaded.", detail
    if "domain_run" in lowered or "uuid" in lowered or "stored run" in lowered:
        return "Stored run could not be found.", detail
    if "exceeds" in lowered or "unknown strategy" in lowered or "validation" in lowered:
        return "Configuration validation failed.", detail
    if "demo" in lowered and "not" in lowered:
        return "Recorded demo bundle could not be loaded.", detail
    return "The requested operation could not be completed.", detail


def render_gate_status_html(gate: dict[str, Any]) -> str:
    alias = str(gate.get("alias") or "candidate")
    passed = bool(gate.get("performance_gate_passed"))
    chips = [
        status_chip("SYSTEM", "Engineering Complete"),
        status_chip("MODEL", "SmartScanScheduler v4"),
        status_chip("TYPE", "PPO Reinforcement Learning"),
        status_chip("STATUS", alias.title(), warn=not passed),
        status_chip("PERFORMANCE GATE", "v2 held-out not passed" if not passed else "Passed", warn=not passed),
    ]
    return '<div class="ss-chip-row">' + "".join(chips) + "</div>"


def help_attr(key: str) -> str:
    return HELP_TEXT.get(key, "")


def _esc(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
