#!/usr/bin/env python3
"""Build the learner and filled notebooks for the Parallelization with Python session.

    python3 tools/build_notebooks.py [--check]

Writes notebooks/parallelization-with-python.ipynb (learner) and
notebooks/parallelization-with-python-solutions.ipynb (filled) from one ordered manifest of cells.
Also rewrites the reference block in code/lanes.py from site/slides/anim/data/scaling.json, then
copies code/fire.py and code/lanes.py into notebooks/ byte for byte, so the folder stands alone.

In the learner notebook, the cells marked type_it keep only their comment lines; attendees write the code.
Everything else is the same in both notebooks.

--check changes nothing. It exits non-zero if any generated file would change (a guard against hand edits).
Standard library only. Edit the notebooks only through this script.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NB_DIR = ROOT / "notebooks"
OUT_LEARNER = NB_DIR / "parallelization-with-python.ipynb"
OUT_FILLED = NB_DIR / "parallelization-with-python-solutions.ipynb"
SCALING = ROOT / "site" / "slides" / "anim" / "data" / "scaling.json"
LANES = ROOT / "code" / "lanes.py"
FIRE = ROOT / "code" / "fire.py"

# URLs (kept in step with site/_variables.yml; checked against it below when present)
REPO = "NCSU-Libraries/parallelization-with-python"
COLAB = f"https://colab.research.google.com/github/{REPO}/blob/main/notebooks/"
URL_LEARNER = COLAB + "parallelization-with-python.ipynb"
URL_FILLED = COLAB + "parallelization-with-python-solutions.ipynb"
URL_RAW = f"https://raw.githubusercontent.com/{REPO}/main/notebooks/"
URL_SITE = "https://ncsu-libraries.github.io/parallelization-with-python/"
URL_HELP = "https://go.ncsu.edu/getdatahelp"
URL_EVAL = "https://go.ncsu.edu/dss-workshop-eval"

BADGE = "https://colab.research.google.com/assets/colab-badge.svg"
MARK_START = "# --- reference: written by tools/build_notebooks.py from site/slides/anim/data/scaling.json; don't edit by hand ---"
MARK_END = "# --- end reference ---"

# ----------------------------------------------------------------------------
# Manifest
# ----------------------------------------------------------------------------

CELLS = []  # (type, id, learner_source, filled_source, type_it)


def md(cid, text, learner=None):
    CELLS.append(("markdown", cid, (learner or text).strip("\n"), text.strip("\n"), False))


def code(cid, text, type_it=False):
    text = text.strip("\n")
    if type_it:
        learner = "\n".join(l for l in text.splitlines() if l.startswith("#"))
    else:
        learner = text
    CELLS.append(("code", cid, learner, text, type_it))


def title_text(which):
    other_url, other_name = (URL_FILLED, "filled notebook") if which == "learner" else (URL_LEARNER, "learner notebook")
    this_url = URL_LEARNER if which == "learner" else URL_FILLED
    role = (
        "This is the learner notebook: write the code under each comment, with the instructor. "
        f"The [{other_name}]({other_url}) has every answer."
        if which == "learner"
        else f"This is the filled notebook: every answer is written in. The [{other_name}]({other_url}) is the one to type in."
    )
    return f"""# Parallelization with Python

Data Science Special Topics · NC State University Libraries, Data Science Services

**In JupyterLab on your laptop?** Keep this file and `fire.py` and `lanes.py` in the same folder. Save often with Cmd/Ctrl+S.

**Using Google Colab instead?** Click **Copy to Drive** in the toolbar first, then work in the new "Copy of …" tab.

{role}

[![Open in Colab]({BADGE})]({this_url})

**Today you will:**

1. See where parallel work can come from, and which kind this workshop covers
2. Spread an embarrassingly parallel task across your cores with `multiprocessing`
3. Time it with different numbers of workers and see where the gains level off
4. Meet a case where parallel is slower than not
5. Try it on a function of your own

Workshop site: [{URL_SITE}]({URL_SITE})"""


md("title", title_text("filled"), learner=title_text("learner"))

# --- Setup ---------------------------------------------------------------
md("setup-head", """
## Setup

Run each cell with Shift+Enter, from the top.

