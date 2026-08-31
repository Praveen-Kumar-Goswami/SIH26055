from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from smartscan.receiver.scanner import run_schedule
from smartscan.receiver.schedules import ScheduleView, SequentialSchedule
from smartscan.rf.bands import named_band_plan
from smartscan.rf.emitters import ContinuousEmitter
from smartscan.rf.environment import render_ground_truth, simulate
from smartscan.types import ReceiverConfig, ScanCommand, SmartScanError


class ScriptedSchedule:
    def __init__(self, pairs: list[tuple[int, int]]) -> None:
        self.pairs = pairs
        self.i = 0

    def next_command(self, view: ScheduleView) -> ScanCommand:
        if self.i >= len(self.pairs):
            raise StopIteration
        band, dwell = self.pairs[self.i]
        self.i += 1
        return ScanCommand(
            decision_id=f"d{view.decision_index:05d}",
            target_band=band,
            dwell_steps=dwell,
        )


def _cfg(**kwargs: object) -> ReceiverConfig:
    payload: dict[str, object] = {
        "receiver_ibw_hz": 1e8,
        "scan_span_hz": 16e9,
        "tune_latency_steps": 1,
        "dwell_bins": (1, 2, 4, 8, 16),
        "pfa_design": 1e-3,
        "samples_per_step": 1,
        "noise_mode": "normalized",
        "noise_power_w": 1.0,
    }
    payload.update(kwargs)
    return ReceiverConfig.model_validate(payload)


def _truth(n_steps: int, power_w: float = 0.0, freq_hz: float = 10.5e9):
    plan = named_band_plan("demo_2_18")
    emitters = []
    if power_w > 0:
        emitters = [
            ContinuousEmitter(emitter_id="c", frequency_hz=freq_hz, power_w=power_w)
        ]
    return render_ground_truth(
        emitters=emitters,
        band_plan=plan,
        n_steps=n_steps,
        dt_s=0.001,
        seed=0,
        scenario_id="rx_fixture",
        scenario_config={"scenario_id": "rx_fixture", "n_steps": n_steps},
    )


def test_same_band_zero_retune() -> None:
    truth = _truth(20)
    run = run_schedule(truth, ScriptedSchedule([(0, 2), (0, 2)]), _cfg(), receiver_seed=0)
    states = [row.receiver_state for row in run.observations.rows]
    # cmd1: T + 2D; cmd2: 2D (settled)
    assert states[:3] == ["TUNING", "DWELLING", "DWELLING"]
    assert states[3:5] == ["DWELLING", "DWELLING"]
    assert sum(1 for s in states if s == "TUNING") == 1
    assert len(run.decisions.rows) == 2
    assert run.decisions.rows[0].end_step == 3
    assert run.decisions.rows[1].start_step == 3
    assert run.decisions.rows[1].tune_end_step == 3
    assert run.decisions.rows[1].end_step == 5


def test_cross_band_tuning_no_detection() -> None:
    truth = _truth(20, power_w=50.0)
    run = run_schedule(truth, ScriptedSchedule([(8, 2), (0, 2)]), _cfg(), receiver_seed=1)
    d0, d1 = run.decisions.rows[:2]
    assert d1.start_step == d0.end_step
    tune_rows = [
        row
        for row in run.observations.rows
        if row.decision_id == d1.decision_id and row.receiver_state == "TUNING"
    ]
    assert len(tune_rows) == 1
    assert tune_rows[0].tuned_band is None
    assert tune_rows[0].integrated_energy == 0.0
    assert tune_rows[0].detection is False


def test_incomplete_final_dwell() -> None:
    truth = _truth(5)
    run = run_schedule(truth, ScriptedSchedule([(0, 2), (1, 2)]), _cfg(), receiver_seed=0)
    # cmd1 uses steps 0,1,2 complete; cmd2 tunes at 3, dwells at 4, incomplete
    assert len(run.decisions.rows) == 1
    assert run.decisions.n_incomplete_commands == 1
    assert run.observations.rows[-1].step == 4
    assert run.observations.rows[-1].detection is False


def test_exact_boundary_completes() -> None:
    truth = _truth(3)
    run = run_schedule(truth, ScriptedSchedule([(0, 2)]), _cfg(), receiver_seed=0)
    assert len(run.decisions.rows) == 1
    assert run.decisions.rows[0].end_step == 3
    assert run.decisions.n_incomplete_commands == 0


def test_invalid_band_command() -> None:
    truth = _truth(10)
    with pytest.raises(SmartScanError, match="outside"):
        run_schedule(truth, ScriptedSchedule([(99, 2)]), _cfg(), receiver_seed=0)


def test_ibw_wider_than_target_band() -> None:
    truth = _truth(10)
    wide = _cfg(receiver_ibw_hz=2e9, scan_span_hz=40e9)
    with pytest.raises((SmartScanError, ValidationError), match="wider"):
        run_schedule(truth, ScriptedSchedule([(0, 2)]), wide, receiver_seed=0)


def test_one_decision_per_complete_dwell_and_hit_timestamp() -> None:
    truth = _truth(30, power_w=0.0)
    run = run_schedule(truth, SequentialSchedule(dwell_steps=4), _cfg(), receiver_seed=0)
    ids = [row.decision_id for row in run.decisions.rows]
    assert len(ids) == len(set(ids))
    for decision in run.decisions.rows:
        usable = [
            row
            for row in run.observations.rows
            if row.decision_id == decision.decision_id and row.receiver_state == "DWELLING"
        ]
        assert len(usable) == decision.dwell_steps
        detecting = [row for row in usable if row.detection]
        if decision.hit:
            assert len(detecting) == 1
            assert detecting[0].step == decision.end_step - 1
        else:
            assert detecting == []
        assert decision.end_step == decision.tune_end_step + decision.dwell_steps


