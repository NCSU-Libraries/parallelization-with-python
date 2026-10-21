"""Record real timings, traces and burn steps for the workshop animations.

Run it from the repo root on a quiet machine (close Zoom, don't render):

    uv run --python 3.13 --no-project tools/record_runs.py

It imports the model from code/fire.py and writes JSON into
site/slides/anim/data/. Don't hand-edit those files; re-record instead.
All times are seconds. Task times use time.perf_counter(), which is a
system-wide monotonic clock on macOS and Linux, so values from different
worker processes can be compared directly.

The "machine" block (the same shape in sweep.json and scaling.json):
    {"platform": str, "cpu_brand": str, "cpu_count": int,
     "performance_cores": int, "efficiency_cores": int,
     "python": str, "start_method": str}

sweep.json  (serial run of the full sweep, so per-run seconds are uncontended)
    {"size": int,                    # grid side length
     "densities": [float, ...],      # 0.40 to 0.80 in steps of 0.02
     "seeds_per_density": int,       # 48
     "results": [[density, seed, burned_fraction, seconds], ...],
     "machine": {...}}

scaling.json
    {"size": int, "n_tasks": int,
     "machine": {...},
     "serial": {"seconds": median, "reps": [..3 values..]},
     "pool_startup_14": {"seconds": median, "reps": [...]},
         # time from Pool(14) call until a trivial map has come back
     "pool": [{"workers": w,
               "total":    {"seconds": median, "reps": [...]},
                   # with Pool(w) as pool: pool.map(..., chunksize=1)
               "map_only": {"seconds": median, "reps": [...]},
                   # pool already started and warmed up
               "speedup_total": serial / total,
               "speedup_map_only": serial / map_only}, ...],
     "tiny": {"size": 4, "n_tasks": 100000, "density": 0.6, "workers": 14,
              "default_chunksize": int, "per_worker_chunksize": int,
              "serial":        {"seconds": median, "reps": [...]},
              "chunksize_1":   {"total": {...}, "map_only": {...}},
              "chunksize_default": {"total": {...}, "map_only": {...}},
              "chunksize_per_worker": {"total": {...}, "map_only": {...}}}}
        # each {...} above is {"seconds": median, "reps": [...]}

trace-w1.json, trace-w4.json, trace-w14.json  (the sweep, chunksize=1)
trace-tiny-c1.json, trace-tiny-chunked.json   (3,000 tiny tasks, Pool(14);
                                               chunksize=1, then the default)
    {"workers": int, "wall": float,
     "tasks": [{"i": int, "density": float, "seed": int,
                "worker": int,       # 0..workers-1, by first appearance of the pid
                "pid": int,
                "start": float, "end": float}, ...]}
    start, end and wall are seconds since the moment map was called.
    The tiny files also carry "size", "chunksize" and "n_tasks".

fire-runs.json  (burn steps for the fire animation)
    {"size": 64, "seed": int,
     "runs": [{"density": float,
               "cells": [int, ...],   # row-major, size*size; -2 bare ground,
                                      # -1 tree that never burned, k>=0 burn step
               "steps": int,          # largest burn step
               "burned_fraction": float}, ...]}
"""

import json
import math
import os
import statistics
import subprocess
import sys
import time
from multiprocessing import Pool, get_start_method
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "code"))
import fire  # noqa: E402

OUT_DIR = ROOT / "site" / "slides" / "anim" / "data"
DENSITIES = [round(0.40 + 0.02 * i, 2) for i in range(21)]
SEEDS = 48
WORKER_COUNTS = [1, 2, 4, 6, 8, 10, 12, 14, 16]
REPS = 3
TINY_SIZE = 4
TINY_RUNS = 100_000
TINY_TRACE_RUNS = 3_000


def timed_burn(args):
    """Worker wrapper. Must be top-level so spawned workers can import it."""
    density, seed, size = args
    start = time.perf_counter()
    result = fire.burn(density, seed, size)
    end = time.perf_counter()
    return result, os.getpid(), start, end


def plain_burn(args):
    return fire.burn(*args)


def nothing(x):
    return x


def sweep_tasks():
    return [(d, s, fire.DEFAULT_SIZE) for d in DENSITIES for s in range(SEEDS)]


def tiny_tasks(n):
    return [(0.6, i, TINY_SIZE) for i in range(n)]


def summarize(values):
    return {"seconds": round(statistics.median(values), 4), "reps": [round(v, 4) for v in values]}


