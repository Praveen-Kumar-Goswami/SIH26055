"""Streamlit view renderers. Call services; do not recompute metrics."""

from __future__ import annotations

from typing import Any

from smartscan.dashboard.layout import LAYOUT_MAX_WIDTH_PX
from smartscan.dashboard.plots import metrics_bar_figure, paired_delta_figure, replay_figure
from smartscan.dashboard.services import (
    DEMO_STRATEGIES,
    OVERLAY_NOTICE,
    _receiver,
    comparison_table,
    doctor_report,
    explain_decision,
    export_comparison,
    lineage_panel,
    list_history,
    load_dashboard_config,
    load_demo_bundle,
    load_performance_gate,
    run_experiment,
    validate_run_request,
    verify_history_run,
)
from smartscan.dashboard.session import (
    PHASE_COMPLETE,
    PHASE_DEMO_LOADED,
    PHASE_ERROR,
    PHASE_RUNNING,
    PHASE_VALIDATING,
    set_phase,
)
from smartscan.dashboard.ui.components import (
    display_metric,
    frozen_air_cards,
    human_error,
    lineage_flow_html,
    rank_bars,
)
from smartscan.dashboard.ui.help import HELP_TEXT
from smartscan.dashboard.ui.statement import statement_matrix_html
from smartscan.experiment_protocol import (
    CROSS_PROTOCOL_MESSAGE,
    NOT_RECORDED,
    ORACLE_EVALUATOR_LABEL,
    PROTOCOL_LEGACY_UNKNOWN,
    PROTOCOL_LIVE_SESSION,
    PROTOCOL_V2_FROZEN_GATE,
    get_protocol,
    selector_options,
)
from smartscan.ml.strategy_registry import PUBLIC_STRATEGIES, strategy_kind_label
from smartscan.types import SmartScanError

VIEWS = (
    "Configure & Run",
    "Scan Replay",
    "Smart Decision",
    "Metrics Compare",
    "Run History",
    "Model & Data Lineage",
)

_HISTORY_ALL = "(all)"


def _strategy_option_label(name: str) -> str:
    try:
        return f"{name} · {strategy_kind_label(name)}"
    except SmartScanError:
        return str(name)


def _periodicity_caption(strategy_id: str) -> str:
    sid = str(strategy_id or "")
    if sid == "periodic-intercept":
        return (
            "Phase-to-next is the estimated wait until the next illumination on this band "
            "(observable hits only). This strategy stares when that wait fits the dwell."
        )
    if sid in {"ppo", "contextual-thompson"}:
        return (
            "Phase-to-next is estimated from observable hit times. This strategy may use "
            "period/phase features; it does not run the search-then-stare rule."
        )
    return (
        "Phase-to-next is estimated from observable hit times for inspection. "
        "This rule baseline does not stare from the periodicity estimate."
    )


def _strategy_source_caption(result: Any) -> str:
    try:
        label = strategy_kind_label(str(result.strategy))
    except SmartScanError:
        label = "Not available"
    if result.strategy == "ppo":
        return f"{label} · model source {result.model_alias or 'candidate'}"
    return label


def _status(st: Any, message: str, *, kind: str = "info") -> None:
    if kind == "error":
        _report_error(st, RuntimeError(message))
    elif kind == "warning":
        st.warning(message)
    else:
        st.info(message)


def _report_error(st: Any, exc: BaseException) -> None:
    headline, detail = human_error(exc)
    st.error(headline)
    with st.expander("Technical details", expanded=False):
        st.caption(detail)


def render_gate_banner(st: Any) -> None:
    gate = load_performance_gate()
    if gate.get("performance_gate_passed"):
        st.success("Held-out performance_gate_passed=true. Scheduler may be highlighted as champion.")
        return
    st.warning(
        "Live PPO: **v4 candidate**. Frozen v2 held-out gate: "
        "**performance_gate_passed=false** — no Champion."
    )
    reasons = gate.get("reasons") or []
    if reasons:
        with st.expander("Failed criteria (held-out gate)", expanded=False):
            for reason in reasons:
                st.caption(f"- {reason}")


