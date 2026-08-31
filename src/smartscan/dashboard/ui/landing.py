"""Immersive landing experience. Offline canvas only — no CDN."""

from __future__ import annotations

from importlib.resources import files
from typing import Any

from smartscan.dashboard.ui.components import lineage_flow_html, render_gate_status_html
from smartscan.dashboard.ui.statement import statement_sections_html
from smartscan.dashboard.ui.styles import contains_remote_asset, landing_hide_sidebar_css

HERO_COPY = "A receiver cannot listen everywhere at once."
HERO_COPY_2 = "SmartScan studies where to listen next."

CORE_FALLBACK_SVG = """
<svg class="ss-core-fallback" viewBox="0 0 720 520" width="100%" height="100%" aria-hidden="true" focusable="false">
  <ellipse cx="360" cy="252" rx="268" ry="92" fill="none" stroke="#8aa0ac" stroke-width="1.15" opacity="0.42" transform="rotate(-16 360 252)"/>
  <ellipse cx="360" cy="252" rx="236" ry="84" fill="none" stroke="#7b929e" stroke-width="1.05" opacity="0.38" transform="rotate(11 360 252)"/>
  <ellipse cx="360" cy="252" rx="204" ry="78" fill="none" stroke="#6f8794" stroke-width="1" opacity="0.40" transform="rotate(-28 360 252)"/>
  <ellipse cx="360" cy="252" rx="176" ry="70" fill="none" stroke="#7d96a2" stroke-width="1" opacity="0.36" transform="rotate(22 360 252)"/>
  <ellipse cx="360" cy="252" rx="148" ry="62" fill="none" stroke="#6a818c" stroke-width="0.95" opacity="0.34" transform="rotate(-8 360 252)"/>
  <ellipse cx="360" cy="252" rx="118" ry="52" fill="none" stroke="#5d737e" stroke-width="0.9" opacity="0.32" transform="rotate(32 360 252)"/>
  <ellipse cx="360" cy="252" rx="78" ry="78" fill="none" stroke="#4e6570" stroke-width="0.8" opacity="0.35"/>
  <ellipse cx="360" cy="252" rx="58" ry="58" fill="none" stroke="#3a4f58" stroke-width="0.8" opacity="0.40"/>
  <path d="M 112 252 A 248 90 0 0 1 220 180" fill="none" stroke="#3aa8b5" stroke-width="2.4" opacity="0.92" transform="rotate(-16 360 252)"/>
  <polygon points="360,228 382,240 382,264 360,276 338,264 338,240" fill="#1a2a30" stroke="#3aa8b5" stroke-width="0.9" opacity="0.92"/>
  <circle cx="198" cy="198" r="2.4" fill="#3aa8b5" opacity="0.85"/>
  <circle cx="486" cy="274" r="2.1" fill="#86b4e9" opacity="0.55"/>
  <circle cx="402" cy="168" r="2.2" fill="#c4922a" opacity="0.7"/>
  <circle cx="268" cy="312" r="1.8" fill="#3aa8b5" opacity="0.6"/>
  <text x="36" y="48" fill="#7c8b96" font-size="11" font-family="Segoe UI, sans-serif">2 GHz</text>
  <text x="36" y="148" fill="#7c8b96" font-size="11" font-family="Segoe UI, sans-serif">6 GHz</text>
  <text x="36" y="248" fill="#7c8b96" font-size="11" font-family="Segoe UI, sans-serif">10 GHz</text>
  <text x="36" y="348" fill="#7c8b96" font-size="11" font-family="Segoe UI, sans-serif">14 GHz</text>
  <text x="36" y="448" fill="#7c8b96" font-size="11" font-family="Segoe UI, sans-serif">18 GHz</text>
  <text x="248" y="498" fill="#8a9aa4" font-size="11" font-family="Segoe UI, sans-serif">SPECTRAL INTERCEPT CORE</text>
</svg>
"""


def hero_parent_javascript() -> str:
    """Spectral Intercept Core — offline canvas 3D, no CDN."""

    js = files("smartscan.dashboard.ui").joinpath("spectral_core.js").read_text(encoding="utf-8")
    if contains_remote_asset(js):
        raise RuntimeError("hero runtime must stay offline")
    return js


def hero_animation_html() -> str:
    html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>"
        "<canvas id='c' width='1100' height='200' aria-label='Spectrum field'></canvas>"
        "<script>" + hero_parent_javascript() + "</script></body></html>"
    )
    if contains_remote_asset(html):
        raise RuntimeError("hero animation must stay offline")
    return html


def landing_intro_html(gate: dict[str, Any]) -> str:
    del gate
    body = f"""
<div class="ss-landing-root">
<div class="ss-hero-band">
<div class="ss-hero-stage">
  <p class="ss-hero-kicker ss-reveal ss-d0">SIH26055 · DRDO electromagnetic spectrum research</p>
  <h1 class="ss-hero-xl ss-reveal ss-d1"><span>SMART</span><span>SCAN</span></h1>
  <p class="ss-hero-sub ss-reveal ss-d1">STRATEGY FOR ELECTRONIC WARFARE</p>
  <p class="ss-hero-sub ss-hero-sub-long ss-reveal ss-d2">INTELLIGENT FREQUENCY–TIME SPECTRUM SURVEILLANCE</p>
  <p class="ss-hero-line ss-reveal ss-d2">{HERO_COPY}</p>
  <p class="ss-hero-line-2 ss-reveal ss-d2">{HERO_COPY_2}</p>
  <p class="ss-hero-meta ss-reveal ss-d3">Observable RF intelligence · Adaptive scheduling · Reproducible evaluation</p>
  <div class="ss-cta ss-reveal ss-d4" id="ss-enter-cta" role="button" tabindex="0">ENTER CONTROL CENTER  →</div>
</div>
<div id="ss-core-host" class="ss-core-host" data-ss-core-host="1" aria-hidden="true">{CORE_FALLBACK_SVG}
</div>
</div>
</div>
"""
    if contains_remote_asset(body):
        raise RuntimeError("landing markup must stay offline")
    return body


