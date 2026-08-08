"""Test extracting STL points within a radius of a hardcoded lat/lon query point.

`pickSTLlocation` takes a lat/lon + radius + wind conditions, converts the
lat/lon into the STL tiles' local (x, y) meter frame, then loads the STL
tiles and filters each one down to the points that fall within the radius --
this is the core "footprint extraction" operation the roughness-length
pipeline will build on.
"""

import os

import numpy as np

from load_stl import load_stl_meshes

# STL tile folder, built with os.path so it's a plain OS-correct path
# ("Data\stl_data\Oxford Course" on Windows) instead of a raw string.
STL_DIR = os.path.join("Data", "stl_data", "Oxford Course")

# Footprint radius, in meters.
RADIUS_M = 200.0

wind_conditions = {
    "wind_speed": 5.0,  # m/s
    "wind_direction": 270.0,  # degrees from north (0 = north, 90 = east)
}


class pickSTLlocation:
    """A query location: lat/lon + radius + wind, with STL point extraction.

    Converts lat/lon to the STL tiles' local (x, y) meters at construction
    time, then `query_points()` loads the STL tiles and filters each one
    down to just the points within `radius` meters of (x, y).
    """

    # Same fitted projection as geo_projection.py (src/Data Viewing/) --
    # class attributes since they're constants of the projection itself,
    # not per-instance state.
    EARTH_RADIUS_M = 6371000.0
    ORIGIN_LAT = 51.776975
    ORIGIN_LON = -1.2042125
    ROTATION_DEG = 0.6125

    def __init__(self, lat, lon, stl_dir, radius, wind_conditions):
        self.lat = lat
        self.lon = lon
        self.stl_dir = stl_dir
        self.radius = radius
        self.wind_conditions = wind_conditions

        # _latlon_to_local_xy returns an (x, y) tuple; unpack straight into
        # attributes instead of storing the intermediate tuple.
        self.x, self.y = self._latlon_to_local_xy(lat, lon)

        # Filled in by query_points() -- {stem: Nx3 numpy array of points}.
        self.points_by_class = {}

    def _latlon_to_local_xy(self, lat, lon):
        """Convert lat/lon (degrees) to the STL tiles' local (x, y) meters."""
        x = np.radians(lon - self.ORIGIN_LON) * np.cos(np.radians(self.ORIGIN_LAT)) * self.EARTH_RADIUS_M
        y = np.radians(lat - self.ORIGIN_LAT) * self.EARTH_RADIUS_M

        theta = np.radians(self.ROTATION_DEG)
        x_rot = x * np.cos(theta) - y * np.sin(theta)
        y_rot = x * np.sin(theta) + y * np.cos(theta)
        return x_rot, y_rot

    def query_points(self):
        """Load the STL tiles and keep only the points within `self.radius`.

        Returns and also stores (on `self.points_by_class`) a dict mapping
        each STL file's stem (e.g. "terrain_tile0") to the Nx3 array of its
        points that fall within the radius, filtered on horizontal (x, y)
        distance only -- height is ignored for this footprint cut.
        """
        meshes = load_stl_meshes(self.stl_dir)

        self.points_by_class = {}
        for stem, mesh in meshes.items():
            # mesh.points is an (n_points, 3) array of (x, y, z). Slicing
            # [:, :2] keeps just the x, y columns; subtracting the query
            # center and taking the row-wise norm (axis=1) gives each
            # point's horizontal distance from (self.x, self.y).
            horizontal_dist = np.linalg.norm(mesh.points[:, :2] - np.array([self.x, self.y]), axis=1)
            # Boolean mask -> fancy indexing: mesh.points[mask] keeps only
            # the rows where the mask is True, i.e. points inside the radius.
            within_radius = horizontal_dist <= self.radius
            self.points_by_class[stem] = mesh.points[within_radius]

        return self.points_by_class

    def __repr__(self):
        return (
            f"pickSTLlocation(lat={self.lat}, lon={self.lon}, xy=({self.x:.1f}, {self.y:.1f}), "
            f"radius={self.radius}, wind_conditions={self.wind_conditions})"
        )



# Hardcoded query location -- reuses the same center as trim_stl_data.py,
# already verified to fall within the Oxford Course STL coverage. Swap
# lat/lon/radius here to test a different location.
test_points_extration = pickSTLlocation(
    lat=51.792827,
    lon=-1.222481,
    stl_dir=STL_DIR,
    radius=RADIUS_M,
    wind_conditions=wind_conditions,
)



def main():
    print(test_points_extration)
    points_by_class = test_points_extration.query_points()
    for stem, points in points_by_class.items():
        print(f"{stem}: {len(points)} points within {RADIUS_M:.0f} m")


if __name__ == "__main__":
    main()