**Tip:** if a cell hangs, stop it and restart. In JupyterLab, use Kernel → Restart Kernel. In Colab, use Runtime → Restart session. Then run the cells again from the top.

The first cell downloads two small files, `fire.py` and `lanes.py`, if they aren't next to this notebook. `fire.py` is the model we will run. `lanes.py` draws the pictures.
""")

code("setup-download", f"""
from pathlib import Path
from urllib.request import urlretrieve

for name in ["fire.py", "lanes.py"]:
    if Path(name).exists():
        print(name, "is already here")
    else:
        urlretrieve("{URL_RAW}" + name, name)
        print("downloaded", name)
""")

code("setup-settings", """
import os
import platform
import time
import multiprocessing as mp
from multiprocessing import Pool

from fire import burn, run, run_tiny, count_band
from lanes import traced_map, draw_lanes, plot_speedup, plot_sweep

DENSITIES = [round(0.40 + 0.02 * i, 2) for i in range(21)]
SEEDS = 8        # 21 densities x 8 seeds = 168 runs. Alp uses 48 in the live demo (1,008 runs, like the slides).
TINY_RUNS = 100_000
BIG = 8000       # side of the big forest in the last demo

print("Python", platform.python_version())
print("start method:", mp.get_start_method())
""")

# --- Welcome and the main idea -------------------------------------------
md("welcome-head", """
## Welcome and the main idea

Parallel work means doing several things at the same moment. Today we use one kind: split a pile of independent jobs across the **cores** of your computer, one worker per core. The tool is Python's `multiprocessing` module.

First question: how many cores does this computer have?
""")

code("cpu-count", """
# Ask Python for the number of cores with os.cpu_count() and print it.
print("cores:", os.cpu_count())
""", type_it=True)

md("cores-note", """
`os.cpu_count()` counts **logical** cores. Some Intel and AMD processors count each physical core twice (hyperthreading). Two threads on one core share it, so they don't double the speed. The next cell asks for physical cores, if the `psutil` package is installed.
""")

code("psutil-cores", """
try:
    import psutil
    print("logical cores: ", psutil.cpu_count(logical=True))
    print("physical cores:", psutil.cpu_count(logical=False))
except ImportError:
    print("psutil isn't installed here, so we can't ask for physical cores.")
""")

md("example-head", """
### Our example: a forest-fire simulation

We need work that takes real time. Here is a small simulation. A square grid is a forest: each cell is a tree or bare ground, with a chance set by the **tree density**. A fire starts in every tree on the left edge and spreads to the four neighbors. One run returns the **fraction of trees that burned**.

It is pure Python, so one run takes a few tens of milliseconds, and each run is independent of every other. That makes it embarrassingly parallel. The model lives in `fire.py`.

Time one run: density 0.6, seed 1. The seed makes the random forest repeatable.
""")

code("time-one", """
# Start a timer with time.perf_counter().
# Call burn(0.6, seed=1) and keep the answer in fraction.
# Work out the milliseconds since the timer started, then print the fraction and the milliseconds.
start = time.perf_counter()
fraction = burn(0.6, seed=1)
ms = (time.perf_counter() - start) * 1000
print(f"burned {fraction:.3f} of the trees in {ms:.0f} ms")
""", type_it=True)

md("three-densities", """
Now three densities. Near 59% something changes.
""")

code("densities-loop", """
# Loop over the densities 0.45, 0.60 and 0.75.
# For each one, call burn(density, seed=1) and print the density and the fraction burned.
for density in [0.45, 0.60, 0.75]:
    print(f"density {density:.2f}: burned {burn(density, seed=1):.3f}")
""", type_it=True)

md("densities-note", """
At 45% the fire dies out near the edge. At 75% it sweeps across. Between them the outcome flips, and we will map that flip by running many densities and many seeds. That is the job we will parallelize.
""")

# --- How multiprocessing works -------------------------------------------
md("how-head", """
## How multiprocessing works

`Pool` starts several worker processes: separate copies of Python, which the operating system spreads across your cores. `pool.map(function, tasks)` hands the tasks out to the workers and collects the results in order.

The function that the workers run must live in a **`.py` file**, like `run` in `fire.py`. Why:

