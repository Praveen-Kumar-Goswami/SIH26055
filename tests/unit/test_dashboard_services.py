from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from smartscan.config import DashboardConfig
from smartscan.dashboard import services
from smartscan.dashboard.services import (
    _receiver,
    action_signature,
    build_replay_frame,
    comparison_table,
    demo_bundle_is_complete,
    doctor_report,
    explain_decision,
    export_comparison,
    load_dashboard_config,
    load_demo_bundle,
    load_performance_gate,
    metric_cell,
    prepare_demo_bundle,
    run_experiment,
    safe_user_path,
    validate_run_request,
)
from smartscan.metrics.engine import evaluate_strategy
from smartscan.types import MetricValue, SmartScanError


def _tiny_dash(tmp_path: Path) -> DashboardConfig:
    cfg = load_dashboard_config()
    cfg.demo_duration_s = 0.05
    cfg.demo_dt_s = 0.001
    cfg.mc_rollouts = 2
    cfg.horizon_steps = 16
    cfg.max_duration_s = 2.0
    cfg.demo_dir = str(tmp_path / "demo")
    return cfg


def test_dashboard_config_loads_v4_live_path() -> None:
    cfg = load_dashboard_config()
    assert cfg.model_dir.replace("\\", "/").endswith("artifacts/models/scheduler_v4")
    assert cfg.train_config.replace("\\", "/").endswith("configs/train_v4.yaml")
    assert cfg.gate_path.replace("\\", "/").endswith("artifacts/models/held_out_gate.json")
    from smartscan.dashboard.identity import dashboard_identity

    ident = dashboard_identity(cfg)
    assert ident["active_model_bundle"]["generation"] == "v4"
    assert ident["active_model_bundle"]["role"] == "active_model_bundle"
    assert ident["gate_evidence_bundle"]["generation"] == "v2"
    assert ident["gate_evidence_bundle"]["role"] == "gate_evidence_bundle"
    assert ident["gate_evidence_bundle"]["protocol_id"] == "v2_frozen_gate"
    assert ident["champion_set"] is False
    assert ident["gate_evidence_bundle"]["performance_gate_passed"] is False


def test_services_call_stage_apis_not_detector_math() -> None:
    source = inspect.getsource(services)
    assert "evaluate_strategy" in source
    assert "simulate(" in source
    assert "run_policy_episode" in source
    assert "GammaPPF" not in source
    assert "ncx2" not in source
    assert "k * T0" not in source


def test_safe_user_path_rejects_secrets_and_escape(tmp_path: Path) -> None:
    root = tmp_path
    (root / "artifacts").mkdir()
    (root / "data").mkdir()
    allowed = root / "artifacts" / "x.json"
    allowed.write_text("{}", encoding="utf-8")
    assert safe_user_path("artifacts/x.json", root=root) == allowed.resolve()
    with pytest.raises(SmartScanError, match="secrets"):
        safe_user_path("data/.env", root=root)
    with pytest.raises(SmartScanError, match="limited"):
        safe_user_path("docs/BUILD_CONTRACT.md", root=root)


def test_validate_run_request_caps() -> None:
    cfg = DashboardConfig(max_duration_s=0.2, max_n_bands=16)
    assert validate_run_request(cfg, duration_s=0.5, n_bands=16, strategy="sequential")
    assert validate_run_request(cfg, duration_s=0.1, n_bands=32, strategy="sequential")
    assert validate_run_request(cfg, duration_s=0.1, n_bands=16, strategy="nope")
    assert not validate_run_request(cfg, duration_s=0.1, n_bands=16, strategy="sequential")
    assert not validate_run_request(cfg, duration_s=0.1, n_bands=16, strategy="periodic-intercept")


def test_overlay_does_not_change_actions_or_rewards(tmp_path: Path) -> None:
    cfg = _tiny_dash(tmp_path)
    a = run_experiment(
        cfg,
        scenario_id="agile_threat",
        seed=42,
        strategy="sequential",
        evaluation_overlay=False,
    )
    b = run_experiment(
        cfg,
        scenario_id="agile_threat",
        seed=42,
        strategy="sequential",
        evaluation_overlay=True,
    )
    assert action_signature(a) == action_signature(b)
    assert a.truth.content_fingerprint == b.truth.content_fingerprint
    off = build_replay_frame(a, evaluation_overlay=False)
    on = build_replay_frame(b, evaluation_overlay=True)
    assert off.occupied is None
    assert on.occupied is not None
    assert on.overlay_notice and "not available to policy" in on.overlay_notice.lower()


