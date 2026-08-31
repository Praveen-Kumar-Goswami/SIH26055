"""Tuning/dwell state machine and schedule runner.

The physical simulator may read GroundTruth signal_power_w to synthesize
measurements. Policy-visible logs do not carry occupancy or emitter IDs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from smartscan.receiver.detector import (
    detect,
    equivalent_samples,
    load_receiver_config,
    measured_snr_db,
    noise_power_w,
    receiver_config_hash,
    sample_energy,
)
from smartscan.receiver.logs import DecisionLog, ObservationLog, ReceiverRun
from smartscan.receiver.schedules import Schedule, ScheduleView
from smartscan.seeding import spawn_generator
from smartscan.types import (
    SCHEMA_VERSION,
    DecisionRow,
    GroundTruth,
    ObservationRow,
    ReceiverConfig,
    ScanCommand,
    SmartScanError,
)


@dataclass
class CommandResult:
    """One physical command attempt. ``decision`` is None if the dwell was cut off."""

    observations: list[ObservationRow]
    decision: DecisionRow | None
    incomplete: bool
    step: int
    settled_band: int | None


@dataclass
class ReceiverEngine:
    """Step-able Stage 2 receiver. Reused by the Stage 5 Gymnasium wrapper."""

    truth: GroundTruth
    config: ReceiverConfig
    receiver_seed: int
    rng: np.random.Generator = field(init=False)
    noise: float = field(init=False)
    config_hash: str = field(init=False)
    widths: np.ndarray = field(init=False)
    step: int = 0
    settled_band: int | None = None
    last_target: int | None = None
    last_hit: bool | None = None
    last_measured_snr_db: float | None = None
    last_dwell_steps: int | None = None
    last_tune_cost_steps: int | None = None
    last_start_step: int | None = None
    last_end_step: int | None = None
    last_decision_id: str | None = None
    incomplete: int = 0

    def __post_init__(self) -> None:
        self.rng = spawn_generator(self.receiver_seed)
        self.noise = noise_power_w(self.config)
        self.config_hash = receiver_config_hash(self.config)
        self.widths = self.truth.band_plan.bandwidths_hz()
        _validate_config_against_truth(self.config, self.truth)

    @property
    def n_steps(self) -> int:
        return int(self.truth.n_steps)

    @property
    def n_bands(self) -> int:
        return int(self.truth.band_plan.n_bands)

    def remaining_steps(self) -> int:
        return max(0, self.n_steps - self.step)

    def done(self) -> bool:
        return self.step >= self.n_steps

    def schedule_view(self, decision_index: int, default_dwell_steps: int) -> ScheduleView:
        return ScheduleView(
            step=self.step,
            n_steps=self.n_steps,
            n_bands=self.n_bands,
            settled_band=self.settled_band,
            last_target_band=self.last_target,
            dwell_bins=self.config.dwell_bins,
            default_dwell_steps=default_dwell_steps,
            decision_index=decision_index,
            last_hit=self.last_hit,
            last_measured_snr_db=self.last_measured_snr_db,
            last_dwell_steps=self.last_dwell_steps,
            last_tune_cost_steps=self.last_tune_cost_steps,
            last_start_step=self.last_start_step,
            last_end_step=self.last_end_step,
            last_decision_id=self.last_decision_id,
            dt_s=float(self.truth.dt_s),
        )

    def execute_command(self, command: ScanCommand) -> CommandResult:
        """Advance through tuning plus the full dwell. Mutates engine state."""

        _validate_command(command, self.n_bands, self.widths, self.config)
        observations: list[ObservationRow] = []
        self.last_target = command.target_band
        start_step = self.step
        need_tune = self.settled_band is None or command.target_band != self.settled_band
        tune_cost = self.config.tune_latency_steps if need_tune else 0

        aborted = False
        for _ in range(tune_cost):
            if self.step >= self.n_steps:
                aborted = True
                break
            observations.append(
                ObservationRow(
                    step=self.step,
                    receiver_state="TUNING",
                    commanded_band=command.target_band,
                    tuned_band=None,
                    decision_id=command.decision_id,
                    dwell_progress=0,
                    integrated_energy=0.0,
                    measured_snr_db=None,
                    detection=False,
                )
            )
            self.step += 1
        if aborted or self.step >= self.n_steps:
            self.incomplete += 1
            return CommandResult(
                observations=observations,
                decision=None,
                incomplete=True,
                step=self.step,
                settled_band=self.settled_band,
            )

        tune_end_step = self.step
        rho_steps: list[float] = []
        completed_dwell = True
        last_obs: ObservationRow | None = None
        for dwell_i in range(command.dwell_steps):
            if self.step >= self.n_steps:
                completed_dwell = False
                break
            rho_n = float(self.truth.signal_power_w[self.step, command.target_band]) / self.noise
            if not np_finite_nonneg(rho_n):
                raise SmartScanError(
                    f"Non-finite rho at step {self.step} band {command.target_band}."
                )
            rho_steps.append(rho_n)
            is_last = dwell_i == command.dwell_steps - 1
            energy = 0.0
            snr_db = None
            hit = False
            if is_last:
                energy = sample_energy(
                    self.rng,
                    np.asarray(rho_steps, dtype=np.float64),
                    samples_per_step=self.config.samples_per_step,
                    dwell_steps=command.dwell_steps,
                )
                m_samples = equivalent_samples(self.config, command.dwell_steps)
                hit = detect(energy, m_samples, self.config.pfa_design)
                snr_db = measured_snr_db(energy, m_samples)
            last_obs = ObservationRow(
                step=self.step,
                receiver_state="DWELLING",
                commanded_band=command.target_band,
                tuned_band=command.target_band,
                decision_id=command.decision_id,
                dwell_progress=dwell_i + 1,
                integrated_energy=float(energy),
                measured_snr_db=snr_db,
                detection=hit,
            )
            observations.append(last_obs)
            self.step += 1

        if not completed_dwell or last_obs is None:
            self.incomplete += 1
            return CommandResult(
                observations=observations,
                decision=None,
                incomplete=True,
                step=self.step,
                settled_band=self.settled_band,
            )

        end_step = self.step
        dt = self.truth.dt_s
        decision = DecisionRow(
            decision_id=command.decision_id,
            start_step=start_step,
            tune_end_step=tune_end_step,
            dwell_end_step=end_step,
            end_step=end_step,
            target_band=command.target_band,
            dwell_steps=command.dwell_steps,
            hit=bool(last_obs.detection),
            measured_snr_db=last_obs.measured_snr_db,
            receiver_seed=self.receiver_seed,
            cost_tune_s=float(tune_cost) * dt,
            cost_time_s=float(end_step - start_step) * dt,
        )
        self.settled_band = command.target_band
        self.last_hit = bool(decision.hit)
        self.last_measured_snr_db = decision.measured_snr_db
        self.last_dwell_steps = int(decision.dwell_steps)
        self.last_tune_cost_steps = int(tune_cost)
        self.last_start_step = int(start_step)
        self.last_end_step = int(end_step)
        self.last_decision_id = command.decision_id
        return CommandResult(
            observations=observations,
            decision=decision,
            incomplete=False,
            step=self.step,
            settled_band=self.settled_band,
        )


def run_schedule(
    truth: GroundTruth,
    schedule: Schedule,
    config: ReceiverConfig | dict[str, object],
    receiver_seed: int,
    *,
    default_dwell_steps: int | None = None,
) -> ReceiverRun:
    """Apply any schedule to GroundTruth and return observation/decision logs."""

    cfg = load_receiver_config(config)
    engine = ReceiverEngine(truth=truth, config=cfg, receiver_seed=receiver_seed)
    dwell_default = default_dwell_steps or min(cfg.dwell_bins)
    observations: list[ObservationRow] = []
    decisions: list[DecisionRow] = []
    decision_index = 0

    while not engine.done():
        view = engine.schedule_view(decision_index, dwell_default)
        try:
            command = schedule.next_command(view)
        except StopIteration:
            break
        result = engine.execute_command(command)
        observations.extend(result.observations)
        if result.decision is not None:
            decisions.append(result.decision)
            decision_index += 1
        if result.incomplete:
            break

    obs_log = ObservationLog(
        rows=observations,
        ground_truth_fingerprint=truth.content_fingerprint,
        receiver_config_hash=engine.config_hash,
        schema_version=SCHEMA_VERSION,
        dt_s=truth.dt_s,
    )
    dec_log = DecisionLog(
        rows=decisions,
        ground_truth_fingerprint=truth.content_fingerprint,
        receiver_config_hash=engine.config_hash,
        schema_version=SCHEMA_VERSION,
        dt_s=truth.dt_s,
        receiver_seed=receiver_seed,
        n_incomplete_commands=engine.incomplete,
    )
    obs_log.validate()
    dec_log.validate()
    return ReceiverRun(observations=obs_log, decisions=dec_log)


def _validate_config_against_truth(config: ReceiverConfig, truth: GroundTruth) -> None:
    del truth
    ratio = config.scan_span_hz / config.receiver_ibw_hz
    if ratio < 10:
        raise SmartScanError(f"scan_span_hz/receiver_ibw_hz must be >= 10, got {ratio:.6g}.")


def _validate_command(
    command: ScanCommand,
    n_bands: int,
    widths: np.ndarray,
    config: ReceiverConfig,
) -> None:
    if command.target_band < 0 or command.target_band >= n_bands:
        raise SmartScanError(
            f"ScanCommand target_band={command.target_band} is outside 0..{n_bands - 1}."
        )
    if command.dwell_steps <= 0:
        raise SmartScanError("ScanCommand dwell_steps must be positive.")
    config.validate_ibw_for_band(float(widths[command.target_band]))


def np_finite_nonneg(value: float) -> bool:
    return bool(value == value and abs(value) != float("inf") and value >= 0.0)
