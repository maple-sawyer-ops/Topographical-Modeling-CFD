"""Map GPX lat/lon onto the Oxford Course STL tiles' local (x, y) meter frame.

The STL tiles don't carry any CRS metadata, so this projection was fitted
empirically: an equirectangular (tangent-plane) projection centered near the
course, plus a small rotation, minimizes the distance between the projected
GPX track (gpx_processing.py) and the actual route.stl surface down to a
~5.7 m mean residual (found via a coordinate-descent grid search over origin
lat/lon and rotation). That residual is the practical accuracy limit of this
mapping -- treat picks as accurate to within roughly +/-10-15 m, not survey
grade.
"""

import numpy as np

EARTH_RADIUS_M = 6371000.0
ORIGIN_LAT = 51.776975
ORIGIN_LON = -1.2042125
ROTATION_DEG = 0.6125


def latlon_to_local_xy(lat, lon):
    """Convert lat/lon (degrees) to the STL tiles' local (x, y) meters."""
    x = np.radians(lon - ORIGIN_LON) * np.cos(np.radians(ORIGIN_LAT)) * EARTH_RADIUS_M
    y = np.radians(lat - ORIGIN_LAT) * EARTH_RADIUS_M

    theta = np.radians(ROTATION_DEG)
    x_rot = x * np.cos(theta) - y * np.sin(theta)
    y_rot = x * np.sin(theta) + y * np.cos(theta)
    return x_rot, y_rot