def test_run_matches_evaluate_strategy(tmp_path: Path) -> None:
    cfg = _tiny_dash(tmp_path)
    result = run_experiment(cfg, scenario_id="agile_threat", seed=0, strategy="random")
    again = evaluate_strategy(
        result.truth,
        result.run.observations,
        result.run.decisions,
        receiver_config=_receiver(cfg),
    )
    assert again.content_fingerprint == result.evaluation.content_fingerprint


def test_unavailable_metric_cell_is_honest() -> None:
    from smartscan.types import MetricsReport

    report = MetricsReport(
        metrics={
            "average_reward": MetricValue(
                name="Average reward/cost",
                available=False,
                unavailable_reason="no_observable_reward_in_decision_log",
                value=None,
            )
        }
    )
    cell = metric_cell(report, "average_reward")
    assert cell["available"] is False
    assert "Not available" in cell["display"]
    assert "0" not in cell["display"] or "no_observable" in cell["display"]
    missing = metric_cell(report, "pd")
    assert missing["display"].startswith("Not available")


def test_gate_honest_without_win_badge(tmp_path: Path) -> None:
    gate = tmp_path / "held_out_gate.json"
    gate.write_text(
        json.dumps({"performance_gate_passed": False, "reasons": ["AIR vs sequential"]}),
        encoding="utf-8",
    )
    payload = load_performance_gate(gate)
    assert payload["performance_gate_passed"] is False
    assert payload["highlight_win"] is False
    assert payload["alias"] == "candidate"
    assert "AIR vs sequential" in payload["reasons"]


def test_comparison_table_and_export(tmp_path: Path) -> None:
    cfg = _tiny_dash(tmp_path)
    seq = run_experiment(cfg, scenario_id="agile_threat", seed=1, strategy="sequential")
    rnd = run_experiment(cfg, scenario_id="agile_threat", seed=1, strategy="random")
    table = comparison_table([seq, rnd])
    assert table["highlight_win"] is False
    assert table["performance_gate_passed"] is False
    assert table.get("metric_source") == "LIVE RUN"
    keys = {row["key"] for row in table["rows"]}
    assert "pd" in keys and "event_interception_ratio" in keys
    assert table["n_seeds"] == 1
    json_path = tmp_path / "cmp.json"
    csv_path = tmp_path / "cmp.csv"
    written = export_comparison([seq, rnd], json_path=json_path, csv_path=csv_path)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["schema_version"]
    assert "occupied" not in json.dumps(payload)
    assert Path(written["json"]).is_file()


def test_recorded_air_evals_match_published_v3_v4() -> None:
    from smartscan.dashboard.services import load_recorded_air_evals
    from smartscan.experiment_protocol import (
        CROSS_PROTOCOL_MESSAGE,
        PROTOCOL_V2_FROZEN_GATE,
        PROTOCOL_V3_RESEARCH,
        PROTOCOL_V4_RESEARCH,
        protocol_air_table,
        require_same_protocol_id,
    )
    from smartscan.types import SmartScanError

    evals = load_recorded_air_evals()
    ids = [col["id"] for col in evals["columns"]]
    assert ids == [PROTOCOL_V2_FROZEN_GATE, PROTOCOL_V3_RESEARCH, PROTOCOL_V4_RESEARCH]
    v2 = protocol_air_table(PROTOCOL_V2_FROZEN_GATE)
    idx = {name: i for i, name in enumerate(v2["strategy"])}
    assert v2["air"][idx["ppo"]] == "5.00"
    assert v2["air"][idx["sequential"]] == "9.25"
    assert v2["air"][idx["periodic-intercept"]] == "Not recorded"
    v3 = protocol_air_table(PROTOCOL_V3_RESEARCH)
    assert v3["air"][idx["sequential"]] == "7.97"
    assert v3["air"][idx["ppo"]] == "3.91"
    v4 = protocol_air_table(PROTOCOL_V4_RESEARCH)
    assert v4["air"][idx["sequential"]] == "10.00"
    assert v4["air"][idx["ppo"]] == "7.97"
    with pytest.raises(SmartScanError, match="different experimental protocols"):
        require_same_protocol_id(PROTOCOL_V2_FROZEN_GATE, PROTOCOL_V4_RESEARCH)
    assert "direct performance comparison" in CROSS_PROTOCOL_MESSAGE


def test_comparison_table_refuses_cross_protocol_pairing(tmp_path: Path) -> None:
    cfg = _tiny_dash(tmp_path)
    seq = run_experiment(cfg, scenario_id="agile_threat", seed=1, strategy="sequential")
    ppo = run_experiment(cfg, scenario_id="agile_threat", seed=1, strategy="random")
    seq.protocol_id = "v2_frozen_gate"
    ppo.protocol_id = "v4_research"
    ppo.strategy = "ppo"
    table = comparison_table([seq, ppo])
    assert table["cross_protocol"] is True
    assert table["summaries"] == {}
    assert "different experimental protocols" in str(table["paired_vs_sequential"]["average_intercept_rate"]["unavailable_reason"])


