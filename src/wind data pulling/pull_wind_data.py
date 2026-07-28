"""
era5land_wind_inlet.py
======================
Extract a SINGLE-TIMESTEP 10 m wind condition from ERA5-Land for use as a
CFD inlet boundary condition.

What it does, end to end:
  1. Takes a configurable datetime and a configurable (lat, lon) point.
  2. Downloads the ERA5-Land 10 m u/v wind for that hour over a tiny area
     box surrounding the point (via the Copernicus CDS API).
  3. Selects the ERA5-Land grid cell nearest to the requested point and the
     hour nearest to the requested time.
  4. Computes wind SPEED and meteorological "from" DIRECTION from u/v.
  5. Prints an inlet summary and reports the ACTUAL cell/time used vs. the
     values you requested (nearest-neighbour snapping is explicit, not hidden).

WHY CDS API (and not the Google ARCO Zarr bucket):
  The public `gcp-public-data-arco-era5` bucket is *base* ERA5 (0.25 deg),
  NOT ERA5-Land. ERA5-Land (0.1 deg) is served by the Copernicus Climate Data
  Store. For a single hour, a small CDS subset is the simplest correct route.

PREREQUISITES (run in YOUR environment, not a sandbox):
  pip install cdsapi xarray netCDF4 numpy
  A free CDS account + an API key saved to ~/.cdsapirc
  Register / key instructions: https://cds.climate.copernicus.eu

NOTE ON DATA LATENCY:
  ERA5-Land is published ~2-3 months behind real time. A very recent
  TARGET_DATETIME may not exist yet; the script guards against this.
"""

# ---------------------------------------------------------------------------
# Standard library imports
# ---------------------------------------------------------------------------
import os                      # os: build/join filesystem paths for the download target
import math                    # math: only used for the degrees<->radians direction math
from datetime import datetime, timezone, timedelta  # datetime types for the config + latency check
import json

# ---------------------------------------------------------------------------
# Third-party imports
#   These are NOT in the Python standard library; install them (see header).
#   Imported at top so a missing dependency fails immediately and clearly.
# ---------------------------------------------------------------------------
import numpy as np             # numpy: vector maths (arctan2, hypot) on the u/v scalars
import xarray as xr            # xarray: open the downloaded NetCDF and do nearest-point select
import cdsapi                  # cdsapi: official Copernicus client that talks to the CDS API


# ===========================================================================
# CONFIGURATION  ---  everything you would routinely change lives here.
# ===========================================================================

# Target instant in time (UTC). ERA5-Land is hourly, so minutes/seconds are
# rounded to the nearest whole hour later. tzinfo=utc makes the intent explicit.
TARGET_DATETIME = datetime(2026, 4, 25, 11, 0, 0, tzinfo=timezone.utc)

# Target point. Defaults sit on the ERA5-Land cell nearest the GPX track
# centroid (Oxford). Both are plain floats so they are trivial to override.
LAT = 51.8     # degrees north  (positive = N)
LON = -1.2     # degrees east   (negative = W, so -1.2 means 1.2 deg West)

# Half-width of the area box requested from CDS, in degrees. ERA5-Land is
# 0.1 deg, so 0.2 guarantees the box contains the surrounding cells even if
# the point sits on a cell edge. Kept small to keep the download tiny.
AREA_HALF_DEG = 0.2

# Where the downloaded NetCDF is written. Cached so re-runs for the same
# request do not re-download; delete the file to force a fresh pull.
OUTPUT_DIR = "."                                   # "." = current working directory
DOWNLOAD_FILENAME = "era5land_wind_subset.nc"      # NetCDF container for the CDS subset

# CDS dataset + variable identifiers. These are fixed ERA5-Land strings;
# change them only if you deliberately want different variables.
CDS_DATASET = "reanalysis-era5-land"                       # the ERA5-Land hourly product
VAR_U = "10m_u_component_of_wind"                          # eastward  wind at 10 m [m/s]
VAR_V = "10m_v_component_of_wind"                          # northward wind at 10 m [m/s]

# ERA5-Land publication lag guard. If TARGET_DATETIME is more recent than
# (now - this many days), the data very likely is not published yet.
PUBLICATION_LAG_DAYS = 90                                  # ~3 months, conservative

# CFD summary conditions output path
SUMMARY_OUT_DIR = os.path.join("out", "Historical Data Summary")
SUMMARY_FILENAME = "wind_summary.json"



# ===========================================================================
# STEP 1 - Sanity/latency guard on the requested time
# ===========================================================================
def check_publication_latency(target_dt):
    """
    Warn if the requested datetime is likely newer than the published record.

    Parameters
    ----------
    target_dt : datetime
        The requested instant (timezone-aware, UTC).

    Returns
    -------
    None
        Prints a warning; does not stop execution (CDS is the final arbiter).
    """
    # datetime.now(timezone.utc): current wall-clock time as a UTC-aware value,
    # so the subtraction below compares like-with-like (both tz-aware).
    now_utc = datetime.now(timezone.utc)

    # The most recent instant we EXPECT to be available in ERA5-Land.
    latest_expected = now_utc - timedelta(days=PUBLICATION_LAG_DAYS)

    # If the request is newer than that expectation, flag it for the user.
    if target_dt > latest_expected:
        print(
            "[WARNING] Requested {0} may be newer than the published ERA5-Land "
            "record (typ. ~{1}-day lag). The CDS request may fail or return "
            "no data.".format(target_dt.isoformat(), PUBLICATION_LAG_DAYS)
        )


