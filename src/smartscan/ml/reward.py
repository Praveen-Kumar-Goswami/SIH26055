"""Observable reward. All terms come from the current action and receiver output."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from smartscan.config import RewardWeights
from smartscan.ml.observable import ObservableTransition
from smartscan.types import DecisionRow, SmartScanError


@dataclass(frozen=True)
class RewardBreakdown:
    reward: float
    priority: float
    novelty: float
    assessed_threat: float
    reward_hit: float
    reward_priority: float
    cost_tune: float
    cost_time: float
    cost_repeat: float
    cost_false_like: float


class RewardCalculator:
    """``RewardCalculator`` accepts only ``ObservableTransition`` (+ optional forecasts)."""

    def __init__(self, weights: RewardWeights | None = None) -> None:
        self.weights = weights or RewardWeights()

    def compute(
        self,
        transition: ObservableTransition,
        *,
        p_hit: float,
        novelty: float,
        uncertainty: float,
        assessed_threat: float,
        recent_same_band_no_hit: bool,
        low_confidence_hit: bool,
        first_hit_on_visit: bool = True,
        coverage_visit: bool = False,
    ) -> RewardBreakdown:
        w = self.weights
        if not np.isfinite(p_hit) or not np.isfinite(novelty) or not np.isfinite(uncertainty):
            raise SmartScanError("Reward inputs must be finite.")
        novelty_b = float(np.clip(novelty, 0.0, w.novelty_bonus_cap))
        unc_b = float(np.clip(uncertainty, 0.0, w.uncertainty_bonus_cap))
        threat = float(assessed_threat) if np.isfinite(assessed_threat) else 1.0
        priority = threat * float(p_hit) + w.lambda_novelty * novelty_b + w.lambda_uncertainty * unc_b
        hit = 1.0 if transition.hit else 0.0
        first_hit = bool(first_hit_on_visit) if transition.hit else False
        if bool(getattr(w, "first_hit_only", False)):
            hit_credit = 1.0 if first_hit else 0.0
        else:
            hit_credit = hit
        reward_hit = w.w_hit * hit_credit
        coverage_bonus = float(getattr(w, "w_coverage", 0.0) or 0.0) if coverage_visit else 0.0
        reward_priority = w.w_priority * hit_credit * float(priority) + coverage_bonus
        if str(w.time_cost_mode) == "per_step":
            ref = max(int(w.time_cost_reference_steps), 1)
            cost_tune = w.c_tune * float(transition.tune_cost_steps)
            cost_time = w.c_time * float(transition.command_steps) / float(ref)
        elif str(w.time_cost_mode) == "excess_dwell":
            ref = max(int(w.time_cost_reference_steps), 1)
            cost_tune = w.c_tune * float(transition.tune_cost_steps)
            excess = max(0.0, float(transition.command_steps) - float(ref))
            cost_time = w.c_time * excess / float(ref)
        else:
            cost_tune = w.c_tune * float(transition.tune_cost_steps) * float(transition.dt_s)
            cost_time = w.c_time * float(transition.command_steps) * float(transition.dt_s)
        cost_time = float(cost_time) + float(getattr(w, "c_action", 0.0) or 0.0)
        cost_repeat = w.c_repeat if recent_same_band_no_hit else 0.0
        if transition.hit and not first_hit:
            cost_repeat = float(cost_repeat) + float(getattr(w, "c_repeat_hit", 0.0) or 0.0)
        cost_false = w.c_false_like if (transition.hit and low_confidence_hit) else 0.0
        reward = reward_hit + reward_priority - cost_tune - cost_time - cost_repeat - cost_false
        if not np.isfinite(reward):
            raise SmartScanError("Non-finite reward.")
        return RewardBreakdown(
            reward=float(reward),
            priority=float(priority),
            novelty=novelty_b,
            assessed_threat=threat,
            reward_hit=float(reward_hit),
            reward_priority=float(reward_priority),
            cost_tune=float(cost_tune),
            cost_time=float(cost_time),
            cost_repeat=float(cost_repeat),
            cost_false_like=float(cost_false),
        )


def stamp_decision_reward(row: DecisionRow, breakdown: RewardBreakdown) -> DecisionRow:
    """Return a copy of *row* with logged reward components."""

    return row.model_copy(
        update={
            "reward": breakdown.reward,
            "assessed_threat": breakdown.assessed_threat,
            "novelty": breakdown.novelty,
            "priority": breakdown.priority,
            "reward_hit": breakdown.reward_hit,
            "reward_priority": breakdown.reward_priority,
            "cost_repeat": breakdown.cost_repeat,
            "cost_false_like": breakdown.cost_false_like,
            "cost_tune_s": breakdown.cost_tune,
            "cost_time_s": breakdown.cost_time,
        }
    )


def recent_same_band_no_hit(history: list[ObservableTransition], band: int) -> bool:
    if not history:
        return False
    last = history[-1]
    return last.target_band == int(band) and not last.hit


def is_first_hit_on_visit(history: list[ObservableTransition], transition: ObservableTransition) -> bool:
    """True when this hit starts a new stay (last command was a miss or a different band)."""

    if not transition.hit:
        return False
    if not history:
        return True
    last = history[-1]
    if last.target_band == int(transition.target_band) and last.hit:
        return False
    return True


def is_coverage_visit(
    history: list[ObservableTransition], band: int, window: int
) -> bool:
    """True when *band* is absent from the last *window* completed commands."""

    span = max(int(window), 1)
    recent = [int(item.target_band) for item in history[-span:]]
    return int(band) not in recent
