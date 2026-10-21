#!/usr/bin/env python3
"""Find overlaps in the rendered deck, at every slide and every fragment, in a few window sizes.

It reports two things:
  - content under the deck's chrome: text or a drawing that runs into the footer, the logo, the slide number or the
    menu button, and chrome that runs into other chrome (a long footer under the logo);
  - text over text: two pieces of text whose boxes overlap.

Animation slides are read inside their background iframe (same origin). Each slide's fragments are visited from the
last to the first, so an animation snaps to each state instead of playing.

    uv run --with playwright python -I tools/check_overlaps.py                 # after quarto render site
    uv run --with playwright python -I tools/check_overlaps.py --size 1000x594 # one window size
"""
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site/_site"
SIZES = [(1000, 594), (1440, 900), (1920, 1080)]   # a laptop browser window, a 16:10 screen, full HD
PORT = 8769
MIN_AREA = 4                                      # px²: smaller touches are anti-aliasing, not overlaps

# Boxes of everything visible under `root`, in this document's viewport pixels.
COLLECT = r"""
(rootSel) => {
  const root = typeof rootSel === "string" ? document.querySelector(rootSel) : rootSel;
  if (!root) return [];
  const SVG = "http://www.w3.org/2000/svg";
  const seen = new Map();
  const vis = el => {                              // effective opacity, 0 when hidden
    let o = 1;
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      if (!seen.has(e)) { const cs = getComputedStyle(e); seen.set(e, cs.display === "none" || cs.visibility === "hidden" ? 0 : +cs.opacity); }
      o *= seen.get(e);
      if (o < 0.05) return 0;
    }
    return o;
  };
  const name = el => {
    const t = (el.getAttribute && el.getAttribute("class")) || "";
    return el.tagName.toLowerCase() + (el.id ? "#" + el.id : "") + (t ? "." + String(t).trim().split(/\s+/).join(".") : "");
  };
  const out = [];
  const push = (kind, r, el, text) => {
    if (r.width < 1 || r.height < 1) return;
    out.push({ kind, x: r.left, y: r.top, w: r.width, h: r.height, el: name(el), text: (text || "").slice(0, 48) });
  };
  // text: tight boxes per line for HTML text, the element box for SVG text
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const s = n.textContent.replace(/\s+/g, " ").trim();
    const p = n.parentElement;
    if (!s || !p || vis(p) < 0.05) continue;
    if (p.closest(".visually-hidden, .sr-only, defs, pattern, script, style")) continue;
    if (p.namespaceURI === SVG) { push("text", p.getBoundingClientRect(), p, s); continue; }
    const range = document.createRange();
    range.selectNodeContents(n);
    for (const r of range.getClientRects()) push("text", r, p, s);
  }
  // drawings: SVG shapes and images
  for (const el of root.querySelectorAll("rect, circle, ellipse, path, line, polygon, polyline, use, image, img, canvas")) {
    if (el.closest("defs, pattern, .visually-hidden, .sr-only") || vis(el) < 0.05) continue;
    push("shape", el.getBoundingClientRect(), el, "");
  }
  return out;
}
"""

# The deck's chrome: the footer's text (tight), the logo, the slide number, the menu button.
CHROME = r"""
() => {
  const out = [];
  const shown = el => { for (let e = el; e && e.nodeType === 1; e = e.parentElement) { const cs = getComputedStyle(e); if (cs.display === "none" || cs.visibility === "hidden" || +cs.opacity < 0.05) return false; } return true; };
  const add = (what, r) => { if (r && r.width >= 1 && r.height >= 1) out.push({ kind: "chrome", what, x: r.left, y: r.top, w: r.width, h: r.height }); };
  const foot = document.querySelector(".reveal .footer");
  if (foot && shown(foot)) {
    const walker = document.createTreeWalker(foot, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (!n.textContent.trim()) continue;
      const range = document.createRange(); range.selectNodeContents(n);
      for (const r of range.getClientRects()) add("footer", r);
    }
  }
  for (const [sel, what] of [[".reveal .slide-logo", "logo"], [".reveal .slide-number", "slide number"], [".reveal .slide-menu-button", "menu button"]]) {
    const el = document.querySelector(sel);
    if (el && shown(el)) add(what, el.getBoundingClientRect());
  }
  return out;
}
"""


def inter(a, b):
    w = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
    h = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
    return w * h if w > 0 and h > 0 else 0


