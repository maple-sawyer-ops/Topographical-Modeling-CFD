"""Elevation profile data: route trackpoints annotated with cumulative distance."""

import streamlit as st

# gpx_viewing.py (in src/Data Viewing) already implements the haversine
# great-circle-distance math needed to turn a sequence of lat/lon points
# into a running "distance travelled" total -- we reuse it instead of
# duplicating that formula here.
import gpx_viewing

import route_map


# Same reasoning as route_map.load_route's @st.cache_data: this shouldn't
# redo the haversine distance calculation on every rerun triggered by a
# marker click.
@st.cache_data
def load_elevation_profile(gpx_filename):
    """Return the route DataFrame with an added `dist_m` column.

    `dist_m` is the cumulative distance (in metres) travelled from the
    first trackpoint up to each row, computed by add_distance_column().
    """
    route_df = route_map.load_route(gpx_filename)
    return gpx_viewing.add_distance_column(route_df)
