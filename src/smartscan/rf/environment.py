"""Scenario construction and GroundTruth simulation."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np

from smartscan.config import SimulateConfig, duration_to_steps
from smartscan.rf.bands import named_band_plan
from smartscan.rf.emitters import (
    CircularScanEmitter,
    ContinuousEmitter,
    Emitter,
    FrequencyAgileEmitter,
    OnOffGate,
    SectorScanEmitter,
    emitter_from_dict,
)
from smartscan.rf.events import combine_events, events_from_occupancy
from smartscan.seeding import spawn_generator
from smartscan.types import (
    GENERATOR_VERSION,
    SCHEMA_VERSION,
    BandPlan,
    EventTable,
    GroundTruth,
    Provenance,
    SmartScanError,
)

GHZ = 1e9
BUILTIN_SCENARIOS = ("sparse", "dense", "agile_threat", "edge_zero")


def simulate(config: SimulateConfig | dict[str, Any]) -> GroundTruth:
    if isinstance(config, dict):
        config = SimulateConfig.model_validate(config)
    band_plan = named_band_plan(config.band_plan_id)
    n_steps = duration_to_steps(config.duration_s, config.dt_s)
    rng = spawn_generator(config.seed)
    if config.emitters is not None:
        emitters = [emitter_from_dict(item) for item in config.emitters]
    else:
        emitters = build_builtin_scenario(
            config.scenario_id, n_steps=n_steps, band_plan=band_plan, dt_s=config.dt_s, rng=rng
        )
    _assert_unique_ids(emitters)
    return render_ground_truth(
        emitters=emitters,
        band_plan=band_plan,
        n_steps=n_steps,
        dt_s=config.dt_s,
        seed=config.seed,
        scenario_id=config.scenario_id,
        scenario_config=config.model_dump(),
    )


def render_ground_truth(
    *,
    emitters: Iterable[Emitter],
    band_plan: BandPlan,
    n_steps: int,
    dt_s: float,
    seed: int,
    scenario_id: str,
    scenario_config: dict[str, Any],
    provenance: Provenance | None = None,
) -> GroundTruth:
    emitter_list = list(emitters)
    occupied = np.zeros((n_steps, band_plan.n_bands), dtype=bool)
    power = np.zeros((n_steps, band_plan.n_bands), dtype=np.float64)
    event_groups = []
    for emitter in emitter_list:
        occ_i, pwr_i = emitter.render(n_steps, band_plan, dt_s)
        occupied |= occ_i
        power += pwr_i.astype(np.float64, copy=False)
        event_groups.append(events_from_occupancy(emitter=emitter, occupied=occ_i, n_steps=n_steps))
    if not np.all(np.isfinite(power)):
        raise SmartScanError("Combined signal_power_w is non-finite.")
    if np.any(power < 0):
        raise SmartScanError("Combined signal_power_w is negative.")
    events = combine_events(event_groups)
    truth = GroundTruth(
        dt_s=dt_s,
        n_steps=n_steps,
        band_plan=band_plan,
        occupied=occupied,
        signal_power_w=np.asarray(power, dtype=np.float32),
        events=events,
        provenance=provenance
        or Provenance(source="builtin_simulator", notes=[f"scenario_id={scenario_id}"]),
        content_fingerprint="",
        artifact_sha256=None,
        scenario_config=scenario_config,
        seed=seed,
        generator_version=GENERATOR_VERSION,
        schema_version=SCHEMA_VERSION,
    )
    truth.content_fingerprint = truth.compute_content_fingerprint()
    return truth


def ground_truth_from_arrays(
    *,
    occupied: np.ndarray,
    signal_power_w: np.ndarray,
    events: EventTable | list[Any],
    band_plan: BandPlan,
    dt_s: float,
    seed: int,
    scenario_id: str,
    scenario_config: dict[str, Any],
    provenance: Provenance,
) -> GroundTruth:
    n_steps = int(occupied.shape[0])
    table = events if isinstance(events, EventTable) else EventTable(events)
    truth = GroundTruth(
        dt_s=dt_s,
        n_steps=n_steps,
        band_plan=band_plan,
        occupied=np.asarray(occupied, dtype=bool),
        signal_power_w=np.asarray(signal_power_w, dtype=np.float32),
        events=table,
        provenance=provenance,
        content_fingerprint="",
        artifact_sha256=None,
        scenario_config=scenario_config,
        seed=seed,
        generator_version=GENERATOR_VERSION,
        schema_version=SCHEMA_VERSION,
    )
    truth.content_fingerprint = truth.compute_content_fingerprint()
    return truth


def build_builtin_scenario(
    scenario_id: str,
    *,
    n_steps: int,
    band_plan: BandPlan,
    dt_s: float,
    rng: np.random.Generator,
) -> list[Emitter]:
    if scenario_id == "edge_zero":
        return []
    if scenario_id == "sparse":
        return _sparse(band_plan, dt_s, rng)
    if scenario_id == "dense":
        return _dense(band_plan, dt_s, rng)
    if scenario_id == "agile_threat":
        return _agile_threat(n_steps, band_plan, dt_s, rng)
    if scenario_id == "random":
        return sample_random_scenario(band_plan, dt_s, rng)
    raise SmartScanError(
        f"Unknown scenario_id {scenario_id!r}. Built-ins: {', '.join(BUILTIN_SCENARIOS)}."
    )


def sample_random_scenario(
    band_plan: BandPlan,
    dt_s: float,
    rng: np.random.Generator,
) -> list[Emitter]:
    """Bounded, validated random mix. Uses only the provided Generator."""

    n_cont = int(rng.integers(0, 3))
    n_circ = int(rng.integers(0, 3))
    n_sec = int(rng.integers(0, 2))
    n_agile = int(rng.integers(0, 2))
    emitters: list[Emitter] = []
    edges = np.asarray(band_plan.band_edges_hz)
    for i in range(n_cont):
        band = int(rng.integers(0, band_plan.n_bands))
        freq = 0.5 * (edges[band] + edges[band + 1])
        emitters.append(
            ContinuousEmitter(
                emitter_id=f"rnd_cont_{i}",
                frequency_hz=float(freq),
                power_w=float(10 ** rng.uniform(-14, -11)),
            )
        )
    for i in range(n_circ):
        band = int(rng.integers(0, band_plan.n_bands))
        freq = 0.5 * (edges[band] + edges[band + 1])
        period = float(rng.choice([0.25, 0.5, 1.0]))
        emitters.append(
            CircularScanEmitter(
                emitter_id=f"rnd_circ_{i}",
                frequency_hz=float(freq),
                power_w=float(10 ** rng.uniform(-14, -11)),
                scan_period_s=period,
                beamwidth_deg=float(rng.uniform(10.0, 40.0)),
                phase0_steps=int(rng.integers(0, max(1, int(round(period / dt_s))))),
            )
        )
    for i in range(n_sec):
        band = int(rng.integers(0, band_plan.n_bands))
        freq = 0.5 * (edges[band] + edges[band + 1])
        emitters.append(
            SectorScanEmitter(
                emitter_id=f"rnd_sec_{i}",
                frequency_hz=float(freq),
                power_w=float(10 ** rng.uniform(-14, -11)),
                scan_period_s=1.0,
                theta_min_deg=-30.0,
                theta_max_deg=30.0,
                beamwidth_deg=12.0,
                receiver_azimuth_deg=0.0,
                initial_direction=1 if rng.random() < 0.5 else -1,
            )
        )
    for i in range(n_agile):
        bands = rng.choice(band_plan.n_bands, size=3, replace=False)
        freqs = tuple(float(0.5 * (edges[b] + edges[b + 1])) for b in bands)
        emitters.append(
            FrequencyAgileEmitter(
                emitter_id=f"rnd_agile_{i}",
                hop_frequencies_hz=freqs,
                dwell_steps=int(rng.choice([8, 16, 32])),
                power_w=float(10 ** rng.uniform(-14, -11)),
                phase_offset=int(rng.integers(0, 8)),
            )
        )
    return emitters


def _center_hz(band_plan: BandPlan, band: int) -> float:
    if band < 0 or band >= band_plan.n_bands:
        raise SmartScanError(f"Band index {band} is outside {band_plan.profile_id}.")
    edges = band_plan.band_edges_hz
    return 0.5 * (edges[band] + edges[band + 1])


def _phase(rng: np.random.Generator, period_s: float, dt_s: float) -> int:
    period_steps = max(1, int(round(period_s / dt_s)))
    return int(rng.integers(0, period_steps))


def _sparse(band_plan: BandPlan, dt_s: float, rng: np.random.Generator) -> list[Emitter]:
    # Two emitters on well-separated bands: low spatial overlap.
    return [
        ContinuousEmitter(
            emitter_id="cont_10ghz",
            frequency_hz=_center_hz(band_plan, min(8, band_plan.n_bands - 1)),
            power_w=1.0e-12,
        ),
        CircularScanEmitter(
            emitter_id="circ_6ghz",
            frequency_hz=_center_hz(band_plan, min(4, band_plan.n_bands - 1)),
            power_w=2.0e-12,
            scan_period_s=0.5,
            beamwidth_deg=36.0,
            receiver_azimuth_deg=0.0,
            phase0_steps=_phase(rng, 0.5, dt_s),
        ),
    ]


def _dense(band_plan: BandPlan, dt_s: float, rng: np.random.Generator) -> list[Emitter]:
    overlap_band = min(2, band_plan.n_bands - 1)
    hops = tuple(
        _center_hz(band_plan, b)
        for b in (3, 5, 7, min(9, band_plan.n_bands - 1))
        if b < band_plan.n_bands
    )
    return [
        ContinuousEmitter(
            emitter_id="cont_overlap",
            frequency_hz=_center_hz(band_plan, overlap_band),
            power_w=1.0e-12,
            gate=OnOffGate(kind="periodic", period_steps=200, on_steps=150, phase_offset=0),
        ),
        CircularScanEmitter(
            emitter_id="circ_overlap",
            frequency_hz=_center_hz(band_plan, overlap_band),
            power_w=3.0e-12,
            scan_period_s=0.4,
            beamwidth_deg=40.0,
            phase0_steps=_phase(rng, 0.4, dt_s),
        ),
        SectorScanEmitter(
            emitter_id="sector_8ghz",
            frequency_hz=_center_hz(band_plan, min(6, band_plan.n_bands - 1)),
            power_w=5.0e-13,
            scan_period_s=1.0,
            theta_min_deg=-20.0,
            theta_max_deg=20.0,
            beamwidth_deg=10.0,
            receiver_azimuth_deg=0.0,
            phase0_steps=_phase(rng, 1.0, dt_s),
            initial_direction=1,
        ),
        FrequencyAgileEmitter(
            emitter_id="agile_hops",
            hop_frequencies_hz=hops,
            dwell_steps=50,
            power_w=8.0e-13,
            phase_offset=int(rng.integers(0, 4)),
        ),
    ]


def _agile_threat(
    n_steps: int, band_plan: BandPlan, dt_s: float, rng: np.random.Generator
) -> list[Emitter]:
    late_start = n_steps // 2
    hops = tuple(
        _center_hz(band_plan, b)
        for b in (1, 4, 8, min(12, band_plan.n_bands - 1))
        if b < band_plan.n_bands
    )
    return [
        CircularScanEmitter(
            emitter_id="scan_periodic",
            frequency_hz=_center_hz(band_plan, min(3, band_plan.n_bands - 1)),
            power_w=2.0e-12,
            scan_period_s=0.2,
            beamwidth_deg=24.0,
            phase0_steps=_phase(rng, 0.2, dt_s),
            threat_weight=1.0,
        ),
        FrequencyAgileEmitter(
            emitter_id="hopper",
            hop_frequencies_hz=hops,
            dwell_steps=25,
            power_w=1.5e-12,
            phase_offset=int(rng.integers(0, 4)),
            threat_weight=0.5,
        ),
        ContinuousEmitter(
            emitter_id="late_unseen",
            frequency_hz=_center_hz(band_plan, min(10, band_plan.n_bands - 1)),
            power_w=4.0e-12,
            start_step=late_start,
            threat_weight=5.0,
        ),
        SectorScanEmitter(
            emitter_id="sector_watch",
            frequency_hz=_center_hz(band_plan, min(7, band_plan.n_bands - 1)),
            power_w=9.0e-13,
            scan_period_s=0.8,
            theta_min_deg=-45.0,
            theta_max_deg=45.0,
            beamwidth_deg=15.0,
            phase0_steps=_phase(rng, 0.8, dt_s),
            initial_direction=-1,
            threat_weight=1.0,
        ),
    ]


def _assert_unique_ids(emitters: list[Emitter]) -> None:
    seen: set[str] = set()
    for emitter in emitters:
        if emitter.emitter_id in seen:
            raise SmartScanError(f"Conflicting emitter_id {emitter.emitter_id!r}.")
        seen.add(emitter.emitter_id)


def per_band_activity(occupied: np.ndarray) -> list[dict[str, Any]]:
    n_steps, n_bands = occupied.shape
    rows = []
    for band in range(n_bands):
        count = int(occupied[:, band].sum())
        rows.append({"band": band, "occupied_steps": count, "occupied_fraction": count / max(n_steps, 1)})
    return rows
