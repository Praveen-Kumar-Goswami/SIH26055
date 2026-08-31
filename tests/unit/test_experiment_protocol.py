from __future__ import annotations

from pathlib import Path

import pytest

from smartscan.config import project_root
from smartscan.experiment_protocol import (
    CROSS_PROTOCOL_MESSAGE,
    NOT_RECORDED,
    PROTOCOL_LIVE_SESSION,
    PROTOCOL_V2_FROZEN_GATE,
    PROTOCOL_V3_RESEARCH,
    PROTOCOL_V4_RESEARCH,
    TOTAL_PUBLIC_STRATEGIES,
    artifact_integrity_report,
    assert_bundle_generation,
    assert_distinct_bundle_fingerprints,
    check_run_bundle_linkage,
    generation_from_bundle_path,
    generation_from_model_version,
    get_protocol,
    infer_protocol_id,
    inspect_bundle_dir,
    known_bundle_fingerprint_map,
    live_session_protocol,
    load_protocol_air_means,
    official_gate_protocol,
    protocol_air_table,
    protocols_comparable,
    registered_protocols,
    require_comparable_protocols,
    require_same_protocol_id,
    selector_options,
)
from smartscan.ml.strategy_registry import PUBLIC_STRATEGIES
from smartscan.types import SmartScanError

V2_FP = "81751a75c678b5bab922f54f77e73fc525a9a2c8c5d9ecbaaaa257a48eef6746"
V3_FP = "e89adc332b7d0532d08fa4d4d694c1dd42cd253a95f6329f2d983d8fc5b4a82f"
V4_FP = "a674290744dd6a18f290a2cc248ccd7c9455d77bd5cc0bf4f05a2b33196a9fe7"


def test_protocol_registry_has_three_frozen_and_live() -> None:
    catalog = registered_protocols()
    assert TOTAL_PUBLIC_STRATEGIES == 7
    assert set(catalog) >= {
        PROTOCOL_V2_FROZEN_GATE,
        PROTOCOL_V3_RESEARCH,
        PROTOCOL_V4_RESEARCH,
        PROTOCOL_LIVE_SESSION,
    }
    v2 = official_gate_protocol()
    assert v2.is_official_gate is True
    assert v2.is_frozen is True
    assert v2.episode_duration_s == 0.4
    assert v2.scenario_seeds[0] == 1000
    assert v2.scenario_seeds[-1] == 1029
    v3 = get_protocol(PROTOCOL_V3_RESEARCH)
    assert v3.episode_duration_s == 0.2
    assert v3.scenario_seeds == tuple(range(8000, 8008))
    v4 = get_protocol(PROTOCOL_V4_RESEARCH)
    assert v4.episode_duration_s == 0.2
    assert v4.scenario_seeds == tuple(range(9000, 9008))
    labels = [item[0] for item in selector_options()]
    assert labels[0] == "Current session"
    assert "Frozen held-out — v2" in labels
    assert "Research test — v3" in labels
    assert "Research test — v4" in labels


def test_v2_v3_v4_evidence_air_exact_and_periodic_not_recorded() -> None:
    v2 = protocol_air_table(PROTOCOL_V2_FROZEN_GATE)
    v3 = protocol_air_table(PROTOCOL_V3_RESEARCH)
    v4 = protocol_air_table(PROTOCOL_V4_RESEARCH)
    idx = {name: i for i, name in enumerate(v2["strategy"])}
    assert list(v2["strategy"]) == list(PUBLIC_STRATEGIES)
    assert v2["air"][idx["sequential"]] == "9.25"
    assert v2["air"][idx["ppo"]] == "5.00"
    assert v2["air"][idx["periodic-intercept"]] == NOT_RECORDED
    assert v2["air"][idx["periodic-intercept"]] != "0"
    assert v2["air"][idx["periodic-intercept"]] != "0.00"
    assert v3["air"][idx["sequential"]] == "7.97"
    assert v3["air"][idx["ppo"]] == "3.91"
    assert v3["air"][idx["periodic-intercept"]] == NOT_RECORDED
    assert v4["air"][idx["sequential"]] == "10.00"
    assert v4["air"][idx["ppo"]] == "7.97"
    assert v4["air"][idx["periodic-intercept"]] == NOT_RECORDED
    loaded_v2 = load_protocol_air_means(PROTOCOL_V2_FROZEN_GATE)
    loaded_v3 = load_protocol_air_means(PROTOCOL_V3_RESEARCH)
    loaded_v4 = load_protocol_air_means(PROTOCOL_V4_RESEARCH)
    assert loaded_v2["gate_passed"] is False
    assert loaded_v3["gate_passed"] is False
    assert loaded_v4["gate_passed"] is False
    assert loaded_v2["oracle_air"] == pytest.approx(23.25)
    assert loaded_v3["oracle_air"] == pytest.approx(15.94, abs=0.005)
    assert loaded_v4["oracle_air"] == pytest.approx(17.97, abs=0.005)


