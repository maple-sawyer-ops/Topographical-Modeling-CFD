"""Route summary calculations.

Stubbed to 0 for now; will be wired up to gpx_processing.load_gpx as the
real distance/elevation/gradient calculations are built out.
"""


class RouteSummary:
    """Summary statistics for a single GPX route.

    A plain class rather than a dict: the field names are fixed and
    IDE-autocompletable (summary.distance_km), and it gives us a natural
    place to later add real calculation methods (e.g. compute distance
    from the parsed GPX points) without changing every call site.
    """

    def __init__(self, gpx_filename):
        # __init__ runs automatically whenever RouteSummary(...) is called.
        # `self` is the specific instance being created; every attribute
        # set on it here (self.xxx = ...) becomes accessible later as
        # summary.xxx.
        self.gpx_filename = gpx_filename

        # --- Stub values (all zero) -- replaced with real GPX-derived
        # numbers once the calculation logic is built out. ---
        self.distance_km = 0.0
        self.time_m = 0.0
        self.elevation_gain_m = 0.0
        self.elevation_loss_m = 0.0
        self.avg_wind_speed_ms = 0.0
        self.avg_wind_dir_deg = 0.0
        self.max_wind_speed_ms = 0.0

    def as_dict(self):
        """Return the stats as a plain dict, keyed by field name.

        The display layer (route_summary_visualization.py) loops over this
        dict rather than reading attributes one by one, so new stats added
        here automatically show up on screen without touching that file.
        """
        return {
            "distance_km": self.distance_km,
            "time_m": self.time_m,
            "elevation_gain_m": self.elevation_gain_m,
            "elevation_loss_m": self.elevation_loss_m,
            "avg_wind_speed_ms": self.avg_wind_speed_ms,
            "avg_wind_dir_deg": self.avg_wind_dir_deg,
            "max_wind_speed_ms": self.max_wind_speed_ms,
        }
