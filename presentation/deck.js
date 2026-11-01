/* Small offline slide engine for presentation/index.html. No dependencies.
   Keys: Right / Space / PageDown next, Left / PageUp previous, Home / End, F fullscreen, O overview, H help. */
(function () {
  "use strict";
  var W = 1920, H = 1080;
  var stage = document.getElementById("stage");
  var slides = Array.prototype.slice.call(stage.querySelectorAll(".slide"));
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
  var cur = 0, step = 0, enterT = performance.now(), overview = false;
  var JOURNEY = ["Import", "Admission", "Patient / eye", "Confirm Image", "AI grade", "Confirm grade",
    "Annotations", "Finish image", "Report", "Referrals", "Export", "Gold-100"];

  function $$(root, sel) { return Array.prototype.slice.call(root.querySelectorAll(sel)); }

  /* Build journey timelines: <div class="timeline" data-map="4:1,5:2,6:3"></div>
     Nodes before the first mapped node are shown as done. */
  $$(document, ".timeline").forEach(function (tl) {
    var map = {};
    (tl.getAttribute("data-map") || "").split(",").forEach(function (p) {
      var kv = p.split(":"); if (kv.length === 2) map[+kv[0]] = kv[1];
    });
    var first = Math.min.apply(null, Object.keys(map).map(Number));
    var html = '<div class="track"><div class="tl-fill"></div></div>';
    JOURNEY.forEach(function (label, i) {
      var n = i + 1, attr = map[n] ? ' data-f="' + map[n] + '"' : "", cls = n < first ? " done" : "";
      html += '<div class="tl-node' + cls + '"' + attr + '><div class="dot">' + n + '</div><div class="lbl">' + label + "</div></div>";
    });
    tl.innerHTML = html;
  });

  var maxSteps = slides.map(function (s) {
    var m = 0; $$(s, "[data-f]").forEach(function (e) { m = Math.max(m, +e.getAttribute("data-f")); }); return m;
  });

  /* HUD */
  var progress = document.getElementById("progress");
  var countEl = document.getElementById("count");
  var labelEl = document.getElementById("label");
  var stepsEl = document.getElementById("steps");

  function fit() {
    var s = Math.min(window.innerWidth / W, window.innerHeight / H);
    stage.style.transform = "translate(-50%, -50%) scale(" + s + ")";
  }

  function fmt(n) { return Math.round(n).toLocaleString("en-US"); }

  function runCount(el) {
    var to = +el.getAttribute("data-to");
    if (reduce.matches || isNaN(to)) { el.textContent = fmt(to); return; }
    var t0 = performance.now(), dur = +(el.getAttribute("data-dur") || 1400);
    el.textContent = "0";
    (function frame(now) {
      var k = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      el.textContent = fmt(to * e);
      if (k < 1) requestAnimationFrame(frame);
    })(t0);
  }

  function revealed(el) {
    var host = el.closest("[data-f]");
    return !host || host.classList.contains("on");
  }

  function updateTimeline(s) {
    $$(s, ".timeline").forEach(function (tl) {
      var nodes = $$(tl, ".tl-node"), last = -1;
      nodes.forEach(function (n, i) { if (n.classList.contains("done") || n.classList.contains("on")) last = i; });
      tl.querySelector(".tl-fill").style.width = (last < 0 ? 0 : (last / (nodes.length - 1)) * 100) + "%";
    });
  }

  function applyStep(s, n, animate) {
    $$(s, "[data-f]").forEach(function (e) {
      var on = +e.getAttribute("data-f") <= n;
      if (on === e.classList.contains("on")) return;
      e.classList.toggle("on", on);
      if (on) {
        e._t = performance.now();
        if (animate) {
          $$(e, ".count").forEach(runCount);
          if (e.classList.contains("count")) runCount(e);
        }
      }
    });
    updateTimeline(s);
  }

  function hud() {
    progress.style.width = ((cur + (maxSteps[cur] ? step / (maxSteps[cur] + 1) : 0)) / (slides.length - 1 || 1)) * 100 + "%";
    if (cur === slides.length - 1) progress.style.width = "100%";
    countEl.innerHTML = "<b>" + (cur + 1) + "</b> / " + slides.length;
    labelEl.textContent = slides[cur].getAttribute("data-title") || "";
    var m = maxSteps[cur], h = "";
    for (var i = 1; i <= m; i++) h += '<i class="' + (i <= step ? "on" : "") + '"></i>';
    stepsEl.innerHTML = h;
    document.getElementById("hud").classList.toggle("dark", slides[cur].classList.contains("s-title"));
  }

  function go(i, n, fromHash) {
    i = Math.max(0, Math.min(slides.length - 1, i));
    var changed = i !== cur || !slides[i].classList.contains("current");
    if (changed) {
      slides[cur].classList.remove("current");
      cur = i;
      var s = slides[cur];
      // restart CSS entrance animations
      void s.offsetWidth;
      s.classList.add("current");
      enterT = performance.now();
    }
    step = Math.max(0, Math.min(maxSteps[cur], n || 0));
    applyStep(slides[cur], step, false);
    if (changed) $$(slides[cur], ".count").forEach(function (c) { if (revealed(c)) runCount(c); });
    hud();
    if (!fromHash) {
      var hsh = "#/" + (cur + 1);
      if (location.hash !== hsh) history.replaceState(null, "", hsh);
    }
  }

  function next() {
    if (overview) return;
    if (step < maxSteps[cur]) { step++; applyStep(slides[cur], step, true); hud(); }
    else if (cur < slides.length - 1) go(cur + 1, 0);
  }
  function prev() {
    if (overview) return;
    if (step > 0) { step--; applyStep(slides[cur], step, false); hud(); }
    else if (cur > 0) go(cur - 1, maxSteps[cur - 1]);
  }

  /* Overview grid */
  function layoutOverview() {
    var cols = 5, k = 0.18, gx = 22, gy = 22;
    var tw = W * k, th = H * k, rows = Math.ceil(slides.length / cols);
    var ox = (W - (cols * tw + (cols - 1) * gx)) / 2, oy = (H - (rows * th + (rows - 1) * gy)) / 2;
    slides.forEach(function (s, i) {
      var c = i % cols, r = Math.floor(i / cols);
      s.style.transform = overview ? "translate(" + (ox + c * (tw + gx)) + "px," + (oy + r * (th + gy)) + "px) scale(" + k + ")" : "";
    });
  }
  function toggleOverview(force) {
    overview = typeof force === "boolean" ? force : !overview;
    document.body.classList.toggle("overview", overview);
    layoutOverview();
  }
  slides.forEach(function (s, i) {
    s.addEventListener("click", function (ev) {
      if (!overview) return;
      ev.stopPropagation();
      toggleOverview(false);
      go(i, 0);
    });
  });

  function toggleFullscreen() {
    var d = document;
    if (!d.fullscreenElement) { if (d.documentElement.requestFullscreen) d.documentElement.requestFullscreen().catch(function () {}); }
    else if (d.exitFullscreen) d.exitFullscreen();
  }

  document.addEventListener("keydown", function (e) {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    var k = e.key;
    if (k === "ArrowRight" || k === " " || k === "PageDown" || k === "ArrowDown" || k === "Enter") { e.preventDefault(); next(); }
    else if (k === "ArrowLeft" || k === "PageUp" || k === "ArrowUp" || k === "Backspace") { e.preventDefault(); prev(); }
    else if (k === "Home") { e.preventDefault(); go(0, 0); }
    else if (k === "End") { e.preventDefault(); go(slides.length - 1, maxSteps[slides.length - 1]); }
    else if (k === "f" || k === "F") { toggleFullscreen(); }
    else if (k === "o" || k === "O") { toggleOverview(); }
    else if (k === "Escape" && overview) { toggleOverview(false); }
    else if (k === "h" || k === "H" || k === "?") { document.body.classList.toggle("show-help"); }
  });

  /* Click / tap: left third goes back, elsewhere forward. Swipe also works. */
  var downX = null;
  document.addEventListener("pointerdown", function (e) { downX = e.clientX; });
  document.addEventListener("pointerup", function (e) {
    if (overview || downX === null) return;
    if (e.target.closest("a, button")) { downX = null; return; }
    var dx = e.clientX - downX; downX = null;
    if (Math.abs(dx) > 60) { if (dx < 0) next(); else prev(); return; }
    if (e.button !== 0) return;
    if (e.clientX < window.innerWidth / 3) prev(); else next();
  });
  document.getElementById("btnPrev").addEventListener("click", function (e) { e.stopPropagation(); prev(); });
  document.getElementById("btnNext").addEventListener("click", function (e) { e.stopPropagation(); next(); });

  window.addEventListener("resize", fit);
  window.addEventListener("hashchange", function () { fromHash(); });
  function fromHash() {
    var m = /^#\/(\d+)$/.exec(location.hash);
    if (m) { var i = +m[1] - 1; if (i !== cur || !slides[i].classList.contains("current")) go(i, 0, true); }
  }

  /* Data packets travelling along SVG paths. <circle class="pkt" data-path="#id" data-dur="2600" data-delay="0"> */
  function tick(now) {
    var s = slides[cur];
    if (s && !overview) {
      $$(s, ".pkt").forEach(function (p) {
        if (reduce.matches) { p.style.opacity = 0; return; }
        var path = s.querySelector(p.getAttribute("data-path"));
        var host = p.closest("[data-f]");
        if (!path || (host && !host.classList.contains("on"))) { p.style.opacity = 0; return; }
        var t0 = (host ? host._t : enterT) + (+(p.getAttribute("data-delay") || 0));
        var dur = +(p.getAttribute("data-dur") || 2600), el = now - t0;
        if (el < 0) { p.style.opacity = 0; return; }
        var k = (el % dur) / dur, L = path.getTotalLength();
        if (p.hasAttribute("data-reverse")) k = 1 - k;
        var pt = path.getPointAtLength(L * k);
        p.setAttribute("cx", pt.x.toFixed(1)); p.setAttribute("cy", pt.y.toFixed(1));
        var edge = Math.min(k, 1 - k);
        p.style.opacity = edge < 0.06 ? (edge / 0.06).toFixed(2) : 1;
      });
    }
    requestAnimationFrame(tick);
  }

  fit();
  var m0 = /^#\/(\d+)$/.exec(location.hash);
  slides[0].classList.remove("current");
  cur = m0 ? Math.max(0, Math.min(slides.length - 1, +m0[1] - 1)) : 0;
  go(cur, 0, true);
  requestAnimationFrame(tick);
  document.body.classList.add("show-help");
  setTimeout(function () { document.body.classList.remove("show-help"); }, 4000);
})();
