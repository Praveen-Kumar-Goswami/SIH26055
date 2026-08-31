from __future__ import annotations

import pytest

from smartscan.receiver.schedules import (
    FixedPrioritySchedule,
    ScheduleView,
    SequentialSchedule,
    UniformRandomSchedule,
    make_schedule,
)
from smartscan.types import SmartScanError


def _view(**kwargs: object) -> ScheduleView:
    payload: dict[str, object] = {
        "step": 0,
        "n_steps": 100,
        "n_bands": 16,
        "settled_band": None,
        "last_target_band": None,
        "dwell_bins": (1, 2, 4, 8, 16),
        "default_dwell_steps": 8,
        "decision_index": 0,
    }
    payload.update(kwargs)
    return ScheduleView(**payload)  # type: ignore[arg-type]


def test_sequential_cycles_without_truth() -> None:
    sched = SequentialSchedule(dwell_steps=8)
    bands = []
    last = None
    for i in range(20):
        cmd = sched.next_command(_view(decision_index=i, last_target_band=last))
        bands.append(cmd.target_band)
        last = cmd.target_band
        assert cmd.dwell_steps == 8
    assert bands[:16] == list(range(16))
    assert bands[16] == 0


def test_random_reproducible_and_independent_of_occupancy() -> None:
    a = UniformRandomSchedule(seed=3)
    b = UniformRandomSchedule(seed=3)
    c = UniformRandomSchedule(seed=4)
    seq_a = [a.next_command(_view(decision_index=i)).target_band for i in range(30)]
    seq_b = [b.next_command(_view(decision_index=i)).target_band for i in range(30)]
    seq_c = [c.next_command(_view(decision_index=i)).target_band for i in range(30)]
    assert seq_a == seq_b
    assert seq_a != seq_c
    assert set(seq_a) <= set(range(16))


def test_fixed_priority_uses_public_list_only() -> None:
    sched = FixedPrioritySchedule(band_order=(8, 4, 10), dwell_steps=4)
    bands = [
        sched.next_command(_view(decision_index=i)).target_band for i in range(6)
    ]
    assert bands == [8, 4, 10, 8, 4, 10]


def test_fixed_priority_rejects_illegal_band() -> None:
    sched = FixedPrioritySchedule(band_order=(99,), dwell_steps=1)
    with pytest.raises(SmartScanError, match="outside"):
        sched.next_command(_view())


def test_make_schedule() -> None:
    assert isinstance(make_schedule("sequential", dwell_steps=4), SequentialSchedule)
    assert isinstance(make_schedule("seq", dwell_steps=4), SequentialSchedule)
    assert isinstance(make_schedule("random", dwell_steps=4, schedule_seed=1), UniformRandomSchedule)
    assert isinstance(make_schedule("uniform", dwell_steps=4, schedule_seed=1), UniformRandomSchedule)
    fp = make_schedule("fixed-priority", dwell_steps=4, band_order=(1, 2))
    assert isinstance(fp, FixedPrioritySchedule)
    with pytest.raises(SmartScanError):
        make_schedule("fixed-priority", dwell_steps=4)
    with pytest.raises(SmartScanError, match="Unknown strategy"):
        make_schedule("oracle", dwell_steps=4)


def test_schedule_constructors_and_view_validation() -> None:
    with pytest.raises(SmartScanError, match="positive"):
        SequentialSchedule(dwell_steps=0)
    with pytest.raises(SmartScanError, match="nonempty"):
        FixedPrioritySchedule(band_order=(), dwell_steps=1)
    with pytest.raises(SmartScanError, match="positive"):
        FixedPrioritySchedule(band_order=(0,), dwell_steps=0)
    sched = SequentialSchedule(dwell_steps=1)
    with pytest.raises(SmartScanError, match="n_bands"):
        sched.next_command(_view(n_bands=0))
    with pytest.raises(SmartScanError, match="default_dwell_steps"):
        sched.next_command(_view(default_dwell_steps=0))
    random = UniformRandomSchedule(seed=0)
    with pytest.raises(SmartScanError, match="nonempty dwell_bins"):
        random.next_command(_view(dwell_bins=()))
