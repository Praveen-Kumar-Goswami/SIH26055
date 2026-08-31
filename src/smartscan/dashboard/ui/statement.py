"""Official SIH26055 statement mapping. Presentation only — no metric formulas."""

from __future__ import annotations

from typing import Any

# Catalogue snapshot of the DRDO software problem (SIH 2026). The live portal
# (sih.gov.in) is gateway-protected; this text matches the published PS dump.
PS_ID = "SIH26055"
PS_TITLE = "Smart Scan strategy for Electronic Warfare"
PS_ORG = "DRDO · Department of Defence Production / iDEX"
PS_CATEGORY = "Software"
PS_DEADLINE = "20 September 2026"
PS_EXPECTED = "Machine learning based Electronic Support receiver scheduler software"
PS_DATASETS = (
    "Turing Synthetic Radar Dataset (Hugging Face, gated ~70 GB)",
    "J.C. Wise Radar emitter Database (optional licensed local catalog)",
)

# Short official asks, paraphrased from the published description without adding
# classified EW capabilities the statement does not request.
STATEMENT_ASKS: tuple[dict[str, str], ...] = (
    {
        "id": "narrow-ibw",
        "ask": "High-sensitivity receiver whose instantaneous bandwidth is at least an order of magnitude below the surveillance span; sweep many bands.",
        "status": "Built",
        "where": "BandPlan + ReceiverEngine. scan_span / IBW ≥ 10.",
    },
    {
        "id": "open-loop-gap",
        "ask": "Open-loop / pre-mission sweeps waste dwell on non-threatening activity and starve new or threatening emitters.",
        "status": "Built",
        "where": "Seven public strategies in Configure and Run, including sequential, random, and fixed-priority vs CTS, periodic-intercept, and PPO.",
    },
    {
        "id": "two-d-search",
        "ask": "Interception is a two-dimensional search: set the receiver frequency at the correct time.",
        "status": "Built",
        "where": "ScanCommand is band + dwell. Replay shows the moving observation window.",
    },
    {
        "id": "seven-foms",
        "ask": "Report Pd, Pfa, Sensitivity, average intercept rate, average reward/cost, percentage of correct predictions, average intercept-time error.",
        "status": "Built",
        "where": "Metrics engine + Metrics Compare. Unavailable values stay Not available.",
    },
    {
        "id": "sim-truth",
        "ask": "Receiver model driven by a simulated RF environment with truth per band and time slot (transmission vs non-transmission).",
        "status": "Built",
        "where": "GroundTruth.occupied / signal_power_w. Policy never reads occupancy.",
    },
    {
        "id": "predict",
        "ask": "Predict intercept time and interception ratio against spatially scanning and frequency-agile emitters.",
        "status": "Built",
        "where": "Hit-hazard + horizon forecast on DecisionLog. CircularScan and FrequencyAgile emitters.",
    },
    {
        "id": "ml-scheduler",
        "ask": "Primary objective: a robust machine-learning scheduler that minimises intercept time and keeps interception rate high, trained on hits and misses.",
        "status": "Built",
        "where": "CTS + PPO v4 candidate. Frozen v2 held-out gate is failed — no Champion claim.",
    },
    {
        "id": "periodic-scan",
        "ask": "Outline and develop algorithms to intercept a periodic-scan emitter optimally.",
        "status": "Built",
        "where": "PeriodicityEstimator + periodic-intercept search-then-stare policy (observable hits only).",
    },
    {
        "id": "es-software",
        "ask": "Deliver Electronic Support receiver scheduler software.",
        "status": "Built",
        "where": "Offline Streamlit Control Center: configure, replay, decide, compare, lineage.",
    },
    {
        "id": "datasets",
        "ask": "Use the referenced radar datasets (Turing synthetic radar; J.C. Wise catalog).",
        "status": "Built",
        "where": "TSRD adapter (optional download) and Wise-compatible importer. No scraped catalog.",
    },
)

FOMS: tuple[tuple[str, str], ...] = (
    ("Pd", "Probability of detection"),
    ("Pfa", "Probability of false alarm"),
    ("Sensitivity", "SNR at target Pd"),
    ("AIR", "Average intercept rate"),
    ("Reward/cost", "Average reward / cost"),
    ("Correct pred.", "Percentage of correct predictions"),
    ("Time error", "Average intercept-time error"),
)


def _esc(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def statement_asks() -> list[dict[str, str]]:
    return [dict(row) for row in STATEMENT_ASKS]


def statement_matrix_html() -> str:
    rows = [
        '<div class="ss-ask-table" id="ss-statement-matrix">',
        '<div class="ss-ask-row is-head"><span>Official ask</span><span>Status</span>'
        "<span>In this prototype</span></div>",
    ]
    for item in STATEMENT_ASKS:
        rows.append(
            '<div class="ss-ask-row">'
            f'<span>{_esc(item["ask"])}</span>'
            f'<span class="ss-tag">{_esc(item["status"])}</span>'
            f'<span>{_esc(item["where"])}</span>'
            "</div>"
        )
    rows.append("</div>")
    return "".join(rows)


def fom_chips_html() -> str:
    chips = []
    for short, long_name in FOMS:
        chips.append(
            '<div class="ss-chip">'
            f"<span>{_esc(long_name)}</span><strong>{_esc(short)}</strong></div>"
        )
    return '<div class="ss-chip-row ss-fom-row">' + "".join(chips) + "</div>"


def statement_sections_html() -> str:
    """Landing sections 04–05: official PS contract and periodic-intercept outline."""

    body = f"""
<section class="ss-section" id="ss-statement">
  <p class="ss-kicker">04  Official statement · {PS_ID}</p>
  <h2>WHAT DRDO ASKED FOR.</h2>
  <p>{_esc(PS_TITLE)}. {_esc(PS_ORG)}. Category {_esc(PS_CATEGORY)}.
  Idea deadline {_esc(PS_DEADLINE)}.</p>
  <p>Expected solution: {_esc(PS_EXPECTED)}.</p>
  {fom_chips_html()}
  <p>Seven figures of merit named in the problem statement. Supporting outputs
  (interception ratio, delay, wasted dwell) are reported beside them.</p>
  {statement_matrix_html()}
  <p>Referenced data: {_esc(PS_DATASETS[0])}; {_esc(PS_DATASETS[1])}.
  Tests never require a Hugging Face token or a scraped Wise dump.</p>
</section>
<section class="ss-section" id="ss-periodic">
  <p class="ss-kicker">05  Periodic-scan intercept</p>
  <h2>FREQUENCY AT THE CORRECT TIME.</h2>
  <p>A circular-scan radar illuminates the receiver only in a repeating time window.
  The problem statement asks for an outlined method, then working algorithms,
  to intercept that pattern. SmartScan does this from hits and misses only.</p>
  <div class="ss-pipe">
    <div><b>SEARCH</b><p>Sweep unvisited bands first so the whole span is covered.</p></div>
    <div><b>ESTIMATE</b><p>From hit timestamps, recover period and phase to the next illumination.</p></div>
    <div><b>STARE</b><p>When the next illumination falls inside the next dwell, stay on that band.</p></div>
    <div><b>RESUME</b><p>Otherwise visit the least-recently-scanned band. No occupancy oracle.</p></div>
  </div>
  <p>Run strategy <b>periodic-intercept</b> in Configure &amp; Run. PPO still uses the
  same period/phase features. Neither path is a Champion scheduler.</p>
</section>
"""
    return body


def statement_table_rows() -> list[dict[str, Any]]:
    return [
        {"ask": row["ask"], "status": row["status"], "implementation": row["where"]}
        for row in STATEMENT_ASKS
    ]
