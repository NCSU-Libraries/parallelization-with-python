"""Lanes: time a Pool.map and draw it the way the workshop slides do.

One lane per worker, one red block per task, time running left to right. Gray is
overhead: the stretch of a lane from its first task to its last that isn't a task.
A vertical line marks the total time. Standard library plus matplotlib.

    traced_map(fn, tasks)       Pool.map that also records when each task ran
    draw_lanes(trace)           draw those records as lanes
    plot_speedup(times)         speedup against worker count, with Alp's curve
    plot_sweep(tasks, results)  burned fraction against tree density
"""

import os
import time
from multiprocessing import Pool

import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

RED = "#CC0000"       # work
INK = "#1F2328"       # text, finish lines
MUTED = "#57606A"     # secondary text
OVERHEAD = "#9AA0A6"  # gray: overhead
IDLE = "#EEF0F2"      # idle track
FLAME = "#D14905"     # fire
LINE = "#D5DADF"      # light rules

# --- reference: written by tools/build_notebooks.py from site/slides/anim/data/scaling.json; don't edit by hand ---
REFERENCE = {
    "label": "Alp's Apple M4 Pro (10 performance + 4 efficiency cores)",
    "speedup": {
        1: 1.0, 2: 1.9, 4: 3.67, 6: 5.41, 8: 7.14,
        10: 8.77, 12: 9.43, 14: 9.82, 16: 9.93,
    },
}
# --- end reference ---

FONT = 12


class _Timed:
    """Wrap a function so each call also returns (result, pid, start, end).

    It is a top-level class so every start method (spawn, fork, forkserver) can pickle it.
    """

    def __init__(self, fn):
        self.fn = fn

    def __call__(self, task):
        start = time.perf_counter()
        result = self.fn(task)
        end = time.perf_counter()
        return result, os.getpid(), start, end


def _nothing(x):
    return x


def traced_map(fn, tasks, workers=None, chunksize=None):
    """Run Pool(workers).map(fn, tasks) and record when each task ran.

    Returns (results, trace). trace is {"workers", "wall", "chunksize", "tasks"}.
    Each task record has i, worker (0, 1, ... by first appearance), pid, start and end,
    in seconds since the map began. wall is the total time of the map.
    The pool is started and warmed up before the clock starts, so wall leaves out startup.
    """
    tasks = list(tasks)
    n = workers or os.cpu_count()
    if chunksize is None:
        # The rule Pool.map uses when you don't pass chunksize.
        chunksize, extra = divmod(len(tasks), n * 4)
        if extra:
            chunksize += 1
    with Pool(n) as pool:
        pool.map(_nothing, range(n * 4), chunksize=1)  # make sure every worker is up
        t0 = time.perf_counter()
        raw = pool.map(_Timed(fn), tasks, chunksize=chunksize)
        wall = time.perf_counter() - t0

    numbers = {}
    records = []
    for i, (_, pid, start, end) in enumerate(raw):
        worker = numbers.setdefault(pid, len(numbers))
        records.append({"i": i, "worker": worker, "pid": pid, "start": start - t0, "end": end - t0})
    trace = {"workers": n, "wall": wall, "chunksize": chunksize, "tasks": records}
    return [r[0] for r in raw], trace


