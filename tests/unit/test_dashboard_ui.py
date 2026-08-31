from __future__ import annotations

import contextlib
from typing import Any

from smartscan.dashboard.layout import NAV_LABELS
from smartscan.dashboard.pages import VIEWS, _periodicity_caption, _strategy_option_label
from smartscan.dashboard.services import DEMO_STRATEGIES
from smartscan.dashboard.ui.chrome import (
    TOUR_STEPS,
    command_bar_model_label,
    inject_pointer_runtime,
    pointer_runtime_html,
    render_command_bar,
    render_gate_status_html,
    render_tour,
)
from smartscan.dashboard.ui.components import (
    display_metric,
    frozen_air_cards,
    human_error,
    lineage_flow_html,
    rank_bars,
)
from smartscan.dashboard.ui.help import HELP_TEXT, help_for, help_payload
from smartscan.dashboard.ui.landing import (
    HERO_COPY,
    hero_animation_html,
    hero_parent_javascript,
    landing_body_html,
    render_landing,
)
from smartscan.dashboard.ui.statement import STATEMENT_ASKS, statement_matrix_html
from smartscan.dashboard.ui.styles import contains_remote_asset, global_css


class _FakeStreamlit:
    session_state: dict[str, Any] = {}

    def markdown(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    def caption(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    def button(self, *args: Any, **kwargs: Any) -> bool:
        del args, kwargs
        return False

    def expander(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        return contextlib.nullcontext()

    def iframe(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    def rerun(self) -> None:
        return None


def test_session_keys_are_unique() -> None:
    from smartscan.dashboard.session import SESSION_KEYS, WIDGET_KEYS, default_session, set_phase

    names = [row[0] for row in SESSION_KEYS]
    assert len(names) == len(set(names))
    widgets = [row[0] for row in WIDGET_KEYS]
    assert len(widgets) == len(set(widgets))
    state = default_session()
    set_phase(state, "COMPLETE")
    assert state["ui_phase"] == "COMPLETE"
    assert state["run_status"] == "RUN COMPLETE"
    set_phase(state, "DEMO_LOADED")
    assert state["run_status"] == "Demo loaded"
    assert state["run_status"] != "RUN COMPLETE"


def test_help_text_covers_required_terms() -> None:
    required = (
        "p_active",
        "p_hit",
        "dwell",
        "air",
        "candidate",
        "pfa",
        "periodicity",
        "agility",
        "overlay",
        "gate",
        "periodic-intercept",
        "strategy",
        "sequential",
        "random",
        "fixed-priority",
        "reactive",
        "contextual-thompson",
        "ppo",
    )
    for key in required:
        assert key in HELP_TEXT
        assert len(HELP_TEXT[key]) > 20
    assert "seven public" in HELP_TEXT["strategy"].lower()
    assert help_for("Average Intercept Rate")
    assert "Champion" in (help_for("candidate") or "")
    payload = help_payload()
    assert payload["delay_ms"] >= 3000
    assert "p_hit" in payload["terms"]
    for name in DEMO_STRATEGIES:
        assert name in payload["terms"]


def test_ui_assets_are_offline() -> None:
    blobs = [
        global_css(),
        hero_animation_html(),
        landing_body_html({"alias": "candidate", "performance_gate_passed": False}),
        pointer_runtime_html(),
        lineage_flow_html(),
        frozen_air_cards({"ppo": 5.0, "sequential": 9.25, "random": 7.0, "fixed-priority": 14.0}),
        statement_matrix_html(),
    ]
    for blob in blobs:
        assert not contains_remote_asset(blob)
        lowered = blob.lower()
        assert "fonts.googleapis" not in lowered
        assert "cdn.jsdelivr" not in lowered
        assert "unpkg.com" not in lowered
    assert contains_remote_asset("https://fonts.googleapis.com/css")
    assert len(STATEMENT_ASKS) == 10
    matrix = statement_matrix_html()
    for row in STATEMENT_ASKS:
        assert row["ask"] in matrix
        assert row["where"] in matrix


def test_frozen_air_cards_show_held_out_means() -> None:
    html = frozen_air_cards(
        {
            "ppo": 5.0,
            "sequential": 9.25,
            "random": 7.0,
            "fixed-priority": 14.0,
            "reactive": 7.08,
            "contextual-thompson": 7.75,
        }
    )
    assert "5.00" in html
    assert "9.25" in html
    assert "7.00" in html
    assert "14.00" in html
    assert "7.08" in html
    assert "7.75" in html
    assert "Reactive" in html
    assert "Contextual Thompson" in html
    assert "Periodic Intercept" in html
    assert "PPO v2" in html
    assert "v2_frozen_gate" in html
    assert html.count("Not recorded") == 1
    missing = frozen_air_cards({})
    assert missing.count("Not recorded") == 1
    assert missing.count("Not available") == 6


def test_human_error_and_metric_display() -> None:
    head, detail = human_error(RuntimeError("PPO bundle not found at /tmp/x"))
    assert head == "Model bundle could not be loaded."
    assert "bundle" in detail.lower()
    head, _ = human_error("duration exceeds the demo cap")
    assert head == "Configuration validation failed."
    head, _ = human_error("invalid domain_run uuid")
    assert head == "Stored run could not be found."
    assert help_for("no-such-term-xyz") is None
    assert display_metric(None) == "Not available"
    assert display_metric(1.2345, digits=2) == "1.23"


def test_nav_keys_preserved_and_tour_is_short() -> None:
    assert VIEWS == (
        "Configure & Run",
        "Scan Replay",
        "Smart Decision",
        "Metrics Compare",
        "Run History",
        "Model & Data Lineage",
    )
    for key in VIEWS:
        assert key in NAV_LABELS
    assert "periodic-intercept" in DEMO_STRATEGIES
    assert DEMO_STRATEGIES[-1] == "ppo"
    assert len(DEMO_STRATEGIES) == 7
    assert list(DEMO_STRATEGIES) == [
        "sequential",
        "random",
        "fixed-priority",
        "reactive",
        "contextual-thompson",
        "periodic-intercept",
        "ppo",
    ]
    assert len(TOUR_STEPS) == 7
    html = render_gate_status_html({"alias": "candidate", "performance_gate_passed": False})
    assert "Candidate" in html
    assert "v2 held-out not passed" in html
    assert "SmartScanScheduler v4" in html
    shell = pointer_runtime_html()
    assert "v4 candidate" in shell
    assert "v2_frozen_gate not passed" in shell
    bars = rank_bars([("07", 0.82), ("04", 0.68)], caption="BAND")
    assert "0.82" in bars
    assert HERO_COPY.startswith("A receiver")
    empty = rank_bars([], caption="BAND")
    assert "Not available" in empty
    shell = pointer_runtime_html()
    assert "ss-burger" in shell
    assert "ss-drawer" in shell
    assert "ss-hero-canvas" in shell or "ss-hero" in shell
    css = global_css()
    assert "#ss-burger" in css
    assert "ss-hero-band" in css
    assert "min(100%" in css
    assert "aspect-ratio" in css
    assert "container-type" in css
    assert "prefers-reduced-motion" in css
    assert "ss-core-host" in landing_body_html(
        {"alias": "candidate", "performance_gate_passed": False}
    )
    assert "ss-enter-cta" in landing_body_html(
        {"alias": "candidate", "performance_gate_passed": False}
    )
    core = hero_parent_javascript()
    assert "SPECTRAL INTERCEPT CORE" in core
    assert "__ssCore" in core
    assert "prefers-reduced-motion" in core
    assert "canvas3d" in core
    assert "svg-fallback" in core
    assert "ss-core-host" in core
    assert "ss-field-canvas" in core
    assert "is-ambient" in pointer_runtime_html()
    assert "data-ss-help" in landing_body_html(
        {"alias": "candidate", "performance_gate_passed": False}
    )
    landing = landing_body_html({"alias": "candidate", "performance_gate_passed": False})
    assert "ss-statement-matrix" in landing
    assert "Electronic Support" in landing
    assert "periodic-intercept" in landing
    assert "Probability of detection" in landing
    assert "ss-ask-row" in landing
    assert "ss-periodic" in landing
    assert "Configure &amp; Run" in landing
    assert "Seven public strategies" in landing
    assert "contextual-thompson" in landing
    assert "SmartScanScheduler v4" in landing
    assert "seven public" in TOUR_STEPS[1].lower()
    assert "periodic-intercept" in TOUR_STEPS[1]
    full = "artifacts/models/scheduler_full"
    assert command_bar_model_label("sequential", "candidate", model_dir=full) == "v2 candidate"
    assert command_bar_model_label("contextual-thompson", "candidate", model_dir=full) == "v2 candidate"
    assert command_bar_model_label("periodic-intercept", "candidate", model_dir=full) == "v2 candidate"
    assert command_bar_model_label("ppo", "candidate", model_dir=full) == "v2 candidate"
    assert command_bar_model_label("—", "candidate", model_dir=full) == "v2 candidate"
    assert (
        command_bar_model_label("ppo", "candidate", model_dir="artifacts/models/scheduler_v4")
        == "v4 candidate"
    )
    from smartscan.dashboard.ui.chrome import command_bar_gate_label, command_bar_run_lede

    assert command_bar_gate_label(False) == "Not Passed"
    assert command_bar_gate_label(True) == "Passed"
    v4 = "artifacts/models/scheduler_v4"
    lede = command_bar_run_lede("RUN COMPLETE", "sequential", model_dir=v4)
    assert "sequential" in lede
    assert "rule / baseline" in lede
    assert "v2_frozen_gate" in lede
    assert "v4" in lede
    assert "unused this run" in lede
    ppo_lede = command_bar_run_lede("RUN COMPLETE", "ppo", model_dir=v4)
    assert "live policy is ppo" in ppo_lede.lower()
    assert "v4" in ppo_lede
    assert "rule / baseline" in _strategy_option_label("sequential")
    assert "stares" in _periodicity_caption("periodic-intercept")
    assert "does not stare" in _periodicity_caption("sequential")
    assert "search-then-stare" in _periodicity_caption("ppo")
    css = global_css()
    assert "is-ambient" in css
    assert "ss-field-canvas" in css
    assert "ss-ask-table" in css
    from smartscan.dashboard.ui.components import command_bar_html

    bar = command_bar_html(
        scenario="agile_threat",
        strategy="sequential",
        seed="42",
        run_status="RUN COMPLETE",
        active_version="v4",
        active_alias="candidate",
        research_status="Candidate",
        gate_protocol="v2_frozen_gate",
        gate_status="Not Passed",
        lede="test",
    )
    assert "Current run" in bar
    assert "Active PPO model" in bar
    assert "Official frozen gate" in bar
    assert "v2_frozen_gate" in bar
    assert "Not Passed" in bar
    assert "v4" in bar


def test_render_wrappers_do_not_require_a_server() -> None:
    st = _FakeStreamlit()
    st.session_state = {}
    render_landing(st, {"alias": "candidate", "performance_gate_passed": False})
    render_command_bar(
        st,
        {
            "last_scenario": "agile_threat",
            "last_strategy": "sequential",
            "last_seed": 42,
            "run_status": "RUN COMPLETE",
        },
        {"alias": "candidate", "performance_gate_passed": False},
    )
    render_tour(st)
    inject_pointer_runtime(st)
