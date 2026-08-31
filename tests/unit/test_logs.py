from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from smartscan.receiver.logs import (
    DecisionLog,
    ObservationLog,
    diagnostic_counts,
    load_receiver_run,
    save_receiver_run,
)
from smartscan.receiver.scanner import run_schedule
from smartscan.receiver.schedules import ScheduleView
from smartscan.rf.bands import named_band_plan
from smartscan.rf.emitters import ContinuousEmitter
from smartscan.rf.environment import render_ground_truth
from smartscan.types import (
    DecisionRow,
    ObservationRow,
    ReceiverConfig,
    ScanCommand,
    SmartScanError,
)


class _Scripted:
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


def _quiet(n_steps: int):
    return render_ground_truth(
        emitters=[],
        band_plan=named_band_plan("demo_2_18"),
        n_steps=n_steps,
        dt_s=0.001,
        seed=0,
        scenario_id="rx_fixture",
        scenario_config={"scenario_id": "rx_fixture", "n_steps": n_steps},
    )


def _obs(step: int, **kwargs: object) -> ObservationRow:
    payload: dict[str, object] = {
        "step": step,
        "receiver_state": "DWELLING",
        "commanded_band": 0,
        "tuned_band": 0,
        "decision_id": "d00000",
        "dwell_progress": 1,
        "integrated_energy": 0.0,
        "measured_snr_db": None,
        "detection": False,
    }
    payload.update(kwargs)
    return ObservationRow.model_validate(payload)


def _dec(**kwargs: object) -> DecisionRow:
    payload: dict[str, object] = {
        "decision_id": "d00000",
        "start_step": 0,
        "tune_end_step": 1,
        "dwell_end_step": 3,
        "end_step": 3,
        "target_band": 0,
        "dwell_steps": 2,
        "hit": False,
    }
    payload.update(kwargs)
    return DecisionRow.model_validate(payload)


def test_observation_steps_must_increase() -> None:
    log = ObservationLog(
        rows=[_obs(1), _obs(1)],
        ground_truth_fingerprint="a",
        receiver_config_hash="b",
    )
    with pytest.raises(SmartScanError, match="strictly increasing"):
        log.validate()


def test_decision_log_validation() -> None:
    base = dict(
        ground_truth_fingerprint="a",
        receiver_config_hash="b",
    )
    with pytest.raises(SmartScanError, match="Duplicate"):
        DecisionLog(rows=[_dec(), _dec()], **base).validate()
    with pytest.raises(SmartScanError, match="empty interval"):
        DecisionLog(rows=[_dec(end_step=0, dwell_end_step=0, dwell_steps=0)], **base).validate()
    with pytest.raises(SmartScanError, match="tune_end_step"):
        DecisionLog(rows=[_dec(tune_end_step=4)], **base).validate()
    with pytest.raises(SmartScanError, match="nondecreasing"):
        DecisionLog(
            rows=[
                _dec(
                    decision_id="a",
                    end_step=5,
                    dwell_end_step=5,
                    start_step=0,
                    tune_end_step=1,
                    dwell_steps=4,
                ),
                _dec(
                    decision_id="b",
                    end_step=3,
                    dwell_end_step=3,
                    start_step=0,
                    tune_end_step=1,
                    dwell_steps=2,
                ),
            ],
            **base,
        ).validate()
    with pytest.raises(SmartScanError, match="usable dwell"):
        DecisionLog(rows=[_dec(dwell_steps=9)], **base).validate()


def test_save_replaces_stale_writing_file(tmp_path: Path) -> None:
    truth = _quiet(8)
    run = run_schedule(truth, _Scripted([(0, 2)]), _cfg(), receiver_seed=0)
    dest = tmp_path / "logs.npz"
    stale = dest.with_name(dest.stem + ".writing.npz")
    stale.write_bytes(b"stale")
    save_receiver_run(run, dest)
    loaded = load_receiver_run(dest)
    assert len(loaded.decisions.rows) == 1


def test_load_missing_file_and_key(tmp_path: Path) -> None:
    missing = tmp_path / "nope.npz"
    with pytest.raises(SmartScanError, match="not found"):
        load_receiver_run(missing)
    broken = tmp_path / "broken.npz"
    np.savez_compressed(broken, meta_utf8=np.frombuffer(b"{}", dtype=np.uint8))
    with pytest.raises(SmartScanError, match="missing"):
        load_receiver_run(broken)


def test_diagnostic_join_hits_misses_and_false_alarms() -> None:
    plan = named_band_plan("demo_2_18")
    emitter = ContinuousEmitter(emitter_id="c", frequency_hz=10.5e9, power_w=80.0)
    occupied = render_ground_truth(
        emitters=[emitter],
        band_plan=plan,
        n_steps=12,
        dt_s=0.001,
        seed=0,
        scenario_id="hot",
        scenario_config={"scenario_id": "hot"},
    )
    quiet = _quiet(12)
    cfg = ReceiverConfig(
        receiver_ibw_hz=1e8,
        scan_span_hz=16e9,
        tune_latency_steps=0,
        pfa_design=0.2,
        noise_power_w=1.0,
    )
    hot_run = run_schedule(occupied, _Scripted([(8, 4)]), cfg, receiver_seed=0)
    quiet_run = run_schedule(quiet, _Scripted([(0, 4)]), cfg, receiver_seed=1)
    hot_run.decisions.rows[0].hit = True
    quiet_run.decisions.rows[0].hit = True
    hot = diagnostic_counts(occupied, hot_run)
    cold = diagnostic_counts(quiet, quiet_run)
    assert hot["hits"] >= 1
    assert cold["false_alarms"] >= 1
    with pytest.raises(SmartScanError, match="fingerprint"):
        diagnostic_counts(quiet, hot_run)
