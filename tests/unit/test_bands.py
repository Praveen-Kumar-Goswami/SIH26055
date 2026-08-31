from __future__ import annotations

import numpy as np
import pytest

from smartscan.config import duration_to_steps
from smartscan.rf.bands import frequency_to_band, named_band_plan
from smartscan.types import SmartScanError


def test_duration_integer_ok() -> None:
    assert duration_to_steps(1.0, 0.001) == 1000
    assert duration_to_steps(0.36, 0.001) == 360


def test_duration_rejects_non_integer() -> None:
    with pytest.raises(SmartScanError, match="not an integer"):
        duration_to_steps(1.0, 0.003)


def test_demo_plan_sixteen_bands() -> None:
    plan = named_band_plan("demo_2_18")
    assert plan.n_bands == 16
    assert plan.band_edges_hz[0] == 2e9
    assert plan.band_edges_hz[-1] == 18e9
    assert frequency_to_band(2e9, plan) == 0
    assert frequency_to_band(3e9, plan) == 1
    assert frequency_to_band(17.999e9, plan) == 15
    with pytest.raises(SmartScanError, match="outside"):
        frequency_to_band(18e9, plan)
    with pytest.raises(SmartScanError, match="outside"):
        frequency_to_band(1.9e9, plan)


def test_turing_plan_eighteen_bands() -> None:
    plan = named_band_plan("turing_0_18")
    assert plan.n_bands == 18
    assert frequency_to_band(0.0, plan) == 0
    with pytest.raises(SmartScanError):
        frequency_to_band(18e9, plan)


def test_searchsorted_high_edge_exclusion() -> None:
    plan = named_band_plan("demo_2_18")
    edges = np.asarray(plan.band_edges_hz)
    # Interior edge 9 GHz belongs to the [9,10) band, not [8,9).
    assert frequency_to_band(9e9, plan) == int(np.searchsorted(edges, 9e9, side="right") - 1)
    assert plan.band_names[frequency_to_band(9e9, plan)].startswith("9-")


def test_unknown_profile() -> None:
    with pytest.raises(SmartScanError, match="Unknown BandPlan"):
        named_band_plan("not_a_profile")
