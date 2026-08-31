"""Offline ML improvement cycle. Train/val only until the model is frozen.

Never reads configs/held_out_manifest.json or seeds 1000–1029 during development.
"""

from __future__ import annotations

import json
import time
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np

from smartscan.config import TrainConfig, load_yaml, project_root
from smartscan.ml.protocol import (
    assert_disjoint_protocol,
    file_sha256,
    fresh_manifest_path,
    fresh_v4_manifest_path,
    write_fresh_test_manifest,
    write_fresh_test_v4_manifest,
)
from smartscan.types import SmartScanError, content_fingerprint

IMPROVE_DIR = Path("artifacts") / "ml_improve"
V2_BUNDLE = Path("artifacts") / "models" / "scheduler_full"
V3_BUNDLE = Path("artifacts") / "models" / "scheduler_v3"
V4_BUNDLE = Path("artifacts") / "models" / "scheduler_v4"

HPO_TRIALS: tuple[dict[str, Any], ...] = (
    {"name": "discrete_ent002", "action_layout": "discrete", "ppo_ent_coef": 0.02, "curriculum": False},
    {"name": "multidiscrete_ent002", "action_layout": "multidiscrete", "ppo_ent_coef": 0.02, "curriculum": False},
    {"name": "discrete_curriculum", "action_layout": "discrete", "ppo_ent_coef": 0.02, "curriculum": True},
)

CURRICULUM_FAMILIES = [
    ["sparse"],
    ["sparse", "dense"],
    ["sparse", "dense", "random"],
    ["sparse", "dense", "random", "agile_threat"],
]
CURRICULUM_BOUNDARIES = [6, 12, 18]


def _root() -> Path:
    return project_root()


def load_improve_config(path: Path | None = None) -> TrainConfig:
    cfg_path = path or (_root() / "configs" / "train_improve.yaml")
    cfg = TrainConfig.model_validate(load_yaml(cfg_path))
    assert_disjoint_protocol(cfg)
    return cfg


def load_v4_config(path: Path | None = None) -> TrainConfig:
    cfg_path = path or (_root() / "configs" / "train_v4.yaml")
    cfg = TrainConfig.model_validate(load_yaml(cfg_path))
    assert_disjoint_protocol(cfg)
    return cfg


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _track(experiment: str, *, params: dict[str, str], metrics: dict[str, float], tags: dict[str, str], artifacts: list[Path] | None = None) -> str | None:
    from smartscan.storage.constants import EXPERIMENT_ML_IMPROVE
    from smartscan.storage.db import StorageSettings
    from smartscan.storage.pipeline import build_repository
    from smartscan.storage.tracking import TrackingPayload

    del experiment
    settings = StorageSettings.from_env()
    repo = build_repository(settings, track=True, upgrade=True)
    payload = TrackingPayload(
        domain_run_id=uuid4(),
        experiment=EXPERIMENT_ML_IMPROVE,
        params=params,
        metrics={k: float(v) for k, v in metrics.items() if v == v},
        tags=tags,
        artifact_files=artifacts or [],
    )
    return repo.tracker.log_run(payload)


def _feature_builder_factory(cfg: TrainConfig) -> Any:
    from smartscan.ml.features import FeatureBuilder
    from smartscan.receiver.detector import load_receiver_config
    from smartscan.rf.bands import named_band_plan

    plan = named_band_plan(cfg.band_plan_id)
    rec_payload = dict(load_yaml(_root() / cfg.receiver_config))
    rec_payload["dwell_bins"] = list(cfg.dwell_bins)
    rec_payload["noise_power_w"] = float(cfg.noise_power_w)
    receiver = load_receiver_config(rec_payload)

    def _factory() -> FeatureBuilder:
        return FeatureBuilder(
            n_bands=plan.n_bands,
            dt_s=cfg.dt_s,
            dwell_bins=tuple(int(x) for x in cfg.dwell_bins),
            ewma_alpha=cfg.ewma_alpha,
            tune_latency_steps=receiver.tune_latency_steps,
            public_priorities={int(b): 2.0 for b in cfg.public_priorities},
        )

    return _factory


