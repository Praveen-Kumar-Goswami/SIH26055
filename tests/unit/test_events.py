from __future__ import annotations

import numpy as np

from smartscan.rf.bands import frequency_to_band, named_band_plan
from smartscan.rf.emitters import ContinuousEmitter, FrequencyAgileEmitter
from smartscan.rf.environment import render_ground_truth
from smartscan.rf.events import extract_runs


def test_extract_runs_half_open() -> None:
    active = np.array([0, 1, 1, 0, 1, 0, 0, 1, 1, 1], dtype=bool)
    assert extract_runs(active) == [(1, 3), (4, 5), (7, 10)]


def test_overlap_or_and_linear_power_sum() -> None:
    plan = named_band_plan("demo_2_18")
    freq = 4.5e9
    a = ContinuousEmitter(emitter_id="a", frequency_hz=freq, power_w=1.0)
    b = ContinuousEmitter(emitter_id="b", frequency_hz=freq, power_w=2.0)
    truth = render_ground_truth(
        emitters=[a, b],
        band_plan=plan,
        n_steps=8,
        dt_s=0.001,
        seed=0,
        scenario_id="overlap",
        scenario_config={"scenario_id": "overlap", "seed": 0},
    )
    band = frequency_to_band(freq, plan)
    assert truth.occupied[:, band].all()
    assert np.allclose(truth.signal_power_w[:, band], 3.0)
    emitter_ids = {record.emitter_id for record in truth.events.records()}
    assert emitter_ids == {"a", "b"}
    assert len(truth.events) == 2


def test_agile_same_band_adjacent_is_one_event() -> None:
    plan = named_band_plan("demo_2_18")
    freq = 4.5e9
    emitter = FrequencyAgileEmitter(
        emitter_id="hop",
        hop_frequencies_hz=(freq, freq),
        dwell_steps=5,
        power_w=1.0,
    )
    truth = render_ground_truth(
        emitters=[emitter],
        band_plan=plan,
        n_steps=20,
        dt_s=0.001,
        seed=0,
        scenario_id="agile_same",
        scenario_config={"scenario_id": "agile_same"},
    )
    records = [r for r in truth.events.records() if r.emitter_id == "hop"]
    assert len(records) == 1
    assert records[0].start_step == 0
    assert records[0].end_step == 20


def test_hop_closes_event() -> None:
    plan = named_band_plan("demo_2_18")
    emitter = FrequencyAgileEmitter(
        emitter_id="hop",
        hop_frequencies_hz=(3.5e9, 9.5e9),
        dwell_steps=4,
        power_w=1.0,
    )
    truth = render_ground_truth(
        emitters=[emitter],
        band_plan=plan,
        n_steps=8,
        dt_s=0.001,
        seed=0,
        scenario_id="agile_switch",
        scenario_config={"scenario_id": "agile_switch"},
    )
    records = truth.events.records()
    assert len(records) == 2
    assert records[0].end_step == 4
    assert records[1].start_step == 4
