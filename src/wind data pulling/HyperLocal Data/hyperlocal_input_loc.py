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
"""

# Standard-library imports only, per project requirements.
# `datetime` and `timedelta` are used for parsing "YYYY-MM-DD" strings into
# real calendar dates and for stepping forward day-by-day when chunking a
# date range.
from datetime import datetime, timedelta


class Location(object):
    """
    Encapsulates a single point of interest for the wind-data pull: its
    geographic position, the radius of stations to consider around it, and
    the date range of history to fetch for those stations.

    Using a class (rather than a handful of loose variables) means every
    consumer of a Location gets the SAME validation and the SAME gotcha
    handling (metres-not-km, 7-day chunking) for free, instead of each file
    re-deriving it and risking inconsistency.
    """

    def __init__(self, lat, lon, radius_km, start_date, end_date, name):
        # `self` is the instance being constructed; assigning to `self.xxx`
        # creates/sets an attribute that lives on this specific object (as
        # opposed to a local variable, which would vanish when __init__ returns).
        #
        # We validate BEFORE assigning anything, so a Location object can
        # never exist in a half-valid state -- if validation fails we raise
        # immediately and no attributes are set at all (the raise below exits
        # __init__ before assignment happens, and the caller's `Location(...)`
        # expression never completes, so no object escapes into the program).

        # --- Latitude / longitude range checks ---
        # `<=` chained like `-85 <= lat <= 85` is Python's chained-comparison
        # syntax: it evaluates to True only if BOTH comparisons hold, and is
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

        # --- Date ordering check ---
        # start_date/end_date arrive as "YYYY-MM-DD" strings (per the spec),
        # so we parse them to real `date` objects with
        # `datetime.strptime(text, format).date()` before comparing. Comparing
        # the raw strings would happen to work for zero-padded ISO dates, but
        # parsing is explicit and also validates the strings are well-formed
        # dates (strptime raises ValueError itself on a malformed string,
        # which is exactly the exception type we want to surface anyway).
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError as exc:
            # `raise ... from exc` chains the new exception onto the original
            # one, so the traceback shows both the parse failure and the
            # context in which we caught it, instead of hiding the cause.
            raise ValueError(
                "Invalid start_date/end_date for Location %r: %s. "
                "Dates must be 'YYYY-MM-DD' strings." % (name, exc)
            ) from exc

        if start_dt > end_dt:
            raise ValueError(
                "Invalid date range for Location %r: start_date %r is after end_date %r."
                % (name, start_date, end_date)
            )

        # All checks passed -- now (and only now) do we populate the instance.
        self.lat = lat
        self.lon = lon
        self.radius_km = radius_km
        # We keep the original strings as the attributes (the spec asks for
        # "YYYY-MM-DD" strings), but we also stash the parsed `date` objects
        # under private-by-convention names (leading underscore) so methods
        # like `date_chunks` don't have to re-parse the strings every call.
        self.start_date = start_date
        self.end_date = end_date
        self._start_dt = start_dt
        self._end_dt = end_dt
        self.name = name

    @property
    def radius_m(self):
        """
        Read-only derived attribute: radius in METRES.

        The `@property` decorator turns this method into something callers
        access WITHOUT parentheses, e.g. `location.radius_m`, as if it were a
        plain attribute -- but it's actually computed fresh from
        `self.radius_km` on every access, so it can never drift out of sync.

        This exists specifically to encapsulate a WeatherXM API gotcha: the
        `/stations/near` endpoint's `radius` query parameter is in METRES,
        not kilometres. By funnelling every caller through this property,
        nobody has to remember to multiply by 1000 themselves.
        """
        return self.radius_km * 1000

    def date_chunks(self):
        """
        Split self.start_date..self.end_date (inclusive) into consecutive
        chunks of AT MOST 7 DAYS each, returned as a list of
        (start_str, end_str) tuples where each string is "YYYY-MM-DD".

        This encapsulates a second WeatherXM API gotcha: the
        `/stations/{id}/history` endpoint REJECTS date ranges longer than 7
        days, so any caller pulling history must iterate chunk-by-chunk
        rather than requesting the whole range in one call.

        Returns
        -------
        list of tuple(str, str)
            e.g. [("2024-01-01", "2024-01-07"), ("2024-01-08", "2024-01-14"), ...]
        """
        # `chunks` is a plain list we build up with `.append(...)`; using a
        # list (rather than e.g. a generator) makes it easy for callers to
        # iterate multiple times or check `len(...)` without re-computing.
        chunks = []

        # `MAX_CHUNK_DAYS = 7` matches the API's hard limit; because ranges
        # are INCLUSIVE of both endpoints, a chunk that starts on day 0 and
        # spans 7 days ends on day 0 + 6 (7 calendar days total: 0..6
        # inclusive), hence `timedelta(days=MAX_CHUNK_DAYS - 1)` below.
        MAX_CHUNK_DAYS = 7

        # `cursor` tracks the start of the NEXT chunk we haven't emitted yet;
        # it walks forward from self._start_dt to self._end_dt.
        cursor = self._start_dt
        while cursor <= self._end_dt:
            # The tentative chunk end is `cursor + 6 days` (7 days inclusive),
            # but it must never run past the overall end date -- `min(...)`
            # clamps it back if the final chunk would otherwise overshoot.
            chunk_end = min(cursor + timedelta(days=MAX_CHUNK_DAYS - 1), self._end_dt)

            # `date.strftime("%Y-%m-%d")` formats a `date` object back into
            # the "YYYY-MM-DD" string shape the WeatherXM API expects.
            chunks.append((cursor.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")))

            # Advance the cursor to the day immediately after this chunk's
            # end, so the next iteration starts a fresh, non-overlapping chunk.
            cursor = chunk_end + timedelta(days=1)

        return chunks

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
            # `self.radius_m` invokes the @property above, converting
            # kilometres to metres at the point of use.
            "radius": self.radius_m,
        }

    def __repr__(self):
        # `__repr__` controls how this object prints/represents itself (e.g.
        # in a REPL, in log messages, or when it appears inside another
        # object like a list). Defining it makes debugging output readable
        # instead of the default `<Location object at 0x...>`.
        return (
            "Location(name=%r, lat=%r, lon=%r, radius_km=%r, start_date=%r, end_date=%r)"
            % (self.name, self.lat, self.lon, self.radius_km, self.start_date, self.end_date)
        )


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
    radius_km=5.0,
    start_date="2024-01-01",
    end_date="2024-01-31",
    name="Oxford",
)


# ---------------------------------------------------------------------------
# Module-level constants.
#
# These are ACCOUNT/RUN settings, not per-location geography, so they live at
# module scope rather than on the Location class -- every Location shares the
# same API key, quality threshold, and cache/output directories.
# ---------------------------------------------------------------------------

# WeatherXM Pro API key, sent as the `X-API-KEY` HTTP header on every request.
# This is a placeholder string; it will be filled in with a real key later.
API_KEY = "<PLACEHOLDER>"

# Minimum acceptable data-quality score (health.data_quality.score), 0-1.
# Observations from a station-day scoring below this are dropped in File 3.
MIN_QOD = 0.8

# Directory where raw per-(station, date-range) JSON API responses are cached.
# A relative path (interpreted relative to the current working directory the
# scripts are run from) matching the other files' string-constant style.
CACHE_DIR = "./wxm_cache"

# Directory where the final assembled dataset JSON file is written.
OUTPUT_DIR = "./wxm_output"
