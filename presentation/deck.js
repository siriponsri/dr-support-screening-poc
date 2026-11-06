/* Motion engine for the team deck: reveal.js handles slides and keys, GSAP draws the motion.
   Each slide gets one paused GSAP timeline with labels s0..sN. Reveal fragments are invisible
   "ghost" steps; fragment k plays the timeline to label s(k+1).

   Data attributes on elements inside a slide:
     data-in            fades and rises in when the slide opens (staggered in DOM order)
     data-h="n"         headline n of the .stack (crossfaded at step n; 0 is shown on entry)
     data-step="n"      appears at step n (paths with class .draw are drawn instead)
     data-dim="n"       dims at step n          data-hide="n"   hides at step n
     data-unblur="n"    comes into focus at step n
     data-cam="s,x,y|s,x,y|..."  on an SVG <g>: camera per step (scale and offset in SVG units)
     data-fill="a,b,c"  on .jbar: journey steps filled on entry and at each step
     .count data-to / data-from: counts when it becomes visible
     .pkt data-path="#id" data-dur data-delay: a packet looping along a path while the slide is open
   A builder in CUSTOM replaces the generic timeline for one slide (data-tl="name"). */
(function () {
  "use strict";
  gsap.registerPlugin(DrawSVGPlugin, MotionPathPlugin);
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var E = "expo.out";
  var JOURNEY = ["Import", "Admission", "Patient / eye", "Confirm Image", "AI grade", "Confirm grade",
    "Annotations", "Finish image", "Report", "Referrals", "Export", "Gold-100"];
  var slides = Array.prototype.slice.call(document.querySelectorAll(".reveal .slides > section"));
  function $$(root, sel) { return Array.prototype.slice.call(root.querySelectorAll(sel)); }
  function nums(s) { return String(s || "").split(",").map(Number); }
  function fmt(n) { return Math.round(n).toLocaleString("en-US"); }

  /* journey bars */
  $$(document, ".jbar").forEach(function (b) {
    var h = '<div class="segs">';
    for (var i = 0; i < 12; i++) h += "<i><b></b></i>";
    b.innerHTML = h + '</div><div class="jcount">Step <b class="jn">0</b> / 12<span class="jname"></span></div>';
  });

  function stepCount(sec) {
    var m = 0;
    $$(sec, "[data-step],[data-dim],[data-hide],[data-unblur],[data-h]").forEach(function (e) {
      ["data-step", "data-dim", "data-hide", "data-unblur", "data-h"].forEach(function (a) {
        if (e.hasAttribute(a)) m = Math.max(m, +e.getAttribute(a));
      });
    });
    $$(sec, "[data-cam]").forEach(function (e) { m = Math.max(m, e.getAttribute("data-cam").split("|").length - 1); });
    $$(sec, ".jbar[data-fill]").forEach(function (e) { m = Math.max(m, nums(e.getAttribute("data-fill")).length - 1); });
    if (sec.hasAttribute("data-steps")) m = Math.max(m, +sec.getAttribute("data-steps"));
    return m;
  }

  /* ghost fragments, added before reveal.js starts */
  slides.forEach(function (sec) {
    var n = stepCount(sec), page = sec.querySelector(".page") || sec;
    for (var i = 0; i < n; i++) {
      var g = document.createElement("span");
      g.className = "fragment ghost"; g.setAttribute("data-fragment-index", String(i));
      page.appendChild(g);
    }
  });

  function countTo(tl, el, pos) {
    var to = +el.getAttribute("data-to"), from = +(el.getAttribute("data-from") || 0), o = { v: from };
    el.textContent = fmt(from);
    tl.to(o, { v: to, duration: 1.2, ease: "power2.out", onUpdate: function () { el.textContent = fmt(o.v); } }, pos);
  }
  function fillBar(tl, bar, v, pos) {
    var segs = $$(bar, ".segs b"), jn = bar.querySelector(".jn"), name = bar.querySelector(".jname");
    var o = { v: +jn.textContent || 0 };
    tl.to(segs, { scaleX: function (i) { return i < v ? 1 : 0; }, duration: 0.5, stagger: 0.04, ease: "power2.out" }, pos)
      .to(o, { v: v, duration: 0.6, ease: "power2.out", onUpdate: function () {
        var r = Math.round(o.v); jn.textContent = r; name.textContent = JOURNEY[r - 1] || "";
      } }, pos);
    jn.textContent = String(v);
  }
  function camSpec(s) { var p = s.split(",").map(Number); return { scale: p[0], x: p[1], y: p[2] }; }

  function reveal(tl, els, pos) {
    els.forEach(function (el, i) {
      var p = pos + i * 0.12;
      if (el.matches && el.matches("path.draw, line.draw, polyline.draw, rect.draw, circle.draw")) {
        tl.to(el, { drawSVG: "100%", duration: 0.8, ease: "power2.out" }, p);
      } else {
        tl.to(el, { autoAlpha: 1, y: 0, duration: 0.7, ease: E }, p);
        $$(el, ".draw").forEach(function (d) { tl.to(d, { drawSVG: "100%", duration: 0.8, ease: "power2.out" }, p + 0.1); });
        $$(el, ".count").forEach(function (c) { countTo(tl, c, p + 0.1); });
      }
    });
  }

  function generic(sec) {
    var tl = gsap.timeline({ paused: true });
    var n = stepCount(sec);
    var stepEls = $$(sec, "[data-step]");
    var inStep = function (el) { return !!(el.closest && el.closest("[data-step]")); };
    // initial states
    stepEls.forEach(function (el) {
      if (el.matches("path.draw, line.draw, polyline.draw, rect.draw, circle.draw")) gsap.set(el, { drawSVG: 0 });
      else gsap.set(el, { autoAlpha: 0, y: el.closest("svg") ? 0 : 24 });
    });
    $$(sec, "[data-step] .draw").forEach(function (d) { gsap.set(d, { drawSVG: 0 }); });
    var heads = $$(sec, ".stack > [data-h]");
    if (heads.length) gsap.set(heads, { autoAlpha: 0 });
    var cams = $$(sec, "[data-cam]").map(function (g) { return { g: g, specs: g.getAttribute("data-cam").split("|").map(camSpec) }; });
    cams.forEach(function (c) { gsap.set(c.g, Object.assign({ transformOrigin: "0px 0px" }, c.specs[0])); });
    var bars = $$(sec, ".jbar[data-fill]").map(function (b) { return { b: b, v: nums(b.getAttribute("data-fill")) }; });
    bars.forEach(function (o) { o.b.querySelector(".jn").textContent = "0"; });

    // entry
    var h0 = heads.filter(function (h) { return h.getAttribute("data-h") === "0"; });
    if (h0.length) tl.fromTo(h0, { autoAlpha: 0, y: 28 }, { autoAlpha: 1, y: 0, duration: 0.9, ease: E }, 0);
    var ins = $$(sec, "[data-in]");
    if (ins.length) tl.from(ins, { autoAlpha: 0, y: function (i, el) { return el.ownerSVGElement ? 0 : 30; }, duration: 0.9, ease: E, stagger: 0.08 }, 0.15);
    var draws = $$(sec, ".draw").filter(function (d) { return !d.hasAttribute("data-step") && !inStep(d); });
    if (draws.length) tl.from(draws, { drawSVG: 0, duration: 1.0, ease: "power2.out", stagger: 0.12 }, 0.3);
    $$(sec, ".count").filter(function (c) { return !inStep(c); }).forEach(function (c) { countTo(tl, c, 0.4); });
    bars.forEach(function (o) { fillBar(tl, o.b, o.v[0], 0.1); });
    tl.addLabel("s0", Math.max(tl.duration(), 0.6));

    for (var k = 1; k <= n; k++) {
      var t = tl.duration(), hasCam = false;
      cams.forEach(function (c) {
        if (c.specs[k]) { hasCam = true; tl.to(c.g, Object.assign({ duration: 1.4, ease: "power3.inOut" }, c.specs[k]), t); }
      });
      var hk = heads.filter(function (h) { return +h.getAttribute("data-h") === k; });
      if (hk.length) {
        tl.to(heads, { autoAlpha: 0, y: -16, duration: 0.35, ease: "power2.in" }, t);
        tl.fromTo(hk, { autoAlpha: 0, y: 24 }, { autoAlpha: 1, y: 0, duration: 0.7, ease: E, immediateRender: false }, t + 0.3);
      }
      var rt = t + (hasCam ? 0.8 : 0.25);
      reveal(tl, stepEls.filter(function (e) { return +e.getAttribute("data-step") === k; }), rt);
      $$(sec, '[data-dim="' + k + '"]').forEach(function (e) { tl.to(e, { opacity: 0.22, duration: 0.6 }, rt); });
      $$(sec, '[data-hide="' + k + '"]').forEach(function (e) { tl.to(e, { autoAlpha: 0, duration: 0.4 }, rt); });
      $$(sec, '[data-unblur="' + k + '"]').forEach(function (e) {
        tl.fromTo(e, { filter: "blur(16px)" }, { filter: "blur(0px)", duration: 1.0, ease: "power2.out", immediateRender: false }, rt);
      });
      bars.forEach(function (o) { if (o.v[k] !== undefined && o.v[k] !== o.v[k - 1]) fillBar(tl, o.b, o.v[k], rt); });
      tl.addLabel("s" + k, Math.max(tl.duration(), t + 0.5));
    }
    $$(sec, "[data-unblur]").forEach(function (e) { gsap.set(e, { filter: "blur(16px)" }); });
    bars.forEach(function (o) { o.b.querySelector(".jn").textContent = "0"; o.b.querySelector(".jname").textContent = ""; });
    return tl;
  }

  var CUSTOM = {
    title: function (sec) {
      var q = function (s) { return sec.querySelectorAll(s); };
      var tl = gsap.timeline({ paused: true });
      tl.fromTo(q(".eye"), { scale: 1.35, autoAlpha: 0, filter: "blur(18px)", transformOrigin: "50% 50%" },
                           { scale: 1, autoAlpha: 1, filter: "blur(0px)", duration: 2.2, ease: E }, 0)
        .from(q(".k-cap"), { autoAlpha: 0, duration: 0.8 }, 1.4)
        .from(q(".k-title"), { yPercent: 18, autoAlpha: 0, duration: 1.2, ease: E }, 0.2)
        .from(q(".k-sub"), { y: 24, autoAlpha: 0, duration: 1, ease: E }, 0.7)
        .from(q(".k-meta span"), { autoAlpha: 0, y: 12, stagger: 0.1, duration: 0.8, ease: E }, 1.0)
        .fromTo(q(".ai"), { autoAlpha: 0, scale: 4, transformOrigin: "50% 50%" }, { autoAlpha: 1, scale: 1, duration: 1.1, ease: E }, 1.8)
        .fromTo(q(".hu"), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.6 }, 3.0)
        .to(q(".ai"), { autoAlpha: 0, duration: 0.6 }, 3.0)
        .addLabel("s0");
      return tl;
    }
  };

  /* build everything up front so hidden states apply before a slide is shown */
  var store = new Map();
  slides.forEach(function (sec) {
    var tl = (CUSTOM[sec.getAttribute("data-tl")] || generic)(sec);
    $$(sec, ".pkt").forEach(function (p) { gsap.set(p, { opacity: 0 }); });
    store.set(sec, { tl: tl, loops: null });
  });

  /* Packets are built the first time their slide is shown: SVG geometry cannot be measured while hidden. */
  function makeLoops(sec) {
    return $$(sec, ".pkt").map(function (p) {
      var path = sec.querySelector(p.getAttribute("data-path"));
      var tw = gsap.to(p, { motionPath: { path: path, align: path, alignOrigin: [0.5, 0.5] },
        duration: +(p.getAttribute("data-dur") || 2.4), repeat: -1, repeatDelay: 0.5, ease: "power1.inOut", paused: true,
        onStart: function () { gsap.set(p, { opacity: 1 }); } });
      tw._offset = +(p.getAttribute("data-delay") || 0);
      return tw;
    });
  }
  var current = null;
  function labelFor(tl) {
    var f = Reveal.getIndices().f, n = (typeof f === "number" ? f + 1 : 0);
    return tl.labels["s" + n] !== undefined ? "s" + n : "s0";
  }
  function enter(sec) {
    if (current && current !== sec) {
      var old = store.get(current); if (old && old.loops) old.loops.forEach(function (l) { l.pause(); });
    }
    current = sec;
    var o = store.get(sec); if (!o) return;
    var label = labelFor(o.tl);
    if (reduce) { o.tl.seek(label); return; }
    if (!o.loops) o.loops = makeLoops(sec);
    o.tl.pause(0);
    if (label === "s0") o.tl.tweenTo("s0"); else o.tl.seek(label);
    o.loops.forEach(function (l) { l.restart(); l.time(l._offset); });
  }
  function step() {
    var o = store.get(Reveal.getCurrentSlide()); if (!o) return;
    var label = labelFor(o.tl);
    if (reduce) o.tl.seek(label); else o.tl.tweenTo(label);
  }

  Reveal.initialize({
    width: 1920, height: 1080, margin: 0, minScale: 0.05, maxScale: 4,
    center: false, controls: false, progress: true, slideNumber: "c/t", hash: true, hashOneBasedIndex: true,
    transition: "fade", transitionSpeed: "fast", backgroundTransition: "fade",
    plugins: [RevealNotes]
  }).then(function () { enter(Reveal.getCurrentSlide()); });
  Reveal.on("slidechanged", function (e) { enter(e.currentSlide); });
  Reveal.on("fragmentshown", step);
  Reveal.on("fragmenthidden", step);
})();