def render_configure(st: Any, state: dict[str, Any]) -> None:
    dash = load_dashboard_config()
    st.subheader("Configure & Run")
    st.caption(f"Layout cap {LAYOUT_MAX_WIDTH_PX}px · live duration ≤ {dash.max_duration_s}s")
    st.markdown("**SCENARIO**")
    cols = st.columns(3)
    scenario = cols[0].selectbox(
        "Scenario / source",
        ["agile_threat", "sparse", "dense", "edge_zero"],
        index=0,
        key="cfg_scenario",
        help=HELP_TEXT["scenario"],
    )
    seed = int(
        cols[1].number_input(
            "Seed", min_value=0, value=int(dash.demo_seed), key="cfg_seed", help=HELP_TEXT["seed"]
        )
    )
    band_plan = cols[2].selectbox(
        "Band plan",
        ["demo_2_18", "turing_0_18"],
        index=0,
        key="cfg_band_plan",
        help="RF configuration: which frequency tiling the receiver and emitters share.",
    )
    st.markdown("**RECEIVER**")
    row2 = st.columns(3)
    dt = float(
        row2[0].number_input(
            "dt (s)",
            min_value=0.0001,
            max_value=0.01,
            value=float(dash.demo_dt_s),
            key="cfg_dt",
            format="%.4f",
            help="Simulation time step. Does not change frozen benchmark results.",
        )
    )
    duration = float(
        row2[1].number_input(
            "Duration (s)",
            min_value=0.02,
            max_value=float(dash.max_duration_s),
            value=float(dash.demo_duration_s),
            key="cfg_duration",
        )
    )
    row2[2].caption("Dwell bins and IBW come from the receiver configuration below.")
    receiver = _receiver(dash)
    st.caption(
        f"Receiver IBW {receiver.receiver_ibw_hz:g} Hz · scan span {receiver.scan_span_hz:g} Hz · "
        f"tune {receiver.tune_latency_steps} step(s) · dwell bins {list(receiver.dwell_bins)} · "
        f"noise_power_w {dash.noise_power_w:g}"
    )
    st.markdown("**STRATEGY**")
    strategy = st.selectbox(
        "Strategy / model",
        list(DEMO_STRATEGIES),
        key="cfg_strategy",
        help=HELP_TEXT["strategy"],
    )
    st.caption(
        "Seven public strategies: "
        + "; ".join(f"{name} ({strategy_kind_label(name)})" for name in DEMO_STRATEGIES)
        + ". PPO executes SmartScanScheduler v4. Frozen gate remains v2 held-out."
    )
    st.markdown("**EXECUTION**")
    persist = st.checkbox("Persist and track this run", value=False, key="cfg_persist")
    n_bands_guess = 18 if str(band_plan).startswith("turing") else 16
    problems = validate_run_request(
        dash, duration_s=duration, n_bands=n_bands_guess, strategy=str(strategy)
    )
    if problems:
        for item in problems:
            st.error("Configuration validation failed.")
            with st.expander("Technical details", expanded=False):
                st.caption(item + " Next action: lower duration or load recorded demo replay.")
    st.caption(f"Primary UI state: {state.get('ui_phase') or 'EMPTY'}")
    demo_col, run_col = st.columns(2)
    if demo_col.button("Load agile_threat demo", key="load_demo"):
        demo_ok = False
        with st.status("LOADING MODEL", expanded=True) as status:
            try:
                status.update(label="LOADING MODEL")
                state["results"] = load_demo_bundle(dash)
                loaded = list(state["results"] or [])
                state["active"] = next(
                    (item for item in loaded if item.strategy == "ppo"),
                    loaded[0] if loaded else None,
                )
                state["seq"] = next(
                    (item for item in loaded if item.strategy == "sequential"),
                    None,
                )
                state["last_scenario"] = dash.demo_scenario_id
                active = state.get("active")
                state["last_strategy"] = str(getattr(active, "strategy", None) or "—")
                state["last_seed"] = dash.demo_seed
                set_phase(state, PHASE_DEMO_LOADED)
                st.session_state.pop("replay_strategy", None)
                demo_ok = True
                status.update(label="Demo loaded", state="complete")
            except SmartScanError as exc:
                status.update(label="Demo failed", state="error")
                set_phase(state, PHASE_ERROR, error=str(exc))
                _report_error(st, exc)
                st.caption("Next action: run scripts/make_demo_data.py.")
        if demo_ok:
            loaded_ids = [item.strategy for item in state.get("results") or []]
            missing = [name for name in DEMO_STRATEGIES if name not in loaded_ids]
            if missing:
                st.warning(
                    "Recorded demo does not include: "
                    + ", ".join(missing)
                    + ". Validate & Run to generate those strategies in this session."
                )
            if "ppo" in loaded_ids:
                st.caption(
                    "Recorded demo PPO is a live_session recording of SmartScanScheduler v4 "
                    "(candidate), not the official v2 frozen held-out gate. "
                    "Validate & Run ppo to generate a new live_session of the same active bundle."
                )
    if run_col.button("VALIDATE & RUN", key="run_experiment", type="primary"):
        if problems:
            st.error("Configuration validation failed.")
            with st.expander("Technical details", expanded=False):
                st.caption(problems[0])
        else:
            run_ok = False
            result = None
            with st.status("GENERATING RF ENVIRONMENT", expanded=False) as status:
                try:
                    set_phase(state, PHASE_VALIDATING)
                    set_phase(state, PHASE_RUNNING)
                    status.update(label="GENERATING RF ENVIRONMENT")
                    overlay = bool(state.get("overlay"))
                    status.update(label="RUNNING STRATEGY")
                    result = run_experiment(
                        dash,
                        scenario_id=str(scenario),
                        seed=seed,
                        strategy=str(strategy),
                        duration_s=duration,
                        dt_s=dt,
                        band_plan_id=str(band_plan),
                        persist=bool(persist),
                        evaluation_overlay=overlay,
                    )
                    status.update(label="COMPUTING METRICS")
                    if persist:
                        status.update(label="PERSISTING RUN")
                    state["active"] = result
                    existing = [
                        item for item in state.get("results") or [] if item.strategy != result.strategy
                    ]
                    existing.append(result)
                    state["results"] = existing
                    state["last_scenario"] = str(scenario)
                    state["last_strategy"] = str(result.strategy)
                    state["last_seed"] = seed
                    set_phase(state, PHASE_COMPLETE)
                    st.session_state.pop("replay_strategy", None)
                    run_ok = True
                    status.update(label="RUN COMPLETE", state="complete")
                except SmartScanError as exc:
                    status.update(label="Run failed", state="error")
                    set_phase(state, PHASE_ERROR, error=str(exc))
                    _report_error(st, exc)
                    st.caption("Next action: check doctor panel.")
            if run_ok and result is not None:
                st.success("RUN COMPLETE")
                st.caption(
                    f"Strategy {result.strategy} · seed {result.seed} · "
                    f"{_strategy_source_caption(result)}"
                )
                if result.domain_run_id:
                    st.caption(f"Run ID {result.domain_run_id}")
                with st.expander("Technical Details", expanded=False):
                    st.caption(f"truth_fingerprint={result.truth.content_fingerprint}")
                    st.caption(f"domain_run_id={result.domain_run_id}")
    if state.get("results"):
        kinds = []
        for item in state["results"]:
            try:
                kinds.append(f"{item.strategy} ({strategy_kind_label(item.strategy)})")
            except SmartScanError:
                kinds.append(str(item.strategy))
        st.caption("Loaded strategies: " + ", ".join(kinds))


