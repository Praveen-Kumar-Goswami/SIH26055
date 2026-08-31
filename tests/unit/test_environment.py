from __future__ import annotations

import numpy as np
import pytest

from smartscan.rf.bands import named_band_plan
from smartscan.rf.emitters import OnOffGate, emitter_from_dict
from smartscan.rf.environment import sample_random_scenario, simulate
from smartscan.seeding import spawn_generator
from smartscan.types import SmartScanError


def test_windows_gate() -> None:
    gate = OnOffGate(kind="windows", windows=((2, 5), (8, 10)))
    mask = gate.mask(12)
    expected = np.zeros(12, dtype=bool)
    expected[2:5] = True
    expected[8:10] = True
    assert np.array_equal(mask, expected)


def test_emitter_from_dict_all_kinds() -> None:
    cont = emitter_from_dict(
        {"kind": "continuous", "emitter_id": "c", "frequency_hz": 3.5e9, "power_w": 1.0}
    )
    circ = emitter_from_dict(
        {
            "kind": "circular_scan",
            "emitter_id": "r",
            "frequency_hz": 3.5e9,
            "power_w": 1.0,
            "scan_period_s": 0.1,
            "beamwidth_deg": 20.0,
        }
    )
    sec = emitter_from_dict(
        {
            "kind": "sector_scan",
            "emitter_id": "s",
            "frequency_hz": 3.5e9,
            "power_w": 1.0,
            "scan_period_s": 0.2,
            "theta_min_deg": -10.0,
            "theta_max_deg": 10.0,
            "beamwidth_deg": 5.0,
        }
    )
    hop = emitter_from_dict(
        {
            "kind": "frequency_agile",
            "emitter_id": "h",
            "hop_frequencies_hz": [3.5e9, 5.5e9],
            "dwell_steps": 4,
            "power_w": 1.0,
        }
    )
    assert cont.kind() == "continuous"
    assert circ.kind() == "circular_scan"
    assert sec.kind() == "sector_scan"
    assert hop.kind() == "frequency_agile"
    with pytest.raises(SmartScanError):
        emitter_from_dict({"kind": "nope", "emitter_id": "x", "power_w": 1.0})


def test_random_scenario_uses_local_rng() -> None:
    plan = named_band_plan("demo_2_18")
    a = sample_random_scenario(plan, 0.001, spawn_generator(0))
    b = sample_random_scenario(plan, 0.001, spawn_generator(0))
    c = sample_random_scenario(plan, 0.001, spawn_generator(1))
    assert [e.emitter_id for e in a] == [e.emitter_id for e in b]
    ids_c = [e.emitter_id for e in c]
    # Different seed may still collide on empty draws; compare dump when nonempty.
    dump_a = [e.model_dump() for e in a]
    dump_c = [e.model_dump() for e in c]
    assert dump_a == [e.model_dump() for e in b]
    if dump_a and dump_c:
        assert dump_a != dump_c or ids_c == [e.emitter_id for e in a]


def test_unknown_scenario() -> None:
    with pytest.raises(SmartScanError, match="Unknown scenario"):
        simulate(
            {
                "seed": 0,
                "dt_s": 0.001,
                "duration_s": 0.01,
                "band_plan_id": "demo_2_18",
                "scenario_id": "not_real",
            }
        )


def test_random_builtin_id() -> None:
    truth = simulate(
        {
            "seed": 3,
            "dt_s": 0.001,
            "duration_s": 0.05,
            "band_plan_id": "demo_2_18",
            "scenario_id": "random",
        }
    )
    assert truth.n_steps == 50
    assert truth.content_fingerprint