def test_cross_protocol_comparison_is_refused() -> None:
    v2 = get_protocol(PROTOCOL_V2_FROZEN_GATE)
    v4 = get_protocol(PROTOCOL_V4_RESEARCH)
    ok, message = protocols_comparable(v2, v4)
    assert ok is False
    assert message == CROSS_PROTOCOL_MESSAGE
    with pytest.raises(SmartScanError, match="different experimental protocols"):
        require_comparable_protocols(v2, v4)
    with pytest.raises(SmartScanError, match="direct performance comparison"):
        require_same_protocol_id(PROTOCOL_V2_FROZEN_GATE, PROTOCOL_V4_RESEARCH)
    v3 = get_protocol(PROTOCOL_V3_RESEARCH)
    ok3, _ = protocols_comparable(v3, v4)
    assert ok3 is False
    same, _ = protocols_comparable(v2, v2)
    assert same is True
    with pytest.raises(SmartScanError, match="legacy_unknown"):
        get_protocol("legacy_unknown")
    with pytest.raises(SmartScanError, match="Unknown experiment protocol"):
        get_protocol("nope")
    banner = v2.as_banner()
    assert banner["protocol"] == PROTOCOL_V2_FROZEN_GATE
    assert "1000" in banner["seeds"]
    assert v2.fingerprint_field("model_bundle_fingerprint")
    v2.fingerprint_field("scenario_manifest_fingerprint")
    assert v2.fingerprint_field("scenario_manifest_fingerprint")
    assert v2.fingerprint_field("receiver_config_fingerprint")
    assert v2.fingerprint_field("benchmark_config_fingerprint") is None
    assert v2.fingerprint_field("unknown") is None


def test_infer_protocol_id_does_not_guess() -> None:
    assert infer_protocol_id(seed=1000, duration_s=0.4) == PROTOCOL_V2_FROZEN_GATE
    assert infer_protocol_id(seed=8000, duration_s=0.2) == PROTOCOL_V3_RESEARCH
    assert infer_protocol_id(seed=9000, duration_s=0.2) == PROTOCOL_V4_RESEARCH
    assert infer_protocol_id(seed=1000, duration_s=0.2) == "legacy_unknown"
    assert infer_protocol_id(seed=None, duration_s=None) == "legacy_unknown"
    assert infer_protocol_id(seed=None, duration_s=None, for_new_write=True) == PROTOCOL_LIVE_SESSION
    assert infer_protocol_id(seed=42, duration_s=0.2, for_new_write=True) == PROTOCOL_LIVE_SESSION
    assert infer_protocol_id(seed=1, duration_s=1.0, explicit="v4_research") == PROTOCOL_V4_RESEARCH


def test_load_v2_v3_v4_fingerprints_are_distinct() -> None:
    root = project_root()
    v2 = assert_bundle_generation(root / "artifacts/models/scheduler_full", "v2")
    v3 = assert_bundle_generation(root / "artifacts/models/scheduler_v3", "v3")
    v4 = assert_bundle_generation(root / "artifacts/models/scheduler_v4", "v4")
    assert v2["content_fingerprint"] == V2_FP
    assert v3["content_fingerprint"] == V3_FP
    assert v4["content_fingerprint"] == V4_FP
    assert_distinct_bundle_fingerprints([v2, v3, v4])
    mapping = known_bundle_fingerprint_map()
    assert mapping["v2"] == V2_FP
    assert mapping["v3"] == V3_FP
    assert mapping["v4"] == V4_FP
    with pytest.raises(SmartScanError, match="expected v4"):
        assert_bundle_generation(root / "artifacts/models/scheduler_full", "v4")
    err = check_run_bundle_linkage(model_version="v4", bundle_fingerprint=V2_FP, fingerprints=mapping)
    assert err is not None
    assert "v4" in err and "v2" in err
    assert check_run_bundle_linkage(model_version="v4", bundle_fingerprint=V4_FP, fingerprints=mapping) is None


def test_generation_from_path_and_integrity_report() -> None:
    assert generation_from_bundle_path("artifacts/models/scheduler_v4") == "v4"
    assert generation_from_bundle_path("artifacts/models/scheduler_v3") == "v3"
    assert generation_from_bundle_path("artifacts/models/scheduler_full") == "v2"
    assert generation_from_model_version("4.0.0-candidate") == "v4"
    assert generation_from_model_version("3.0.0") == "v3"
    assert generation_from_model_version("2") == "v2"
    assert live_session_protocol().protocol_id == PROTOCOL_LIVE_SESSION
    report = artifact_integrity_report()
    assert report["ok"] is True
    assert report["demo_present"] is True
    assert not report["missing"]
    assert not report["stale"]
    assert not report["duplicate"]
    missing = inspect_bundle_dir(Path("does-not-exist-bundle"))
    assert missing["ok"] is False
