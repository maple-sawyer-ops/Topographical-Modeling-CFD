"""Click a lat/lon plot of the GPX route to read off a candidate center/radius.

Plots the parsed GPX track (see gpx_processing.py) on a plain lat/lon grid --
no STL loading, so it opens instantly. Left-click a point on the track:
prints its (lat, lon). The first click is treated as a candidate center;
every click after that also prints its great-circle distance from the first
click (in meters), so you can click a center then an edge point to read off
a candidate radius.
"""

import matplotlib.pyplot as plt
import numpy as np

from gpx_processing import load_gpx
from gpx_viewing import haversine_m

picked = []  # list of (lat, lon) tuples


def on_click(event):
    if event.inaxes is None or event.xdata is None:
        return

    lon, lat = event.xdata, event.ydata
    picked.append((lat, lon))
    msg = f"Picked #{len(picked)}: lat={lat:.6f}, lon={lon:.6f}"
    if len(picked) > 1:
        lat0, lon0 = picked[0]
        dist = haversine_m(lat0, lon0, lat, lon)
        msg += f"  |  dist from pick #1 (candidate radius): {dist:.1f} m"
    print(msg)


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
    ax.set_title("GPX route - click to read off lat/lon")
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(loc="upper right")

    fig.canvas.mpl_connect("button_press_event", on_click)
    plt.show()


if __name__ == "__main__":
    main()
