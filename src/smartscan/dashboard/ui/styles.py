"""Offline dashboard CSS. No remote fonts or CDNs."""

from __future__ import annotations

from smartscan.dashboard.layout import PALETTE, SIDEBAR_WIDTH_PX

REMOTE_MARKERS: tuple[str, ...] = (
    "fonts.googleapis",
    "fonts.gstatic",
    "cdn.jsdelivr",
    "unpkg.com",
    "cdnjs.cloudflare",
    "ajax.googleapis",
    "code.jquery.com",
    "threejs.org",
    "unpkg",
    "jsdelivr",
)


def contains_remote_asset(blob: str) -> bool:
    """True if *blob* references a known remote CDN or font host."""

    lowered = blob.lower()
    return any(marker in lowered for marker in REMOTE_MARKERS)


def global_css() -> str:
    return f"""
<style>
html, body, .stApp {{
  background: {PALETTE["bg"]};
  color: {PALETTE["text"]};
  overflow-x: hidden;
  width: 100%;
  max-width: 100%;
  font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
}}
html {{ font-size: clamp(13px, 0.45vw + 11.4px, 16px); }}
.stApp {{
  max-width: 100% !important;
  width: 100% !important;
}}
[data-testid="stToolbar"], .stDeployButton, div[data-testid="stDecoration"],
footer, [data-testid="stFooter"] {{
  display: none;
}}
header[data-testid="stHeader"], [data-testid="stHeader"], .stAppHeader {{
  display: none !important;
  height: 0 !important;
  min-height: 0 !important;
  background: transparent !important;
}}
[data-testid="stIFrame"] {{
  position: absolute !important;
  width: 1px !important;
  height: 1px !important;
  opacity: 0;
  pointer-events: none;
  overflow: hidden;
}}
section[data-testid="stSidebar"] {{
  min-width: 220px;
  max-width: {SIDEBAR_WIDTH_PX}px;
  visibility: hidden !important;
  pointer-events: none !important;
  transform: translateX(-120%) !important;
  position: fixed !important;
}}
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapseButton"],
[data-testid="stExpandSidebarButton"],
[data-testid="stSidebarCollapsedControl"] {{
  display: none !important;
}}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {{
  overflow-wrap: anywhere;
  word-break: break-word;
}}
[data-testid="stMain"] {{ overflow-x: hidden; width: 100%; }}
[data-testid="stMainBlockContainer"] {{
  max-width: min(100%, 90rem) !important;
  width: 100% !important;
  padding: 0.7rem clamp(0.7rem, 2vw, 1.6rem) 1.2rem max(3.6rem, calc(54px + 0.8rem));
}}
body.ss-on-landing [data-testid="stMainBlockContainer"] {{
  max-width: min(100%, 96rem) !important;
  padding: 0.35rem clamp(0.85rem, 2.8vw, 2.4rem) 2rem max(3.6rem, calc(54px + 0.85rem));
  background: transparent;
}}
body.ss-on-landing [data-testid="stElementContainer"]:has(.ss-landing-root),
body.ss-on-landing [data-testid="stVerticalBlockBorderWrapper"]:has(.ss-landing-root),
body.ss-on-landing [data-testid="stMarkdownContainer"]:has(.ss-landing-root),
body.ss-on-landing [data-testid="stVerticalBlock"] {{
  width: 100% !important;
}}
[data-testid="stMetric"] {{ min-width: 0; }}
[data-testid="stDataFrame"] {{ max-width: 100%; }}
.stPlotlyChart, [data-testid="stPlotlyChart"] {{ max-width: 100%; overflow: hidden; }}
img, svg, video, canvas {{ max-width: 100%; }}
.ss-section, .ss-cmd, .ss-pipe, .ss-split {{ min-width: 0; }}
#ss-burger {{
  position: fixed !important;
  top: 12px;
  left: 12px;
  z-index: 2147483000;
  width: 42px;
  height: 42px;
  margin: 0;
  padding: 0;
  border: 1px solid {PALETTE["line"]};
  border-radius: 4px;
  background: rgba(5, 8, 11, 0.92);
  box-shadow: 0 0 0 1px rgba(58, 168, 181, 0.12);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 5px;
  visibility: visible !important;
  opacity: 1 !important;
  pointer-events: auto !important;
}}
#ss-burger span {{
  display: block;
  width: 16px;
  height: 1px;
  background: {PALETTE["text"]};
  transition: transform 0.16s ease, opacity 0.16s ease;
}}
#ss-burger.is-open span:nth-child(1) {{ transform: translateY(6px) rotate(45deg); }}
#ss-burger.is-open span:nth-child(2) {{ opacity: 0; }}
#ss-burger.is-open span:nth-child(3) {{ transform: translateY(-6px) rotate(-45deg); }}
#ss-nav-backdrop {{
  position: fixed;
  inset: 0;
  background: rgba(2, 4, 6, 0.45);
  z-index: 2147482998;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s ease;
}}
body.ss-nav-open #ss-nav-backdrop {{
  opacity: 1;
  pointer-events: auto;
}}
#ss-drawer {{
  position: fixed;
  top: 0;
  left: 0;
  height: 100vh;
  width: 276px;
  max-width: 80vw;
  z-index: 2147482999;
  background: rgba(7, 16, 21, 0.94);
  border-right: 1px solid {PALETTE["accent"]};
  box-shadow: 8px 0 40px rgba(0, 0, 0, 0.45);
  transform: translateX(-105%);
  visibility: hidden;
  transition: transform 0.22s ease;
  overflow-y: auto;
  padding: 4.2rem 1rem 1.4rem 1rem;
}}
body.ss-nav-open #ss-drawer {{ transform: translateX(0); visibility: visible; }}
@supports ((-webkit-backdrop-filter: blur(14px)) or (backdrop-filter: blur(14px))) {{
  #ss-drawer {{
    background: rgba(7, 16, 21, 0.78);
    -webkit-backdrop-filter: blur(14px);
    backdrop-filter: blur(14px);
  }}
}}
.ss-drawer-brand strong {{
  display: block;
  letter-spacing: 0.18em;
  font-size: 0.82rem;
}}
.ss-drawer-brand em {{
  display: block;
  font-style: normal;
  color: {PALETTE["muted"]};
  font-size: 0.72rem;
  margin: 0.2rem 0 0.8rem 0;
}}
.ss-drawer-kicker {{
  margin: 0.85rem 0 0.35rem 0;
  font-size: 0.62rem;
  letter-spacing: 0.16em;
  color: {PALETTE["accent"]};
}}
.ss-nav-item {{
  display: block;
  width: 100%;
  text-align: left;
  background: transparent;
  color: {PALETTE["text"]};
  border: 0;
  border-left: 2px solid transparent;
  padding: 0.38rem 0.45rem;
  margin: 0 0 0.12rem 0;
  cursor: pointer;
  font-size: 0.82rem;
}}
.ss-nav-item.is-active {{
  border-left-color: {PALETTE["accent"]};
  background: rgba(58, 168, 181, 0.08);
}}
.ss-nav-item:hover {{ background: rgba(58, 168, 181, 0.12); }}
.ss-nav-quiet {{ color: {PALETTE["muted"]}; font-size: 0.78rem; }}
.ss-drawer-meta {{
  display: flex;
  justify-content: space-between;
  gap: 0.4rem;
  font-size: 0.72rem;
  color: {PALETTE["muted"]};
  padding: 0.18rem 0.45rem;
}}
.ss-drawer-meta strong {{ color: {PALETTE["text"]}; font-weight: 600; }}
.stApp {{
  position: relative !important;
  z-index: 2 !important;
  isolation: isolate;
  background: {PALETTE["bg"]};
}}
body.ss-on-landing .stApp,
body.ss-on-landing [data-testid="stAppViewContainer"],
body.ss-on-landing [data-testid="stMain"],
body.ss-on-landing [data-testid="stMainBlockContainer"],
body.ss-on-landing [data-testid="stVerticalBlock"],
body.ss-on-landing [data-testid="stVerticalBlockBorderWrapper"],
body.ss-on-landing [data-testid="stElementContainer"],
body.ss-on-landing [data-testid="stMarkdownContainer"],
body.ss-on-landing [data-testid="stBottomBlockContainer"] {{
  background: transparent !important;
  background-color: transparent !important;
}}
[data-testid="stAppViewContainer"], [data-testid="stMain"] {{
  position: relative;
  z-index: 2;
}}
body.ss-on-landing [data-testid="stMainBlockContainer"] [data-testid="stVerticalBlock"] {{
  gap: 0.32rem !important;
}}
body.ss-on-landing [data-testid="stButton"] {{
  position: absolute !important;
  left: -10000px !important;
  width: 1px !important;
  height: 1px !important;
  overflow: hidden !important;
  opacity: 0 !important;
}}
.ss-cta {{
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  width: auto;
  max-width: 100%;
  gap: 0.55rem;
  margin: 0.85rem 0 0.2rem 0;
  padding: 0.72rem 1.25rem;
  min-height: 44px;
  border: 1px solid {PALETTE["accent"]};
  border-radius: 2px;
  background: rgba(8, 18, 22, 0.92);
  color: {PALETTE["text"]};
  letter-spacing: 0.16em;
  font-size: clamp(0.68rem, 0.5vw + 0.58rem, 0.78rem);
  font-weight: 650;
  cursor: pointer;
  white-space: nowrap;
  transition: transform 0.12s ease, box-shadow 0.12s ease;
}}
.ss-cta:hover {{
  transform: translateX(6px);
  box-shadow: 0 0 0 1px rgba(58, 168, 181, 0.45), 0 0 22px rgba(58, 168, 181, 0.16);
}}
#ss-hero-canvas {{
  position: absolute !important;
  inset: 0 !important;
  width: 100% !important;
  height: 100% !important;
  z-index: 2 !important;
  pointer-events: none !important;
  background: transparent !important;
}}
body.ss-on-control #ss-hero-canvas,
body.ss-on-control .ss-core-host {{ display: none !important; }}
.ss-landing-root {{
  position: relative;
  z-index: 2;
  width: 100% !important;
  max-width: 100%;
  min-width: 0;
  container-type: inline-size;
  container-name: ss-landing;
}}
.ss-hero-band {{
  display: grid;
  grid-template-columns: minmax(min(100%, 17rem), 0.92fr) minmax(0, 1.18fr);
  align-items: center;
  gap: clamp(0.35rem, 1.4vw, 1.5rem) clamp(0.4rem, 1.8vw, 1.8rem);
  width: 100%;
  min-height: clamp(200px, 48vh, 560px);
  min-width: 0;
}}
.ss-hero-stage {{
  position: relative;
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  padding: clamp(1.5rem, 5.5vh, 3.4rem) 0 0.15rem 0;
  max-width: min(36rem, 100%);
  z-index: 3;
}}
#ss-field-canvas {{
  position: fixed !important;
  inset: 0 !important;
  z-index: 0 !important;
  pointer-events: none !important;
  background: transparent !important;
}}
body.ss-on-control #ss-field-canvas {{ display: none !important; }}
.ss-core-host {{
  position: relative;
  min-height: clamp(180px, 46vh, 560px);
  min-width: 0;
  width: 100%;
  pointer-events: auto;
  overflow: visible;
  cursor: crosshair;
}}
.ss-core-fallback {{
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0.92;
}}
.ss-core-host.has-canvas .ss-core-fallback {{
  opacity: 0;
}}
.ss-hero-kicker {{
  letter-spacing: 0.22em;
  font-size: 0.64rem;
  color: {PALETTE["accent"]};
  margin: 0 0 0.4rem 0;
}}
.ss-hero-xl {{
  font-size: clamp(1.55rem, 2.2vw + 1.3vh, 3.5rem);
  line-height: 0.9;
  letter-spacing: 0.02em;
  font-weight: 650;
  margin: 0;
}}
.ss-hero-xl span {{ display: block; }}
.ss-hero-sub {{
  margin: 0.45rem 0 0 0;
  letter-spacing: 0.14em;
  font-size: 0.72rem;
  color: {PALETTE["muted"]};
}}
.ss-hero-line {{
  margin: 0.55rem 0 0.1rem 0;
  font-size: clamp(0.92rem, 0.7vw + 0.7rem, 1.08rem);
  max-width: min(36rem, 100%);
}}
.ss-hero-line-2 {{
  margin: 0.15rem 0 0.45rem 0;
  color: {PALETTE["muted"]};
  max-width: min(36rem, 100%);
}}
.ss-hero-meta {{
  color: {PALETTE["muted"]};
  font-size: 0.68rem;
  letter-spacing: 0.08em;
  margin: 0 0 0.15rem 0;
}}
.ss-annots {{
  position: absolute;
  inset: 12% 8% auto auto;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  pointer-events: none;
  opacity: 0.28;
  font-size: 0.62rem;
  letter-spacing: 0.16em;
  color: {PALETTE["muted"]};
}}
@media (max-width: 980px) {{
  .ss-hero-band {{
    grid-template-columns: 1fr;
    min-height: 0;
  }}
  .ss-hero-stage {{ max-width: 100%; padding-top: clamp(2.1rem, 8vw, 2.8rem); }}
  .ss-core-host {{ min-height: clamp(180px, 38vh, 320px); }}
  .ss-cta {{ white-space: normal; letter-spacing: 0.12em; }}
}}
@media (max-width: 640px) {{
  .ss-hero-kicker {{ font-size: 0.58rem; max-width: 16rem; }}
  .ss-hero-sub {{ letter-spacing: 0.08em; }}
  .ss-hero-sub-long, .ss-hero-meta {{ display: none; }}
  .ss-core-host {{ min-height: min(32vh, 220px); }}
  .ss-section {{ margin: 1rem 0; padding: 0.85rem 0.7rem; }}
  .ss-preview {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .ss-cta {{ padding: 0.65rem 0.9rem; letter-spacing: 0.1em; }}
}}
@media (max-height: 800px) and (min-width: 981px) {{
  .ss-hero-band {{ min-height: min(50vh, 390px); align-items: start; }}
  .ss-hero-stage {{ padding-top: 2.2rem; }}
  .ss-core-host {{ min-height: min(46vh, 370px); }}
  .ss-annots {{ display: none; }}
  .ss-hero-xl {{ font-size: clamp(1.65rem, 2vw + 1vh, 2.7rem); }}
  .ss-hero-sub-long {{ display: none; }}
  .ss-hero-meta {{ display: none; }}
  .ss-hero-line {{ font-size: 0.95rem; margin-top: 0.4rem; }}
}}
@media (min-aspect-ratio: 2/1) {{
  .ss-hero-band {{
    grid-template-columns: minmax(20rem, 0.72fr) minmax(0, 1.28fr);
    max-width: 92rem;
    margin-inline: auto;
  }}
}}
@media (max-aspect-ratio: 3/4) {{
  .ss-hero-band {{ grid-template-columns: 1fr; }}
  .ss-core-host {{ min-height: min(36vh, 280px); }}
}}
@container ss-landing (max-width: 720px) {{
  .ss-hero-band {{ grid-template-columns: 1fr; min-height: 0; }}
  .ss-core-host {{ min-height: 210px; }}
}}
.ss-reveal {{
  animation: ssFadeUp 0.55s ease both;
}}
.ss-d0 {{ animation-delay: 0.05s; }}
.ss-d1 {{ animation-delay: 0.45s; }}
.ss-d2 {{ animation-delay: 0.75s; }}
.ss-d3 {{ animation-delay: 1.05s; }}
.ss-d4 {{ animation-delay: 1.35s; }}
@keyframes ssFadeUp {{
  from {{ opacity: 0; transform: translateY(10px); }}
  to {{ opacity: 1; transform: none; }}
}}
.ss-section {{
  position: relative;
  z-index: 3;
  margin: 1.4rem 0;
  padding: 1rem 0.95rem;
  border-top: 1px solid {PALETTE["line"]};
  background: rgba(7, 16, 21, 0.90);
  opacity: 1;
  transform: none;
  transition: opacity 0.4s ease, transform 0.4s ease;
}}
.ss-section.is-in {{
  opacity: 1;
  transform: none;
}}
.ss-control-root {{
  animation: ssFadeUp 0.35s ease both;
}}
.ss-section h2 {{
  font-size: clamp(1.2rem, 2.4vw + 0.4rem, 2rem);
  letter-spacing: 0.04em;
  margin: 0 0 0.6rem 0;
  max-width: min(42rem, 100%);
}}
.ss-section p {{
  color: {PALETTE["muted"]};
  max-width: min(42rem, 100%);
  line-height: 1.45;
}}
.ss-split {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 16rem), 1fr));
  gap: 0.8rem;
}}
.ss-panel {{
  background: rgba(10, 22, 28, 0.65);
  border: 1px solid {PALETTE["line"]};
  border-radius: 4px;
  padding: 0.75rem 0.85rem;
}}
.ss-spectrum {{
  position: relative;
  height: 2.1rem;
  margin: 0.7rem 0;
  background: repeating-linear-gradient(90deg, {PALETTE["line"]} 0 8px, transparent 8px 14px);
  overflow: hidden;
  cursor: pointer;
}}
.ss-spectrum .occ {{
  position: absolute; top: 0; bottom: 0;
  background: rgba(86, 180, 233, 0.35);
}}
.ss-spectrum .win {{
  position: absolute; top: -3px; bottom: -3px; width: 8%;
  border: 1px solid {PALETTE["accent"]};
  background: rgba(58, 168, 181, 0.16);
  animation: ss-scan 9s ease-in-out infinite;
}}
.ss-spectrum.is-live .win {{
  animation: none;
}}
.ss-spectrum .win.is-held {{
  box-shadow: 0 0 12px rgba(58, 168, 181, 0.55);
  background: rgba(58, 168, 181, 0.32);
}}
@keyframes ss-scan {{
  0% {{ left: 6%; }} 25% {{ left: 38%; }} 55% {{ left: 70%; }} 80% {{ left: 22%; }} 100% {{ left: 78%; }}
}}
.ss-pipe {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  align-items: stretch;
}}
.ss-pipe > div {{
  flex: 1 1 8.2rem;
  border: 1px solid {PALETTE["line"]};
  padding: 0.5rem 0.55rem;
  background: rgba(10, 22, 28, 0.65);
}}
.ss-pipe b {{ display: block; font-size: 0.72rem; letter-spacing: 0.1em; }}
.ss-pipe p {{ margin: 0.25rem 0 0 0; font-size: 0.78rem; }}
.ss-ask-table {{
  display: flex;
  flex-direction: column;
  max-width: min(72rem, 100%);
  margin: 0.85rem 0 0.4rem 0;
}}
.ss-ask-row {{
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) 6.4rem minmax(0, 1.55fr);
  gap: 0.55rem 0.75rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid {PALETTE["line"]};
  font-size: 0.8rem;
  line-height: 1.4;
  color: {PALETTE["text"]};
}}
.ss-ask-row.is-head {{
  font-size: 0.66rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: {PALETTE["muted"]};
  padding-top: 0;
}}
.ss-ask-row .ss-tag {{
  color: {PALETTE["green"]};
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-size: 0.72rem;
  align-self: start;
}}
.ss-fom-row {{
  margin: 0.65rem 0 0.85rem 0;
}}
@media (max-width: 640px) {{
  .ss-ask-row {{ grid-template-columns: 1fr; }}
  .ss-ask-row.is-head {{ display: none; }}
}}
.ss-preview {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(7.2rem, 1fr));
  gap: 0.4rem;
  perspective: 900px;
}}
.ss-preview i {{
  display: block;
  min-height: 4.2rem;
  border: 1px solid {PALETTE["line"]};
  background: linear-gradient(160deg, rgba(10,22,28,0.9), rgba(5,8,11,0.9));
  transform: rotateX(8deg);
  padding: 0.45rem;
  font-style: normal;
  font-size: 0.72rem;
  letter-spacing: 0.08em;
}}
.ss-kicker {{
  letter-spacing: 0.18em;
  font-size: 0.68rem;
  color: {PALETTE["accent"]};
  text-transform: uppercase;
  margin: 0 0 0.35rem 0;
}}
.ss-hero-title {{
  font-size: 1.85rem;
  font-weight: 650;
  letter-spacing: 0.04em;
  line-height: 1.15;
  margin: 0 0 0.35rem 0;
  color: {PALETTE["text"]};
}}
.ss-lede {{
  color: {PALETTE["muted"]};
  max-width: 46rem;
  line-height: 1.45;
}}
.ss-chip-row, .ss-status-row, .ss-flow, .ss-steps {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}}
.ss-chip, .ss-status {{
  border: 1px solid {PALETTE["line"]};
  background: rgba(10, 22, 28, 0.65);
  border-radius: 4px;
  padding: 0.35rem 0.55rem;
  min-width: 7.2rem;
}}
.ss-chip span, .ss-status span {{
  display: block;
  font-size: 0.62rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: {PALETTE["muted"]};
}}
.ss-chip strong, .ss-status strong {{
  font-size: 0.86rem;
  font-weight: 600;
}}
.ss-status.is-warn, .ss-chip.is-warn {{ border-color: {PALETTE["amber"]}; }}
.ss-status.is-ok, .ss-chip.is-ok {{ border-color: {PALETTE["green"]}; }}
.ss-pipeline {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  align-items: center;
  margin: 0.6rem 0 0.9rem 0;
}}
.ss-pipeline b {{
  border: 1px solid {PALETTE["accent"]};
  color: {PALETTE["text"]};
  padding: 0.28rem 0.5rem;
  border-radius: 3px;
  font-size: 0.72rem;
  letter-spacing: 0.08em;
}}
.ss-pipeline i {{ color: {PALETTE["muted"]}; font-style: normal; }}
.ss-card {{
  border: 1px solid {PALETTE["line"]};
  background: rgba(10, 22, 28, 0.65);
  border-radius: 6px;
  padding: 0.7rem 0.8rem;
  margin: 0.35rem 0;
}}
.ss-bar {{
  height: 6px;
  background: {PALETTE["line"]};
  border-radius: 99px;
  overflow: hidden;
}}
.ss-bar > i {{
  display: block;
  height: 100%;
  background: {PALETTE["accent"]};
}}
.ss-cmd {{
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
  margin: 0 0 0.7rem 0;
  width: 100%;
}}
.ss-cmd-brand .brand {{
  font-size: 0.78rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: {PALETTE["accent"]};
}}
.ss-cmd-brand .sub {{ color: {PALETTE["muted"]}; font-size: 0.72rem; }}
.ss-cmd-kicker {{
  margin: 0 0 0.22rem 0;
  font-size: 0.62rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: {PALETTE["muted"]};
}}
.ss-cmd-group .ss-chip-row {{ margin: 0; }}
@media (max-width: 1200px) {{
  .ss-cmd {{ gap: 0.45rem; }}
}}
.ss-cursor {{
  position: fixed;
  width: 14px;
  height: 14px;
  margin: -7px 0 0 -7px;
  border: 1px solid {PALETTE["accent"]};
  border-radius: 50%;
  pointer-events: none;
  z-index: 2147483001;
  opacity: 0.5;
  transition: width 0.12s ease, height 0.12s ease, margin 0.12s ease, opacity 0.12s ease, box-shadow 0.18s ease;
}}
.ss-cursor::before {{
  content: "";
  position: absolute;
  inset: -34px;
  border-radius: 50%;
  pointer-events: none;
  opacity: 0;
  background: radial-gradient(
    circle,
    rgba(255, 255, 255, 0.28) 0%,
    rgba(255, 255, 255, 0.10) 28%,
    rgba(255, 255, 255, 0.03) 52%,
    rgba(255, 255, 255, 0) 72%
  );
  filter: blur(1.2px);
  transition: opacity 0.18s ease;
}}
.ss-cursor::after {{
  content: "";
  position: absolute;
  inset: 4px;
  border-radius: 50%;
  background: {PALETTE["accent"]};
  opacity: 0.7;
}}
.ss-cursor.is-ambient::before {{ opacity: 1; }}
.ss-cursor.is-ambient {{
  box-shadow: 0 0 16px 5px rgba(255, 255, 255, 0.10), 0 0 42px 16px rgba(255, 255, 255, 0.04);
}}
.ss-cursor.is-ambient.is-core::before {{
  inset: -20px;
  opacity: 0.55;
}}
.ss-cursor.is-section::before,
.ss-cursor.is-section {{
  opacity: 0.5;
  box-shadow: none;
}}
.ss-cursor.is-section::before {{ opacity: 0 !important; }}
.ss-cursor.is-hot {{
  width: 26px;
  height: 26px;
  margin: -13px 0 0 -13px;
  opacity: 0.85;
}}
.ss-cursor.is-cta {{
  width: 32px;
  height: 32px;
  margin: -16px 0 0 -16px;
  box-shadow: 0 0 0 6px rgba(58, 168, 181, 0.12);
}}
.ss-cursor.is-core {{
  width: 28px;
  height: 28px;
  margin: -14px 0 0 -14px;
  opacity: 0.72;
}}
.ss-tip {{
  position: fixed;
  max-width: 240px;
  padding: 0.45rem 0.55rem;
  background: {PALETTE["panel_alt"]};
  border: 1px solid {PALETTE["line"]};
  color: {PALETTE["text"]};
  font-size: 0.75rem;
  line-height: 1.35;
  border-radius: 4px;
  pointer-events: none;
  z-index: 2147483002;
  opacity: 0;
  transform: translateY(4px);
  transition: opacity 0.18s ease;
}}
.ss-tip.is-on {{ opacity: 1; transform: none; }}
.ss-lineage {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  align-items: center;
}}
.ss-lineage span {{
  border: 1px solid {PALETTE["line"]};
  padding: 0.25rem 0.45rem;
  border-radius: 3px;
  font-size: 0.72rem;
}}
.ss-problem {{
  position: relative;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 0.78rem;
  line-height: 1.7;
  color: {PALETTE["muted"]};
}}
.ss-track {{
  position: relative;
  height: 1.15rem;
  background: repeating-linear-gradient(
    90deg,
    {PALETTE["line"]} 0 10px,
    {PALETTE["panel_alt"]} 10px 14px
  );
  border-radius: 2px;
  overflow: hidden;
  margin: 0.2rem 0 0.55rem 0;
}}
.ss-track .ss-occ {{
  position: absolute;
  top: 0;
  bottom: 0;
  background: {PALETTE["sky"]};
  opacity: 0.55;
}}
.ss-track .ss-window {{
  position: absolute;
  top: -2px;
  bottom: -2px;
  width: 7%;
  border: 1px solid {PALETTE["accent"]};
  background: rgba(58, 168, 181, 0.18);
  animation: ss-scan 8s ease-in-out infinite;
}}
.ss-step {{
  flex: 1 1 8.5rem;
  border: 1px solid {PALETTE["line"]};
  border-radius: 4px;
  padding: 0.45rem 0.5rem;
  background: rgba(10, 22, 28, 0.65);
}}
.ss-step b {{ display: block; font-size: 0.72rem; letter-spacing: 0.08em; }}
.ss-step p {{ margin: 0.2rem 0 0 0; color: {PALETTE["muted"]}; font-size: 0.78rem; }}
@media (prefers-reduced-motion: reduce) {{
  .ss-cursor, .ss-tip, .ss-track .ss-window, .ss-spectrum .win, .ss-reveal, #ss-drawer, #ss-nav-backdrop, .ss-section, .ss-control-root {{
    transition: none; animation: none;
  }}
  .ss-reveal, .ss-section {{ opacity: 1; transform: none; }}
}}
</style>
"""


def landing_hide_sidebar_css() -> str:
    """Landing no longer hides navigation. Streamlit sidebar stays off-screen; hamburger remains."""

    return """
<style>
body.ss-on-landing [data-testid="stHeader"] { background: transparent !important; }
</style>
"""
