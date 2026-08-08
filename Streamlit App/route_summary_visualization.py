"""Display and layout of route summary values, route map, and elevation profile."""

import math

import plotly.graph_objects as go
import streamlit as st

# Maps each RouteSummary field name to a (display label, unit) pair, so
# this file is the single place that controls how stats are labelled --
# route_summary.py only deals in raw numbers.
_LABELS = {
    "distance_km": ("Distance", "km"),
    "time_m": ("Time", "min"),
    "elevation_gain_m": ("Elevation Gain", "m"),
    "elevation_loss_m": ("Elevation Loss", "m"),
    "avg_wind_speed_ms": ("Avg Wind Speed", "m/s"),
    "avg_wind_dir_deg": ("Avg Wind Dir", "deg"),
    "max_wind_speed_ms": ("Max Wind Speed", "m/s"),
}


def render_main_summary(gpx_filename, summary):
    """Full-width Route Summary block for the main page body.

    `summary` is a route_summary.RouteSummary instance.
    """
    values = summary.as_dict()
    st.caption(f"GPX file: {gpx_filename}")

    # st.columns(n) creates n side-by-side layout slots; we make one column
    # per stat so they lay out in a row like a dashboard.
    cols = st.columns(len(values))

    # zip(cols, values.items()) pairs each column with one (key, value)
    # entry from the dict, in order, so the loop places one metric per
    # column. `for col, (key, value) in ...` unpacks both the column and
    # the dict entry's two parts in a single loop variable step.
    for col, (key, value) in zip(cols, values.items()):
        # dict.get(key, default) looks up the label/unit; if a stat name
        # isn't in _LABELS yet, it falls back to showing the raw key with
        # no unit instead of crashing.
        label, unit = _LABELS.get(key, (key, ""))
        # st.metric draws Streamlit's built-in "big number" stat tile.
        # f"{value:g}" formats the float compactly (drops trailing zeros,
        # e.g. 12.0 -> "12" but 12.34 -> "12.34"). .strip() removes the
        # trailing space left over when unit is "".
        col.metric(label, f"{value:g} {unit}".strip())


def render_sidebar_summary(gpx_filename, summary):
    """Compact, stacked version of the same stats for the sidebar tab."""
    st.caption(gpx_filename)
    # No columns here -- st.metric calls stack vertically by default,
    # which suits the narrow sidebar better than a side-by-side row.
    for key, value in summary.as_dict().items():
        label, unit = _LABELS.get(key, (key, ""))
        st.metric(label, f"{value:g} {unit}".strip())


def get_selected_index(chart_key, curve_number=0, default=0):
    """Read back the point index last clicked on a chart rendered with `key=chart_key`.

    Streamlit keeps a widget's selection state in `st.session_state[chart_key]`
    across reruns, so this can be called *before* that chart is drawn later
    in the script and still see the latest click. `curve_number` picks which
    trace's clicks count -- trace 0 is always the main line, so clicks on an
    overlaid marker trace (added after it) are ignored rather than
    overwriting the selection with that marker's own point_index (0).
    """
    state = st.session_state.get(chart_key)
    if not state:
        return default
    for point in state.get("selection", {}).get("points", []):
        if point.get("curve_number") == curve_number:
            return point.get("point_index", default)
    return default


def _estimate_zoom(lat_span, lon_span, padding=1.3):
    """Rough Scattermapbox zoom level that fits a lat/lon bounding box.

    Web-Mercator zoom level z divides the world into 2**z longitude tiles,
    each (360 / 2**z) degrees wide -- inverting that formula gives an
    approximate zoom for a given span. `padding` adds a small margin so the
    route isn't touching the edges of the view; the `max(..., 1e-6)` avoids
    `log2(0)` when the window narrows to a single point.
    """
    span = max(lat_span, lon_span, 1e-6) * padding
    return max(1.0, min(18.0, math.log2(360.0 / span)))


