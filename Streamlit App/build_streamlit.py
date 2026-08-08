"""Launching framework for the Wind Profile Modelling Streamlit app.

Run with: streamlit run "Streamlit App/build_streamlit.py"
"""

# `sys` lets us edit the module search path (sys.path) at runtime.
# `pathlib.Path` is the modern, cross-platform way to build file paths
# (it uses the correct slash direction for Windows/Mac/Linux automatically).
import sys
from pathlib import Path

# __file__ is the path to *this* script. .resolve() turns it into an
# absolute path, and .parent walks up one directory level.
APP_DIR = Path(__file__).resolve().parent          # .../Streamlit App
PROJECT_ROOT = APP_DIR.parent                       # .../Topographical Modeling CFD
# The GPX-parsing helpers (gpx_processing.py, gpx_viewing.py) live in this
# folder, which is not normally on Python's import search path.
GPX_MODULE_DIR = PROJECT_ROOT / "src" / "Data Viewing"

# Python only looks for modules to import in the folders listed in sys.path.
# We add our two extra folders so that `import frontpage_streamlit` and
# `import gpx_processing` (used later, in other files) succeed.
# insert(0, ...) puts them at the FRONT of the search order.
for path in (APP_DIR, GPX_MODULE_DIR):
    if str(path) not in sys.path:      # avoid adding the same path twice on reruns
        sys.path.insert(0, str(path))

# These imports must come after the sys.path edit above, because
# frontpage_streamlit.py (and the modules it imports) rely on those folders
# already being importable.
import streamlit as st
import frontpage_streamlit

# Configures the browser tab title, and makes the app use the full window
# width ("wide") with the sidebar open by default. Must be the first
# Streamlit command called, before any other st.* output.
st.set_page_config(
    page_title="Wind Profile Modelling for Time-Trial Simulation",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Hand off to the actual page layout, defined in frontpage_streamlit.py.
# Streamlit re-runs this whole script top-to-bottom on every user
# interaction (button click, dropdown change, etc.), so render() is called
# fresh each time.
frontpage_streamlit.render()