"""Command bar, tour, pointer, hamburger, and hero runtime. Offline only."""

from __future__ import annotations

import json
from typing import Any

from smartscan.dashboard.ui.components import command_bar_html, render_gate_status_html
from smartscan.dashboard.ui.help import help_payload
from smartscan.dashboard.ui.landing import hero_parent_javascript
from smartscan.dashboard.ui.nav import nav_shell_javascript
from smartscan.dashboard.ui.styles import contains_remote_asset
from smartscan.ml.strategy_registry import canonicalize_strategy_id, strategy_kind_label
from smartscan.types import SmartScanError

TOUR_STEPS: tuple[str, ...] = (
    "Choose a scenario that defines the RF environment.",
    "Choose one of the seven public strategies (rule baselines, contextual Thompson, periodic-intercept, or PPO candidate).",
    "Validate and run the receiver, or load the recorded demo.",
    "Replay what the receiver observed in frequency and time.",
    "Inspect Smart Decision reasoning for a recorded command.",
    "Compare this session and the frozen held-out gate. periodic-intercept is live-only.",
    "Inspect lineage and fingerprints for reproducibility.",
)


def pointer_runtime_javascript() -> str:
    payload = json.dumps(help_payload(), separators=(",", ":"))
    return f"""
(function() {{
  var PAYLOAD = {payload};
  var TERMS = PAYLOAD.terms || {{}};
  var DELAY = PAYLOAD.delay_ms || 3500;
  var doc;
  try {{ doc = window.parent.document; }} catch (e) {{ return; }}
  if (!doc || !doc.body) return;
  var coarse = window.matchMedia && window.matchMedia("(pointer: coarse)").matches;
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var prev = doc.getElementById("ss-cursor-root");
  if (prev) prev.remove();
  if (coarse) return;
  var root = doc.createElement("div");
  root.id = "ss-cursor-root";
  var halo = doc.createElement("div");
  halo.className = "ss-cursor";
  halo.setAttribute("aria-hidden", "true");
  var tip = doc.createElement("div");
  tip.className = "ss-tip";
  tip.setAttribute("role", "note");
  root.appendChild(halo);
  root.appendChild(tip);
  doc.body.appendChild(root);
  if (reduce) {{ halo.style.display = "none"; }}
  var timer = null;
  function hideTip() {{
    tip.classList.remove("is-on");
    tip.textContent = "";
  }}
  function lookup(el) {{
    if (!el) return null;
    var helpKey = el.getAttribute && el.getAttribute("data-ss-help");
    if (helpKey && TERMS[helpKey.toLowerCase()]) return TERMS[helpKey.toLowerCase()];
    var blob = ((el.innerText || "") + " " + (el.getAttribute("aria-label") || "") + " " +
      (el.getAttribute("title") || "")).toLowerCase();
    var keys = Object.keys(TERMS);
    for (var i = 0; i < keys.length; i++) {{
      if (blob.indexOf(keys[i]) >= 0) return TERMS[keys[i]];
    }}
    return el.parentElement && el.parentElement !== doc.body ? lookup(el.parentElement) : null;
  }}
  function isOnSection(el) {{
    return !!(el && el.closest && el.closest(".ss-section"));
  }}
  function isPointInSection(x, y) {{
    var secs = doc.querySelectorAll(".ss-section");
    for (var i = 0; i < secs.length; i++) {{
      var r = secs[i].getBoundingClientRect();
      if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) return true;
    }}
    return false;
  }}
  function isHot(el) {{
    if (!el || !el.closest) return false;
    return !!el.closest("button, a, input, select, textarea, [role='button'], [role='radio'], [data-testid='stButton']");
  }}
  function isCta(el) {{
    if (!el) return false;
    var t = (el.innerText || "") + " " + (el.getAttribute("aria-label") || "");
    return /ENTER CONTROL CENTER/i.test(t);
  }}
  function isCoreZone(ev) {{
    var w = window.parent.innerWidth || 1366;
    var h = window.parent.innerHeight || 768;
    return ev.clientX > w * 0.52 && ev.clientY < h * 0.86 && !isCta(ev.target) && !isHot(ev.target);
  }}
  doc.addEventListener("mousemove", function(ev) {{
    if (!reduce) {{
      halo.style.left = ev.clientX + "px";
      halo.style.top = ev.clientY + "px";
    }}
    halo.classList.toggle("is-hot", isHot(ev.target));
    halo.classList.toggle("is-cta", isCta(ev.target));
    halo.classList.toggle("is-core", isCoreZone(ev));
    var onLanding = doc.body.classList.contains("ss-on-landing") || !!doc.querySelector(".ss-landing-root");
    var onSec = isOnSection(ev.target) || isPointInSection(ev.clientX, ev.clientY);
    halo.classList.toggle("is-section", onSec);
    halo.classList.toggle("is-ambient", !reduce && onLanding && !onSec);
    hideTip();
    if (timer) window.parent.clearTimeout(timer);
    var text = lookup(ev.target);
    if (!text) return;
    timer = window.parent.setTimeout(function() {{
      tip.textContent = text;
      tip.style.left = (ev.clientX + 18) + "px";
      tip.style.top = (ev.clientY + 22) + "px";
      tip.classList.add("is-on");
    }}, DELAY);
  }}, true);
  doc.addEventListener("click", hideTip, true);
  doc.addEventListener("mouseleave", hideTip, true);
}})();
"""


