"""Censored completed-command hit-hazard predictor and recency baseline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from smartscan.ml.calibrate import IsotonicCalibrator
from smartscan.ml.features import FeatureBuilder
from smartscan.receiver.detector import analytic_pd
from smartscan.types import SmartScanError

MODEL_EPS = 1e-8


def survival_nll(
    hazards: np.ndarray,
    event_index: int | None,
    *,
    n_bins: int | None = None,
) -> float:
    """Masked discrete-time survival NLL.

    ``event_index`` is the first completed-hit command (0-based). ``None`` is a
    right-censor at the declared horizon. Unobserved bands are not encoded here;
    callers simply omit those rows.
    """

    h = np.clip(np.asarray(hazards, dtype=np.float64).reshape(-1), MODEL_EPS, 1.0 - MODEL_EPS)
    j_max = int(h.size if n_bins is None else min(n_bins, h.size))
    h = h[:j_max]
    if event_index is None:
        # Right-censor: survive all bins.
        return float(-np.sum(np.log(1.0 - h)))
    e = int(event_index)
    if e < 0 or e >= j_max:
        raise SmartScanError(f"event_index {e} is outside hazard bins 0..{j_max - 1}.")
    loss = -np.log(h[e])
    if e > 0:
        loss = loss - np.sum(np.log(1.0 - h[:e]))
    return float(loss)


def expected_time_to_hit(
    hazards: np.ndarray,
    completion_time_s: np.ndarray,
) -> tuple[float, float]:
    """E[t_next|hit] and survival mass 1-S[J] from discrete hazards."""

    h = np.clip(np.asarray(hazards, dtype=np.float64).reshape(-1), 0.0, 1.0)
    t = np.asarray(completion_time_s, dtype=np.float64).reshape(-1)
    if h.size != t.size or h.size == 0:
        raise SmartScanError("hazards and completion_time_s must align and be nonempty.")
    survival_prev = 1.0
    expected = 0.0
    hit_mass = 0.0
    for j in range(h.size):
        contrib = float(h[j]) * survival_prev
        expected += float(t[j]) * contrib
        hit_mass += contrib
        survival_prev *= 1.0 - float(h[j])
    denom = max(hit_mass, MODEL_EPS)
    return float(expected / denom), float(hit_mass)


def derive_p_active(
    p_hit: float,
    *,
    pd_operating: float,
    pfa: float,
) -> tuple[float | None, str | None]:
    """p_active = clip((p_hit - Pfa) / max(Pd - Pfa, eps), 0, 1). Distinct from p_hit."""

    if pd_operating <= pfa:
        return None, "pd_operating_leq_pfa"
    raw = (float(p_hit) - float(pfa)) / max(float(pd_operating) - float(pfa), MODEL_EPS)
    return float(np.clip(raw, 0.0, 1.0)), None


@dataclass
class ForecastResult:
    p_hit_within_dwell: float
    p_active: float | None
    p_active_unavailable_reason: str | None
    time_to_next_completed_intercept_s: float
    right_censor_horizon_s: float
    uncertainty: float
    model_version: str
    hazards: np.ndarray


class RecencyPredictor:
    """Non-neural EWMA/recency baseline. Required forecast baseline."""

    def __init__(self, n_bands: int, horizon_s: float, model_version: str = "recency-v1") -> None:
        self.n_bands = int(n_bands)
        self.horizon_s = float(horizon_s)
        self.model_version = model_version

    def forecast_next_intercept(
        self,
        builder: FeatureBuilder,
        *,
        band: int,
        dwell_steps: int,
        proposed_schedule: list[tuple[int, int]],
        horizon_s: float,
        pfa: float,
        pd_operating: float | None = None,
        dt_s: float,
        step: int,
        n_steps: int,
        settled_band: int | None,
        last_target_band: int | None,
        last_dwell_steps: int | None,
    ) -> ForecastResult:
        mem = builder.bands[int(band)]
        q_hit = float(np.clip(mem.ewma_hit if mem.visit_count > 0 else pfa, 0.0, 1.0))
        if mem.last_hit_step is None:
            t_next = float(horizon_s)
        else:
            age = max(0, int(step) - int(mem.last_hit_step)) * float(dt_s)
            t_next = float(min(horizon_s, max(dt_s, age * (1.0 - q_hit) + dt_s)))
        del proposed_schedule, dwell_steps, n_steps, settled_band, last_target_band, last_dwell_steps
        pd_op = float(pfa) if pd_operating is None else float(pd_operating)
        p_act, reason = derive_p_active(q_hit, pd_operating=pd_op, pfa=pfa)
        n_bins = max(1, len(builder.dwell_bins))
        hazards = np.full(n_bins, q_hit, dtype=np.float64)
        return ForecastResult(
            p_hit_within_dwell=q_hit,
            p_active=p_act,
            p_active_unavailable_reason=reason,
            time_to_next_completed_intercept_s=float(t_next),
            right_censor_horizon_s=float(horizon_s),
            uncertainty=float(1.0 - mem.ewma_hit if mem.visit_count else 1.0),
            model_version=self.model_version,
            hazards=hazards,
        )


def pd_operating_from_snr(
    snr_db: float | None,
    *,
    dwell_steps: int,
    samples_per_step: int,
    pfa: float,
) -> float:
    if snr_db is None or not np.isfinite(snr_db):
        return float(pfa)
    rho = float(10.0 ** (float(snr_db) / 10.0))
    m = int(samples_per_step) * int(dwell_steps)
    return float(np.clip(analytic_pd(rho, m, pfa), 0.0, 1.0))


class HitHazardNet:
    """Lazy-imported small PyTorch multi-head network."""

    def __init__(
        self,
        n_in: int,
        n_bands: int,
        n_dwell: int,
        n_bins: int,
        hidden: int = 32,
        arch: str = "mlp",
        dropout: float = 0.0,
    ) -> None:
        import torch
        from torch import nn

        self.n_in = int(n_in)
        self.n_bands = int(n_bands)
        self.n_dwell = int(n_dwell)
        self.n_bins = int(n_bins)
        self.hidden = int(hidden)
        self.arch = str(arch)
        self.dropout = float(dropout)
        extra = n_bands + n_dwell + n_bins * (n_bands + 1)
        n_trunk = n_in + extra
        self.net: Any
        if self.arch == "residual_ln":

            class ResidualLNTrunk(nn.Module):
                def __init__(self, n_in_local: int, hidden_local: int, drop: float) -> None:
                    super().__init__()
                    self.fc1 = nn.Linear(n_in_local, hidden_local)
                    self.ln1 = nn.LayerNorm(hidden_local)
                    self.fc2 = nn.Linear(hidden_local, hidden_local)
                    self.ln2 = nn.LayerNorm(hidden_local)
                    self.drop = nn.Dropout(float(drop))

                def forward(self, x: Any) -> Any:
                    h = torch.relu(self.ln1(self.fc1(x)))
                    h = self.drop(h)
                    return torch.relu(self.ln2(self.fc2(h)) + h)

            self.net = ResidualLNTrunk(n_trunk, hidden, self.dropout)
        else:
            layers: list[Any] = [
                nn.Linear(n_trunk, hidden),
                nn.ReLU(),
                nn.Linear(hidden, hidden),
                nn.ReLU(),
            ]
            if self.dropout > 0:
                layers.insert(2, nn.Dropout(self.dropout))
                layers.append(nn.Dropout(self.dropout))
            self.net = nn.Sequential(*layers)
        self.head_q = nn.Linear(hidden, 1)
        self.head_h = nn.Linear(hidden, n_bins)
        self.head_u = nn.Linear(hidden, 1)
        self._torch = torch

    def parameters(self) -> Any:
        return list(self.net.parameters()) + list(self.head_q.parameters()) + list(
            self.head_h.parameters()
        ) + list(self.head_u.parameters())

    def encode_aux(
        self,
        band: int,
        dwell_index: int,
        schedule: list[tuple[int, int]],
    ) -> Any:
        torch = self._torch
        band_oh = torch.zeros(self.n_bands)
        if 0 <= band < self.n_bands:
            band_oh[band] = 1.0
        dwell_oh = torch.zeros(self.n_dwell)
        if 0 <= dwell_index < self.n_dwell:
            dwell_oh[dwell_index] = 1.0
        sched = torch.zeros(self.n_bins * (self.n_bands + 1))
        for j, (b, d) in enumerate(schedule[: self.n_bins]):
            base = j * (self.n_bands + 1)
            if 0 <= b < self.n_bands:
                sched[base + b] = 1.0
            sched[base + self.n_bands] = float(d) / 16.0
        return torch.cat([band_oh, dwell_oh, sched], dim=0)

    def forward(
        self,
        features: Any,
        band: int,
        dwell_index: int,
        schedule: list[tuple[int, int]],
    ) -> tuple[Any, Any, Any]:
        torch = self._torch
        x = features if torch.is_tensor(features) else torch.as_tensor(features, dtype=torch.float32)
        if x.dim() == 1:
            x = x.unsqueeze(0)
        aux = self.encode_aux(band, dwell_index, schedule).to(x.device)
        aux = aux.unsqueeze(0).expand(x.shape[0], -1)
        h = self.net(torch.cat([x, aux], dim=1))
        q = torch.sigmoid(self.head_q(h)).clamp(MODEL_EPS, 1.0 - MODEL_EPS)
        hazards = torch.sigmoid(self.head_h(h)).clamp(MODEL_EPS, 1.0 - MODEL_EPS)
        unc = torch.sigmoid(self.head_u(h))
        return q, hazards, unc

    def state_dict(self) -> dict[str, Any]:
        payload = {}
        payload.update({f"net.{k}": v for k, v in self.net.state_dict().items()})
        payload.update({f"q.{k}": v for k, v in self.head_q.state_dict().items()})
        payload.update({f"h.{k}": v for k, v in self.head_h.state_dict().items()})
        payload.update({f"u.{k}": v for k, v in self.head_u.state_dict().items()})
        payload["meta"] = {
            "n_in": self.n_in,
            "n_bands": self.n_bands,
            "n_dwell": self.n_dwell,
            "n_bins": self.n_bins,
            "hidden": self.hidden,
            "arch": self.arch,
            "dropout": self.dropout,
        }
        return payload

    def load_state_dict(self, payload: dict[str, Any]) -> None:
        net = {k.split("net.", 1)[1]: v for k, v in payload.items() if k.startswith("net.")}
        q = {k.split("q.", 1)[1]: v for k, v in payload.items() if k.startswith("q.")}
        h = {k.split("h.", 1)[1]: v for k, v in payload.items() if k.startswith("h.")}
        u = {k.split("u.", 1)[1]: v for k, v in payload.items() if k.startswith("u.")}
        self.net.load_state_dict(net)
        self.head_q.load_state_dict(q)
        self.head_h.load_state_dict(h)
        self.head_u.load_state_dict(u)

    def eval_mode(self) -> None:
        self.net.eval()
        self.head_q.eval()
        self.head_h.eval()
        self.head_u.eval()

    def train_mode(self) -> None:
        self.net.train()
        self.head_q.train()
        self.head_h.train()
        self.head_u.train()


class HitHazardPredictor:
    """Calibrated q_hit plus discrete first-future-completed-hit hazards."""

    def __init__(
        self,
        net: HitHazardNet,
        *,
        dwell_bins: tuple[int, ...],
        hit_calibrator: IsotonicCalibrator | None = None,
        active_calibrator: IsotonicCalibrator | None = None,
        pfa: float = 1e-3,
        samples_per_step: int = 1,
        model_version: str = "hithazard-v1",
    ) -> None:
        self.net = net
        self.dwell_bins = tuple(int(x) for x in dwell_bins)
        self.hit_calibrator = hit_calibrator or IsotonicCalibrator.identity()
        self.active_calibrator = active_calibrator or IsotonicCalibrator.identity()
        self.pfa = float(pfa)
        self.samples_per_step = int(samples_per_step)
        self.model_version = model_version

    def _dwell_index(self, dwell_steps: int) -> int:
        try:
            return list(self.dwell_bins).index(int(dwell_steps))
        except ValueError as exc:
            raise SmartScanError(
                f"dwell_steps={dwell_steps} incompatible with frozen bins {self.dwell_bins}."
            ) from exc

    def forecast_next_intercept(
        self,
        features: np.ndarray,
        *,
        band: int,
        dwell_steps: int,
        proposed_schedule: list[tuple[int, int]],
        horizon_s: float,
        snr_db: float | None,
        dt_s: float,
        start_step: int,
        tune_cost_steps: int,
    ) -> ForecastResult:
        self.net.eval_mode()
        torch = self.net._torch
        dwell_index = self._dwell_index(dwell_steps)
        with torch.no_grad():
            q_t, h_t, u_t = self.net.forward(features, int(band), dwell_index, proposed_schedule)
        q_raw = float(q_t.squeeze().cpu().item())
        hazards = np.asarray(h_t.squeeze().cpu().numpy(), dtype=np.float64)
        uncertainty = float(u_t.squeeze().cpu().item())
        q_hit = float(self.hit_calibrator.predict_one(q_raw))
        pd_op = pd_operating_from_snr(
            snr_db,
            dwell_steps=dwell_steps,
            samples_per_step=self.samples_per_step,
            pfa=self.pfa,
        )
        p_act_raw, reason = derive_p_active(q_hit, pd_operating=pd_op, pfa=self.pfa)
        p_act = None if p_act_raw is None else float(self.active_calibrator.predict_one(p_act_raw))
        times: list[float] = []
        t_cursor = float(tune_cost_steps) * dt_s + float(dwell_steps) * dt_s
        times.append(t_cursor)
        for _b, d_s in proposed_schedule[: hazards.size - 1]:
            t_cursor += float(d_s) * dt_s
            times.append(t_cursor)
        while len(times) < hazards.size:
            t_cursor += float(dwell_steps) * dt_s
            times.append(t_cursor)
        t_hat, mass = expected_time_to_hit(hazards, np.asarray(times))
        if mass < 0.05:
            t_hat = float(horizon_s)
        t_hat = float(np.clip(t_hat, 0.0, horizon_s))
        return ForecastResult(
            p_hit_within_dwell=q_hit,
            p_active=p_act,
            p_active_unavailable_reason=reason,
            time_to_next_completed_intercept_s=t_hat,
            right_censor_horizon_s=float(horizon_s),
            uncertainty=uncertainty,
            model_version=self.model_version,
            hazards=hazards,
        )

    def forecast_all_bands(
        self,
        features: np.ndarray,
        *,
        dwell_steps: int,
        proposed_schedule: list[tuple[int, int]],
        horizon_s: float,
        dt_s: float,
        start_step: int,
        builder: FeatureBuilder | None = None,
        settled_band: int | None = None,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Batched per-band q_hit, p_active, uncertainty. CPU-sized; no future leakage."""

        del horizon_s, dt_s, start_step
        self.net.eval_mode()
        torch = self.net._torch
        dwell_index = self._dwell_index(dwell_steps)
        x = torch.as_tensor(np.asarray(features, dtype=np.float32), dtype=torch.float32)
        if x.dim() == 1:
            x = x.unsqueeze(0)
        aux_rows = [
            self.net.encode_aux(band, dwell_index, proposed_schedule) for band in range(self.net.n_bands)
        ]
        aux = torch.stack(aux_rows, dim=0)
        xk = x.expand(self.net.n_bands, -1)
        with torch.no_grad():
            h = self.net.net(torch.cat([xk, aux], dim=1))
            q_raw = torch.sigmoid(self.net.head_q(h)).clamp(MODEL_EPS, 1.0 - MODEL_EPS)
            u_raw = torch.sigmoid(self.net.head_u(h))
        q_np = np.asarray(q_raw.squeeze(-1).cpu().numpy(), dtype=np.float64).reshape(-1)
        u_np = np.asarray(u_raw.squeeze(-1).cpu().numpy(), dtype=np.float64).reshape(-1)
        q_cal = np.asarray([self.hit_calibrator.predict_one(float(v)) for v in q_np], dtype=np.float64)
        p_act = np.zeros_like(q_cal)
        for i, qv in enumerate(q_cal):
            snr = None
            if builder is not None and 0 <= i < builder.n_bands:
                mem = builder.bands[i]
                snr = mem.snr_ewma if mem.snr_seen else None
            pd_op = pd_operating_from_snr(
                snr,
                dwell_steps=dwell_steps,
                samples_per_step=self.samples_per_step,
                pfa=self.pfa,
            )
            raw, _reason = derive_p_active(float(qv), pd_operating=max(pd_op, self.pfa + 1e-6), pfa=self.pfa)
            p_act[i] = (
                float(self.active_calibrator.predict_one(raw)) if raw is not None else float(qv)
            )
        del settled_band
        return (
            np.clip(q_cal, 0.0, 1.0).astype(np.float32),
            np.clip(p_act, 0.0, 1.0).astype(np.float32),
            np.clip(u_np, 0.0, 1.0).astype(np.float32),
        )


