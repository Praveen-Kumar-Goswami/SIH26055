"""Stage 5 CLI handlers. Imported lazily from ``smartscan.cli``."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from uuid import uuid4

from smartscan.config import BenchmarkConfig, TrainConfig, load_yaml, project_root
from smartscan.storage.constants import (
    EXPERIMENT_PREDICTOR,
    EXPERIMENT_SCHEDULER,
    VALIDATION_UNVALIDATED,
    VALIDATION_VALIDATED,
)
from smartscan.types import SmartScanError


def load_train_config(path: Path) -> TrainConfig:
    return TrainConfig.model_validate(load_yaml(path))


def cmd_collect(args: Namespace) -> int:
    from smartscan.ml.dataset import collect_exploration, save_dataset

    cfg = load_train_config(Path(args.config))
    out = Path(args.output) if args.output else project_root() / "artifacts" / "models" / "datasets" / "smoke"
    rows, manifest = collect_exploration(cfg)
    save_dataset(rows, manifest, out)
    print(f"wrote {out}")
    print(f"n_rows={manifest.n_rows} train={manifest.n_train} val={manifest.n_val} test={manifest.n_test}")
    print(f"content_fingerprint={manifest.content_fingerprint}")
    print(f"artifact_sha256={manifest.artifact_sha256}")
    return 0


def cmd_train_predictor(args: Namespace) -> int:
    from smartscan.ml.dataset import collect_exploration
    from smartscan.ml.train import train_predictor
    from smartscan.rf.bands import named_band_plan
    from smartscan.storage.db import StorageSettings
    from smartscan.storage.pipeline import build_repository
    from smartscan.storage.tracking import TrackingPayload

    cfg = load_train_config(Path(args.config))
    rows, manifest = collect_exploration(cfg)
    n_bands = named_band_plan(cfg.band_plan_id).n_bands
    predictor, hit_cal, act_cal, metrics = train_predictor(rows, cfg, n_bands=n_bands)
    dest = Path(args.output) if args.output else project_root() / "artifacts" / "models" / "predictor_smoke"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    (dest / "manifest.json").write_text(
        json.dumps({"dataset": manifest.content_fingerprint, "metrics": metrics}, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {dest}")
    print(f"dataset_fingerprint={manifest.content_fingerprint}")
    for key, value in metrics.items():
        print(f"  {key}={value:.6g}")
    if args.track:
        settings = StorageSettings.from_env()
        repo = build_repository(settings, track=True, upgrade=True)
        domain_id = uuid4()
        payload = TrackingPayload(
            domain_run_id=domain_id,
            experiment=EXPERIMENT_PREDICTOR,
            params={"algorithm": "hit_hazard", "seed": str(cfg.seed)},
            metrics={k: float(v) for k, v in metrics.items() if v == v},
            tags={"stage": "5", "kind": "predictor", "dataset_fp": manifest.content_fingerprint},
            artifact_files=[dest / "metrics.json"],
        )
        mlflow_id = repo.tracker.log_run(payload)
        print(f"mlflow_run_id={mlflow_id or '-'}")
    del predictor, hit_cal, act_cal
    return 0


def cmd_train_contextual_bandit(args: Namespace) -> int:
    from smartscan.ml.calibrate import IsotonicCalibrator
    from smartscan.ml.features import ObservationNormalizer, observation_size
    from smartscan.ml.train import build_and_save_bundle, train_contextual_bandit
    from smartscan.rf.bands import named_band_plan
    from smartscan.storage.db import StorageSettings
    from smartscan.storage.pipeline import build_repository
    from smartscan.storage.tracking import TrackingPayload

    cfg = load_train_config(Path(args.config))
    n_bands = named_band_plan(cfg.band_plan_id).n_bands
    cts = train_contextual_bandit(cfg, n_bands=n_bands)
    dest = Path(args.output) if args.output else project_root() / "artifacts" / "models" / "cts_smoke"
    ident = IsotonicCalibrator.identity()
    checksums = build_and_save_bundle(
        cfg,
        predictor=None,
        hit_cal=ident,
        act_cal=ident,
        cts=cts,
        ppo_state=None,
        normalizer=ObservationNormalizer(size=observation_size(n_bands)),
        dest=dest,
    )
    print(f"wrote {dest}")
    print(f"bundle_checksum={checksums.get('content_fingerprint')}")
    if args.track:
        settings = StorageSettings.from_env()
        repo = build_repository(settings, track=True, upgrade=True)
        payload = TrackingPayload(
            domain_run_id=uuid4(),
            experiment=EXPERIMENT_SCHEDULER,
            params={"algorithm": "contextual_thompson", "seed": str(cfg.seed)},
            tags={"stage": "5", "kind": "contextual_bandit"},
        )
        print(f"mlflow_run_id={repo.tracker.log_run(payload) or '-'}")
    return 0


def cmd_train_scheduler(args: Namespace) -> int:
    from smartscan.ml.bundle import BUNDLE_NAME
    from smartscan.ml.dataset import collect_exploration
    from smartscan.ml.train import (
        build_and_save_bundle,
        train_contextual_bandit,
        train_ppo,
        train_predictor,
    )
    from smartscan.rf.bands import named_band_plan
    from smartscan.storage.constants import VALIDATION_UNVALIDATED
    from smartscan.storage.db import StorageSettings
    from smartscan.storage.pipeline import build_repository, persist_baseline_run
    from smartscan.storage.tracking import TrackingPayload

    cfg = load_train_config(Path(args.config))
    n_bands = named_band_plan(cfg.band_plan_id).n_bands
    rows, manifest = collect_exploration(cfg)
    predictor, hit_cal, act_cal, pred_metrics = train_predictor(rows, cfg, n_bands=n_bands)
    cts = train_contextual_bandit(cfg, n_bands=n_bands)
    ppo_state, normalizer, ppo_meta = train_ppo(cfg, predictor=predictor, rows=rows)
    dest = Path(args.output) if args.output else project_root() / "artifacts" / "models" / "scheduler_smoke"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "val_curve.json").write_text(
        json.dumps(ppo_meta, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    checksums = build_and_save_bundle(
        cfg,
        predictor=predictor,
        hit_cal=hit_cal,
        act_cal=act_cal,
        cts=cts,
        ppo_state=ppo_state,
        normalizer=normalizer,
        dest=dest,
    )
    print(f"wrote {dest}")
    print(f"dataset_fingerprint={manifest.content_fingerprint}")
    print(f"bundle_checksum={checksums.get('content_fingerprint')}")
    print(f"ppo_checkpoint={ppo_meta.get('checkpoint')} best_val_air={ppo_meta.get('best_val_air')}")
    for row in ppo_meta.get("val_curve") or []:
        print(f"  val_step={int(row['timestep'])} val_air={row['val_air']:.6g}")
    for key, value in pred_metrics.items():
        print(f"  {key}={value:.6g}")
    if args.track:
        settings = StorageSettings.from_env()
        repo = build_repository(settings, track=True, upgrade=True)
        from smartscan.config import SimulateConfig
        from smartscan.receiver.detector import load_receiver_config

        sim = SimulateConfig(
            seed=cfg.seed,
            dt_s=cfg.dt_s,
            duration_s=cfg.duration_s,
            band_plan_id=cfg.band_plan_id,
            scenario_id=cfg.train_scenarios[0].scenario_id if cfg.train_scenarios else "sparse",
        )
        receiver = load_receiver_config(load_yaml(project_root() / cfg.receiver_config))
        receiver = receiver.model_copy(update={"noise_power_w": cfg.noise_power_w})
        domain_id = persist_baseline_run(
            simulate_config=sim,
            receiver_config=receiver,
            strategy="sequential",
            receiver_seed=cfg.seed,
            schedule_seed=cfg.seed,
            dwell_steps=cfg.default_dwell_steps,
            band_order=tuple(cfg.public_priorities),
            repo=repo,
            track=True,
        )
        payload = TrackingPayload(
            domain_run_id=domain_id,
            experiment=EXPERIMENT_SCHEDULER,
            params={
                "algorithm": "ppo",
                "seed": str(cfg.seed),
                "timesteps": str(cfg.timesteps),
                "ppo_checkpoint": str(ppo_meta.get("checkpoint")),
            },
            metrics={
                **{k: float(v) for k, v in pred_metrics.items() if v == v},
                **(
                    {"best_val_air": float(ppo_meta["best_val_air"])}
                    if ppo_meta.get("best_val_air") is not None
                    else {}
                ),
            },
            tags={
                "stage": "5",
                "kind": "scheduler",
                "parent_dataset": manifest.content_fingerprint,
                "bundle_checksum": str(checksums.get("content_fingerprint")),
            },
            artifact_files=[dest / "manifest.json"],
        )
        mlflow_id = repo.tracker.log_run(payload)
        if mlflow_id:
            repo.tracker.log_model_bundle(mlflow_run_id=mlflow_id, local_dir=dest)
            version = repo.tracker.register_model_version(
                name=BUNDLE_NAME,
                source_run_id=mlflow_id,
                alias="candidate",
                validation_status=VALIDATION_UNVALIDATED,
            )
            repo.register_domain_model_version(
                registered_name=BUNDLE_NAME,
                version=str(version),
                source_run_id=domain_id,
                bundle_checksum=str(checksums.get("content_fingerprint")),
                alias="candidate",
                validation_status=VALIDATION_UNVALIDATED,
            )
            print(f"registered {BUNDLE_NAME} version={version} alias=candidate")
        print(f"domain_run_id={domain_id}")
        print(f"mlflow_run_id={mlflow_id or '-'}")
    return 0


def cmd_evaluate(args: Namespace) -> int:
    from smartscan.ml.bundle import load_bundle, ppo_predict_fn
    from smartscan.ml.evaluate import evaluate_held_out, load_held_out_manifest
    from smartscan.ml.features import FeatureBuilder
    from smartscan.rf.bands import named_band_plan

    bench = BenchmarkConfig.model_validate(load_yaml(Path(args.config)))
    train_cfg = load_train_config(Path(args.train_config) if args.train_config else project_root() / "configs" / "train_smoke.yaml")
    manifest_path = project_root() / bench.manifest
    manifest = load_held_out_manifest(manifest_path)
    print(f"held_out_manifest_fp={manifest['content_fingerprint']}")
    ppo_predict = None
    fb_factory = None
    builder_predictor = None
    if args.model:
        local = args.model
        if str(local).startswith("models:"):
            full = project_root() / "artifacts" / "models" / "scheduler_full"
            smoke = project_root() / "artifacts" / "models" / "scheduler_smoke"
            local = str(full if full.is_dir() else smoke)
        bundle = load_bundle(local)
        ppo_predict = ppo_predict_fn(bundle)
        if bundle.predictor is not None:
            from smartscan.ml.predictor import BuilderBackedHazardPredictor

            builder_predictor = BuilderBackedHazardPredictor(bundle.predictor)

        def fb_factory() -> FeatureBuilder:
            from smartscan.receiver.detector import load_receiver_config

            plan = named_band_plan(train_cfg.band_plan_id)
            rec_payload = dict(load_yaml(project_root() / train_cfg.receiver_config))
            rec_payload["dwell_bins"] = list(train_cfg.dwell_bins)
            rec_payload["noise_power_w"] = float(train_cfg.noise_power_w)
            receiver = load_receiver_config(rec_payload)
            return FeatureBuilder(
                n_bands=plan.n_bands,
                dt_s=train_cfg.dt_s,
                dwell_bins=tuple(int(x) for x in train_cfg.dwell_bins),
                ewma_alpha=train_cfg.ewma_alpha,
                tune_latency_steps=receiver.tune_latency_steps,
                public_priorities={int(b): 2.0 for b in train_cfg.public_priorities},
            )

    rows, gate = evaluate_held_out(
        bench,
        train_cfg,
        manifest,
        ppo_predict=ppo_predict,
        feature_builder_factory=fb_factory,
        include_oracle=True,
        predictor=builder_predictor,
    )
    out = Path(args.output) if args.output else project_root() / "artifacts" / "models" / "held_out_gate.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "performance_gate_passed": gate.performance_gate_passed,
        "reasons": gate.reasons,
        "comparisons": gate.comparisons,
        "family_pass": gate.family_pass,
        "n_rows": len(rows),
        "manifest_fingerprint": manifest["content_fingerprint"],
        "seeds": args.seeds,
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
    out.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(f"wrote {out}")
    print(f"performance_gate_passed={str(gate.performance_gate_passed).lower()}")
    for reason in gate.reasons:
        print(f"  reason: {reason}")
    if args.track:
        from smartscan.storage.db import StorageSettings
        from smartscan.storage.pipeline import build_repository
        from smartscan.storage.tracking import TrackingPayload

        settings = StorageSettings.from_env()
        repo = build_repository(settings, track=True, upgrade=True)
        mlflow_id = repo.tracker.log_run(
            TrackingPayload(
                domain_run_id=uuid4(),
                experiment=EXPERIMENT_SCHEDULER,
                params={
                    "kind": "held_out_eval",
                    "seeds": str(args.seeds),
                    "model": str(args.model or ""),
                },
                metrics={"performance_gate_passed": 1.0 if gate.performance_gate_passed else 0.0},
                tags={
                    "stage": "5",
                    "kind": "held_out_eval",
                    "manifest_fp": str(manifest["content_fingerprint"]),
                },
                artifact_files=[out],
            )
        )
        print(f"mlflow_run_id={mlflow_id or '-'}")
    return 0


def cmd_models_promote(args: Namespace) -> int:
    from smartscan.ml.bundle import BUNDLE_NAME
    from smartscan.storage.db import StorageSettings
    from smartscan.storage.pipeline import build_repository

    gate_path = Path(args.gate) if args.gate else project_root() / "artifacts" / "models" / "held_out_gate.json"
    if args.require_gate:
        if not gate_path.is_file():
            raise SmartScanError(f"Gate evidence not found: {gate_path}")
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        if not gate.get("performance_gate_passed"):
            raise SmartScanError(
                "Refusing champion promotion; performance_gate_passed is false. "
                f"Reasons: {gate.get('reasons')}"
            )
        validation = VALIDATION_VALIDATED
        alias = "champion"
    else:
        validation = VALIDATION_UNVALIDATED
        alias = "candidate"
    settings = StorageSettings.from_env()
    repo = build_repository(settings, track=True, upgrade=False)
    name = args.name or BUNDLE_NAME
    version = str(args.version)
    repo.tracker.set_model_alias(name, alias, version, validation_status=validation)
    print(f"set alias {alias} on {name} v{version} validation={validation}")
    return 0


def cmd_ml_improve(args: Namespace) -> int:
    from smartscan.ml.improve_cycle import run_cycle

    seeds = tuple(int(part.strip()) for part in str(args.seeds).split(",") if part.strip())
    if any(1000 <= seed <= 1029 or 8000 <= seed <= 8007 or 9000 <= seed <= 9007 for seed in seeds):
        raise SmartScanError(
            "ml-improve training seeds must not use frozen evaluation ranges "
            "1000–1029, 8000–8007, or 9000–9007."
        )
    result = run_cycle(
        phase=str(args.phase),
        track=bool(args.track),
        hpo_timesteps=int(args.hpo_timesteps),
        final_seeds=seeds or (41, 42, 43),
    )
    print(f"phase={result.get('phase')}")
    if result.get("hpo", {}).get("selected"):
        selected = result["hpo"]["selected"]
        print(f"hpo_selected={selected.get('name')} val_score={selected.get('best_val_score')}")
    if result.get("v3"):
        print(
            f"v3_bundle={result['v3'].get('bundle_dir')} selected_seed={result['v3'].get('selected_seed')}"
        )
    if result.get("v4"):
        print(
            f"v4_bundle={result['v4'].get('bundle_dir')} selected_seed={result['v4'].get('selected_seed')} "
            f"val_air={result['v4'].get('val_air_mean')}"
        )
    if result.get("fresh_test"):
        gate = result["fresh_test"]
        print(f"new_performance_gate_passed={str(gate.get('performance_gate_passed')).lower()}")
        for reason in gate.get("reasons") or []:
            print(f"  reason: {reason}")
    if result.get("fresh_test_v4"):
        gate = result["fresh_test_v4"]
        print(f"v4_performance_gate_passed={str(gate.get('performance_gate_passed')).lower()}")
        for reason in gate.get("reasons") or []:
            print(f"  reason: {reason}")
    if result.get("registry"):
        print(f"registry={result['registry']}")
    return 0
