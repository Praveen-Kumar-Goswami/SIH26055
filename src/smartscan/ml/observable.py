"""Policy-visible transitions. No GroundTruth, emitter IDs, or future rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from smartscan.types import DecisionRow, SmartScanError, is_evaluator_only_key


@dataclass(frozen=True)
class ObservableTransition:
    """One completed command as seen by the predictor, policy, and reward."""

    decision_id: str
    start_step: int
    tune_end_step: int
    end_step: int
    target_band: int
    dwell_steps: int
    hit: bool
    measured_snr_db: float | None
    n_steps: int
    n_bands: int
    dt_s: float
    settled_band_before: int | None
    last_target_band: int | None
    public_catalog_priority: float | None = None

    @property
    def tune_cost_steps(self) -> int:
        return max(0, int(self.tune_end_step) - int(self.start_step))

    @property
    def command_steps(self) -> int:
        return max(0, int(self.end_step) - int(self.start_step))

    @property
    def elapsed_fraction(self) -> float:
        return float(self.start_step) / float(max(self.n_steps, 1))

    @property
    def remaining_horizon_steps(self) -> int:
        return max(0, int(self.n_steps) - int(self.start_step))


def transition_from_decision(
    row: DecisionRow,
    *,
    n_steps: int,
    n_bands: int,
    dt_s: float,
    settled_band_before: int | None,
    last_target_band: int | None,
    public_catalog_priority: float | None = None,
) -> ObservableTransition:
    return ObservableTransition(
        decision_id=row.decision_id,
        start_step=int(row.start_step),
        tune_end_step=int(row.tune_end_step),
        end_step=int(row.end_step),
        target_band=int(row.target_band),
        dwell_steps=int(row.dwell_steps),
        hit=bool(row.hit),
        measured_snr_db=row.measured_snr_db,
        n_steps=int(n_steps),
        n_bands=int(n_bands),
        dt_s=float(dt_s),
        settled_band_before=settled_band_before,
        last_target_band=last_target_band,
        public_catalog_priority=public_catalog_priority,
    )


def assert_no_oracle_payload(payload: dict[str, Any], *, where: str) -> None:
    leaked = [key for key in payload if is_evaluator_only_key(str(key))]
    if leaked:
        raise SmartScanError(f"Oracle fields entered {where}: {leaked}")


class ExplodingOracle:
    """Test double: any attribute access raises. Used by the leakage firewall."""

    def __init__(self, label: str = "ground_truth") -> None:
        object.__setattr__(self, "_label", label)

    def __getattribute__(self, name: str) -> Any:
        if name in {"_label", "__class__", "__repr__", "__str__"}:
            return object.__getattribute__(self, name)
        if name.startswith("__") and name.endswith("__"):
            return object.__getattribute__(self, name)
        label = object.__getattribute__(self, "_label")
        raise RuntimeError(f"oracle leak: accessed {label}.{name}")

    def __setattr__(self, name: str, value: Any) -> None:
        raise RuntimeError(f"oracle leak: set {name}")

    def __getitem__(self, key: Any) -> Any:
        raise RuntimeError(f"oracle leak: indexed {key!r}")
