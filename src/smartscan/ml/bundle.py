"""Checksummed model bundle: predictor, calibrators, estimators, CTS, PPO, schema."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from smartscan.ml.actions import logits_to_discrete_action
from smartscan.ml.calibrate import IsotonicCalibrator
from smartscan.ml.features import ObservationNormalizer
from smartscan.ml.policies import ContextualThompsonSchedule
from smartscan.ml.predictor import HitHazardNet, HitHazardPredictor
from smartscan.types import BandPlan, SmartScanError, content_fingerprint, sha256_file

BUNDLE_NAME = "SmartScanScheduler"
WEIGHTS_NAME = "predictor_weights.pt"
NORMALIZER_NAME = "normalizer.npz"
CTS_NAME = "cts.npz"
MANIFEST_NAME = "manifest.json"
CHECKSUMS_NAME = "checksums.json"
PPO_WEIGHTS_NAME = "ppo_policy.pt"


class SchedulerBundle:
    def __init__(
        self,
        *,
        band_plan: BandPlan,
        dwell_bins: tuple[int, ...],
        receiver_ibw_hz: float,
        feature_schema_payload: dict[str, object],
        predictor: HitHazardPredictor | None,
        recency_ok: bool,
        hit_calibrator: IsotonicCalibrator,
        active_calibrator: IsotonicCalibrator,
        normalizer: ObservationNormalizer,
        cts: ContextualThompsonSchedule | None,
        ppo_state: dict[str, Any] | None,
        config: dict[str, Any],
        model_version: str,
    ) -> None:
        self.band_plan = band_plan
        self.dwell_bins = dwell_bins
        self.receiver_ibw_hz = float(receiver_ibw_hz)
        self.feature_schema_payload = feature_schema_payload
        self.predictor = predictor
        self.recency_ok = recency_ok
        self.hit_calibrator = hit_calibrator
        self.active_calibrator = active_calibrator
        self.normalizer = normalizer
        self.cts = cts
        self.ppo_state = ppo_state
        self.config = config
        self.model_version = model_version

    def assert_compatible(self, band_plan: BandPlan, dwell_bins: tuple[int, ...], ibw: float) -> None:
        if band_plan.profile_id != self.band_plan.profile_id:
            raise SmartScanError("Bundle BandPlan profile_id does not match input.")
        if tuple(band_plan.band_edges_hz) != tuple(self.band_plan.band_edges_hz):
            raise SmartScanError("Bundle BandPlan edges do not match input.")
        if tuple(dwell_bins) != tuple(self.dwell_bins):
            raise SmartScanError("Bundle dwell_bins do not match input.")
        if abs(float(ibw) - self.receiver_ibw_hz) > 1e-6:
            raise SmartScanError("Bundle receiver IBW does not match input.")


def save_bundle(bundle: SchedulerBundle, directory: str | Path) -> dict[str, str]:
    dest = Path(directory)
    dest.mkdir(parents=True, exist_ok=True)
    import torch

    checksums: dict[str, str] = {}
    if bundle.predictor is not None:
        weights = bundle.predictor.net.state_dict()
        meta = weights.pop("meta")
        torch.save(weights, dest / WEIGHTS_NAME)
        (dest / "predictor_meta.json").write_text(json.dumps(meta, sort_keys=True), encoding="utf-8")
        checksums[WEIGHTS_NAME] = sha256_file(dest / WEIGHTS_NAME)
        checksums["predictor_meta.json"] = sha256_file(dest / "predictor_meta.json")
    np.savez_compressed(
        dest / NORMALIZER_NAME,
        mean=bundle.normalizer.mean,
        m2=bundle.normalizer.m2,
        count=np.asarray([bundle.normalizer.count]),
        clip=np.asarray([bundle.normalizer.clip]),
        size=np.asarray([bundle.normalizer.size]),
    )
    checksums[NORMALIZER_NAME] = sha256_file(dest / NORMALIZER_NAME)
    (dest / "hit_calibrator.json").write_text(
        json.dumps(bundle.hit_calibrator.state_dict(), sort_keys=True), encoding="utf-8"
    )
    (dest / "active_calibrator.json").write_text(
        json.dumps(bundle.active_calibrator.state_dict(), sort_keys=True), encoding="utf-8"
    )
    checksums["hit_calibrator.json"] = sha256_file(dest / "hit_calibrator.json")
    checksums["active_calibrator.json"] = sha256_file(dest / "active_calibrator.json")
    if bundle.cts is not None:
        arrays: dict[str, np.ndarray] = {f"A_{i}": m for i, m in enumerate(bundle.cts.A)}
        arrays.update({f"b_{i}": v for i, v in enumerate(bundle.cts.b)})
        arrays["meta"] = np.asarray(
            [bundle.cts.n_bands, bundle.cts.d, len(bundle.cts.dwell_bins)], dtype=np.int32
        )
        arrays["dwell_bins"] = np.asarray(bundle.cts.dwell_bins, dtype=np.int32)
        np.savez_compressed(dest / CTS_NAME, **arrays)  # type: ignore[arg-type]
        checksums[CTS_NAME] = sha256_file(dest / CTS_NAME)
    if bundle.ppo_state is not None:
        torch.save(bundle.ppo_state, dest / PPO_WEIGHTS_NAME)
        checksums[PPO_WEIGHTS_NAME] = sha256_file(dest / PPO_WEIGHTS_NAME)
    manifest = {
        "registered_name": BUNDLE_NAME,
        "model_version": bundle.model_version,
        "band_plan": bundle.band_plan.model_dump(),
        "dwell_bins": list(bundle.dwell_bins),
        "receiver_ibw_hz": bundle.receiver_ibw_hz,
        "feature_schema": bundle.feature_schema_payload,
        "config": bundle.config,
        "recency_ok": bundle.recency_ok,
        "has_predictor": bundle.predictor is not None,
        "has_cts": bundle.cts is not None,
        "has_ppo": bundle.ppo_state is not None,
    }
    (dest / MANIFEST_NAME).write_text(json.dumps(manifest, sort_keys=True, indent=2), encoding="utf-8")
    checksums[MANIFEST_NAME] = sha256_file(dest / MANIFEST_NAME)
    checksums["content_fingerprint"] = content_fingerprint(manifest)
    (dest / CHECKSUMS_NAME).write_text(json.dumps(checksums, sort_keys=True, indent=2), encoding="utf-8")
    return checksums


def verify_checksums(directory: str | Path) -> dict[str, str]:
    dest = Path(directory)
    listed_raw: Any = json.loads((dest / CHECKSUMS_NAME).read_text(encoding="utf-8"))
    if not isinstance(listed_raw, dict):
        raise SmartScanError("Bundle checksums file must be a JSON object.")
    listed: dict[str, str] = {str(k): str(v) for k, v in listed_raw.items()}
    for name, expected in listed.items():
        if name == "content_fingerprint":
            continue
        path = dest / name
        if not path.is_file():
            raise SmartScanError(f"Bundle missing {name}.")
        actual = sha256_file(path)
        if actual != expected:
            raise SmartScanError(f"Bundle checksum mismatch for {name}.")
    return listed


def load_bundle(directory: str | Path) -> SchedulerBundle:
    dest = Path(directory)
    verify_checksums(dest)
    manifest = json.loads((dest / MANIFEST_NAME).read_text(encoding="utf-8"))
    from smartscan.types import BandPlan

    band_plan = BandPlan.model_validate(manifest["band_plan"])
    dwell_bins = tuple(int(x) for x in manifest["dwell_bins"])
    hit = IsotonicCalibrator.from_state(
        json.loads((dest / "hit_calibrator.json").read_text(encoding="utf-8"))
    )
    active = IsotonicCalibrator.from_state(
        json.loads((dest / "active_calibrator.json").read_text(encoding="utf-8"))
    )
    with np.load(dest / NORMALIZER_NAME) as payload:
        normalizer = ObservationNormalizer(size=int(payload["size"][0]), clip=float(payload["clip"][0]))
        normalizer.mean = np.asarray(payload["mean"], dtype=np.float64)
        normalizer.m2 = np.asarray(payload["m2"], dtype=np.float64)
        normalizer.count = int(payload["count"][0])
    predictor = None
    if manifest.get("has_predictor") and (dest / WEIGHTS_NAME).is_file():
        import torch

        weights = torch.load(dest / WEIGHTS_NAME, map_location="cpu", weights_only=True)
        meta = json.loads((dest / "predictor_meta.json").read_text(encoding="utf-8"))
        net = HitHazardNet(
            n_in=int(meta["n_in"]),
            n_bands=int(meta["n_bands"]),
            n_dwell=int(meta["n_dwell"]),
            n_bins=int(meta["n_bins"]),
            hidden=int(meta["hidden"]),
            arch=str(meta.get("arch") or "mlp"),
            dropout=float(meta.get("dropout") or 0.0),
        )
        net.load_state_dict(weights)
        predictor = HitHazardPredictor(
            net,
            dwell_bins=dwell_bins,
            hit_calibrator=hit,
            active_calibrator=active,
            model_version=str(manifest["model_version"]),
        )
    cts = None
    if manifest.get("has_cts") and (dest / CTS_NAME).is_file():
        with np.load(dest / CTS_NAME) as payload:
            n_bands = int(payload["meta"][0])
            d = int(payload["meta"][1])
            bins = tuple(int(x) for x in payload["dwell_bins"].tolist())
            cts = ContextualThompsonSchedule(n_bands=n_bands, dwell_bins=bins, seed=0, feature_dim=d)
            n_a = n_bands * len(bins)
            cts.A = [np.asarray(payload[f"A_{i}"], dtype=np.float64) for i in range(n_a)]
            cts.b = [np.asarray(payload[f"b_{i}"], dtype=np.float64) for i in range(n_a)]
    ppo_state = None
    if manifest.get("has_ppo") and (dest / PPO_WEIGHTS_NAME).is_file():
        import torch

        ppo_state = torch.load(dest / PPO_WEIGHTS_NAME, map_location="cpu", weights_only=True)
    return SchedulerBundle(
        band_plan=band_plan,
        dwell_bins=dwell_bins,
        receiver_ibw_hz=float(manifest["receiver_ibw_hz"]),
        feature_schema_payload=manifest["feature_schema"],
        predictor=predictor,
        recency_ok=bool(manifest.get("recency_ok", True)),
        hit_calibrator=hit,
        active_calibrator=active,
        normalizer=normalizer,
        cts=cts,
        ppo_state=ppo_state,
        config=manifest.get("config") or {},
        model_version=str(manifest["model_version"]),
    )


def ppo_predict_fn(bundle: SchedulerBundle) -> Callable[[np.ndarray], int]:
    if bundle.ppo_state is None:
        raise SmartScanError("Bundle has no PPO weights.")
    import torch
    import torch.nn.functional as F

    policy = bundle.ppo_state
    # SB3 MlpPolicy actor: look for typical keys; fallback greedy linear.
    def _predict(obs: np.ndarray) -> int:
        x = bundle.normalizer.transform(obs)
        tensor = torch.as_tensor(x, dtype=torch.float32).unsqueeze(0)
        if "mlp_extractor.policy_net.0.weight" in policy:
            w1 = policy["mlp_extractor.policy_net.0.weight"]
            b1 = policy["mlp_extractor.policy_net.0.bias"]
            h = F.relu(tensor @ w1.T + b1)
            if "mlp_extractor.policy_net.2.weight" in policy:
                w2 = policy["mlp_extractor.policy_net.2.weight"]
                b2 = policy["mlp_extractor.policy_net.2.bias"]
                h = F.relu(h @ w2.T + b2)
            w_act = policy["action_net.weight"]
            b_act = policy["action_net.bias"]
            logits = h @ w_act.T + b_act
            n_bands = int(bundle.band_plan.n_bands)
            return logits_to_discrete_action(logits, n_bands, bundle.dwell_bins)
        # Fallback: argmax of a tiny projection stored as action_net only
        if "action_net.weight" in policy:
            logits = tensor @ policy["action_net.weight"].T + policy["action_net.bias"]
            n_bands = int(bundle.band_plan.n_bands)
            return logits_to_discrete_action(logits, n_bands, bundle.dwell_bins)
        raise SmartScanError("Unrecognized PPO state_dict keys.")

    return _predict


class SmartScanPyFunc:
    """MLflow pyfunc-style wrapper. Loads only checksum-verified local artifacts."""

    def __init__(self, bundle: SchedulerBundle) -> None:
        self.bundle = bundle
        self._predict = ppo_predict_fn(bundle) if bundle.ppo_state is not None else None

    def predict(self, model_input: np.ndarray) -> np.ndarray:
        if self._predict is None:
            raise SmartScanError("Bundle has no PPO policy to serve.")
        arr = np.asarray(model_input, dtype=np.float32)
        if arr.ndim == 1:
            return np.asarray([self._predict(arr)], dtype=np.int64)
        return np.asarray([self._predict(row) for row in arr], dtype=np.int64)
