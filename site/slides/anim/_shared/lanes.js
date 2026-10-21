/*
 * lanes.js: the lanes picture grammar as a reusable renderer. Needs anim.js (Anim.svg, Anim.EASE) and anim.css (.lanes).
 *
 *   one lane per worker, with time running left to right; one block per task; gray for overhead;
 *   an empty track for idle time; a vertical finish line for the total time.
 *
 *   const view = Lanes.create({
 *     parent,                // an SVG element or <g> to draw into
 *     x, y,                  // x: where domain[0] sits. y: the top of lane 0
 *     width,                 // pixel width of the time domain
 *     domain: [t0, t1],      // the time scale: domain maps onto [x, x + width]. Or pass scale: Lanes.scale(domain, [x0, x1])
 *     lanes: 4,              // lane rows the layout reserves
 *     laneH: 64, gap: 24,    // lane height, space between lanes
 *     inset: 8,              // space between a block and the top and bottom of its lane
 *     blockGap: 3,           // space between neighbouring blocks, taken out of the block
 *     overheadGap: 1,        // the same for an overhead sliver (default: blockGap); a thin sliver needs most of its width
 *     finLead: 40, labelLift: 14,   // the finish line starts this far above lane 0; its label sits this far above the line
 *     ghostDrop: 34,                // a ghost's short label sits this much lower, so it never runs into the live label
 *     labels: i => "worker " + (i + 1),     // lane labels, or an array. Drawn right-aligned, left of the track
 *     axis: { ticks: [0, 3, 6, 9, 12], title: "time →" },   // or false
 *     align: "top",          // "top": lane 0 stays put. "center": the shown lanes are centered in the reserved height
 *     show: 1,               // lanes shown at the start (default: all)
 *     animate: ctx.animate,  // route animations through the beat engine so that a cut-short beat can cancel them
 *   });
 *
 *   Items: {id, worker, start, end, kind: "task" | "overhead", label?, pos?: {x, y}}. Times are in domain units.
 *   pos parks an item outside the lanes at a fixed place in stage pixels, like a queue waiting to start.
 *
 *   view.set(items, opts)      show exactly these items. A known id moves, a new id appears, a missing id disappears.
 *                              opts: animate, duration, delay, stagger (ms between items), delayOf ((item, i) => ms, replaces
 *                              stagger), ease, order (item => sort key), arc (px: a moving block swoops this far above its
 *                              higher end instead of sliding across the others; or a function (from, to) => y of the peak),
 *                              fill (true: add the blocks empty, ready for view.fill)
 *   view.showLanes(n, opts)    show the first n lanes; moves the axis and, with align "center", the whole stack
 *   view.finish(t, label, opts)   the finish line at t. The line before it stays as a ghost.
 *                              opts: side "start" | "end" (the label sits right | left of the line), ghostLabel, animate, delay
 *   view.moveFinish(t, label, opts)   slide the current finish line to t and change its label
 *   view.clearFinish(opts)     remove the finish line and the ghosts
 *   view.fill(opts)            replay: every block grows over its own time span. opts.duration is the length of the
 *                              whole domain in ms; also delay, ease
 *   view.seek(p)               snap a replay to progress p in [0, 1]
 *   view.scale                 {x(t), w(dt), t(x)}
 *   view.laneTop(i), view.box(item), view.root, view.destroy()
 *
 * Every state change takes opts.animate (default false: snap). With animate the new state is written first and the
 * transition is played from the old one, so cancelling the animations leaves the end state in place.
 */