def render_replay(st: Any, state: dict[str, Any]) -> None:
    st.subheader("Scan Replay")
    st.caption("Recorded logs only — replay never issues new scan decisions.")
    results = state.get("results") or []
    if not results:
        _status(st, "Load the demo or run an experiment first.", kind="warning")
        return
    names = [item.strategy for item in results]
    if st.session_state.get("replay_strategy") not in names:
        st.session_state.pop("replay_strategy", None)
    choice = st.selectbox(
        "Replay strategy",
        names,
        key="replay_strategy",
    )
    if state.get("replay_strategy_seen") != str(choice):
        st.session_state["replay_step"] = 0
        st.session_state["replay_playing"] = False
        st.session_state["dec_index"] = 0
        state["replay_strategy_seen"] = str(choice)
    st.caption(_strategy_option_label(str(choice)))
    target = next(item for item in results if item.strategy == choice)
    state["active"] = target
    state["last_strategy"] = str(target.strategy)
    overlay = bool(state.get("overlay"))
    if overlay:
        st.caption(OVERLAY_NOTICE)
    from smartscan.dashboard.services import build_replay_frame

    n_steps = max(1, target.truth.n_steps)
    controls = st.columns(4)
    if controls[0].button("Play", key="replay_play"):
        st.session_state["replay_playing"] = True
        st.session_state["replay_pause"] = False
    if controls[1].button("Pause", key="replay_pause_btn"):
        st.session_state["replay_playing"] = False
        st.session_state["replay_pause"] = True
    if controls[2].button("Step", key="replay_step_fwd"):
        st.session_state["replay_playing"] = False
        current = int(st.session_state.get("replay_step", 0))
        st.session_state["replay_step"] = min(n_steps - 1, current + 1)
    speed = float(st.slider("Replay speed", 0.25, 4.0, 1.0, key="replay_speed"))
    cursor = int(st.slider("Step", 0, n_steps - 1, 0, key="replay_step"))
    pause = st.checkbox("Pause", value=True, key="replay_pause")
    st.caption("Play clears Pause so the chart animation controls appear. Scrub time with the step slider.")
    frame = build_replay_frame(target, evaluation_overlay=overlay)
    cursor_s = float(cursor) * float(target.truth.dt_s)
    st.plotly_chart(
        replay_figure(frame, speed=speed, cursor_s=cursor_s, animate=not pause),
        width="stretch",
        key="replay_chart",
    )
    st.caption(f"pause={pause} cursor={cursor_s:.4f}s seed={target.seed}/{target.receiver_seed}")


