"""Authoritative public strategy identifiers.

Dashboard, CLI, replay, and persistence must use these exact strings.
Frozen held-out evaluation keeps a smaller baseline set so historical
gate evidence is not rewritten.
"""

from __future__ import annotations

from typing import Any

from smartscan.types import SmartScanError

SEQUENTIAL = "sequential"
RANDOM = "random"
FIXED_PRIORITY = "fixed-priority"
REACTIVE = "reactive"
CONTEXTUAL_THOMPSON = "contextual-thompson"
PERIODIC_INTERCEPT_STRATEGY = "periodic-intercept"
PPO = "ppo"

PUBLIC_STRATEGIES: tuple[str, ...] = (
    SEQUENTIAL,
    RANDOM,
    FIXED_PRIORITY,
    REACTIVE,
    CONTEXTUAL_THOMPSON,
    PERIODIC_INTERCEPT_STRATEGY,
    PPO,
)
TOTAL_PUBLIC_STRATEGIES = len(PUBLIC_STRATEGIES)

# Frozen Stage 5/7 held-out gate baselines. Do not add periodic-intercept or
# extra names here — that would change historical n_rows / comparisons.
HELD_OUT_BASELINE_STRATEGIES: tuple[str, ...] = (
    SEQUENTIAL,
    RANDOM,
    FIXED_PRIORITY,
    REACTIVE,
    CONTEXTUAL_THOMPSON,
)

# Live/demo policies that do not require a learned bundle.
LIVE_STRATEGIES: tuple[str, ...] = tuple(name for name in PUBLIC_STRATEGIES if name != PPO)

KIND_RULE = "rule_baseline"
KIND_STATISTICAL = "adaptive_statistical"
KIND_LEARNED = "learned_rl"

KIND_LABELS: dict[str, str] = {
    KIND_RULE: "rule / baseline",
    KIND_STATISTICAL: "adaptive statistical",
    KIND_LEARNED: "learned RL model",
}

BEST_AVAILABLE_TOKENS = frozenset({"best-available", "best", "bestavailable"})
ORACLE_TOKENS = frozenset({"oracle-ceiling", "oracle"})
ORACLE_STRATEGY = "oracle-ceiling"

_ALIASES: dict[str, str] = {
    "seq": SEQUENTIAL,
    "uniform": RANDOM,
    "uniform-random": RANDOM,
    "fixed": FIXED_PRIORITY,
    "priority": FIXED_PRIORITY,
    "hit-recency": REACTIVE,
    "periodic": PERIODIC_INTERCEPT_STRATEGY,
    "scan-on-scan": PERIODIC_INTERCEPT_STRATEGY,
    "cts": CONTEXTUAL_THOMPSON,
    "thompson": CONTEXTUAL_THOMPSON,
    "scheduler": PPO,
}

STRATEGY_REGISTRY: dict[str, dict[str, Any]] = {
    SEQUENTIAL: {
        "kind": KIND_RULE,
        "display_name": "Sequential",
        "requires_bundle": False,
        "held_out_baseline": True,
        "rule": "Visits bands in documented sequence.",
    },
    RANDOM: {
        "kind": KIND_RULE,
        "display_name": "Random",
        "requires_bundle": False,
        "held_out_baseline": True,
        "rule": "Selects legal bands according to the seeded random policy.",
    },
    FIXED_PRIORITY: {
        "kind": KIND_RULE,
        "display_name": "Fixed Priority",
        "requires_bundle": False,
        "held_out_baseline": True,
        "rule": "Uses the configured fixed-priority ordering.",
    },
    REACTIVE: {
        "kind": KIND_RULE,
        "display_name": "Reactive",
        "requires_bundle": False,
        "held_out_baseline": True,
        "rule": "Responds only to previous receiver-visible hits and misses.",
    },
    CONTEXTUAL_THOMPSON: {
        "kind": KIND_STATISTICAL,
        "display_name": "Contextual Thompson",
        "requires_bundle": False,
        "held_out_baseline": True,
        "rule": "Contextual Thompson sampling over observable band/dwell features.",
    },
    PERIODIC_INTERCEPT_STRATEGY: {
        "kind": KIND_RULE,
        "display_name": "Periodic Intercept",
        "requires_bundle": False,
        "held_out_baseline": False,
        "rule": (
            "Searches unvisited bands, then stares near the next estimated "
            "illumination from observed hit times only."
        ),
    },
    PPO: {
        "kind": KIND_LEARNED,
        "display_name": "PPO",
        "requires_bundle": True,
        "held_out_baseline": False,
        "rule": "Learned PPO policy from the loaded SmartScanScheduler bundle.",
    },
}


def normalize_strategy_token(name: str) -> str:
    return str(name).strip().lower().replace("_", "-")


def canonicalize_strategy_id(name: str) -> str:
    """Map a user/CLI token onto a public strategy id. Aliases are not public ids."""

    token = normalize_strategy_token(name)
    if token in STRATEGY_REGISTRY:
        return token
    mapped = _ALIASES.get(token)
    if mapped is not None:
        return mapped
    raise SmartScanError(
        f"Unknown strategy {name!r}. Public strategies: {', '.join(PUBLIC_STRATEGIES)}."
    )


def canonicalize_run_strategy(name: str, *, allow_oracle: bool = True) -> str:
    """Public strategy id, or evaluator-only oracle-ceiling when explicitly allowed."""

    token = normalize_strategy_token(name)
    if token in ORACLE_TOKENS:
        if not allow_oracle:
            raise SmartScanError("Oracle ceiling is evaluator-only and is not a deployable baseline.")
        return ORACLE_STRATEGY
    return canonicalize_strategy_id(name)


def parse_cli_strategy(name: str, *, allow_best_available: bool = False) -> str:
    """Validate a CLI --strategy token. Returns a public id or best-available."""

    token = normalize_strategy_token(name)
    if allow_best_available and token in BEST_AVAILABLE_TOKENS:
        return "best-available"
    return canonicalize_strategy_id(name)


def is_public_strategy(name: str) -> bool:
    try:
        return canonicalize_strategy_id(name) in PUBLIC_STRATEGIES
    except SmartScanError:
        return False


def strategy_kind(name: str) -> str:
    return str(STRATEGY_REGISTRY[canonicalize_strategy_id(name)]["kind"])


def strategy_kind_label(name: str) -> str:
    return KIND_LABELS[strategy_kind(name)]


def strategy_rule(name: str) -> str:
    return str(STRATEGY_REGISTRY[canonicalize_strategy_id(name)]["rule"])


def strategy_requires_bundle(name: str) -> bool:
    return bool(STRATEGY_REGISTRY[canonicalize_strategy_id(name)]["requires_bundle"])


def public_strategy_count() -> int:
    return len(PUBLIC_STRATEGIES)