def run_diagnostics(cfg: TrainConfig, dest: Path, *, track: bool = False) -> dict[str, Any]:
    from smartscan.ml.bundle import load_bundle, ppo_predict_fn
    from smartscan.ml.diagnose import diagnose_split
    from smartscan.ml.predictor import BuilderBackedHazardPredictor

    v2_predict = None
    v2_predictor = None
    v2_factory = None
    v2_dir = _root() / V2_BUNDLE
    if v2_dir.is_dir():
        bundle = load_bundle(v2_dir)
        v2_predict = ppo_predict_fn(bundle)
        if bundle.predictor is not None:
            v2_predictor = BuilderBackedHazardPredictor(bundle.predictor)
        v2_factory = _feature_builder_factory(cfg)
    diag_cfg = cfg.model_copy(
        update={
            "include_predictor_obs": False,
            "include_neural_predictor_obs": False,
            "include_action_history": 0,
        }
    )
    payload: dict[str, Any] = {
        "protocol": assert_disjoint_protocol(cfg),
        "note": (
            "Diagnostics use the improvement TRAIN/VAL splits only. "
            "Held-out 1000–1029 unused. PPO here is historical SmartScanScheduler v2 "
            "with its original 309-d observation (no v3 extras)."
        ),
        "v2_bundle_present": v2_dir.is_dir(),
    }
    for split in ("train", "val"):
        payload[split] = diagnose_split(
            diag_cfg,
            split=split,
            ppo_predict=v2_predict,
            feature_builder_factory=v2_factory,
            predictor=v2_predictor,
        )
    _write_json(dest / "diagnostics.json", payload)
    if track:
        payload["mlflow_run_id"] = _track(
            "diagnose",
            params={"phase": "diagnose", "seed": str(cfg.seed)},
            metrics={
                "val_fixed_priority_air": float(
                    (((payload.get("val") or {}).get("strategies") or {}).get("fixed-priority") or {}).get(
                        "mean_air"
                    )
                    or 0.0
                )
            },
            tags={"phase": "diagnose", "kind": "ml-improve"},
            artifacts=[dest / "diagnostics.json"],
        )
    return payload


def run_predictor_study(cfg: TrainConfig, dest: Path, *, track: bool = False) -> dict[str, Any]:
    from smartscan.ml.dataset import collect_exploration
    from smartscan.ml.train import train_predictor
    from smartscan.rf.bands import named_band_plan

    rows, manifest = collect_exploration(cfg)
    n_bands = named_band_plan(cfg.band_plan_id).n_bands
    results: dict[str, Any] = {
        "dataset_fingerprint": manifest.content_fingerprint,
        "n_rows": manifest.n_rows,
        "architectures": {},
    }
    for arch in ("mlp", "residual_ln"):
        trial_cfg = cfg.model_copy(update={"predictor_arch": arch})
        _pred, _hit, _act, metrics = train_predictor(rows, trial_cfg, n_bands=n_bands)
        results["architectures"][arch] = dict(metrics)
        if track:
            run_id = _track(
                "predictor",
                params={"phase": "predictor", "arch": arch, "seed": str(cfg.seed)},
                metrics={k: float(v) for k, v in metrics.items() if isinstance(v, (int, float))},
                tags={"phase": "predictor", "arch": arch},
            )
            results["architectures"][arch]["mlflow_run_id"] = run_id
        del _pred, _hit, _act
    mlp_brier = float(results["architectures"]["mlp"].get("val_brier_cal") or 1.0)
    res_brier = float(results["architectures"]["residual_ln"].get("val_brier_cal") or 1.0)
    results["selected_arch"] = "residual_ln" if res_brier <= mlp_brier + 1e-6 else "mlp"
    _write_json(dest / "predictor_study.json", results)
    return results


