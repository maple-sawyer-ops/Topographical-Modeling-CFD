"""
synoptic_input_location.py

Configuration module for the HyperLocal Synoptic wind-data pull.

Synoptic's `/stations/timeseries` endpoint accepts a `radius` selector
directly, so -- unlike the WeatherXM pipeline (see
"HyperLocal Data WeatherXM/"), which needs a separate `/stations/near` call
before it can pull history -- ONE call returns every nearby station's
observations at once. There is no separate "find_stations" module here;
synoptic_build_dataset.py does discovery and pull together.

Two gotchas this `Location` class encapsulates so the build script never has
to re-derive them:
  1. Synoptic's radius is in MILES (WeatherXM's was in metres).
  2. Synoptic's start/end times are UTC strings in "YYYYmmddHHMM" format,
     not ISO dates.
"""

from datetime import datetime, timedelta

logger_name = __name__


class Location(object):
    def __init__(self, lat, lon, radius_mi, query_date, name, days_back=6):
        if not (-90 <= lat <= 90):
            raise ValueError(
                "Invalid latitude %r for Location %r: must be between -90 and 90 degrees."
                % (lat, name)
            )
        if not (-180 <= lon <= 180):
            raise ValueError(
                "Invalid longitude %r for Location %r: must be between -180 and 180 degrees."
                % (lon, name)
            )
        if not (radius_mi > 0):
            raise ValueError(
                "Invalid radius_mi %r for Location %r: must be greater than 0."
                % (radius_mi, name)
            )
        try:
            datetime.strptime(query_date, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(
                "Invalid query_date %r for Location %r: %s. "
                "Date must be a 'YYYY-MM-DD' string." % (query_date, name, exc)
            ) from exc

        self.lat = lat
        self.lon = lon
        self.radius_mi = radius_mi
        self.query_date = query_date
        self.days_back = days_back
        self.name = name

    def to_radius_param(self):
        """Build the `radius=lat,lon,miles` query value Synoptic expects."""
        return "%s,%s,%s" % (self.lat, self.lon, self.radius_mi)

    def to_time_params(self):
        """Return {"start": ..., "end": ...} in Synoptic's UTC
        "YYYYmmddHHMM" format, covering `days_back` days up to query_date
        (end of day)."""
        end_dt = datetime.strptime(self.query_date, "%Y-%m-%d") + timedelta(
            hours=23, minutes=59
        )
        start_dt = end_dt - timedelta(days=self.days_back, hours=23, minutes=59)
        return {
            "start": start_dt.strftime("%Y%m%d%H%M"),
            "end": end_dt.strftime("%Y%m%d%H%M"),
        }

    def __repr__(self):
        return (
            "Location(name=%r, lat=%r, lon=%r, radius_mi=%r, query_date=%r)"
            % (self.name, self.lat, self.lon, self.radius_mi, self.query_date)
        )


# ---------------------------------------------------------------------------
# Module-level constants.

API_TOKEN = "80886b069bdc4dd9b12bbc90ed482d7b"  # Synoptic API token

# Wind fields this project cares about; passed as Synoptic's `vars=` param.
WIND_VARS = "wind_speed,wind_gust,wind_direction"

CACHE_DIR = "./synoptic_cache"
OUTPUT_DIR = "./synoptic_output"
LOG_DIR = "./synoptic_logs"


OXFORD = Location(
    lat=51.792827,
    lon=-1.222481,
    radius_mi=2.0,  # ~3 km, to roughly match the WeatherXM OXFORD instance
    query_date="2026-08-04",
    name="Oxford",
)


def smoke_test(location, api_token):
    """
    Minimal sanity check of the Synoptic pipeline: ONE combined
    radius+timeseries call (Synoptic needs no separate discovery call),
    printing how many stations responded and confirming the wind fields
    are present on the first station's most recent observation.
    """
    import json
    import logging
    import requests

    logger = logging.getLogger(__name__)

    logger.info("=" * 70)
    logger.info("SMOKE TEST for %r", location)
    logger.info("=" * 70)

    url = "https://api.synopticdata.com/v2/stations/timeseries"
    params = {
        "token": api_token,
        "radius": location.to_radius_param(),
        "vars": WIND_VARS,
        "units": "metric",
        "qc": "on",
        **location.to_time_params(),
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("FAILED: timeseries call raised %s", exc)
        return False

    try:
        payload = response.json()
    except ValueError as exc:
        logger.error("FAILED: could not parse response JSON: %s", exc)
        return False

    stations = payload.get("STATION", [])
    logger.info("%d station(s) returned near %s.", len(stations), location.name)

    if not stations:
        logger.error("FAILED: no stations in response. SUMMARY=%r", payload.get("SUMMARY"))
        return False

    first = stations[0]
    obs = first.get("OBSERVATIONS", {})
    logger.info(
        "First station: STID=%s NAME=%r, %d timestamp(s) of data.",
        first.get("STID"), first.get("NAME"), len(obs.get("date_time", [])),
    )

    # Synoptic suffixes each variable with its "set" number, e.g.
    # "wind_speed_set_1" -- we just look for any key that starts with the
    # bare variable name.
    wind_fields = ("wind_speed", "wind_gust", "wind_direction")
    present = {
        field: any(key.startswith(field) for key in obs)
        for field in wind_fields
    }
    logger.info("Wind fields present in response: %r", present)

    logger.info("Sample OBSERVATIONS keys: %s", json.dumps(list(obs.keys())))

    fields_ok = all(present.values())
    if fields_ok:
        logger.info("PASSED: wind fields present.")
    else:
        logger.error("FAILED: one or more wind fields missing.")

    return fields_ok


if __name__ == "__main__":
    from synoptic_logging import setup_logging

    setup_logging(LOG_DIR)
    smoke_test(OXFORD, API_TOKEN)
