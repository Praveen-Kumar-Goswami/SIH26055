"""Layout constants for a 1366x768 laptop viewport."""

from __future__ import annotations

LAYOUT_MAX_WIDTH_PX = 1366
LAYOUT_MAX_HEIGHT_PX = 768
PLOT_HEIGHT_PX = 360
SIDEBAR_WIDTH_PX = 280
CONTENT_MAX_WIDTH_PX = LAYOUT_MAX_WIDTH_PX - SIDEBAR_WIDTH_PX

# Okabe–Ito color-blind-safe palette, with a restrained defence-tech chrome.
PALETTE = {
    "black": "#000000",
    "orange": "#E69F00",
    "sky": "#56B4E9",
    "green": "#009E73",
    "yellow": "#F0E442",
    "blue": "#0072B2",
    "vermillion": "#D55E00",
    "purple": "#CC79A7",
    "bg": "#05080B",
    "panel": "#0A161C",
    "panel_alt": "#091319",
    "text": "#E8EEF2",
    "muted": "#7C8B96",
    "line": "#1C2A33",
    "accent": "#3AA8B5",
    "amber": "#C4922A",
    "fail": "#A85A4E",
}

STRATEGY_COLORS = {
    "sequential": PALETTE["sky"],
    "random": PALETTE["orange"],
    "fixed-priority": PALETTE["green"],
    "reactive": PALETTE["yellow"],
    "contextual-thompson": PALETTE["purple"],
    "periodic-intercept": PALETTE["vermillion"],
    "ppo": PALETTE["blue"],
    "oracle-ceiling": PALETTE["muted"],
}

NAV_LABELS: dict[str, str] = {
    "Configure & Run": "01  Configure & Run",
    "Scan Replay": "02  Scan Replay",
    "Smart Decision": "03  Smart Decision",
    "Metrics Compare": "04  Metrics Compare",
    "Run History": "05  Run History",
    "Model & Data Lineage": "06  Model & Data Lineage",
}
