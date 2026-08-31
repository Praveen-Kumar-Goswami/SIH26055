"""Plotly figures from typed dashboard payloads. No metric formulas here."""

from __future__ import annotations

from typing import Any

from smartscan.dashboard.layout import (
    CONTENT_MAX_WIDTH_PX,
    PALETTE,
    PLOT_HEIGHT_PX,
    STRATEGY_COLORS,
)
from smartscan.dashboard.services import ReplayFrame

OKABE = [PALETTE["sky"], PALETTE["orange"], PALETTE["green"], PALETTE["blue"], PALETTE["purple"]]


def _empty_figure(title: str, note: str) -> Any:
    import plotly.graph_objects as go

    fig = go.Figure()
    fig.update_layout(
        title=title,
        annotations=[{"text": note, "x": 0.5, "y": 0.5, "showarrow": False, "font": {"color": PALETTE["muted"]}}],
        template="plotly_dark",
        height=PLOT_HEIGHT_PX,
        width=min(1100, CONTENT_MAX_WIDTH_PX),
        margin={"l": 48, "r": 16, "t": 48, "b": 40},
        paper_bgcolor=PALETTE["bg"],
        plot_bgcolor=PALETTE["panel"],
        font={"color": PALETTE["text"], "size": 13},
        autosize=True,
    )
    return fig


