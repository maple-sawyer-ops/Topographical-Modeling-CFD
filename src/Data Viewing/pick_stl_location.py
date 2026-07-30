"""Click a lat/lon plot of the GPX route to read off a candidate center/radius.

Plots the parsed GPX track (see gpx_processing.py) on a plain lat/lon grid --
no STL loading, so it opens instantly. Left-click a point on the track:
prints its (lat, lon). The first click is treated as a candidate center;
every click after that also prints its great-circle distance from the first
click (in meters) and redraws a preview circle of that radius around the
center, so you can see the trim area before touching trim_stl_data.py.
Press 'c' to clear and start over.
"""

import matplotlib.pyplot as plt
import numpy as np

from gpx_processing import load_gpx
from gpx_viewing import EARTH_RADIUS_M, haversine_m


def circle_latlon(center_lat, center_lon, radius_m, n=180):
    """Boundary points (lon, lat) of a circle of `radius_m` around a lat/lon center."""
    phi = np.linspace(0, 2 * np.pi, n)
    dlat = (radius_m * np.cos(phi)) / EARTH_RADIUS_M
    dlon = (radius_m * np.sin(phi)) / (EARTH_RADIUS_M * np.cos(np.radians(center_lat)))
    return center_lon + np.degrees(dlon), center_lat + np.degrees(dlat)


def main():
    df = load_gpx()

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.plot(df["lon"], df["lat"], "-", color="#1f77b4", linewidth=1, label="route")

    # Longitude degrees cover less ground than latitude degrees away from the
    # equator; scale the aspect ratio so on-screen distances stay proportional
    # to real-world distances instead of stretching the route east-west.
    mean_lat_rad = np.radians(df["lat"].mean())
    ax.set_aspect(1.0 / np.cos(mean_lat_rad))

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("GPX route - click center, then edge point for radius ('c' to clear)")
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(loc="upper right")

    picked = []  # list of (lat, lon) tuples
    preview_artists = []

    def clear_preview():
        for artist in preview_artists:
            artist.remove()
        preview_artists.clear()

    def draw_preview():
        clear_preview()
        if not picked:
            return

        lat0, lon0 = picked[0]
        preview_artists.append(
            ax.scatter([lon0], [lat0], color="black", marker="x", s=80, zorder=5)
        )

        if len(picked) > 1:
            lat1, lon1 = picked[-1]
            radius_m = haversine_m(lat0, lon0, lat1, lon1)
            circ_lon, circ_lat = circle_latlon(lat0, lon0, radius_m)
            (circle_line,) = ax.plot(circ_lon, circ_lat, "--", color="black", linewidth=1.5, zorder=4)
            preview_artists.append(circle_line)
            preview_artists.append(
                ax.scatter([lon1], [lat1], color="black", marker="+", s=80, zorder=5)
            )

    def on_click(event):
        if event.inaxes is not ax or event.xdata is None:
            return

        lon, lat = event.xdata, event.ydata
        picked.append((lat, lon))
        msg = f"Picked #{len(picked)}: lat={lat:.6f}, lon={lon:.6f}"
        if len(picked) > 1:
            lat0, lon0 = picked[0]
            dist = haversine_m(lat0, lon0, lat, lon)
            msg += f"  |  dist from pick #1 (candidate radius): {dist:.1f} m"
        print(msg)

        draw_preview()
        fig.canvas.draw_idle()

    def on_key(event):
        if event.key == "c":
            picked.clear()
            draw_preview()
            fig.canvas.draw_idle()
            print("Cleared picks")

    fig.canvas.mpl_connect("button_press_event", on_click)
    fig.canvas.mpl_connect("key_press_event", on_key)
    plt.show()


if __name__ == "__main__":
    main()