def render_route_map(route_df, marker_idx=None):
    """Draw the route as a line on an OpenStreetMap basemap.

    `route_df` has one row per GPS trackpoint with `lat`/`lon` columns --
    pass a windowed subset (e.g. from the start/finish slider) to zoom the
    map to just that segment; center/zoom are recomputed from whatever rows
    are given. `marker_idx` (if given) highlights that row's point with a
    marker, kept in sync with the elevation chart's click selection.
    """
    # go.Figure wraps one or more "traces" (data series) for Plotly to
    # render. Scattermapbox is the trace type for points/lines drawn on
    # top of a map tile layer (as opposed to plain Scatter, which just
    # plots on blank x/y axes).
    fig = go.Figure(go.Scattermapbox(
        lat=route_df["lat"],
        lon=route_df["lon"],
        mode="lines",                       # connect points with a line (vs "markers")
        line=dict(width=3, color="#d62728"),
        name="Route",
    ))
    if marker_idx is not None and 0 <= marker_idx < len(route_df):
        point = route_df.iloc[marker_idx]
        # A second, single-point trace drawn on top of the line -- this is
        # the "marker" that tracks whatever point was last clicked on the
        # (separate) elevation chart.
        fig.add_trace(go.Scattermapbox(
            lat=[point["lat"]],
            lon=[point["lon"]],
            mode="markers",
            marker=dict(size=14, color="#1f77b4"),
            name="Selected point",
            showlegend=False,
        ))
    lat_min, lat_max = route_df["lat"].min(), route_df["lat"].max()
    lon_min, lon_max = route_df["lon"].min(), route_df["lon"].max()

    fig.update_layout(
        mapbox=dict(
            # "open-street-map" is a free basemap style that needs no API
            # token (unlike Mapbox's own styles), but does require
            # internet access to fetch map tiles at render time.
            style="open-street-map",
            # Centre on the midpoint of whatever's plotted, so a windowed
            # (start/finish-slider) subset recenters onto that segment
            # instead of staying centred on the whole route.
            center=dict(lat=(lat_min + lat_max) / 2, lon=(lon_min + lon_max) / 2),
            zoom=_estimate_zoom(lat_max - lat_min, lon_max - lon_min),
        ),
        margin=dict(l=0, r=0, t=0, b=0),   # no whitespace border around the map
        height=500,                         # pixel height of the chart
        # uirevision: while this stays the same value across redraws,
        # Plotly's frontend treats it as "still the same chart" and
        # preserves the user's current pan/zoom instead of snapping back to
        # `center`/`zoom` above -- which matters because every Streamlit
        # rerun (e.g. clicking a point on the elevation chart) rebuilds
        # this figure from scratch. Keying it off the plotted bounding box
        # means marker-only clicks (bounding box unchanged) keep whatever
        # view the user had, while actually moving the start/finish slider
        # (bounding box changes) intentionally snaps to the new window.
        uirevision=f"route-map-{lat_min}-{lat_max}-{lon_min}-{lon_max}",
        showlegend=False,
    )
    # use_container_width=True stretches the chart to fill the page width.
    # config={"scrollZoom": True} turns on plain mouse-wheel zooming --
    # Plotly disables that by default so page scrolling isn't hijacked.
    st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True})


def render_elevation_profile(route_df, marker_idx=None):
    """Line chart of elevation (y) against cumulative distance (x).

    `route_df` must already have a `dist_m` column, as produced by
    elevation_profile.load_elevation_profile(). Clicking a point on the
    line selects it (captured via `on_select`/`key` below) -- read the
    result back with get_selected_index("elevation_chart") to sync a
    marker onto the (separate) route map. `marker_idx` draws the marker
    that resulted from that selection back onto this chart too.
    """
    dist_km = route_df["dist_m"] / 1000.0   # convert metres -> kilometres for the axis

    # Plain Scatter (not Scattermapbox) plots on ordinary numeric x/y axes
    # -- there's no basemap involved here, just a line graph.
    # mode="lines+markers" (not just "lines") so every trackpoint has an
    # actual marker to click on -- Plotly's click-selection hit-tests
    # against data points, not arbitrary positions along the interpolated
    # line, so a line with no markers can't be clicked precisely.
    fig = go.Figure(go.Scatter(
        x=dist_km,
        y=route_df["ele"],
        mode="lines+markers",
        line=dict(width=2, color="#2ca02c"),
        marker=dict(size=4, opacity=0.15),   # small + faint: visible enough to click, not visually noisy
        fill="tozeroy",   # shades the area between the line and y=0, like an area chart
        name="Elevation",
    ))
    if marker_idx is not None and 0 <= marker_idx < len(route_df):
        fig.add_trace(go.Scatter(
            x=[dist_km.iloc[marker_idx]],
            y=[route_df["ele"].iloc[marker_idx]],
            mode="markers",
            marker=dict(size=14, color="#1f77b4"),
            name="Selected point",
            showlegend=False,
        ))
    fig.update_layout(
        # Plotly's autorange adds a small padding margin before the first
        # data point by default, which reads as a gap before the fill
        # starts at x=0. Pinning the range to the data's actual min/max
        # removes that padding so the chart starts exactly at x=0.
        xaxis=dict(title="Distance (km)", range=[dist_km.min(), dist_km.max()]),
        yaxis_title="Elevation (m)",
        margin=dict(l=40, r=20, t=10, b=40),   # left/right/top/bottom padding in pixels
        height=350,
        # Same reasoning as render_route_map's uirevision: keyed off the
        # plotted distance range so a marker-only click (range unchanged)
        # keeps the user's zoom, but moving the start/finish slider (range
        # changes) intentionally snaps the x-axis to the new window.
        uirevision=f"elevation-profile-{dist_km.min()}-{dist_km.max()}",
        showlegend=False,
    )
    # on_select="rerun" tells Streamlit to capture click/select events on
    # this chart and trigger a script rerun when they happen; `key` is
    # where that selection state is stored in st.session_state so
    # get_selected_index() can read it back.
    st.plotly_chart(fig, use_container_width=True, on_select="rerun", key="elevation_chart")
