"""Permanent hamburger + drawer. Does not use Streamlit's collapse control."""

from __future__ import annotations

import json

from smartscan.dashboard.layout import NAV_LABELS
from smartscan.dashboard.ui.styles import contains_remote_asset


def nav_shell_javascript() -> str:
    """Parent-document script: hamburger, drawer, radio proxy clicks."""

    items = [{"key": key, "label": label} for key, label in NAV_LABELS.items()]

    payload = json.dumps({"views": items}, separators=(",", ":"))
    js = f"""
(function() {{
  var SPEC = {payload};
  var doc;
  try {{ doc = window.parent.document; }} catch (e) {{ return; }}
  if (!doc || !doc.body) return;

  var old = doc.getElementById("ss-nav-root");
  if (old) old.remove();

  var root = doc.createElement("div");
  root.id = "ss-nav-root";
  root.setAttribute("aria-hidden", "false");

  var burger = doc.createElement("button");
  burger.id = "ss-burger";
  burger.type = "button";
  burger.setAttribute("aria-label", "Open navigation");
  burger.setAttribute("title", "Open navigation");
  burger.innerHTML = "<span></span><span></span><span></span>";

  var backdrop = doc.createElement("div");
  backdrop.id = "ss-nav-backdrop";

  var drawer = doc.createElement("nav");
  drawer.id = "ss-drawer";
  drawer.setAttribute("aria-label", "SmartScan navigation");
  drawer.innerHTML = [
    '<div class="ss-drawer-brand">',
    '  <strong>SMARTSCAN</strong>',
    '  <em>Spectrum Intelligence System</em>',
    '</div>',
    '<p class="ss-drawer-kicker">OVERVIEW</p>',
    '<button type="button" class="ss-nav-item" data-ss-act="overview">⌂  Mission Overview</button>',
    '<p class="ss-drawer-kicker">CONTROL CENTER</p>',
    SPEC.views.map(function(v) {{
      return '<button type="button" class="ss-nav-item" data-ss-act="view" data-ss-view="'+v.key+'">'+v.label+'</button>';
    }}).join(""),
    '<p class="ss-drawer-kicker">SYSTEM</p>',
    '<div class="ss-drawer-meta"><span>Active PPO</span><strong>v4 candidate</strong></div>',
    '<div class="ss-drawer-meta"><span>Official gate</span><strong>v2_frozen_gate not passed</strong></div>',
    '<div class="ss-drawer-meta"><span>Mode</span><strong>Offline</strong></div>',
    '<button type="button" class="ss-nav-item ss-nav-quiet" data-ss-act="tour">?  Quick Guide</button>',
    '<button type="button" class="ss-nav-item ss-nav-quiet" data-ss-act="overlay">Evaluation overlay</button>',
    '<button type="button" class="ss-nav-item ss-nav-quiet" data-ss-act="doctor">Doctor</button>'
  ].join("");

  root.appendChild(backdrop);
  root.appendChild(drawer);
  root.appendChild(burger);
  doc.body.appendChild(root);

  function onLanding() {{
    return !!doc.querySelector(".ss-landing-root");
  }}
  function markLanding() {{
    doc.body.classList.toggle("ss-on-landing", onLanding());
    doc.body.classList.toggle("ss-on-control", !onLanding());
  }}
  function isOpen() {{
    return doc.body.classList.contains("ss-nav-open");
  }}
  function setOpen(next) {{
    doc.body.classList.toggle("ss-nav-open", !!next);
    burger.setAttribute("aria-label", next ? "Close navigation" : "Open navigation");
    burger.classList.toggle("is-open", !!next);
    try {{ window.parent.sessionStorage.setItem("ss_nav_open", next ? "1" : "0"); }} catch (e) {{}}
    paintActive();
  }}
  function findButton(re) {{
    var nodes = doc.querySelectorAll("button");
    for (var i = 0; i < nodes.length; i++) {{
      var t = (nodes[i].innerText || "").replace(/\\s+/g, " ").trim();
      if (re.test(t)) return nodes[i];
    }}
    return null;
  }}
  function clickRadio(viewKey) {{
    var idx = -1;
    for (var s = 0; s < SPEC.views.length; s++) {{
      if (SPEC.views[s].key === viewKey) idx = s;
    }}
    var inputs = doc.querySelectorAll('[data-testid="stRadio"] input, [data-testid="stRadio"] [role="radio"]');
    if (idx >= 0 && inputs[idx]) {{
      inputs[idx].click();
      return true;
    }}
    var labels = doc.querySelectorAll('[data-testid="stRadio"] label, [data-testid="stRadio"] p, [data-testid="stRadio"] div');
    var want = (viewKey || "").toLowerCase();
    for (var i = 0; i < labels.length; i++) {{
      var t = (labels[i].innerText || "").toLowerCase();
      if (!t) continue;
      if (t.indexOf(want) >= 0) {{
        labels[i].click();
        return true;
      }}
    }}
    return false;
  }}
  function pending(view) {{
    try {{ window.parent.sessionStorage.setItem("ss_pending_view", view || ""); }} catch (e) {{}}
  }}
  function consumePending() {{
    var view = "";
    try {{ view = window.parent.sessionStorage.getItem("ss_pending_view") || ""; }} catch (e) {{}}
    if (!view) return;
    try {{ window.parent.sessionStorage.removeItem("ss_pending_view"); }} catch (e) {{}}
    window.parent.setTimeout(function() {{ clickRadio(view); }}, 700);
  }}
  function paintActive() {{
    var items = drawer.querySelectorAll("[data-ss-view]");
    var current = "";
    var labels = doc.querySelectorAll('[data-testid="stRadio"] label');
    for (var i = 0; i < labels.length; i++) {{
      var input = labels[i].querySelector("input");
      if (input && input.checked) current = (labels[i].innerText || "");
    }}
    for (var k = 0; k < items.length; k++) {{
      var key = items[k].getAttribute("data-ss-view") || "";
      var lab = items[k].innerText || "";
      items[k].classList.toggle("is-active", !onLanding() && (current.indexOf(key) >= 0 || current.indexOf(lab.replace(/^\\d+\\s+/, "")) >= 0 || lab.indexOf(current.trim()) >= 0));
    }}
  }}
  function goView(viewKey) {{
    if (onLanding()) {{
      pending(viewKey);
      var cta = findStreamlitEnter();
      if (cta) {{ cta.click(); setOpen(false); return; }}
    }}
    clickRadio(viewKey);
    setOpen(false);
  }}
  burger.addEventListener("click", function(ev) {{
    ev.preventDefault();
    ev.stopPropagation();
    setOpen(!isOpen());
  }});
  function findStreamlitEnter() {{
    var nodes = doc.querySelectorAll('[data-testid="stButton"] button, [data-testid="stBaseButton-primary"], [data-testid="stBaseButton-secondary"]');
    for (var i = 0; i < nodes.length; i++) {{
      if (/ENTER CONTROL CENTER/i.test(nodes[i].innerText || "")) return nodes[i];
    }}
    return null;
  }}
  function activateCta() {{
    var real = findStreamlitEnter();
    if (real) real.click();
  }}
  function placeCta() {{
    if (!onLanding()) return;
    var stage = doc.querySelector(".ss-hero-stage");
    if (stage && !doc.getElementById("ss-enter-cta")) {{
      var hero = doc.createElement("button");
      hero.type = "button";
      hero.id = "ss-enter-cta";
      hero.className = "ss-cta";
      hero.textContent = "ENTER CONTROL CENTER  →";
      hero.style.width = "max-content";
      hero.style.alignSelf = "flex-start";
      stage.appendChild(hero);
    }}
    var preview = doc.getElementById("ss-preview");
    if (preview && !doc.getElementById("ss-enter-cta-foot")) {{
      var foot = doc.createElement("button");
      foot.type = "button";
      foot.id = "ss-enter-cta-foot";
      foot.className = "ss-cta";
      foot.textContent = "ENTER CONTROL CENTER  →";
      preview.appendChild(foot);
    }}
  }}
  doc.addEventListener("click", function(ev) {{
    var cta = ev.target.closest ? ev.target.closest(".ss-cta") : null;
    if (!cta) return;
    ev.preventDefault();
    activateCta();
  }}, true);
  doc.addEventListener("keydown", function(ev) {{
    if (ev.key === "Enter" || ev.key === " ") {{
      var cta = ev.target && ev.target.closest && ev.target.closest(".ss-cta");
      if (cta) {{
        ev.preventDefault();
        activateCta();
      }}
    }}
  }}, true);
  backdrop.addEventListener("click", function() {{ setOpen(false); }});
  drawer.addEventListener("click", function(ev) {{
    var btn = ev.target.closest("[data-ss-act]");
    if (!btn) return;
    var act = btn.getAttribute("data-ss-act");
    if (act === "overview") {{
      if (!onLanding()) {{
        var intro = findButton(/^Introduction$/);
        if (intro) intro.click();
      }}
      setOpen(false);
      return;
    }}
    if (act === "view") {{
      goView(btn.getAttribute("data-ss-view") || "");
      return;
    }}
    if (act === "tour") {{
      var exp = Array.prototype.find.call(doc.querySelectorAll('[data-testid="stExpander"] p, [data-testid="stExpander"] summary, [data-testid="stExpander"]'), function(el) {{
        return /How to Use SmartScan/i.test(el.innerText || "");
      }});
      if (exp) exp.click();
      return;
    }}
    if (act === "overlay") {{
      var sw = doc.querySelector('[data-testid="stSidebar"] [role="switch"], [data-testid="stSidebar"] input[type="checkbox"]');
      if (sw) sw.click();
      else {{
        var tog = Array.prototype.find.call(doc.querySelectorAll("label, p"), function(el) {{
          return /Evaluation overlay/i.test((el.innerText || "").trim());
        }});
        if (tog) tog.click();
      }}
      setOpen(false);
      return;
    }}
    if (act === "doctor") {{
      var docBtn = findButton(/^Doctor$/);
      if (docBtn) docBtn.click();
      setOpen(false);
    }}
  }});
  doc.addEventListener("keydown", function(ev) {{
    if (ev.key === "Escape" && isOpen()) setOpen(false);
  }}, true);

  markLanding();
  var restore = false;
  try {{ restore = window.parent.sessionStorage.getItem("ss_nav_open") === "1"; }} catch (e) {{}}
  setOpen(restore);
  consumePending();
  window.parent.setTimeout(paintActive, 400);
  var mo = new MutationObserver(function() {{
    markLanding();
    paintActive();
    placeCta();
  }});
  mo.observe(doc.body, {{ childList: true, subtree: true }});
  placeCta();
  window.parent.setTimeout(placeCta, 400);
  window.parent.setTimeout(placeCta, 1200);
}})();
"""
    if contains_remote_asset(js):
        raise RuntimeError("nav runtime must stay offline")
    return js