def landing_explainer_html() -> str:
    body = """
<section class="ss-section" id="ss-problem">
  <p class="ss-kicker">01  The problem</p>
  <h2>THE SPECTRUM IS WIDE.<br>THE RECEIVER IS NOT.</h2>
  <p>Instantaneous receiver bandwidth is substantially smaller than the spectrum that must be monitored.</p>
  <div class="ss-spectrum" data-ss-help="dwell" title="How long the receiver remains tuned to the selected frequency band.">
    <div class="occ" style="left:6%;width:7%"></div>
    <div class="occ" style="left:24%;width:9%"></div>
    <div class="occ" style="left:61%;width:8%"></div>
    <div class="occ" style="left:84%;width:10%"></div>
    <div class="win" data-ss-help="dwell"></div>
  </div>
  <p>FULL SPECTRUM above. The cyan window is the current observation band. Emitters may appear elsewhere.</p>
</section>
<section class="ss-section" id="ss-fixed">
  <p class="ss-kicker">02  Motivation for adaptive scheduling</p>
  <div class="ss-split">
    <div class="ss-panel">
      <b>FIXED SCAN</b>
      <p>A predictable sweep revisits bands on a clock. Time is spent even where recent evidence shows no useful activity.</p>
    </div>
    <div class="ss-panel">
      <b>DYNAMIC RF ENVIRONMENT</b>
      <p>Emitters appear, hop and pause. Static scanning can miss intercept opportunities without claiming any learned policy has solved this.</p>
    </div>
  </div>
</section>
<section class="ss-section" id="ss-pipeline">
  <p class="ss-kicker">03  SmartScan pipeline</p>
  <div class="ss-pipe">
    <div><b>OBSERVE</b><p>Receiver measurements only.</p></div>
    <div><b>DETECT</b><p>Hits and misses become evidence.</p></div>
    <div><b>ESTIMATE</b><p>Predict observable signal opportunities.</p></div>
    <div><b>PRIORITIZE</b><p>Select frequency band + dwell.</p></div>
    <div><b>SCAN</b><p>Execute receiver action.</p></div>
    <div><b>EVALUATE</b><p>Measure interception, delay, Pd and Pfa.</p></div>
  </div>
</section>
"""
    combined = body + statement_sections_html()
    if contains_remote_asset(combined):
        raise RuntimeError("landing markup must stay offline")
    return combined


def landing_status_html(gate: dict[str, Any]) -> str:
    status = render_gate_status_html(gate)
    body = f"""
<section class="ss-section" id="ss-status">
  <p class="ss-kicker">06  Scientific status</p>
  {status}
  <p>Live PPO is SmartScanScheduler v4 (candidate). The frozen v2 held-out
  performance gate remains failed, so the system does not claim Champion status.</p>
</section>
<section class="ss-section" id="ss-preview">
  <p class="ss-kicker">07  Control center</p>
  <h2>READY TO INSPECT THE SYSTEM?</h2>
  <p>Seven public strategies in Configure &amp; Run: sequential, random,
  fixed-priority, reactive, contextual-thompson, periodic-intercept, and PPO.</p>
  <div class="ss-preview" aria-hidden="true">
    <i>Configure &amp; Run</i><i>Scan Replay</i><i>Smart Decision</i><i>Metrics Compare</i><i>Run History</i><i>Lineage</i>
  </div>
  <div class="ss-cta" id="ss-enter-cta-foot" role="button" tabindex="0">ENTER CONTROL CENTER  →</div>
</section>
"""
    if contains_remote_asset(body):
        raise RuntimeError("landing markup must stay offline")
    return body


def landing_body_html(gate: dict[str, Any]) -> str:
    return landing_intro_html(gate) + landing_explainer_html() + landing_status_html(gate)


def render_landing(st: Any, gate: dict[str, Any]) -> None:
    st.markdown(landing_hide_sidebar_css(), unsafe_allow_html=True)
    st.markdown(landing_intro_html(gate), unsafe_allow_html=True)
    if st.button("ENTER CONTROL CENTER", key="enter_control_center", type="primary"):
        st.session_state["entered_control_center"] = True
        st.rerun()
    st.markdown(landing_explainer_html(), unsafe_allow_html=True)
    st.markdown(landing_status_html(gate), unsafe_allow_html=True)
    if st.button("ENTER CONTROL CENTER", key="enter_control_center_footer"):
        st.session_state["entered_control_center"] = True
        st.rerun()
    with st.expander("View System Architecture", expanded=False):
        st.markdown(lineage_flow_html(), unsafe_allow_html=True)
        st.caption(
            "Learned policies never receive GroundTruth occupancy. Overlay views are evaluator-only."
        )
    st.caption(
        "This prototype does not claim that the live PPO v4 candidate beats conventional strategies."
    )
