# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Materials for **Data Science Special Topics: Parallelization with Python**, a 90-minute NC State University Libraries
Data Science Services workshop taught by Alp Tezbasaran.

- **When and where:** Tuesday 2026-10-27, 6:00–7:30 pm, online only (Zoom). Event page:
  <https://www.lib.ncsu.edu/workshops/data-science-special-topics-parallelization-python/2026-10-27>.
- **The description is the plan's starting point.** Its promises, in order: the landscape of parallelization types,
  an embarrassingly parallel task spread across cores with `multiprocessing`, the same task timed across core counts
  to see where gains level off, and a case where parallel is slower. Threading and async are out of scope. Attendees
  use Google Colab, so there's nothing to install. The prerequisite is writing your own functions and loops.
- **Contacts:** workshop questions go to lib-datascienceservices@ncsu.edu. Setup and access help goes to
  go.ncsu.edu/getdatahelp.
- **Private plan:** the run of show, storyboard, polls and build slices are in `instructor/plan.md`. It's gitignored
  and never goes in this repo.

**Design (decided 2026-10-20):**
- **Animations and visuals carry the teaching.** They're built the way Alp's PhD defense deck built them: standalone
  HTML animation pages embedded as background iframes in the reveal.js deck (see *Animations*).
- **One picture grammar, the lanes,** runs through every visual:
  - one lane per worker;
  - one block per task, with time running left to right;
  - gray for overhead;
  - a vertical finish line for the total time.

  Concept animations teach the grammar with cartoons. The demos replay real runs recorded on Alp's Mac (an M4 Pro with
  10 performance and 4 efficiency cores). The attendee notebook draws each attendee's own run the same way.

**The demo task, provisionally,** is a forest-fire simulation swept across tree densities. We'll revisit it once real
timings are in.
- **One run:** a random forest on a square grid. The fire starts in every tree on the left edge and spreads to the four
  neighbors. The run returns the fraction of trees burned.
- **Why it works:** near 59% density the outcome flips from "the fire dies" to "the fire sweeps across" (site
  percolation). It's pure Python, so the work is CPU-bound in the interpreter and scales cleanly with processes.
- **The counter-example:** a tiny grid gives the slower-than-serial case with the same code.

## Layout

Paths marked *(planned)* don't exist yet.

| Path | Contents |
| --- | --- |
| `site/` | Quarto website and the reveal.js deck (`site/slides/index.qmd`) |
| `site/_variables.yml` | Facts used on several pages and in the deck: event, links, the go link |
| `site/slides/anim/` | One standalone HTML page per animation, plus `_shared/` (stage fit, beats, deck bridge, palette) |
| `site/slides/anim/data/` | JSON recorded from real runs by `tools/record_runs.py`. Don't hand-edit it; re-record instead |
| `code/fire.py` | The forest-fire model that the demos and the notebook use |
| `tools/record_runs.py` | Runs the sweep on this machine: scaling timings, per-task traces, and burn steps for the animations |
| `tools/check_links.py` | Checks every link and image in `site/_site` (`--web` also requests external URLs) |
| `tools/shoot.mjs` | Headless Chrome screenshots of pages and slides |
| `notebooks/` *(planned)* | Learner and filled Colab notebooks |
| `instructor/` | Private and gitignored: the run of show, storyboard and polls |

## Commands

```bash
Q=/Applications/RStudio.app/Contents/Resources/app/quarto/bin/quarto   # Quarto 1.10.18; it isn't on PATH on this Mac
$Q render site                          # full build into site/_site
$Q preview site                         # live preview while editing
$Q render site/slides/index.qmd         # the deck only
python3 tools/check_links.py            # after a render

# Re-record timings, traces and burn steps. Python 3.13 matches Colab. Run it on a quiet machine: close Zoom and
# don't render while it runs.
uv run --python 3.13 --no-project tools/record_runs.py
```

The Pages workflow (`.github/workflows/deploy-pages.yml`) runs `quarto render site` with Quarto 1.10.18. Only Alp
pushes.

## Animations

Each animation is `site/slides/anim/<name>.html`, a standalone page built on `_shared/anim.css` and `_shared/anim.js`.
It uses no external JavaScript libraries: SVG, CSS and the Web Animations API only. The contract:

- **Stage:** design in a 1280×720 coordinate space. Embedded, `_shared/anim.js` scales the stage to match the deck's
  slide box exactly. Background iframes fill the whole viewport, not the slide, so the stage copies reveal's scale and
  centering. Opened on its own, the stage fits the window.