# ===========================================================================
# STEP 2 - Download the ERA5-Land subset for the requested hour
# ===========================================================================
def download_era5land_subset(target_dt, lat, lon, out_path):
    """
    Fetch a small ERA5-Land 10 m u/v subset for a single hour via the CDS API.

    Parameters
    ----------
    target_dt : datetime
        Requested instant (UTC). Rounded to the nearest hour for the request.
    lat, lon : float
        Target point in degrees. Used to build the area box.
    out_path : str
        Filesystem path the NetCDF is written to.

    Returns
    -------
    str
        The path to the downloaded NetCDF (== out_path).
    """
    # Round to the nearest whole hour: ERA5-Land has no sub-hourly data.
    # Adding 30 min then truncating minutes/seconds == round-to-nearest-hour.
    rounded = target_dt + timedelta(minutes=30)                # push toward next hour
    rounded = rounded.replace(minute=0, second=0, microsecond=0)  # truncate to the hour

    # CDS "area" is [North, West, South, East] in degrees. Build a small box
    # centred on the point using the configured half-width.
    area = [
        lat + AREA_HALF_DEG,   # North edge
        lon - AREA_HALF_DEG,   # West edge
        lat - AREA_HALF_DEG,   # South edge
        lon + AREA_HALF_DEG,   # East edge
    ]

    # The CDS request dict. Date/time components are zero-padded strings, which
    # is the format the API expects (e.g. month "04", hour "11:00").
    request = {
        "variable": [VAR_U, VAR_V],                 # only the two wind components
        "year":  "{0:04d}".format(rounded.year),    # 4-digit year,  e.g. "2026"
        "month": "{0:02d}".format(rounded.month),   # 2-digit month, e.g. "04"
        "day":   "{0:02d}".format(rounded.day),     # 2-digit day,   e.g. "25"
        "time":  "{0:02d}:00".format(rounded.hour), # HH:00,         e.g. "11:00"
        "area":  area,                              # spatial subset box (above)
        "data_format": "netcdf",                    # current CDS key (was "format")
        "download_format": "unarchived",             # plain .nc; default zips the file
    }

    # cdsapi.Client(): reads credentials from ~/.cdsapirc automatically.
    client = cdsapi.Client()

    # .retrieve(dataset, request, target): submits the job, waits in the CDS
    # queue, then downloads the result to `out_path`. Can take seconds-minutes.
    print("[INFO] Requesting ERA5-Land subset for {0} ...".format(rounded.isoformat()))
    client.retrieve(CDS_DATASET, request, out_path)
    print("[INFO] Downloaded to {0}".format(out_path))

    return out_path


# ===========================================================================
# STEP 3 - Read the subset and select the nearest cell + nearest hour
# ===========================================================================
def select_point(nc_path, target_dt, lat, lon):
    """
    Open the NetCDF and extract u/v at the grid cell + hour nearest the target.

    Parameters
    ----------
    nc_path : str
        Path to the downloaded NetCDF.
    target_dt : datetime
        Requested instant (UTC).
    lat, lon : float
        Requested point in degrees.

    Returns
    -------
    dict
        Requested vs. actual coordinates plus the u and v scalars (floats).
    """
    # xr.open_dataset(): lazily opens the NetCDF into an xarray Dataset.
    # `with` guarantees the file handle is released afterwards.
    with xr.open_dataset(nc_path) as ds:

        # ERA5-Land NetCDFs name their coords "latitude"/"longitude"; newer
        # CDS files use a single time coord called "valid_time" (older: "time").
        # Pick whichever exists so the script works across CDS versions.
        time_name = "valid_time" if "valid_time" in ds.coords else "time"

        # np.datetime64: xarray compares times as numpy datetimes. Strip the
        # tzinfo (make naive UTC) because numpy datetime64 is timezone-naive.
        target_np = np.datetime64(target_dt.replace(tzinfo=None))

        # .sel(..., method="nearest"): snap each requested coordinate to the
        # closest available grid value instead of requiring an exact match.
        # Done in one call across the three dims so all snapping is explicit.
        point = ds.sel(
            latitude=lat,             # nearest ERA5-Land row
            longitude=lon,            # nearest ERA5-Land column
            **{time_name: target_np}, # nearest available hour (dynamic key)
            method="nearest",
        )

        # Pull the actual snapped coordinate values back out for reporting.
        # float(...) converts the 0-d xarray scalar to a plain Python float.
        actual_lat = float(point["latitude"].values)
        actual_lon = float(point["longitude"].values)
        # The time value is datetime64; str() gives a clean ISO-ish string.
        actual_time = str(point[time_name].values)

        # Extract the u/v scalars. ERA5-Land variable short-names in NetCDF are
        # "u10" and "v10" (the CDS shortName), regardless of the long request
        # names above. .values -> numpy scalar -> float() -> Python float.
        u = float(point["u10"].values)   # eastward  component [m/s]
        v = float(point["v10"].values)   # northward component [m/s]

    # Return everything the caller needs, keeping requested vs actual distinct.
    return {
        "req_lat": lat, "req_lon": lon, "req_time": target_dt.isoformat(),
        "act_lat": actual_lat, "act_lon": actual_lon, "act_time": actual_time,
        "u": u, "v": v,
    }


