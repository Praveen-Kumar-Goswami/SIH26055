"""Training-data construction from completed hit/miss commands.

Splits are by complete (scenario, seed), never by row.
Unvisited bands are masked, never used as negative q_hit labels.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from smartscan.config import SimulateConfig, TrainConfig, load_yaml, project_root
from smartscan.ml.features import FeatureBuilder, feature_schema
from smartscan.ml.observable import ObservableTransition, transition_from_decision
from smartscan.receiver.detector import load_receiver_config, receiver_config_hash
from smartscan.receiver.logs import DecisionLog
from smartscan.receiver.scanner import run_schedule
from smartscan.receiver.schedules import make_schedule
from smartscan.rf.environment import simulate
from smartscan.types import (
    ReceiverConfig,
    SmartScanError,
    content_fingerprint,
    sha256_bytes,
    strip_volatile,
)


@dataclass
class SupervisedRow:
    features: np.ndarray
    band: int
    dwell_steps: int
    q_hit: float
    event_index: int | None
    future_bands: list[int]
    future_dwells: list[int]
    scenario_id: str
    seed: int
    source_strategy: str
    decision_id: str
    split: str


@dataclass
class DatasetManifest:
    schema_version: str
    n_rows: int
    n_train: int
    n_val: int
    n_test: int
    split_ids: dict[str, list[str]]
    feature_schema: dict[str, object]
    source_run_keys: list[str]
    content_fingerprint: str
    artifact_sha256: str | None = None
    row_counts_by_family: dict[str, int] = field(default_factory=dict)


def split_key(scenario_id: str, seed: int) -> str:
    return f"{scenario_id}::{int(seed)}"


def assign_split(key: str, train_keys: set[str], val_keys: set[str], test_keys: set[str]) -> str:
    if key in train_keys:
        return "train"
    if key in val_keys:
        return "val"
    if key in test_keys:
        return "test"
    raise SmartScanError(f"Scenario/seed {key} is not in the frozen split lists.")


def survival_label(
    rows: list[ObservableTransition],
    origin: int,
    *,
    horizon_steps: int,
    n_bins: int,
) -> int | None:
    """First future completed hit command index, or None if right-censored."""

    origin_row = rows[origin]
    horizon_end = int(origin_row.start_step) + int(horizon_steps)
    future = rows[origin + 1 : origin + 1 + n_bins]
    for j, item in enumerate(future):
        if item.end_step > horizon_end:
            return None
        if item.hit:
            return j
    return None


def rows_from_decisions(
    log: DecisionLog,
    *,
    n_steps: int,
    n_bands: int,
    dt_s: float,
    dwell_bins: tuple[int, ...],
    horizon_steps: int,
    n_bins: int,
    scenario_id: str,
    seed: int,
    strategy: str,
    split: str,
    ewma_alpha: float,
    tune_latency_steps: int,
    public_priorities: dict[int, float],
) -> list[SupervisedRow]:
    history: list[ObservableTransition] = []
    settled: int | None = None
    last_target: int | None = None
    out: list[SupervisedRow] = []
    transitions: list[ObservableTransition] = []
    for row in log.rows:
        tr = transition_from_decision(
            row,
            n_steps=n_steps,
            n_bands=n_bands,
            dt_s=dt_s,
            settled_band_before=settled,
            last_target_band=last_target,
        )
        transitions.append(tr)
        settled = int(row.target_band)
        last_target = int(row.target_band)

    builder = FeatureBuilder(
        n_bands=n_bands,
        dt_s=dt_s,
        dwell_bins=dwell_bins,
        ewma_alpha=ewma_alpha,
        tune_latency_steps=tune_latency_steps,
        public_priorities=public_priorities,
    )
    last_dwell: int | None = None
    for i, tr in enumerate(transitions):
        features = builder.vector(
            step=tr.start_step,
            n_steps=n_steps,
            settled_band=tr.settled_band_before,
            last_target_band=tr.last_target_band,
            last_dwell_steps=last_dwell,
        )
        event_index = survival_label(transitions, i, horizon_steps=horizon_steps, n_bins=n_bins)
        future = transitions[i + 1 : i + 1 + n_bins]
        out.append(
            SupervisedRow(
                features=features,
                band=tr.target_band,
                dwell_steps=tr.dwell_steps,
                q_hit=1.0 if tr.hit else 0.0,
                event_index=event_index,
                future_bands=[item.target_band for item in future],
                future_dwells=[item.dwell_steps for item in future],
                scenario_id=scenario_id,
                seed=seed,
                source_strategy=strategy,
                decision_id=tr.decision_id,
                split=split,
            )
        )
        builder.observe(tr)
        last_dwell = tr.dwell_steps
        history.append(tr)
    return out


def _receiver_from_train(cfg: TrainConfig) -> ReceiverConfig:
    payload = load_yaml(project_root() / cfg.receiver_config)
    payload = dict(payload)
    payload["dwell_bins"] = list(cfg.dwell_bins)
    payload["noise_power_w"] = float(cfg.noise_power_w)
    return load_receiver_config(payload)


def collect_exploration(
    cfg: TrainConfig,
    *,
    persist_fn: Any | None = None,
) -> tuple[list[SupervisedRow], DatasetManifest]:
    """Generate exploration logs over frozen train/val/test scenario+seed lists."""

    receiver = _receiver_from_train(cfg)
    dwell_bins = tuple(int(x) for x in cfg.dwell_bins)
    public = {int(b): 2.0 for b in cfg.public_priorities}
    train_keys = {split_key(item.scenario_id, seed) for item in cfg.train_scenarios for seed in item.seeds}
    val_keys = {split_key(item.scenario_id, seed) for item in cfg.val_scenarios for seed in item.seeds}
    test_keys = {split_key(item.scenario_id, seed) for item in cfg.test_scenarios for seed in item.seeds}
    all_specs: list[tuple[str, int, str]] = []
    for item in cfg.train_scenarios:
        for seed in item.seeds:
            all_specs.append((item.scenario_id, int(seed), "train"))
    for item in cfg.val_scenarios:
        for seed in item.seeds:
            all_specs.append((item.scenario_id, int(seed), "val"))
    for item in cfg.test_scenarios:
        for seed in item.seeds:
            all_specs.append((item.scenario_id, int(seed), "test"))
    if not all_specs:
        raise SmartScanError("TrainConfig has no scenario/seed split entries.")

    rows: list[SupervisedRow] = []
    source_keys: list[str] = []
    family_counts: dict[str, int] = {}
    from smartscan.ml.policies import make_policy

    for scenario_id, seed, split in all_specs:
        sim = SimulateConfig(
            seed=seed,
            dt_s=cfg.dt_s,
            duration_s=cfg.duration_s,
            band_plan_id=cfg.band_plan_id,
            scenario_id=scenario_id,
        )
        truth = simulate(sim)
        for strategy in cfg.collect_strategies:
            schedule: Any
            try:
                schedule = make_schedule(
                    strategy,
                    dwell_steps=cfg.default_dwell_steps,
                    schedule_seed=seed,
                    band_order=tuple(cfg.public_priorities),
                )
            except SmartScanError:
                schedule = make_policy(
                    strategy,
                    dwell_steps=cfg.default_dwell_steps,
                    schedule_seed=seed,
                    band_order=tuple(cfg.public_priorities),
                    n_bands=truth.band_plan.n_bands,
                    dwell_bins=dwell_bins,
                )
            run = run_schedule(
                truth,
                schedule,
                receiver,
                receiver_seed=seed,
                default_dwell_steps=cfg.default_dwell_steps,
            )
            key = f"{scenario_id}:{seed}:{strategy}"
            source_keys.append(key)
            part = rows_from_decisions(
                run.decisions,
                n_steps=truth.n_steps,
                n_bands=truth.band_plan.n_bands,
                dt_s=truth.dt_s,
                dwell_bins=dwell_bins,
                horizon_steps=cfg.horizon_steps,
                n_bins=cfg.forecast_command_bins,
                scenario_id=scenario_id,
                seed=seed,
                strategy=strategy,
                split=split,
                ewma_alpha=cfg.ewma_alpha,
                tune_latency_steps=receiver.tune_latency_steps,
                public_priorities=public,
            )
            rows.extend(part)
            family_counts[scenario_id] = family_counts.get(scenario_id, 0) + len(part)
            if persist_fn is not None:
                persist_fn(truth, run, strategy, seed)

    n_train = sum(1 for row in rows if row.split == "train")
    n_val = sum(1 for row in rows if row.split == "val")
    n_test = sum(1 for row in rows if row.split == "test")
    schema = feature_schema(receiver_config_n_bands(receiver, cfg), dwell_bins)
    payload = {
        "schema_version": "1.0.0",
        "n_rows": len(rows),
        "split_ids": {
            "train": sorted(train_keys),
            "val": sorted(val_keys),
            "test": sorted(test_keys),
        },
        "feature_schema": schema,
        "source_run_keys": source_keys,
        "row_counts_by_family": family_counts,
        "train_config": strip_volatile(cfg.model_dump()),
        "receiver_config_hash": receiver_config_hash(receiver),
    }
    digest = content_fingerprint(payload)
    manifest = DatasetManifest(
        schema_version="1.0.0",
        n_rows=len(rows),
        n_train=n_train,
        n_val=n_val,
        n_test=n_test,
        split_ids={
            "train": sorted(train_keys),
            "val": sorted(val_keys),
            "test": sorted(test_keys),
        },
        feature_schema=schema,
        source_run_keys=source_keys,
        content_fingerprint=digest,
        row_counts_by_family=family_counts,
    )
    return rows, manifest


def receiver_config_n_bands(receiver: ReceiverConfig, cfg: TrainConfig) -> int:
    from smartscan.rf.bands import named_band_plan

    del receiver
    return named_band_plan(cfg.band_plan_id).n_bands


def save_dataset(
    rows: list[SupervisedRow],
    manifest: DatasetManifest,
    directory: str | Path,
) -> DatasetManifest:
    dest = Path(directory)
    dest.mkdir(parents=True, exist_ok=True)
    features = np.stack([row.features for row in rows], axis=0) if rows else np.zeros((0, 1), np.float32)
    q_hit = np.asarray([row.q_hit for row in rows], dtype=np.float32)
    bands = np.asarray([row.band for row in rows], dtype=np.int32)
    dwells = np.asarray([row.dwell_steps for row in rows], dtype=np.int32)
    event = np.asarray(
        [-1 if row.event_index is None else int(row.event_index) for row in rows], dtype=np.int32
    )
    meta = [
        {
            "scenario_id": row.scenario_id,
            "seed": row.seed,
            "source_strategy": row.source_strategy,
            "decision_id": row.decision_id,
            "split": row.split,
            "future_bands": row.future_bands,
            "future_dwells": row.future_dwells,
        }
        for row in rows
    ]
    np.savez_compressed(
        dest / "dataset.npz",
        features=features,
        q_hit=q_hit,
        bands=bands,
        dwells=dwells,
        event_index=event,
        meta_utf8=np.frombuffer(json.dumps(meta, sort_keys=True).encode("utf-8"), dtype=np.uint8),
    )
    man_path = dest / "manifest.json"
    blob = json.dumps(
        {
            "schema_version": manifest.schema_version,
            "n_rows": manifest.n_rows,
            "n_train": manifest.n_train,
            "n_val": manifest.n_val,
            "n_test": manifest.n_test,
            "split_ids": manifest.split_ids,
            "feature_schema": manifest.feature_schema,
            "source_run_keys": manifest.source_run_keys,
            "content_fingerprint": manifest.content_fingerprint,
            "row_counts_by_family": manifest.row_counts_by_family,
        },
        sort_keys=True,
        indent=2,
    ).encode("utf-8")
    man_path.write_bytes(blob)
    manifest.artifact_sha256 = sha256_bytes((dest / "dataset.npz").read_bytes())
    extra = json.loads(blob)
    extra["artifact_sha256"] = manifest.artifact_sha256
    man_path.write_text(json.dumps(extra, sort_keys=True, indent=2), encoding="utf-8")
    return manifest
