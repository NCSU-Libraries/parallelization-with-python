"""Forest-fire model: pure Python, standard library only.

A forest is a square grid. Each cell is a tree (True) or bare ground (False).
The fire starts in every tree in the left column and spreads to the four
neighbors (up, down, left, right). We measure the fraction of trees that burn.
Near a tree density of about 0.59, the outcome flips from "the fire dies out"
to "the fire sweeps across".
"""

import random
from collections import deque

DEFAULT_SIZE = 450  # cells per side; one run at density 0.6 takes about 40 ms


def make_forest(size, density, seed):
    """Return a size x size list of lists. True means a tree."""
    rng = random.Random(seed)
    return [[rng.random() < density for _ in range(size)] for _ in range(size)]


def spread(forest):
    """Burn the forest. Return a grid of burn steps (None = never burned).

    Left-column trees burn at step 0. Their neighbors burn at step 1, and so on.
    """
    size = len(forest)
    step_of = [[None] * size for _ in range(size)]
    queue = deque()

    # Light every tree in the left column.
    for row in range(size):
        if forest[row][0]:
            step_of[row][0] = 0
            queue.append((row, 0))

    # Breadth-first: take the oldest burning tree, light its unburned neighbors.
    while queue:
        row, col = queue.popleft()
        step = step_of[row][col] + 1
        for r, c in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
            if 0 <= r < size and 0 <= c < size:
                if forest[r][c] and step_of[r][c] is None:
                    step_of[r][c] = step
                    queue.append((r, c))
    return step_of


def burn(density, seed, size=DEFAULT_SIZE):
    """Return the fraction of trees that burned (0.0 if there are no trees)."""
    forest = make_forest(size, density, seed)
    trees = sum(sum(row) for row in forest)
    if trees == 0:
        return 0.0
    step_of = spread(forest)
    burned = sum(1 for row in step_of for s in row if s is not None)
    return burned / trees


def burn_steps(density, seed, size):
    """Return a flat, row-major list with one int per cell.

    -2 = bare ground, -1 = tree that never burned, k >= 0 = burned at step k.
    """
    forest = make_forest(size, density, seed)
    step_of = spread(forest)
    cells = []
    for row in range(size):
        for col in range(size):
            if not forest[row][col]:
                cells.append(-2)
            elif step_of[row][col] is None:
                cells.append(-1)
            else:
                cells.append(step_of[row][col])
    return cells


if __name__ == "__main__":
    import time

    for density in (0.45, 0.60, 0.75):
        start = time.perf_counter()
        fraction = burn(density, seed=1)
        ms = (time.perf_counter() - start) * 1000
        print(f"density {density:.2f}: burned {fraction:.3f} ({ms:.1f} ms, size {DEFAULT_SIZE})")