def render_decision(st: Any, state: dict[str, Any]) -> None:
    st.subheader("Smart Decision")
    active = state.get("active")
    if active is None:
        _status(st, "Run or load a learned/baseline episode first.", kind="warning")
        return
    n = len(active.run.decisions.rows)
    if n == 0:
        _status(st, "No completed commands in this run.", kind="warning")
        return
    idx = int(st.number_input("Decision index", min_value=0, max_value=n - 1, value=0, key="dec_index"))
    expl = explain_decision(active, idx)
    st.markdown(f"**{expl.decision_id}** band `{expl.target_band}` dwell `{expl.dwell_steps}` hit `{expl.hit}`")
    st.caption(
        f"{expl.strategy_id or active.strategy} · {expl.strategy_kind_label or 'Not available'}"
    )
    from smartscan.dashboard.identity import active_model_status

    live = active_model_status()
    st.caption(
        f"Current run strategy: {expl.strategy_id or active.strategy}. "
        f"Active PPO bundle: SmartScanScheduler {live.get('generation')} "
        f"({live.get('alias')}). These are separate."
    )
    if str(expl.strategy_id or active.strategy) != "ppo":
        st.caption(
            "This replay is not PPO. Predicted fields below are from the recorded "
            "decision log for this strategy, not from the active PPO bundle."
        )
    st.caption(f"Metric source: {getattr(active, 'metric_source', None) or 'LIVE RUN'}")
    st.caption(expl.strategy_rule or "Not available")
    st.caption(f"Forecast recorded at step {expl.recorded_at_step} (not recomputed with future history).")
    left, right = st.columns(2)
    with left:
        st.markdown("**OBSERVED**")
        st.caption("Fields recorded from the completed dwell — not hidden GroundTruth.")
        o1, o2, o3 = st.columns(3)
        o1.metric("SELECTED BAND", str(expl.target_band))
        o2.metric("DWELL", str(expl.dwell_steps), help=HELP_TEXT["dwell"])
        o3.metric("hit", "yes" if expl.hit else "no")
        st.caption(
            f"periodicity={display_metric(expl.period_s)} · "
            f"confidence={display_metric(expl.periodicity_confidence)} · "
            f"phase-to-next={display_metric(expl.phase_to_next, digits=4)} · "
            f"agility={display_metric(expl.agility_score)} · "
            f"novelty={display_metric(expl.novelty)}"
        )
        st.caption(f"uncertainty={display_metric(expl.uncertainty)}")
        st.caption(_periodicity_caption(str(expl.strategy_id or active.strategy)))
    with right:
        st.markdown("**PREDICTED**")
        st.caption("Pre-action forecasts stored with the decision. Never regenerated from future hits.")
        p1, p2 = st.columns(2)
        p1.metric("p_hit", display_metric(expl.p_hit), help=HELP_TEXT["p_hit"])
        if expl.p_active is None:
            p2.metric("p_active", "Not available", help=HELP_TEXT["p_active"])
            p2.caption(expl.p_active_unavailable or "Why? p_active was not stored on this decision.")
        else:
            p2.metric("p_active", f"{expl.p_active:.3f}", help=HELP_TEXT["p_active"])
        tnext = expl.time_to_next_completed_intercept_s
        st.metric("predicted next-intercept (s)", display_metric(tnext, digits=4))
        if expl.horizon_ratio is not None:
            lo = expl.horizon_ci_low
            hi = expl.horizon_ci_high
            st.caption(
                f"Predicted interception-ratio {expl.horizon_ratio:.3f} "
                f"interval [{lo if lo is not None else 'Not available'}, "
                f"{hi if hi is not None else 'Not available'}]"
            )
        else:
            st.caption(
                "Horizon interception-ratio: Not available. "
                "Why? Forecast metric unavailable because this run does not contain a pre-action forecast."
            )
    agility_rows = [
        (f"{band:02d}", score)
        for band, score in sorted(
            enumerate(expl.observable_agility_by_band),
            key=lambda item: -item[1],
        )[:12]
    ]
    st.markdown(
        rank_bars(
            agility_rows,
            caption="Observable agility by band (policy-visible — not evaluator-only truth)",
        ),
        unsafe_allow_html=True,
    )
    st.markdown("**EVALUATOR-ONLY TRUTH**")
    st.caption(
        "Hit outcome and reward components are scored after the dwell. "
        "They are not available to the policy as oracle occupancy."
    )
    if state.get("overlay"):
        st.caption(OVERLAY_NOTICE)
    st.caption("Threat is assessed/public priority × novelty — not a hidden hostile label.")
    with st.expander("Reward components", expanded=False):
        st.write(
            {
                "novelty": expl.novelty,
                "assessed_threat": expl.assessed_threat,
                "uncertainty": expl.uncertainty,
                "priority": expl.priority,
                "reward": expl.reward,
                "reward_hit": expl.reward_hit,
                "reward_priority": expl.reward_priority,
                "cost_tune_s": expl.cost_tune_s,
                "cost_time_s": expl.cost_time_s,
                "cost_repeat": expl.cost_repeat,
                "cost_false_like": expl.cost_false_like,
            }
        )