def _style(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(LINE)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(colors=INK, labelsize=FONT)


def _seconds(x):
    if x < 0.1:
        return f"{x * 1000:.1f} ms"
    if x < 1:
        return f"{x:.2f} s"
    return f"{x:.1f} s" if x < 100 else f"{x:.0f} s"


def draw_lanes(trace, loop_seconds=None, title=None, ax=None):
    """Draw a trace as lanes: one per worker, red blocks for tasks, gray for overhead.

    With loop_seconds, a top lane shows the plain loop as one solid bar on the same time axis.
    Returns the Axes.
    """
    n = trace["workers"]
    wall = trace["wall"]
    tasks = trace["tasks"]
    rows = n + (1 if loop_seconds is not None else 0)
    if ax is None:
        _, ax = plt.subplots(figsize=(10, min(1.8 + 0.42 * rows, 9)))
    _style(ax)

    xmax = max(wall, loop_seconds or 0) * 1.04
    lane_h = 0.7
    labels, ys = [], []
    row = 0

    if loop_seconds is not None:
        ax.broken_barh([(0, loop_seconds)], (row - lane_h / 2, lane_h), facecolors=RED, linewidth=0)
        ax.vlines(loop_seconds, row - 0.5, row + 0.5, color=INK, linewidth=2)
        ax.text(loop_seconds, -0.65, _seconds(loop_seconds), ha="center", va="bottom", fontsize=FONT,
                color=INK, fontweight="bold")
        labels.append("the loop")
        ys.append(row)
        row += 1

    by_worker = {}
    for t in tasks:
        by_worker.setdefault(t["worker"], []).append(t)
    for w in range(n):
        y = row + w
        ax.broken_barh([(0, wall)], (y - lane_h / 2, lane_h), facecolors=IDLE, linewidth=0)
        mine = by_worker.get(w, [])
        if mine:
            first = min(t["start"] for t in mine)
            last = max(t["end"] for t in mine)
            ax.broken_barh([(first, last - first)], (y - lane_h / 2, lane_h), facecolors=OVERHEAD, linewidth=0)
            ax.broken_barh([(t["start"], max(t["end"] - t["start"], wall / 800)) for t in mine],
                           (y - lane_h / 2, lane_h), facecolors=RED, linewidth=0)  # at least about a pixel wide
        labels.append(f"worker {w + 1}")
        ys.append(y)

    ax.vlines(wall, row - 0.5, rows - 0.5, color=INK, linewidth=2)
    ax.text(wall, rows - 0.35, _seconds(wall), ha="center", va="top", fontsize=FONT, color=INK,
            fontweight="bold")

    ax.set_yticks(ys)
    ax.set_yticklabels(labels)
    ax.set_ylim(rows + 0.5, -1.2 if loop_seconds is not None else -0.5)
    ax.set_xlim(0, xmax)
    ax.set_xlabel("seconds", fontsize=FONT, color=INK)
    ax.xaxis.set_major_locator(MaxNLocator(8))
    ax.tick_params(axis="y", length=0)
    ax.set_title(title or f"{n} workers", fontsize=FONT + 2, color=INK, loc="left", fontweight="bold")
    return ax


def plot_speedup(times, ax=None):
    """Plot speedup against workers. times is {workers: seconds} and must include 1.

    Shows your speedup (red), the ideal (dashed), Alp's recorded curve, and a line at your core count.
    """
    if ax is None:
        _, ax = plt.subplots(figsize=(8, 5))
    _style(ax)
    counts = sorted(times)
    mine = [times[1] / times[w] for w in counts]
    ref = REFERENCE["speedup"]
    right = max(counts + list(ref))  # wide enough for Alp's whole curve, so a small machine sees both
    best = max(mine + list(ref.values()) + [1])
    ax.plot([0, right], [0, right], color=MUTED, linestyle="--", linewidth=1.8, label="ideal: speedup = workers")
    xs = sorted(ref)
    ax.plot(xs, [ref[x] for x in xs], color=INK, linewidth=1.6, alpha=0.75, marker="o", markersize=4,
            label=REFERENCE["label"])
    ax.plot(counts, mine, color=RED, linewidth=2.5, marker="o", markersize=8, label="your computer")
    ax.axvline(os.cpu_count(), color=MUTED, linestyle=":", linewidth=2)
    ax.text(os.cpu_count(), 0.02, f" your cores ({os.cpu_count()})", transform=ax.get_xaxis_transform(),
            ha="left", va="bottom", fontsize=FONT, color=MUTED)
    ax.set_xlim(0, right * 1.05)
    ax.set_ylim(0, best * 1.2)
    ax.set_xlabel("workers", fontsize=FONT, color=INK)
    ax.set_ylabel("speedup (× faster than the loop)", fontsize=FONT, color=INK)
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.14), fontsize=FONT - 1, frameon=False)  # below, clear of the lines
    ax.set_title("Where the gains level off", fontsize=FONT + 2, color=INK, loc="left", fontweight="bold")
    return ax


def plot_sweep(tasks, results, ax=None):
    """Plot the mean burned fraction at each tree density. tasks are (density, seed) pairs."""
    if ax is None:
        _, ax = plt.subplots(figsize=(8, 4.5))
    _style(ax)
    by_density = {}
    for (density, _), fraction in zip(tasks, results):
        by_density.setdefault(density, []).append(fraction)
    xs = sorted(by_density)
    ys = [sum(by_density[d]) / len(by_density[d]) for d in xs]
    ax.axvline(0.593, color=MUTED, linestyle="--", linewidth=1.8)
    ax.text(0.593, 0.5, " about 59%", transform=ax.get_xaxis_transform(), ha="left", va="center",
            fontsize=FONT, color=MUTED)
    ax.plot(xs, ys, color=FLAME, linewidth=2.5, marker="o", markersize=7)
    ax.set_ylim(-0.03, 1.03)
    ax.set_xlabel("tree density", fontsize=FONT, color=INK)
    ax.set_ylabel("fraction of trees burned", fontsize=FONT, color=INK)
    ax.set_title("The fire flips near 59% density", fontsize=FONT + 2, color=INK, loc="left", fontweight="bold")
    return ax
