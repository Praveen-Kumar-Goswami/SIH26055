"""Stability-audit browser pass at 1366x768. Does not retrain or rewrite evidence."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from smartscan.dashboard.layout import NAV_LABELS

URL = os.environ.get("SMARTSCAN_DASHBOARD_URL", "http://127.0.0.1:8501")
VIEWPORT = {"width": 1366, "height": 768}
OUT = Path(__file__).resolve().parents[1] / "artifacts" / "stability_audit_browser.json"
VIEWS = (
    "Configure & Run",
    "Scan Replay",
    "Smart Decision",
    "Metrics Compare",
    "Run History",
    "Model & Data Lineage",
)


def _wait_idle(page, timeout_ms: int = 60000) -> None:
    deadline = time.time() + timeout_ms / 1000
    page.wait_for_timeout(300)
    while time.time() < deadline:
        running = page.locator('[data-testid="stStatusWidget"]').count()
        if running == 0:
            page.wait_for_timeout(200)
            if page.locator('[data-testid="stStatusWidget"]').count() == 0:
                return
        page.wait_for_timeout(200)


def _hamburger(page):
    return page.locator("#ss-burger")


def _nav_open(page) -> bool:
    return bool(page.evaluate("() => document.body.classList.contains('ss-nav-open')"))


def _open_nav(page) -> None:
    _hamburger(page).wait_for(state="visible", timeout=20000)
    if not _nav_open(page):
        _hamburger(page).click()
        page.wait_for_timeout(280)


def _close_nav(page) -> None:
    if _nav_open(page):
        _hamburger(page).click()
        page.wait_for_timeout(280)


def _select_view(page, name: str) -> None:
    label = NAV_LABELS.get(name, name)
    _open_nav(page)
    drawer = page.locator("#ss-drawer")
    target = drawer.get_by_text(label, exact=True)
    if target.count() == 0:
        target = drawer.get_by_text(name, exact=True)
    target.click()
    _wait_idle(page)
    _close_nav(page)


def _traceback(page) -> bool:
    body = page.inner_text("body")
    return "Traceback" in body or "IndentationError" in body or "ImportError" in body


def main() -> int:
    report: dict = {
        "captured_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "url": URL,
        "viewport": VIEWPORT,
        "ok": False,
        "failures": [],
        "views": {},
        "hamburger": {},
        "metrics": {},
        "command_bar": {},
    }
    failures: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport=VIEWPORT)
        errors: list[str] = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        _hamburger(page).wait_for(state="visible", timeout=30000)
        page.wait_for_timeout(800)
        _open_nav(page)
        report["hamburger"]["open"] = _nav_open(page)
        if not report["hamburger"]["open"]:
            failures.append("hamburger did not open on landing")
        _close_nav(page)
        report["hamburger"]["close"] = not _nav_open(page)
        cta = page.locator("#ss-enter-cta")
        if cta.count():
            cta.first.click()
        else:
            page.get_by_role("button", name="ENTER CONTROL CENTER").first.click(timeout=15000)
        page.get_by_role("button", name="Load agile_threat demo").wait_for(timeout=30000)
        _wait_idle(page)
        body = page.inner_text("body")
        report["command_bar"]["has_current_run"] = "Current run" in body or "CURRENT RUN" in body.upper()
        report["command_bar"]["has_active_ppo"] = "Active PPO" in body or "v4" in body
        report["command_bar"]["has_frozen_gate"] = "v2_frozen_gate" in body or "Official frozen" in body
        if not report["command_bar"]["has_frozen_gate"]:
            failures.append("command bar missing official frozen gate")
        page.get_by_role("button", name="Load agile_threat demo").click()
        _wait_idle(page, timeout_ms=120000)
        if _traceback(page):
            failures.append("traceback after load demo")
        for name in VIEWS:
            try:
                _select_view(page, name)
                text = page.inner_text("body")
                report["views"][name] = {
                    "ok": name.split()[0] in text or name in text,
                    "traceback": _traceback(page),
                    "burger_visible": _hamburger(page).is_visible(),
                }
                if report["views"][name]["traceback"]:
                    failures.append(f"traceback on {name}")
                if not report["views"][name]["burger_visible"]:
                    failures.append(f"hamburger missing on {name}")
            except Exception as exc:
                report["views"][name] = {"ok": False, "error": str(exc)}
                failures.append(f"{name}: {exc}")
        _select_view(page, "Metrics Compare")
        metrics = page.inner_text("body")
        report["metrics"]["has_selector"] = "Evidence set" in metrics or "protocol" in metrics.lower()
        report["metrics"]["has_v2"] = "v2_frozen_gate" in metrics or "Frozen held-out" in metrics
        report["metrics"]["has_v3"] = "v3_research" in metrics or "Research test" in metrics
        report["metrics"]["has_v4"] = "v4_research" in metrics or "v4" in metrics
        report["metrics"]["periodic_not_recorded"] = "Not recorded" in metrics
        report["metrics"]["periodic_zero"] = "periodic-intercept" in metrics.lower() and (
            "0.00" in metrics and "periodic" in metrics.lower()
        )
        if not report["metrics"]["periodic_not_recorded"]:
            failures.append("Metrics Compare missing Not recorded for periodic-intercept")
        if "These results originate from different experimental protocols" not in metrics:
            failures.append("cross-protocol message missing on Metrics Compare")
        _open_nav(page)
        report["hamburger"]["control_center_open"] = _nav_open(page)
        _close_nav(page)
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        report["hamburger"]["after_refresh"] = _hamburger(page).is_visible()
        if not report["hamburger"]["after_refresh"]:
            failures.append("hamburger missing after refresh")
        report["page_errors"] = errors
        if errors:
            failures.extend(errors[:5])
        browser.close()
    report["failures"] = failures
    report["ok"] = not failures
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "failures": failures, "views": report["views"]}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