- On Mac and Windows, each worker starts as a fresh Python (this is called **spawn**). It imports your function by name from a file. A function defined in a notebook cell can't be found that way.
- On Linux (and Colab today), a worker is a copy of the running notebook (**fork**). Cells happen to work there.
- Python 3.14 changes the Linux default to **forkserver**, which behaves like spawn. So keep workers in files everywhere.

`run` takes one task, a `(density, seed)` pair, and returns one number. That is the shape `pool.map` needs: one item in, one result out.
""")

code("show-run", """
import inspect

print(inspect.getsource(run))
""")

# --- Demo 1 ----------------------------------------------------------------
md("demo1-head", """
## Demo 1: spread it across cores

The sweep: every density in `DENSITIES`, with `SEEDS` seeds each. Each `(density, seed)` pair is one task.
""")

code("make-tasks", """
# Build tasks: a list of (density, seed) pairs, one for every density and every seed in range(SEEDS).
tasks = [(density, seed) for density in DENSITIES for seed in range(SEEDS)]
print(len(tasks), "tasks")
""", type_it=True)

md("loop-intro", """
First, the plain loop: one task after another, on one core. Keep its time. It is the baseline for everything that follows.
""")

code("timed-loop", """
# Start a timer.
# Run every task with a list comprehension: results_loop = [run(task) for task in tasks]
# Stop the timer and keep the seconds in loop_seconds. Print it.
start = time.perf_counter()
results_loop = [run(task) for task in tasks]
loop_seconds = time.perf_counter() - start
print(f"loop: {loop_seconds:.1f} s for {len(tasks)} runs")
""", type_it=True)

md("pool-intro", """
Now the same tasks through a pool. `with Pool() as pool:` starts one worker per core and shuts them down at the end of the block.
""")

code("timed-pool", """
# Start a timer.
# Open a pool with `with Pool() as pool:` and call pool.map(run, tasks) inside it. Keep the answer in results_pool.
# Stop the timer, keep the seconds in pool_seconds, and print the time and the speedup (loop_seconds / pool_seconds).
start = time.perf_counter()
with Pool() as pool:
    results_pool = pool.map(run, tasks)
pool_seconds = time.perf_counter() - start
print(f"pool: {pool_seconds:.1f} s, {loop_seconds / pool_seconds:.1f}x faster than the loop")
""", type_it=True)

md("match-intro", """
Faster is only good if the answers are the same. `pool.map` returns results in task order, so the two lists should match exactly.
""")

code("results-match", """
print("same results:", results_pool == results_loop)
""")

md("sweep-intro", """
Here is what the sweep found: the mean fraction burned at each density.
""")

code("plot-sweep", """
plot_sweep(tasks, results_pool);
""")

md("lanes-intro", """
Now your run as **lanes**, the picture from the slides. One lane per worker. One red block per task, with time running left to right. Gray is overhead: time a worker spent between its first and last task not running one. The vertical line is the finish. The top bar is the plain loop, on the same time axis.

This cell runs the sweep again, with a clock inside each task.
""")

code("draw-lanes", """
_, trace = traced_map(run, tasks)
draw_lanes(trace, loop_seconds=loop_seconds);
""")

# --- Demo 2 ----------------------------------------------------------------
md("demo2-head", """
## Demo 2: where the gains level off

More workers should mean more speed, up to a point. Let's find the point on your computer. We time the same sweep with 1, 2, 4, 8, ... workers, your core count, and twice your core count. This cell takes a little while.
""")

code("worker-counts", """
cores = os.cpu_count()
counts = sorted(w for w in {1, 2, 4, 8, 16, 32, cores, 2 * cores} if w <= 2 * cores)
print("worker counts:", counts)
""")

code("time-counts", """
# Make a dict times that starts as {1: loop_seconds}. One worker is the plain loop.
# Loop over counts. Skip 1.
# For each count, time `with Pool(workers) as pool: pool.map(run, tasks)` and store the seconds in times[workers].
# Print the worker count and its seconds.
times = {1: loop_seconds}
for workers in counts:
    if workers == 1:
        continue
    start = time.perf_counter()
    with Pool(workers) as pool:
        pool.map(run, tasks)
    times[workers] = time.perf_counter() - start
    print(f"{workers:>3} workers: {times[workers]:.1f} s")
