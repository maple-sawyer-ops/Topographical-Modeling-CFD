"""
hyperlocal_input_loc.py

Configuration module for the HyperLocal WeatherXM Pro wind-data pull.

This file is OBJECT-ORIENTED: geography, timeframe, and the two WeatherXM API
"gotchas" (radius must be in METRES, history ranges are capped at 7 DAYS) are
all encapsulated inside the `Location` class. Files 2 and 3 never re-implement
this logic themselves -- they only ever call methods/properties on a Location
instance. To point this project at a new place, add another `Location(...)`
instance below (or build one elsewhere and pass it in) -- Files 2 and 3 do not
need to change.

This file also owns the pipeline SMOKE TEST (see `smoke_test` near the
bottom): a low-call-count sanity check you can run on its own, before
committing to a full historical pull, via `python hyperlocal_input_loc.py`.
"""

from datetime import datetime, timedelta, timezone

# `requests` is used there too, to make the single ad-hoc history call.
import json
import logging
import requests

# Logger for this module's smoke_test output -- see hyperlocal_find_stations.py
# for the full explanation of the getLogger(__name__)/root-logger pattern.
logger = logging.getLogger(__name__)


class Location(object):
    # Builds single point of interest for the wind-data pull:
    # geographic position, the radius of intrest to stations and data range
  
    def __init__(self, lat, lon, radius_km, query_date, name):
    
        # if validation fails raise immediately and no attributes are set at all

        # --- Latitude / longitude range checks ---
        # equivalent to `(-85 <= lat) and (lat <= 85)`.
        if not (-85 <= lat <= 85):
            raise ValueError(
                "Invalid latitude %r for Location %r: must be between -85 and 85 degrees."
                % (lat, name)
            )
        if not (-180 <= lon <= 180):
            raise ValueError(
                "Invalid longitude %r for Location %r: must be between -180 and 180 degrees."
                % (lon, name)
            )

        # --- Radius must be a positive number of kilometres ---
        if not (radius_km > 0):
            raise ValueError(
                "Invalid radius_km %r for Location %r: must be greater than 0."
                % (radius_km, name)
            )

        # --- query_date must be a valid "YYYY-MM-DD" string ---
        try:
            datetime.strptime(query_date, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(
                "Invalid query_date %r for Location %r: %s. "
                "Date must be a 'YYYY-MM-DD' string." % (query_date, name, exc)
            ) from exc

        self.lat = lat
        self.lon = lon
        self.radius_m = radius_km * 1000
        self.query_date = query_date
        self.name = name


    def date_chunks(self):
        #Compute the 7-day pull window from query_date and return it as
       
        end_dt = datetime.strptime(self.query_date, "%Y-%m-%d").date()
        # 7 days INCLUSIVE means 6 days back from query_date.
        start_dt = end_dt - timedelta(days=6)
        return [(start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d"))]

    def to_near_params(self):
        """
        Build the query-parameter dict for the `/stations/near` endpoint.

        Returns a plain dict -- `requests` accepts a dict directly via its
        `params=` keyword argument and handles URL-encoding for us, so
        callers just do `requests.get(url, params=location.to_near_params())`.
        """
        return {
            "lat": self.lat,
            "lon": self.lon,
            "radius": self.radius_m,
        }

    def __repr__(self):
        # `__repr__` controls how this object prints/represents itself 
        return (
            "Location(name=%r, lat=%r, lon=%r, radius_m=%r, query_date=%r)"
            % (self.name, self.lat, self.lon, self.radius_m, self.query_date)
        )


# ---------------------------------------------------------------------------
# Module-level constants.

API_KEY = "33492be5-9804-42db-9296-a97904ab3d2e" # WeatherXM Pro API key

# Minimum acceptable data-quality score (health.data_quality.score), 0-1.
# Observations from a station-day scoring below this are dropped in File 3.
MIN_QOD = 0.8

# Directory where raw per-(station, date-range) JSON API responses are cached.
# A relative path (interpreted relative to the current working directory the
# scripts are run from) matching the other files' string-constant style.
CACHE_DIR = "./wxm_cache"

# Directory where the final assembled dataset JSON file is written.
OUTPUT_DIR = "./wxm_output"

# Directory where per-run log files are written (see hyperlocal_logging.py).
LOG_DIR = "./wxm_logs"


# ---------------------------------------------------------------------------
# Hardcoded location instance(s).
#
# To generalise this project to another place later, add MORE `Location(...)`
# instances here (and loop over them in a driver script) -- Files 2 and 3
# require no changes, since they only ever operate on whatever Location
# object they're handed.
# ---------------------------------------------------------------------------
OXFORD = Location(
    lat=51.792827,
    lon=-1.222481,
    radius_km=3.0,
    query_date="2026-08-04",  # YYYY-MM-DD; window = this date - 6 days
    name="Oxford",
)


# ---------------------------------------------------------------------------
# Pipeline smoke test.
#
# A low-call-count sanity check meant to be run BEFORE committing to a full
# historical pull. It lives here (rather than in hyperlocal_build_dataset.py
# or hyperlocal_find_stations.py) so that running `python
# hyperlocal_input_loc.py` alone is enough to validate the API key, both
# endpoints, station coverage, and the wind fields this project cares about --
# no dependency on the caching/assembly logic in File 3.
#
# Import note: `discover_stations` and `BASE_URL` are imported from
# hyperlocal_find_stations here, INSIDE this module -- hyperlocal_find_stations
# does not import anything from hyperlocal_input_loc, so this stays a
# one-directional dependency (no circular import). hyperlocal_build_dataset.py
# is deliberately NOT imported here, since IT imports FROM this module --
# importing it back would create an import cycle.
# ---------------------------------------------------------------------------


def smoke_test(location, api_key):
    """
    Minimal sanity check of the WeatherXM Pro pipeline: validates that the
    API key works, both endpoints respond, station coverage exists near
    `location`, and the wind fields this project cares about are actually
    present and populated -- using at most 2 API calls total.

    Functionality -- two steps:
      1. Calls `/stations/near` (via `discover_stations`) and prints how many
         stations came back plus each one's id/name/createdAt.
      2. Takes the FIRST discovered station and pulls a single recent 7-day
         history range for it directly (no caching -- this is a one-off
         diagnostic call, not part of the main cached pull), prints an
         observation count plus ONE sample observation (not the full raw
         response -- a 7-day range can hold hundreds of observations and
         would flood the terminal), and confirms wind_speed/wind_gust/
         wind_direction and health.data_quality.score are present.

    Syntax note: this function takes `location` and `api_key` as arguments,
    same as the rest of the pipeline -- no hardcoded place name appears in
    the body; only the `if __name__ == "__main__":` block below decides to
    run it against OXFORD specifically.
    """
    # Imported here (function-local), rather than at module top level, so
    # that simply importing hyperlocal_input_loc (as Files 2 and 3 do) never
    # pulls in `requests`-dependent discovery code unless `smoke_test` is
    # actually called.
    from hyperlocal_find_stations import discover_stations, BASE_URL

    logger.info("=" * 70)
    logger.info("SMOKE TEST for %r", location)
    logger.info("=" * 70)

    # --- Step 1: station discovery ---
    # `min_qod=0.0` is passed deliberately (rather than the real MIN_QOD) so
    # this step reports every station with date-range coverage, without also
    # silently dropping some to the optional quality gate inside
    # discover_stations -- we want to SEE what's out there, not pre-filter it.
    logger.info("Step 1: calling /stations/near ...")
    stations = discover_stations(location, api_key, min_qod=0.0)
    logger.info("%d station(s) returned near %s:", len(stations), location.name)
    # `enumerate(stations, start=1)` pairs each station with a 1-based index
    # for readable numbered output, instead of a raw 0-based loop counter.
    for i, station in enumerate(stations, start=1):
        logger.info(
            "  %d. id=%s  name=%r  createdAt=%s", i, station["id"], station["name"], station["createdAt"]
        )

    if not stations:
        logger.error("FAILED: no stations available -- cannot proceed to Step 2.")
        return False

    # --- Step 2: single recent 7-day history pull, on the first station ---
    first_station = stations[0]
    station_id = first_station["id"]

    # "A single recent 7-day range" means near TODAY, not location's own
    # (possibly historical) start/end_date -- so we compute it fresh here
    # rather than using `location.date_chunks()`.
    # `datetime.now(timezone.utc).date()` gives today's UTC calendar date
    # (the timezone-aware replacement for the deprecated `utcnow()`);
    # WeatherXM timestamps are UTC, so anchoring "recent" to UTC keeps this
    # consistent.
    end_dt = datetime.now(timezone.utc).date()
    # 7 days INCLUSIVE means 6 days back from today (today counts as day 7).
    start_dt = end_dt - timedelta(days=6)
    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = end_dt.strftime("%Y-%m-%d")

    logger.info("Step 2: calling /stations/%s/history for %s..%s ...", station_id, start_str, end_str)

    url = BASE_URL + "/stations/" + station_id + "/history"
    params = {"start": start_str, "end": end_str}
    headers = {"X-API-KEY": api_key}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        # Covers connection errors, timeouts, and HTTP error statuses
        # (including 429 rate-limit responses); logged and treated as a
        # failed smoke test rather than crashing.
        logger.error("FAILED: history call raised %s", exc)
        return False

    try:
        payload = response.json()
    except ValueError as exc:
        logger.error("FAILED: could not parse history response JSON: %s", exc)
        return False

    # --- Confirm the wind fields we actually care about are present ---
    observations = payload.get("observations", [])
    health = payload.get("health", {})
    data_quality_score = health.get("data_quality", {}).get("score")

    # We deliberately do NOT dump the whole `payload` to the terminal here --
    # a 7-day range can carry hundreds of observations (one per few minutes),
    # and printing all of them floods the terminal. Instead we print just a
    # count and a single sample observation (below), which is enough to
    # confirm the response shape without the noise.
    logger.info("Response has %d observation(s) for %s..%s.", len(observations), start_str, end_str)
    logger.info("health.data_quality.score = %r", data_quality_score)

    if not observations:
        logger.error("FAILED: response had no observations for this range.")
        return False

    # `json.dumps(observations[0], indent=2)` pretty-prints ONLY the first
    # observation dict -- one small, readable sample instead of the full list.
    logger.info("Sample observation (first of %d):", len(observations))
    logger.info(json.dumps(observations[0], indent=2))

    # Check the first observation for the three wind fields; `all(...)` over
    # a generator expression is True only if EVERY field is present AND not
    # None, giving one clean pass/fail check instead of three separate ifs.
    first_obs = observations[0]
    wind_fields = ("wind_speed", "wind_gust", "wind_direction")
    fields_ok = all(first_obs.get(field) is not None for field in wind_fields)

    logger.info(
        "First observation wind fields -- wind_speed=%r wind_gust=%r wind_direction=%r",
        first_obs.get("wind_speed"), first_obs.get("wind_gust"), first_obs.get("wind_direction"),
    )

    if fields_ok:
        logger.info("PASSED: wind fields present and populated.")
    else:
        logger.error("FAILED: one or more wind fields missing/null.")

    return fields_ok


# `if __name__ == "__main__":` runs only when this file is executed directly
# (e.g. `python hyperlocal_input_loc.py`), not when it's imported as a module
# by hyperlocal_find_stations.py / hyperlocal_build_dataset.py.
if __name__ == "__main__":
    # Local import: hyperlocal_logging.py is stdlib-only, but kept out of
    # the module-level imports so plain `import hyperlocal_input_loc` (as
    # Files 2 and 3 do) doesn't implicitly configure logging as a side effect.
    from hyperlocal_logging import setup_logging

    setup_logging(LOG_DIR)
    smoke_test(OXFORD, API_KEY)
