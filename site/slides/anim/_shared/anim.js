/*
 * anim.js: the shared engine for the animation pages in site/slides/anim/.
 *
 * A page includes this file after anim.css, builds its drawing inside #stage (a 1280x720 design space) and calls
 *
 *   defineAnimation({
 *     beats: 4,            // the last beat number; beat 0 is the slide's entry state, so a page with beats 0..4 says 4
 *     alt:   [...],        // optional: one sentence per beat 0..beats, the text alternative of that state
 *     load(ctx)   {},      // optional: return a promise for the data the page needs (Anim.loadJSON); it is handed to setup
 *     setup(ctx, data) {}, // optional: build the drawing once
 *     render(n, ctx) {},   // snap to beat n's end state. Must set every element it owns (it is called on any beat)
 *     enter(n, ctx)  {},   // animate from beat n-1 to beat n through ctx.animate() / ctx.later(). Must end where render(n) does
 *   });
 *
 * What this file does:
 *   - Stage fit. Embedded in the deck, the stage copies the deck's slide box exactly (see "stage fit").
 *     Standalone, or framed by something that is not a deck, it fits the window.
 *   - The beat engine. Moving forward one beat runs enter(n); every other change snaps through render(n).
 *     When enter(n) is over the engine calls render(n), so a page always ends in its snapped state.
 *   - Inputs: {type: "beat", n} messages from deck-sync.js, ?b=n (open at beat n's end state), window.__anim,
 *     and keys when standalone.
 *   - The deck bridge, ported from the PhD defense deck: a click inside the iframe gives it the keyboard, so keys are
 *     forwarded to reveal through its postMessage API.
 *   - prefers-reduced-motion: every move snaps.
 *
 * Rules for pages: use only transform, opacity and the like through ctx.animate (the Web Animations API), take colors
 * from the CSS tokens (Anim.tok), and keep every animation in a beat under about 8 s.
 */
