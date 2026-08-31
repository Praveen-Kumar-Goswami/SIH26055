"""Central contextual help copy. One dictionary for cursor hints and ARIA titles."""

from __future__ import annotations

from typing import Any

from smartscan.ml.strategy_registry import STRATEGY_REGISTRY

HELP_TEXT: dict[str, str] = {
    "p_active": (
        "Estimated probability that useful signal activity is currently present in this band."
    ),
    "p_hit": (
        "Estimated probability that scanning this band will produce a completed interception."
    ),
    "dwell": "How long the receiver remains tuned to the selected frequency band.",
    "dwell time": "How long the receiver remains tuned to the selected frequency band.",
    "air": (
        "Average Intercept Rate — how frequently successful interceptions are completed. "
        "Frozen v2 held-out AIR is not the v3/v4 research-test AIR; protocols differ."
    ),
    "average intercept rate": (
        "Average Intercept Rate — how frequently successful interceptions are completed."
    ),
    "candidate": (
        "This model is a technically valid research candidate. Live PPO is v4; "
        "the frozen v2 held-out gate is still failed, so Champion stays unset."
    ),
    "pfa": "Probability that noise is incorrectly declared as a signal detection.",
    "false alarm": "Probability that noise is incorrectly declared as a signal detection.",
    "periodicity": "Evidence that detected activity follows a repeating temporal pattern.",
    "agility": "Evidence that signal activity changes frequency over time.",
    "novelty": "Assessed unusualness of recent observable activity — not a hidden hostile label.",
    "overlay": "Evaluation overlay shows GroundTruth occupancy. It is not available to the policy.",
    "gate": "Frozen held-out acceptance result. False means champion/production stay unset.",
    "pd": "Operational probability of detection on occupied completed dwells.",
    "seed": "Deterministic RNG seed for the scenario and, independently, the detector.",
    "scenario": "Which built-in RF environment to simulate (sparse, dense, agile_threat, …).",
    "strategy": (
        "Seven public scan policies: sequential, random, fixed-priority, reactive, "
        "contextual-thompson, periodic-intercept, and ppo. Aliases are not separate strategies."
    ),
    "periodic-intercept": (
        "Search every band once, then stare when the next estimated illumination "
        "fits the dwell. Uses observed hits only — not GroundTruth occupancy."
    ),
    "phase": (
        "Estimated seconds until the next repeating illumination on this band, "
        "from observed hit times only."
    ),
}

for _sid, _meta in STRATEGY_REGISTRY.items():
    HELP_TEXT.setdefault(_sid, str(_meta["rule"]))

HELP_JSON: dict[str, str] = {key.lower(): value for key, value in HELP_TEXT.items()}


def help_for(label: str) -> str | None:
    """Return help text if *label* matches a known term."""

    text = label.strip().lower()
    if text in HELP_JSON:
        return HELP_JSON[text]
    for key, value in HELP_JSON.items():
        if key in text:
            return value
    return None


def help_payload() -> dict[str, Any]:
    return {"terms": HELP_JSON, "delay_ms": 3500}
