# HyperLocal Synoptic Wind-Data Pull

Pulls historical wind data (speed, gust, direction) from the Synoptic
Weather API for stations near a location, using a cache-first fetch
strategy.

## Run order

1. **synoptic_input_location.py** -- `Location` class (lat/lon/radius_mi/
   query_date), the hardcoded `OXFORD` instance, and account-level constants
   (`API_TOKEN`, `WIND_VARS`, `CACHE_DIR`, `OUTPUT_DIR`, `LOG_DIR`). Fill in
   `API_TOKEN` before running anything. `python synoptic_input_location.py`
   runs a 1-call smoke test.
2. **synoptic_build_dataset.py** -- `build_dataset_for_location(...)` does
   discovery and pull TOGETHER in one API call and writes the flat dataset.
   Run this file directly to execute the pipeline for `OXFORD`.
3. **synoptic_logging.py** -- `setup_logging(log_dir)`, same pattern as the
   WeatherXM pipeline.

## How this differs from the WeatherXM pipeline

See `../wind data pulling/HyperLocal Data WeatherXM/READ_ME_WEATHERXM.md`
for the WeatherXM side of this comparison.

- **One call instead of two.** WeatherXM requires `/stations/near` (find
  stations) then `/stations/{id}/history` per station. Synoptic's
  `/stations/timeseries` accepts a `radius` selector directly, so one call
  returns every nearby station's observations -- there's no separate
  `find_stations` module here.
- **Radius unit gotcha is reversed.** WeatherXM wants radius in METRES;
  Synoptic wants `radius=lat,lon,MILES`. `Location.to_radius_param()` builds
  this string so no call site converts by hand.
- **No documented 7-day cap.** WeatherXM hard-rejects date ranges over 7
  days. Synoptic's docs don't state a range limit, so `Location` still
  defaults to a 7-day window (`days_back=6`) for parity with the WeatherXM
  datasets, but it's a plain constructor argument, not an API-enforced cap.
- **Auth is a query param, not a header.** `token=...` on every request,
  vs. WeatherXM's `X-API-KEY` header.
- **Quality control is flag-based, not a single score.** Synoptic exposes
  `qc`, `qc_flags`, `qc_checks` params and per-flag results, rather than
  WeatherXM's single `health.data_quality.score` (0-1). This pipeline
  currently just requests `qc=on&qc_flags=on` and passes flagged data
  through unfiltered -- add a filter in `build_dataset_for_location` if you
  want failed-QC observations dropped.
- **Response shape.** Synoptic returns parallel arrays per station
  (`OBSERVATIONS.date_time`, `OBSERVATIONS.wind_speed_set_1`, ...) rather
  than WeatherXM's one-dict-per-observation list; `_series_for()` in
  `synoptic_build_dataset.py` unpacks these by index.

## Output

`OUTPUT_DIR/{location_name}_wind_dataset.json`: a flat list of records with
`station_id`, `station_name`, `timestamp`, `wind_speed`, `wind_gust`,
`wind_direction`, sorted by `station_id` then `timestamp`.
