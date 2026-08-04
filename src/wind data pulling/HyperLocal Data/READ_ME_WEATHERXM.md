# HyperLocal WeatherXM Pro Wind-Data Pull

Pulls historical wind data (speed, gust, direction) from the WeatherXM Pro
API for weather stations near a location, using a cache-first fetch strategy
and per-observation data-quality filtering.

## Run order

1. **hyperlocal_input_loc.py** -- defines the `Location` class and the
   hardcoded `OXFORD` instance, plus account-level constants (`API_KEY`,
   `MIN_QOD`, `CACHE_DIR`, `OUTPUT_DIR`). Edit this file to change the
   target place/date-range, or to add another `Location` for a different
   place.
2. **hyperlocal_find_stations.py** -- `discover_stations(location, api_key,
   min_qod)` finds nearby WeatherXM Pro stations and filters out ones with
   no coverage for the requested window.
3. **hyperlocal_build_dataset.py** -- pulls per-station history for every
   station `discover_stations` returns, assembles it into one flat JSON
   dataset. Run this file directly (`python hyperlocal_build_dataset.py`)
   to execute the full pipeline for `OXFORD`.

## Gotchas handled by the `Location` class

### Gotcha #1 -- radius is in METRES, not km

The WeatherXM `/stations/near` endpoint's `radius` query parameter is in
METRES. This project stores radius as `radius_km` for human readability, but
every call site uses `Location.radius_m` (a property) or
`Location.to_near_params()` (which uses that property internally), so the
conversion happens in exactly one place and callers never do it by hand.

### Gotcha #2 -- history ranges are capped at 7 days

The WeatherXM `/stations/{id}/history` endpoint REJECTS date ranges longer
than 7 days. This project never asks for the whole `START_DATE..END_DATE`
range in one call; instead `Location.date_chunks()` splits it into
consecutive <=7-day `(start, end)` string pairs, and `hyperlocal_build_dataset.py`
makes one API call per station PER CHUNK.

## Rate limits / costs

WeatherXM Pro's call allowance and any billing depend on your specific plan.
The build script does not assume a fixed daily quota (unlike a fixed-rate
API); instead it is CACHE-FIRST (a cached station+range JSON file is never
re-fetched) and treats HTTP 429 ("Too Many Requests") as a per-call failure
that is logged and skipped rather than crashing the run -- re-running the
script later will pick up any stations/chunks that failed, since
already-successful ones are served from cache.

## Code structure

### `hyperlocal_input_loc.py` (config, object-oriented)

- `Location` -- encapsulates geography, timeframe, and both API gotchas:
  - `__init__(lat, lon, radius_km, start_date, end_date, name)` -- validates
    lat/lon ranges, `radius_km > 0`, and `start_date <= end_date`; raises
    `ValueError` on any violation.
  - `radius_m` (property) -- `radius_km * 1000`.
  - `date_chunks()` -- splits the date range into <=7-day `(start, end)`
    string-pair chunks.
  - `to_near_params()` -- builds the `/stations/near` query-param dict
    (`lat`, `lon`, `radius` in metres).
- `OXFORD` -- the single hardcoded `Location` instance for this project.
  Add more `Location(...)` instances here to generalise to other places;
  Files 2 and 3 require no changes.
- Module-level constants (account/run settings, not per-location): `API_KEY`,
  `MIN_QOD`, `CACHE_DIR`, `OUTPUT_DIR`.

### `hyperlocal_find_stations.py` (discovery)

- `discover_stations(location, api_key, min_qod)` -- calls `/stations/near`
  with `location.to_near_params()`, handles both possible response shapes
  (bare list or `{"stations": [...]}`), hard-gates out stations whose
  `createdAt` is after `location.start_date`, optionally applies a
  per-station quality filter if the field is present, and returns
  `[{"id", "name", "lat", "lon", "createdAt"}, ...]`.

### `hyperlocal_build_dataset.py` (pull + assemble)

- `build_dataset_for_location(location, api_key, min_qod, cache_dir,
  output_dir)` -- the pipeline entry point: calls `discover_stations`, gets
  `location.date_chunks()`, fetches history per station per chunk
  (cache-first via `_fetch_history`), filters observations on
  `health.data_quality.score < min_qod`, assembles a flat sorted record
  list, writes it to `output_dir`, and prints a run summary.
- `_fetch_history(station_id, start, end, api_key, cache_dir, stats)` --
  cache-first single history call; reads/writes
  `CACHE_DIR/{station_id}_{start}_{end}.json`.
- `if __name__ == "__main__":` block -- runs `build_dataset_for_location`
  for `OXFORD` when the script is executed directly.

## Output

A single JSON file at `OUTPUT_DIR/{location_name}_wind_dataset.json`: a flat
list of records, each with `station_id`, `timestamp`, `wind_speed`,
`wind_gust`, `wind_direction`, `data_quality_score`, `location_quality_score`,
sorted by `station_id` then `timestamp`.
