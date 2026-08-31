(function(){
  var doc;
  try { doc = window.parent.document; } catch (e) { return; }
  if (!doc || !doc.body) return;
  var win = window.parent;
  var reduce = win.matchMedia && win.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var coarse = win.matchMedia && win.matchMedia("(pointer: coarse)").matches;
  var old = doc.getElementById("ss-hero-canvas");
  if (old) old.remove();
  var c = doc.createElement("canvas");
  c.id = "ss-hero-canvas";
  c.setAttribute("aria-hidden", "true");
  c.setAttribute("data-ss-core", "1");
  c.style.position = "absolute";
  c.style.inset = "0";
  c.style.width = "100%";
  c.style.height = "100%";
  c.style.zIndex = "2";
  c.style.pointerEvents = "none";
  c.style.background = "transparent";
  var stack = doc.getElementById("ss-stack-css");
  if (!stack) {
    stack = doc.createElement("style");
    stack.id = "ss-stack-css";
    (doc.head || doc.body).appendChild(stack);
  }
  stack.textContent = "#ss-core-host{position:relative;pointer-events:auto;cursor:crosshair}#ss-hero-canvas{position:absolute!important;inset:0!important;width:100%!important;height:100%!important;z-index:2!important;pointer-events:none!important;background:transparent!important}.ss-core-host.has-canvas .ss-core-fallback{opacity:0}#ss-field-canvas{position:fixed!important;inset:0!important;z-index:0!important;pointer-events:none!important}";

  var oldField = doc.getElementById("ss-field-canvas");
  if (oldField) oldField.remove();
  var field = doc.createElement("canvas");
  field.id = "ss-field-canvas";
  field.setAttribute("aria-hidden", "true");
  field.style.position = "fixed";
  field.style.inset = "0";
  field.style.zIndex = "0";
  field.style.pointerEvents = "none";
  if (doc.body.firstChild) doc.body.insertBefore(field, doc.body.firstChild);
  else doc.body.appendChild(field);
  var fctx = field.getContext("2d");
  var fW = 1366, fH = 768;
  var stars = [];
  var waves = [];
  var si, wi;
  for (si = 0; si < 84; si++) {
    stars.push({
      x: Math.random(),
      y: Math.random(),
      z: 0.22 + Math.random() * 0.78,
      tw: Math.random() * 6.28
    });
  }
  for (wi = 0; wi < 4; wi++) {
    waves.push({
      amp: 16 + wi * 11,
      len: 240 + wi * 95,
      speed: 0.10 + wi * 0.045,
      dir: wi % 2 === 0 ? 1 : -1,
      phase: wi * 1.15,
      y: 0.16 + wi * 0.21
    });
  }
  function resizeField() {
    if (!fctx) return;
    var fw = Math.max(320, win.innerWidth || 1366);
    var fh = Math.max(240, win.innerHeight || 768);
    var fdpr = Math.min(win.devicePixelRatio || 1, 1.25);
    field.width = Math.floor(fw * fdpr);
    field.height = Math.floor(fh * fdpr);
    field.style.width = fw + "px";
    field.style.height = fh + "px";
    fctx.setTransform(fdpr, 0, 0, fdpr, 0, 0);
    fW = fw;
    fH = fh;
  }
  resizeField();
  win.addEventListener("resize", resizeField);
  function drawField(timeSec) {
    if (!fctx) return;
    fctx.clearRect(0, 0, fW, fH);
    var sy = win.scrollY || 0;
    var i, st, wv, x, y, tw, baseY;
    for (i = 0; i < stars.length; i++) {
      st = stars[i];
      tw = reduce ? 0.55 : 0.32 + 0.68 * (0.5 + 0.5 * Math.sin(timeSec * 1.35 + st.tw));
      y = ((st.y * fH - sy * st.z * 0.22) % fH + fH) % fH;
      fctx.fillStyle = "rgba(236,244,252," + (0.22 + 0.5 * tw * st.z) + ")";
      var sz = st.z > 0.62 ? 1.7 : 1.05;
      fctx.fillRect(st.x * fW, y, sz, sz);
    }
    if (reduce) return;
    fctx.lineWidth = 1.05;
    for (i = 0; i < waves.length; i++) {
      wv = waves[i];
      fctx.beginPath();
      fctx.strokeStyle = "rgba(190,220,230," + (0.11 + i * 0.03) + ")";
      baseY = ((wv.y * fH + sy * wv.dir * 0.18) % (fH + 120)) - 40;
      for (x = 0; x <= fW; x += 10) {
        y = baseY
          + Math.sin(x / wv.len + timeSec * wv.speed * wv.dir + wv.phase) * wv.amp
          + Math.sin(x / (wv.len * 0.41) + timeSec * 0.19) * wv.amp * 0.32;
        if (x === 0) fctx.moveTo(x, y);
        else fctx.lineTo(x, y);
      }
      fctx.stroke();
    }
  }

  function findHost() {
    return doc.getElementById("ss-core-host") || doc.querySelector("[data-ss-core-host], .ss-core-host");
  }
  function ensureFallback(host) {
    if (!host || host.querySelector(".ss-core-fallback")) return;
    host.insertAdjacentHTML("afterbegin",
      '<svg class="ss-core-fallback" viewBox="0 0 720 520" width="100%" height="100%" aria-hidden="true">' +
      '<ellipse cx="360" cy="252" rx="268" ry="92" fill="none" stroke="#8aa0ac" stroke-width="1.2" opacity="0.5" transform="rotate(-16 360 252)"/>' +
      '<ellipse cx="360" cy="252" rx="204" ry="78" fill="none" stroke="#6f8794" stroke-width="1.1" opacity="0.45" transform="rotate(-28 360 252)"/>' +
      '<ellipse cx="360" cy="252" rx="148" ry="62" fill="none" stroke="#7d96a2" stroke-width="1" opacity="0.4" transform="rotate(22 360 252)"/>' +
      '<path d="M112 252 A248 90 0 0 1 220 180" fill="none" stroke="#3aa8b5" stroke-width="2.4" transform="rotate(-16 360 252)"/>' +
      '<polygon points="360,228 382,240 382,264 360,276 338,264 338,240" fill="#1a2a30" stroke="#3aa8b5" stroke-width="0.9"/>' +
      '<text x="248" y="498" fill="#8a9aa4" font-size="11" font-family="Segoe UI,sans-serif">SPECTRAL INTERCEPT CORE</text></svg>'
    );
  }
  function attachHost() {
    var host = findHost();
    if (host) {
      ensureFallback(host);
      if (c.parentNode !== host) host.appendChild(c);
      host.style.pointerEvents = "auto";
      return true;
    }
    return false;
  }
  attachHost();

  var probe = doc.createElement("canvas");
  var hasWebGL = !!(probe.getContext("webgl") || probe.getContext("experimental-webgl"));
  probe = null;
  var ctx = c.getContext("2d");
  if (!ctx) {
    var hostOnly = findHost();
    if (hostOnly) ensureFallback(hostOnly);
    win.__ssCore = {renderer: "svg-fallback", hasWebGL: hasWebGL, inverse: true, fallback: true};
    function drawLite(ts) {
      if (doc.hidden) { raf = 0; return; }
      var landingLite = !!doc.querySelector(".ss-landing-root");
      field.style.display = landingLite ? "block" : "none";
      drawField((ts || 0) / 1000);
      bindSpectrum();
      raf = win.requestAnimationFrame(drawLite);
    }
    doc.addEventListener("visibilitychange", function() {
      if (!doc.hidden && !raf) raf = win.requestAnimationFrame(drawLite);
    }, false);
    drawLite(0);
    return;
  }

  var dpr = 1, W = 1366, H = 768, raf = 0, t = 0;
  var px = 0, py = 0, tx = 0, ty = 0;
  var rotX = 0.18, rotY = -0.42, rotZ = 0.08;
  var tRotX = 0.18, tRotY = -0.42, tPosX = 0, tPosY = 0, posX = 0, posY = 0;
  var idleY = 0, idleX = 0;
  var scan = 0.35, scanT = 0.35, scanMode = "observe", scanUntil = 1.6;
  var corePulse = 0, depart = 0, ctaPull = 0, coreClick = 0;
  var lastTs = 0, overCore = false;
  var hit = {ox: 0, oy: 0, scale: 180, cox: 0, coy: 0};
  var specPos = 0.12, specVel = 0.11, specHold = 0;

  function ico() {
    var tphi = (1 + Math.sqrt(5)) / 2;
    var raw = [
      [-1, tphi, 0], [1, tphi, 0], [-1, -tphi, 0], [1, -tphi, 0],
      [0, -1, tphi], [0, 1, tphi], [0, -1, -tphi], [0, 1, -tphi],
      [tphi, 0, -1], [tphi, 0, 1], [-tphi, 0, -1], [-tphi, 0, 1]
    ];
    var v = [];
    var i, L;
    for (i = 0; i < raw.length; i++) {
      L = Math.sqrt(raw[i][0]*raw[i][0] + raw[i][1]*raw[i][1] + raw[i][2]*raw[i][2]);
      v.push({x: raw[i][0]/L, y: raw[i][1]/L, z: raw[i][2]/L});
    }
    var f = [
      [0,11,5],[0,5,1],[0,1,7],[0,7,10],[0,10,11],
      [1,5,9],[5,11,4],[11,10,2],[10,7,6],[7,1,8],
      [3,9,4],[3,4,2],[3,2,6],[3,6,8],[3,8,9],
      [4,9,5],[2,4,11],[6,2,10],[8,6,7],[9,8,1]
    ];
    return {v: v, f: f};
  }
  var CORE = ico();

  var rings = [];
  for (var ri = 0; ri < 14; ri++) {
    var tilt = (ri % 5) * 0.33;
    rings.push({
      r: 0.56 + ri * 0.088,
      ax: 0.38 + tilt,
      ay: -0.62 + (ri % 6) * 0.21,
      az: (ri - 6.5) * 0.055,
      layer: ri < 4 ? 0.30 : ri < 9 ? 0.60 : 0.80,
      ghz: 2 + ri * (16 / 13),
      flash: 0,
      flashU: 0
    });
  }

  var gyros = [
    {ax: 1.57, ay: 0.10, az: 0, r: 0.34},
    {ax: 0.18, ay: 1.52, az: 0.2, r: 0.38},
    {ax: 0.9, ay: 0.9, az: 0.7, r: 0.31}
  ];

  var kinds = ["cont", "cont", "period", "period", "sector", "sector", "agile", "agile", "agile", "cont", "period", "sector"];
  var signals = [];
  for (var si = 0; si < 14; si++) {
    signals.push({
      kind: kinds[si % kinds.length],
      ring: si % 14,
      u: Math.random(),
      speed: 0.08 + Math.random() * 0.18,
      phase: Math.random() * 6.28,
      hop: 0,
      novel: 0,
      inward: 0
    });
  }
  var novelAt = 4.5;
  var smartAt = 6.2;

  function resize() {
    var hosted = attachHost();
    var host = findHost();
    if (!hosted || !host || !ctx) return;
    var box = host.getBoundingClientRect();
    var cssW = Math.max(240, Math.floor(box.width) || 520);
    var cssH = Math.max(220, Math.floor(box.height) || 400);
    c.style.position = "absolute";
    c.style.left = "0";
    c.style.top = "0";
    c.style.width = "100%";
    c.style.height = "100%";
    c.style.zIndex = "2";
    if (cssW > 80 && cssH > 80) host.classList.add("has-canvas");
    else host.classList.remove("has-canvas");
    W = cssW;
    H = cssH;
    dpr = Math.min(win.devicePixelRatio || 1, 1.5);
    c.width = Math.floor(W * dpr);
    c.height = Math.floor(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  resize();
  win.addEventListener("resize", resize);

  function normPointer(clientX, clientY) {
    var fw = win.innerWidth || 1366;
    var fh = win.innerHeight || 768;
    return {
      x: (clientX / Math.max(1, fw) - 0.5) * 2,
      y: (clientY / Math.max(1, fh) - 0.5) * 2
    };
  }
  function aimFromPointer(nx, ny, towardCta) {
    var cx = nx, cy = ny;
    if (towardCta) { cx = Math.min(cx, -0.35); }
    tRotY = -0.42 + (-cx * 0.18);
    tRotX = 0.18 + (cy * 0.11);
    tx = -cx;
    ty = -cy;
    tPosX = -cx * 22;
    tPosY = -cy * 14;
  }
  function updateCursorGlow(ev) {
    var halo = doc.querySelector(".ss-cursor");
    if (!halo) return;
    var landingNow = !!doc.querySelector(".ss-landing-root");
    var onSec = false;
    var secs = doc.querySelectorAll(".ss-section");
    var i, r;
    for (i = 0; i < secs.length; i++) {
      r = secs[i].getBoundingClientRect();
      if (ev.clientX >= r.left && ev.clientX <= r.right && ev.clientY >= r.top && ev.clientY <= r.bottom) {
        onSec = true;
        break;
      }
    }
    halo.classList.toggle("is-section", onSec);
    halo.classList.toggle("is-ambient", !reduce && landingNow && !onSec);
  }
  function onMove(ev) {
    updateCursorGlow(ev);
    if (reduce || coarse) return;
    var n = normPointer(ev.clientX, ev.clientY);
    var host = findHost();
    if (host) {
      var hr = host.getBoundingClientRect();
      overCore = ev.clientX >= hr.left && ev.clientX <= hr.right && ev.clientY >= hr.top && ev.clientY <= hr.bottom;
    } else {
      overCore = n.x > 0.05 && ev.clientY < H * 0.86;
    }
    var cta = ev.target && ev.target.closest && ev.target.closest(".ss-cta");
    ctaPull = cta ? 1 : 0;
    aimFromPointer(n.x, n.y, !!cta);
  }
  function onLeave() {
    overCore = false;
    ctaPull = 0;
    tRotY = -0.42;
    tRotX = 0.18;
    tx = 0; ty = 0; tPosX = 0; tPosY = 0;
    var halo = doc.querySelector(".ss-cursor");
    if (halo) {
      halo.classList.remove("is-ambient");
      halo.classList.remove("is-section");
    }
  }
  win.addEventListener("mousemove", onMove, {passive: true});
  win.addEventListener("mouseleave", onLeave);
  doc.addEventListener("mouseleave", onLeave);
  win.addEventListener("scroll", function() {
    var y = win.scrollY || 0;
    if (!depart) c.style.opacity = String(Math.max(0.18, 1 - y / 640));
  }, {passive: true});
  doc.addEventListener("click", function(ev) {
    var el = ev.target && ev.target.closest && ev.target.closest(".ss-cta");
    if (!el) return;
    depart = 0.01;
  }, true);

  function rx(p, a) {
    var cs = Math.cos(a), sn = Math.sin(a);
    return {x: p.x, y: p.y * cs - p.z * sn, z: p.y * sn + p.z * cs};
  }
  function ry(p, a) {
    var cs = Math.cos(a), sn = Math.sin(a);
    return {x: p.x * cs + p.z * sn, y: p.y, z: -p.x * sn + p.z * cs};
  }
  function rz(p, a) {
    var cs = Math.cos(a), sn = Math.sin(a);
    return {x: p.x * cs - p.y * sn, y: p.x * sn + p.y * cs, z: p.z};
  }
  function xform(p, extraX, extraY) {
    var q = rz(p, rotZ);
    q = rx(q, rotX + extraX);
    q = ry(q, rotY + extraY);
    q.x += posX * 0.004;
    q.y += posY * 0.004;
    return q;
  }
  function proj(p, originX, originY, scale) {
    var z = p.z + 3.6;
    var f = 2.35 / Math.max(0.35, z);
    return {x: originX + p.x * f * scale, y: originY + p.y * f * scale, z: p.z, f: f};
  }
  function ringPoint(ring, u) {
    var a = u * Math.PI * 2;
    var p = {x: Math.cos(a) * ring.r, y: 0, z: Math.sin(a) * ring.r};
    p = rx(p, ring.ax);
    p = ry(p, ring.ay);
    p = rz(p, ring.az);
    return p;
  }
  function angDiff(a, b) {
    var d = a - b;
    while (d > Math.PI) d -= Math.PI * 2;
    while (d < -Math.PI) d += Math.PI * 2;
    return Math.abs(d);
  }
  function lerp(a, b, k) { return a + (b - a) * k; }

  function stepScan(dt) {
    if (reduce) return;
    scanUntil -= dt;
    if (scanMode === "slew") {
      scan = lerp(scan, scanT, 0.045);
      if (Math.abs(scan - scanT) < 0.02 || scanUntil < 0) {
        scan = scanT;
        scanMode = "observe";
        scanUntil = 0.9 + Math.random() * 0.7;
        corePulse = 1;
      }
    } else if (scanUntil < 0) {
      if (scanMode === "observe") {
        scanMode = "dwell";
        scanUntil = 1.1 + Math.random() * 1.2;
      } else {
        scanMode = "slew";
        scanT = (scanT + 0.55 + Math.random() * 1.4) % (Math.PI * 2);
        scanUntil = 1.5 + Math.random() * 0.8;
      }
    }
  }

  function bindSections() {
    var secs = doc.querySelectorAll(".ss-section:not([data-ss-bound])");
    if (!secs.length || !win.IntersectionObserver) return;
    var io = new win.IntersectionObserver(function(entries) {
      for (var n = 0; n < entries.length; n++) {
        entries[n].target.classList.toggle("is-in", entries[n].isIntersecting);
      }
    }, {threshold: 0.12});
    for (var s = 0; s < secs.length; s++) {
      secs[s].setAttribute("data-ss-bound", "1");
      io.observe(secs[s]);
    }
  }
  bindSections();
  function bindSpectrum() {
    var bars = doc.querySelectorAll(".ss-spectrum:not([data-ss-scan-bound])");
    var b;
    for (b = 0; b < bars.length; b++) {
      (function(bar) {
        bar.setAttribute("data-ss-scan-bound", "1");
        bar.classList.add("is-live");
        bar.addEventListener("click", function(ev) {
          var r = bar.getBoundingClientRect();
          var w = Math.max(1, r.width);
          specPos = Math.max(0.02, Math.min(0.90, (ev.clientX - r.left) / w - 0.04));
          specHold = 1.65;
          var winEl = bar.querySelector(".win");
          if (winEl) winEl.classList.add("is-held");
          ev.stopPropagation();
        });
      })(bars[b]);
    }
  }
  function stepSpectrum(dt) {
    var bar = doc.querySelector(".ss-spectrum");
    var winEl = bar && bar.querySelector(".win");
    if (!winEl) return;
    if (specHold > 0) {
      specHold = Math.max(0, specHold - dt);
      if (specHold <= 0) winEl.classList.remove("is-held");
    } else if (!reduce) {
      specPos += specVel * dt;
      if (specPos > 0.88 || specPos < 0.04) specVel *= -1;
      specPos = Math.max(0.04, Math.min(0.88, specPos));
    }
    winEl.style.left = (specPos * 100) + "%";
  }
  function bindCoreClick() {
    var host = findHost();
    if (!host || host.getAttribute("data-ss-click") === "1") return;
    host.setAttribute("data-ss-click", "1");
    host.style.pointerEvents = "auto";
    host.addEventListener("click", function(ev) {
      var r = host.getBoundingClientRect();
      var x = ev.clientX - r.left;
      var y = ev.clientY - r.top;
      var dx = x - hit.cox, dy = y - hit.coy;
      if (Math.hypot(dx, dy) < hit.scale * 0.17) {
        corePulse = 1.45;
        coreClick = 1;
        ev.stopPropagation();
        return;
      }
      var bestD = 64, bestI = -1, bestU = 0;
      var i, j, u, pr, d, ring, ox, oy;
      for (i = 0; i < rings.length; i++) {
        ring = rings[i];
        ox = hit.ox + px * 18 * ring.layer;
        oy = hit.oy + py * 12 * ring.layer;
        for (j = 0; j <= 48; j++) {
          u = j / 48;
          pr = proj(xform(ringPoint(ring, u), 0, 0), ox, oy, hit.scale);
          d = Math.hypot(pr.x - x, pr.y - y);
          if (d < bestD) { bestD = d; bestI = i; bestU = u; }
        }
      }
      if (bestI < 0) {
        bestD = 1e9;
        for (i = 0; i < rings.length; i++) {
          ring = rings[i];
          ox = hit.ox + px * 18 * ring.layer;
          oy = hit.oy + py * 12 * ring.layer;
          for (j = 0; j <= 32; j++) {
            u = j / 32;
            pr = proj(xform(ringPoint(ring, u), 0, 0), ox, oy, hit.scale);
            d = Math.hypot(pr.x - x, pr.y - y);
            if (d < bestD) { bestD = d; bestI = i; bestU = u; }
          }
        }
      }
      if (bestI >= 0) {
        rings[bestI].flash = 1.3;
        rings[bestI].flashU = bestU;
      }
      ev.stopPropagation();
    });
  }
  bindSpectrum();
  bindCoreClick();
  var mo = new MutationObserver(function() {
    bindSections();
    bindSpectrum();
    bindCoreClick();
    if (attachHost()) resize();
  });
  mo.observe(doc.body, {childList: true, subtree: true});

  function drawBackground() {
    ctx.clearRect(0, 0, W, H);
    var g = ctx.createRadialGradient(W * 0.48, H * 0.5, 12, W * 0.5, H * 0.52, Math.max(W, H) * 0.72);
    g.addColorStop(0, "rgba(9,19,25,0.35)");
    g.addColorStop(1, "rgba(5,8,11,0.02)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = "rgba(58,168,181,0.10)";
    ctx.lineWidth = 1;
    var i;
    for (i = 0; i < 6; i++) {
      ctx.beginPath();
      ctx.moveTo(W * 0.08 + i * W * 0.16, 12);
      ctx.lineTo(W * 0.08 + i * W * 0.16, H - 12);
      ctx.stroke();
    }
    ctx.font = "10px Segoe UI, sans-serif";
    ctx.fillStyle = "rgba(124,139,150,0.40)";
    var labels = ["2 GHz", "6 GHz", "10 GHz", "14 GHz", "18 GHz"];
    for (i = 0; i < labels.length; i++) {
      ctx.fillText(labels[i], 10, 36 + i * ((H - 70) / 4));
    }
    ctx.fillText("FREQ", W - 48, 22);
    ctx.fillText("RX BAND", W - 62, H - 28);
    ctx.fillText("DWELL", W - 48, H - 14);
  }

  function draw(ts) {
    if (doc.hidden) { raf = 0; return; }
    var landing = !!doc.querySelector(".ss-landing-root");
    if (landing) doc.body.classList.add("ss-on-landing");
    attachHost();
    bindSpectrum();
    bindCoreClick();
    c.style.display = landing ? "block" : "none";
    field.style.display = landing ? "block" : "none";
    if (landing) {
      var hostNow = findHost();
      if (hostNow) {
        var nb = hostNow.getBoundingClientRect();
        if (Math.abs(Math.floor(nb.width) - W) > 12 || Math.abs(Math.floor(nb.height) - H) > 12) {
          resize();
        }
      }
    }
    if (!landing || !c.parentNode) {
      var nowLite = ts || 0;
      var dtLite = lastTs ? Math.min(0.033, (nowLite - lastTs) / 1000) : 0.016;
      lastTs = nowLite;
      if (!reduce) t += dtLite;
      if (landing) {
        drawField(t);
        stepSpectrum(dtLite);
      }
      raf = win.requestAnimationFrame(draw);
      return;
    }
    var now = ts || 0;
    var dt = lastTs ? Math.min(0.033, (now - lastTs) / 1000) : 0.016;
    lastTs = now;
    var damp = reduce ? 1 : 0.055;
    rotX = lerp(rotX, tRotX + idleX, damp);
    rotY = lerp(rotY, tRotY + idleY, damp);
    posX = lerp(posX, tPosX, damp);
    posY = lerp(posY, tPosY, damp);
    px = lerp(px, tx, damp);
    py = lerp(py, ty, damp);
    if (!reduce) {
      idleY = Math.sin(t * 0.09) * 0.10;
      idleX = Math.sin(t * 0.11) * 0.025;
      t += dt;
      stepScan(dt);
      if (depart > 0) {
        depart = Math.min(1, depart + dt / 0.75);
        c.style.opacity = String(Math.max(0.08, 1 - depart));
      }
      if (t > novelAt) {
        novelAt = t + 9 + Math.random() * 5;
        var ns = signals[Math.floor(Math.random() * signals.length)];
        ns.novel = 1.6;
        ns.u = Math.random();
        ns.ring = Math.floor(Math.random() * 14);
      }
      if (t > smartAt) {
        smartAt = t + 7 + Math.random() * 4;
        var pick = signals[Math.floor(Math.random() * signals.length)];
        scanMode = "slew";
        scanT = pick.u * Math.PI * 2;
        scanUntil = 1.8;
        pick.inward = 1;
      }
      var s;
      for (s = 0; s < signals.length; s++) {
        var sg = signals[s];
        if (sg.kind === "cont") sg.u = (sg.u + dt * sg.speed * 0.12) % 1;
        else if (sg.kind === "period") sg.u = (0.5 + 0.5 * Math.sin(t * sg.speed * 2.2 + sg.phase));
        else if (sg.kind === "sector") sg.u = 0.28 + 0.22 * Math.sin(t * sg.speed * 1.6 + sg.phase);
        else if (sg.kind === "agile") {
          sg.hop += dt;
          if (sg.hop > 1.8 + sg.phase) {
            sg.hop = 0;
            sg.ring = (sg.ring + 3 + (sg.phase > 3 ? 2 : 1)) % 14;
            sg.u = Math.random();
          }
        }
        if (sg.novel > 0) sg.novel = Math.max(0, sg.novel - dt);
        if (sg.inward > 0) sg.inward = Math.max(0, sg.inward - dt * 0.7);
      }
    }
    if (corePulse > 0) corePulse = Math.max(0, corePulse - dt * 1.6);
    if (coreClick > 0) coreClick = Math.max(0, coreClick - dt * 1.35);
    var rf;
    for (rf = 0; rf < rings.length; rf++) {
      if (rings[rf].flash > 0) rings[rf].flash = Math.max(0, rings[rf].flash - dt * 1.05);
    }
    stepSpectrum(dt);

    var vw = win.innerWidth || 1366;
    var vh = win.innerHeight || 768;
    var narrow = vw < 980 || (vw / Math.max(1, vh)) < 0.82;
    var short = vh < 720;
    var originX = W * 0.50;
    var originY = H * 0.50;
    var scale = Math.min(W, H) * (narrow ? 0.40 : short ? 0.44 : 0.50);
    if (depart) scale *= (1 - depart * 0.35);
    originY += depart * 28;
    hit.ox = originX;
    hit.oy = originY;
    hit.scale = scale;
    hit.cox = originX + px * 18 * 0.8;
    hit.coy = originY + py * 12 * 0.8;

    drawField(t);
    drawBackground();

    var segs = coarse || reduce ? 40 : 64;
    var i, j, p, q, a, b, pr, ring, u, lit, depthK, sg;

    for (i = 0; i < rings.length; i++) {
      ring = rings[i];
      var flash = ring.flash || 0;
      depthK = ring.layer;
      var ox = originX + px * 18 * depthK;
      var oy = originY + py * 12 * depthK;
      ctx.beginPath();
      for (j = 0; j <= segs; j++) {
        u = j / segs;
        p = xform(ringPoint(ring, u), 0, 0);
        pr = proj(p, ox, oy, scale);
        if (j === 0) ctx.moveTo(pr.x, pr.y); else ctx.lineTo(pr.x, pr.y);
      }
      ctx.strokeStyle = flash > 0
        ? "rgba(236,248,255," + (0.55 + 0.45 * flash) + ")"
        : "rgba(168,190,200,0.72)";
      ctx.lineWidth = 1.35 + flash * 1.9;
      ctx.stroke();
      if (flash > 0.08) {
        ctx.beginPath();
        var lit2 = false;
        for (j = 0; j <= segs; j++) {
          u = j / segs;
          a = u * Math.PI * 2;
          if (angDiff(a, ring.flashU * Math.PI * 2) > 0.22) { lit2 = false; continue; }
          p = xform(ringPoint(ring, u), 0, 0);
          pr = proj(p, ox, oy, scale);
          if (!lit2) { ctx.moveTo(pr.x, pr.y); lit2 = true; }
          else ctx.lineTo(pr.x, pr.y);
        }
        ctx.strokeStyle = "rgba(255,255,255," + (0.55 + 0.4 * flash) + ")";
        ctx.lineWidth = 2.8;
        ctx.stroke();
      }
      ctx.beginPath();
      var started = false;
      for (j = 0; j <= segs; j++) {
        u = j / segs;
        a = u * Math.PI * 2;
        lit = angDiff(a, scan) < 0.16;
        if (!lit) { started = false; continue; }
        p = xform(ringPoint(ring, u), 0, 0);
        pr = proj(p, ox, oy, scale);
        if (!started) { ctx.moveTo(pr.x, pr.y); started = true; }
        else ctx.lineTo(pr.x, pr.y);
      }
      ctx.strokeStyle = "rgba(70,210,220,1)";
      ctx.lineWidth = 2.6;
      ctx.stroke();
    }

    var gox = originX + px * 18 * 0.8;
    var goy = originY + py * 12 * 0.8;
    for (i = 0; i < gyros.length; i++) {
      ctx.beginPath();
      for (j = 0; j <= 48; j++) {
        u = j / 48;
        a = u * Math.PI * 2;
        p = {x: Math.cos(a) * gyros[i].r, y: 0, z: Math.sin(a) * gyros[i].r};
        p = rx(p, gyros[i].ax); p = ry(p, gyros[i].ay);
        p = xform(p, 0, 0);
        pr = proj(p, gox, goy, scale);
        if (j === 0) ctx.moveTo(pr.x, pr.y); else ctx.lineTo(pr.x, pr.y);
      }
      ctx.strokeStyle = "rgba(140,165,175,0.55)";
      ctx.lineWidth = 1.15;
      ctx.stroke();
    }

    var cox = originX + px * 18 * 0.8;
    var coy = originY + py * 12 * 0.8;
    var faces = [];
    for (i = 0; i < CORE.f.length; i++) {
      var ia = CORE.f[i][0], ib = CORE.f[i][1], ic = CORE.f[i][2];
      a = xform({x: CORE.v[ia].x * 0.28, y: CORE.v[ia].y * 0.28, z: CORE.v[ia].z * 0.28}, 0, 0);
      b = xform({x: CORE.v[ib].x * 0.28, y: CORE.v[ib].y * 0.28, z: CORE.v[ib].z * 0.28}, 0, 0);
      q = xform({x: CORE.v[ic].x * 0.28, y: CORE.v[ic].y * 0.28, z: CORE.v[ic].z * 0.28}, 0, 0);
      var nx = (b.y - a.y) * (q.z - a.z) - (b.z - a.z) * (q.y - a.y);
      var ny = (b.z - a.z) * (q.x - a.x) - (b.x - a.x) * (q.z - a.z);
      var nz = (b.x - a.x) * (q.y - a.y) - (b.y - a.y) * (q.x - a.x);
      faces.push({a: a, b: b, c: q, z: (a.z + b.z + q.z) / 3, nz: nz});
    }
    faces.sort(function(m, n) { return m.z - n.z; });
    for (i = 0; i < faces.length; i++) {
      var fa = proj(faces[i].a, cox, coy, scale);
      var fb = proj(faces[i].b, cox, coy, scale);
      var fc = proj(faces[i].c, cox, coy, scale);
      var litn = 0.18 + 0.55 * Math.max(0, faces[i].nz);
      var pulse = 0.12 * corePulse + 0.28 * coreClick;
      ctx.beginPath();
      ctx.moveTo(fa.x, fa.y); ctx.lineTo(fb.x, fb.y); ctx.lineTo(fc.x, fc.y); ctx.closePath();
      ctx.fillStyle = "rgba(" + Math.floor(28 + litn * 55) + "," + Math.floor(42 + litn * 70 + pulse * 80) + "," + Math.floor(48 + litn * 75 + pulse * 90) + "," + (0.78 + pulse) + ")";
      ctx.fill();
      ctx.strokeStyle = "rgba(70,210,220," + (0.35 + pulse) + ")";
      ctx.lineWidth = 0.85;
      ctx.stroke();
    }

    var sox = originX + px * 22;
    var soy = originY + py * 16;
    for (i = 0; i < signals.length; i++) {
      sg = signals[i];
      ring = rings[sg.ring];
      p = ringPoint(ring, sg.u);
      if (sg.inward > 0) {
        p = {x: p.x * sg.inward, y: p.y * sg.inward, z: p.z * sg.inward};
      }
      p = xform(p, 0, 0);
      pr = proj(p, sox, soy, scale);
      a = sg.u * Math.PI * 2;
      lit = angDiff(a, scan) < 0.18;
      var rad = 1.5 + (lit ? 1.4 : 0) + (sg.novel > 0 ? 1.2 : 0);
      if (sg.novel > 0) ctx.fillStyle = "rgba(196,146,42," + (0.35 + 0.5 * sg.novel) + ")";
      else if (lit) ctx.fillStyle = "rgba(58,168,181,0.9)";
      else ctx.fillStyle = "rgba(86,180,233,0.35)";
      ctx.beginPath(); ctx.arc(pr.x, pr.y, rad, 0, 6.283); ctx.fill();
      if (sg.novel > 0.4) {
        ctx.strokeStyle = "rgba(196,146,42,0.45)";
        ctx.beginPath(); ctx.arc(pr.x, pr.y, rad + 4, 0, 6.283); ctx.stroke();
      }
    }

    ctx.font = "10px Segoe UI, sans-serif";
    ctx.fillStyle = "rgba(168,186,196,0.55)";
    ctx.fillText("SPECTRAL INTERCEPT CORE", originX - 78, originY + scale * 0.92);
    ctx.fillText("RX / SCAN", originX - 22, originY - scale * 0.78);

    win.__ssCore = {
      rotX: rotX, rotY: rotY, posX: posX, posY: posY,
      tx: tx, ty: ty, scan: scan, scanMode: scanMode,
      overCore: overCore, renderer: "canvas3d", hasWebGL: hasWebGL,
      hosted: !!findHost(),
      w: W, h: H, field: true, specHold: specHold
    };

    raf = win.requestAnimationFrame(draw);
  }
  doc.addEventListener("visibilitychange", function() {
    if (!doc.hidden && !raf) raf = win.requestAnimationFrame(draw);
  }, false);
  draw(0);
})();
