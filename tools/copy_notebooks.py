#!/usr/bin/env python3
"""Copy the notebooks and their two helper files into the built site, so the Download links work.

Quarto runs this after a full render (project: post-render in site/_quarto.yml).
It copies notebooks/*.ipynb and notebooks/*.py (fire.py, lanes.py) into
<output dir>/notebooks/. Quarto sets QUARTO_PROJECT_OUTPUT_DIR; without it, the
output dir is site/_site.

The files go only into the output. Copied into site/, Quarto would render the
.ipynb files as pages and rewrite the links. Copied from dsti-python.
"""
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PATTERNS = ["*.ipynb", "*.py"]


def output_dir() -> Path:
    env = os.environ.get("QUARTO_PROJECT_OUTPUT_DIR")
    if not env:
        return REPO / "site" / "_site"
    out = Path(env)
    # Quarto may give a path relative to the project (site/), where it runs scripts.
    return out if out.is_absolute() else (REPO / "site" / out).resolve()


def main() -> int:
    dest = output_dir() / "notebooks"
    dest.mkdir(parents=True, exist_ok=True)
    for pattern in PATTERNS:
        files = sorted((REPO / "notebooks").glob(pattern))
        if not files:
            print(f"copy_notebooks: no {pattern} files found in notebooks/", file=sys.stderr)
            return 1
        for f in files:
            shutil.copy2(f, dest / f.name)
            print(f"copy_notebooks: {f.name} -> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
