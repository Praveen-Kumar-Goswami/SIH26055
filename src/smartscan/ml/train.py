"""Predictor, contextual-bandit, and PPO training loops."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import numpy as np

from smartscan.config import TrainConfig, project_root
from smartscan.ml.bundle import SchedulerBundle, save_bundle
from smartscan.ml.calibrate import IsotonicCalibrator, brier_score, expected_calibration_error
from smartscan.ml.dataset import SupervisedRow
from smartscan.ml.features import ObservationNormalizer, feature_schema, observation_size
from smartscan.ml.policies import (
    ContextualThompsonSchedule,
    PeriodicInterceptSchedule,
    ReactiveSchedule,
)
from smartscan.ml.predictor import (
    BuilderBackedHazardPredictor,
    HitHazardNet,
    HitHazardPredictor,
    RecencyPredictor,
)
from smartscan.receiver.schedules import FixedPrioritySchedule, SequentialSchedule
from smartscan.rf.bands import named_band_plan
from smartscan.types import SmartScanError


def seed_ml_backends(seed: int) -> None:
    """Seed Python/NumPy/PyTorch for SB3. RF simulation still uses local Generators."""

    random.seed(int(seed))
    np.random.seed(int(seed) % (2**32 - 1))
    try:
        import torch

        torch.manual_seed(int(seed))
        torch.use_deterministic_algorithms(False)
    except ImportError:
        pass
    try:
        import gymnasium

        gymnasium.utils.seeding.np_random(int(seed))
    except Exception:
        pass


def _predictor_q_loss(
    q: Any,
    target: Any,
    *,
    pos_weight: float,
    loss_name: str,
    focal_gamma: float,
    torch: Any,
) -> Any:
    p = q.clamp(1e-8, 1.0 - 1e-8)
    y = target
    bce = -(y * torch.log(p) + (1.0 - y) * torch.log(1.0 - p))
    weight = torch.where(y > 0.5, torch.as_tensor(pos_weight, dtype=p.dtype), torch.ones_like(p))
    bce = bce * weight
    if loss_name == "focal":
        pt = torch.where(y > 0.5, p, 1.0 - p)
        bce = ((1.0 - pt) ** float(focal_gamma)) * bce
    return bce.mean()


def _val_predictor_scores(
    net: HitHazardNet,
    rows: list[SupervisedRow],
    dwell_bins: tuple[int, ...],
    torch: Any,
) -> tuple[list[float], list[float]]:
    q_val: list[float] = []
    y_val: list[float] = []
    with torch.no_grad():
        for row in rows:
            try:
                dwell_index = list(dwell_bins).index(int(row.dwell_steps))
            except ValueError:
                continue
            sched = list(zip(row.future_bands, row.future_dwells, strict=False))
            q, _h, _u = net.forward(row.features, int(row.band), dwell_index, sched)
            q_val.append(float(q.squeeze().cpu().item()))
            y_val.append(float(row.q_hit))
    return q_val, y_val


def _balanced_order(rows: list[SupervisedRow], rng: np.random.Generator) -> np.ndarray:
    by_family: dict[str, list[int]] = {}
    for i, row in enumerate(rows):
        by_family.setdefault(str(row.scenario_id), []).append(i)
    for key in by_family:
        rng.shuffle(by_family[key])
    out: list[int] = []
    index = 0
    while True:
        added = False
        for key in sorted(by_family):
            bucket = by_family[key]
            if index < len(bucket):
                out.append(int(bucket[index]))
                added = True
        if not added:
            break
        index += 1
    return np.asarray(out, dtype=np.int64) if out else np.arange(len(rows))


def train_predictor(
    rows: list[SupervisedRow],
    cfg: TrainConfig,
    *,
    n_bands: int,
) -> tuple[HitHazardPredictor, IsotonicCalibrator, IsotonicCalibrator, dict[str, float]]:
    import torch
    from torch import nn

    seed_ml_backends(cfg.seed)
    dwell_bins = tuple(int(x) for x in cfg.dwell_bins)
    n_in = observation_size(n_bands)
    net = HitHazardNet(
        n_in=n_in,
        n_bands=n_bands,
        n_dwell=len(dwell_bins),
        n_bins=int(cfg.forecast_command_bins),
        hidden=int(cfg.predictor_hidden),
        arch=str(getattr(cfg, "predictor_arch", "mlp")),
        dropout=float(getattr(cfg, "predictor_dropout", 0.0) or 0.0),
    )
    opt = torch.optim.Adam(net.parameters(), lr=float(cfg.predictor_lr))
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, mode="min", factor=0.5, patience=1)
    train_rows = [row for row in rows if row.split == "train"]
    val_rows = [row for row in rows if row.split == "val"] or train_rows
    if not train_rows:
        raise SmartScanError("No training rows for the predictor.")
    n_pos = sum(1 for row in train_rows if float(row.q_hit) >= 0.5)
    n_neg = max(len(train_rows) - n_pos, 1)
    pos_weight = float(n_neg / max(n_pos, 1)) if bool(getattr(cfg, "predictor_balance", False)) else 1.0
    loss_name = str(getattr(cfg, "predictor_loss", "bce"))
    focal_gamma = float(getattr(cfg, "predictor_focal_gamma", 2.0))
    patience = int(getattr(cfg, "predictor_patience", 0) or 0)
    best_state: dict[str, Any] | None = None
    best_brier = 1e18
    stale = 0
    net.train_mode()
    metrics: dict[str, float] = {
        "predictor_pos_weight": float(pos_weight),
        "n_train_rows": float(len(train_rows)),
        "n_val_rows": float(len(val_rows)),
        "n_pos": float(n_pos),
    }
    del nn
    for epoch in range(int(cfg.n_epochs_predictor)):
        rng = np.random.default_rng(cfg.seed + epoch)
        order = _balanced_order(train_rows, rng) if bool(getattr(cfg, "predictor_balance", False)) else rng.permutation(len(train_rows))
        losses: list[float] = []
        net.train_mode()
        for start in range(0, len(order), int(cfg.batch_size)):
            batch_idx = order[start : start + int(cfg.batch_size)]
            opt.zero_grad()
            loss_acc = torch.zeros((), dtype=torch.float32)
            n_used = 0
            for bi in batch_idx:
                row = train_rows[int(bi)]
                try:
                    dwell_index = list(dwell_bins).index(int(row.dwell_steps))
                except ValueError:
                    continue
                sched = list(zip(row.future_bands, row.future_dwells, strict=False))
                q, hazards, _u = net.forward(row.features, int(row.band), dwell_index, sched)
                target = torch.tensor([[row.q_hit]], dtype=torch.float32)
                q_loss = _predictor_q_loss(
                    q,
                    target,
                    pos_weight=pos_weight,
                    loss_name=loss_name,
                    focal_gamma=focal_gamma,
                    torch=torch,
                )
                h = hazards.clamp(1e-8, 1.0 - 1e-8).reshape(-1)
                if row.event_index is None:
                    h_loss = -torch.sum(torch.log(1.0 - h))
                else:
                    e = int(row.event_index)
                    if e >= int(h.numel()):
                        h_loss = -torch.sum(torch.log(1.0 - h))
                    else:
                        h_loss = -torch.log(h[e])
                        if e > 0:
                            h_loss = h_loss - torch.sum(torch.log(1.0 - h[:e]))
                loss_acc = loss_acc + q_loss + 0.5 * h_loss
                n_used += 1
            if n_used == 0:
                continue
            loss = loss_acc / float(n_used)
            loss.backward()
            opt.step()
            losses.append(float(loss.detach().cpu().item()))
        metrics[f"epoch_{epoch}_loss"] = float(np.mean(losses) if losses else 0.0)
        net.eval_mode()
        q_epoch, y_epoch = _val_predictor_scores(net, val_rows, dwell_bins, torch)
        val_brier = brier_score(np.asarray(q_epoch), np.asarray(y_epoch))
        metrics[f"epoch_{epoch}_val_brier"] = float(val_brier) if val_brier == val_brier else 1.0
        scheduler.step(metrics[f"epoch_{epoch}_val_brier"])
        if metrics[f"epoch_{epoch}_val_brier"] + 1e-12 < best_brier:
            best_brier = float(metrics[f"epoch_{epoch}_val_brier"])
            best_state = {k: v.detach().cpu().clone() for k, v in net.state_dict().items() if k != "meta"}
            stale = 0
        else:
            stale += 1
            if patience > 0 and stale >= patience:
                metrics["predictor_early_stop_epoch"] = float(epoch)
                break
    if best_state is not None:
        net.load_state_dict({**best_state, "meta": net.state_dict()["meta"]})
    net.eval_mode()
    q_val, y_val = _val_predictor_scores(net, val_rows, dwell_bins, torch)
    p_act_raw: list[float] = []
    y_act: list[float] = []
    for qv, yv in zip(q_val, y_val, strict=False):
        pd_op = 0.2
        from smartscan.ml.predictor import derive_p_active

        raw, reason = derive_p_active(qv, pd_operating=max(pd_op, 0.2), pfa=1e-3)
        if raw is not None:
            p_act_raw.append(raw)
            y_act.append(float(yv))
        del reason
    hit_cal = IsotonicCalibrator.fit(np.asarray(q_val), np.asarray(y_val))
    act_cal = (
        IsotonicCalibrator.fit(np.asarray(p_act_raw), np.asarray(y_act))
        if p_act_raw
        else IsotonicCalibrator.identity()
    )
    q_cal = [hit_cal.predict_one(v) for v in q_val]
    metrics["val_brier_raw"] = float(brier_score(np.asarray(q_val), np.asarray(y_val)))
    metrics["val_brier_cal"] = float(brier_score(np.asarray(q_cal), np.asarray(y_val)))
    metrics["val_ece_raw"] = float(expected_calibration_error(np.asarray(q_val), np.asarray(y_val)))
    metrics["val_ece_cal"] = float(expected_calibration_error(np.asarray(q_cal), np.asarray(y_val)))
    metrics["best_val_brier"] = float(best_brier if best_brier < 1e17 else metrics["val_brier_raw"])
    predictor = HitHazardPredictor(
        net,
        dwell_bins=dwell_bins,
        hit_calibrator=hit_cal,
        active_calibrator=act_cal,
        model_version=cfg.model_version,
    )
    return predictor, hit_cal, act_cal, metrics


def train_contextual_bandit(
    cfg: TrainConfig,
    *,
    n_bands: int,
) -> ContextualThompsonSchedule:
    from smartscan.config import SimulateConfig
    from smartscan.ml.dataset import _receiver_from_train
    from smartscan.receiver.scanner import run_schedule
    from smartscan.rf.environment import simulate

    seed_ml_backends(cfg.seed)
    dwell_bins = tuple(int(x) for x in cfg.dwell_bins)
    cts = ContextualThompsonSchedule(n_bands=n_bands, dwell_bins=dwell_bins, seed=cfg.seed)
    receiver = _receiver_from_train(cfg)
    for spec in cfg.train_scenarios:
        for seed in spec.seeds:
            truth = simulate(
                SimulateConfig(
                    seed=int(seed),
                    dt_s=cfg.dt_s,
                    duration_s=cfg.duration_s,
                    band_plan_id=cfg.band_plan_id,
                    scenario_id=spec.scenario_id,
                )
            )
            run_schedule(
                truth,
                cts,
                receiver,
                receiver_seed=int(seed),
                default_dwell_steps=cfg.default_dwell_steps,
            )
    return cts


def _obs_size(cfg: TrainConfig, n_bands: int) -> int:
    return observation_size(
        n_bands,
        predictor_obs=bool(getattr(cfg, "include_predictor_obs", False)),
        action_history=int(getattr(cfg, "include_action_history", 0) or 0),
    )


def fit_observation_normalizer(
    rows: list[SupervisedRow],
    n_bands: int,
    cfg: TrainConfig | None = None,
) -> ObservationNormalizer:
    """Fit running mean/std on training-split feature rows only.

    When the policy observation includes extras not stored in SupervisedRow,
    the caller should warmup via env rollouts instead of this helper.
    """

    size = _obs_size(cfg, n_bands) if cfg is not None else observation_size(n_bands)
    normalizer = ObservationNormalizer(size=size)
    base = observation_size(n_bands)
    if size != base:
        return normalizer
    for row in rows:
        if row.split != "train":
            continue
        normalizer.update(row.features)
    return normalizer


def warmup_observation_normalizer(
    cfg: TrainConfig,
    *,
    predictor: RecencyPredictor | BuilderBackedHazardPredictor | None,
    n_episodes: int = 6,
) -> ObservationNormalizer:
    """Fit normalizer on composed train observations. No validation/test stats."""

    from smartscan.ml.env import SmartScanEnv
    from smartscan.rf.bands import named_band_plan

    n_bands = named_band_plan(cfg.band_plan_id).n_bands
    fitted = ObservationNormalizer(size=_obs_size(cfg, n_bands))
    env = SmartScanEnv(
        cfg,
        predictor=predictor,
        normalizer=fitted,
        record_forecast=False,
        freeze_obs_stats=False,
        split="train",
    )
    for _episode in range(max(int(n_episodes), 1)):
        obs, _info = env.reset(options={})
        done = False
        steps = 0
        while not done and steps < 4096:
            action = env.action_space.sample()
            obs, _reward, terminated, truncated, _info = env.step(action)
            done = bool(terminated or truncated)
            steps += 1
        env._obs_stats_checkpoint = env.normalizer.state_dict()
    return env.normalizer


def wrap_predictor(
    predictor: RecencyPredictor | HitHazardPredictor | None,
) -> RecencyPredictor | BuilderBackedHazardPredictor | None:
    if predictor is None:
        return None
    if isinstance(predictor, HitHazardPredictor):
        return BuilderBackedHazardPredictor(predictor)
    return predictor


def _make_bc_teacher(name: str, cfg: TrainConfig, n_bands: int) -> Any:
    key = str(name).strip().lower().replace("_", "-")
    dwell = int(cfg.default_dwell_steps)
    if key in {"sequential", "seq"}:
        return SequentialSchedule(dwell_steps=dwell)
    if key in {"reactive"}:
        return ReactiveSchedule(dwell_steps=dwell, seed=int(cfg.seed) + 17, epsilon=0.2)
    if key in {"fixed-priority", "fixed", "priority"}:
        order = tuple(int(b) for b in cfg.public_priorities if 0 <= int(b) < int(n_bands))
        if not order:
            order = (0,)
        return FixedPrioritySchedule(band_order=order, dwell_steps=dwell)
    if key in {"periodic-intercept", "periodic"}:
        return PeriodicInterceptSchedule(dwell_steps=dwell, seed=int(cfg.seed))
    raise SmartScanError(f"Unknown BC teacher {name!r}.")


def collect_teacher_actions(
    cfg: TrainConfig,
    *,
    predictor: RecencyPredictor | BuilderBackedHazardPredictor | None,
    normalizer: ObservationNormalizer,
    n_episodes: int,
    teachers: list[str],
) -> tuple[np.ndarray, np.ndarray]:
    """Roll frozen teachers in the train env. Observations stay policy-visible."""

    from smartscan.ml.actions import encode_action
    from smartscan.ml.env import SmartScanEnv
    from smartscan.rf.bands import named_band_plan

    n_bands = named_band_plan(cfg.band_plan_id).n_bands
    names = [str(item) for item in teachers if str(item).strip()]
    if not names:
        names = ["sequential"]
    env = SmartScanEnv(
        cfg,
        predictor=predictor,
        normalizer=normalizer,
        record_forecast=False,
        freeze_obs_stats=True,
        split="train",
    )
    layout = str(getattr(cfg, "action_layout", "discrete")).strip().lower()
    dwell_bins = tuple(int(x) for x in cfg.dwell_bins)
    obs_rows: list[np.ndarray] = []
    act_rows: list[np.ndarray] = []
    for episode in range(max(int(n_episodes), 1)):
        teacher = _make_bc_teacher(names[episode % len(names)], cfg, n_bands)
        obs, _info = env.reset(options={})
        done = False
        steps = 0
        while not done and steps < 4096:
            assert env._engine is not None
            view = env._engine.schedule_view(env._decision_index, cfg.default_dwell_steps)
            command = teacher.next_command(view)
            if layout == "multidiscrete":
                try:
                    dwell_index = list(dwell_bins).index(int(command.dwell_steps))
                except ValueError:
                    dwell_index = list(dwell_bins).index(int(cfg.default_dwell_steps))
                    command = command.model_copy(update={"dwell_steps": int(cfg.default_dwell_steps)})
                action: np.ndarray | int = np.asarray(
                    [int(command.target_band), int(dwell_index)], dtype=np.int64
                )
            else:
                action = encode_action(
                    int(command.target_band), int(command.dwell_steps), n_bands, dwell_bins
                )
            obs_rows.append(np.asarray(obs, dtype=np.float32))
            act_rows.append(np.asarray(action, dtype=np.int64).reshape(-1))
            obs, _reward, terminated, truncated, _info = env.step(action)
            done = bool(terminated or truncated)
            steps += 1
    if not obs_rows:
        raise SmartScanError("Behavioral cloning collected no teacher actions.")
    return np.stack(obs_rows, axis=0), np.stack(act_rows, axis=0)


def behavioral_clone_policy(
    model: Any,
    observations: np.ndarray,
    actions: np.ndarray,
    *,
    n_epochs: int,
    batch_size: int = 64,
    learning_rate: float = 3e-4,
) -> float:
    """Cross-entropy clone of teacher actions. No future / oracle labels."""

    import torch

    device = model.device
    obs_t, _vectorized = model.policy.obs_to_tensor(observations)
    act_t = torch.as_tensor(actions, device=device)
    if act_t.ndim == 1:
        act_t = act_t.view(-1)
    n_rows = int(observations.shape[0])
    opt = torch.optim.Adam(model.policy.parameters(), lr=float(learning_rate))
    last = 0.0
    epochs = max(int(n_epochs), 1)
    bs = max(int(batch_size), 1)
    for _epoch in range(epochs):
        perm = torch.randperm(n_rows, device=device)
        for start in range(0, n_rows, bs):
            index = perm[start : start + bs]
            if isinstance(obs_t, dict):
                batch_obs = {key: value[index] for key, value in obs_t.items()}
            else:
                batch_obs = obs_t[index]
            dist = model.policy.get_distribution(batch_obs)
            loss = -dist.log_prob(act_t[index]).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
            last = float(loss.detach().cpu().item())
    return last



def selection_score(metrics: dict[str, float], cfg: TrainConfig) -> float:
    """Predeclared composite used for checkpoint and candidate selection."""

    air = float(metrics.get("air") or 0.0)
    ratio = float(metrics.get("interception_ratio") or 0.0)
    delay = float(metrics.get("delay") or 0.0)
    pfa = float(metrics.get("pfa") or 0.0)
    return (
        float(cfg.selection_air_weight) * air
        + float(cfg.selection_ratio_weight) * ratio
        + float(cfg.selection_delay_weight) * delay
        + float(cfg.selection_pfa_weight) * pfa
    )


def validation_metrics(
    cfg: TrainConfig,
    *,
    predict_action: Any,
    normalizer: ObservationNormalizer,
    predictor: RecencyPredictor | BuilderBackedHazardPredictor | None,
) -> dict[str, float]:
    """Validation metrics on frozen val pairs only. Never held-out."""

    from smartscan.metrics.engine import evaluate_strategy
    from smartscan.ml.env import SmartScanEnv, episode_catalog

    pairs = episode_catalog(cfg, "val")
    if not pairs:
        return {"air": 0.0, "interception_ratio": 0.0, "delay": 0.0, "pfa": 0.0, "n": 0.0}
    airs: list[float] = []
    ratios: list[float] = []
    delays: list[float] = []
    pfas: list[float] = []
    for scenario_id, seed in pairs:
        env = SmartScanEnv(
            cfg,
            scenario_id=scenario_id,
            scenario_seed=int(seed),
            receiver_seed=int(seed),
            normalizer=normalizer,
            predictor=predictor,
            record_forecast=False,
            freeze_obs_stats=True,
            split="val",
        )
        obs, _info = env.reset(
            seed=int(seed),
            options={
                "scenario_id": scenario_id,
                "scenario_seed": int(seed),
                "receiver_seed": int(seed),
            },
        )
        done = False
        steps = 0
        while not done and steps < 4096:
            action = predict_action(obs)
            obs, _reward, terminated, truncated, _info = env.step(action)
            done = bool(terminated or truncated)
            steps += 1
        run = env.receiver_run()
        if env._truth is None:
            continue
        result = evaluate_strategy(
            env._truth, run.observations, run.decisions, receiver_config=env.receiver
        )
        item = result.report.metrics.get("average_intercept_rate")
        if item is not None and item.available and item.value is not None:
            airs.append(float(item.value))
        ratio_item = result.report.metrics.get("event_interception_ratio")
        if ratio_item is not None and ratio_item.available and ratio_item.value is not None:
            ratios.append(float(ratio_item.value))
        delay_item = result.report.metrics.get("successful_event_delay_median_s")
        if delay_item is not None and delay_item.available and delay_item.value is not None:
            delays.append(float(delay_item.value))
        pfa_item = result.report.metrics.get("pfa")
        if pfa_item is not None and pfa_item.available and pfa_item.value is not None:
            pfas.append(float(pfa_item.value))
    metrics = {
        "air": float(np.mean(airs)) if airs else 0.0,
        "interception_ratio": float(np.mean(ratios)) if ratios else 0.0,
        "delay": float(np.mean(delays)) if delays else 0.0,
        "pfa": float(np.mean(pfas)) if pfas else 0.0,
        "n": float(len(airs)),
    }
    metrics["selection_score"] = float(selection_score(metrics, cfg))
    return metrics


def validation_air(
    cfg: TrainConfig,
    *,
    predict_action: Any,
    normalizer: ObservationNormalizer,
    predictor: RecencyPredictor | BuilderBackedHazardPredictor | None,
) -> float:
    """Mean Stage 3 AIR on frozen validation (scenario, seed) pairs. Not held-out."""

    return float(
        validation_metrics(
            cfg, predict_action=predict_action, normalizer=normalizer, predictor=predictor
        ).get("air")
        or 0.0
    )


def train_ppo(
    cfg: TrainConfig,
    *,
    predictor: RecencyPredictor | HitHazardPredictor | None = None,
    normalizer: ObservationNormalizer | None = None,
    rows: list[SupervisedRow] | None = None,
) -> tuple[dict[str, Any], ObservationNormalizer, dict[str, Any]]:
    seed_ml_backends(cfg.seed)
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import BaseCallback
    from stable_baselines3.common.vec_env import DummyVecEnv

    from smartscan.ml.env import SmartScanEnv
    from smartscan.rf.bands import named_band_plan

    n_bands = named_band_plan(cfg.band_plan_id).n_bands
    wrapped = wrap_predictor(predictor)
    extras = bool(getattr(cfg, "include_predictor_obs", False)) or int(
        getattr(cfg, "include_action_history", 0) or 0
    ) > 0
    fitted_norm: ObservationNormalizer
    if normalizer is not None:
        fitted_norm = normalizer
    elif extras:
        fitted_norm = warmup_observation_normalizer(cfg, predictor=wrapped, n_episodes=4)
    elif rows:
        fitted_norm = fit_observation_normalizer(rows, n_bands, cfg)
    else:
        fitted_norm = ObservationNormalizer(size=_obs_size(cfg, n_bands))
    freeze = fitted_norm.count >= 2
    arch = [int(x) for x in cfg.ppo_net_arch] or [64, 64]
    n_steps = max(8, int(cfg.ppo_n_steps))
    batch_size = min(int(cfg.ppo_batch_size), n_steps)

    def _make() -> SmartScanEnv:
        return SmartScanEnv(
            cfg,
            predictor=wrapped,
            normalizer=fitted_norm,
            record_forecast=False,
            freeze_obs_stats=freeze,
            split="train",
        )

    n_envs = max(1, int(cfg.n_envs))
    vec = DummyVecEnv([_make for _ in range(n_envs)])
    lr = float(cfg.ppo_learning_rate)

    def _lr_schedule(progress_remaining: float) -> float:
        if int(cfg.timesteps) < 4096:
            return lr
        return float(lr * max(0.2, progress_remaining))

    model = PPO(
        "MlpPolicy",
        vec,
        learning_rate=_lr_schedule,
        n_steps=n_steps,
        batch_size=batch_size,
        n_epochs=int(cfg.ppo_n_epochs),
        gamma=float(cfg.ppo_gamma),
        gae_lambda=float(getattr(cfg, "ppo_gae_lambda", 0.95)),
        clip_range=float(getattr(cfg, "ppo_clip_range", 0.2)),
        vf_coef=float(getattr(cfg, "ppo_vf_coef", 0.5)),
        max_grad_norm=float(getattr(cfg, "ppo_max_grad_norm", 0.5)),
        ent_coef=float(cfg.ppo_ent_coef),
        seed=int(cfg.seed),
        device=str(cfg.device),
        verbose=0,
        policy_kwargs={"net_arch": dict(pi=arch, vf=arch)},
    )
    bc_loss = None
    teachers = [str(item) for item in list(getattr(cfg, "ppo_bc_teachers", None) or []) if str(item).strip()]
    bc_epochs = int(getattr(cfg, "ppo_bc_epochs", 0) or 0)
    bc_episodes = int(getattr(cfg, "ppo_bc_episodes", 0) or 0)
    if bc_epochs > 0 and bc_episodes > 0:
        teacher_obs, teacher_act = collect_teacher_actions(
            cfg,
            predictor=wrapped,
            normalizer=fitted_norm,
            n_episodes=bc_episodes,
            teachers=teachers or ["sequential", "reactive"],
        )
        bc_loss = behavioral_clone_policy(
            model,
            teacher_obs,
            teacher_act,
            n_epochs=bc_epochs,
            batch_size=min(64, max(8, teacher_obs.shape[0])),
            learning_rate=float(cfg.ppo_learning_rate),
        )
        print(
            f"bc_teachers={teachers or ['sequential', 'reactive']} "
            f"n={teacher_obs.shape[0]} loss={bc_loss:.4f}",
            flush=True,
        )

    cadence = int(cfg.eval_cadence)
    patience = int(cfg.early_stopping_patience)
    history: list[dict[str, float]] = []
    train_logs: list[dict[str, float]] = []
    best_score = -1e18
    best_air = -1e18
    best_state: dict[str, Any] | None = None
    stale = 0

    class _ValCallback(BaseCallback):
        def __init__(self) -> None:
            super().__init__()
            self._next = cadence if cadence > 0 else 10**18

        def _on_rollout_end(self) -> None:
            names = getattr(self.model.logger, "name_to_value", {}) or {}
            rec = {
                str(k): float(v)
                for k, v in names.items()
                if str(k).startswith("train/") and v == v
            }
            rec["timestep"] = float(self.num_timesteps)
            train_logs.append(rec)

        def _on_step(self) -> bool:
            nonlocal best_air, best_score, best_state, stale
            if cadence <= 0 or self.num_timesteps < self._next:
                return True
            self._next = self.num_timesteps + cadence

            def _act(obs: np.ndarray) -> Any:
                action, _st = self.model.predict(obs, deterministic=True)
                arr = np.asarray(action).reshape(-1)
                if str(getattr(cfg, "action_layout", "discrete")) == "multidiscrete":
                    return arr
                return int(arr[0])

            metrics = validation_metrics(
                cfg, predict_action=_act, normalizer=fitted_norm, predictor=wrapped
            )
            score = float(metrics["selection_score"])
            air = float(metrics["air"])
            row = {"timestep": float(self.num_timesteps), **metrics}
            history.append(row)
            improved = score > best_score + 1e-12
            if improved:
                best_score = score
                best_air = air
                best_state = {
                    k: v.detach().cpu().clone() for k, v in self.model.policy.state_dict().items()
                }
                stale = 0
            else:
                stale += 1
            print(
                f"val_step={int(self.num_timesteps)} val_air={air:.6g} "
                f"val_score={score:.6g} best_val_air={best_air:.6g} stale={stale}",
                flush=True,
            )
            if patience > 0 and stale >= patience:
                print(f"early_stop_patience={patience} at step={int(self.num_timesteps)}", flush=True)
                return False
            return True

    model.learn(
        total_timesteps=int(cfg.timesteps),
        progress_bar=False,
        callback=_ValCallback() if cadence > 0 else None,
    )
    if best_state is not None:
        model.policy.load_state_dict(best_state)
        state = best_state
        selected = "best_validation"
    else:
        state = {k: v.detach().cpu() for k, v in model.policy.state_dict().items()}
        selected = "final"
    meta = {
        "val_curve": history,
        "train_logs": train_logs,
        "best_val_air": None if best_air < -1e17 else best_air,
        "best_val_score": None if best_score < -1e17 else best_score,
        "checkpoint": selected,
        "timesteps_requested": int(cfg.timesteps),
        "timesteps_completed": int(model.num_timesteps),
        "n_val_evals": len(history),
        "normalizer_count": int(fitted_norm.count),
        "freeze_obs_stats": freeze,
        "ent_coef": float(cfg.ppo_ent_coef),
        "net_arch": arch,
        "action_layout": str(getattr(cfg, "action_layout", "discrete")),
        "early_stopping_patience": patience,
        "checkpoint_rule": "best_validation_composite_then_restore",
        "selection_weights": {
            "air": float(cfg.selection_air_weight),
            "ratio": float(cfg.selection_ratio_weight),
            "delay": float(cfg.selection_delay_weight),
            "pfa": float(cfg.selection_pfa_weight),
        },
        "bc_loss": bc_loss,
        "bc_teachers": teachers,
        "bc_epochs": bc_epochs,
        "bc_episodes": bc_episodes,
    }
    vec.close()
    return state, fitted_norm, meta


def build_and_save_bundle(
    cfg: TrainConfig,
    *,
    predictor: HitHazardPredictor | None,
    hit_cal: IsotonicCalibrator,
    act_cal: IsotonicCalibrator,
    cts: ContextualThompsonSchedule | None,
    ppo_state: dict[str, Any] | None,
    normalizer: ObservationNormalizer,
    dest: Path,
) -> dict[str, str]:
    plan = named_band_plan(cfg.band_plan_id)
    payload = dict(
        __import__("smartscan.config", fromlist=["load_yaml"]).load_yaml(
            project_root() / cfg.receiver_config
        )
    )
    ibw = float(payload["receiver_ibw_hz"])
    bundle = SchedulerBundle(
        band_plan=plan,
        dwell_bins=tuple(int(x) for x in cfg.dwell_bins),
        receiver_ibw_hz=ibw,
        feature_schema_payload=feature_schema(
            plan.n_bands,
            tuple(int(x) for x in cfg.dwell_bins),
            predictor_obs=bool(getattr(cfg, "include_predictor_obs", False)),
            action_history=int(getattr(cfg, "include_action_history", 0) or 0),
        ),
        predictor=predictor,
        recency_ok=True,
        hit_calibrator=hit_cal,
        active_calibrator=act_cal,
        normalizer=normalizer,
        cts=cts,
        ppo_state=ppo_state,
        config=cfg.model_dump(),
        model_version=cfg.model_version,
    )
    dest.mkdir(parents=True, exist_ok=True)
    return save_bundle(bundle, dest)
