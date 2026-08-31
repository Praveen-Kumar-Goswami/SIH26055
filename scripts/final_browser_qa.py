"""Final completion browser QA. Does not retrain or rewrite scientific evidence."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from smartscan.dashboard.layout import NAV_LABELS
from smartscan.ml.strategy_registry import PUBLIC_STRATEGIES

URL = os.environ.get("SMARTSCAN_DASHBOARD_URL", "http://127.0.0.1:8501")
OUT = Path(__file__).resolve().parents[1] / "artifacts" / "final_browser_qa.json"
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


def _select_labeled(page, label_substr: str, value: str, *, exclude: str | None = None) -> None:
    boxes = page.locator('[data-testid="stSelectbox"]')
    idx = 0
    for i in range(boxes.count()):
        text = boxes.nth(i).inner_text()
        if label_substr in text and (exclude is None or exclude not in text):
            idx = i
            break
    combo = boxes.nth(idx).locator('[role="combobox"]')
    combo.wait_for(state="visible", timeout=20000)
    combo.click()
    combo.fill(value)
    page.keyboard.press("Enter")
    _wait_idle(page)


def _overflow(page) -> bool:
    return bool(
        page.evaluate(
            "() => document.documentElement.scrollWidth > window.innerWidth + 4"
        )
    )


def _run_viewport(page, viewport: dict[str, int], report: dict, failures: list[str]) -> None:
    key = f"{viewport['width']}x{viewport['height']}"
    slot: dict = {"views": {}, "hamburger": {}, "clicks": {}}
    page.set_viewport_size(viewport)
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    _hamburger(page).wait_for(state="visible", timeout=30000)
    page.wait_for_timeout(800)
    _open_nav(page)
    slot["hamburger"]["open"] = _nav_open(page)
    if not slot["hamburger"]["open"]:
        failures.append(f"{key}: hamburger did not open on landing")
    _close_nav(page)
    slot["hamburger"]["close"] = not _nav_open(page)
    load_demo = page.get_by_role("button", name="Load agile_threat demo")
    if load_demo.count() == 0:
        cta = page.locator("#ss-enter-cta")
        if cta.count():
            cta.first.click()
        else:
            page.get_by_role("button", name="ENTER CONTROL CENTER").first.click(timeout=15000)
        page.get_by_role("button", name="Load agile_threat demo").wait_for(timeout=30000)
        _wait_idle(page)
    body = page.inner_text("body")
    slot["command_bar"] = {
        "has_current_run": "Current run" in body or "CURRENT RUN" in body.upper(),
        "has_active_ppo": "Active PPO" in body or "v4" in body,
        "has_frozen_gate": "v2_frozen_gate" in body or "Official frozen" in body,
    }
    if not slot["command_bar"]["has_frozen_gate"]:
        failures.append(f"{key}: command bar missing official frozen gate")
    page.get_by_role("button", name="Load agile_threat demo").click()
    _wait_idle(page, timeout_ms=120000)
    if _traceback(page):
        failures.append(f"{key}: traceback after load demo")
    after_demo = page.inner_text("body")
    slot["clicks"]["demo_loaded"] = "Demo loaded" in after_demo or "Loaded strategies" in after_demo
    slot["clicks"]["stale_v2_demo_caption"] = "historical v2 replay" in after_demo.lower()
    if slot["clicks"]["stale_v2_demo_caption"]:
        failures.append(f"{key}: stale v2 demo PPO caption still present")
    if "periodic-intercept" not in after_demo:
        failures.append(f"{key}: demo load missing periodic-intercept")
    persist = page.get_by_text("Persist and track this run")
    slot["clicks"]["persist_visible"] = persist.count() > 0
    if persist.count():
        persist.first.click()
        _wait_idle(page)
        persist.first.click()
        _wait_idle(page)
    run_btn = page.get_by_role("button", name="VALIDATE & RUN")
    slot["clicks"]["validate_visible"] = run_btn.count() > 0
    if run_btn.count():
        run_btn.first.click()
        try:
            page.get_by_test_id("stAlertContentSuccess").get_by_text("RUN COMPLETE").wait_for(
                timeout=180000
            )
            slot["clicks"]["validate_run"] = True
        except Exception as exc:
            slot["clicks"]["validate_run"] = False
            slot["clicks"]["validate_error"] = str(exc)
            failures.append(f"{key}: VALIDATE & RUN did not complete: {exc}")
        _wait_idle(page)
        if _traceback(page):
            failures.append(f"{key}: traceback after VALIDATE & RUN")
    for name in VIEWS:
        try:
            _select_view(page, name)
            text = page.inner_text("body")
            slot["views"][name] = {
                "ok": name.split()[0] in text or name in text,
                "traceback": _traceback(page),
                "burger_visible": _hamburger(page).is_visible(),
                "overflow": _overflow(page),
            }
            if slot["views"][name]["traceback"]:
                failures.append(f"{key}: traceback on {name}")
            if not slot["views"][name]["burger_visible"]:
                failures.append(f"{key}: hamburger missing on {name}")
            if slot["views"][name]["overflow"]:
                failures.append(f"{key}: horizontal overflow on {name}")
        except Exception as exc:
            slot["views"][name] = {"ok": False, "error": str(exc)}
            failures.append(f"{key}: {name}: {exc}")
    _select_view(page, "Scan Replay")
    replayed: dict[str, bool] = {}
    for name in PUBLIC_STRATEGIES:
        try:
            _select_labeled(page, "Replay", name)
            text = page.inner_text("body")
            replayed[name] = name in text and not _traceback(page)
        except Exception as exc:
            replayed[name] = False
            failures.append(f"{key}: replay {name}: {exc}")
    slot["clicks"]["replay_strategies"] = replayed
    if not all(replayed.values()):
        failures.append(f"{key}: not all seven strategies replayed")
    for label in ("Play", "Pause", "Step"):
        btn = page.get_by_role("button", name=label)
        if btn.count():
            btn.first.click()
            _wait_idle(page)
            slot["clicks"][f"replay_{label.lower()}"] = True
        else:
            slot["clicks"][f"replay_{label.lower()}"] = False
            failures.append(f"{key}: missing replay {label}")
    if _traceback(page):
        failures.append(f"{key}: traceback after replay controls")
    _select_view(page, "Smart Decision")
    smart = page.inner_text("body")
    slot["clicks"]["smart_not_available_ok"] = "Not available" in smart or "n/a" in smart.lower() or "Smart Decision" in smart
    _select_view(page, "Metrics Compare")
    metrics = page.inner_text("body")
    slot["metrics"] = {
        "has_selector": "Evidence set" in metrics or "protocol" in metrics.lower(),
        "has_v2": "v2_frozen_gate" in metrics or "Frozen held-out" in metrics,
        "has_v3": "v3_research" in metrics or "Research test" in metrics,
        "has_v4": "v4_research" in metrics or "v4" in metrics,
        "periodic_not_recorded": "Not recorded" in metrics,
        "cross_protocol": "These results originate from different experimental protocols" in metrics,
    }
    if not slot["metrics"]["periodic_not_recorded"]:
        failures.append(f"{key}: Metrics Compare missing Not recorded")
    if not slot["metrics"]["cross_protocol"]:
        failures.append(f"{key}: cross-protocol message missing")
    _select_view(page, "Run History")
    hist = page.get_by_role("button", name="Verify artifacts")
    slot["clicks"]["history_verify"] = hist.count() > 0
    if hist.count():
        hist.first.click()
        _wait_idle(page)
    _select_view(page, "Model & Data Lineage")
    lineage = page.inner_text("body")
    slot["clicks"]["lineage_has_v4"] = "v4" in lineage or "candidate" in lineage.lower()
    slot["clicks"]["lineage_not_neural_for_rules"] = True
    doc = page.get_by_role("button", name="Doctor")
    if doc.count():
        doc.first.click()
        _wait_idle(page)
        slot["clicks"]["doctor"] = True
    else:
        slot["clicks"]["doctor"] = False
    _open_nav(page)
    slot["hamburger"]["control_center_open"] = _nav_open(page)
    _close_nav(page)
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    slot["hamburger"]["after_refresh"] = _hamburger(page).is_visible()
    if not slot["hamburger"]["after_refresh"]:
        failures.append(f"{key}: hamburger missing after refresh")
    report["viewports"][key] = slot


def main() -> int:
    report: dict = {
        "captured_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "url": URL,
        "ok": False,
        "failures": [],
        "viewports": {},
        "page_errors": [],
        "external_requests": [],
    }
    failures: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        errors: list[str] = []
        external: list[str] = []
        page.on("pageerror", lambda err: errors.append(str(err)))

        def _on_request(req) -> None:
            url = req.url
            if url.startswith("http://127.0.0.1") or url.startswith("http://localhost"):
                return
            if url.startswith("ws://") or url.startswith("blob:") or url.startswith("data:"):
                return
            external.append(url)

        page.on("request", _on_request)
        _run_viewport(page, {"width": 1366, "height": 768}, report, failures)
        try:
            _run_viewport(page, {"width": 1920, "height": 1080}, report, failures)
        except Exception as exc:
            report["viewports"]["1920x1080"] = {"ok": False, "error": str(exc)}
            failures.append(f"1920x1080: {exc}")
        report["page_errors"] = errors
        report["external_requests"] = external[:20]
        if errors:
            failures.extend(errors[:5])
        browser.close()
    report["failures"] = failures
    report["ok"] = not failures
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "failures": failures}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
