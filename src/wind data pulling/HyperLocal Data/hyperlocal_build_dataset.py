"""
hyperlocal_build_dataset.py

Pulls per-station WeatherXM Pro history, assembles it into one flat JSON
dataset. See READ_ME_WEATHERXM.md in this folder for run order, the
metres/7-day API gotchas, rate-limit behaviour, and full code structure.
"""

# Standard-library imports only, besides `requests` (the one allowed
# third-party dependency).
import json
import time
from pathlib import Path

# `requests` is used directly here (not just inside hyperlocal_find_stations)
# because this file makes its own HTTP calls to the /history endpoint.
import requests

# Config: the hardcoded Location instance plus account-level run settings.
from hyperlocal_input_loc import OXFORD, API_KEY, MIN_QOD, CACHE_DIR, OUTPUT_DIR

# Station discovery function from File 2.
from hyperlocal_find_stations import discover_stations, BASE_URL


# Small pause between consecutive history calls so we don't hammer the API
# back-to-back; this is a courtesy delay, independent of any specific quota.
SLEEP_BETWEEN_CALLS_SECONDS = 0.5


def _cache_path(cache_dir, station_id, start, end):
    """
    Build the on-disk cache file path for one station+date-range history call.

    Functionality: every (station_id, start, end) combination maps to exactly
    one cache file, named "{station_id}_{start}_{end}.json" inside cache_dir.
    Because start/end are already "YYYY-MM-DD" strings, the resulting
    filename is both unique and human-readable.

    Syntax: `Path(cache_dir)` wraps the string path in a `pathlib.Path`
    object, which overloads the `/` operator to join path segments (this is
    NOT division -- `Path.__truediv__` is defined to do path-joining instead,
    so `Path(cache_dir) / "foo.json"` produces a new Path pointing at
    "<cache_dir>/foo.json" in an OS-appropriate way, e.g. using backslashes
    on Windows).
    """
    filename = "%s_%s_%s.json" % (station_id, start, end)
    return Path(cache_dir) / filename


def _fetch_history(station_id, start, end, api_key, cache_dir, stats):
    """
    Fetch one station's history for one <=7-day (start, end) chunk, using the
    on-disk cache when available.

    Parameters
    ----------
    station_id : str
    start, end : str
        "YYYY-MM-DD" strings; caller (build_dataset_for_location) is
        responsible for ensuring the range is <=7 days, since that's the
        Location class's job via `date_chunks()`.
    api_key : str
    cache_dir : str
        Directory path (as a string) where cache JSON files live.
    stats : dict
        A shared mutable dict this function increments in place to track
        "api_calls" vs "cache_hits" vs "failures" across the whole run.
        Passing a dict (a mutable object) lets this helper report back to
        the caller without needing a return-value tuple for bookkeeping --
        the caller and this function share the SAME dict object in memory.

    Returns
    -------
    dict or None
        The parsed JSON response body, or None if the data wasn't available
        (cache miss AND the API call failed) -- callers must check for None.
    """
    cache_file = _cache_path(cache_dir, station_id, start, end)

    # --- Cache-first: if we've already fetched this station+range, use it ---
    if cache_file.exists():
        try:
            # `.read_text(encoding="utf-8")` reads the whole file as a
            # decoded string; `json.loads(...)` parses that string into
            # Python objects (dicts/lists/etc).
            cached_text = cache_file.read_text(encoding="utf-8")
            stats["cache_hits"] += 1
            return json.loads(cached_text)
        except (OSError, ValueError) as exc:
            # `OSError` covers file-read problems; `ValueError` covers
            # malformed JSON in the cache file. Either way we fall through
            # and re-fetch from the API rather than crashing on a corrupt
            # cache entry.
            print(
                "[_fetch_history] Cache file %s unreadable (%s); re-fetching from API."
                % (cache_file, exc)
            )

    # --- Not cached (or cache was unreadable): call the API ---
    url = BASE_URL + "/stations/" + station_id + "/history"
    params = {"start": start, "end": end}
    headers = {"X-API-KEY": api_key}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        # Covers connection errors, timeouts, and HTTP error statuses
        # (including 429 rate-limit responses) -- all logged and treated as
        # "this one call failed", not a fatal error for the whole run.
        print(
            "[_fetch_history] FAILED history call for station=%s range=%s..%s: %s"
            % (station_id, start, end, exc)
        )
        stats["failures"] += 1
        stats["api_calls"] += 1
        return None

    stats["api_calls"] += 1

    try:
        payload = response.json()
    except ValueError as exc:
        print(
            "[_fetch_history] FAILED to parse JSON for station=%s range=%s..%s: %s"
            % (station_id, start, end, exc)
        )
        stats["failures"] += 1
        return None

    # --- Write-through to cache so future runs skip the API call entirely ---
    try:
        # `cache_dir` might not exist yet on a fresh checkout; `Path(...).mkdir(
        # parents=True, exist_ok=True)` creates it (and any missing parent
        # directories) without raising if it already exists.
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        # `json.dumps(payload)` serializes the parsed Python object back into
        # a JSON string; we write exactly what we parsed so the cache is a
        # faithful copy of the raw API response.
        cache_file.write_text(json.dumps(payload), encoding="utf-8")
    except OSError as exc:
        # Failing to WRITE the cache shouldn't discard data we already
        # successfully fetched -- log it and continue using `payload` as-is.
        print(
            "[_fetch_history] WARNING: could not write cache file %s: %s"
            % (cache_file, exc)
        )

    # Courtesy delay before the NEXT call this function's caller makes.
    time.sleep(SLEEP_BETWEEN_CALLS_SECONDS)

    return payload