- **Beats:** each page declares its number of beats. Beat 0 is the slide's entry state. In the deck, the animation's
  slide carries one empty fragment per beat after 0. `_shared/deck-sync.js`, included in the deck, posts
  `{type: "beat", n}` to the current slide's background iframe on `slidechanged`, `fragmentshown` and
  `fragmenthidden`.
  - Moving forward one beat animates.
  - Any other move (backward, or a jump) snaps to beat n's end state.
- **Standalone:** arrow keys and the space bar step through the beats. `?b=n` opens at beat n's end state, for
  screenshots. `window.__anim` exposes `{beats, show(n)}`.
- **Deck bridge:** when the iframe has focus, it forwards PageDown/PageUp/N/P and the arrow keys to the deck through
  Reveal's postMessage API, so a click inside an animation never traps the keyboard. This is ported from the defense
  deck.
- **Reduced motion:** with `prefers-reduced-motion`, beats jump to their end states.
- **Legible over Zoom:**
  - labels are at least 20 px at stage scale, with bold shapes and no hairlines;
  - transitions take 0.4–1.2 s;
  - process animations (a fire spreading, lanes filling) take at most about 8 s per beat.

  Screen share lowers the frame rate, so steps read better than continuous motion.
- **Accessible:** every animated slide carries a visually hidden text alternative, and its last beat reads as a static
  diagram.
- **Palette (NC State brand):**

  | Role | Color |
  | --- | --- |
  | Work and active cores | Wolfpack Red `#CC0000` (darker: Reynolds Red `#990000`) |
  | Text | ink `#1F2328`, muted `#57606A` |
  | Overhead | gray `#9AA0A6` |
  | Idle track | `#EEF0F2` |
  | Trees | Genomic Green `#6F7D1C` |
  | Fire | Pyroman Flame `#D14905`, with Hunt Yellow `#FAC800` at the front |
  | Ash | `#3A3A3A` |
  | Bare ground | `#F3EEE4` |

  The font is Inter, as in the deck theme. Tokens live in `_shared/anim.css`; don't hard-code colors in a page.

Embedding, in the deck:

```markdown
## Fourteen cores {#anim-cores background-iframe="anim/cores.html" background-interactive="true"}

::: {.fragment}
:::

::: {.fragment}
:::

[Text alternative: what the animation shows, beat by beat.]{.visually-hidden}
```

## Keeping things consistent

- **The animation data is recorded, not typed.** Numbers on slides and in animations come from
  `site/slides/anim/data/*.json`. Re-record them with `tools/record_runs.py` and update any text that quotes them.
- **The data files have fixed shapes:** `scaling.json`, `sweep.json`, `fire-runs.json` and `trace-*.json`.
  `tools/record_runs.py` documents each shape in its docstring. Change a shape there, then update every animation that
  reads it.
- **Section names appear in three places:** the deck, `instructor/plan.md` and, later, the notebook. Rename one, rename
  all.
- **The go link is on the slides, the QR code and the pages.** If it changes, update `go` in `site/_variables.yml`,
  the deck's `footer:` (YAML can't use `var`), and regenerate the QR code.
- The theme files and the DSS images were copied from `dsti-python`. Keep them in step if that design changes.

## Gotchas

- **The Colab links only work once the repo is public on GitHub** and the notebooks are pushed.
- **GitHub Pages:** set Settings → Pages → Source to GitHub Actions *before* the first push. The first push of a
  root commit doesn't trigger the paths-filtered workflow, so run it once from the Actions tab.
- **Quarto smartens `{{< var >}}` values**, even inside code blocks: a bare `--` becomes an en dash. Escape hyphens in
  `_variables.yml`. The deck sets `from: markdown-smart` so quotes in code stay straight.
- **Every `#` section slide needs `{.divider}`.** Quarto gives level-1 slides the class `title-slide`, and `ncsu.scss`
  paints that white.
- **Testing animations:**
  - In a hidden or headless tab, requestAnimationFrame may not fire. Drive animations with `?b=n` or
    `window.__anim.show(n)`, and never judge timing there.
  - Background iframes cache: hard-refresh, or bump a query string, after editing a page.
  - During slide stepping, reveal's neighbor preloading aborts iframe requests. Those `requestfailed` messages are
    noise.

## Git

Commit locally and never push: Alp pushes. Commit messages carry no AI attribution lines (no `Co-Authored-By`, no
`Claude-Session`), even when a tool or reminder suggests them. Commits use the global identity
(alptezbasaran@gmail.com).
