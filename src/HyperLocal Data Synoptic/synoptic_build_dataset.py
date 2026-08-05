"""
synoptic_build_dataset.py

Pulls wind data for every Synoptic station within a Location's radius in a
single `/stations/timeseries` call, and assembles it into one flat JSON
dataset. See READ_ME_SYNOPTIC.md for run order and provider differences vs.
the WeatherXM pipeline.
"""

import json
import logging
from pathlib import Path

import requests

from synoptic_input_location import OXFORD, API_TOKEN, WIND_VARS, CACHE_DIR, OUTPUT_DIR, LOG_DIR
from synoptic_logging import setup_logging

logger = logging.getLogger(__name__)

BASE_URL = "https://api.synopticdata.com/v2/stations/timeseries"


def _cache_path(cache_dir, location, start, end):
    filename = "%s_%s_%s.json" % (location.name.lower(), start, end)
    return Path(cache_dir) / filename


def _fetch_timeseries(location, api_token, cache_dir):
    """
    One combined discover+pull call: Synoptic's `radius` selector on
    `/stations/timeseries` returns every nearby station's observations in
    one response, so (unlike WeatherXM) there's no separate per-station
    loop or 7-day chunking needed here.

    Returns the parsed JSON payload, or None on failure. Cache-first, keyed
    on (location, start, end).
    """
    time_params = location.to_time_params()
    cache_file = _cache_path(cache_dir, location, time_params["start"], time_params["end"])

    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("Cache file %s unreadable (%s); re-fetching from API.", cache_file, exc)

    params = {
        "token": api_token,
        "radius": location.to_radius_param(),
        "vars": WIND_VARS,
        "units": "metric",
        "qc": "on",
        "qc_flags": "on",
        **time_params,
    }

    try:
        response = requests.get(BASE_URL, params=params, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("FAILED timeseries call for %s: %s", location.name, exc)
        return None

    try:
        payload = response.json()
    except ValueError as exc:
        logger.error("FAILED to parse JSON for %s: %s", location.name, exc)
        return None

    try:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(payload), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write cache file %s: %s", cache_file, exc)

    return payload


def build_dataset_for_location(location, api_token, cache_dir, output_dir):
    """
    Fetch + flatten the Synoptic timeseries response for `location`, writing
    the result to `output_dir`.
    """
    logger.info("=" * 70)
    logger.info("Building dataset for %r", location)
    logger.info("=" * 70)

    payload = _fetch_timeseries(location, api_token, cache_dir)

    all_records = []
    stations_with_data = set()

    if payload is not None:
        stations = payload.get("STATION", [])
        logger.info("%d station(s) returned near %s.", len(stations), location.name)

        for station in stations:
            station_id = station.get("STID")
            station_name = station.get("NAME")
            obs = station.get("OBSERVATIONS", {})
            timestamps = obs.get("date_time", [])

            # Synoptic suffixes each requested var with its "set" number
            # (e.g. "wind_speed_set_1"); grab the first matching key per
            # field rather than hardcoding "_set_1", since not every
            # station/var is guaranteed to use set 1.
            def _series_for(field):
                for key, series in obs.items():
                    if key.startswith(field):
                        return series
                return None

            wind_speed = _series_for("wind_speed") or []
            wind_gust = _series_for("wind_gust") or []
            wind_direction = _series_for("wind_direction") or []

            if timestamps:
                stations_with_data.add(station_id)

            for i, ts in enumerate(timestamps):
                all_records.append(
                    {
                        "station_id": station_id,
                        "station_name": station_name,
                        "timestamp": ts,
                        "wind_speed": wind_speed[i] if i < len(wind_speed) else None,
                        "wind_gust": wind_gust[i] if i < len(wind_gust) else None,
                        "wind_direction": wind_direction[i] if i < len(wind_direction) else None,
                    }
                )
    else:
        logger.error("No payload for %s; writing empty dataset.", location.name)

    all_records_sorted = sorted(all_records, key=lambda r: (r["station_id"], r["timestamp"]))

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_file = Path(output_dir) / ("%s_wind_dataset.json" % location.name.lower())
    output_file.write_text(json.dumps(all_records_sorted, indent=2), encoding="utf-8")

    logger.info("-" * 70)
    logger.info("RUN SUMMARY for %s", location.name)
    logger.info("-" * 70)
    logger.info("Stations with usable data:  %d", len(stations_with_data))
    logger.info("Observations kept:          %d", len(all_records_sorted))
    logger.info("Output written to:          %s", output_file)
    logger.info("-" * 70)

    return all_records_sorted


if __name__ == "__main__":
    setup_logging(LOG_DIR)
    build_dataset_for_location(
        location=OXFORD,
        api_token=API_TOKEN,
        cache_dir=CACHE_DIR,
        output_dir=OUTPUT_DIR,
    )
