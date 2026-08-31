from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from smartscan.rf.bands import frequency_to_band, named_band_plan
from smartscan.rf.emitters import (
    CircularScanEmitter,
    ContinuousEmitter,
    FrequencyAgileEmitter,
    OnOffGate,
    SectorScanEmitter,
    wrap_free_angular_distance_deg,
)
from smartscan.types import SmartScanError

DT = 0.001


def _plan():
    return named_band_plan("demo_2_18")


def test_continuous_duty_cycle() -> None:
    plan = _plan()
    emitter = ContinuousEmitter(emitter_id="c", frequency_hz=10.5e9, power_w=1e-12)
    occ, pwr = emitter.render(100, plan, DT)
    band = frequency_to_band(10.5e9, plan)
    assert occ[:, band].all()
    assert occ[:, band + 1].sum() == 0
    assert np.allclose(pwr[:, band], 1e-12)


def test_on_off_gate_periodic() -> None:
    plan = _plan()
    gate = OnOffGate(kind="periodic", period_steps=10, on_steps=4, phase_offset=0)
    emitter = ContinuousEmitter(
        emitter_id="g", frequency_hz=10.5e9, power_w=1.0, gate=gate
    )
    occ, _ = emitter.render(20, plan, DT)
    band = frequency_to_band(10.5e9, plan)
    expected = np.array([True, True, True, True, False, False, False, False, False, False] * 2)
    assert np.array_equal(occ[:, band], expected)


def test_circular_sampled_duty_count() -> None:
    plan = _plan()
    period_s = 0.360
    period_steps = 360
    beamwidth = 36.0
    emitter = CircularScanEmitter(
        emitter_id="circ",
        frequency_hz=6.5e9,
        power_w=1.0,
        scan_period_s=period_s,
        beamwidth_deg=beamwidth,
        receiver_azimuth_deg=0.0,
        phase0_steps=0,
    )
    occ, _ = emitter.render(period_steps, plan, DT)
    band = frequency_to_band(6.5e9, plan)
    count = int(occ[:, band].sum())
    expected = int(round(beamwidth / 360.0 * period_steps))
    assert abs(count - expected) <= 1
    # One-period duty fraction vs exact illuminated-step count.
    assert abs(count / period_steps - expected / period_steps) <= 1 / period_steps


def test_sector_endpoints_and_directions() -> None:
    plan = _plan()
    period_s = 0.100
    common = dict(
        emitter_id="sec",
        frequency_hz=8.5e9,
        power_w=1.0,
        scan_period_s=period_s,
        theta_min_deg=-20.0,
        theta_max_deg=20.0,
        beamwidth_deg=8.0,
        receiver_azimuth_deg=0.0,
        phase0_steps=0,
    )
    up = SectorScanEmitter(**common, initial_direction=1)
    down = SectorScanEmitter(**{**common, "emitter_id": "sec_down"}, initial_direction=-1)
    pointing_up = up.pointing_deg(100, DT)
    pointing_down = down.pointing_deg(100, DT)
    assert pointing_up[0] == pytest.approx(-20.0)
    assert pointing_up[50] == pytest.approx(20.0)
    assert pointing_down[0] == pytest.approx(20.0)
    assert pointing_down[50] == pytest.approx(-20.0)
    occ, _ = up.render(100, plan, DT)
    assert occ.any()


def test_wrap_free_angular_distance() -> None:
    assert wrap_free_angular_distance_deg(359.0, 1.0) == pytest.approx(2.0)
    assert wrap_free_angular_distance_deg(10.0, 350.0) == pytest.approx(20.0)
    vec = wrap_free_angular_distance_deg(np.array([0.0, 180.0]), 0.0)
    assert vec[0] == pytest.approx(0.0)
    assert vec[1] == pytest.approx(180.0)


def test_agile_hop_at_every_boundary() -> None:
    plan = _plan()
    hops = (3.5e9, 5.5e9, 7.5e9)
    emitter = FrequencyAgileEmitter(
        emitter_id="hop",
        hop_frequencies_hz=hops,
        dwell_steps=10,
        power_w=2.0,
        phase_offset=0,
    )
    occ, pwr = emitter.render(30, plan, DT)
    bands = [frequency_to_band(f, plan) for f in hops]
    assert occ[:10, bands[0]].all()
    assert occ[10:20, bands[1]].all()
    assert occ[20:30, bands[2]].all()
    assert occ[:10, bands[1]].sum() == 0
    assert np.allclose(pwr[10:20, bands[1]], 2.0)
    # Same-band adjacent dwells remain one event (tested in events).


def test_agile_rejects_empty_or_zero_dwell() -> None:
    with pytest.raises((SmartScanError, ValidationError)):
        FrequencyAgileEmitter(emitter_id="x", hop_frequencies_hz=(), dwell_steps=1, power_w=1.0)
    with pytest.raises((SmartScanError, ValidationError)):
        FrequencyAgileEmitter(
            emitter_id="x", hop_frequencies_hz=(3.5e9,), dwell_steps=0, power_w=1.0
        )


def test_negative_power_rejected() -> None:
    with pytest.raises((SmartScanError, ValidationError), match="power_w"):
        ContinuousEmitter(emitter_id="bad", frequency_hz=3e9, power_w=-1.0)
