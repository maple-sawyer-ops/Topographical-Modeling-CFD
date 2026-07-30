"""Trim the Oxford Course STL tiles to a circular region around a center point.

The center is given as lat/lon (e.g. read off pick_stl_location.py) and
converted to the STL tiles' local (x, y) meters via geo_projection.py.
"""

import glob
import os

import numpy as np
import pyvista as pv

from geo_projection import latlon_to_local_xy

STL_DIR = os.path.join("Data", "stl_data", "Oxford Course")
OUT_DIR = os.path.join("out", "stl_trimmed")

# Center point (lat, lon degrees) and radius (meters).
CENTER_LATLON = (51.78, -1.20)
RADIUS_M = 1000.0


def load_stl_files(stl_dir):
    paths = sorted(glob.glob(os.path.join(stl_dir, "*.stl")))
    if not paths:
        raise FileNotFoundError(f"No .stl files found in {stl_dir}")
    return paths


def trim_to_radius(mesh, center_xy, radius):
    """Clip a mesh to the points within `radius` meters of `center_xy` in the XY plane.

    Clips on a horizontal-distance scalar field so the cut follows the mesh
    surface, instead of just dropping points and leaving ragged edges.
    """
    dist = np.linalg.norm(mesh.points[:, :2] - np.asarray(center_xy), axis=1)
    mesh = mesh.copy()
    mesh["dist_from_center"] = dist
    return mesh.clip_scalar(scalars="dist_from_center", value=radius, invert=True)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    center_xy = latlon_to_local_xy(*CENTER_LATLON)
    print(f"Center {CENTER_LATLON} (lat, lon) -> local xy {center_xy}")

    for path in load_stl_files(STL_DIR):
        stem = os.path.splitext(os.path.basename(path))[0]
        mesh = pv.read(path)
        trimmed = trim_to_radius(mesh, center_xy, RADIUS_M)

        if trimmed.n_points == 0:
            print(f"{stem}: no geometry within {RADIUS_M} m of {CENTER_LATLON}, skipping")
            continue

        surface = trimmed.extract_surface(algorithm="dataset_surface").triangulate()
        out_path = os.path.join(OUT_DIR, f"{stem}.stl")
        surface.save(out_path)
        print(f"{stem}: {mesh.n_points} -> {surface.n_points} points, wrote {out_path}")


if __name__ == "__main__":
    main()
