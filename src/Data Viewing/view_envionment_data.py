"""Visualize the Oxford Course STL tiles (terrain, buildings, canopy, route) with PyVista."""

import os
import glob

import pyvista as pv

STL_DIR = os.path.join("Data", "stl_data", "Oxford Course")

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


def main():
    plotter = pv.Plotter()

    for path in load_stl_files(STL_DIR):
        stem = os.path.splitext(os.path.basename(path))[0]
        mesh = pv.read(path)
        style = STYLE_BY_STEM.get(stem, DEFAULT_STYLE)
        plotter.add_mesh(mesh, label=stem, **style)

    plotter.add_legend()
    plotter.add_axes()
    plotter.show()


if __name__ == "__main__":
    main()
