"""YAML configuration loading and project-root path helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from smartscan.types import SmartScanError

DT_INTEGER_TOLERANCE = 1e-9


def project_root() -> Path:
    env = os.environ.get("SMARTSCAN_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve()
    for candidate in (here.parent, *here.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return Path.cwd().resolve()


def resolve_under_root(path: str | Path, *, root: Path | None = None) -> Path:
    base = root or project_root()
    candidate = Path(path)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (base / candidate).resolve()
    try:
        resolved.relative_to(base.resolve())
    except ValueError as exc:
        # Absolute user-supplied inputs (CLI --output) may live under artifacts/.
        # Still reject path traversal that escapes via '..' from a relative path.
        if not Path(path).is_absolute():
            raise SmartScanError(f"Path {path} escapes project root {base}.") from exc
    return resolved


def load_yaml(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = project_root() / file_path
    with file_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise SmartScanError(f"YAML root must be a mapping: {file_path}")
    return data


def duration_to_steps(duration_s: float, dt_s: float, *, tol: float = DT_INTEGER_TOLERANCE) -> int:
    """Require T/dt to be an integer within *tol*; return N = round(T/dt)."""

    if not np_finite_positive(duration_s) or not np_finite_positive(dt_s):
        raise SmartScanError(f"duration_s and dt_s must be finite and positive, got {duration_s}, {dt_s}.")
    ratio = duration_s / dt_s
    steps = int(round(ratio))
    residual = abs(ratio - steps)
    limit = tol * max(1.0, abs(ratio))
    if residual > max(tol, limit):
        raise SmartScanError(
            f"duration_s/dt_s = {ratio:.12g} is not an integer within tolerance {tol}."
        )
    if steps <= 0:
        raise SmartScanError("N = round(T/dt) must be positive.")
    return steps


def np_finite_positive(value: float) -> bool:
    return bool(value > 0 and value == value and abs(value) != float("inf"))


class SimulateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed: int = 42
    dt_s: float = 0.001
    duration_s: float = 2.0
    band_plan_id: str = "demo_2_18"
    scenario_id: str = "sparse"
    schema_version: str = "1.0.0"
    output: str | None = None
    emitters: list[dict[str, Any]] | None = None

    @field_validator("seed")
    @classmethod
    def _seed_nonneg(cls, value: int) -> int:
        if value < 0:
            raise SmartScanError("seed must be nonnegative.")
        return value

    @field_validator("dt_s", "duration_s")
    @classmethod
    def _positive(cls, value: float) -> float:
        if not np_finite_positive(value):
            raise SmartScanError("dt_s and duration_s must be finite and positive.")
        return value


class ReceiverYaml(BaseModel):
    """YAML schema for configs/receiver.yaml (loaded by Stage 2 receive)."""

    model_config = ConfigDict(extra="allow")

    receiver_ibw_hz: float
    scan_span_hz: float
    tune_latency_steps: int = 1
    dwell_bins: list[int] = Field(default_factory=lambda: [1, 2, 4, 8, 16])
    noise_mode: str = "normalized"
    pfa_design: float = 1e-3
    samples_per_step: int = 1


class RewardWeights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    w_hit: float = 1.0
    w_priority: float = 0.5
    c_tune: float = 0.1
    c_time: float = 0.05
    c_repeat: float = 0.2
    c_false_like: float = 0.1
    lambda_novelty: float = 0.2
    lambda_uncertainty: float = 0.1
    novelty_bonus_cap: float = 0.5
    uncertainty_bonus_cap: float = 0.5
    # dt_scaled: multiply step counts by dt_s (historical v2; costs ~1e-4).
    # per_step: costs on the same order as hit rewards (research v3).
    time_cost_mode: Literal["dt_scaled", "per_step", "excess_dwell"] = "dt_scaled"
    time_cost_reference_steps: int = 8
    # Credit a hit only when it starts a new stay (aligns with event matching / AIR).
    first_hit_only: bool = False
    # Bonus for visiting a band absent from the last coverage_window commands.
    w_coverage: float = 0.0
    coverage_window: int = 16
    # Constant cost per completed command (penalizes 1-step hit-farming).
    c_action: float = 0.0
    c_repeat_hit: float = 0.0


class ScenarioSeedSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    seeds: list[int] = Field(default_factory=list)


class TrainConfig(BaseModel):
    """Stage 5 training profile (smoke or full)."""

    model_config = ConfigDict(extra="allow")

    schema_version: str = "1.0.0"
    seed: int = 0
    device: str = "cpu"
    timesteps: int = 256
    n_envs: int = 1
    n_epochs_predictor: int = 4
    batch_size: int = 32
    dt_s: float = 0.001
    duration_s: float = 0.2
    band_plan_id: str = "demo_2_18"
    receiver_config: str = "configs/receiver.yaml"
    noise_power_w: float = 1.0e-13
    dwell_bins: list[int] = Field(default_factory=lambda: [1, 2, 4, 8, 16])
    default_dwell_steps: int = 8
    horizon_steps: int = 80
    forecast_command_bins: int = 8
    mc_rollouts: int = 128
    collect_strategies: list[str] = Field(
        default_factory=lambda: ["sequential", "random", "fixed-priority", "reactive"]
    )
    train_scenarios: list[ScenarioSeedSpec] = Field(default_factory=list)
    val_scenarios: list[ScenarioSeedSpec] = Field(default_factory=list)
    test_scenarios: list[ScenarioSeedSpec] = Field(default_factory=list)
    public_priorities: list[int] = Field(default_factory=lambda: [8, 4, 10])
    reward: RewardWeights = Field(default_factory=RewardWeights)
    predictor_hidden: int = 32
    predictor_lr: float = 1e-2
    ppo_learning_rate: float = 3e-4
    ppo_n_steps: int = 64
    ppo_batch_size: int = 32
    ppo_n_epochs: int = 2
    ppo_gamma: float = 0.99
    ppo_gae_lambda: float = 0.95
    ppo_clip_range: float = 0.2
    ppo_vf_coef: float = 0.5
    ppo_max_grad_norm: float = 0.5
    ppo_ent_coef: float = 0.0
    ppo_net_arch: list[int] = Field(default_factory=lambda: [64, 64])
    eval_cadence: int = 0
    early_stopping_patience: int = 0
    ewma_alpha: float = 0.3
    model_version: str = "0.1.0"
    ablate_periodicity: bool = False
    ablate_novelty: bool = False
    ablate_priority: bool = False
    predictor_arch: str = "mlp"
    predictor_dropout: float = 0.0
    predictor_patience: int = 0
    predictor_balance: bool = False
    predictor_loss: str = "bce"
    predictor_focal_gamma: float = 2.0
    action_layout: str = "discrete"
    include_predictor_obs: bool = False
    include_neural_predictor_obs: bool = False
    include_action_history: int = 0
    balanced_family_sampling: bool = False
    curriculum_families: list[list[str]] = Field(default_factory=list)
    curriculum_episode_boundaries: list[int] = Field(default_factory=list)
    selection_air_weight: float = 1.0
    selection_ratio_weight: float = 0.5
    selection_delay_weight: float = -0.05
    selection_pfa_weight: float = -20.0
    ppo_bc_epochs: int = 0
    ppo_bc_episodes: int = 0
    ppo_bc_teachers: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _reject_frozen_held_out_seeds(self) -> TrainConfig:
        """Train/val/dev-test must never reuse locked evaluation seeds."""

        reserved = set(range(1000, 1030)) | set(range(8000, 8008)) | set(range(9000, 9008))
        for label, specs in (
            ("train", self.train_scenarios),
            ("val", self.val_scenarios),
            ("test", self.test_scenarios),
        ):
            for spec in specs:
                bad = [int(seed) for seed in spec.seeds if int(seed) in reserved]
                if bad:
                    raise ValueError(
                        f"{label} split must not use frozen evaluation seeds {bad}."
                    )
        layout = str(self.action_layout).strip().lower()
        if layout not in {"discrete", "multidiscrete"}:
            raise ValueError("action_layout must be discrete or multidiscrete.")
        if str(self.predictor_arch) not in {"mlp", "residual_ln"}:
            raise ValueError("predictor_arch must be mlp or residual_ln.")
        if str(self.predictor_loss) not in {"bce", "focal"}:
            raise ValueError("predictor_loss must be bce or focal.")
        return self


class BenchmarkConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str = "1.0.0"
    dt_s: float = 0.001
    duration_s: float = 0.4
    band_plan_id: str = "demo_2_18"
    receiver_config: str = "configs/receiver.yaml"
    noise_power_w: float = 1.0e-13
    default_dwell_steps: int = 8
    n_seeds: int = 30
    seed_list: list[int] = Field(default_factory=list)
    scenarios: list[str] = Field(default_factory=lambda: ["sparse", "dense", "agile_threat"])
    manifest: str = "configs/held_out_manifest.json"
    pfa_design: float = 1e-3
    public_priorities: list[int] = Field(default_factory=lambda: [8, 4, 10])
    vs_sequential_air_rel: float = 0.05
    vs_random_air_rel: float = 0.05
    vs_sequential_delay_rel: float = 0.10
    vs_best_noninferior_rel: float = 0.02
    pfa_newcombe_abs: float = 0.001
    pfa_newcombe_rel: float = 0.20
    bootstrap_seed: int = 0


class DashboardConfig(BaseModel):
    """Offline dashboard limits and demo profile. Does not retrain models."""

    model_config = ConfigDict(extra="allow")

    schema_version: str = "1.0.0"
    host: str = "127.0.0.1"
    port: int = 8501
    max_duration_s: float = 2.0
    max_n_bands: int = 16
    demo_scenario_id: str = "agile_threat"
    demo_seed: int = 42
    demo_duration_s: float = 0.2
    demo_dt_s: float = 0.001
    noise_power_w: float = 1.0e-13
    dwell_steps: int = 8
    mc_rollouts: int = 8
    horizon_steps: int = 80
    public_priorities: list[int] = Field(default_factory=lambda: [8, 4, 10])
    receiver_config: str = "configs/receiver.yaml"
    band_plan_id: str = "demo_2_18"
    model_dir: str = "artifacts/models/scheduler_v4"
    gate_path: str = "artifacts/models/held_out_gate.json"
    demo_dir: str = "artifacts/demo"
    train_config: str = "configs/train_v4.yaml"