def _protocol_banner(st: Any, protocol_id: str) -> None:
    proto = get_protocol(protocol_id)
    banner = proto.as_banner()
    st.markdown("**Protocol banner**")
    st.caption(
        f"Protocol: {banner['protocol']} · Bundle: {banner['bundle']} · "
        f"Seeds: {banner['seeds']} · Episode: {banner['episode']} · "
        f"Purpose: {banner['purpose']} · Source: {banner['source']}"
    )


def _recorded_protocol_panel(st: Any, protocol_id: str) -> None:
    from smartscan.experiment_protocol import load_protocol_air_means, protocol_air_table

    proto = get_protocol(protocol_id)
    loaded = load_protocol_air_means(protocol_id)
    _protocol_banner(st, protocol_id)
    st.caption(CROSS_PROTOCOL_MESSAGE)
    st.caption(
        f"periodic-intercept is {NOT_RECORDED} for this protocol "
        "(absent from the recorded pair set). Do not display 0."
    )
    air = loaded["air"] if loaded["available"] else {}
    st.markdown(frozen_air_cards(air, protocol_id=protocol_id), unsafe_allow_html=True)
    table = protocol_air_table(protocol_id)
    st.dataframe(table, hide_index=True, width="stretch", key=f"protocol_air_{protocol_id}")
    oracle = loaded.get("oracle_air")
    if oracle is not None:
        st.caption(
            f"{ORACLE_EVALUATOR_LABEL}: oracle-ceiling AIR {float(oracle):.2f}. "
            "Not a deployable strategy and not ranked with public policies."
        )
    passed = loaded.get("gate_passed")
    st.warning(
        f"{proto.display_name} gate_passed={passed}. Champion is unset."
    )
    if protocol_id == PROTOCOL_V2_FROZEN_GATE:
        delay = (load_performance_gate().get("comparisons") or {}).get(
            "delay_reduction_vs_sequential"
        )
        if delay is not None:
            st.caption(
                "Successful-event delay vs sequential on this frozen protocol only "
                f"(delay_reduction_vs_sequential={float(delay):.3f})."
            )


