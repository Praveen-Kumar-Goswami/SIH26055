"""Train/validation-only diagnostics. Never reads the held-out manifest."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import numpy as np

from smartscan.config import SimulateConfig, TrainConfig, load_yaml, project_root
from smartscan.metrics.engine import evaluate_strategy
from smartscan.ml.calibrate import brier_score, expected_calibration_error
from smartscan.ml.env import episode_catalog
from smartscan.ml.policies import make_policy
from smartscan.ml.protocol import assert_no_held_out_seeds
from smartscan.ml.runner import run_policy_episode
from smartscan.receiver.detector import load_receiver_config
from smartscan.rf.environment import simulate


def _receiver(cfg: TrainConfig) -> Any:
    payload = dict(load_yaml(project_root() / cfg.receiver_config))
    payload["dwell_bins"] = list(cfg.dwell_bins)
    payload["noise_power_w"] = float(cfg.noise_power_w)
    return load_receiver_config(payload)


def _entropy(counts: Counter[int]) -> float:
    if not counts:
        return 0.0
    arr = np.asarray(list(counts.values()), dtype=np.float64)
    p = arr / max(float(arr.sum()), 1e-12)
    return float(-np.sum(p * np.log(p + 1e-12)))


def _metric(result: Any, key: str) -> float | None:
    item = result.report.metrics.get(key)
    if item is None or not item.available or item.value is None:
        return None
    return float(item.value)


def diagnose_split(
    cfg: TrainConfig,
    *,
    split: str = "train",
    strategies: list[str] | None = None,
    ppo_predict: Any | None = None,
    feature_builder_factory: Any | None = None,
    predictor: Any | None = None,
) -> dict[str, Any]:
    """Summarize baselines on a frozen train or val catalog. Not held-out."""

    pairs = episode_catalog(cfg, split)
    assert_no_held_out_seeds(pairs, where=f"diagnose:{split}")
    if not pairs:
        return {"split": split, "n_pairs": 0, "strategies": {}, "by_family": {}}
    receiver = _receiver(cfg)
    names = list(
        strategies
        or ["sequential", "random", "fixed-priority", "reactive", "contextual-thompson"]
    )
    if ppo_predict is not None and "ppo" not in names:
        names.append("ppo")
    out: dict[str, Any] = {"split": split, "n_pairs": len(pairs), "strategies": {}, "by_family": {}}
    family_store: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for name in names:
        airs: list[float] = []
        ratios: list[float] = []
        delays: list[float] = []
        pds: list[float] = []
        pfas: list[float] = []
        returns: list[float] = []
        bands: Counter[int] = Counter()
        dwells: Counter[int] = Counter()
        hits_by_band: Counter[int] = Counter()
        visits_by_band: Counter[int] = Counter()
        hits = 0
        n_dec = 0
        unique_bands_ep: list[int] = []
        streaks: list[int] = []
        reward_hit = 0.0
        reward_priority = 0.0
        cost_tune = 0.0
        cost_time = 0.0
        cost_repeat = 0.0
        cost_false = 0.0
        p_hit_pred: list[float] = []
        p_hit_y: list[float] = []
        explore_hits = 0
        exploit_hits = 0
        n_tune_steps = 0
        n_obs_steps = 0
        wasted = 0.0
        n_wasted = 0
        for scenario_id, seed in pairs:
            truth = simulate(
                SimulateConfig(
                    seed=int(seed),
                    dt_s=cfg.dt_s,
                    duration_s=cfg.duration_s,
                    band_plan_id=cfg.band_plan_id,
                    scenario_id=scenario_id,
                )
            )
            fb = feature_builder_factory() if feature_builder_factory is not None else None
            schedule = make_policy(
                name,
                dwell_steps=cfg.default_dwell_steps,
                schedule_seed=int(seed),
                band_order=tuple(cfg.public_priorities),
                n_bands=truth.band_plan.n_bands,
                dwell_bins=tuple(int(x) for x in cfg.dwell_bins),
                ppo_predict=ppo_predict if name == "ppo" else None,
                feature_builder=fb if name == "ppo" else None,
                predictor=predictor if name == "ppo" else None,
                include_predictor_obs=bool(getattr(cfg, "include_predictor_obs", False))
                if name == "ppo"
                else False,
                include_action_history=int(getattr(cfg, "include_action_history", 0) or 0)
                if name == "ppo"
                else 0,
                include_neural_predictor_obs=bool(
                    getattr(cfg, "include_neural_predictor_obs", False)
                )
                if name == "ppo"
                else False,
            )
            run = run_policy_episode(
                truth,
                schedule,
                receiver,
                cfg=cfg,
                receiver_seed=int(seed),
                record_horizon=False,
                predictor=predictor if name == "ppo" else None,
            )
            result = evaluate_strategy(
                truth, run.observations, run.decisions, receiver_config=receiver
            )
            air_v = _metric(result, "average_intercept_rate")
            ratio_v = _metric(result, "event_interception_ratio")
            delay_v = _metric(result, "successful_event_delay_median_s")
            pd_v = _metric(result, "pd")
            pfa_v = _metric(result, "pfa")
            if air_v is not None:
                airs.append(air_v)
                family_store[scenario_id][f"{name}:air"].append(air_v)
            if ratio_v is not None:
                ratios.append(ratio_v)
                family_store[scenario_id][f"{name}:ratio"].append(ratio_v)
            if delay_v is not None:
                delays.append(delay_v)
            if pd_v is not None:
                pds.append(pd_v)
            if pfa_v is not None:
                pfas.append(pfa_v)
            wasted_v = _metric(result, "wasted_dwell_fraction")
            if wasted_v is not None:
                wasted += wasted_v
                n_wasted += 1
            n_tune_steps += sum(1 for row in run.observations.rows if row.receiver_state == "TUNING")
            n_obs_steps += len(run.observations.rows)
            ep_return = 0.0
            ep_bands: set[int] = set()
            last_band: int | None = None
            streak = 1
            for row in run.decisions.rows:
                band = int(row.target_band)
                bands[band] += 1
                dwells[int(row.dwell_steps)] += 1
                visits_by_band[band] += 1
                n_dec += 1
                hits += int(bool(row.hit))
                if row.hit:
                    hits_by_band[band] += 1
                ep_bands.add(band)
                ep_return += float(row.reward or 0.0)
                reward_hit += float(row.reward_hit or 0.0)
                reward_priority += float(row.reward_priority or 0.0)
                cost_tune += float(row.cost_tune_s or 0.0)
                cost_time += float(row.cost_time_s or 0.0)
                cost_repeat += float(row.cost_repeat or 0.0)
                cost_false += float(row.cost_false_like or 0.0)
                if row.p_hit is not None:
                    p_hit_pred.append(float(row.p_hit))
                    p_hit_y.append(1.0 if row.hit else 0.0)
                if last_band is None:
                    last_band = band
                elif band == last_band:
                    streak += 1
                else:
                    streaks.append(streak)
                    streak = 1
                    last_band = band
                if last_band is not None and band != last_band:
                    if row.hit:
                        explore_hits += 1
                elif row.hit:
                    exploit_hits += 1
            streaks.append(streak)
            unique_bands_ep.append(len(ep_bands))
            returns.append(ep_return)
        denom = max(n_dec, 1)
        hit_per_band = {
            str(band): (hits_by_band[band] / max(visits_by_band[band], 1))
            for band in sorted(visits_by_band)
        }
        out["strategies"][name] = {
            "mean_air": float(np.mean(airs)) if airs else None,
            "median_air": float(np.median(airs)) if airs else None,
            "mean_interception_ratio": float(np.mean(ratios)) if ratios else None,
            "mean_delay": float(np.mean(delays)) if delays else None,
            "mean_pd": float(np.mean(pds)) if pds else None,
            "mean_pfa": float(np.mean(pfas)) if pfas else None,
            "mean_episode_return": float(np.mean(returns)) if returns else None,
            "hit_rate": hits / denom,
            "n_decisions": n_dec,
            "dwell_hist": {str(k): int(v) for k, v in sorted(dwells.items())},
            "top_bands": {str(k): int(v) for k, v in bands.most_common(8)},
            "band_visit_entropy": _entropy(bands),
            "dwell_entropy": _entropy(dwells),
            "mean_unique_bands": float(np.mean(unique_bands_ep)) if unique_bands_ep else 0.0,
            "mean_repeat_streak": float(np.mean(streaks)) if streaks else 0.0,
            "hit_rate_per_visited_band": hit_per_band,
            "mean_reward_hit": reward_hit / denom,
            "mean_reward_priority": reward_priority / denom,
            "mean_cost_tune": cost_tune / denom,
            "mean_cost_time": cost_time / denom,
            "mean_cost_repeat": cost_repeat / denom,
            "mean_cost_false": cost_false / denom,
            "reward_hit_total": reward_hit,
            "reward_priority_total": reward_priority,
            "cost_tune_total": cost_tune,
            "cost_time_total": cost_time,
            "cost_repeat_total": cost_repeat,
            "cost_false_total": cost_false,
            "tuning_fraction": n_tune_steps / max(n_obs_steps, 1),
            "wasted_scan_fraction": wasted / max(n_wasted, 1) if n_wasted else None,
            "hits_following_exploration": explore_hits,
            "hits_following_exploitation": exploit_hits,
            "p_hit_brier": brier_score(np.asarray(p_hit_pred), np.asarray(p_hit_y))
            if p_hit_pred
            else None,
            "p_hit_ece": expected_calibration_error(np.asarray(p_hit_pred), np.asarray(p_hit_y))
            if p_hit_pred
            else None,
        }
    family_out: dict[str, dict[str, dict[str, float]]] = {}
    for family, metrics in family_store.items():
        family_out[family] = {}
        for key, values in metrics.items():
            strategy, metric = key.split(":", 1)
            family_out[family].setdefault(strategy, {})[metric] = float(np.mean(values))
    out["by_family"] = family_out
    return out