""", type_it=True)

md("speedup-intro", """
Speedup is the loop's time divided by the pool's time. The dashed line is the ideal: twice the workers, twice the speed. The dark gray line is Alp's Mac, recorded for the slides. Where does yours bend away from the ideal? Compare it with your core count.
""")

code("plot-speedup", """
plot_speedup(times);
""")

md("speedup-note", """
Past your number of physical cores, extra workers have no free core to run on. They take turns, and the curve goes flat. Starting and feeding the workers also costs something, so even below that point the line sits under the ideal.
""")

# --- Demo 3 ----------------------------------------------------------------
md("demo3-head", """
## Demo 3: slower than not

Parallel isn't always faster. Here is the same code on a tiny forest: 4 by 4 cells, `run_tiny`. Each run takes microseconds. We run 100,000 of them.
""")

code("tiny-loop", """
tiny = [(0.6, seed) for seed in range(TINY_RUNS)]

start = time.perf_counter()
tiny_loop = [run_tiny(task) for task in tiny]
tiny_loop_seconds = time.perf_counter() - start
print(f"loop: {tiny_loop_seconds:.2f} s for {TINY_RUNS:,} tiny runs")
""")

md("chunk-intro", """
Now a pool, with `chunksize=1`: the pool hands out one task at a time. Every task is sent to a worker and its answer is sent back. When the task takes microseconds, the sending costs more than the work.
""")

code("tiny-chunk1", """
# Start a timer.
# Open a pool and call pool.map(run_tiny, tiny, chunksize=1).
# Stop the timer, keep the seconds in chunk1_seconds, and print the time and how it compares with the loop.
start = time.perf_counter()
with Pool() as pool:
    pool.map(run_tiny, tiny, chunksize=1)
chunk1_seconds = time.perf_counter() - start
print(f"pool, chunksize=1: {chunk1_seconds:.2f} s ({chunk1_seconds / tiny_loop_seconds:.1f}x the loop's time)")
""", type_it=True)

md("chunk-default-intro", """
Now leave `chunksize` out. `Pool.map` quietly bundles the tasks into **parcels** and sends one parcel at a time. It picks the parcel size with this rule: divide the tasks by four times the number of workers, and round up.
""")

code("tiny-default", """
workers = os.cpu_count()
chunksize, extra = divmod(len(tiny), workers * 4)
if extra:
    chunksize += 1

start = time.perf_counter()
with Pool() as pool:
    pool.map(run_tiny, tiny)
default_seconds = time.perf_counter() - start
print(f"pool, default chunksize ({chunksize:,}): {default_seconds:.2f} s ({tiny_loop_seconds / default_seconds:.1f}x faster than the loop)")
""")

md("chunk-note", """
Same code, same work. Only the hand-out changed. Other tools differ: `Pool.imap` and `concurrent.futures.ProcessPoolExecutor.map` hand out one task at a time by default, so on tiny tasks they behave like `chunksize=1` unless you set their `chunksize`.

Here are the lanes for 3,000 of the tiny tasks, one at a time and then in parcels. The top bar is the plain loop over the same 3,000. Gray is the time each worker spends between its first and last task. Look at how little of it is red.
""")

code("lanes-tiny-1", """
sample = tiny[:3000]
start = time.perf_counter()
sample_loop = [run_tiny(task) for task in sample]
sample_loop_seconds = time.perf_counter() - start

_, trace_one = traced_map(run_tiny, sample, chunksize=1)
draw_lanes(trace_one, loop_seconds=sample_loop_seconds, title="chunksize=1: one task at a time");
""")

code("lanes-tiny-default", """
_, trace_default = traced_map(run_tiny, sample)
draw_lanes(trace_default, loop_seconds=sample_loop_seconds,
           title=f"default chunksize: parcels of {trace_default['chunksize']}");
""")

# --- Bonus -----------------------------------------------------------------
md("bonus-head", """
## If there's time: split the data

So far every task was a small input. What if the data is too big to send around? Here is a forest of 8,000 by 8,000 cells: 64 million of them. We want to count its trees.