# ===========================================================================
# STEP 4 - Convert u/v to speed and meteorological direction
# ===========================================================================
def uv_to_speed_direction(u, v):
    """
    Convert eastward/northward wind components to speed and MET "from" bearing.

    Convention (IMPORTANT for CFD):
      * u = eastward component, v = northward component (ERA5 convention).
      * Returned direction is METEOROLOGICAL: the compass bearing the wind
        blows FROM, measured clockwise from true north (0 = N, 90 = E,
        180 = S, 270 = W).
      * A CFD inlet velocity VECTOR usually points in the direction the wind
        blows TOWARD, which is this bearing + 180 deg. Convert if your solver
        expects the "toward" direction — do not feed the "from" bearing blind.

    Parameters
    ----------
    u, v : float
        10 m wind components in m/s.

    Returns
    -------
    tuple(float, float)
        (speed_m_s, direction_from_deg)
    """
    # Wind speed magnitude: hypot(u, v) == sqrt(u**2 + v**2), numerically safe.
    speed = float(np.hypot(u, v))

    # Meteorological "from" direction.
    #   atan2(u, v) gives the angle of the (u,v) vector measured clockwise from
    #   north = the direction the wind blows TOWARD. Adding 180 flips it to the
    #   direction it comes FROM. math.degrees converts rad->deg. % 360 wraps
    #   the result into the [0, 360) range.
    direction_from = (math.degrees(math.atan2(u, v)) + 180.0) % 360.0

    return speed, direction_from

def export_json(wind_summary,summary_out_path):

    with open(summary_out_path, "w") as f:
        json.dump(wind_summary, f, indent=2)


    
    


# ===========================================================================
# MAIN - orchestrate the steps and print the inlet condition
# ===========================================================================
def main():
    """Run the full pipeline for the configured datetime and point."""

    # Resolve the download path once, from the config values.
    out_path = os.path.join(OUTPUT_DIR, DOWNLOAD_FILENAME)

    # 1) Warn early if the requested time is probably not published yet.
    check_publication_latency(TARGET_DATETIME)

    # 2) Download only if we do not already have the file cached locally.
    #    os.path.exists() avoids re-queuing an identical CDS request.
    if not os.path.exists(out_path):
        download_era5land_subset(TARGET_DATETIME, LAT, LON, out_path)
    else:
        print("[INFO] Using cached download: {0}".format(out_path))

    # 3) Select nearest cell + hour and pull the raw u/v components.
    res = select_point(out_path, TARGET_DATETIME, LAT, LON)

    # 4) Derive the inlet speed + direction from the components.
    speed, direction_from = uv_to_speed_direction(res["u"], res["v"])

    # ---- Report -----------------------------------------------------------
    # Requested vs. actual makes the nearest-neighbour snapping transparent.
    print("\n=== ERA5-Land 10 m wind inlet ===")
    print("Requested : lat {0:.4f}, lon {1:.4f}, {2}".format(
        res["req_lat"], res["req_lon"], res["req_time"]))
    print("Actual    : lat {0:.4f}, lon {1:.4f}, {2}".format(
        res["act_lat"], res["act_lon"], res["act_time"]))
    print("-" * 33)
    print("u (east)  : {0:+.3f} m/s".format(res["u"]))
    print("v (north) : {0:+.3f} m/s".format(res["v"]))
    print("speed     : {0:.3f} m/s".format(speed))
    print("direction : {0:.1f} deg (MET, blows FROM, cw from N)".format(direction_from))
    print("=" * 33)

    wind_summary = {
        "u": res["u"], "v": res["v"],
        "speed": speed, "direction_from_deg": direction_from,
        "actual_lat": res["act_lat"], "actual_lon": res["act_lon"],
        "actual_time": res["act_time"],
    }

    # 5) Persist the summary so it can be picked up by a CFD case writer.
    os.makedirs(SUMMARY_OUT_DIR, exist_ok=True)
    summary_out_path = os.path.join(SUMMARY_OUT_DIR, SUMMARY_FILENAME)
    export_json(wind_summary, summary_out_path)
    print("[INFO] Wrote wind summary to {0}".format(summary_out_path))

    # Return the dict so this can also be imported and called programmatically
    # (e.g. to feed the numbers straight into a CFD case writer).
    return wind_summary




# Standard Python entry-point guard: run main() only when this file is
# executed directly, not when it is imported as a module.
if __name__ == "__main__":
    main()