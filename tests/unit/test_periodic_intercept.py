from __future__ import annotations

import inspect

import pytest

from smartscan.ml.policies import PeriodicInterceptSchedule, make_policy
from smartscan.receiver.schedules import ScheduleView
from smartscan.types import SmartScanError


def _view(**kwargs: object) -> ScheduleView:
    payload: dict[str, object] = {
        "step": 0,
        "n_steps": 2000,
        "n_bands": 4,
        "settled_band": None,
        "last_target_band": None,
        "dwell_bins": (2, 8),
        "default_dwell_steps": 8,
        "decision_index": 0,
        "dt_s": 0.01,
    }
    payload.update(kwargs)
    return ScheduleView(**payload)  # type: ignore[arg-type]


def test_make_policy_periodic_intercept_name() -> None:
    sched = make_policy("periodic-intercept", dwell_steps=8, schedule_seed=0)
    assert isinstance(sched, PeriodicInterceptSchedule)
    assert isinstance(make_policy("scan-on-scan", dwell_steps=8), PeriodicInterceptSchedule)
    with pytest.raises(SmartScanError, match="positive"):
        PeriodicInterceptSchedule(dwell_steps=0)


def test_periodic_intercept_never_reads_occupancy() -> None:
    source = inspect.getsource(PeriodicInterceptSchedule.next_command)
    assert "occupied" not in source


def test_periodic_intercept_requires_dwell_bins() -> None:
    sched = PeriodicInterceptSchedule(dwell_steps=8)
    with pytest.raises(SmartScanError, match="dwell_bins"):
        sched.next_command(_view(dwell_bins=()))


def test_periodic_intercept_sweeps_unvisited_bands_first() -> None:
    sched = PeriodicInterceptSchedule(dwell_steps=8)
    bands: list[int] = []
    last_band: int | None = None
    for i in range(4):
        cmd = sched.next_command(
            _view(
                decision_index=i,
                step=i * 10,
                last_target_band=last_band,
                last_hit=False,
                last_decision_id=None if i == 0 else f"d{i - 1:05d}",
                last_end_step=None if i == 0 else i * 10,
            )
        )
        bands.append(int(cmd.target_band))
        last_band = int(cmd.target_band)
        assert cmd.dwell_steps == 2
    assert bands == [0, 1, 2, 3]


def test_periodic_intercept_finishes_search_even_after_hits() -> None:
    sched = PeriodicInterceptSchedule(dwell_steps=8)
    first = sched.next_command(_view(decision_index=0, step=0))
    assert first.target_band == 0
    second = sched.next_command(
        _view(
            decision_index=1,
            step=10,
            last_target_band=0,
            last_hit=True,
            last_decision_id="d00000",
            last_end_step=10,
        )
    )
    assert second.target_band == 1
    assert second.dwell_steps == 2


def test_periodic_intercept_stares_when_illumination_is_imminent() -> None:
    sched = PeriodicInterceptSchedule(dwell_steps=8)
    last_band: int | None = None
    last_id = None
    step = 0
    for i in range(4):
        cmd = sched.next_command(
            _view(
                decision_index=i,
                step=step,
                last_target_band=last_band,
                last_hit=False,
                last_decision_id=last_id,
                last_end_step=step if i else None,
            )
        )
        last_band = int(cmd.target_band)
        last_id = cmd.decision_id
        step += 10

    hit_ends = (50, 60, 70)
    for j, end in enumerate(hit_ends):
        cmd = sched.next_command(
            _view(
                decision_index=4 + j,
                step=end,
                last_target_band=2,
                last_hit=True,
                last_decision_id=f"hit{j}",
                last_end_step=end,
                settled_band=2,
            )
        )
        last_id = cmd.decision_id
        last_band = int(cmd.target_band)

    cmd = sched.next_command(
        _view(
            decision_index=10,
            step=72,
            last_target_band=last_band,
            last_hit=True,
            last_decision_id=last_id,
            last_end_step=70,
            settled_band=2,
        )
    )
    assert cmd.target_band == 2
    assert cmd.dwell_steps == 8


def test_periodic_no_history_uses_search_dwell() -> None:
    sched = PeriodicInterceptSchedule(dwell_steps=8, seed=0)
    cmd = sched.next_command(_view())
    assert cmd.target_band == 0
    assert cmd.dwell_steps == 2
    assert sched.last_mode == "search"
    assert sched.last_confidence is None


def test_periodic_one_hit_still_searches_unvisited() -> None:
    sched = PeriodicInterceptSchedule(dwell_steps=8, seed=0)
    sched.next_command(_view(decision_index=0, step=0))
    cmd = sched.next_command(
        _view(
            decision_index=1,
            step=10,
            last_target_band=0,
            last_hit=True,
            last_decision_id="d00000",
            last_end_step=10,
        )
    )
    assert cmd.target_band == 1
    assert cmd.dwell_steps == 2
    assert sched.last_mode == "search"


