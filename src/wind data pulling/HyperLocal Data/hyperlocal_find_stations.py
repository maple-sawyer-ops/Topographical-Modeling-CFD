"""
hyperlocal_find_stations.py

Station-discovery module for the HyperLocal WeatherXM Pro wind-data pull.

Given a `Location` object (see hyperlocal_input_loc.py), `discover_stations`
calls the WeatherXM Pro `/stations/near` endpoint, filters the result down to
stations that can actually contribute data for the requested date range, and
returns a plain list of small dicts for File 3 to consume.

Nothing in this file references "Oxford" or any hardcoded place -- everything
comes in through the `location` argument, so this module works unchanged for
any Location instance.
"""

# `requests` is a third-party HTTP client library; it is the one non-stdlib
# dependency this project uses, per the project requirements.
import requests

# `datetime` is used to parse the "createdAt" ISO8601 timestamp WeatherXM
# returns for each station, so it can be compared against the Location's
# start_date.
from datetime import datetime


# Base URL for the WeatherXM Pro API. Kept as a module constant so it's
# defined once and reused by every endpoint call in this file.
BASE_URL = "https://pro.weatherxm.com/api/v1"


def _parse_created_at(created_at_str):
    """
    Parse a WeatherXM `createdAt` ISO8601 timestamp string into a `date`.

    Functionality: WeatherXM timestamps are ISO8601 and commonly end in a
    "Z" suffix (meaning UTC / "Zulu time"), e.g. "2023-05-01T12:00:00Z".
    Python's `datetime.fromisoformat` (on the versions this project targets)
    does not accept a trailing "Z" directly, so we swap it for "+00:00"
    (the explicit UTC offset form) before parsing.

    Syntax: leading underscore in `_parse_created_at` is a Python convention
    (not an enforced rule) signalling "internal helper, not part of this
    module's public API" -- callers outside this file shouldn't rely on it.
    `str.replace("Z", "+00:00")` returns a NEW string (strings are immutable
    in Python) with the substitution applied; it does not mutate the input.
    `.date()` on the resulting `datetime` object strips the time-of-day
    component, leaving just the calendar date for comparison purposes.
    """
    normalized = created_at_str.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized).date()