def replay_figure(
    frame: ReplayFrame,
    *,
    speed: float = 1.0,
    cursor_s: float | None = None,
    animate: bool = False,
) -> Any:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    if not frame.times_s:
        return _empty_figure("Scan replay", "No observation steps in this run.")
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.65, 0.35],
        vertical_spacing=0.08,
        subplot_titles=("Receiver band vs time", "Measured SNR (dB)"),
    )
    t = frame.times_s
    tuned = [(-1 if b is None else int(b)) for b in frame.tuned_band]
    fig.add_trace(
        go.Scatter(
            x=t,
            y=tuned,
            mode="lines",
            name="tuned band",
            line={"color": PALETTE["sky"], "width": 2},
            hovertemplate="t=%{x:.4f}s band=%{y}<extra></extra>",
        ),
        row=1,
        col=1,
    )
    tuning_t = [tt for tt, state in zip(t, frame.receiver_state, strict=False) if state == "TUNING"]
    tuning_y = [yy for yy, state in zip(tuned, frame.receiver_state, strict=False) if state == "TUNING"]
    if tuning_t:
        fig.add_trace(
            go.Scatter(
                x=tuning_t,
                y=tuning_y,
                mode="markers",
                name="tuning gap",
                marker={"color": PALETTE["orange"], "size": 6, "symbol": "x"},
            ),
            row=1,
            col=1,
        )
    if frame.occupied is not None:
        # Sparse occupancy markers — evaluation overlay only.
        occ_t: list[float] = []
        occ_b: list[int] = []
        step = max(1, len(frame.occupied) // 400)
        dt = frame.dt_s
        for i in range(0, len(frame.occupied), step):
            for band, flag in enumerate(frame.occupied[i]):
                if flag:
                    occ_t.append(float(i) * dt)
                    occ_b.append(band)
        fig.add_trace(
            go.Scatter(
                x=occ_t,
                y=occ_b,
                mode="markers",
                name="truth occupancy (not available to policy)",
                marker={"color": PALETTE["muted"], "size": 4, "opacity": 0.35},
            ),
            row=1,
            col=1,
        )
    if frame.hit_times_s:
        fig.add_trace(
            go.Scatter(
                x=frame.hit_times_s,
                y=frame.hit_bands,
                mode="markers",
                name="hit",
                marker={"color": PALETTE["green"], "size": 10, "symbol": "circle"},
            ),
            row=1,
            col=1,
        )
    if frame.miss_times_s:
        fig.add_trace(
            go.Scatter(
                x=frame.miss_times_s,
                y=frame.miss_bands,
                mode="markers",
                name="miss",
                marker={"color": PALETTE["vermillion"], "size": 9, "symbol": "triangle-down"},
            ),
            row=1,
            col=1,
        )
    snr = [float(v) if v is not None else None for v in frame.snr_db]
    fig.add_trace(
        go.Scatter(
            x=t,
            y=snr,
            mode="lines",
            name="SNR dB",
            line={"color": PALETTE["yellow"]},
            connectgaps=False,
        ),
        row=2,
        col=1,
    )
    if cursor_s is not None:
        fig.add_vline(x=float(cursor_s), line_dash="dot", line_color=PALETTE["text"])
        nearest = min(range(len(t)), key=lambda i: abs(t[i] - float(cursor_s)))
        fig.add_trace(
            go.Scatter(
                x=[t[nearest]],
                y=[tuned[nearest]],
                mode="markers",
                name="scan position",
                marker={
                    "color": PALETTE["accent"],
                    "size": 12,
                    "line": {"width": 1, "color": PALETTE["text"]},
                },
            ),
            row=1,
            col=1,
        )
    fig.update_yaxes(title_text="band", row=1, col=1, rangemode="tozero")
    fig.update_yaxes(title_text="dB", row=2, col=1)
    fig.update_xaxes(title_text="time (s)", row=2, col=1)
    title = "Scan replay"
    if frame.overlay_notice:
        title = f"Scan replay — {frame.overlay_notice}"
    menus: list[dict[str, Any]] = []
    if animate and len(t) >= 3:
        stride = max(1, len(t) // 32)
        scan_trace = len(fig.data) - 1 if cursor_s is not None else None
        if scan_trace is not None:
            fig.frames = [
                go.Frame(
                    name=str(i),
                    data=[go.Scatter(x=[t[i]], y=[tuned[i]])],
                    traces=[scan_trace],
                )
                for i in range(0, len(t), stride)
            ]
            duration_ms = max(40, int(140.0 / max(0.25, float(speed))))
            menus.append(
                {
                    "type": "buttons",
                    "direction": "left",
                    "x": 0.0,
                    "y": 1.22,
                    "xanchor": "left",
                    "showactive": False,
                    "buttons": [
                        {
                            "label": "Play",
                            "method": "animate",
                            "args": [
                                None,
                                {
                                    "frame": {"duration": duration_ms, "redraw": False},
                                    "fromcurrent": True,
                                    "mode": "immediate",
                                },
                            ],
                        },
                        {
                            "label": "Pause",
                            "method": "animate",
                            "args": [[None], {"mode": "immediate", "frame": {"duration": 0}}],
                        },
                    ],
                }
            )
    fig.update_layout(
        title=title,
        template="plotly_dark",
        height=PLOT_HEIGHT_PX + 80,
        width=min(1100, CONTENT_MAX_WIDTH_PX),
        margin={"l": 52, "r": 16, "t": 64 if menus else 56, "b": 48},
        paper_bgcolor=PALETTE["bg"],
        plot_bgcolor=PALETTE["panel"],
        font={"color": PALETTE["text"], "size": 13},
        legend={"orientation": "h", "y": 1.12},
        autosize=True,
        uirevision="replay",
        updatemenus=menus,
    )
    return fig


def metrics_bar_figure(table: dict[str, Any], metric_key: str) -> Any:
    import plotly.graph_objects as go

    row = next((item for item in table.get("rows", []) if item["key"] == metric_key), None)
    if row is None:
        return _empty_figure(metric_key, "Not available")
    names: list[str] = []
    values: list[float] = []
    colors: list[str] = []
    custom: list[str] = []
    skipped: list[str] = []
    for strategy, cell in row["cells"].items():
        if not cell["available"] or cell["value"] is None:
            skipped.append(f"{strategy}: {cell['display']}")
            continue
        names.append(strategy)
        values.append(float(cell["value"]))
        colors.append(STRATEGY_COLORS.get(strategy, PALETTE["sky"]))
        den = cell.get("denominator")
        num = cell.get("numerator")
        custom.append(f"{num}/{den}" if num is not None and den is not None else cell["display"])
    if not names:
        note = "; ".join(skipped) if skipped else "Not available"
        return _empty_figure(str(row.get("name", metric_key)), note)
    fig = go.Figure(
        go.Bar(
            x=names,
            y=values,
            marker_color=colors,
            customdata=custom,
            hovertemplate="%{x}<br>value=%{y}<br>%{customdata}<extra></extra>",
        )
    )
    direction = row.get("direction", "")
    omitted = f" · omitted unavailable: {'; '.join(skipped)}" if skipped else ""
    fig.update_layout(
        title=f"{row['name']} ({direction}){omitted}",
        template="plotly_dark",
        height=PLOT_HEIGHT_PX,
        width=min(1100, CONTENT_MAX_WIDTH_PX),
        yaxis_rangemode="tozero",
        paper_bgcolor=PALETTE["bg"],
        plot_bgcolor=PALETTE["panel"],
        font={"color": PALETTE["text"], "size": 13},
        autosize=True,
        showlegend=False,
    )
    return fig


def paired_delta_figure(table: dict[str, Any]) -> Any:
    import plotly.graph_objects as go

    paired = table.get("paired_vs_sequential") or {}
    if not paired:
        return _empty_figure("Paired deltas vs sequential", "Need PPO and sequential on the same seed.")
    names: list[str] = []
    means: list[float] = []
    lows: list[float] = []
    highs: list[float] = []
    for key, payload in paired.items():
        if not isinstance(payload, dict) or payload.get("mean_delta") is None:
            continue
        names.append(key)
        mean = float(payload["mean_delta"])
        lo = float(payload["ci_low"]) if payload.get("ci_low") is not None else mean
        hi = float(payload["ci_high"]) if payload.get("ci_high") is not None else mean
        means.append(mean)
        lows.append(mean - lo)
        highs.append(hi - mean)
    if not names:
        return _empty_figure("Paired deltas vs sequential", "Not available")
    fig = go.Figure(
        go.Scatter(
            x=means,
            y=names,
            mode="markers",
            error_x={"type": "data", "array": highs, "arrayminus": lows},
            marker={"color": PALETTE["blue"], "size": 10},
            name="PPO − sequential",
        )
    )
    fig.add_vline(x=0.0, line_dash="dot", line_color=PALETTE["muted"])
    n_seeds = table.get("n_seeds", 1)
    fig.update_layout(
        title=f"Paired 95% CI vs sequential (n_seeds={n_seeds})",
        template="plotly_dark",
        height=PLOT_HEIGHT_PX,
        width=min(1100, CONTENT_MAX_WIDTH_PX),
        xaxis_title="delta (PPO − sequential)",
        paper_bgcolor=PALETTE["bg"],
        plot_bgcolor=PALETTE["panel"],
        font={"color": PALETTE["text"], "size": 13},
        autosize=True,
        showlegend=False,
    )
    return fig


def plot_payload_complete(table: dict[str, Any]) -> bool:
    """True when every required compare key and CI/strategy field is present."""

    keys = {row["key"] for row in table.get("rows", [])}
    required = {
        "pd",
        "pfa",
        "sensitivity",
        "average_intercept_rate",
        "average_reward",
        "correct_predictions",
        "average_intercept_time_error",
        "event_interception_ratio",
        "successful_event_delay_median_s",
    }
    if not required.issubset(keys):
        return False
    if "strategies" not in table or "n_seeds" not in table:
        return False
    for row in table.get("rows", []):
        if "direction" not in row or "cells" not in row:
            return False
        for cell in row["cells"].values():
            if "unit" not in cell or "numerator" not in cell or "denominator" not in cell:
                return False
            if "available" not in cell or "display" not in cell:
                return False
    return True