def repeat(fn):
    values = []
    for _ in range(REPS):
        t = time.perf_counter()
        fn()
        values.append(time.perf_counter() - t)
    return summarize(values)


def run_serial(tasks):
    for task in tasks:
        plain_burn(task)


def run_pool_total(tasks, workers, chunksize):
    with Pool(workers) as pool:
        pool.map(plain_burn, tasks, chunksize=chunksize)


def machine_info():
    def sysctl(name):
        try:
            return subprocess.check_output(["sysctl", "-n", name], text=True).strip()
        except Exception:
            return None

    perf, eff = sysctl("hw.perflevel0.physicalcpu"), sysctl("hw.perflevel1.physicalcpu")
    return {
        "platform": sys.platform + " " + os.uname().release + " " + os.uname().machine,
        "cpu_brand": sysctl("machdep.cpu.brand_string"),
        "cpu_count": os.cpu_count(),
        "performance_cores": int(perf) if perf else None,
        "efficiency_cores": int(eff) if eff else None,
        "python": sys.version.split()[0],
        "start_method": get_start_method(),
    }


def save(name, data):
    path = OUT_DIR / name
    path.write_text(json.dumps(data, separators=(",", ":")))
    print(f"  wrote {name} ({path.stat().st_size / 1000:.0f} KB)")


def record_trace(tasks, workers, chunksize, extra=None):
    """Map the tasks over a warmed-up pool and return per-task records."""
    with Pool(workers) as pool:
        pool.map(nothing, range(workers * 4), chunksize=1)  # make sure every worker is up
        t0 = time.perf_counter()
        out = pool.map(timed_burn, tasks, chunksize=chunksize)
        wall = time.perf_counter() - t0
    worker_of = {}
    for _, pid, _, _ in sorted(out, key=lambda r: r[2]):
        worker_of.setdefault(pid, len(worker_of))
    records = []
    for i, ((density, seed, _), (_, pid, start, end)) in enumerate(zip(tasks, out)):
        records.append({"i": i, "density": density, "seed": seed, "worker": worker_of[pid],
                        "pid": pid, "start": round(start - t0, 6), "end": round(end - t0, 6)})
    trace = {"workers": workers, "wall": round(wall, 4)}
    trace.update(extra or {})
    trace["tasks"] = records
    return trace