def _apply_trial(cfg: TrainConfig, trial: dict[str, Any], *, timesteps: int) -> TrainConfig:
    updates: dict[str, Any] = {
        "action_layout": trial["action_layout"],
        "ppo_ent_coef": float(trial["ppo_ent_coef"]),
        "timesteps": int(timesteps),
        "eval_cadence": max(256, int(timesteps) // 2),
        "early_stopping_patience": 2,
        "mc_rollouts": 2,
    }
    if trial.get("curriculum"):
        updates["curriculum_families"] = CURRICULUM_FAMILIES
        updates["curriculum_episode_boundaries"] = CURRICULUM_BOUNDARIES
    else:
        updates["curriculum_families"] = []
        updates["curriculum_episode_boundaries"] = []
    return cfg.model_copy(update=updates)


def run_hpo(cfg: TrainConfig, dest: Path, *, track: bool = False, timesteps: int = 1536) -> dict[str, Any]:
    from smartscan.ml.dataset import collect_exploration
    from smartscan.ml.train import train_ppo, train_predictor
    from smartscan.rf.bands import named_band_plan

    rows, manifest = collect_exploration(cfg)
    n_bands = named_band_plan(cfg.band_plan_id).n_bands
    predictor, _hit, _act, pred_metrics = train_predictor(rows, cfg, n_bands=n_bands)
    trials_out: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    for trial in HPO_TRIALS:
        trial_cfg = _apply_trial(cfg, trial, timesteps=timesteps)
        t0 = time.perf_counter()
        _state, _norm, meta = train_ppo(trial_cfg, predictor=predictor, rows=rows)
        elapsed = time.perf_counter() - t0
        score = meta.get("best_val_score")
        if score is None:
            curve = meta.get("val_curve") or []
            score = curve[-1]["selection_score"] if curve else -1e18
        record = {
            "name": trial["name"],
            "action_layout": trial["action_layout"],
            "ppo_ent_coef": trial["ppo_ent_coef"],
            "curriculum": bool(trial.get("curriculum")),
            "best_val_air": meta.get("best_val_air"),
            "best_val_score": score,
            "checkpoint": meta.get("checkpoint"),
            "elapsed_s": elapsed,
            "val_curve": meta.get("val_curve"),
        }
        trials_out.append(record)
        if track:
            record["mlflow_run_id"] = _track(
                "hpo",
                params={"phase": "hpo", "trial": str(trial["name"]), "seed": str(cfg.seed)},
                metrics={
                    "best_val_air": float(meta.get("best_val_air") or 0.0),
                    "best_val_score": float(score or 0.0),
                    "elapsed_s": float(elapsed),
                },
                tags={"phase": "hpo", "trial": str(trial["name"])},
            )
        if best is None or float(score or -1e18) > float(best.get("best_val_score") or -1e18):
            best = record
        del _state, _norm
    payload = {
        "dataset_fingerprint": manifest.content_fingerprint,
        "predictor_val_brier_cal": pred_metrics.get("val_brier_cal"),
        "trials": trials_out,
        "selected": best,
        "selection_rule": "max validation composite score (AIR + 0.5 ratio - 0.05 delay - 20 Pfa)",
    }
    _write_json(dest / "hpo.json", payload)
    return payload


def train_v3_seeds(
    cfg: TrainConfig,
    selected: dict[str, Any],
    dest: Path,
    *,
    seeds: tuple[int, ...] = (41, 42, 43),
    track: bool = False,
) -> dict[str, Any]:
    from smartscan.ml.dataset import collect_exploration
    from smartscan.ml.train import (
        build_and_save_bundle,
        train_contextual_bandit,
        train_ppo,
        train_predictor,
    )
    from smartscan.rf.bands import named_band_plan

    trial = {
        "action_layout": selected.get("action_layout", "discrete"),
        "ppo_ent_coef": float(selected.get("ppo_ent_coef") or cfg.ppo_ent_coef),
        "curriculum": bool(selected.get("curriculum")),
        "name": selected.get("name", "selected"),
    }
    base = _apply_trial(cfg, trial, timesteps=int(cfg.timesteps))
    rows, manifest = collect_exploration(base)
    n_bands = named_band_plan(base.band_plan_id).n_bands
    predictor, hit_cal, act_cal, pred_metrics = train_predictor(rows, base, n_bands=n_bands)
    cts = train_contextual_bandit(base, n_bands=n_bands)
    seed_rows: list[dict[str, Any]] = []
    best_seed: dict[str, Any] | None = None
    best_bundle_state: tuple[Any, Any, Any] | None = None
    for seed in seeds:
        seed_cfg = base.model_copy(update={"seed": int(seed)})
        t0 = time.perf_counter()
        ppo_state, normalizer, ppo_meta = train_ppo(seed_cfg, predictor=predictor, rows=rows)
        elapsed = time.perf_counter() - t0
        record = {
            "seed": int(seed),
            "best_val_air": ppo_meta.get("best_val_air"),
            "best_val_score": ppo_meta.get("best_val_score"),
            "checkpoint": ppo_meta.get("checkpoint"),
            "elapsed_s": elapsed,
            "val_curve": ppo_meta.get("val_curve"),
            "train_logs": ppo_meta.get("train_logs"),
        }
        seed_rows.append(record)
        score = float(ppo_meta.get("best_val_score") or -1e18)
        if best_seed is None or score > float(best_seed.get("best_val_score") or -1e18):
            best_seed = record
            best_bundle_state = (ppo_state, normalizer, ppo_meta)
        if track:
            record["mlflow_run_id"] = _track(
                "v3-seed",
                params={"phase": "v3-seed", "seed": str(seed), "trial": str(trial["name"])},
                metrics={
                    "best_val_air": float(ppo_meta.get("best_val_air") or 0.0),
                    "best_val_score": float(score),
                },
                tags={"phase": "v3-seed"},
            )
    if best_bundle_state is None or best_seed is None:
        raise SmartScanError("v3 training produced no seed.")
    ppo_state, normalizer, ppo_meta = best_bundle_state
    bundle_dir = _root() / V3_BUNDLE
    checksums = build_and_save_bundle(
        base.model_copy(update={"seed": int(best_seed["seed"])}),
        predictor=predictor,
        hit_cal=hit_cal,
        act_cal=act_cal,
        cts=cts,
        ppo_state=ppo_state,
        normalizer=normalizer,
        dest=bundle_dir,
    )
    airs = [float(r["best_val_air"]) for r in seed_rows if r.get("best_val_air") is not None]
    scores = [float(r["best_val_score"]) for r in seed_rows if r.get("best_val_score") is not None]
    summary = {
        "selected_trial": trial,
        "dataset_fingerprint": manifest.content_fingerprint,
        "predictor_metrics": pred_metrics,
        "seeds": seed_rows,
        "selected_seed": best_seed["seed"],
        "val_air_mean": float(np.mean(airs)) if airs else None,
        "val_air_median": float(np.median(airs)) if airs else None,
        "val_air_std": float(np.std(airs)) if airs else None,
        "val_score_mean": float(np.mean(scores)) if scores else None,
        "val_score_std": float(np.std(scores)) if scores else None,
        "bundle_dir": str(bundle_dir),
        "bundle_checksums": checksums,
        "ppo_meta": {k: v for k, v in ppo_meta.items() if k not in {"train_logs"}},
    }
    _write_json(dest / "v3_selection.json", summary)
    (bundle_dir / "val_curve.json").write_text(
        json.dumps(ppo_meta, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    return summary


def register_v3_candidate(*, track: bool = True) -> dict[str, Any]:
    from smartscan.ml.bundle import BUNDLE_NAME
    from smartscan.storage.constants import VALIDATION_UNVALIDATED
    from smartscan.storage.db import StorageSettings
    from smartscan.storage.pipeline import build_repository
    from smartscan.storage.tracking import TrackingPayload

    dest = _root() / V3_BUNDLE
    if not dest.is_dir():
        raise SmartScanError(f"v3 bundle missing at {dest}")
    if not track:
        return {"registered": False, "reason": "track=false"}
    settings = StorageSettings.from_env()
    repo = build_repository(settings, track=True, upgrade=True)
    payload = TrackingPayload(
        domain_run_id=uuid4(),
        experiment="smartscan-ml-improve",
        params={"algorithm": "ppo", "model_version": "3.0.0-candidate"},
        tags={"kind": "scheduler_v3", "alias": "candidate"},
        artifact_files=[dest / "manifest.json"],
    )
    mlflow_id = repo.tracker.log_run(payload)
    version = None
    if mlflow_id:
        repo.tracker.log_model_bundle(mlflow_run_id=mlflow_id, local_dir=dest)
        version = repo.tracker.register_model_version(
            name=BUNDLE_NAME,
            source_run_id=mlflow_id,
            alias="candidate",
            validation_status=VALIDATION_UNVALIDATED,
        )
    return {"mlflow_run_id": mlflow_id, "version": version, "alias": "candidate"}


def run_fresh_test(cfg: TrainConfig, dest: Path, *, track: bool = False) -> dict[str, Any]:
    from smartscan.config import BenchmarkConfig
    from smartscan.ml.bundle import load_bundle, ppo_predict_fn
    from smartscan.ml.evaluate import evaluate_held_out, load_held_out_manifest
    from smartscan.ml.predictor import BuilderBackedHazardPredictor

    manifest_path = write_fresh_test_manifest(fresh_manifest_path(), overwrite=False)
    frozen_fp = str(manifest_path["content_fingerprint"])
    bench = BenchmarkConfig.model_validate(load_yaml(_root() / "configs" / "benchmark_v3_fresh.yaml"))
    loaded = load_held_out_manifest(_root() / bench.manifest)
    if str(loaded["content_fingerprint"]) != frozen_fp:
        raise SmartScanError("Fresh-test manifest fingerprint changed after freeze.")
    bundle = load_bundle(_root() / V3_BUNDLE)
    ppo_predict = ppo_predict_fn(bundle)
    builder_predictor = (
        BuilderBackedHazardPredictor(bundle.predictor) if bundle.predictor is not None else None
    )
    train_cfg = deepcopy(cfg)
    if isinstance(bundle.config, dict):
        layout = bundle.config.get("action_layout")
        if layout:
            train_cfg = train_cfg.model_copy(update={"action_layout": layout})
        train_cfg = train_cfg.model_copy(
            update={
                "include_predictor_obs": bool(bundle.config.get("include_predictor_obs", False)),
                "include_action_history": int(bundle.config.get("include_action_history") or 0),
                "include_neural_predictor_obs": bool(
                    bundle.config.get("include_neural_predictor_obs", False)
                ),
            }
        )
    rows, gate = evaluate_held_out(
        bench,
        train_cfg,
        loaded,
        ppo_predict=ppo_predict,
        feature_builder_factory=_feature_builder_factory(train_cfg),
        include_oracle=True,
        predictor=builder_predictor,
    )
    payload = {
        "performance_gate_passed": gate.performance_gate_passed,
        "reasons": gate.reasons,
        "comparisons": gate.comparisons,
        "family_pass": gate.family_pass,
        "n_rows": len(rows),
        "manifest_fingerprint": loaded["content_fingerprint"],
        "manifest_sha256": file_sha256(_root() / bench.manifest),
        "benchmark_yaml_sha256": file_sha256(_root() / "configs" / "benchmark_v3_fresh.yaml"),
        "bundle_dir": str(_root() / V3_BUNDLE),
        "evaluated_once": True,
        "seed_rows": [
            {
                "scenario_id": row.scenario_id,
                "seed": row.seed,
                "strategy": row.strategy,
                "metrics": row.metrics,
                "pfa_num": row.pfa_num,
                "pfa_den": row.pfa_den,
            }
            for row in rows
        ],
    }
    _write_json(dest / "fresh_test_gate.json", payload)
    if track:
        payload["mlflow_run_id"] = _track(
            "fresh-test",
            params={"phase": "fresh-test", "n_rows": str(len(rows))},
            metrics={"performance_gate_passed": 1.0 if gate.performance_gate_passed else 0.0},
            tags={"phase": "fresh-test", "manifest_fp": str(loaded["content_fingerprint"])},
            artifacts=[dest / "fresh_test_gate.json"],
        )
    return payload


def train_v4_seeds(
    cfg: TrainConfig,
    dest: Path,
    *,
    seeds: tuple[int, ...] = (51, 52, 53),
    track: bool = False,
) -> dict[str, Any]:
    from smartscan.ml.dataset import collect_exploration
    from smartscan.ml.train import (
        build_and_save_bundle,
        train_contextual_bandit,
        train_ppo,
        train_predictor,
    )
    from smartscan.rf.bands import named_band_plan

    rows, manifest = collect_exploration(cfg)
    n_bands = named_band_plan(cfg.band_plan_id).n_bands
    predictor, hit_cal, act_cal, pred_metrics = train_predictor(rows, cfg, n_bands=n_bands)
    cts = train_contextual_bandit(cfg, n_bands=n_bands)
    seed_rows: list[dict[str, Any]] = []
    best_seed: dict[str, Any] | None = None
    best_bundle_state: tuple[Any, Any, Any] | None = None
    for seed in seeds:
        seed_cfg = cfg.model_copy(update={"seed": int(seed)})
        t0 = time.perf_counter()
        ppo_state, normalizer, ppo_meta = train_ppo(seed_cfg, predictor=predictor, rows=rows)
        elapsed = time.perf_counter() - t0
        record = {
            "seed": int(seed),
            "best_val_air": ppo_meta.get("best_val_air"),
            "best_val_score": ppo_meta.get("best_val_score"),
            "checkpoint": ppo_meta.get("checkpoint"),
            "elapsed_s": elapsed,
            "val_curve": ppo_meta.get("val_curve"),
            "train_logs": ppo_meta.get("train_logs"),
            "bc_loss": ppo_meta.get("bc_loss"),
        }
        seed_rows.append(record)
        score = float(ppo_meta.get("best_val_score") or -1e18)
        if best_seed is None or score > float(best_seed.get("best_val_score") or -1e18):
            best_seed = record
            best_bundle_state = (ppo_state, normalizer, ppo_meta)
        if track:
            record["mlflow_run_id"] = _track(
                "v4-seed",
                params={"phase": "v4-seed", "seed": str(seed), "model_version": str(cfg.model_version)},
                metrics={
                    "best_val_air": float(ppo_meta.get("best_val_air") or 0.0),
                    "best_val_score": float(score),
                },
                tags={"phase": "v4-seed"},
            )
    if best_bundle_state is None or best_seed is None:
        raise SmartScanError("v4 training produced no seed.")
    ppo_state, normalizer, ppo_meta = best_bundle_state
    bundle_dir = _root() / V4_BUNDLE
    checksums = build_and_save_bundle(
        cfg.model_copy(update={"seed": int(best_seed["seed"])}),
        predictor=predictor,
        hit_cal=hit_cal,
        act_cal=act_cal,
        cts=cts,
        ppo_state=ppo_state,
        normalizer=normalizer,
        dest=bundle_dir,
    )
    airs = [float(r["best_val_air"]) for r in seed_rows if r.get("best_val_air") is not None]
    scores = [float(r["best_val_score"]) for r in seed_rows if r.get("best_val_score") is not None]
    summary = {
        "selected_trial": {
            "name": "v4_bc_firsthit_multidiscrete",
            "action_layout": cfg.action_layout,
            "curriculum": False,
            "ppo_ent_coef": cfg.ppo_ent_coef,
        },
        "dataset_fingerprint": manifest.content_fingerprint,
        "predictor_metrics": pred_metrics,
        "seeds": seed_rows,
        "selected_seed": best_seed["seed"],
        "val_air_mean": float(np.mean(airs)) if airs else None,
        "val_air_median": float(np.median(airs)) if airs else None,
        "val_air_std": float(np.std(airs)) if airs else None,
        "val_score_mean": float(np.mean(scores)) if scores else None,
        "val_score_std": float(np.std(scores)) if scores else None,
        "bundle_dir": str(bundle_dir),
        "bundle_checksums": checksums,
        "ppo_meta": {k: v for k, v in ppo_meta.items() if k not in {"train_logs"}},
    }
    _write_json(dest / "v4_selection.json", summary)
    (bundle_dir / "val_curve.json").write_text(
        json.dumps(ppo_meta, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    return summary


def run_fresh_test_v4(cfg: TrainConfig, dest: Path, *, track: bool = False) -> dict[str, Any]:
    from smartscan.config import BenchmarkConfig
    from smartscan.ml.bundle import load_bundle, ppo_predict_fn
    from smartscan.ml.evaluate import evaluate_held_out, load_held_out_manifest
    from smartscan.ml.predictor import BuilderBackedHazardPredictor

    manifest_path = write_fresh_test_v4_manifest(fresh_v4_manifest_path(), overwrite=False)
    frozen_fp = str(manifest_path["content_fingerprint"])
    bench = BenchmarkConfig.model_validate(load_yaml(_root() / "configs" / "benchmark_v4_fresh.yaml"))
    loaded = load_held_out_manifest(_root() / bench.manifest)
    if str(loaded["content_fingerprint"]) != frozen_fp:
        raise SmartScanError("v4 fresh-test manifest fingerprint changed after freeze.")
    bundle = load_bundle(_root() / V4_BUNDLE)
    ppo_predict = ppo_predict_fn(bundle)
    builder_predictor = (
        BuilderBackedHazardPredictor(bundle.predictor) if bundle.predictor is not None else None
    )
    train_cfg = deepcopy(cfg)
    if isinstance(bundle.config, dict):
        layout = bundle.config.get("action_layout")
        if layout:
            train_cfg = train_cfg.model_copy(update={"action_layout": layout})
        train_cfg = train_cfg.model_copy(
            update={
                "include_predictor_obs": bool(bundle.config.get("include_predictor_obs", False)),
                "include_action_history": int(bundle.config.get("include_action_history") or 0),
                "include_neural_predictor_obs": bool(
                    bundle.config.get("include_neural_predictor_obs", False)
                ),
            }
        )
    rows, gate = evaluate_held_out(
        bench,
        train_cfg,
        loaded,
        ppo_predict=ppo_predict,
        feature_builder_factory=_feature_builder_factory(train_cfg),
        include_oracle=True,
        predictor=builder_predictor,
    )
    payload = {
        "performance_gate_passed": gate.performance_gate_passed,
        "reasons": gate.reasons,
        "comparisons": gate.comparisons,
        "family_pass": gate.family_pass,
        "n_rows": len(rows),
        "manifest_fingerprint": loaded["content_fingerprint"],
        "manifest_sha256": file_sha256(_root() / bench.manifest),
        "benchmark_yaml_sha256": file_sha256(_root() / "configs" / "benchmark_v4_fresh.yaml"),
        "bundle_dir": str(_root() / V4_BUNDLE),
        "evaluated_once": True,
        "seed_rows": [
            {
                "scenario_id": row.scenario_id,
                "seed": row.seed,
                "strategy": row.strategy,
                "metrics": row.metrics,
                "pfa_num": row.pfa_num,
                "pfa_den": row.pfa_den,
            }
            for row in rows
        ],
    }
    _write_json(dest / "fresh_test_v4_gate.json", payload)
    if track:
        payload["mlflow_run_id"] = _track(
            "fresh-test-v4",
            params={"phase": "fresh-test-v4", "n_rows": str(len(rows))},
            metrics={"performance_gate_passed": 1.0 if gate.performance_gate_passed else 0.0},
            tags={"phase": "fresh-test-v4", "manifest_fp": str(loaded["content_fingerprint"])},
            artifacts=[dest / "fresh_test_v4_gate.json"],
        )
    return payload


def inference_benchmark(dest: Path, *, bundle_rel: Path | None = None) -> dict[str, Any]:
    import time as time_mod

    from smartscan.ml.bundle import load_bundle, ppo_predict_fn, verify_checksums

    path = _root() / (bundle_rel or V3_BUNDLE)
    t0 = time_mod.perf_counter()
    checksums = verify_checksums(path)
    bundle = load_bundle(path)
    load_s = time_mod.perf_counter() - t0
    fn = ppo_predict_fn(bundle)
    rng = np.random.default_rng(0)
    size = int(bundle.normalizer.size)
    dummy = rng.normal(size=size).astype(np.float32)
    for _ in range(8):
        fn(dummy)
    t1 = time_mod.perf_counter()
    n_rep = 64
    for _ in range(n_rep):
        fn(dummy)
    elapsed = time_mod.perf_counter() - t1
    payload = {
        "load_s": load_s,
        "mean_infer_ms": 1000.0 * elapsed / float(n_rep),
        "n_rep": n_rep,
        "obs_size": size,
        "bundle_fingerprint": checksums.get("content_fingerprint"),
        "cpu_only": True,
        "bundle_dir": str(path),
    }
    name = "inference_v4.json" if bundle_rel == V4_BUNDLE else "inference.json"
    _write_json(dest / name, payload)
    return payload


def run_cycle(
    *,
    phase: str = "all",
    track: bool = True,
    hpo_timesteps: int = 1536,
    final_seeds: tuple[int, ...] = (41, 42, 43),
) -> dict[str, Any]:
    cfg = load_improve_config()
    dest = _root() / IMPROVE_DIR
    dest.mkdir(parents=True, exist_ok=True)
    out: dict[str, Any] = {"phase": phase}
    write_fresh_test_manifest(fresh_manifest_path(), overwrite=False)
    study_path = dest / "predictor_study.json"
    if study_path.is_file() and phase in {"hpo", "train", "all"}:
        study = json.loads(study_path.read_text(encoding="utf-8"))
        arch = study.get("selected_arch")
        if arch:
            cfg = cfg.model_copy(update={"predictor_arch": str(arch)})
    if phase in {"diagnose", "all"}:
        out["diagnostics"] = run_diagnostics(cfg, dest, track=track)
    if phase in {"predictor", "all"}:
        out["predictor"] = run_predictor_study(cfg, dest, track=track)
        if out["predictor"].get("selected_arch"):
            cfg = cfg.model_copy(update={"predictor_arch": out["predictor"]["selected_arch"]})
    if phase in {"hpo", "all"}:
        out["hpo"] = run_hpo(cfg, dest, track=track, timesteps=hpo_timesteps)
    if phase in {"train", "all"}:
        selected = (out.get("hpo") or {}).get("selected")
        if selected is None and (dest / "hpo.json").is_file():
            selected = json.loads((dest / "hpo.json").read_text(encoding="utf-8")).get("selected")
        if selected is None:
            selected = {
                "name": "discrete_ent002",
                "action_layout": "discrete",
                "ppo_ent_coef": cfg.ppo_ent_coef,
                "curriculum": False,
            }
        out["v3"] = train_v3_seeds(cfg, selected, dest, seeds=final_seeds, track=track)
        if track:
            out["registry"] = register_v3_candidate(track=True)
        out["inference"] = inference_benchmark(dest)
    if phase in {"fresh-test", "all"}:
        if not (_root() / V3_BUNDLE).is_dir():
            raise SmartScanError("Cannot run fresh-test before train writes scheduler_v3.")
        out["fresh_test"] = run_fresh_test(cfg, dest, track=track)
    if phase in {"train-v4"}:
        cfg_v4 = load_v4_config()
        write_fresh_test_v4_manifest(fresh_v4_manifest_path(), overwrite=False)
        out["v4"] = train_v4_seeds(cfg_v4, dest, seeds=final_seeds, track=track)
        out["inference_v4"] = inference_benchmark(dest, bundle_rel=V4_BUNDLE)
    if phase in {"fresh-test-v4"}:
        cfg_v4 = load_v4_config()
        if not (_root() / V4_BUNDLE).is_dir():
            raise SmartScanError("Cannot run fresh-test-v4 before train-v4 writes scheduler_v4.")
        out["fresh_test_v4"] = run_fresh_test_v4(cfg_v4, dest, track=track)
    out["content_fingerprint"] = content_fingerprint(
        {k: v for k, v in out.items() if k not in {"diagnostics", "fresh_test"}}
    )
    _write_json(dest / "cycle_summary.json", {k: v for k, v in out.items() if k != "diagnostics"})
    return out
