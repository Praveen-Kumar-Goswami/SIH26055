"""Fixed-size observable feature vectors with explicit missingness masks."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from smartscan.ml.novelty import AgilityEstimator, NoveltyEstimator, assess_threat
from smartscan.ml.observable import ObservableTransition
from smartscan.ml.periodicity import PeriodicityEstimator
from smartscan.types import SmartScanError, content_fingerprint

FEATURE_SCHEMA_VERSION = "1.0.0"

PER_BAND_FIELDS: tuple[str, ...] = (
    "t_since_visit",
    "m_visit",
    "t_since_hit",
    "m_hit",
    "last_outcome",
    "ewma_hit",
    "miss_streak",
    "hit_count",
    "snr_ewma",
    "m_snr",
    "visit_count",
    "recent_dwell",
    "period_s",
    "phase_to_next",
    "period_conf",
    "agility_score",
    "novelty",
    "threat",
)

GLOBAL_FIELDS: tuple[str, ...] = (
    "settled_band_norm",
    "last_band_norm",
    "elapsed_fraction",
    "last_dwell_norm",
    "remaining_horizon_norm",
)


def observation_size(
    n_bands: int,
    *,
    predictor_obs: bool = False,
    action_history: int = 0,
) -> int:
    size = int(n_bands) * (len(PER_BAND_FIELDS) + 1) + len(GLOBAL_FIELDS)
    if predictor_obs:
        size += int(n_bands) * 3 + 1
    size += max(int(action_history), 0) * 2
    return size


def observation_size_from_flags(
    n_bands: int,
    *,
    include_predictor_obs: bool = False,
    include_action_history: int = 0,
) -> int:
    return observation_size(
        n_bands,
        predictor_obs=bool(include_predictor_obs),
        action_history=int(include_action_history),
    )


def feature_schema(
    n_bands: int,
    dwell_bins: tuple[int, ...],
    *,
    predictor_obs: bool = False,
    action_history: int = 0,
) -> dict[str, object]:
    return {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "n_bands": int(n_bands),
        "dwell_bins": list(dwell_bins),
        "per_band_fields": list(PER_BAND_FIELDS),
        "global_fields": list(GLOBAL_FIELDS),
        "includes_tune_cost_per_band": True,
        "predictor_obs": bool(predictor_obs),
        "action_history": int(action_history),
        "size": observation_size(
            n_bands, predictor_obs=predictor_obs, action_history=action_history
        ),
    }


@dataclass
class _BandMemory:
    last_visit_step: int | None = None
    last_hit_step: int | None = None
    last_outcome: float = 0.0
    ewma_hit: float = 0.0
    miss_streak: float = 0.0
    hit_count: float = 0.0
    visit_count: float = 0.0
    snr_ewma: float = 0.0
    snr_seen: bool = False
    recent_dwell: float = 0.0


@dataclass
class FeatureBuilder:
    """Causal per-band features. ``observe`` must only be called with past commands."""

    n_bands: int
    dt_s: float
    dwell_bins: tuple[int, ...]
    ewma_alpha: float = 0.3
    tune_latency_steps: int = 1
    max_dwell: int = 16
    ablate_periodicity: bool = False
    ablate_novelty: bool = False
    public_priorities: dict[int, float] = field(default_factory=dict)
    bands: list[_BandMemory] = field(init=False)
    periodicity: PeriodicityEstimator = field(init=False)
    agility: AgilityEstimator = field(init=False)
    novelty_est: NoveltyEstimator = field(init=False)
    last_step: int = 0
    recent_actions: deque[tuple[float, float]] = field(init=False)

    def __post_init__(self) -> None:
        if self.n_bands <= 0:
            raise SmartScanError("FeatureBuilder.n_bands must be positive.")
        self.bands = [_BandMemory() for _ in range(self.n_bands)]
        self.periodicity = PeriodicityEstimator(dt_s=self.dt_s)
        self.agility = AgilityEstimator(n_bands=self.n_bands)
        self.novelty_est = NoveltyEstimator(n_bands=self.n_bands)
        self.max_dwell = max(int(self.max_dwell), max(self.dwell_bins) if self.dwell_bins else 1)
        self.recent_actions = deque(maxlen=8)

    def reset(self) -> None:
        self.__post_init__()
        self.last_step = 0

    def snapshot(self) -> FeatureBuilder:
        out = FeatureBuilder(
            n_bands=self.n_bands,
            dt_s=self.dt_s,
            dwell_bins=self.dwell_bins,
            ewma_alpha=self.ewma_alpha,
            tune_latency_steps=self.tune_latency_steps,
            max_dwell=self.max_dwell,
            ablate_periodicity=self.ablate_periodicity,
            ablate_novelty=self.ablate_novelty,
            public_priorities=dict(self.public_priorities),
        )
        out.bands = [
            _BandMemory(
                last_visit_step=item.last_visit_step,
                last_hit_step=item.last_hit_step,
                last_outcome=item.last_outcome,
                ewma_hit=item.ewma_hit,
                miss_streak=item.miss_streak,
                hit_count=item.hit_count,
                visit_count=item.visit_count,
                snr_ewma=item.snr_ewma,
                snr_seen=item.snr_seen,
                recent_dwell=item.recent_dwell,
            )
            for item in self.bands
        ]
        out.periodicity = self.periodicity.snapshot()
        out.agility = self.agility.snapshot()
        out.novelty_est = self.novelty_est.snapshot()
        out.last_step = self.last_step
        out.recent_actions = deque(self.recent_actions, maxlen=8)
        return out

    def observe(self, transition: ObservableTransition) -> None:
        band = int(transition.target_band)
        if band < 0 or band >= self.n_bands:
            raise SmartScanError(f"Observable band {band} outside 0..{self.n_bands - 1}.")
        mem = self.bands[band]
        alpha = float(self.ewma_alpha)
        mem.last_visit_step = int(transition.end_step)
        mem.visit_count += 1.0
        mem.recent_dwell = 0.7 * mem.recent_dwell + 0.3 * (
            float(transition.dwell_steps) / float(self.max_dwell)
        )
        hit = 1.0 if transition.hit else 0.0
        mem.ewma_hit = (1.0 - alpha) * mem.ewma_hit + alpha * hit
        mem.last_outcome = 1.0 if transition.hit else -1.0
        if transition.hit:
            mem.last_hit_step = int(transition.end_step)
            mem.hit_count += 1.0
            mem.miss_streak = 0.0
            self.periodicity.observe_hit(band, float(transition.end_step) * self.dt_s)
            self.agility.observe_hit(band)
        else:
            mem.miss_streak += 1.0
        if transition.measured_snr_db is not None and np.isfinite(transition.measured_snr_db):
            if not mem.snr_seen:
                mem.snr_ewma = float(transition.measured_snr_db)
                mem.snr_seen = True
            else:
                mem.snr_ewma = (1.0 - alpha) * mem.snr_ewma + alpha * float(
                    transition.measured_snr_db
                )
        self.novelty_est.observe(
            band=band,
            hit=bool(transition.hit),
            time_s=float(transition.end_step) * self.dt_s,
            snr_db=transition.measured_snr_db,
        )
        band_norm = float(band) / float(max(self.n_bands - 1, 1))
        self.recent_actions.append((band_norm, 1.0 if transition.hit else -1.0))
        self.last_step = int(transition.end_step)

    def action_history_features(self, k: int) -> np.ndarray:
        """Last *k* observable (band_norm, hit_sign) pairs. Causal; padded with -1/0."""

        k_i = max(int(k), 0)
        if k_i == 0:
            return np.zeros((0,), dtype=np.float32)
        out = np.zeros(k_i * 2, dtype=np.float32)
        out[0::2] = -1.0
        items = list(self.recent_actions)[-k_i:]
        start = k_i - len(items)
        for i, (band_norm, hit_sign) in enumerate(items):
            out[(start + i) * 2] = float(band_norm)
            out[(start + i) * 2 + 1] = float(hit_sign)
        return out

    def vector(
        self,
        *,
        step: int,
        n_steps: int,
        settled_band: int | None,
        last_target_band: int | None,
        last_dwell_steps: int | None,
    ) -> np.ndarray:
        n_steps_i = max(int(n_steps), 1)
        now = int(step)
        now_s = float(now) * self.dt_s
        agility = self.agility.next_scores()
        parts: list[float] = []
        for band, mem in enumerate(self.bands):
            last_visit = mem.last_visit_step
            t_visit = float(now - last_visit) / float(n_steps_i) if last_visit is not None else 1.0
            last_hit = mem.last_hit_step
            hit_seen = last_hit is not None
            t_hit = float(now - last_hit) / float(n_steps_i) if last_hit is not None else 1.0
            period_s, phase, conf = (0.0, 0.0, 0.0)
            if not self.ablate_periodicity:
                period_s, phase, conf = self.periodicity.estimate(band, now_s)
            novelty = 0.0 if self.ablate_novelty else self.novelty_est.score(
                band=band, snr_db=mem.snr_ewma if mem.snr_seen else None, time_s=now_s
            )
            catalog = self.public_priorities.get(band)
            threat = assess_threat(public_catalog_priority=catalog, novelty=novelty)
            parts.extend(
                [
                    float(np.clip(t_visit, 0.0, 1.0)),
                    0.0 if last_visit is not None else 1.0,
                    float(np.clip(t_hit, 0.0, 1.0)),
                    0.0 if hit_seen else 1.0,
                    float(mem.last_outcome),
                    float(mem.ewma_hit),
                    float(mem.miss_streak) / 16.0,
                    float(mem.hit_count) / 16.0,
                    float(mem.snr_ewma) / 20.0 if mem.snr_seen else 0.0,
                    0.0 if mem.snr_seen else 1.0,
                    float(mem.visit_count) / 16.0,
                    float(mem.recent_dwell),
                    float(period_s) / 2.0,
                    float(phase) / 2.0,
                    float(conf),
                    float(agility[band]),
                    float(novelty),
                    float(threat) / 10.0,
                ]
            )
        for band in range(self.n_bands):
            need_tune = settled_band is None or int(settled_band) != band
            cost = float(self.tune_latency_steps) / float(n_steps_i) if need_tune else 0.0
            parts.append(cost)
        last_dwell = 0.0 if last_dwell_steps is None else float(last_dwell_steps) / float(self.max_dwell)
        parts.extend(
            [
                -1.0 if settled_band is None else float(settled_band) / float(max(self.n_bands - 1, 1)),
                -1.0
                if last_target_band is None
                else float(last_target_band) / float(max(self.n_bands - 1, 1)),
                float(now) / float(n_steps_i),
                last_dwell,
                float(max(0, n_steps_i - now)) / float(n_steps_i),
            ]
        )
        vec = np.asarray(parts, dtype=np.float32)
        if vec.shape != (observation_size(self.n_bands),):
            raise SmartScanError(
                f"Feature vector shape {vec.shape} != {(observation_size(self.n_bands),)}"
            )
        if not np.all(np.isfinite(vec)):
            raise SmartScanError("Feature vector contains NaN or Inf.")
        return vec

    def schema_fingerprint(self) -> str:
        return content_fingerprint(feature_schema(self.n_bands, self.dwell_bins))


def recency_predictor_obs(builder: FeatureBuilder) -> np.ndarray:
    """Per-band recency q_hit / p_active proxy / uncertainty plus global confidence."""

    n = int(builder.n_bands)
    q_hit = np.zeros(n, dtype=np.float32)
    p_active = np.zeros(n, dtype=np.float32)
    unc = np.ones(n, dtype=np.float32)
    for i, mem in enumerate(builder.bands):
        if mem.visit_count > 0:
            q = float(np.clip(mem.ewma_hit, 0.0, 1.0))
            q_hit[i] = q
            p_active[i] = q
            unc[i] = float(np.clip(1.0 - q, 0.0, 1.0))
    confidence = float(np.clip(1.0 - float(np.mean(unc)), 0.0, 1.0))
    return np.concatenate([q_hit, p_active, unc, np.asarray([confidence], dtype=np.float32)])


def compose_observation(
    builder: FeatureBuilder,
    *,
    step: int,
    n_steps: int,
    settled_band: int | None,
    last_target_band: int | None,
    last_dwell_steps: int | None,
    predictor: Any | None = None,
    include_predictor_obs: bool = False,
    include_action_history: int = 0,
    default_dwell_steps: int = 8,
    include_neural_predictor_obs: bool = False,
) -> np.ndarray:
    """Policy observation: base features plus optional causal extras.

    Predictor extras use only current FeatureBuilder state and a forecast of
    the *next* dwell. No occupancy, emitter IDs, or future hits.
    """

    base = builder.vector(
        step=int(step),
        n_steps=int(n_steps),
        settled_band=settled_band,
        last_target_band=last_target_band,
        last_dwell_steps=last_dwell_steps,
    )
    chunks: list[np.ndarray] = [np.asarray(base, dtype=np.float32)]
    history_k = max(int(include_action_history), 0)
    if history_k:
        chunks.append(builder.action_history_features(history_k))
    if include_predictor_obs:
        extra = recency_predictor_obs(builder)
        if include_neural_predictor_obs:
            neural = _neural_predictor_obs(
                predictor,
                builder,
                step=int(step),
                n_steps=int(n_steps),
                settled_band=settled_band,
                last_target_band=last_target_band,
                last_dwell_steps=last_dwell_steps,
                default_dwell_steps=int(default_dwell_steps),
            )
            if neural is not None:
                extra = neural
        chunks.append(np.asarray(extra, dtype=np.float32))
    vec = np.concatenate(chunks).astype(np.float32, copy=False)
    expected = observation_size(
        builder.n_bands,
        predictor_obs=bool(include_predictor_obs),
        action_history=history_k,
    )
    if vec.shape != (expected,):
        raise SmartScanError(f"Composed observation shape {vec.shape} != {(expected,)}")
    if not np.all(np.isfinite(vec)):
        raise SmartScanError("Composed observation contains NaN or Inf.")
    return vec


def _neural_predictor_obs(
    predictor: Any,
    builder: FeatureBuilder,
    *,
    step: int,
    n_steps: int,
    settled_band: int | None,
    last_target_band: int | None,
    last_dwell_steps: int | None,
    default_dwell_steps: int,
) -> np.ndarray | None:
    if predictor is None:
        return None
    dwell = int(last_dwell_steps) if last_dwell_steps is not None else int(default_dwell_steps)
    if dwell not in builder.dwell_bins:
        dwell = int(builder.dwell_bins[min(len(builder.dwell_bins) - 1, 0)])
    inner = getattr(predictor, "inner", predictor)
    forecast_all = getattr(inner, "forecast_all_bands", None)
    if callable(forecast_all):
        feats = builder.vector(
            step=int(step),
            n_steps=int(n_steps),
            settled_band=settled_band,
            last_target_band=last_target_band,
            last_dwell_steps=last_dwell_steps,
        )
        q_hit, p_active, unc = forecast_all(
            feats,
            dwell_steps=dwell,
            proposed_schedule=[(0, dwell)],
            horizon_s=float(max(int(n_steps) - int(step), 1)) * float(builder.dt_s),
            dt_s=float(builder.dt_s),
            start_step=int(step),
            builder=builder,
            settled_band=settled_band,
        )
        conf = float(np.clip(1.0 - float(np.mean(unc)), 0.0, 1.0))
        return np.concatenate(
            [
                np.asarray(q_hit, dtype=np.float32),
                np.asarray(p_active, dtype=np.float32),
                np.asarray(unc, dtype=np.float32),
                np.asarray([conf], dtype=np.float32),
            ]
        )
    forecast = getattr(predictor, "forecast_next_intercept", None)
    if not callable(forecast):
        return None
    q_hit_v: list[float] = []
    p_active_v: list[float] = []
    unc_v: list[float] = []
    for band in range(builder.n_bands):
        try:
            fc = forecast(
                builder,
                band=int(band),
                dwell_steps=dwell,
                proposed_schedule=[(int(band), dwell)],
                horizon_s=float(max(int(n_steps) - int(step), 1)) * float(builder.dt_s),
                pfa=1e-3,
                dt_s=float(builder.dt_s),
                step=int(step),
                n_steps=int(n_steps),
                settled_band=settled_band,
                last_target_band=last_target_band,
                last_dwell_steps=last_dwell_steps,
            )
        except TypeError:
            return None
        q_hit_v.append(float(np.clip(fc.p_hit_within_dwell, 0.0, 1.0)))
        raw_act = fc.p_active
        p_active_v.append(float(np.clip(raw_act if raw_act is not None else q_hit_v[-1], 0.0, 1.0)))
        unc_v.append(float(np.clip(fc.uncertainty, 0.0, 1.0)))
    conf = float(np.clip(1.0 - float(np.mean(unc_v)), 0.0, 1.0))
    return np.concatenate(
        [
            np.asarray(q_hit_v, dtype=np.float32),
            np.asarray(p_active_v, dtype=np.float32),
            np.asarray(unc_v, dtype=np.float32),
            np.asarray([conf], dtype=np.float32),
        ]
    )


class ObservationNormalizer:
    """Running mean/std saved in the model bundle. Zero-std channels stay 0."""

    def __init__(self, size: int, clip: float = 10.0) -> None:
        self.size = int(size)
        self.clip = float(clip)
        self.count = 0
        self.mean = np.zeros(self.size, dtype=np.float64)
        self.m2 = np.zeros(self.size, dtype=np.float64)

    def update(self, vector: np.ndarray) -> None:
        x = np.asarray(vector, dtype=np.float64).reshape(-1)
        if x.size != self.size:
            raise SmartScanError(f"Normalizer expected size {self.size}, got {x.size}.")
        self.count += 1
        delta = x - self.mean
        self.mean += delta / float(self.count)
        delta2 = x - self.mean
        self.m2 += delta * delta2

    def transform(self, vector: np.ndarray) -> np.ndarray:
        x = np.asarray(vector, dtype=np.float64).reshape(-1)
        if not np.all(np.isfinite(x)):
            raise SmartScanError("Normalizer input contains NaN/Inf.")
        if self.count < 2:
            out = np.clip(x, -self.clip, self.clip)
            return np.asarray(out, dtype=np.float32)
        var = self.m2 / float(self.count - 1)
        std = np.sqrt(np.maximum(var, 1e-8))
        z = (x - self.mean) / std
        return np.asarray(np.clip(z, -self.clip, self.clip), dtype=np.float32)

    def state_dict(self) -> dict[str, np.ndarray | int | float]:
        return {
            "size": self.size,
            "clip": self.clip,
            "count": self.count,
            "mean": self.mean.copy(),
            "m2": self.m2.copy(),
        }

    @classmethod
    def from_state(cls, payload: dict[str, Any]) -> ObservationNormalizer:
        inst = cls(size=int(payload["size"]), clip=float(payload["clip"]))
        inst.count = int(payload["count"])
        inst.mean = np.array(payload["mean"], dtype=np.float64, copy=True)
        inst.m2 = np.array(payload["m2"], dtype=np.float64, copy=True)
        return inst