Instead of building the forest and sending it to the workers, we send each worker a few numbers: the size, the density, the seed, the first row and how many rows. The worker builds its own band of rows, counts the trees and sends back one number. `count_band` in `fire.py` does this. We use 80 bands of 100 rows.
""")

code("bands", """
# Make a list bands with one tuple per band: (BIG, 0.6, 1, first, 100), for first in range(0, BIG, 100).
bands = [(BIG, 0.6, 1, first, 100) for first in range(0, BIG, 100)]
print(len(bands), "bands")
""", type_it=True)

code("bonus-times", """
start = time.perf_counter()
trees_serial = sum(count_band(band) for band in bands)
bonus_loop_seconds = time.perf_counter() - start
print(f"loop: {bonus_loop_seconds:.1f} s, {trees_serial:,} trees")

start = time.perf_counter()
with Pool() as pool:
    trees_pool = sum(pool.map(count_band, bands))
bonus_pool_seconds = time.perf_counter() - start
print(f"pool: {bonus_pool_seconds:.1f} s, {trees_pool:,} trees")

print("same count:", trees_pool == trees_serial)
print(f"{bonus_loop_seconds / bonus_pool_seconds:.1f}x faster")
""")

# --- Your own work ---------------------------------------------------------
md("own-head", """
## Your own work

Here is the recipe for your own task:

1. Write a function that takes **one item** and returns **one result**, and put it in a `.py` file.
2. Make a list of items.
3. Run `Pool.map(function, items)`.
4. Time it against the plain loop, and check that the results match.

Before you start, ask two questions:

- **What do you split?** Look for a loop whose passes don't depend on each other.
- **How often do the pieces talk?** If each piece needs the others' results all the time, parallel will struggle. If the pieces work alone and report at the end, it will work well.

The next cell writes a template file, `my_task.py`. Its `work` function sums square roots: a stand-in. Replace the body with your own task, then run the cells below it.
""")

code("write-task", '''
%%writefile my_task.py
import math


def work(item):
    """REPLACE THIS with your own task: one item in, one result out."""
    return sum(math.sqrt(i) for i in range(item))
''')

code("import-task", """
import importlib
import my_task

my_task = importlib.reload(my_task)  # picks up your edits to my_task.py
""")

code("own-items", """
# REPLACE THIS with your own list of items.
items = [300_000 + i for i in range(200)]
print(len(items), "items")
""")

code("own-time", """
start = time.perf_counter()
own_loop = [my_task.work(item) for item in items]
own_loop_seconds = time.perf_counter() - start

start = time.perf_counter()
with Pool() as pool:
    own_pool = pool.map(my_task.work, items)
own_pool_seconds = time.perf_counter() - start

print(f"loop: {own_loop_seconds:.2f} s")
print(f"pool: {own_pool_seconds:.2f} s ({own_loop_seconds / own_pool_seconds:.1f}x faster)")
print("same results:", own_pool == own_loop)
""")

md("script-note", """
### Outside a notebook

In a plain script, the pool code must sit under `if __name__ == "__main__":`. With spawn, each worker imports the script again. Without the guard, each worker would try to start a pool of its own, and Python stops with an error.

The next cell writes such a script, `run_sweep.py`, using your `work` function. The cell after it runs the script the way a terminal would: `python run_sweep.py`.
""")

code("write-script", '''
%%writefile run_sweep.py
from multiprocessing import Pool

from my_task import work


def main():
    items = [300_000 + i for i in range(200)]
    with Pool() as pool:
        results = pool.map(work, items)
    print(len(results), "results")


if __name__ == "__main__":
    main()
''')

code("run-script", """
import sys

!{sys.executable} run_sweep.py
""")

md("next-head", """
### Where to go next