def pick_fire_seed(size=64):
    """First seed where 0.45 dies out, 0.60 reaches the right edge but leaves
    much unburned (a branching path), and 0.75 sweeps."""
    for seed in range(1, 500):
        cells = {}
        for d in (0.45, 0.60, 0.75):
            cells[d] = fire.burn_steps(d, seed, size)
        def frac(c):
            trees = sum(1 for v in c if v != -2)
            return sum(1 for v in c if v >= 0) / trees
        mid = cells[0.60]
        reaches = any(mid[r * size + size - 1] >= 0 for r in range(size))
        if frac(cells[0.45]) < 0.15 and reaches and 0.25 < frac(mid) < 0.6 and frac(cells[0.75]) > 0.9:
            return seed
    return 1


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    machine = machine_info()
    print("machine:", machine)
    size = fire.DEFAULT_SIZE
    tasks = sweep_tasks()

    # fire-runs.json
    print("fire-runs.json")
    seed = pick_fire_seed()
    runs = []
    for d in (0.45, 0.60, 0.75):
        cells = fire.burn_steps(d, seed, 64)
        trees = sum(1 for v in cells if v != -2)
        burned = sum(1 for v in cells if v >= 0)
        runs.append({"density": d, "cells": cells, "steps": max(cells),
                     "burned_fraction": round(burned / trees, 4)})
    save("fire-runs.json", {"size": 64, "seed": seed, "runs": runs})
    print(f"  chosen seed: {seed}")

    # sweep.json: serial, so each run's time is uncontended
    print("sweep.json (serial sweep, 1,008 runs)")
    results = []
    t = time.perf_counter()
    for density, s, sz in tasks:
        frac, _, start, end = timed_burn((density, s, sz))
        results.append([density, s, round(frac, 5), round(end - start, 5)])
    first_serial = time.perf_counter() - t
    print(f"  serial wall: {first_serial:.1f} s")
    save("sweep.json", {"size": size, "densities": DENSITIES, "seeds_per_density": SEEDS,
                        "results": results, "machine": machine})

    # scaling.json
    print("scaling.json")
    scaling = {"size": size, "n_tasks": len(tasks), "machine": machine}
    serial_reps = [first_serial]
    for _ in range(REPS - 1):
        t = time.perf_counter()
        run_serial(tasks)
        serial_reps.append(time.perf_counter() - t)
    scaling["serial"] = summarize(serial_reps)
    serial = scaling["serial"]["seconds"]
    print("  serial", scaling["serial"])

    starts = []
    for _ in range(5):
        t = time.perf_counter()
        pool = Pool(14)
        pool.map(nothing, range(14), chunksize=1)
        starts.append(time.perf_counter() - t)
        pool.terminate()
        pool.join()
    scaling["pool_startup_14"] = summarize(starts)
    print("  pool startup 14", scaling["pool_startup_14"])

    scaling["pool"] = []
    for w in WORKER_COUNTS:
        total = repeat(lambda: run_pool_total(tasks, w, 1))
        with Pool(w) as pool:
            pool.map(nothing, range(w * 4), chunksize=1)
            map_only = repeat(lambda: pool.map(plain_burn, tasks, chunksize=1))
        scaling["pool"].append({
            "workers": w, "total": total, "map_only": map_only,
            "speedup_total": round(serial / total["seconds"], 2),
            "speedup_map_only": round(serial / map_only["seconds"], 2)})
        print(f"  w={w}: total {total}  map_only {map_only}")

    # tiny tasks
    tiny = tiny_tasks(TINY_RUNS)
    default_chunk = math.ceil(TINY_RUNS / (14 * 4))  # what Pool.map picks
    per_worker = math.ceil(TINY_RUNS / 14)
    tiny_result = {"size": TINY_SIZE, "n_tasks": TINY_RUNS, "density": 0.6, "workers": 14,
                   "default_chunksize": default_chunk, "per_worker_chunksize": per_worker}
    tiny_result["serial"] = repeat(lambda: run_serial(tiny))
    print("  tiny serial", tiny_result["serial"])
    for name, chunk in (("chunksize_1", 1), ("chunksize_default", None), ("chunksize_per_worker", per_worker)):
        total = repeat(lambda: run_pool_total(tiny, 14, chunk))
        with Pool(14) as pool:
            pool.map(nothing, range(56), chunksize=1)
            map_only = repeat(lambda: pool.map(plain_burn, tiny, chunksize=chunk))
        tiny_result[name] = {"total": total, "map_only": map_only}
        print(f"  tiny {name}: total {total} map_only {map_only}")
    scaling["tiny"] = tiny_result
    save("scaling.json", scaling)

    # traces
    print("traces")
    for w in (1, 4, 14):
        save(f"trace-w{w}.json", record_trace(tasks, w, 1))
    small = tiny_tasks(TINY_TRACE_RUNS)
    default_small = math.ceil(TINY_TRACE_RUNS / (14 * 4))
    save("trace-tiny-c1.json", record_trace(small, 14, 1, {"size": TINY_SIZE, "chunksize": 1, "n_tasks": TINY_TRACE_RUNS}))
    save("trace-tiny-chunked.json", record_trace(small, 14, None, {"size": TINY_SIZE, "chunksize": default_small, "n_tasks": TINY_TRACE_RUNS}))

    # summary
    print("\nSummary (first look)")
    print(f"size {size}, serial sweep {serial:.1f} s (reps {scaling['serial']['reps']})")
    print(f"{'w':>3} {'total s':>8} {'speedup':>8} {'map s':>8} {'speedup':>8}")
    for row in scaling["pool"]:
        print(f"{row['workers']:>3} {row['total']['seconds']:>8.2f} {row['speedup_total']:>8.2f} "
              f"{row['map_only']['seconds']:>8.2f} {row['speedup_map_only']:>8.2f}")
    print(f"pool startup (14): {scaling['pool_startup_14']['seconds']:.3f} s")
    print(f"tiny serial {tiny_result['serial']['seconds']:.3f} s; " + "; ".join(
        f"{k} {tiny_result[k]['total']['seconds']:.3f}/{tiny_result[k]['map_only']['seconds']:.3f} s"
        for k in ("chunksize_1", "chunksize_default", "chunksize_per_worker")) + " (total/map_only)")
    print("density  mean burned")
    for d in DENSITIES:
        vals = [r[2] for r in results if r[0] == d]
        print(f"  {d:.2f}   {statistics.mean(vals):.3f}")


if __name__ == "__main__":
    main()
