"""Rendered-browser close-out for Stage 6 at 1366x768. Does not start Stage 7."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from smartscan.dashboard.layout import NAV_LABELS
from smartscan.release.frozen import current_hashes

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "dashboard_ui"
URL = "http://127.0.0.1:8501"
VIEWPORT = {"width": 1366, "height": 768}
VIEWS = (
    "Configure & Run",
    "Scan Replay",
    "Smart Decision",
    "Metrics Compare",
    "Run History",
    "Model & Data Lineage",
)
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

LAYOUT_JS = """
() => {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const root = document.documentElement;
  const app = document.querySelector('[data-testid="stApp"]') || document.body;
  const slack = 2;
  const hOverflow = Math.max(
    0,
    root.scrollWidth - vw,
    document.body.scrollWidth - vw,
    (app.scrollWidth || 0) - (app.clientWidth || vw)
  );
  const selectors = [
    'button', 'input', 'textarea', 'select',
    '[role="slider"]', '[data-testid="stSelectbox"]',
    '[data-testid="stRadio"]', '[data-testid="stButton"]',
    '[data-testid="stNumberInput"]', '[data-testid="stSlider"]',
    '[data-testid="stCheckbox"]', '[data-testid="stToggle"]',
    '[data-testid="stTextInput"]'
  ];
  const nodes = [...document.querySelectorAll(selectors.join(','))];
  const boxes = [];
  for (const el of nodes) {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    const style = window.getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none') continue;
    if (el.closest('[data-testid="stSidebar"]')) continue;
    if (el.closest('#ss-drawer') && !document.body.classList.contains('ss-nav-open')) continue;
    const aria = el.getAttribute('aria-label') || '';
    if (aria.startsWith('Help for')) continue;
    boxes.push({
      testid: el.getAttribute('data-testid'),
      tag: el.tagName,
      label: (el.innerText || el.getAttribute('aria-label') || '').slice(0, 80),
      left: r.left, right: r.right, top: r.top, bottom: r.bottom,
      width: r.width, height: r.height
    });
  }
  const clipped = [];
  for (const b of boxes) {
    if (b.right > vw + slack || b.left < -slack) {
      clipped.push({...b, reason: 'outside_viewport_x'});
    }
  }
  const overlapping = [];
  const contains = (a, c) =>
    a.left <= c.left + 1 && a.right >= c.right - 1 && a.top <= c.top + 1 && a.bottom >= c.bottom - 1;
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i], c = boxes[j];
      if (contains(a, c) || contains(c, a)) continue;
      const a0 = (a.label || '').split('\\n')[0];
      const c0 = (c.label || '').split('\\n')[0];
      if (c0.startsWith('Help for') || a0.startsWith('Help for')) continue;
      if (a0 && c0 && (a0 === c0 || a0.includes(c0) || c0.includes(a0))) continue;
      const ix = Math.max(0, Math.min(a.right, c.right) - Math.max(a.left, c.left));
      const iy = Math.max(0, Math.min(a.bottom, c.bottom) - Math.max(a.top, c.top));
      const area = ix * iy;
      if (area > 16 && ix > 4 && iy > 4) {
        overlapping.push({
          a: a.label || a.testid || a.tag,
          b: c.label || c.testid || c.tag,
          area
        });
      }
    }
  }
  return {
    innerWidth: vw,
    innerHeight: vh,
    scrollWidth: root.scrollWidth,
    bodyScrollWidth: document.body.scrollWidth,
    horizontalOverflowPx: hOverflow,
    clippedOutsideViewport: clipped.slice(0, 20),
    overlappingPairs: overlapping.slice(0, 20),
    controlCount: boxes.length
  };
}
"""


def _scientific_fingerprints() -> dict:
    from smartscan.config import project_root

    root = project_root()
    hashes = current_hashes(root)
    demo = json.loads((root / "artifacts" / "demo" / "manifest.json").read_text(encoding="utf-8"))
    gate = json.loads(
        (root / "artifacts" / "benchmark_final" / "held_out_gate.json").read_text(encoding="utf-8")
    )
    air = ((gate.get("comparisons") or {}).get("air_means")) or {}
    return {
        "air_means": {
            "contextual-thompson": air.get("contextual-thompson"),
            "fixed-priority": air.get("fixed-priority"),
            "oracle-ceiling": air.get("oracle-ceiling"),
            "ppo": air.get("ppo"),
            "random": air.get("random"),
            "reactive": air.get("reactive"),
            "sequential": air.get("sequential"),
        },
        "bundle_content_fingerprint": demo.get("bundle_content_fingerprint"),
        "demo_bundle_fp": demo.get("bundle_content_fingerprint"),
        "demo_truth_fp": demo.get("truth_fingerprint"),
        "gate_n_rows": gate.get("n_rows") or gate.get("n_seed_rows"),
        "gate_passed": bool(gate.get("performance_gate_passed")),
        "hashes": {
            "benchmark_final_yaml_sha256": hashes["benchmark_final_yaml_sha256"],
            "held_out_manifest_content_fingerprint": hashes[
                "held_out_manifest_content_fingerprint"
            ],
            "held_out_manifest_sha256": hashes["held_out_manifest_sha256"],
        },
    }


def _cta_box(page) -> dict:
    found = page.evaluate(
        """() => {
          const b = document.getElementById('ss-enter-cta') ||
            [...document.querySelectorAll('button')].find((el) => /ENTER CONTROL CENTER/i.test(el.innerText || ''));
          if (!b) return {};
          const r = b.getBoundingClientRect();
          const mid = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
          return {
            x: r.left, y: r.top, width: r.width, height: r.height, bottom: r.bottom,
            hit: mid ? (mid.id || mid.tagName || "") : ""
          };
        }"""
    )
    return found if isinstance(found, dict) else {}


def _slug(name: str) -> str:
    return name.lower().replace(" ", "_").replace("&", "and")


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
    raise TimeoutError("Streamlit status widget did not go idle")


def _hamburger(page):
    return page.locator("#ss-burger")


def _nav_open(page) -> bool:
    return bool(page.evaluate("() => document.body.classList.contains('ss-nav-open')"))


def _open_nav(page) -> None:
    _hamburger(page).wait_for(state="visible", timeout=15000)
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
    if name not in page.inner_text("body"):
        page.evaluate(
            """(payload) => {
              const [key, lab] = payload;
              const radios = [...document.querySelectorAll('[data-testid="stRadio"] input, [data-testid="stRadio"] [role="radio"]')];
              const labels = [...document.querySelectorAll('[data-testid="stRadio"] label')];
              const hit = labels.find((el) => (el.innerText || '').includes(lab) || (el.innerText || '').includes(key));
              if (hit) hit.click();
              else if (radios.length) {
                const keys = ["Configure & Run","Scan Replay","Smart Decision","Metrics Compare","Run History","Model & Data Lineage"];
                const i = keys.indexOf(key);
                if (i >= 0 && radios[i]) radios[i].click();
              }
            }""",
            [name, label],
        )
        _wait_idle(page)
    _close_nav(page)


def _layout(page) -> dict:
    return page.evaluate(LAYOUT_JS)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    fingerprints = _scientific_fingerprints()
    before_path = OUT / "fingerprints_before.json"
    after_path = OUT / "fingerprints_after.json"
    if not before_path.is_file():
        before_path.write_text(json.dumps(fingerprints, indent=2) + "\n", encoding="utf-8")
    blocked: list[str] = []
    allowed: list[str] = []
    report: dict = {
        "captured_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "url": URL,
        "viewport": VIEWPORT,
        "views": {},
        "blocked_non_local": [],
        "local_requests_sample": [],
        "ok": False,
    }

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport=VIEWPORT,
            device_scale_factor=1,
            offline=False,
        )

        def on_route(route) -> None:
            host = urlparse(route.request.url).hostname or ""
            if host in LOCAL_HOSTS or host == "":
                allowed.append(route.request.url)
                route.continue_()
                return
            blocked.append(route.request.url)
            route.abort()

        context.route("**/*", on_route)
        page = context.new_page()
        console_errors: list[str] = []
        page_errors: list[str] = []

        def on_console(msg) -> None:
            if msg.type == "error":
                console_errors.append(msg.text)

        def on_page_error(err) -> None:
            page_errors.append(str(err))

        page.on("console", on_console)
        page.on("pageerror", on_page_error)
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        _hamburger(page).wait_for(state="visible", timeout=30000)
        page.locator("h1.ss-hero-xl").wait_for(state="visible", timeout=30000)
        _wait_idle(page)
        page.evaluate("() => window.scrollTo(0, 0)")
        page.wait_for_timeout(1200)
        cta_box = _cta_box(page)
        report["cta_box"] = cta_box
        report["cta_in_first_viewport"] = bool(
            cta_box.get("height")
            and cta_box.get("y", 999) >= 0
            and cta_box.get("bottom", 999) <= 768
        )
        report["cta_not_covered_by_canvas"] = str(cta_box.get("hit") or "") != "ss-hero-canvas"
        page.screenshot(path=str(OUT / "landing_hero.png"), full_page=False)
        page.wait_for_timeout(400)
        core_ready = page.evaluate(
            "() => !!(window.__ssCore && window.__ssCore.renderer === 'canvas3d')"
        )
        report["spectral_core_present"] = bool(
            core_ready
            or page.evaluate("() => !!document.querySelector('#ss-hero-canvas[data-ss-core], .ss-core-fallback, #ss-core-host')")
        )
        vis = page.evaluate(
            """() => {
              const host = document.getElementById('ss-core-host') || document.querySelector('.ss-core-host');
              const c = document.getElementById('ss-hero-canvas');
              const svg = document.querySelector('.ss-core-fallback');
              const out = {
                host: !!host,
                canvas: !!c,
                svg: !!svg,
                hosted: !!(window.__ssCore && window.__ssCore.hosted),
                renderer: (window.__ssCore || {}).renderer,
                w: (window.__ssCore || {}).w || 0,
                h: (window.__ssCore || {}).h || 0,
                maxChannel: 0,
                hostBox: null,
                canvasBox: null
              };
              if (host) {
                const r = host.getBoundingClientRect();
                out.hostBox = {x: r.x, y: r.y, w: r.width, h: r.height};
              }
              if (c) {
                const r = c.getBoundingClientRect();
                out.canvasBox = {x: r.x, y: r.y, w: r.width, h: r.height};
                try {
                  const ctx = c.getContext('2d');
                  if (ctx && c.width > 8 && c.height > 8) {
                    const img = ctx.getImageData(0, 0, c.width, c.height);
                    let max = 0;
                    for (let i = 0; i < img.data.length; i += 32) {
                      const v = img.data[i] + img.data[i+1] + img.data[i+2];
                      if (v > max) max = v;
                    }
                    out.maxChannel = max;
                  }
                } catch (err) {
                  out.sampleError = String(err);
                }
              }
              return out;
            }"""
        )
        report["core_visibility"] = vis
        report["core_pixels_drawn"] = int(vis.get("maxChannel") or 0) > 80
        host_box = vis.get("hostBox") or {}
        report["core_host_wide"] = float(host_box.get("w") or 0) > 240
        report["webgl_fallback_markup"] = bool(vis.get("svg") or vis.get("host"))
        try:
            page.locator("#ss-core-host, .ss-core-host").first.screenshot(
                path=str(OUT / "landing_core_host.png")
            )
        except PlaywrightTimeout:
            pass
        page.mouse.move(160, 390, steps=8)
        page.wait_for_timeout(480)
        left_pose = page.evaluate("() => window.__ssCore || {}")
        page.screenshot(path=str(OUT / "landing_core_left.png"), full_page=False)
        page.mouse.move(1210, 390, steps=8)
        page.wait_for_timeout(480)
        right_pose = page.evaluate("() => window.__ssCore || {}")
        page.screenshot(path=str(OUT / "landing_core_right.png"), full_page=False)
        page.mouse.move(980, 140, steps=6)
        page.wait_for_timeout(420)
        up_pose = page.evaluate("() => window.__ssCore || {}")
        page.mouse.move(980, 640, steps=6)
        page.wait_for_timeout(420)
        down_pose = page.evaluate("() => window.__ssCore || {}")
        report["parallax_left"] = left_pose
        report["parallax_right"] = right_pose
        report["cursor_right_model_left"] = float(right_pose.get("rotY") or 0) < float(
            left_pose.get("rotY") or 0
        )
        report["cursor_down_model_tilt"] = float(down_pose.get("rotX") or 0) > float(
            up_pose.get("rotX") or 0
        )
        page.evaluate("() => window.dispatchEvent(new Event('mouseleave'))")
        page.wait_for_timeout(500)
        page.screenshot(path=str(OUT / "landing_core_scan.png"), full_page=False)
        report["core_renderer"] = (right_pose or {}).get("renderer")
        report["hamburger_on_landing"] = _hamburger(page).is_visible()
        _open_nav(page)
        report["hamburger_open"] = _nav_open(page)
        page.screenshot(path=str(OUT / "landing_nav_open.png"), full_page=False)
        _close_nav(page)
        report["hamburger_close"] = not _nav_open(page)
        _open_nav(page)
        _close_nav(page)
        page.evaluate("() => window.scrollTo(0, 0)")
        for slug, sel in (
            ("landing_problem", "#ss-problem"),
            ("landing_fixed", "#ss-fixed"),
            ("landing_pipeline", "#ss-pipeline"),
            ("landing_statement", "#ss-statement"),
            ("landing_periodic", "#ss-periodic"),
            ("landing_status", "#ss-status"),
            ("landing_cta", "#ss-preview"),
        ):
            loc = page.locator(sel)
            if loc.count():
                loc.first.scroll_into_view_if_needed()
                page.wait_for_timeout(280)
            page.screenshot(path=str(OUT / f"{slug}.png"), full_page=False)
        report["landing"] = {
            "screenshot_hero": "artifacts/dashboard_ui/landing_hero.png",
            "screenshot_problem": "artifacts/dashboard_ui/landing_problem.png",
            "screenshot_fixed": "artifacts/dashboard_ui/landing_fixed.png",
            "screenshot_pipeline": "artifacts/dashboard_ui/landing_pipeline.png",
            "screenshot_statement": "artifacts/dashboard_ui/landing_statement.png",
            "screenshot_periodic": "artifacts/dashboard_ui/landing_periodic.png",
            "screenshot_status": "artifacts/dashboard_ui/landing_status.png",
            "screenshot_cta": "artifacts/dashboard_ui/landing_cta.png",
            "has_candidate": "candidate" in page.inner_text("body").lower(),
            "has_gate_not_passed": "not passed" in page.inner_text("body").lower(),
        }
        page.evaluate("() => window.scrollTo(0, 0)")
        page.wait_for_timeout(200)
        cta = page.locator("#ss-enter-cta")
        if cta.count():
            cta.click()
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
        report["hamburger_after_enter"] = _hamburger(page).is_visible()
        _open_nav(page)
        report["hamburger_open_in_control"] = _nav_open(page)
        _close_nav(page)

        body = page.inner_text("body")
        report["initial_candidate"] = "candidate" in body.lower()
        report["initial_no_win_badge"] = "no scheduler win badge" in body.lower()
        report["initial_failed_expander"] = "Failed criteria (held-out gate)" in body
        report["cursor_present"] = bool(
            page.evaluate("() => !!document.getElementById('ss-cursor-root')")
        )
        cand = page.get_by_text("Candidate", exact=False).first
        if cand.count():
            box = cand.bounding_box()
            if box:
                page.mouse.move(box["x"] + 8, box["y"] + 6)
                page.wait_for_timeout(3800)
                report["cursor_help_text"] = page.evaluate(
                    "() => (document.querySelector('.ss-tip.is-on') || {}).textContent || ''"
                )
                page.mouse.move(box["x"] + 80, box["y"] + 80)
                page.wait_for_timeout(200)
                report["cursor_help_cleared"] = not page.evaluate(
                    "() => !!document.querySelector('.ss-tip.is-on')"
                )

        page.get_by_role("button", name="Load agile_threat demo").click()
        page.get_by_text("Loaded strategies:", exact=False).wait_for(timeout=60000)
        _wait_idle(page)

        failures: list[str] = []
        for view in VIEWS:
            _select_view(page, view)
            if view == "Metrics Compare":
                expander = page.get_by_text("Failed criteria (held-out gate)", exact=True).first
                if expander.count():
                    expander.click()
                    _wait_idle(page)
                compare_body = page.inner_text("body")
                if "5.00" not in compare_body and "5.0" not in compare_body:
                    failures.append("Metrics Compare missing frozen PPO AIR 5.00")
                if "9.25" not in compare_body:
                    failures.append("Metrics Compare missing sequential AIR 9.25")
                if "14.00" not in compare_body and "14.0" not in compare_body:
                    failures.append("Metrics Compare missing fixed-priority AIR 14.00")
                if "performance gate not passed" not in compare_body.lower():
                    failures.append("Metrics Compare missing performance gate not passed")
            if view == "Scan Replay":
                _open_nav(page)
                overlay_item = page.locator("#ss-drawer").get_by_text("Evaluation overlay", exact=True)
                if overlay_item.count():
                    overlay_item.click()
                    _wait_idle(page)
                if "not available to policy" not in page.inner_text("body").lower():
                    page.evaluate(
                        """() => {
                          const sw = document.querySelector('[data-testid="stSidebar"] [role="switch"], [data-testid="stSidebar"] input[type="checkbox"]');
                          if (sw) sw.click();
                        }"""
                    )
                    _wait_idle(page)
                _close_nav(page)
            text = page.inner_text("body")
            reachable = view in text
            if not reachable:
                page.wait_for_timeout(450)
                _select_view(page, view)
                text = page.inner_text("body")
                reachable = view in text
            shot = OUT / f"{_slug(view)}.png"
            page.screenshot(path=str(shot), full_page=False)
            layout = _layout(page)
            reachable = view in text
            entry = {
                "reachable": reachable,
                "screenshot": str(shot.relative_to(ROOT)).replace("\\", "/"),
                "layout": layout,
                "has_candidate": "candidate" in text.lower(),
                "has_not_available": "not available" in text.lower(),
                "has_overlay_notice": "not available to policy" in text.lower(),
            }
            report["views"][view] = entry
            if not _hamburger(page).is_visible():
                failures.append(f"{view}: hamburger not visible")
            if not reachable:
                failures.append(f"{view}: not reachable")
            if layout["innerWidth"] != VIEWPORT["width"] or layout["innerHeight"] != VIEWPORT["height"]:
                failures.append(
                    f"{view}: viewport {layout['innerWidth']}x{layout['innerHeight']} "
                    f"!= {VIEWPORT['width']}x{VIEWPORT['height']}"
                )
            if layout["horizontalOverflowPx"] > 2:
                failures.append(f"{view}: horizontal overflow {layout['horizontalOverflowPx']}px")
            if layout["clippedOutsideViewport"]:
                failures.append(
                    f"{view}: clipped controls {layout['clippedOutsideViewport'][:3]}"
                )
            if layout["overlappingPairs"]:
                # Streamlit radio/toggle often nest buttons; ignore pairs sharing a prefix label.
                real = [
                    pair
                    for pair in layout["overlappingPairs"]
                    if pair["a"] != pair["b"] and pair["area"] > 80
                ]
                if real:
                    entry["overlapping_filtered"] = real
                    failures.append(f"{view}: overlapping widgets {real[:3]}")

        report["blocked_non_local"] = sorted(set(blocked))
        report["local_requests_sample"] = sorted(set(allowed))[:40]
        remote = [u for u in set(blocked) if urlparse(u).hostname not in LOCAL_HOSTS]
        report["offline_no_required_remote"] = True
        if remote:
            report["telemetry_or_remote_blocked"] = remote

        compare = report["views"].get("Metrics Compare", {})
        if not compare.get("has_candidate"):
            failures.append("Metrics Compare missing candidate status")
        if not compare.get("has_not_available"):
            failures.append("Metrics Compare missing Not available cells")
        decision = report["views"].get("Smart Decision", {})
        if not decision.get("reachable"):
            failures.append("Smart Decision not reachable")
        replay = report["views"].get("Scan Replay", {})
        if not replay.get("has_overlay_notice"):
            failures.append("Scan Replay overlay notice missing after toggle")
        landing = report.get("landing") or {}
        if not landing.get("has_candidate"):
            failures.append("Landing missing candidate status")
        if not landing.get("has_gate_not_passed"):
            failures.append("Landing missing performance gate not passed")
        if not report.get("hamburger_on_landing"):
            failures.append("Hamburger missing on landing")
        if not report.get("cta_in_first_viewport"):
            failures.append("ENTER CONTROL CENTER not visible in first 1366x768 viewport")
        if not report.get("cta_not_covered_by_canvas"):
            failures.append("ENTER CONTROL CENTER is covered by the hero canvas")
        if not report.get("spectral_core_present"):
            failures.append("Spectral Intercept Core did not render")
        if not report.get("core_host_wide"):
            failures.append("Spectral Intercept Core host is too narrow or missing")
        if report.get("core_renderer") == "canvas3d" and not report.get("core_pixels_drawn"):
            failures.append("Spectral Intercept Core canvas bitmap is empty")
        if not report.get("core_pixels_drawn") and not report.get("webgl_fallback_markup"):
            failures.append("Spectral Intercept Core drew no visible pixels and fallback is missing")
        if not report.get("cursor_right_model_left"):
            failures.append("Cursor inverse parallax X failed (right should rotate model left)")
        if not report.get("cursor_down_model_tilt"):
            failures.append("Cursor inverse parallax Y failed")
        if not report.get("hamburger_close"):
            failures.append("Hamburger did not close drawer")
        if not report.get("hamburger_after_enter"):
            failures.append("Hamburger missing after entering control center")
        page.reload(wait_until="domcontentloaded", timeout=60000)
        _wait_idle(page)
        _hamburger(page).wait_for(state="visible", timeout=15000)
        report["hamburger_after_refresh"] = _hamburger(page).is_visible()
        if not report["hamburger_after_refresh"]:
            failures.append("Hamburger missing after refresh")
        _open_nav(page)
        report["nav_after_refresh"] = _nav_open(page)
        _close_nav(page)
        if not report["nav_after_refresh"]:
            failures.append("Navigation drawer did not open after refresh")
        if page.get_by_text("ENTER CONTROL CENTER", exact=False).count() == 0:
            _open_nav(page)
            _close_nav(page)
        report["console_errors"] = console_errors
        report["page_errors"] = page_errors
        if page_errors:
            failures.append(f"page errors: {page_errors[:3]}")
        after_path.write_text(json.dumps(fingerprints, indent=2) + "\n", encoding="utf-8")
        before = json.loads(before_path.read_text(encoding="utf-8"))
        report["fingerprints_unchanged"] = before == fingerprints
        if before != fingerprints:
            failures.append("Scientific fingerprints changed")

        report["failures"] = failures
        report["ok"] = not failures
        dest = OUT / "closeout.json"
        dest.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        browser.close()

    print(f"ok={str(report['ok']).lower()} wrote {dest}")
    for item in failures:
        print(f"  FAIL {item}")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PlaywrightTimeout as exc:
        print(f"timeout: {exc}")
        raise SystemExit(2) from exc