def build_dataset_for_location(location, api_key, min_qod, cache_dir, output_dir):
    """
    Run the full discovery + history-pull + assembly pipeline for one
    `Location`, writing the resulting flat dataset to `output_dir`.

    This is the function that ties Files 1-3 together. It takes `location`,
    `api_key`, `min_qod`, `cache_dir`, `output_dir` as ARGUMENTS (rather than
    importing OXFORD/API_KEY/etc. and using them directly in its body), which
    is what lets this function be reused for any Location later -- the
    `if __name__ == "__main__":` block below is the only place that actually
    decides "run this for OXFORD".
    """
    # `stats` is a plain dict used as shared, mutable run-summary state,
    # passed into `_fetch_history` so it can increment counters in place.
    stats = {"api_calls": 0, "cache_hits": 0, "failures": 0}

    print("=" * 70)
    print("Building dataset for %r" % location)
    print("=" * 70)

    # --- Step 1: discover stations near this location ---
    stations = discover_stations(location, api_key, min_qod)
    print("[build_dataset] %d station(s) available for %s." % (len(stations), location.name))

    # --- Step 2: get the <=7-day date chunks for this location's range ---
    # We do NOT compute chunking logic here -- `location.date_chunks()` owns
    # that, per the class's encapsulation of the 7-day API gotcha.
    chunks = location.date_chunks()
    print(
        "[build_dataset] Date range %s..%s split into %d chunk(s) of <=7 days."
        % (location.start_date, location.end_date, len(chunks))
    )

    all_records = []
    stations_with_data = set()
    observations_dropped_quality = 0

    # `for station in stations:` outer loop, `for (start, end) in chunks:`
    # inner loop -- together these produce one `_fetch_history` call per
    # station PER CHUNK, i.e. len(stations) * len(chunks) calls at most
    # (fewer once caching kicks in on a re-run).
    for station in stations:
        station_id = station["id"]

        for (start, end) in chunks:
            payload = _fetch_history(station_id, start, end, api_key, cache_dir, stats)

            if payload is None:
                # Already logged inside _fetch_history; nothing more to do
                # for this station+chunk.
                continue

            # `.get("health", {})` defaults to an empty dict if "health" is
            # missing from the payload, so the subsequent `.get(...)` calls
            # below don't raise KeyError on a malformed/partial response.
            health = payload.get("health", {})
            data_quality = health.get("data_quality", {})
            location_quality = health.get("location_quality", {})

            data_quality_score = data_quality.get("score")
            location_quality_score = location_quality.get("score")

            # --- Quality gate: drop this whole station-day's observations
            #     if data_quality_score is below MIN_QOD ---
            # `data_quality_score is None` guards against a payload that
            # omits the score entirely; we treat "unknown quality" as NOT
            # passing the gate (safer default than silently keeping it).
            if data_quality_score is None or data_quality_score < min_qod:
                observations_list = payload.get("observations", [])
                observations_dropped_quality += len(observations_list)
                continue

            observations = payload.get("observations", [])
            if observations:
                stations_with_data.add(station_id)

            # `for obs in observations:` iterates each observation dict in
            # this station-day's response.
            for obs in observations:
                # Build one flat output record per observation, keeping only
                # the wind-focused fields the spec asks for (plus the two
                # quality scores, carried alongside each record so
                # downstream consumers can re-filter/weight without
                # re-fetching).
                all_records.append(
                    {
                        "station_id": station_id,
                        "timestamp": obs.get("timestamp"),
                        "wind_speed": obs.get("wind_speed"),
                        "wind_gust": obs.get("wind_gust"),
                        "wind_direction": obs.get("wind_direction"),
                        "data_quality_score": data_quality_score,
                        "location_quality_score": location_quality_score,
                    }
                )

    # --- Step 3: sort the flat record list by station_id, then timestamp ---
    # `sorted(iterable, key=...)` returns a NEW sorted list without mutating
    # the input; `key=lambda r: (r["station_id"], r["timestamp"])` sorts by
    # a tuple, so records are grouped by station_id first and ordered by
    # timestamp within each group (tuple comparison in Python compares
    # element-by-element, left to right).
    all_records_sorted = sorted(all_records, key=lambda r: (r["station_id"], r["timestamp"]))

    # --- Step 4: write the combined dataset to OUTPUT_DIR ---
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_file = Path(output_dir) / ("%s_wind_dataset.json" % location.name.lower())
    # `json.dumps(..., indent=2)` pretty-prints the JSON with 2-space
    # indentation, trading a larger file size for human readability.
    output_file.write_text(json.dumps(all_records_sorted, indent=2), encoding="utf-8")

    # --- Step 5: print the run summary ---
    print("-" * 70)
    print("RUN SUMMARY for %s" % location.name)
    print("-" * 70)
    print("Stations discovered:              %d" % len(stations))
    print("Stations with usable history:     %d" % len(stations_with_data))
    print("Date chunks processed:            %d" % len(chunks))
    print("Observations kept:                %d" % len(all_records_sorted))
    print("Observations dropped (quality):   %d" % observations_dropped_quality)
    print("API calls made:                   %d" % stats["api_calls"])
    print("Served from cache:                %d" % stats["cache_hits"])
    print("Failed calls:                     %d" % stats["failures"])
    print("Output written to:                %s" % output_file)
    print("-" * 70)

    return all_records_sorted


# `if __name__ == "__main__":` is Python's standard "only run this when the
# file is executed directly (e.g. `python hyperlocal_build_dataset.py`), not
# when it's imported as a module elsewhere" guard. `__name__` is a built-in
# variable Python sets to "__main__" for the script that was launched, and to
# the module's own name when it's imported instead.
if __name__ == "__main__":
    # This is the ONE place in the whole project that decides "run for
    # OXFORD" -- build_dataset_for_location itself takes location as an
    # argument, so pointing this at a different place later means adding a
    # new Location in hyperlocal_input_loc.py and passing it here instead
    # (or looping over several).
    build_dataset_for_location(
        location=OXFORD,
        api_key=API_KEY,
        min_qod=MIN_QOD,
        cache_dir=CACHE_DIR,
        output_dir=OUTPUT_DIR,
    )