def test_no_integration_during_tuning() -> None:
    truth = _truth(12, power_w=80.0)
    run = run_schedule(truth, SequentialSchedule(dwell_steps=2), _cfg(), receiver_seed=3)
    for row in run.observations.rows:
        if row.receiver_state == "TUNING":
            assert row.integrated_energy == 0.0
            assert row.detection is False
            assert row.tuned_band is None


def test_overlapping_power_is_linear() -> None:
    plan = named_band_plan("demo_2_18")
    a = ContinuousEmitter(emitter_id="a", frequency_hz=10.5e9, power_w=3.0)
    b = ContinuousEmitter(emitter_id="b", frequency_hz=10.5e9, power_w=4.0)
    truth = render_ground_truth(
        emitters=[a, b],
        band_plan=plan,
        n_steps=8,
        dt_s=0.001,
        seed=0,
        scenario_id="sum",
        scenario_config={"scenario_id": "sum"},
    )
    band = 8
    assert np.allclose(truth.signal_power_w[:, band], 7.0)
    run = run_schedule(
        truth, ScriptedSchedule([(band, 4)]), _cfg(tune_latency_steps=0), receiver_seed=0
    )
    assert len(run.decisions.rows) == 1


def test_receiver_seed_changes_detections_not_bands() -> None:
    truth = simulate(
        {
            "seed": 0,
            "dt_s": 0.001,
            "duration_s": 0.2,
            "band_plan_id": "demo_2_18",
            "scenario_id": "edge_zero",
        }
    )
    cfg = _cfg(pfa_design=0.2)
    a = run_schedule(truth, SequentialSchedule(4), cfg, receiver_seed=1)
    b = run_schedule(truth, SequentialSchedule(4), cfg, receiver_seed=2)
    bands_a = [row.target_band for row in a.decisions.rows]
    bands_b = [row.target_band for row in b.decisions.rows]
    assert bands_a == bands_b
    hits_a = [row.hit for row in a.decisions.rows]
    hits_b = [row.hit for row in b.decisions.rows]
    assert hits_a != hits_b


def test_identical_replay() -> None:
    truth = _truth(40)
    cfg = _cfg()
    a = run_schedule(truth, SequentialSchedule(4), cfg, receiver_seed=9)
    b = run_schedule(truth, SequentialSchedule(4), cfg, receiver_seed=9)
    assert [r.hit for r in a.decisions.rows] == [r.hit for r in b.decisions.rows]
    assert [r.target_band for r in a.decisions.rows] == [r.target_band for r in b.decisions.rows]
    assert [r.integrated_energy for r in a.observations.rows] == [
        r.integrated_energy for r in b.observations.rows
    ]


def test_incomplete_during_tuning() -> None:
    truth = _truth(2)
    run = run_schedule(
        truth, ScriptedSchedule([(0, 2)]), _cfg(tune_latency_steps=3), receiver_seed=0
    )
    assert len(run.decisions.rows) == 0
    assert run.decisions.n_incomplete_commands == 1
    assert all(row.receiver_state == "TUNING" for row in run.observations.rows)


def test_tune_consumes_entire_horizon() -> None:
    truth = _truth(1)
    run = run_schedule(truth, ScriptedSchedule([(0, 2)]), _cfg(), receiver_seed=0)
    assert len(run.decisions.rows) == 0
    assert run.decisions.n_incomplete_commands == 1
    assert run.observations.rows[0].receiver_state == "TUNING"


def test_nonfinite_rho_rejected() -> None:
    truth = _truth(8)
    truth.signal_power_w[1, 0] = np.nan
    with pytest.raises(SmartScanError, match="Non-finite rho"):
        run_schedule(truth, ScriptedSchedule([(0, 2)]), _cfg(), receiver_seed=0)


def test_command_dwell_and_span_ratio_defense() -> None:
    truth = _truth(10)

    class BadDwell:
        def next_command(self, view: ScheduleView) -> ScanCommand:
            return ScanCommand.model_construct(
                decision_id=f"d{view.decision_index:05d}",
                target_band=0,
                dwell_steps=0,
            )

    with pytest.raises(SmartScanError, match="dwell_steps must be positive"):
        run_schedule(truth, BadDwell(), _cfg(), receiver_seed=0)

    illegal = ReceiverConfig.model_construct(
        receiver_ibw_hz=1e8,
        scan_span_hz=5e8,
        tune_latency_steps=1,
        dwell_bins=(1, 2, 4),
        noise_mode="normalized",
        pfa_design=1e-3,
        samples_per_step=1,
        temperature_k=None,
        noise_figure_db=None,
        noise_power_w=1.0,
        receiver_id="rx0",
        n_channels=1,
    )
    with pytest.raises(SmartScanError, match=">= 10"):
        run_schedule(truth, ScriptedSchedule([(0, 2)]), illegal, receiver_seed=0)


def test_run_schedule_accepts_dict_config() -> None:
    truth = _truth(6)
    run = run_schedule(
        truth,
        ScriptedSchedule([(0, 2)]),
        {
            "receiver_ibw_hz": 1e8,
            "scan_span_hz": 16e9,
            "tune_latency_steps": 1,
            "dwell_bins": [1, 2, 4],
            "pfa_design": 1e-3,
            "samples_per_step": 1,
            "noise_mode": "normalized",
        },
        receiver_seed=0,
    )
    assert len(run.decisions.rows) == 1
