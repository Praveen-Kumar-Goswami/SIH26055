"""Streamlit entrypoint. Thin chrome around dashboard services and pages."""

from __future__ import annotations

from typing import Any, cast

from smartscan.dashboard.layout import LAYOUT_MAX_HEIGHT_PX, LAYOUT_MAX_WIDTH_PX, NAV_LABELS
from smartscan.dashboard.pages import VIEWS, render_gate_banner, render_view
from smartscan.dashboard.services import (
    OVERLAY_NOTICE,
    doctor_report,
    load_dashboard_config,
    load_performance_gate,
)
from smartscan.dashboard.session import SESSION_DEFAULTS, default_session
from smartscan.dashboard.ui.chrome import inject_pointer_runtime, render_command_bar, render_tour
from smartscan.dashboard.ui.landing import render_landing
from smartscan.dashboard.ui.styles import global_css


def _session_state(st: Any) -> dict[str, Any]:
    if "smartscan" not in st.session_state:
        st.session_state.smartscan = default_session()
    state = cast(dict[str, Any], st.session_state.smartscan)
    for key, value in SESSION_DEFAULTS.items():
        state.setdefault(key, value)
    return state


def _render_hidden_streamlit_nav(st: Any, state: dict[str, Any], dash: Any) -> str:
    """Keep widget keys alive. Visual navigation is the injected hamburger drawer."""

    if st.button("Introduction", key="show_landing"):
        st.session_state["entered_control_center"] = False
        st.rerun()
    view = st.radio(
        "View",
        list(VIEWS),
        key="view_select",
        format_func=lambda name: NAV_LABELS.get(name, name),
    )
    overlay = st.toggle(
        "Evaluation overlay",
        value=bool(state.get("overlay")),
        key="overlay_toggle",
        help=OVERLAY_NOTICE,
    )
    state["overlay"] = bool(overlay)
    if overlay:
        st.caption(OVERLAY_NOTICE)
    render_tour(st)
    st.caption(f"Host {dash.host} · viewport ≤ {LAYOUT_MAX_WIDTH_PX}×{LAYOUT_MAX_HEIGHT_PX}")
    if st.button("Doctor", key="sidebar_doctor"):
        st.session_state["doctor_payload"] = doctor_report(dash)
    payload = st.session_state.get("doctor_payload")
    if payload:
        st.json(payload)
    return str(view)


def main() -> None:
    import streamlit as st

    dash = load_dashboard_config()
    st.set_page_config(
        page_title="SmartScan — EW Spectrum Intelligence",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            "Get help": None,
            "Report a bug": None,
            "About": "SIH26055 Smart Scan — offline dashboard",
        },
    )
    st.markdown(global_css(), unsafe_allow_html=True)
    inject_pointer_runtime(st)
    state = _session_state(st)
    gate = load_performance_gate()
    with st.sidebar:
        view = _render_hidden_streamlit_nav(st, state, dash)
    if not st.session_state.get("entered_control_center"):
        render_landing(st, gate)
        return
    st.markdown('<div class="ss-control-root"></div>', unsafe_allow_html=True)
    render_command_bar(st, state, gate)
    render_gate_banner(st)
    render_view(st, str(view), state)


if __name__ == "__main__":
    main()