def discover_stations(location, api_key, min_qod):
    """
    Discover WeatherXM Pro stations near `location` that have data covering
    `location`'s requested date range.

    Parameters
    ----------
    location : hyperlocal_input_loc.Location
        Encapsulates lat/lon/radius/date-range for the search. This function
        calls `location.to_near_params()` rather than building the lat/lon/
        radius query dict itself, so it never has to know about the
        metres-vs-kilometres gotcha -- that's the Location class's job.
    api_key : str
        WeatherXM Pro API key, sent as the `X-API-KEY` header.
    min_qod : float
        Minimum acceptable quality-of-data score (0-1). Applied here ONLY if
        the `/stations/near` response happens to carry a per-station quality
        field; otherwise per-observation quality is enforced later, in File 3,
        via each history response's `health.data_quality.score` block.

    Returns
    -------
    list of dict
        Each dict has keys: "id", "name", "lat", "lon", "createdAt".
        Stations that can't possibly contribute data (created after the
        requested window starts) are excluded.

    Syntax note: this function takes `location`, `api_key`, `min_qod` as
    plain positional/keyword ARGUMENTS rather than importing them from the
    config module directly. That's deliberate -- it keeps this function
    reusable for any Location/key/threshold combination, not just the
    hardcoded OXFORD instance.
    """
    url = BASE_URL + "/stations/near"

    # `location.to_near_params()` returns {"lat": ..., "lon": ..., "radius": ...}
    # with radius ALREADY converted to metres by the Location class.
    params = location.to_near_params()

    # HTTP headers are passed as a dict too; WeatherXM Pro expects the API
    # key under the `X-API-KEY` header name (case-insensitive per the HTTP
    # spec, but we match the documented casing exactly).
    headers = {"X-API-KEY": api_key}

    # --- Make the request, failing gracefully on any transport/HTTP error ---
    try:
        # `requests.get(url, params=..., headers=...)` builds and sends a GET
        # request; `params` values are URL-encoded and appended as a query
        # string automatically (e.g. ?lat=...&lon=...&radius=...).
        response = requests.get(url, params=params, headers=headers, timeout=30)

        # `raise_for_status()` raises a `requests.HTTPError` if the response
        # status code indicates failure (4xx/5xx), including a 429 rate-limit
        # response -- we let the `except` block below catch and log it rather
        # than letting the exception propagate and crash the whole run.
        response.raise_for_status()
    except requests.RequestException as exc:
        # `requests.RequestException` is the base class for every exception
        # `requests` can raise (connection errors, timeouts, HTTP errors,
        # etc.), so catching it here covers all failure modes for this one
        # call. We log and return an empty list rather than propagating,
        # per the "fail gracefully" requirement.
        print(
            "[discover_stations] FAILED to fetch stations near %s: %s"
            % (location.name, exc)
        )
        return []

    # `.json()` parses the response body as JSON into Python objects (dicts/
    # lists/etc). This can itself raise if the body isn't valid JSON, so it's
    # wrapped in its own try/except.
    try:
        payload = response.json()
    except ValueError as exc:
        print(
            "[discover_stations] FAILED to parse JSON for stations near %s: %s"
            % (location.name, exc)
        )
        return []

    # --- Handle both possible response shapes ---
    # The `/stations/near` endpoint's exact response shape isn't guaranteed
    # by this project's spec to be one form or the other, so we handle both:
    #   1. A bare JSON list:      [ {...station...}, {...station...} ]
    #   2. An object with a
    #      "stations" array:      { "stations": [ {...}, {...} ], ... }
    if isinstance(payload, list):
        # `isinstance(payload, list)` checks the runtime type directly.
        raw_stations = payload
    elif isinstance(payload, dict):
        # `.get("stations", [])` looks up the "stations" key, returning an
        # empty list (rather than raising KeyError) if the key is absent --
        # a defensive default for an unexpected object shape.
        raw_stations = payload.get("stations", [])
    else:
        print(
            "[discover_stations] Unexpected response shape for stations near %s: %r"
            % (location.name, type(payload))
        )
        raw_stations = []

    kept_stations = []
    dropped_no_coverage = 0
    dropped_bad_data = 0

    # `for station in raw_stations:` iterates each station object (a dict) in
    # the list we extracted above.
    for station in raw_stations:
        # Defensive per-station try/except: one malformed station record
        # should not abort discovery for every other station.
        try:
            station_id = station["id"]
            name = station["name"]
            # WeatherXM nests lat/lon under a "location" sub-object on each
            # station record; `station["location"]["lat"]` reaches into that
            # nested dict.
            lat = station["location"]["lat"]
            lon = station["location"]["lon"]
            created_at_str = station["createdAt"]
        except (KeyError, TypeError) as exc:
            # `KeyError` if an expected key is missing; `TypeError` if e.g.
            # `station["location"]` isn't a dict at all. Either way, log and
            # skip just this one record.
            print(
                "[discover_stations] Skipping malformed station record %r: %s"
                % (station, exc)
            )
            dropped_bad_data += 1
            continue

        # --- Hard gate: station must have existed before/at start_date ---
        # A station's `createdAt` marks when it STARTED having observations.
        # If that's after the requested window begins, it cannot possibly
        # have any data for that window, so we drop it outright (rather than
        # wasting an API call on it in File 3).
        try:
            created_date = _parse_created_at(created_at_str)
        except ValueError as exc:
            print(
                "[discover_stations] Skipping station %s (%s): unparseable createdAt %r: %s"
                % (station_id, name, created_at_str, exc)
            )
            dropped_bad_data += 1
            continue

        # Compare against location.start_date (the public "YYYY-MM-DD" string
        # attribute) rather than reaching into Location's private parsed-date
        # attribute -- we re-parse it here to respect the class's
        # encapsulation. `datetime.strptime(text, fmt).date()` mirrors the
        # parsing Location itself does internally.
        location_start_date = datetime.strptime(location.start_date, "%Y-%m-%d").date()
        if created_date > location_start_date:
            dropped_no_coverage += 1
            continue

        # --- Optional secondary quality gate ---
        # If this endpoint's station objects happen to carry a quality field
        # such as "lastDayQod", filter on it here too. As of the documented
        # WeatherXM Pro `/stations/near` response, no such field is present,
        # so `.get("lastDayQod")` returns None and this block is skipped --
        # per-observation quality (via each history response's
        # `health.data_quality.score`) is enforced instead, in File 3.
        last_day_qod = station.get("lastDayQod")
        if last_day_qod is not None and last_day_qod < min_qod:
            dropped_bad_data += 1
            continue

        kept_stations.append(
            {
                "id": station_id,
                "name": name,
                "lat": lat,
                "lon": lon,
                "createdAt": created_at_str,
            }
        )

    # --- Log a summary of what was dropped and why ---
    print(
        "[discover_stations] %s: found %d station(s) near location; "
        "kept %d, dropped %d (no coverage before start_date), dropped %d (bad/low-quality data)."
        % (
            location.name,
            len(raw_stations),
            len(kept_stations),
            dropped_no_coverage,
            dropped_bad_data,
        )
    )

    return kept_stations
