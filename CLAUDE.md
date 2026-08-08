# Topographical Modeling CFD

## STANDING RULE: no code without explicit approval

Do NOT use Write or Edit on any code file in this repo until the user has
given explicit, standalone approval for that specific change — the literal
words "ok to code" (or an unambiguous equivalent said unprompted). This
applies even after a plan, design, or scope has been discussed and agreed —
agreeing "yes" to a *plan* is not approval to *write the code*. If there is
any doubt whether approval was given, stop and ask "Ok to code?" as its own
question and wait for a direct answer to it before touching any file.

This does not restrict Read/Grep/Glob (investigation), or editing
non-code project docs like this file when the user directly asks for that
specific doc edit.

Wind-profile modelling for cycling time-trial simulation. The project pulls
wind data (forecast + historical), terrain (STL tiles), and a rider's route
(GPX) together so a course's wind exposure can be analyzed and eventually fed
into a CFD simulation. A Streamlit app ties the pieces together into an
interactive interface.

## Repo layout

```
Data/
  files_gpx/          -- GPX route files (e.g. English_Weather_.gpx)
  stl_data/            -- terrain/building/canopy/route STL tiles ("Oxford Course")
src/
  Data Viewing/         -- GPX parsing, STL terrain viewing/trimming, lat-lon <-> STL local xy projection
  GraphCast Functionality/  -- DeepMind GraphCast wind forecast pipeline (Colab/Linux only)
  HyperLocal Data Synoptic/ -- historical wind pull via Synoptic Weather API
  wind data pulling/
    pull_wind_data.py         -- ERA5-Land single-timestep wind inlet (Copernicus CDS API)
    HyperLocal Data WeatherXM/ -- historical wind pull via WeatherXM Pro API
out/                   -- generated/cached outputs (gpx cache, trimmed STL, HTML viewers)
Streamlit App/          -- the interactive front end (see below)
requirements.txt        -- Windows-side deps (numpy, pandas, xarray, netCDF4, cdsapi, pyvista, plotly, streamlit)
```

Folder names under `src/` contain spaces (`"Data Viewing"`, `"GraphCast
Functionality"`, etc.) — these aren't Python packages, they're plain
directories added to `sys.path` at runtime so their modules can be imported
by bare name (e.g. `import gpx_processing`). See `Streamlit App/build_streamlit.py`
for the pattern.

## Subsystems

**Data Viewing** (`src/Data Viewing/`)
- `gpx_processing.py` -- parses GPX trackpoints (incl. Garmin extension
  channels like `atemp`) into a cached, time-sorted pandas DataFrame.
- `gpx_viewing.py` -- standalone Plotly HTML viewer (track map + elevation
  profile, cursor-linked); also home of `add_distance_column()`
  (haversine-based cumulative distance), reused by the Streamlit app.
- `geo_projection.py` -- empirically-fitted equirectangular projection from
  GPX lat/lon to the Oxford Course STL tiles' local (x, y) meter frame.
  Accuracy limit is ~5.7 m mean residual (+/-10-15 m) — not survey grade.
- `pick_stl_location.py` / `trim_stl_data.py` -- PyVista STL tile viewing and
  circular trimming around a lat/lon center point.
- `view_envionment_data.py` -- (filename typo, kept as-is) STL tile viewer.

**GraphCast Functionality** (`src/GraphCast Functionality/`) — full details
in its own `README_GraphCast.md`.
- Runs Google DeepMind's pretrained `GraphCast_operational` model to extract
  a 10m wind forecast at a point/time, for use as a CFD inlet condition.
- **Linux/Colab only** — JAX has no supported Windows GPU build. Do not try
  to install `requirements-linux-gpu.txt` on Windows.
- `prediciton_build_test.py` (typo intentionally kept, matches an existing
  import) runs against Google's static example batch — proves the pipeline
  works, is **not a live forecast**.
- `prediction_build.py` (live-data path) is **not yet runnable end to end**
  — `build_forcings_template()` deliberately raises `NotImplementedError`.

**Historical wind pulls** — two independent, parallel pipelines pulling
station observations near Oxford, both cache-first:
- `src/wind data pulling/HyperLocal Data WeatherXM/` — WeatherXM Pro API.
  Radius in **metres**; history capped at **7 days** per call; quality
  filter is a single `health.data_quality.score` (0-1). Full details in its
  `READ_ME_WEATHERXM.md`.
- `src/HyperLocal Data Synoptic/` — Synoptic Weather API. Radius in
  **miles**; one call does discovery+pull together (`/stations/timeseries`);
  quality control is flag-based (`qc`, `qc_flags`), not a single score. Full
  details in `READ_ME_SYNOPTIC.md`.
- Both hardcode an `OXFORD` `Location` instance as the current target place.

**ERA5-Land** (`src/wind data pulling/pull_wind_data.py`) — pulls a single
10m u/v wind timestep near a point/time from Copernicus CDS (ERA5-Land,
0.1 deg — finer than the public ARCO-ERA5 Zarr bucket's 0.25 deg base ERA5).
Needs a free CDS account + API key in `~/.cdsapirc`.

**Streamlit App** (`Streamlit App/`) — the interactive front end.
- `build_streamlit.py` — launch entry point (`streamlit run "Streamlit
  App/build_streamlit.py"`); wires up `sys.path` and page config.
- `frontpage_streamlit.py` — page layout (sidebar + main body).
- Each feature is split into a **calculation file** and a matching
  **`*_visualization.py` display file** (established convention — keep
  following it for new features): `route_summary.py` /
  `route_summary_visualization.py`, `route_map.py` /
  `route_map_visualization.py`, `elevation_profile.py` /
  `elevation_profile_visualization.py`.
- Theme forced to a white background via `Streamlit App/.streamlit/config.toml`.
- `route_summary.RouteSummary` stats are currently stubbed to `0.0` pending
  real GPX/wind-derived calculations.

## Conventions / gotchas worth remembering

- Radius units differ per wind API: WeatherXM = metres, Synoptic = miles.
  Always go through the pipeline's `Location` class rather than passing a
  raw number, since it encodes the correct unit per API.
- All the historical-wind and GPX pulls are cache-first — re-running a
  pipeline reuses cached JSON/pickle rather than re-hitting the API/re-parsing.
- Logging in the WeatherXM/Synoptic pipelines is set up once via
  `setup_logging(log_dir)` on the root logger; other modules just call
  `logging.getLogger(__name__)`.
- API tokens/keys (`API_TOKEN`, `API_KEY`) are hardcoded constants in each
  pipeline's `*_input_loc*.py` — fill in before running, don't commit real
  keys.
