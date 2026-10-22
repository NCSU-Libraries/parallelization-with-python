#!/usr/bin/env python3
"""Wire the animation pages into the deck, and check that the deck drives them.

For every animation slide in site/slides/index.qmd (listed in SLIDES below), this opens the page in headless Chrome,
reads its title, beats and per-beat text alternatives from window.__anim, and rewrites the slide: the title, the
background iframe, one empty fragment per beat after 0, and a visually hidden text alternative. Run it after adding
or changing an animation, then render.

    uv run --with playwright python -I tools/wire_deck.py           # rewrite the slides
    uv run --with playwright python -I tools/wire_deck.py --check   # after a render: step every slide in site/_site

--check serves the rendered site, opens each animation slide, steps through its fragments forward and back, and
reports any slide whose iframe beat doesn't follow.
"""
import re
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DECK = ROOT / "site/slides/index.qmd"
ANIM = ROOT / "site/slides/anim"
SITE = ROOT / "site/_site"

# slide id in the deck -> animation page, in deck order
SLIDES = {
    "anim-cores": "cores.html",
    "anim-example": "example.html",
    "anim-lanes-primer": "lanes-primer.html",
    "anim-split": "split.html",
    "anim-talk": "talk.html",
    "anim-waiting": "waiting.html",
    "anim-where": "where.html",
    "anim-cpu-gpu": "cpu-gpu.html",
    "decision-map": "decision-map.html",
    "anim-processes": "processes.html",
    "anim-pool-map": "pool-map.html",
    "anim-fire": "fire.html",
    "anim-replay": "replay.html",
    "anim-scaling": "scaling.html",
    "anim-ceilings": "ceilings.html",
    "anim-overhead": "overhead.html",
    "tool-ladder": "tool-ladder.html",
}


def serve(folder, port):
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "-d", str(folder)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    return srv


def md(text):
    """Escape what pandoc would otherwise read as markup inside a [span]."""
    return re.sub(r"([\\`*\[\]<>])", r"\\\1", " ".join(str(text).split()))


def read_pages():
    srv = serve(ANIM, 8767)
    info = {}
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(channel="chrome")
            pg = b.new_page(viewport={"width": 1280, "height": 720})
            for page in SLIDES.values():
                pg.goto(f"http://localhost:8767/{page}", wait_until="networkidle")
                pg.wait_for_function("window.__anim && window.__anim.alt", timeout=15000)
                info[page] = pg.evaluate("""() => ({ beats: window.__anim.beats, alt: window.__anim.alt,
                    title: ((document.querySelector('.title') || {}).textContent || document.title).trim() })""")
            b.close()
    finally:
        srv.terminate()
    return info


def wire():
    missing = [p for p in SLIDES.values() if not (ANIM / p).exists()]
    if missing:
        sys.exit(f"missing animation pages: {missing}")
    info = read_pages()
    lines = DECK.read_text(encoding="utf-8").split("\n")
    out, i = [], 0
    while i < len(lines):
        m = re.match(r"^## .*\{#([\w-]+)[ }]", lines[i])
        if not (m and m.group(1) in SLIDES):
            out.append(lines[i]); i += 1; continue
        sid, page = m.group(1), SLIDES[m.group(1)]
        d = info[page]
        j = i + 1                                         # the slide runs to the next heading
        while j < len(lines) and not re.match(r"^#{1,2} |^\{\{< include ", lines[j]):   # an include belongs to the deck
            j += 1
        block = [f'## {md(d["title"])} {{#{sid} data-state="anim-slide" background-iframe="anim/{page}" background-interactive="true"}}', ""]
        for _ in range(d["beats"]):
            block += ["::: {.fragment}", ":::", ""]
        block += [f'[Text alternative: {md(" ".join(d["alt"]))}]{{.visually-hidden}}', ""]
        out += block
        print(f"  {sid:20} {page:18} {d['beats']} fragments  {d['title']}")
        i = j
    DECK.write_text("\n".join(out), encoding="utf-8")


def check():
    srv = serve(SITE, 8768)
    bad = 0
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(channel="chrome")
            pg = b.new_page(viewport={"width": 1600, "height": 900})
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            for sid, page in SLIDES.items():
                pg.goto(f"http://localhost:8768/slides/index.html#/{sid}", wait_until="networkidle")
                pg.wait_for_function("window.Reveal && Reveal.isReady()", timeout=15000)
                pg.evaluate(f"Reveal.slide(...Object.values(Reveal.getIndices(document.getElementById('{sid}'))))")
                frame_beat = f"""() => {{
                    const s = Reveal.getCurrentSlide(), f = Reveal.getSlideBackground(s).querySelector('iframe');
                    const a = f && f.contentWindow && f.contentWindow.__anim; return a ? a.beat : null; }}"""
                pg.wait_for_function(f"({frame_beat})() === 0", timeout=15000)
                beats = pg.evaluate(f"""() => document.getElementById('{sid}').querySelectorAll('.fragment').length""")
                seen = []
                for _ in range(beats):
                    pg.evaluate("Reveal.next()"); pg.wait_for_timeout(250)
                    seen.append(pg.evaluate(f"({frame_beat})()"))
                for _ in range(beats):
                    pg.evaluate("Reveal.prev()"); pg.wait_for_timeout(150)
                back = pg.evaluate(f"({frame_beat})()")
                ok = seen == list(range(1, beats + 1)) and back == 0
                bad += not ok
                print(f"  {'ok ' if ok else 'BAD'} {sid:20} forward {seen} back to {back}")
            if errors:
                print("page errors:", *errors[:5], sep="\n  ")
            b.close()
    finally:
        srv.terminate()
    sys.exit(1 if bad else 0)


check() if "--check" in sys.argv else wire()