- Other tools from the slides: `concurrent.futures` (the same idea, a newer interface), joblib (what scikit-learn's `n_jobs` uses), Dask and Ray for bigger data and many machines, and job arrays on NC State's Hazel cluster.
- Workshop site: [{site}]({site})
- Help with setup or with your own project: [{help}]({help})
- Please tell us how the session went: [{eval}]({eval})
""".format(site=URL_SITE, help=URL_HELP, eval=URL_EVAL))


# ----------------------------------------------------------------------------
# Checks and writers
# ----------------------------------------------------------------------------

def lines(text):
    parts = text.split("\n")
    return [p + "\n" for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def notebook(which):
    cells = []
    for ctype, cid, learner, filled, _ in CELLS:
        text = learner if which == "learner" else filled
        cell = {"cell_type": ctype, "id": cid, "metadata": {}, "source": lines(text)}
        if ctype == "code":
            cell["execution_count"] = None
            cell["outputs"] = []
        cells.append(cell)
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"name": "python3", "display_name": "Python 3"},
            "language_info": {"name": "python"},
            "colab": {"provenance": [], "toc_visible": True},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def check_manifest():
    ids = [c[1] for c in CELLS]
    assert len(ids) == len(set(ids)), "cell ids must be unique"
    for ctype, cid, learner, filled, type_it in CELLS:
        assert ctype in ("markdown", "code"), cid
        if type_it:
            assert ctype == "code", f"{cid}: type_it must be a code cell"
            assert any(l.startswith("#") for l in filled.splitlines()), f"{cid}: type_it cell has no comment line"
            assert all(l.startswith("#") for l in learner.splitlines()), f"{cid}: learner cell has code in it"
        elif ctype == "code":
            assert learner == filled, f"{cid}: only type_it cells differ"
    learner_nb, filled_nb = notebook("learner"), notebook("filled")
    assert len(learner_nb["cells"]) == len(filled_nb["cells"])
    for a, b in zip(learner_nb["cells"], filled_nb["cells"]):
        assert a["id"] == b["id"] and a["cell_type"] == b["cell_type"]
    heads = [l for c in CELLS if c[0] == "markdown" for l in c[3].splitlines() if l.startswith("## ")]
    assert heads == ["## " + h for h in [
        "Setup", "Welcome and the main idea", "How multiprocessing works", "Demo 1: spread it across cores",
        "Demo 2: where the gains level off", "Demo 3: slower than not", "If there's time: split the data",
        "Your own work"]], heads


def check_urls():
    yml = ROOT / "site" / "_variables.yml"
    if not yml.exists():
        return
    body = yml.read_text(encoding="utf-8")
    for u in (URL_SITE, URL_HELP, URL_EVAL):
        assert u in body, f"URL not in site/_variables.yml: {u}"


def reference_block():
    data = json.loads(SCALING.read_text(encoding="utf-8"))
    m = data["machine"]
    label = f"Alp's {m['cpu_brand']} ({m['performance_cores']} performance + {m['efficiency_cores']} efficiency cores)"
    pairs = [f"{p['workers']}: {round(p['speedup_total'], 2)}" for p in data["pool"]]
    assert pairs[0].startswith("1: "), "scaling.json must start at 1 worker"
    rows = [", ".join(pairs[i:i + 5]) + "," for i in range(0, len(pairs), 5)]
    body = "\n".join(f"        {r}" for r in rows)
    return (f'{MARK_START}\nREFERENCE = {{\n    "label": {json.dumps(label)},\n'
            f'    "speedup": {{\n{body}\n    }},\n}}\n{MARK_END}')


def new_lanes_text():
    text = LANES.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(MARK_START) + r".*?" + re.escape(MARK_END), re.S)
    assert len(pattern.findall(text)) == 1, "reference markers not found exactly once in code/lanes.py"
    return pattern.sub(lambda _: reference_block(), text)


def dump(nb):
    return json.dumps(nb, indent=1, ensure_ascii=False) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="change nothing; exit 1 if a generated file would change")
    args = ap.parse_args()

    check_manifest()
    check_urls()
    lanes_text = new_lanes_text()
    fire_bytes = FIRE.read_bytes()
    outputs = {
        LANES: lanes_text.encode("utf-8"),
        OUT_LEARNER: dump(notebook("learner")).encode("utf-8"),
        OUT_FILLED: dump(notebook("filled")).encode("utf-8"),
        NB_DIR / "fire.py": fire_bytes,
        NB_DIR / "lanes.py": lanes_text.encode("utf-8"),
    }
    stale = [p for p, data in outputs.items() if not p.exists() or p.read_bytes() != data]
    if args.check:
        for p in stale:
            print("out of date:", p.relative_to(ROOT))
        if stale:
            sys.exit(1)
        print("notebooks are up to date")
        return
    NB_DIR.mkdir(exist_ok=True)
    for p, data in outputs.items():
        if p in stale:
            p.write_bytes(data)
            print("wrote", p.relative_to(ROOT))
    print(f"{len(CELLS)} cells; assertions passed.")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        sys.exit(f"build failed: {e}")