def test_periodic_insufficient_evidence_uses_lrv_fallback() -> None:
    sched = PeriodicInterceptSchedule(dwell_steps=8, seed=0)
    last_band: int | None = None
    last_id = None
    for i in range(4):
        cmd = sched.next_command(
            _view(
                decision_index=i,
                step=i * 10,
                last_target_band=last_band,
                last_hit=False,
                last_decision_id=last_id,
                last_end_step=None if i == 0 else i * 10,
            )
        )
        last_band = int(cmd.target_band)
        last_id = cmd.decision_id
    cmd = sched.next_command(
        _view(
            decision_index=4,
            step=40,
            last_target_band=last_band,
            last_hit=False,
            last_decision_id=last_id,
            last_end_step=40,
        )
    )
    assert cmd.dwell_steps == 2
    assert sched.last_mode == "fallback"
    assert 0 <= int(cmd.target_band) < 4


def test_periodic_irregular_misses_do_not_invent_period() -> None:
    sched = PeriodicInterceptSchedule(dwell_steps=8, seed=0)
    last_band: int | None = None
    last_id = None
    for i in range(4):
        cmd = sched.next_command(
            _view(
                decision_index=i,
                step=i * 7,
                last_target_band=last_band,
                last_hit=i == 0,
                last_decision_id=last_id,
                last_end_step=None if i == 0 else i * 7,
            )
        )
        last_band = int(cmd.target_band)
        last_id = cmd.decision_id
    cmd = sched.next_command(
        _view(
            decision_index=4,
            step=40,
            last_target_band=last_band,
            last_hit=False,
            last_decision_id=last_id,
            last_end_step=28,
        )
    )
    assert cmd.dwell_steps in {2, 8}
    assert sched.last_mode in {"fallback", "intercept", "search"}


def test_periodic_legal_dwell_and_seed_reproducible() -> None:
    a = PeriodicInterceptSchedule(dwell_steps=8, seed=3)
    b = PeriodicInterceptSchedule(dwell_steps=8, seed=3)
    seq_a: list[tuple[int, int]] = []
    seq_b: list[tuple[int, int]] = []
    last_a: int | None = None
    last_b: int | None = None
    id_a = None
    id_b = None
    for i in range(8):
        va = _view(
            decision_index=i,
            step=i * 10,
            last_target_band=last_a,
            last_hit=bool(i % 3 == 1),
            last_decision_id=id_a,
            last_end_step=None if i == 0 else i * 10,
            settled_band=last_a,
        )
        vb = _view(
            decision_index=i,
            step=i * 10,
            last_target_band=last_b,
            last_hit=bool(i % 3 == 1),
            last_decision_id=id_b,
            last_end_step=None if i == 0 else i * 10,
            settled_band=last_b,
        )
        ca = a.next_command(va)
        cb = b.next_command(vb)
        seq_a.append((int(ca.target_band), int(ca.dwell_steps)))
        seq_b.append((int(cb.target_band), int(cb.dwell_steps)))
        assert ca.dwell_steps in {2, 8}
        last_a, id_a = int(ca.target_band), ca.decision_id
        last_b, id_b = int(cb.target_band), cb.decision_id
    assert seq_a == seq_b


def test_periodic_staying_on_current_band_is_legal() -> None:
    sched = PeriodicInterceptSchedule(dwell_steps=8, seed=0)
    last_band: int | None = None
    last_id = None
    step = 0
    for i in range(4):
        cmd = sched.next_command(
            _view(
                decision_index=i,
                step=step,
                last_target_band=last_band,
                last_hit=False,
                last_decision_id=last_id,
                last_end_step=step if i else None,
            )
        )
        last_band = int(cmd.target_band)
        last_id = cmd.decision_id
        step += 10
    for j, end in enumerate((50, 60, 70)):
        cmd = sched.next_command(
            _view(
                decision_index=4 + j,
                step=end,
                last_target_band=2,
                last_hit=True,
                last_decision_id=f"hit{j}",
                last_end_step=end,
                settled_band=2,
            )
        )
        last_id = cmd.decision_id
        last_band = int(cmd.target_band)
    cmd = sched.next_command(
        _view(
            decision_index=10,
            step=72,
            last_target_band=last_band,
            last_hit=True,
            last_decision_id=last_id,
            last_end_step=70,
            settled_band=2,
        )
    )
    assert cmd.target_band == 2
    assert cmd.dwell_steps == 8
    assert sched.last_mode == "intercept"
    assert sched.last_period_s is not None
    assert sched.last_confidence is not None
    assert sched.last_phase_s is not None
