"""Visualize STL tiles (terrain, buildings, canopy, route) with PyVista.

Prompts with a folder picker on launch so any STL folder can be viewed, not
just the Oxford Course tiles.
"""

import os
import glob
import tkinter as tk
from tkinter import filedialog

import pyvista as pv

DEFAULT_STL_DIR = os.path.join("Data", "stl_data", "Oxford Course")

# Per-file styling so overlapping surfaces (e.g. route vs route_tile0) stay legible.
STYLE_BY_STEM = {
    "terrain_tile0": dict(color="tan", opacity=1.0),
    "buildings_tile0": dict(color="lightgray", opacity=1.0),
    "canopy_tile0": dict(color="forestgreen", opacity=0.6),
    "route_tile0": dict(color="red", opacity=1.0),
    "route": dict(color="orange", opacity=1.0),
}
DEFAULT_STYLE = dict(color="white", opacity=1.0)


def load_stl_files(stl_dir):
    paths = sorted(glob.glob(os.path.join(stl_dir, "*.stl")))
    if not paths:
        raise FileNotFoundError(f"No .stl files found in {stl_dir}")
    return paths


def select_stl_dir(initial_dir=DEFAULT_STL_DIR):
    """Pop up a folder picker for the STL directory; cancel keeps `initial_dir`."""
    root = tk.Tk()
    root.withdraw()
    chosen = filedialog.askdirectory(
        title="Select folder containing STL tiles",
        initialdir=initial_dir if os.path.isdir(initial_dir) else os.getcwd(),
    )
    root.destroy()
    return chosen or initial_dir


def main():
    stl_dir = select_stl_dir()
    plotter = pv.Plotter()

    for path in load_stl_files(stl_dir):
        stem = os.path.splitext(os.path.basename(path))[0]
        mesh = pv.read(path)
        style = STYLE_BY_STEM.get(stem, DEFAULT_STYLE)
        plotter.add_mesh(mesh, label=stem, **style)

    plotter.add_legend()
    plotter.add_axes()
    plotter.show()


if __name__ == "__main__":
    main()
