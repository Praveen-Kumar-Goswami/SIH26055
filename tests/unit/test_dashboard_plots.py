from __future__ import annotations

from smartscan.dashboard.layout import CONTENT_MAX_WIDTH_PX, LAYOUT_MAX_WIDTH_PX
from smartscan.dashboard.plots import (
    metrics_bar_figure,
    paired_delta_figure,
    plot_payload_complete,
    replay_figure,
)
from smartscan.dashboard.services import ReplayFrame, comparison_table


def _frame(*, overlay: bool) -> ReplayFrame:
    occupied = [[1, 0, 0, 0]] if overlay else None
    return ReplayFrame(
        times_s=[0.0, 0.001, 0.002],
        tuned_band=[0, None, 0],
        commanded_band=[0, 0, 0],
        receiver_state=["DWELLING", "TUNING", "DWELLING"],
        snr_db=[1.0, None, 2.0],
        detections=[False, False, True],
        hit_times_s=[0.002],
        hit_bands=[0],
        miss_times_s=[0.001],
        miss_bands=[1],
        occupied=occupied,
        overlay_notice="Evaluation overlay — not available to policy" if overlay else None,
        dt_s=0.001,
        n_bands=4,
    )


def test_replay_figure_passes_units_and_overlay_metadata() -> None:
    fig = replay_figure(_frame(overlay=True), cursor_s=0.001)
    assert fig.layout.width <= LAYOUT_MAX_WIDTH_PX
    assert fig.layout.width <= CONTENT_MAX_WIDTH_PX or fig.layout.autosize
    names = [trace.name for trace in fig.data]
    assert "hit" in names
    assert "miss" in names
    assert any("not available to policy" in str(name) for name in names)
    off = replay_figure(_frame(overlay=False))
    assert not any("occupancy" in str(trace.name) for trace in off.data)


def test_plot_payload_requires_all_metrics_strategies_and_ci() -> None:
    from smartscan.types import MetricsReport, MetricValue

    def report(value: float) -> MetricsReport:
        metrics = {
            key: MetricValue(name=key, value=value, available=True, numerator=1, denominator=2)
            for key in (
                "pd",
                "pfa",
                "sensitivity",
                "average_intercept_rate",
                "average_reward",
                "correct_predictions",
                "average_intercept_time_error",
                "event_interception_ratio",
                "successful_event_delay_median_s",
                "all_event_penalized_delay_s",
                "missed_event_count",
                "wasted_dwell_fraction",
                "tuning_fraction",
            )
        }
        return MetricsReport(metrics=metrics)

    class _E:
        def __init__(self, name: str) -> None:
            self.strategy = name
            self.evaluation = type("R", (), {"report": report(1.0)})()

    table = comparison_table([_E("sequential"), _E("random")])  # type: ignore[list-item]
    assert plot_payload_complete(table)
    assert table["n_seeds"] == 1
    assert "sequential" in table["strategies"]
    fig = paired_delta_figure(table)
    assert fig.layout.title.text
    bar = metrics_bar_figure(table, "average_intercept_rate")
    assert bar.data
    empty = {
        "rows": [
            {
                "key": "pd",
                "name": "Pd",
                "direction": "higher-is-better",
                "cells": {
                    "sequential": {
                        "available": False,
                        "value": None,
                        "display": "Not available (no_completed_dwells)",
                    }
                },
            }
        ]
    }
    missing_bar = metrics_bar_figure(empty, "pd")
    assert missing_bar.data == () or len(missing_bar.data) == 0
    assert "Not available" in str(missing_bar.layout.annotations[0].text)


def test_layout_fits_1366x768() -> None:
    assert LAYOUT_MAX_WIDTH_PX == 1366
    assert CONTENT_MAX_WIDTH_PX <= 1366
