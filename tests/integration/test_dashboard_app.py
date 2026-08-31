from __future__ import annotations

from pathlib import Path

import pytest

from smartscan.cli import main
from smartscan.config import DashboardConfig
from smartscan.dashboard.services import dashboard_argv, prepare_demo_bundle


def test_cli_dashboard_invokes_streamlit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, list[str]] = {}

    def fake_call(argv: list[str]) -> int:
        captured["argv"] = list(argv)
        return 0

    monkeypatch.setattr("subprocess.call", fake_call)
    assert main(["dashboard", "--host", "127.0.0.1", "--port", "8501"]) == 0
    assert captured["argv"][1:4] == ["-m", "streamlit", "run"]
    assert "127.0.0.1" in captured["argv"]
    assert "--browser.gatherUsageStats" in captured["argv"]
    argv = dashboard_argv("127.0.0.1", 8501, tmp_path / "app.py")
    assert "--server.headless" in argv
    assert argv[argv.index("--server.headless") + 1] == "true"


def test_cli_doctor_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMARTSCAN_DB", str(tmp_path / "smartscan.db"))
    monkeypatch.setenv("SMARTSCAN_ARTIFACT_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("MLFLOW_BACKEND_STORE_URI", f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}")
    monkeypatch.setenv("MLFLOW_ARTIFACT_ROOT", str(tmp_path / "mlart"))
    monkeypatch.setenv("MLFLOW_PORT", "59998")
    code = main(["doctor"])
    assert code in {0, 2}


def test_app_smoke_default_launch_demo_compare_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    streamlit = pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    del streamlit
    monkeypatch.setenv("SMARTSCAN_DB", str(tmp_path / "smartscan.db"))
    monkeypatch.setenv("SMARTSCAN_ARTIFACT_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("MLFLOW_BACKEND_STORE_URI", f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}")
    monkeypatch.setenv("MLFLOW_ARTIFACT_ROOT", str(tmp_path / "mlart"))
    monkeypatch.setenv("SMARTSCAN_DEMO_DIR", str(tmp_path / "demo"))
    monkeypatch.setenv("MLFLOW_PORT", "59997")
    cfg = DashboardConfig(
        demo_duration_s=0.05,
        mc_rollouts=2,
        horizon_steps=16,
        demo_dir=str(tmp_path / "demo"),
    )
    prepare_demo_bundle(cfg, dest=tmp_path / "demo", include_ppo=False)
    app = Path(__file__).resolve().parents[2] / "src" / "smartscan" / "dashboard" / "app.py"
    at = AppTest.from_file(str(app), default_timeout=30)
    at.run()
    assert not at.exception
    at.button(key="enter_control_center").click().run()
    assert not at.exception
    at.button(key="load_demo").click().run()
    assert not at.exception
    at.radio(key="view_select").set_value("Metrics Compare").run()
    assert not at.exception
    warnings = " ".join(str(item.value) for item in at.warning)
    assert "candidate" in warnings.lower() or "performance_gate_passed=false" in warnings.lower()
    expander_labels = [str(getattr(item, "label", "")) for item in at.expander]
    assert any("Failed criteria" in label for label in expander_labels)
    at.radio(key="view_select").set_value("Scan Replay").run()
    assert not at.exception
    at.radio(key="view_select").set_value("Smart Decision").run()
    assert not at.exception
    at.radio(key="view_select").set_value("Run History").run()
    assert not at.exception
    at.radio(key="view_select").set_value("Model & Data Lineage").run()
    assert not at.exception
    at.toggle(key="overlay_toggle").set_value(True).run()
    assert not at.exception


def test_app_missing_model_and_unavailable_mlflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("SMARTSCAN_DB", str(tmp_path / "smartscan.db"))
    monkeypatch.setenv("SMARTSCAN_ARTIFACT_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("MLFLOW_BACKEND_STORE_URI", f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}")
    monkeypatch.setenv("MLFLOW_ARTIFACT_ROOT", str(tmp_path / "mlart"))
    monkeypatch.setenv("SMARTSCAN_DEMO_DIR", str(tmp_path / "demo"))
    monkeypatch.setenv("SMARTSCAN_MODEL_DIR", str(tmp_path / "no_model"))
    monkeypatch.setenv("MLFLOW_PORT", "1")
    app = Path(__file__).resolve().parents[2] / "src" / "smartscan" / "dashboard" / "app.py"
    at = AppTest.from_file(str(app), default_timeout=20)
    at.run()
    assert not at.exception
    at.button(key="enter_control_center").click().run()
    assert not at.exception
    at.radio(key="view_select").set_value("Configure & Run").run()
    at.selectbox(key="cfg_strategy").set_value("ppo").run()
    at.button(key="run_experiment").click().run()
    assert not at.exception
    at.button(key="sidebar_doctor").click().run()
    assert not at.exception


def test_app_configure_dropdown_and_periodic_intercept_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    from smartscan.ml.strategy_registry import PUBLIC_STRATEGIES

    monkeypatch.setenv("SMARTSCAN_DB", str(tmp_path / "smartscan.db"))
    monkeypatch.setenv("SMARTSCAN_ARTIFACT_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("MLFLOW_BACKEND_STORE_URI", f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}")
    monkeypatch.setenv("MLFLOW_ARTIFACT_ROOT", str(tmp_path / "mlart"))
    monkeypatch.setenv("SMARTSCAN_DEMO_DIR", str(tmp_path / "demo"))
    monkeypatch.setenv("MLFLOW_PORT", "59996")
    app = Path(__file__).resolve().parents[2] / "src" / "smartscan" / "dashboard" / "app.py"
    at = AppTest.from_file(str(app), default_timeout=60)
    at.run()
    assert not at.exception
    at.button(key="enter_control_center").click().run()
    assert not at.exception
    box = at.selectbox(key="cfg_strategy")
    assert list(box.options) == list(PUBLIC_STRATEGIES)
    assert len(box.options) == 7
    at.selectbox(key="cfg_strategy").set_value("periodic-intercept").run()
    at.button(key="run_experiment").click().run()
    assert not at.exception
    captions = " ".join(str(item.value) for item in at.caption)
    assert "periodic-intercept" in captions
    assert any("RUN COMPLETE" in str(getattr(item, "value", item)) for item in at.success)
    at.radio(key="view_select").set_value("Scan Replay").run()
    assert not at.exception
    replay = at.selectbox(key="replay_strategy")
    assert "periodic-intercept" in list(replay.options)
    at.radio(key="view_select").set_value("Smart Decision").run()
    assert not at.exception
    decision_text = " ".join(str(item.value) for item in at.caption).lower()
    assert "illumination" in decision_text or "observed hit" in decision_text
    assert "stares" in decision_text
    at.radio(key="view_select").set_value("Metrics Compare").run()
    assert not at.exception
    compare_text = " ".join(str(item.value) for item in at.caption).lower()
    assert "periodic-intercept" in compare_text
    assert "v2" in compare_text
    assert "v4" in compare_text
    assert "8000" in compare_text or "v3" in compare_text
    assert "9000" in compare_text or "v4" in compare_text
    at.radio(key="view_select").set_value("Run History").run()
    assert not at.exception
    hist = at.selectbox(key="hist_strategy")
    assert list(hist.options)[0] == "(all)"
    assert list(hist.options)[1:] == list(PUBLIC_STRATEGIES)
    at.radio(key="view_select").set_value("Model & Data Lineage").run()
    assert not at.exception
