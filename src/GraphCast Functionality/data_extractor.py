# Script for extracting a single point/time wind value from a GraphCast rollout Dataset
# 1. Snap the requested lat/lon to the nearest grid cell (0-360 longitude convention)
# 2. Snap the requested time to the nearest forecast step using the rollout's absolute
#    "datetime" coordinate -- GraphCast's "time" dimension is a relative lead-time offset,
#    not an absolute datetime axis, so nearest-time matching can't use it directly
# 3. Derive wind speed and meteorological "from" direction from the 10m u/v components
# 4. Return a dict summarizing both the requested and actual selected point/time

# Key library imports
import math  # for atan2/hypot used in the speed and direction calculations
import numpy as np  # for datetime64 comparisons when snapping to the nearest forecast step


def normalize_longitude(lon):
    # Converts a -180..180 input into the grid's 0-360 convention; values already in
    # 0-360 pass through unchanged
    return lon % 360


def nearest_time_index(ds, query_time):
    # ds["time"] is a lead-time offset (e.g. -6h, 0h, +6h...), so the nearest step has to
    # be found via the "datetime" coordinate carried alongside it instead
    query_datetime = np.datetime64(query_time)
    time_diffs = abs(ds["datetime"] - query_datetime)

    return int(time_diffs.argmin())


def extract_point(ds, lat, lon, query_time):
    if "batch" in ds.dims:
        ds = ds.isel(batch=0)  # this pipeline only ever queries a single, non-batched run

    grid_lon = normalize_longitude(lon)

    time_index = nearest_time_index(ds, query_time)
    cell = ds.isel(time=time_index).sel(lat=lat, lon=grid_lon, method="nearest")

    u10 = float(cell["10m_u_component_of_wind"].values)
    v10 = float(cell["10m_v_component_of_wind"].values)

    speed_ms = math.hypot(u10, v10)
    dir_from_deg = (270 - math.degrees(math.atan2(v10, u10))) % 360  # meteorological "from" direction

    wind_summary = {
        "u10": u10,
        "v10": v10,
        "speed_ms": speed_ms,
        "dir_from_deg": dir_from_deg,
        "valid_time": str(cell["datetime"].values),
        "cell_lat": float(cell["lat"].values),
        "cell_lon": float(cell["lon"].values),
        "requested_lat": lat,
        "requested_lon": lon,
        "requested_time": str(query_time),
    }

    return wind_summary