def render_compare(st: Any, state: dict[str, Any]) -> None:
    st.subheader("Metrics Compare")
    labels = [item[0] for item in selector_options()]
    ids = {item[0]: item[1] for item in selector_options()}
    choice = st.selectbox(
        "Evidence set / protocol",
        labels,
        index=1,
        key="metrics_evidence_set",
        help="Switch the entire comparison dataset. Protocols are never mixed.",
    )
    protocol_id = ids[str(choice)]
    st.caption(
        "Recorded protocols v2_frozen_gate, v3_research, and v4_research are separate "
        "evidence sets. Do not rank across them."
    )
    if protocol_id == PROTOCOL_LIVE_SESSION:
        results = state.get("results") or []
        _protocol_banner(st, PROTOCOL_LIVE_SESSION)
        if not results:
            _status(
                st,
                "Load the demo or Validate & Run to compare strategies in this session.",
                kind="warning",
            )
            return
        st.markdown("**This session (LIVE RUN)**")
        table = comparison_table(results)
        if table.get("cross_protocol"):
            st.error(table.get("cross_protocol_message") or CROSS_PROTOCOL_MESSAGE)
        header = ["metric", "direction"] + table["strategies"]
        body = []
        unavailable_notes: list[str] = []
        for row in table["rows"]:
            line = [row["name"], row["direction"]]
            for name in table["strategies"]:
                cell = row["cells"][name]
                if cell.get("available"):
                    line.append(cell["display"])
                else:
                    line.append("Not available")
                    reason = cell.get("unavailable_reason") or cell.get("display")
                    unavailable_notes.append(f"{row['name']} / {name}: {reason}")
            body.append(line)
        st.dataframe(
            {header[i]: [line[i] for line in body] for i in range(len(header))},
            hide_index=True,
            width="stretch",
            key="compare_table",
        )
        if unavailable_notes:
            with st.expander("Not available — reasons", expanded=False):
                for note in unavailable_notes:
                    st.caption(note)
                st.caption("Why? Missing data is never shown as 0 or a win.")
        st.caption(
            "Numerators/denominators are in cell details and export JSON. "
            "Missing data is never shown as 0 or a win. Source: LIVE RUN."
        )
        st.plotly_chart(
            metrics_bar_figure(table, "average_intercept_rate"),
            width="stretch",
            key="air_bar",
        )
        st.plotly_chart(paired_delta_figure(table), width="stretch", key="paired_delta")
        if table.get("oracle_separate"):
            st.caption(f"{ORACLE_EVALUATOR_LABEL} (excluded from win comparison):")
            st.json(table["oracle_separate"])
        from smartscan.config import project_root

        if st.button("Export comparison JSON/CSV", key="export_compare"):
            dest = project_root() / "artifacts" / "demo" / "comparison_export.json"
            csv_path = project_root() / "artifacts" / "demo" / "comparison_export.csv"
            written = export_comparison(results, json_path=dest, csv_path=csv_path)
            st.caption(str(written))
        return
    _recorded_protocol_panel(st, protocol_id)


