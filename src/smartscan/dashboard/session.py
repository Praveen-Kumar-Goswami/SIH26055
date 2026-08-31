"""Dashboard session-state contract. One primary UI phase at a time."""

from __future__ import annotations

from typing import Any

PHASE_EMPTY = "EMPTY"
PHASE_DEMO_LOADED = "DEMO_LOADED"
PHASE_VALIDATING = "VALIDATING"
PHASE_RUNNING = "RUNNING"
PHASE_COMPLETE = "COMPLETE"
PHASE_ERROR = "ERROR"

RUN_STATUS = {
    PHASE_EMPTY: "Idle",
    PHASE_DEMO_LOADED: "Demo loaded",
    PHASE_VALIDATING: "Validating",
    PHASE_RUNNING: "Running",
    PHASE_COMPLETE: "RUN COMPLETE",
    PHASE_ERROR: "Error",
}

SESSION_KEYS: tuple[tuple[str, str, str, str], ...] = (
    ("results", "list[ExperimentResult]", "configure/demo/run", "replace on demo load; merge on run"),
    ("active", "ExperimentResult|None", "configure/replay", "set to chosen replay strategy"),
    ("seq", "ExperimentResult|None", "configure demo (legacy)", "cleared on new demo; unused by replay"),
    ("overlay", "bool", "sidebar toggle", "persists across views; evaluator-only"),
    ("last_scenario", "str", "configure", "reset on demo/run"),
    ("last_strategy", "str", "configure/replay", "follows active replay strategy"),
    ("last_seed", "int|None", "configure", "reset on demo/run"),
    ("run_status", "str", "configure", "mirrors ui_phase; one primary status"),
    ("ui_phase", "str", "configure", "EMPTY|DEMO_LOADED|VALIDATING|RUNNING|COMPLETE|ERROR"),
    ("replay_strategy_seen", "str|None", "replay", "reset replay_step when strategy changes"),
    ("last_error", "str|None", "configure", "set on ERROR"),
)

WIDGET_KEYS: tuple[tuple[str, str, str], ...] = (
    ("cfg_scenario", "str", "configure"),
    ("cfg_seed", "int", "configure"),
    ("cfg_band_plan", "str", "configure"),
    ("cfg_dt", "float", "configure"),
    ("cfg_duration", "float", "configure"),
    ("cfg_strategy", "str", "configure"),
    ("cfg_persist", "bool", "configure"),
    ("replay_strategy", "str", "replay; reset when results change"),
    ("replay_step", "int", "replay; zeroed when replay_strategy_seen changes"),
    ("replay_playing", "bool", "replay"),
    ("replay_speed", "float", "replay"),
    ("replay_pause", "bool", "replay"),
    ("dec_index", "int", "decision; zeroed when replay strategy changes"),
    ("metrics_evidence_set", "str", "compare; selects one protocol, never mixes"),
    ("hist_strategy", "str", "history"),
    ("hist_status", "str", "history"),
    ("hist_scenario", "str", "history"),
    ("hist_protocol", "str", "history"),
    ("hist_select", "str", "history"),
    ("view_select", "str", "chrome"),
    ("overlay_toggle", "bool", "chrome"),
)

SESSION_DEFAULTS: dict[str, Any] = {
    "results": [],
    "active": None,
    "seq": None,
    "overlay": False,
    "last_scenario": "—",
    "last_strategy": "—",
    "last_seed": None,
    "run_status": RUN_STATUS[PHASE_EMPTY],
    "ui_phase": PHASE_EMPTY,
    "replay_strategy_seen": None,
    "last_error": None,
}


def default_session() -> dict[str, Any]:
    return dict(SESSION_DEFAULTS)


def set_phase(state: dict[str, Any], phase: str, *, error: str | None = None) -> None:
    state["ui_phase"] = phase
    state["run_status"] = RUN_STATUS.get(phase, phase)
    state["last_error"] = error
