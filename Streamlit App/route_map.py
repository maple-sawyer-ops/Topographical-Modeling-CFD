"""Route map data: loads the GPX track for map rendering."""

from pathlib import Path

import streamlit as st

# Importable because build_streamlit.py added src/Data Viewing to
# sys.path before any of these Streamlit App modules were imported.
import gpx_processing

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GPX_DIR = PROJECT_ROOT / "Data" / "files_gpx"


# st.cache_data memoizes this by its argument (gpx_filename): Streamlit
# reruns the whole script on every interaction (e.g. clicking a point on
# the elevation chart), which would otherwise re-run this every time --
# the cache makes repeat calls with the same filename return instantly
# instead of re-reading/re-parsing the GPX file on each rerun.
@st.cache_data
def load_route(gpx_filename):
    """Load lat/lon/elevation trackpoints for a GPX file as a DataFrame.

    `gpx_filename` is just the file's name (e.g. "English_Weather_.gpx"),
    as shown in the sidebar dropdown -- we join it onto GPX_DIR here to
    get the full path gpx_processing.load_gpx() needs.
    """
    gpx_path = GPX_DIR / gpx_filename   # Path "/" operator joins path segments
    # load_gpx() parses the XML, caches the parsed result as a pickle for
    # faster reloads, and returns a pandas DataFrame with one row per
    # trackpoint (columns: lat, lon, ele, time, ...).
    return gpx_processing.load_gpx(str(gpx_path))