def check(page, sid, beat, size):
    found = []
    chrome = page.evaluate(CHROME)
    slide_info = page.evaluate("""() => { const s = Reveal.getCurrentSlide();
        return { anim: (s.getAttribute('data-background-iframe') || ''), title: (s.querySelector('h1, h2') || {}).textContent || '' }; }""")
    if slide_info["anim"]:
        frame = next((f for f in page.frames if f.url.split("?")[0].endswith(slide_info["anim"])), None)
        content = frame.evaluate(COLLECT, "#stage") if frame else []
        box = frame.evaluate("() => { const r = document.getElementById('stage').getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; }") if frame else None
    else:
        content = page.evaluate(COLLECT, page.evaluate_handle("Reveal.getCurrentSlide()"))
        box = page.evaluate("() => { const r = Reveal.getCurrentSlide().getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; }")
    if box:
        for c in content:
            if c["x"] < box["x"] - 2 or c["y"] < box["y"] - 2 or c["x"] + c["w"] > box["x"] + box["w"] + 2 or c["y"] + c["h"] > box["y"] + box["h"] + 2:
                found.append(f"{c['kind']} {c['el']} '{c['text']}' runs off the slide")
    for c in content:
        for k in chrome:
            if inter(c, k) > MIN_AREA:
                found.append(f"{c['kind']} {c['el']} '{c['text']}' under the {k['what']}")
    for i, a in enumerate(chrome):
        for b in chrome[i + 1:]:
            if a["what"] != b["what"] and inter(a, b) > MIN_AREA:
                found.append(f"the {a['what']} under the {b['what']}")
    texts = [c for c in content if c["kind"] == "text"]
    for i, a in enumerate(texts):
        for b in texts[i + 1:]:
            ar = inter(a, b)
            union = a["w"] * a["h"] + b["w"] * b["h"] - ar
            if a["text"] == b["text"] and ar > 0.6 * union:
                continue                              # a twin drawn on top on purpose, like a red cell over its gray one
            if ar > MIN_AREA and ar > 0.15 * min(a["w"] * a["h"], b["w"] * b["h"]) and (a["text"], a["el"]) != (b["text"], b["el"]):
                found.append(f"text '{a['text']}' ({a['el']}) over text '{b['text']}' ({b['el']})")
    return sorted(set(found))


def main():
    sizes = [tuple(map(int, v.split("x"))) for v in sys.argv[sys.argv.index("--size") + 1:sys.argv.index("--size") + 2]] if "--size" in sys.argv else SIZES
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1", "-d", str(SITE)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    total = 0
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(channel="chrome")
            for (w, h) in sizes:
                pg = b.new_page(viewport={"width": w, "height": h})
                pg.goto(f"http://localhost:{PORT}/slides/index.html", wait_until="networkidle")
                pg.wait_for_function("window.Reveal && Reveal.isReady()", timeout=15000)
                slides = pg.evaluate("""() => Reveal.getSlides().map(s => { const i = Reveal.getIndices(s);
                    return { h: i.h, v: i.v || 0, id: s.id || '', frags: s.querySelectorAll('.fragment').length,
                             anim: !!s.getAttribute('data-background-iframe') }; })""")
                print(f"== {w}x{h}: {len(slides)} slides")
                for s in slides:
                    for f in range(s["frags"] - 1, -2, -1):        # last fragment first, down to none: every move snaps
                        pg.evaluate(f"Reveal.slide({s['h']}, {s['v']}, {f})")
                        beat = f + 1
                        if s["anim"]:
                            pg.wait_for_function(f"""() => {{ const sl = Reveal.getCurrentSlide();
                                const fr = Reveal.getSlideBackground(sl).querySelector('iframe');
                                const a = fr && fr.contentWindow && fr.contentWindow.__anim;
                                return a && a.beat === {beat} && !a.busy; }}""", timeout=20000)
                            pg.wait_for_timeout(120)
                        else:
                            pg.wait_for_timeout(250)
                        for line in check(pg, s["id"], beat, (w, h)):
                            total += 1
                            print(f"  slide {s['h'] + 1}{'.' + str(s['v'] + 1) if s['v'] else ''} {s['id'] or ''} beat {beat}: {line}")
                pg.close()
            b.close()
    finally:
        srv.terminate()
    print(f"{total} overlap(s)")
    sys.exit(1 if total else 0)


main()