def render_history(st: Any, state: dict[str, Any]) -> None:
    del state
    st.subheader("Run History")
    f1, f2, f3, f4 = st.columns(4)
    strategy_choice = f1.selectbox(
        "Filter strategy",
        [_HISTORY_ALL, *PUBLIC_STRATEGIES],
        key="hist_strategy",
    )
    status = f2.text_input("Filter status", value="", key="hist_status")
    scenario = f3.text_input("Filter scenario", value="", key="hist_scenario")
    protocol_choice = f4.selectbox(
        "Filter protocol",
        [
            _HISTORY_ALL,
            PROTOCOL_LIVE_SESSION,
            PROTOCOL_LEGACY_UNKNOWN,
            PROTOCOL_V2_FROZEN_GATE,
            "v3_research",
            "v4_research",
        ],
        key="hist_protocol",
    )
    rows = list_history(
        strategy=None if strategy_choice == _HISTORY_ALL else str(strategy_choice),
        status=status or None,
        scenario=scenario or None,
        protocol_id=None if protocol_choice == _HISTORY_ALL else str(protocol_choice),
    )
    if rows and rows[0].get("error"):
        _report_error(st, RuntimeError(str(rows[0]["error"])))
        st.caption(str(rows[0].get("next_action", "")))
        return
    st.caption(f"{len(rows)} runs")
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch", key="history_table")
        ids = [str(item.get("domain_run_id") or "") for item in rows if item.get("domain_run_id")]
        selected = st.selectbox("Selected run", ["—"] + ids, key="hist_select")
        if selected and selected != "—":
            match = next((item for item in rows if str(item.get("domain_run_id")) == selected), None)
            if match:
                st.markdown("**Selected run**")
                st.caption(
                    f"strategy={match.get('strategy')} · scenario={match.get('scenario_name')} · "
                    f"status={match.get('status')} · protocol_id={match.get('protocol_id')}"
                )
                st.write(
                    {
                        "seeds": match.get("seeds"),
                        "metrics": match.get("metrics"),
                        "mlflow_run_id": match.get("mlflow_run_id"),
                        "domain_run_id": match.get("domain_run_id"),
                    }
                )
                with st.expander("Technical Details", expanded=False):
                    st.json(match)
    run_id = st.text_input("Verify domain_run_id", value="", key="hist_verify_id")
    if st.button("Verify artifacts", key="hist_verify") and run_id.strip():
        try:
            report = verify_history_run(run_id.strip())
            st.json(report)
        except (SmartScanError, ValueError) as exc:
            _report_error(st, exc)
            st.caption("Next action: paste a UUID from the table.")


def render_lineage(st: Any, state: dict[str, Any]) -> None:
    del state
    st.subheader("Model & Data Lineage")
    st.markdown(lineage_flow_html(), unsafe_allow_html=True)
    st.markdown("**SIH26055 statement coverage**")
    st.caption("Official DRDO asks mapped to this prototype. Engineering complete is not a Champion claim.")
    st.markdown(statement_matrix_html(), unsafe_allow_html=True)
    panel = lineage_panel()
    gate = panel.get("gate") or {}
    bundle = panel.get("bundle") or {}
    active = panel.get("active_model_bundle") or bundle
    frozen = panel.get("gate_evidence_bundle") or {}
    st.caption(
        f"Active PPO {active.get('generation')} fingerprint: "
        f"{active.get('content_fingerprint') or 'Not available'} · "
        f"Official gate {frozen.get('protocol_id') or 'v2_frozen_gate'} "
        f"{frozen.get('gate_status')} · Champion unset"
    )
    st.caption(
        f"manifest fingerprint: {gate.get('manifest_fingerprint') or 'Not available'} · "
        f"candidate alias: {panel.get('alias')}"
    )
    st.caption(
        "Dashboard executes the active_model_bundle (v4). "
        "Official frozen gate evidence remains v2_frozen_gate (seeds 1000–1029). Champion is unset."
    )
    catalog = panel.get("strategy_catalog") or []
    if catalog:
        st.caption(
            "Public strategies: "
            + "; ".join(f"{row['id']} ({row['kind_label']})" for row in catalog)
            + ". Only PPO is a learned RL model; rule baselines are not registered as neural MLflow models."
        )
    with st.expander("Technical Details", expanded=False):
        st.write(
            {
                "git_sha": panel.get("git_sha") or "not a git repository",
                "alias": panel.get("alias"),
                "bundle": panel.get("bundle"),
                "mlflow_db": panel.get("mlflow_db"),
                "mlflow_db_exists": panel.get("mlflow_db_exists"),
                "domain_db": panel.get("domain_db"),
            }
        )
    ui = panel.get("mlflow_ui") or {}
    if ui.get("reachable"):
        st.markdown(f"Open local MLflow UI: {panel.get('mlflow_open_url')}")
    else:
        st.caption(ui.get("detail", "MLflow UI unavailable"))
    if st.button("Doctor", key="doctor"):
        report = doctor_report()
        st.json(report)


def render_view(st: Any, view: str, state: dict[str, Any]) -> None:
    if view == "Configure & Run":
        render_configure(st, state)
    elif view == "Scan Replay":
        render_replay(st, state)
    elif view == "Smart Decision":
        render_decision(st, state)
    elif view == "Metrics Compare":
        render_compare(st, state)
    elif view == "Run History":
        render_history(st, state)
    else:
        render_lineage(st, state)