(function () {
  "use strict";

  const W = 1280, H = 720;                          // the design space every page draws in
  const NS = "http://www.w3.org/2000/svg";
  const EASE = {
    out: "cubic-bezier(0.22, 0.8, 0.3, 1)",         // quick start, soft landing: the default
    inOut: "cubic-bezier(0.65, 0, 0.35, 1)",
    pop: "cubic-bezier(0.3, 1.4, 0.5, 1)",          // a small overshoot
    linear: "linear",
  };
  const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

  // ---- small DOM helpers -------------------------------------------------------------------------------------------
  // attrs: any attribute; `text` sets textContent, `html` innerHTML (HTML elements only), `style` an object.
  function make(ns, tag, attrs, parent) {
    const e = ns ? document.createElementNS(ns, tag) : document.createElement(tag);
    if (attrs) {
      for (const k in attrs) {
        const v = attrs[k];
        if (v == null || v === false) continue;
        if (k === "text") e.textContent = v;
        else if (k === "html") e.innerHTML = v;
        else if (k === "style") Object.assign(e.style, v);
        else e.setAttribute(k, typeof v === "number" ? String(Math.round(v * 100) / 100) : v);
      }
    }
    if (parent) parent.appendChild(e);
    return e;
  }
  const svg = (tag, attrs, parent) => make(NS, tag, attrs, parent);
  const html = (tag, attrs, parent) => make(null, tag, attrs, parent);
  // A token's value, for Web Animations keyframes that need a literal color.
  const tok = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  // JSON next to the page (data/*.json). fetch is refused for file:// pages, so fall back to XMLHttpRequest, which
  // works there when the browser allows local file access (tools/shoot.mjs does).
  function loadJSON(url) {
    return fetch(url).then(r => { if (!r.ok) throw new Error(r.status + " " + url); return r.json(); }).catch(err => new Promise((resolve, reject) => {
      const x = new XMLHttpRequest();
      x.open("GET", url);
      x.onload = () => { try { resolve(JSON.parse(x.responseText)); } catch (e) { reject(e); } };
      x.onerror = () => reject(err);
      x.send();
    }));
  }

  // ---- stage fit ---------------------------------------------------------------------------------------------------
  // Embedded in a reveal deck, a background iframe fills the whole viewport, not the slide. The stage must land exactly
  // on the slide box. Reveal puts .slides at left/top 50% with translate(-50%, -50%) scale(s), so the bounding rect of
  // .slides IS the box, whatever the window shape, margin, or deck-specific offsets. The iframe is same-origin, so read
  // it from the parent. If that fails: parent.Reveal.getScale() centered in this frame; then reveal's own scale law with
  // its defaults (a deck opened from file:// makes the parent opaque).
  // A deck opened from file:// is opaque to this frame: there deck-sync.js, which runs in the deck, pushes the box in a
  // {type: "box", x, y, w, h} message (in this frame's pixels) and anim.js uses that.
  // Not in a deck (opened on its own, or framed by _dev.html): the stage fits the window.
  let pushedBox = null;                                          // the last box deck-sync.js sent
  let refit = () => {};                                          // set by installFit
  function deckInfo() {
    let P;
    try { P = window.parent; if (P === window) return null; void P.document; } catch (e) { return { opaque: true }; }
    let R = null, slides = null;
    try { R = P.Reveal || null; slides = (R && R.getSlidesElement && R.getSlidesElement()) || P.document.querySelector(".reveal .slides"); } catch (e) {}
    return R || slides ? { R, slides } : null;
  }

  // The scale that maps our 1280-wide design onto the deck's slide box. reveal scales its own design size (config.width),
  // so convert from that to ours.
  function revealScale(R) {
    let c = {};
    try { c = (R && R.getConfig()) || {}; } catch (e) {}
    const w = typeof c.width === "number" ? c.width : W, h = typeof c.height === "number" ? c.height : H;
    let s = null;
    try { s = R && R.getScale(); } catch (e) {}
    if (!(s > 0)) {
      // reveal's scale law: the viewport less the margin, fitted to the slide size, clamped to [minScale, maxScale]
      const m = c.margin == null ? 0.04 : c.margin;
      s = clamp(Math.min(innerWidth * (1 - m) / w, innerHeight * (1 - m) / h), c.minScale == null ? 0.2 : c.minScale, c.maxScale == null ? 2 : c.maxScale);
    }
    return s * (w / W);
  }

  function slideBox(info) {
    if (info.slides) {
      const r = info.slides.getBoundingClientRect();
      let fx = 0, fy = 0;
      try { const f = window.frameElement.getBoundingClientRect(); fx = f.left; fy = f.top; } catch (e) {}
      if (r.width > 50 && r.height > 50) return { x: r.left - fx, y: r.top - fy, w: r.width, h: r.height };
    }
    if (info.opaque && pushedBox) return pushedBox;
    const s = revealScale(info.R);
    return { x: (innerWidth - W * s) / 2, y: (innerHeight - H * s) / 2, w: W * s, h: H * s };
  }

  function installFit(stage) {
    const root = document.documentElement;
    let last = "";
    function fit() {
      if (innerWidth < 20 || innerHeight < 20) return;            // an iframe that is not displayed
      const info = deckInfo();
      const box = info ? slideBox(info) : { x: 0, y: 0, w: innerWidth, h: innerHeight };
      const s = Math.min(box.w / W, box.h / H);
      const x = box.x + (box.w - W * s) / 2, y = box.y + (box.h - H * s) / 2;
      const t = `translate(${x.toFixed(2)}px, ${y.toFixed(2)}px) scale(${s.toFixed(5)})`;
      root.classList.toggle("in-deck", !!info);
      if (t !== last) { last = t; stage.style.transform = t; }
    }
    addEventListener("resize", fit);
    document.addEventListener("visibilitychange", fit);
    addEventListener("load", fit);
    // reveal lays out in its own resize handler, which can run after this frame's resize event: listen to it too
    try {
      const R = window.parent.Reveal;
      if (window.parent !== window && R && R.on) {
        R.on("resize", fit);
        addEventListener("pagehide", () => { try { R.off("resize", fit); } catch (e) {} });
      }
    } catch (e) {}
    setInterval(fit, 750);                                        // cheap: it writes only when the box changed
    refit = fit;
    fit();
  }

  // ---- the engine --------------------------------------------------------------------------------------------------
  function defineAnimation(def) {
    const stage = document.getElementById("stage");
    if (!stage) throw new Error("anim.js: the page needs an element with id=\"stage\"");
    const beats = def.beats | 0;
    const embedded = window.parent !== window;
    let cur = 0;                 // the beat on display, or the one being animated to
    let run = null;              // the enter() in progress: {anims, timers, end, ...}
    let deckDriven = false;      // true once a {type: "beat"} message has arrived: the deck owns the beat
    let ready = false;           // false while def.load() is pending
    let pending = null;          // a beat asked for before the page was ready

    const ctx = {
      stage, beats, EASE, svg, html, tok, W, H,
      reduced,
      get beat() { return cur; },
      // A Web Animations animation that the engine tracks: cancelled if the beat is cut short, waited for otherwise.
      animate(el, keyframes, opt) {
        const o = Object.assign({ duration: 500, easing: EASE.out, fill: "both" }, opt);
        const a = el.animate(keyframes, o);
        if (run) {
          run.anims.add(a);
          run.end = Math.max(run.end, (o.delay || 0) + o.duration * (o.iterations || 1) + (o.endDelay || 0));
        }
        return a;
      },
      // A tracked timeout, for things that are not animations (a counter, a label swap). Dropped if the beat is cut short.
      later(ms, fn) {
        const r = run;
        if (!r) return;
        const id = setTimeout(() => { r.timers.delete(id); if (run === r) fn(); }, ms);
        r.timers.add(id);
        r.end = Math.max(r.end, ms);
      },
    };

    function label() {
      const a = def.alt && def.alt[cur];
      stage.setAttribute("aria-label", a || "");
      document.documentElement.dataset.beat = String(cur);
    }

    function drop(r) {           // stop an enter(): cancel its animations and timers
      r.anims.forEach(a => { try { a.cancel(); } catch (e) {} });
      r.timers.forEach(clearTimeout);
      clearTimeout(r.guard);
    }

    function finish() {          // end the running enter() now: the beat shows its end state
      const r = run;
      if (!r) return;
      run = null;
      drop(r);
      def.render(cur, ctx);
      r.done();
    }

    function snap(n) {
      if (run) { const r = run; run = null; drop(r); r.done(); }
      cur = n;
      def.render(n, ctx);
      label();
    }

    function step(n) {           // n is cur + 1
      if (run) finish();
      let done;
      const idle = new Promise(res => { done = res; });
      const r = run = { anims: new Set(), timers: new Set(), end: 0, idle, done };
      cur = n;
      try { def.enter(n, ctx); }
      catch (err) {                                          // a bug in one beat must not strand the slide: show its end state
        console.error(err);
        run = null; drop(r); r.done();
        def.render(n, ctx); label();
        return;
      }
      label();
      // Done when every animation has finished and the last timer has fired. A hidden tab may never advance the
      // animation timeline, so a guard timer settles the beat too.
      const settle = () => { if (run === r) finish(); };
      const t0 = performance.now();
      Promise.allSettled([...r.anims].map(a => a.finished)).then(() => setTimeout(settle, Math.max(0, r.end - (performance.now() - t0)) + 40));
      r.guard = setTimeout(settle, r.end + 800);
      if (!r.anims.size && !r.timers.size) settle();
    }

    // Moving forward one beat animates; any other change snaps to the end state of beat n.
    function show(n, snapOnly) {
      n = clamp(Math.round(+n), 0, beats);
      if (!Number.isFinite(n)) return;
      if (!ready) { pending = n; return; }
      if (n === cur) return;
      if (!snapOnly && !reduced() && n === cur + 1) step(n); else snap(n);
    }

    // ---- inputs ----------------------------------------------------------------------------------------------------
    // The deck: reveal posts nothing to us; deck-sync.js posts {type: "beat", n}.
    addEventListener("message", e => {
      if (e.source !== window.parent && e.source !== window) return;
      let d = e.data;
      if (typeof d === "string") {                          // reveal sends strings like "slide:start"
        if (d.charAt(0) !== "{") return;
        try { d = JSON.parse(d); } catch (err) { return; }
      }
      if (d && d.type === "beat" && Number.isFinite(+d.n)) {
        if (+d.n > beats) console.warn(`anim.js: the slide has ${d.n} fragments but this page has ${beats} beats`);
        deckDriven = true;
        show(+d.n);
      }
      else if (d && d.type === "box" && d.w > 50 && d.h > 50) { pushedBox = { x: +d.x, y: +d.y, w: +d.w, h: +d.h }; refit(); }
    });

    // The deck bridge. Inside reveal's background iframe a click gives this page the keyboard, so reveal never sees
    // the keys. PageDown/PageUp (clickers), N and P always move the deck; Escape toggles its overview. The arrow keys and
    // the space bar step through the beats and fall through to the deck at either end. In the deck the deck owns the
    // beat (its fragments), so "step" means asking reveal for the next fragment or slide. Standalone: just the beats.
    const send = m => { try { window.parent.postMessage(JSON.stringify({ method: m, args: [] }), "*"); } catch (e) {} };
    function press(dir) {                                   // a beat key
      if (embedded && deckDriven) return send(dir > 0 ? "next" : "prev");
      const n = cur + dir;
      if (n < 0 || n > beats) { if (embedded) send(dir > 0 ? "next" : "prev"); return; }
      show(n);
    }
    addEventListener("keydown", e => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key;
      let dir = 0, deck = false;
      if (k === "PageDown" || k === "n" || k === "N") { dir = 1; deck = true; }
      else if (k === "PageUp" || k === "p" || k === "P") { dir = -1; deck = true; }
      else if (k === "ArrowRight" || (k === " " && !e.shiftKey)) dir = 1;
      else if (k === "ArrowLeft" || (k === " " && e.shiftKey)) dir = -1;
      else if (k === "Escape" && embedded) { send("toggleOverview"); return; }
      else if (!embedded && k === "Home") { e.preventDefault(); show(0, true); return; }
      else if (!embedded && k === "End") { e.preventDefault(); show(beats, true); return; }
      else return;
      e.preventDefault();
      e.stopImmediatePropagation();
      if (e.repeat) return;
      if (deck && embedded) send(dir > 0 ? "next" : "prev"); else press(dir);
    }, true);

    // ---- start -----------------------------------------------------------------------------------------------------
    function start(data) {
      if (def.setup) def.setup(ctx, data);
      const b0 = clamp(parseInt(new URLSearchParams(location.search).get("b"), 10) || 0, 0, beats);
      cur = b0;
      def.render(b0, ctx);
      label();
      ready = true;
      window.__anim = {
        beats,
        alt: def.alt || [],
        show,                                               // show(n[, snapOnly]): forward one beat animates, else snaps
        get beat() { return cur; },
        get busy() { return !!run; },
        whenIdle() { return run ? run.idle : Promise.resolve(); },
      };
      if (pending != null) { const n = pending; pending = null; show(n, true); }
      // Tell the deck that this page is ready for its first beat message (deck-sync.js answers).
      if (embedded) { try { window.parent.postMessage({ type: "anim-ready", beats }, "*"); } catch (e) {} }
    }

    installFit(stage);
    if (def.load) {
      Promise.resolve().then(() => def.load(ctx)).then(start).catch(err => {
        console.error(err);
        window.__animError = String(err);
        html("p", { class: "load-error", text: "This animation could not load its data. Open the deck through a web server (quarto preview) rather than from a file." }, stage);
      });
    } else start();
  }

  window.defineAnimation = defineAnimation;
  window.Anim = { svg, html, tok, loadJSON, EASE, W, H, clamp, reduced };
})();