(function () {
  "use strict";
  const { svg, EASE } = window.Anim;

  const r2 = v => Math.round(v * 100) / 100;
  const tr = (x, y) => `translate(${r2(x)}px, ${r2(y)}px)`;

  function scale(domain, range) {
    const [t0, t1] = domain, [x0, x1] = range, k = (x1 - x0) / (t1 - t0);
    return { domain, range, x: t => x0 + (t - t0) * k, w: dt => dt * k, t: x => t0 + (x - x0) / k };
  }

  function create(opts) {
    const o = Object.assign({
      x: 0, y: 0, width: 800, domain: [0, 1], lanes: 4, laneH: 64, gap: 24, inset: 8, blockGap: 3, overheadGap: null, pad: 6, labelGap: 16, finLead: 40, labelLift: 14, ghostDrop: 34,
      labels: i => "worker " + (i + 1), axis: false, align: "top", show: null,
      animate: (el, keyframes, opt) => el.animate(keyframes, Object.assign({ fill: "both" }, opt)),
    }, opts);
    if (o.overheadGap == null) o.overheadGap = o.blockGap;
    const S = o.scale || scale(o.domain, [o.x, o.x + o.width]);
    o.domain = S.domain; o.x = S.range[0]; o.width = S.range[1] - S.range[0];
    const labelOf = Array.isArray(o.labels) ? i => o.labels[i] : o.labels;
    const anim = (el, kf, opt) => o.animate(el, kf, Object.assign({ duration: 600, easing: EASE.out }, opt));

    // ---- geometry. All of it is in stage pixels; the stack group applies the vertical centering. ----
    const pitch = o.laneH + o.gap;
    const laneTop = i => o.y + i * pitch;
    const visH = n => (n - 1) * pitch + o.laneH;                       // height of n lanes
    const axisY = n => laneTop(0) + visH(n) + 26;                      // the axis line, under the last shown lane
    const extent = n => visH(n) + (o.axis ? 26 + 46 : 0);              // lanes + axis + tick labels
    const offsetFor = n => (o.align === "center" ? (extent(o.lanes) - extent(n)) / 2 : 0);
    const finTop = () => laneTop(0) - o.finLead;
    const finBottom = n => (o.axis ? axisY(n) : laneTop(0) + visH(n) + 14);
    const lineScale = n => (finBottom(n) - finTop()) / (finBottom(o.lanes) - finTop());
    const blockH = o.laneH - 2 * o.inset;
    const trackX = S.x(o.domain[0]) - o.pad, trackW = o.width + 2 * o.pad;

    let shown = o.show == null ? o.lanes : o.show;

    // ---- the drawing: root > stack > [lanes, axis, items, finish lines] ----
    const root = svg("g", { class: "lanes" }, o.parent);
    const stack = svg("g", {}, root);
    stack.style.transform = tr(0, offsetFor(shown));
    const laneEls = [];
    for (let i = 0; i < o.lanes; i++) {
      const g = svg("g", {}, stack);
      svg("rect", { class: "track", x: trackX, y: laneTop(i), width: trackW, height: o.laneH, rx: 14 }, g);
      const name = labelOf(i);
      if (name != null) svg("text", { class: "lane-label", x: trackX - o.labelGap, y: laneTop(i) + o.laneH / 2, dy: "0.35em", "text-anchor": "end", text: name }, g);
      g.style.opacity = i < shown ? 1 : 0;
      laneEls.push(g);
    }
    let axisEl = null;
    if (o.axis) {
      axisEl = svg("g", {}, stack);
      axisEl.style.transform = tr(0, axisY(shown));
      svg("line", { class: "axis-line", x1: trackX, x2: trackX + trackW, y1: 0, y2: 0 }, axisEl);
      for (const t of o.axis.ticks || o.domain) {
        svg("line", { class: "tick", x1: S.x(t), x2: S.x(t), y1: 0, y2: 12 }, axisEl);
        svg("text", { class: "tick-label", x: S.x(t), y: 40, "text-anchor": "middle", text: String(t) }, axisEl);
      }
      if (o.axis.title) svg("text", { class: "axis-title", x: trackX - o.labelGap, y: 0, dy: "0.35em", "text-anchor": "end", text: o.axis.title }, axisEl);
    }
    const gItems = svg("g", {}, stack);
    const gFinish = svg("g", {}, stack);

    // ---- items ----
    const items = new Map();                                           // id -> {it, g, rect, text, b, dead}

    function box(it) {
      const w = Math.max(S.w(it.end - it.start), 1);
      if (it.pos) return { x: it.pos.x, y: it.pos.y - offsetFor(shown), w, h: blockH };
      return { x: S.x(it.start), y: laneTop(it.worker) + o.inset, w, h: blockH };
    }
    const cls = it => "blk fb-l " + (it.kind === "overhead" ? "overhead" : "task");
    const gapOf = it => (it.kind === "overhead" ? o.overheadGap : o.blockGap);       // space taken out of a block, shared by its neighbours
    const rectW = (w, it) => Math.max(w - gapOf(it), 1);
    const rectR = (w, it) => Math.min(10, rectW(w, it) * 0.3);       // a narrow block keeps square-ish corners

    // the number or name inside a block; hidden when the block is too short to hold it
    function labelFor(rec, label, w) {
      if (rec.text) { rec.text.remove(); rec.text = null; }
      if (label == null) return null;
      const t = svg("text", { class: "blk-label", x: w / 2, y: blockH / 2, dy: "0.35em", "text-anchor": "middle", text: String(label) }, rec.g);
      t.style.opacity = w >= 34 ? 1 : 0;
      rec.text = t;
      return t;
    }

    function build(it, b, empty) {
      const g = svg("g", {}, gItems);
      g.style.transform = tr(b.x, b.y);
      const rect = svg("rect", { class: cls(it), x: gapOf(it) / 2, y: 0, width: rectW(b.w, it), height: b.h, rx: rectR(b.w, it) }, g);
      const rec = { it, g, rect, text: null, b, dead: false };
      labelFor(rec, it.label, b.w);
      if (empty) rect.style.transform = "scaleX(0)";
      return rec;
    }

    // Keyframes for a hop: the block lifts almost straight up, crosses `arc` px above the higher end, and comes down
    // almost straight onto its target, so it never slides across the blocks that have already landed.
    function arcPath(a, b, arc) {
      const top = typeof arc === "function" ? arc(a, b) : Math.min(a.y, b.y) - arc, dx = b.x - a.x;
      const c1 = { x: a.x + 0.08 * dx, y: top }, c2 = { x: b.x - 0.08 * dx, y: top };
      const out = [];
      for (let i = 0; i <= 16; i++) {
        const t = i / 16, u = 1 - t;
        const k0 = u * u * u, k1 = 3 * u * u * t, k2 = 3 * u * t * t, k3 = t * t * t;
        out.push({ transform: tr(k0 * a.x + k1 * c1.x + k2 * c2.x + k3 * b.x, k0 * a.y + k1 * c1.y + k2 * c2.y + k3 * b.y) });
      }
      return out;
    }

    function purge() { for (const [id, rec] of items) if (rec.dead) { rec.g.remove(); items.delete(id); } }

    function set(list, opt) {
      const p = Object.assign({ animate: false, duration: 600, delay: 0, stagger: 0, delayOf: null, ease: EASE.out, fill: false, order: null, arc: 0 }, opt);
      purge();
      const ordered = p.order ? [...list].sort((a, b) => p.order(a) - p.order(b)) : list;
      const seen = new Set();
      let k = 0;
      for (const it of ordered) {
        seen.add(it.id);
        const b = box(it);
        const delay = p.delay + (p.delayOf ? p.delayOf(it, k) : k * p.stagger);
        k++;
        let rec = items.get(it.id);
        if (!rec) {                                                    // a new block: it grows in from its left edge
          rec = build(it, b, p.fill || p.animate);
          items.set(it.id, rec);
          if (p.animate && !p.fill) {
            rec.rect.style.transform = "";
            anim(rec.rect, [{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }], { duration: Math.min(p.duration, 500), delay, easing: p.ease });
            if (rec.text) anim(rec.text, [{ opacity: 0 }, { opacity: rec.text.style.opacity }], { duration: 300, delay: delay + 200 });
          }
          continue;
        }
        const to = tr(b.x, b.y), from = rec.g.style.transform;
        const relabel = (it.label == null ? null : String(it.label)) !== (rec.it.label == null ? null : String(rec.it.label));
        const rekind = it.kind !== rec.it.kind;
        rec.it = it;
        rec.rect.setAttribute("class", cls(it));
        if (rekind) { rec.rect.setAttribute("x", gapOf(it) / 2); rec.rect.setAttribute("width", rectW(b.w, it)); rec.rect.setAttribute("rx", rectR(b.w, it)); }
        if (relabel) {
          const t = labelFor(rec, it.label, b.w);
          if (t && p.animate && t.style.opacity === "1") anim(t, [{ opacity: 0 }, { opacity: 1 }], { duration: 350, delay: delay + p.duration * 0.45, easing: EASE.out });
        }
        if (from !== to) {
          rec.g.style.transform = to;
          if (p.animate) anim(rec.g, p.arc ? arcPath(rec.b, b, p.arc) : [{ transform: from }, { transform: to }], { duration: p.duration, delay, easing: p.ease });
        }
        if (Math.abs(b.w - rec.b.w) > 0.5) {                           // a block that changed length stretches from its left edge
          rec.rect.setAttribute("width", rectW(b.w, it));
          rec.rect.setAttribute("rx", rectR(b.w, it));
          if (rec.text) { rec.text.setAttribute("x", b.w / 2); rec.text.style.opacity = b.w >= 34 ? 1 : 0; }
          if (p.animate) anim(rec.rect, [{ transform: `scaleX(${rec.b.w / b.w})` }, { transform: "scaleX(1)" }], { duration: p.duration, delay, easing: p.ease });
        }
        rec.b = b;
      }
      for (const [id, rec] of items) {                                 // a block that is gone fades out, then is purged
        if (seen.has(id) || rec.dead) continue;
        rec.dead = true;
        rec.g.style.opacity = 0;
        if (p.animate) anim(rec.g, [{ opacity: 1 }, { opacity: 0 }], { duration: 300, delay: p.delay });
        else { rec.g.remove(); items.delete(id); }
      }
    }

    // ---- lanes, axis, stack ----
    function showLanes(n, opt) {
      const p = Object.assign({ animate: false, duration: 600, delay: 0, stagger: 140, ease: EASE.inOut }, opt);
      const old = shown;
      shown = n;
      laneEls.forEach((g, i) => {
        g.style.opacity = i < n ? 1 : 0;
        if (p.animate && i >= old && i < n) {
          anim(g, [{ opacity: 0, transform: tr(0, 14) }, { opacity: 1, transform: tr(0, 0) }], { duration: 500, delay: p.delay + 120 + (i - old) * p.stagger, easing: EASE.out });
        }
      });
      const s0 = stack.style.transform, s1 = tr(0, offsetFor(n));
      stack.style.transform = s1;
      if (p.animate && s0 !== s1) anim(stack, [{ transform: s0 }, { transform: s1 }], { duration: p.duration, delay: p.delay, easing: p.ease });
      if (axisEl) {
        const a0 = axisEl.style.transform, a1 = tr(0, axisY(n));
        axisEl.style.transform = a1;
        // it fades out where it was and back in where it belongs, so it never sweeps across the lanes that unfold
        if (p.animate && a0 !== a1) anim(axisEl, [{ opacity: 1, transform: a0 }, { opacity: 0, transform: a0, offset: 0.12 }, { opacity: 0, transform: a1, offset: 0.7 }, { opacity: 1, transform: a1 }], { duration: p.duration + 300, delay: p.delay, easing: "ease-in-out" });
      }
      for (const f of fins) {                                          // finish lines reach down to the axis
        const l0 = f.solid.style.transform, l1 = `scaleY(${r2(lineScale(n) * 1000) / 1000})`;
        f.solid.style.transform = l1;
        f.dots.style.transform = l1;
        if (p.animate && l0 !== l1) { anim(f.solid, [{ transform: l0 || "scaleY(1)" }, { transform: l1 }], { duration: p.duration, delay: p.delay, easing: p.ease }); anim(f.dots, [{ transform: l0 || "scaleY(1)" }, { transform: l1 }], { duration: p.duration, delay: p.delay, easing: p.ease }); }
      }
    }

    // ---- finish lines ----
    const fins = [];                                                   // every finish line, the last one is current
    let cur = null;

    function labelEl(rec, text, side, ghost) {
      const t = svg("text", { class: "finish-label" + (ghost ? " ghost" : ""), x: side === "end" ? -16 : 16, y: finTop() - o.labelLift + (ghost ? o.ghostDrop : 0), "text-anchor": side, text }, rec.g);
      return t;
    }

    function pruneFins() {                                             // drop the lines that clearFinish faded out
      for (let i = fins.length - 1; i >= 0; i--) if (fins[i].cleared) { fins[i].g.remove(); fins.splice(i, 1); }
    }

    function finish(t, label, opt) {
      const p = Object.assign({ side: "start", animate: false, duration: 600, delay: 0, ghostLabel: null }, opt);
      pruneFins();
      if (cur) ghostify(cur, p);
      const g = svg("g", {}, gFinish);
      const x = S.x(t);
      g.style.transform = tr(x, 0);
      const scaleY = `scaleY(${r2(lineScale(shown) * 1000) / 1000})`;
      const attrs = { x1: 0, x2: 0, y1: finTop(), y2: finBottom(o.lanes) };
      const rec = { g, t, side: p.side, ghostLabelText: p.ghostLabel, old: [], ghost: false };
      rec.dots = svg("line", Object.assign({ class: "finish-ghost fb-t" }, attrs), g);
      rec.solid = svg("line", Object.assign({ class: "finish-line fb-t" }, attrs), g);
      rec.dots.style.transform = scaleY;
      rec.solid.style.transform = scaleY;
      rec.dots.style.opacity = 0;
      rec.lab = labelEl(rec, label, p.side, false);
      rec.gl = p.ghostLabel ? labelEl(rec, p.ghostLabel, p.side, true) : null;
      if (rec.gl) rec.gl.style.opacity = 0;
      fins.push(rec);
      cur = rec;
      if (p.animate) anim(g, [{ opacity: 0, transform: tr(x, -36) }, { opacity: 1, transform: tr(x, 0) }], { duration: p.duration, delay: p.delay, easing: EASE.out });
      return rec;
    }

    function ghostify(rec, p) {
      if (rec.ghost) return;
      rec.ghost = true;
      const d = { duration: 500, delay: p.delay || 0, easing: EASE.inOut };
      rec.solid.style.opacity = 0;
      rec.dots.style.opacity = 0.6;
      rec.lab.style.opacity = 0;
      if (rec.gl) rec.gl.style.opacity = 1;
      if (p.animate) {
        anim(rec.solid, [{ opacity: 1 }, { opacity: 0 }], d);
        anim(rec.dots, [{ opacity: 0 }, { opacity: 0.6 }], d);
        anim(rec.lab, [{ opacity: 1 }, { opacity: 0 }], Object.assign({}, d, { duration: 250 }));
        if (rec.gl) anim(rec.gl, [{ opacity: 0 }, { opacity: 1 }], Object.assign({}, d, { delay: d.delay + 250, duration: 300 }));
      }
    }

    function moveFinish(t, label, opt) {
      const p = Object.assign({ animate: false, duration: 800, delay: 0, side: null }, opt);
      const rec = cur;
      if (!rec) return;
      const f0 = tr(S.x(rec.t), 0), f1 = tr(S.x(t), 0);
      rec.t = t;
      rec.g.style.transform = f1;
      if (p.animate && f0 !== f1) anim(rec.g, [{ transform: f0 }, { transform: f1 }], { duration: p.duration, delay: p.delay, easing: EASE.inOut });
      if (label != null && label !== rec.lab.textContent) {
        rec.old.forEach(e => e.remove());
        const prev = rec.lab;
        rec.old = [prev];
        if (p.side) rec.side = p.side;
        rec.lab = labelEl(rec, label, rec.side, false);
        prev.style.opacity = 0;
        if (p.animate) {
          anim(prev, [{ opacity: 1 }, { opacity: 0 }], { duration: 300, delay: p.delay });
          anim(rec.lab, [{ opacity: 0 }, { opacity: 1 }], { duration: 400, delay: p.delay + p.duration - 300 });
        }
      }
    }

    function clearFinish(opt) {
      const p = Object.assign({ animate: false, delay: 0 }, opt);
      pruneFins();
      for (const rec of fins) {
        rec.cleared = true;
        if (p.animate) { rec.g.style.opacity = 0; anim(rec.g, [{ opacity: 1 }, { opacity: 0 }], { duration: 300, delay: p.delay }); }
      }
      if (!p.animate) pruneFins();
      cur = null;
    }

    // ---- replay ----
    function fill(opt) {
      const p = Object.assign({ duration: 6000, delay: 0, ease: EASE.linear }, opt);
      const span = o.domain[1] - o.domain[0];
      for (const rec of items.values()) {
        if (rec.dead) continue;
        const a = ((rec.it.start - o.domain[0]) / span) * p.duration, d = Math.max(((rec.it.end - rec.it.start) / span) * p.duration, 16);
        rec.rect.style.transform = "";
        anim(rec.rect, [{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }], { duration: d, delay: p.delay + a, easing: p.ease });
      }
    }

    function seek(prog) {
      const span = o.domain[1] - o.domain[0], t = o.domain[0] + prog * span;
      for (const rec of items.values()) {
        if (rec.dead) continue;
        const f = Math.min(1, Math.max(0, (t - rec.it.start) / Math.max(rec.it.end - rec.it.start, 1e-9)));
        rec.rect.style.transform = f >= 1 ? "" : `scaleX(${r2(f * 1000) / 1000})`;
      }
    }

    return {
      scale: S, root, set, showLanes, finish, moveFinish, clearFinish, fill, seek,
      laneTop, box, get shown() { return shown; },
      destroy() { root.remove(); },
    };
  }

  window.Lanes = { create, scale };
})();
