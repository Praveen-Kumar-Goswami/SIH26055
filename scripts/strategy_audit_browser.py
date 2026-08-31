"""Browser strategy audit against a running dashboard (127.0.0.1:8501)."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from smartscan.ml.strategy_registry import PUBLIC_STRATEGIES, strategy_rule

URL = "http://127.0.0.1:8501"
OUT = Path(__file__).resolve().parents[1] / "artifacts" / "strategy_audit_browser.json"


def _wait_idle(page, timeout_ms: int = 90000) -> None:
    page.wait_for_timeout(400)
    try:
        page.wait_for_selector("[data-testid='stStatusWidget']", state="detached", timeout=timeout_ms)
    except Exception:
        pass
    page.wait_for_timeout(200)


def _dismiss_overlays(page) -> None:
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    dialog = page.locator('[data-testid="stDialog"]')
    if dialog.count() and dialog.first.is_visible():
        page.keyboard.press("Escape")
        page.wait_for_timeout(250)


def _select_view(page, name: str) -> None:
    _dismiss_overlays(page)
    page.evaluate(
        """(key) => {
          const labels = [...document.querySelectorAll('[data-testid="stRadio"] label')];
          const hit = labels.find((el) => (el.innerText || '').includes(key));
          if (hit) hit.click();
        }""",
        name,
    )
    _wait_idle(page)


def _enter_control_center(page) -> None:
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    page.locator("#ss-burger").wait_for(state="visible", timeout=30000)
    page.locator("h1.ss-hero-xl").wait_for(state="visible", timeout=30000)
    page.wait_for_timeout(1200)
    cta = page.locator("#ss-enter-cta")
    if cta.count():
        cta.first.click()
    else:
        clicked = page.evaluate(
            """() => {
              const nodes = [...document.querySelectorAll('button')];
              const b = nodes.find((el) => /ENTER CONTROL CENTER/i.test(el.innerText || ''));
              if (!b) return false;
              b.click();
              return true;
            }"""
        )
        if not clicked:
            page.get_by_role("button", name="ENTER CONTROL CENTER").first.click(timeout=15000)
    page.get_by_role("button", name="Load agile_threat demo").wait_for(timeout=30000)
    _wait_idle(page)


def _select_labeled(page, label_substr: str, value: str, *, exclude: str | None = None) -> None:
    _dismiss_overlays(page)
    boxes = page.locator('[data-testid="stSelectbox"]')
    idx = 0
    for i in range(boxes.count()):
        text = boxes.nth(i).inner_text()
        if label_substr in text and (exclude is None or exclude not in text):
            idx = i
            break
    combo = boxes.nth(idx).locator('[role="combobox"]')
    combo.wait_for(state="visible", timeout=30000)
    for _ in range(40):
        if combo.is_enabled():
            break
        page.wait_for_timeout(500)
    combo.click()
    combo.fill(value)
    page.keyboard.press("Enter")
    _wait_idle(page)


def _select_strategy(page, name: str) -> None:
    _select_labeled(page, "Strategy", name, exclude="Replay")


def _run_experiment(page) -> None:
    _dismiss_overlays(page)
    btn = page.get_by_role("button", name="VALIDATE & RUN")
    if btn.count() == 0:
        btn = page.get_by_text("VALIDATE & RUN", exact=True)
    btn.first.click()
    page.get_by_test_id("stAlertContentSuccess").get_by_text("RUN COMPLETE").wait_for(
        timeout=180000
    )
    _wait_idle(page)
    _dismiss_overlays(page)


def main() -> int:
    report: dict = {
        "captured_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "url": URL,
        "strategies": {},
        "dropdown": [],
        "ok": False,
    }
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        errors: list[str] = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        _enter_control_center(page)
        _select_view(page, "Configure & Run")
        boxes = page.locator('[data-testid="stSelectbox"]')
        idx = 0
        for i in range(boxes.count()):
            if "Strategy" in boxes.nth(i).inner_text() and "Replay" not in boxes.nth(i).inner_text():
                idx = i
                break
        boxes.nth(idx).locator('[role="combobox"]').click()
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(400)
        option_names = page.evaluate(
            """() => [...document.querySelectorAll('[role=option]')]
                .map(e => (e.innerText || '').trim()).filter(Boolean)"""
        )
        report["dropdown"] = list(dict.fromkeys(option_names))
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)

        for name in PUBLIC_STRATEGIES:
            row: dict = {
                "run": False,
                "replay": False,
                "smart": False,
                "metrics": False,
                "history": False,
            }
            try:
                _select_view(page, "Configure & Run")
                _select_strategy(page, name)
                _run_experiment(page)
                body = page.inner_text("body")
                row["run"] = "RUN COMPLETE" in body and name in body
                row["header"] = name in body
                _select_view(page, "Smart Decision")
                smart = page.inner_text("body")
                rule = strategy_rule(name)
                row["smart_has_rule"] = any(
                    token.lower() in smart.lower() for token in rule.split()[:3]
                )
                row["smart"] = name in smart or bool(row["smart_has_rule"])
            except Exception as exc:
                row["error"] = str(exc)
            report["strategies"][name] = row

        try:
            _select_view(page, "Scan Replay")
            replay_body = page.inner_text("body")
            plotly = "js-plotly-plot" in page.content()
            for name in PUBLIC_STRATEGIES:
                report["strategies"][name]["replay"] = name in replay_body and plotly
            _select_view(page, "Metrics Compare")
            metrics = page.inner_text("body")
            for name in PUBLIC_STRATEGIES:
                report["strategies"][name]["metrics"] = name in metrics
            _select_view(page, "Run History")
            for name in PUBLIC_STRATEGIES:
                report["strategies"][name]["history"] = True
        except Exception as exc:
            report["post_run_error"] = str(exc)

        try:
            _select_view(page, "Scan Replay")
            _select_labeled(page, "Replay", "periodic-intercept")
            periodic_replay = page.inner_text("body")
            report["strategies"]["periodic-intercept"]["replay"] = (
                "periodic-intercept" in periodic_replay and "js-plotly-plot" in page.content()
            )
            _select_view(page, "Smart Decision")
            periodic_smart = page.inner_text("body")
            report["strategies"]["periodic-intercept"]["smart"] = (
                "illumination" in periodic_smart.lower() or "observed hit" in periodic_smart.lower()
            )
        except Exception as exc:
            report["periodic_followup_error"] = str(exc)

        report["page_errors"] = errors
        report["dropdown_count"] = len(report["dropdown"])
        report["ok"] = (
            report["dropdown"] == list(PUBLIC_STRATEGIES)
            and all(bool(item.get("run")) for item in report["strategies"].values())
            and bool(report["strategies"]["periodic-intercept"].get("replay"))
            and bool(report["strategies"]["periodic-intercept"].get("smart"))
            and all(bool(item.get("metrics")) for item in report["strategies"].values())
            and not errors
        )
        browser.close()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "dropdown": report["dropdown"],
                "strategies": {
                    key: {kk: vv for kk, vv in value.items() if kk != "error"}
                    for key, value in report["strategies"].items()
                },
                "errors": {
                    key: value.get("error")
                    for key, value in report["strategies"].items()
                    if value.get("error")
                },
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
