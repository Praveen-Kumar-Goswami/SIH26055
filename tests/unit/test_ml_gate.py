from __future__ import annotations

import numpy as np

from smartscan.config import BenchmarkConfig
from smartscan.metrics.statistics import newcombe_diff_upper
from smartscan.ml.evaluate import GateResult, SeedRow, score_performance_gate
from smartscan.ml.predictor import survival_nll


def _row(strategy: str, scenario: str, seed: int, air: float, delay: float, pfa_n: float, pfa_d: float) -> SeedRow:
    return SeedRow(
        scenario_id=scenario,
        seed=seed,
        strategy=strategy,
        metrics={
            "average_intercept_rate": air,
            "event_interception_ratio": air * 0.5,
            "median_delay": delay,
            "pfa": pfa_n / pfa_d,
        },
        pfa_num=pfa_n,
        pfa_den=pfa_d,
    )


def test_newcombe_upper_reasonable() -> None:
    upper = newcombe_diff_upper(2, 1000, 1, 1000)
    assert upper < 0.05
    assert upper > -0.01


def test_performance_gate_fails_without_improvement() -> None:
    bench = BenchmarkConfig()
    rows: list[SeedRow] = []
    for i in range(8):
        for fam in ("sparse", "dense", "agile_threat"):
            rows.append(_row("ppo", fam, i, 1.0, 0.2, 1, 100))
            rows.append(_row("sequential", fam, i, 1.0, 0.2, 1, 100))
            rows.append(_row("random", fam, i, 1.0, 0.2, 1, 100))
            rows.append(_row("reactive", fam, i, 1.0, 0.2, 1, 100))
            rows.append(_row("fixed-priority", fam, i, 1.0, 0.2, 1, 100))
            rows.append(_row("contextual-thompson", fam, i, 1.0, 0.2, 1, 100))
    gate = score_performance_gate(rows, bench)
    assert isinstance(gate, GateResult)
    assert gate.performance_gate_passed is False
    assert gate.reasons


def test_performance_gate_can_pass_synthetic_win() -> None:
    bench = BenchmarkConfig()
    rows: list[SeedRow] = []
    for i in range(10):
        for fam in ("sparse", "agile_threat"):
            rows.append(_row("ppo", fam, i, 2.0, 0.05, 1, 1000))
            rows.append(_row("sequential", fam, i, 1.0, 0.20, 1, 1000))
            rows.append(_row("random", fam, i, 1.0, 0.20, 1, 1000))
            rows.append(_row("reactive", fam, i, 1.1, 0.18, 1, 1000))
            rows.append(_row("fixed-priority", fam, i, 1.05, 0.19, 1, 1000))
            rows.append(_row("contextual-thompson", fam, i, 1.2, 0.16, 1, 1000))
    gate = score_performance_gate(rows, bench)
    assert gate.performance_gate_passed is True


def test_survival_numerical_stability() -> None:
    h = np.clip(np.array([1e-12, 1.0 - 1e-12, 0.5]), 1e-8, 1 - 1e-8)
    assert np.isfinite(float(survival_nll(h, 0)))
    assert np.isfinite(float(survival_nll(h, None)))
