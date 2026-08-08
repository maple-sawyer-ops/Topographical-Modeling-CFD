"""Pop up a folder picker and load all STL tiles in it with PyVista.

Same folder-picker convention as `Data Viewing/view_envionment_data.py`, but
returns the loaded meshes (keyed by filename stem, e.g. "terrain_tile0")
instead of plotting them -- this is the loader the roughness-length pipeline
builds on.
"""

# `os` gives cross-platform path joining/splitting (os.path.*) and folder
# checks (os.path.isdir). `glob` expands wildcard patterns (e.g. "*.stl")
# into a list of matching file paths on disk.
import os
import glob

# `tkinter` is Python's built-in GUI toolkit -- we only use it here for its
# native "browse for a folder" dialog box (filedialog.askdirectory), not for
# building a full GUI.
import tkinter as tk
from tkinter import filedialog

# PyVista wraps VTK and gives a simple `pv.read()` for loading mesh files
# (STL, OBJ, etc.) into a PolyData object with .points, .n_points, .n_cells,
# .bounds, etc.
import pyvista as pv

# os.path.join builds a path using the right slash for the current OS
# ("Data\stl_data\Oxford Course" on Windows, "Data/stl_data/Oxford Course" on
# Linux/Mac) instead of hardcoding one style.
DEFAULT_STL_DIR = os.path.join("Data", "stl_data", "Oxford Course")


def select_stl_dir(initial_dir=DEFAULT_STL_DIR):
    """Pop up a folder picker for the STL directory; cancel keeps `initial_dir`."""
    # tk.Tk() creates a hidden root application window that tkinter dialogs
    # need to exist even if we never show it -- root.withdraw() immediately
    # hides it so only the folder-picker dialog itself is visible.
    root = tk.Tk()
    root.withdraw()
    # askdirectory() blocks execution and opens the OS's native folder
    # browser; it returns the chosen path as a string, or "" (empty string)
    # if the user hits Cancel.
    chosen = filedialog.askdirectory(
        title="Select folder containing STL tiles",
        initialdir=initial_dir if os.path.isdir(initial_dir) else os.getcwd(),
    )
    # root.destroy() tears down the hidden window so it doesn't linger as a
    # dangling process/window after this function returns.
    root.destroy()
    # `chosen or initial_dir` relies on Python's truthiness: an empty string
    # is falsy, so Cancel (chosen == "") falls back to initial_dir.
    return chosen or initial_dir


def load_stl_paths(stl_dir):
    """Sorted list of every .stl file path in `stl_dir`."""
    # glob.glob() returns filesystem matches for the "*.stl" wildcard in
    # arbitrary OS order, so sorted() makes the result deterministic
    # (alphabetical) across runs/platforms.
    paths = sorted(glob.glob(os.path.join(stl_dir, "*.stl")))
    if not paths:
        # Fail loudly and immediately rather than silently returning an
        # empty/unusable result -- a wrong or empty folder pick should stop
        # the script here, not surface as a confusing error later.
        raise FileNotFoundError(f"No .stl files found in {stl_dir}")
    return paths


def load_stl_meshes(stl_dir):
    """Load every .stl in `stl_dir` with PyVista, keyed by filename stem."""
    # A dict comprehension-style build: `meshes` maps each file's "stem"
    # (filename without directory or extension, e.g. "terrain_tile0") to its
    # loaded PyVista mesh, so callers can look up a specific class of
    # geometry by name instead of guessing list order.
    meshes = {}
    for path in load_stl_paths(stl_dir):
        # os.path.basename(path) strips the directory, leaving just the
        # filename (e.g. "terrain_tile0.stl"); os.path.splitext() then
        # splits that into ("terrain_tile0", ".stl") and we keep index [0].
        stem = os.path.splitext(os.path.basename(path))[0]
        meshes[stem] = pv.read(path)
    return meshes


def main():
    stl_dir = select_stl_dir()
    meshes = load_stl_meshes(stl_dir)
    # .items() iterates a dict as (key, value) pairs -- here (stem, mesh) --
    # so we can print a per-file sanity check without a separate lookup.
    for stem, mesh in meshes.items():
        print(f"{stem}: {mesh.n_points} points, {mesh.n_cells} cells")


# This guard only runs main() when the file is executed directly
# (`python load_stl.py`), not when it's imported by another module (e.g.
# point_query_test.py importing select_stl_dir/load_stl_meshes) -- Python
# sets __name__ to "__main__" only for the script that was launched.
if __name__ == "__main__":
    main()