def test_explain_decision_and_demo_bundle(tmp_path: Path) -> None:
    cfg = _tiny_dash(tmp_path)
    result = run_experiment(cfg, scenario_id="agile_threat", seed=3, strategy="fixed-priority")
    expl = explain_decision(result, 0)
    assert expl.target_band in cfg.public_priorities
    assert expl.p_hit is not None
    dest = tmp_path / "demo"
    manifest = prepare_demo_bundle(cfg, dest=dest, include_ppo=False)
    assert manifest["scenario_id"] == "agile_threat"
    assert "sequential" in manifest["strategies"]
    assert "periodic-intercept" in manifest["strategies"]
    loaded = load_demo_bundle(cfg, dest=dest)
    assert {item.strategy for item in loaded} >= {"sequential", "random", "fixed-priority"}
    assert all(item.protocol_id == "live_session" for item in loaded)


def test_load_demo_bundle_rebuilds_when_truth_missing(tmp_path: Path) -> None:
    cfg = _tiny_dash(tmp_path)
    dest = tmp_path / "demo"
    dest.mkdir()
    (dest / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "scenario_id": "agile_threat",
                "seed": 42,
                "receiver_seed": 42,
                "strategies": ["sequential"],
                "matched": True,
            }
        ),
        encoding="utf-8",
    )
    assert demo_bundle_is_complete(dest) is False
    loaded = load_demo_bundle(cfg, dest=dest)
    assert (dest / "truth.npz").is_file()
    assert demo_bundle_is_complete(dest) is True
    assert {item.strategy for item in loaded} >= {"sequential", "periodic-intercept"}


def test_missing_ppo_bundle_errors(tmp_path: Path) -> None:
    cfg = _tiny_dash(tmp_path)
    cfg.model_dir = str(tmp_path / "no_such_bundle")
    with pytest.raises(SmartScanError, match="PPO bundle not found"):
        run_experiment(cfg, scenario_id="sparse", seed=0, strategy="ppo")


def test_corrupt_bundle_in_lineage(tmp_path: Path) -> None:
    from smartscan.dashboard.services import lineage_panel

    bundle = tmp_path / "bad_bundle"
    bundle.mkdir()
    (bundle / "manifest.json").write_text("{}", encoding="utf-8")
    (bundle / "checksums.json").write_text('{"manifest.json": "deadbeef"}', encoding="utf-8")
    cfg = _tiny_dash(tmp_path)
    cfg.model_dir = str(bundle)
    panel = lineage_panel(cfg)
    assert panel["bundle"]["ok"] is False


def test_doctor_does_not_crash_without_mlflow_ui(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMARTSCAN_DB", str(tmp_path / "smartscan.db"))
    monkeypatch.setenv("SMARTSCAN_ARTIFACT_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("MLFLOW_BACKEND_STORE_URI", f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}")
    monkeypatch.setenv("MLFLOW_ARTIFACT_ROOT", str(tmp_path / "mlart"))
    monkeypatch.setenv("MLFLOW_PORT", "59999")
    report = doctor_report(_tiny_dash(tmp_path))
    assert "checks" in report
    mlflow_ui = next(item for item in report["checks"] if item["name"] == "mlflow_ui")
    assert mlflow_ui["ok"] is False


def test_periodic_intercept_run_experiment_end_to_end(tmp_path: Path) -> None:
    cfg = _tiny_dash(tmp_path)
    off = run_experiment(
        cfg,
        scenario_id="agile_threat",
        seed=7,
        strategy="periodic-intercept",
        evaluation_overlay=False,
    )
    on = run_experiment(
        cfg,
        scenario_id="agile_threat",
        seed=7,
        strategy="periodic-intercept",
        evaluation_overlay=True,
    )
    assert off.strategy == "periodic-intercept"
    assert off.run.decisions.rows
    assert all(row.p_hit is not None for row in off.run.decisions.rows)
    assert off.run.decisions.predicted_interception_ratio is not None
    assert action_signature(off) == action_signature(on)
    expl = explain_decision(off, 0)
    assert expl.target_band == off.run.decisions.rows[0].target_band
    table = comparison_table([off])
    assert "periodic-intercept" in table["strategies"]
    for key in (
        "pd",
        "pfa",
        "sensitivity",
        "average_intercept_rate",
        "average_reward",
        "correct_predictions",
        "average_intercept_time_error",
    ):
        assert key in off.evaluation.report.metrics