def pointer_runtime_html() -> str:
    html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'></head>"
        "<body style='margin:0;background:transparent'><script>"
        + pointer_runtime_javascript()
        + nav_shell_javascript()
        + hero_parent_javascript()
        + "</script></body></html>"
    )
    if contains_remote_asset(html):
        raise RuntimeError("pointer runtime must stay offline")
    return html


def inject_pointer_runtime(st: Any) -> None:
    st.iframe(pointer_runtime_html(), height=1, width="stretch")


def scheduler_generation_tag(model_dir: str | None = None) -> str:
    """v2 / v3 / v4 from the *active* bundle path. Default dashboard path is v4."""

    from smartscan.experiment_protocol import generation_from_bundle_path

    raw = str(model_dir or "")
    if not raw:
        try:
            from smartscan.dashboard.identity import active_model_bundle_dir

            raw = str(active_model_bundle_dir())
        except (OSError, RuntimeError, TypeError, ValueError):
            raw = "artifacts/models/scheduler_v4"
    return generation_from_bundle_path(raw)


def command_bar_model_label(last_strategy: str, alias: str, *, model_dir: str | None = None) -> str:
    """Loaded PPO bundle + gate alias. Never the live strategy kind."""

    del last_strategy
    gen = scheduler_generation_tag(model_dir)
    alias_bit = str(alias or "candidate").strip() or "candidate"
    return f"{gen} {alias_bit}"


def command_bar_gate_label(passed: bool) -> str:
    """Official frozen v2 held-out gate — not the outcome of the live run."""

    return "Not Passed" if not passed else "Passed"


def command_bar_run_lede(
    run_status: str, last_strategy: str, *, model_dir: str | None = None
) -> str:
    status = str(run_status or "Idle")
    gen = scheduler_generation_tag(model_dir)
    token = str(last_strategy or "").strip()
    if token in {"", "—"}:
        return (
            f"{status}. Active PPO is {gen} candidate. "
            "Official frozen gate is v2_frozen_gate, not this session."
        )
    try:
        sid = canonicalize_strategy_id(token)
        kind = strategy_kind_label(sid)
    except SmartScanError:
        sid, kind = token, "Not available"
    if sid == "ppo":
        return (
            f"{status}. Live policy is ppo using active PPO {gen} candidate. "
            "Official gate remains v2_frozen_gate, not this episode."
        )
    return (
        f"{status}. Live policy is {sid} ({kind}). "
        f"Active PPO is {gen} candidate (unused this run). "
        "Official gate is v2_frozen_gate, unused this run."
    )


def render_command_bar(st: Any, state: dict[str, Any], gate: dict[str, Any]) -> None:
    del gate
    from smartscan.dashboard.identity import dashboard_identity

    identity = dashboard_identity()
    active = identity["active_model_bundle"]
    frozen = identity["gate_evidence_bundle"]
    model_dir = str(active.get("path") or "")
    st.markdown(
        command_bar_html(
            scenario=str(state.get("last_scenario") or "—"),
            strategy=str(state.get("last_strategy") or "—"),
            seed=str(state.get("last_seed") if state.get("last_seed") is not None else "—"),
            run_status=str(state.get("run_status") or "Idle"),
            active_version=str(active.get("generation") or "v4"),
            active_alias=str(active.get("alias") or "candidate"),
            research_status=str(active.get("research_status") or "Candidate"),
            gate_protocol=str(frozen.get("protocol_id") or "v2_frozen_gate"),
            gate_status=str(frozen.get("gate_status") or "Not Passed"),
            lede=command_bar_run_lede(
                str(state.get("run_status") or "Idle"),
                str(state.get("last_strategy") or "—"),
                model_dir=model_dir,
            ),
        ),
        unsafe_allow_html=True,
    )


def render_tour(st: Any) -> None:
    with st.expander("How to Use SmartScan", expanded=False):
        st.caption("About one minute. Optional for first-time operators.")
        for i, step in enumerate(TOUR_STEPS, start=1):
            st.markdown(f"**{i}.** {step}")


__all__ = [
    "TOUR_STEPS",
    "command_bar_gate_label",
    "command_bar_model_label",
    "command_bar_run_lede",
    "inject_pointer_runtime",
    "pointer_runtime_html",
    "render_command_bar",
    "render_gate_status_html",
    "render_tour",
]
