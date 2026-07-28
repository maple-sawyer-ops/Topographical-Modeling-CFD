"""Interactive GPX viewer (Plotly): track map + elevation-vs-distance, linked by cursor."""

import json
import os
import webbrowser

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from gpx_processing import load_gpx

EARTH_RADIUS_M = 6371000.0
OUT_HTML = os.path.join("out", "gpx_track_view.html")
DIV_ID = "gpx-track-view"

# Trace order added in build_figure(); the linking JS restyles these by index.
TRACE_MAP_LINE, TRACE_MAP_MARKER, TRACE_ELEV_LINE, TRACE_ELEV_MARKER = range(4)


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance between two points (degrees in, metres out)."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def add_distance_column(df):
    """Add a cumulative `dist_m` column (metres travelled from the first point)."""
    lat = df["lat"].to_numpy()
    lon = df["lon"].to_numpy()
    step = np.zeros(len(df))
    step[1:] = haversine_m(lat[:-1], lon[:-1], lat[1:], lon[1:])
    df = df.copy()
    df["dist_m"] = np.cumsum(step)
    return df


def build_figure(df):
    """Build the track-map + elevation-profile subplot figure.

    Returns the figure plus the plain lon/lat/dist_km/ele lists (needed by
    the linking JS to look up coordinates for an arbitrary point index).
    """
    df = add_distance_column(df)
    lon, lat, ele = df["lon"].tolist(), df["lat"].tolist(), df["ele"].tolist()
    dist_km = (df["dist_m"] / 1000.0).tolist()

    fig = make_subplots(
        rows=1, cols=2, column_widths=[0.5, 0.5],
        subplot_titles=("Track", "Elevation profile"),
    )

    fig.add_trace(
        go.Scatter(x=lon, y=lat, mode="lines", name="track", line=dict(color="#1f77b4")),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(x=[lon[0]], y=[lat[0]], mode="markers", name="cursor",
                   marker=dict(color="#d62728", size=12), showlegend=False),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(x=dist_km, y=ele, mode="lines", name="elevation", line=dict(color="#2ca02c")),
        row=1, col=2,
    )
    fig.add_trace(
        go.Scatter(x=[dist_km[0]], y=[ele[0]], mode="markers", name="cursor",
                   marker=dict(color="#d62728", size=12), showlegend=False),
        row=1, col=2,
    )

    fig.update_xaxes(title_text="Longitude", row=1, col=1)
    fig.update_yaxes(title_text="Latitude", row=1, col=1)
    # Elevation x-axis keeps its own range slider so it can be dragged/scaled
    # independently; column_widths above keeps both plots the same fixed
    # width regardless of how the slider or zoom range is used.
    fig.update_xaxes(
        title_text="Distance (km)", rangeslider=dict(visible=True, thickness=0.08),
        row=1, col=2,
    )
    fig.update_yaxes(title_text="Elevation (m)", row=1, col=2)
    fig.update_layout(hovermode="closest", height=600, title="GPX track viewer")

    return fig, lon, lat, dist_km, ele


# Injected after the Plotly figure is rendered. Hovering either subplot's
# line looks up that point's index and moves BOTH cursor-marker traces to
# the matching lon/lat and dist/ele, so the same trackpoint highlights on
# both axes. Pure client-side JS -- no server needed to view the HTML.
LINK_JS_TEMPLATE = """
<script>
(function() {{
  var gd = document.getElementById("{div_id}");
  var lon = {lon_json}, lat = {lat_json}, distKm = {dist_json}, ele = {ele_json};
  function setIndex(idx) {{
    Plotly.restyle(gd, {{x: [[lon[idx]]], y: [[lat[idx]]]}}, [{map_marker}]);
    Plotly.restyle(gd, {{x: [[distKm[idx]]], y: [[ele[idx]]]}}, [{elev_marker}]);
  }}
  gd.on("plotly_hover", function(data) {{
    var idx = data.points[0].pointIndex;
    setIndex(idx);
  }});
  gd.on("plotly_click", function(data) {{
    var idx = data.points[0].pointIndex;
    setIndex(idx);
  }});
}})();
</script>
"""


def save_html(fig, lon, lat, dist_km, ele, out_path=OUT_HTML):
    """Render the figure to a self-contained HTML file with cursor-linking JS."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    html = fig.to_html(include_plotlyjs="cdn", full_html=True, div_id=DIV_ID)
    js = LINK_JS_TEMPLATE.format(
        div_id=DIV_ID,
        lon_json=json.dumps(lon),
        lat_json=json.dumps(lat),
        dist_json=json.dumps(dist_km),
        ele_json=json.dumps(ele),
        map_marker=TRACE_MAP_MARKER,
        elev_marker=TRACE_ELEV_MARKER,
    )
    html = html.replace("</body>", js + "</body>")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


def main():
    df = load_gpx()
    fig, lon, lat, dist_km, ele = build_figure(df)
    out_path = save_html(fig, lon, lat, dist_km, ele)
    print(f"Wrote {out_path}")
    webbrowser.open("file://" + os.path.abspath(out_path))


if __name__ == "__main__":
    main()
