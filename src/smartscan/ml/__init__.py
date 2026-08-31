"""Observable intercept prediction and smart scheduler (Stage 5)."""

from __future__ import annotations

from smartscan.ml.actions import decode_action, encode_action, n_actions
from smartscan.ml.features import FeatureBuilder, ObservationNormalizer
from smartscan.ml.observable import ObservableTransition, assert_no_oracle_payload
from smartscan.ml.policies import (
    LIVE_STRATEGIES,
    PERIODIC_INTERCEPT_STRATEGY,
    PUBLIC_STRATEGIES,
    ContextualThompsonSchedule,
    OracleCeilingSchedule,
    PeriodicInterceptSchedule,
    ReactiveSchedule,
    construct_live_policy,
    make_policy,
)
from smartscan.ml.predictor import HitHazardPredictor, RecencyPredictor, survival_nll
from smartscan.ml.reward import RewardCalculator
from smartscan.ml.strategy_registry import STRATEGY_REGISTRY, canonicalize_strategy_id

__all__ = [
    "ContextualThompsonSchedule",
    "FeatureBuilder",
    "HitHazardPredictor",
    "LIVE_STRATEGIES",
    "ObservableTransition",
    "ObservationNormalizer",
    "OracleCeilingSchedule",
    "PERIODIC_INTERCEPT_STRATEGY",
    "PUBLIC_STRATEGIES",
    "PeriodicInterceptSchedule",
    "ReactiveSchedule",
    "RecencyPredictor",
    "RewardCalculator",
    "STRATEGY_REGISTRY",
    "assert_no_oracle_payload",
    "canonicalize_strategy_id",
    "construct_live_policy",
    "decode_action",
    "encode_action",
    "make_policy",
    "n_actions",
    "survival_nll",
]
