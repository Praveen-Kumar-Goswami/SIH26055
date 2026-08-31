from __future__ import annotations


def test_dashboard_app_imports_cleanly() -> None:
    import smartscan.dashboard.app as app

    assert callable(app.main)
    assert callable(app._session_state)
