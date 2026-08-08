"""Page layout: sidebar (GPX import/select, Route Summary) + main content."""

from pathlib import Path

import streamlit as st

# Our own modules (calculation files + one shared display module),
# importable because build_streamlit.py added this folder to sys.path
# before importing us. elevation_profile.load_elevation_profile() already
# returns everything route_map.load_route() would (lat/lon/ele/time) plus
# a dist_m column, so there's no need to load the route twice.
import elevation_profile
import route_summary
import route_summary_visualization

# Path(__file__) = this file's path. .parent.parent walks up two levels:
# Streamlit App/frontpage_streamlit.py -> Streamlit App/ -> project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
GPX_DIR = PROJECT_ROOT / "Data" / "files_gpx"


def _list_gpx_files():
    """Return the names of all .gpx files in Data/files_gpx, alphabetically sorted.

    Leading underscore = a "private" helper, only meant to be used inside
    this file (a Python convention, not a hard rule the language enforces).
    """
    # mkdir with exist_ok=True creates the folder if it's missing and does
    # nothing (no error) if it already exists.
    GPX_DIR.mkdir(parents=True, exist_ok=True)
    # .glob("*.gpx") yields every matching Path in the folder; the
    # generator expression `p.name for p in ...` pulls out just the
    # filename (not the full path) for each match, and sorted() alphabetizes them.
    return sorted(p.name for p in GPX_DIR.glob("*.gpx"))


def _render_import_tab():
    """Sidebar tab 1: upload a GPX file (with a rename option) and pick the active route."""
    st.subheader("Import GPX")

    # File uploader widget. `uploaded` is None until the user picks a file;
    # once picked, it behaves like an in-memory file object.
    uploaded = st.file_uploader("Upload GPX file", type=["gpx"])
    # Ternary (inline if/else) expression: pre-fill the rename box with the
    # uploaded file's name (without its .gpx extension) if a file was
    # picked, otherwise leave it blank.
    default_name = Path(uploaded.name).stem if uploaded else ""
    new_name = st.text_input("Save as", value=default_name)

    # The Save button is disabled (greyed out, unclickable) until both a
    # file has been uploaded AND a name has been typed.
    if st.button("Save", disabled=uploaded is None or not new_name):
        target = GPX_DIR / f"{new_name}.gpx"   # f-string builds "<name>.gpx"
        # .getvalue() reads the uploaded file's raw bytes; write_bytes()
        # writes them straight to disk under the new filename -- this is
        # the actual "rename on import" behaviour.
        target.write_bytes(uploaded.getvalue())
        st.success(f"Saved {target.name}")
        # st.rerun() immediately restarts the script from the top, so the
        # newly saved file shows up in the dropdown below right away.
        st.rerun()

    st.divider()  # a horizontal line, purely visual separation

    files = _list_gpx_files()
    if files:
        # `key="selected_gpx"` stores the chosen value in
        # st.session_state["selected_gpx"], which persists across reruns
        # (Streamlit state is normally wiped every rerun, but session_state
        # survives) so other parts of the page can read the current selection.
        st.selectbox("Active route", files, key="selected_gpx")
    else:
        st.info("No GPX files found. Upload one above.")


def _render_summary_tab():
    """Sidebar tab 2: a compact Route Summary for the currently selected route."""
    # .get() returns None instead of raising an error if the key isn't set
    # yet (e.g. before the user has picked a route).
    gpx_filename = st.session_state.get("selected_gpx")
    if not gpx_filename:
        st.info("Select a route in the Import tab first.")
        return  # early exit -- nothing more to render in this tab
    summary = route_summary.RouteSummary(gpx_filename)
    route_summary_visualization.render_sidebar_summary(gpx_filename, summary)


# @st.fragment scopes reruns to just this function. Without it, clicking a
# point on the elevation chart (on_select="rerun") reruns Streamlit's ENTIRE
# script top to bottom -- every widget on the page (sidebar, title, summary
# metrics, both charts) gets torn down and redrawn, which is what reads as
# the map and elevation chart "disappearing and reappearing." Wrapping the
# two charts in a fragment means that click only reruns this function, so
# nothing outside it (and nothing here that hasn't changed, thanks to
# uirevision) needs to redraw.
@st.fragment
def _render_map_and_elevation(gpx_filename):
    """Route Map + Elevation Profile, sharing one click-driven marker and
    one start/finish window slider that zooms both to the same segment.
    """
    elevation_df = elevation_profile.load_elevation_profile(gpx_filename)
    total_km = elevation_df["dist_m"].max() / 1000.0

    # The elevation chart (drawn below) is where the user clicks to place
    # the marker; get_selected_index() reads that click back out of
    # session_state so the map -- drawn first -- can show the same point.
    marker_idx = route_summary_visualization.get_selected_index("elevation_chart")

    st.subheader("Route Map")
    # st.container() reserves this chart's position in the page now, but
    # doesn't draw anything into it yet -- it's filled in below, after the
    # slider (which needs to appear *below* the elevation chart) has a
    # value. Streamlit lets you write into a container after the fact; the
    # container still renders where it was created, not where you wrote to it.
    map_slot = st.container()

    st.subheader("Elevation Profile")
    elevation_slot = st.container()

    # A two-handle range slider: dragging either handle sets `start_km`/
    # `finish_km` as a (low, high) tuple. Placed after both container()
    # calls above so it's the last thing on the page -- visually below the
    # elevation chart -- while still being available to filter the data
    # those containers get filled with.
    start_km, finish_km = st.slider(
        "Route window (km)",
        min_value=0.0,
        max_value=total_km,
        value=(0.0, total_km),
        step=0.1,
        key="route_window",
    )

    dist_km = elevation_df["dist_m"] / 1000.0
    # .between() gives a boolean mask; .loc[] keeps only the rows inside the
    # slider's window. reset_index(drop=True) renumbers rows 0..n so
    # marker_idx (a position within *this* windowed set) and .iloc[] lookups
    # in the render functions line up correctly.
    windowed_df = elevation_df.loc[dist_km.between(start_km, finish_km)].reset_index(drop=True)

    with map_slot:
        route_summary_visualization.render_route_map(windowed_df, marker_idx)
    with elevation_slot:
        route_summary_visualization.render_elevation_profile(windowed_df, marker_idx)


def render():
    """Build the whole page: sidebar + main content. Called once per Streamlit rerun."""
    st.title("Wind Profile Modelling for Time-Trial Simulation")

    # `with st.sidebar:` routes every Streamlit call inside this block to
    # the left sidebar instead of the main page body.
    with st.sidebar:
        # st.tabs() returns one "tab" object per label; each acts as its
        # own `with` block/container for the widgets placed inside it.
        import_tab, summary_tab = st.tabs(["Import", "Route Summary"])
        with import_tab:
            _render_import_tab()
        with summary_tab:
            _render_summary_tab()

    # --- Main page body (outside the `with st.sidebar:` block again) ---
    st.subheader("Route Summary")
    gpx_filename = st.session_state.get("selected_gpx")
    if not gpx_filename:
        st.info("No route selected. Use the sidebar to import or select a GPX file.")
        return  # nothing to plot yet, stop here

    summary = route_summary.RouteSummary(gpx_filename)
    route_summary_visualization.render_main_summary(gpx_filename, summary)

    _render_map_and_elevation(gpx_filename)