class BuilderBackedHazardPredictor:
    """Expose ``HitHazardPredictor`` with the Recency/builder-first signature."""

    def __init__(self, inner: HitHazardPredictor) -> None:
        self.inner = inner
        self.model_version = inner.model_version

    def forecast_next_intercept(
        self,
        builder: FeatureBuilder,
        *,
        band: int,
        dwell_steps: int,
        proposed_schedule: list[tuple[int, int]],
        horizon_s: float,
        pfa: float,
        pd_operating: float | None = None,
        dt_s: float,
        step: int,
        n_steps: int,
        settled_band: int | None,
        last_target_band: int | None,
        last_dwell_steps: int | None,
    ) -> ForecastResult:
        del pfa, pd_operating
        feats = builder.vector(
            step=int(step),
            n_steps=int(n_steps),
            settled_band=settled_band,
            last_target_band=last_target_band,
            last_dwell_steps=last_dwell_steps,
        )
        mem = None
        if 0 <= int(band) < builder.n_bands:
            mem = builder.bands[int(band)]
        snr = mem.snr_ewma if mem is not None and mem.snr_seen else None
        need_tune = settled_band is None or int(settled_band) != int(band)
        tune = int(builder.tune_latency_steps) if need_tune else 0
        return self.inner.forecast_next_intercept(
            feats,
            band=int(band),
            dwell_steps=int(dwell_steps),
            proposed_schedule=proposed_schedule,
            horizon_s=float(horizon_s),
            snr_db=snr,
            dt_s=float(dt_s),
            start_step=int(step),
            tune_cost_steps=tune,
        )
