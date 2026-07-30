# GraphCast Functionality

Extracts a near-surface wind forecast at a point and time from a GraphCast rollout, for use
as a CFD inlet boundary condition.

## Objective

Given a query latitude/longitude/time, run Google DeepMind's pretrained `GraphCast_operational`
model and return the nearest grid cell's 10m wind speed and direction, plus enough metadata
(actual selected cell/time) to see how far the query snapped from what was asked for.

Model: GraphCast_operational (0.25 deg / ~28km global grid, 13 pressure levels, 6h timestep).
Pretrained on ERA5 (1979-2017), fine-tuned on HRES (2016-2021), initialized from HRES
near-real-time analysis (no precipitation input required).
Source: [google-deepmind/weathernext](https://github.com/google-deepmind/weathernext).
Weights: `dm_graphcast` public GCS bucket. License: code Apache-2.0, weights
CC-BY-NC-SA-4.0 (non-commercial).

## Pipeline

```
build_GraphCast.py          -- loads the pretrained architecture + weights
        |
        v
prediciton_build_test.py    -- runs the rollout against a static example batch (or
prediction_build.py            eventually live data), returns the global forecast Dataset
        |
        v
data_extractor.py           -- pulls the nearest point/time out of that Dataset,
                                derives wind speed + direction
        |
        v
query_builder.py             -- orchestrates the above, prints + saves wind_summary.json
```

| File | Role |
|---|---|
| `build_GraphCast.py` | `load_model()` -- pulls the operational checkpoint and normalization stats from the `dm_graphcast` GCS bucket, returns a jitted forward function plus `model_config`/`task_config`. |
| `data_extractor.py` | `extract_point(ds, lat, lon, query_time)` -- nearest-cell/nearest-time selection, returns the `wind_summary` dict. Post-processing only; doesn't care where the rollout's input data came from. |
| `prediciton_build_test.py` | Runs the rollout against Google's static example batch. Validates the pipeline end to end but is **not a live forecast** -- see Known limitations below. Filename has a typo (missing the 'd' in "prediction") that's been kept to avoid a mismatched import; rename with care if you fix it. |
| `prediction_build.py` | Live-data version. Fetches two 6h-apart HRES cycles from ECMWF's free Open Data feed and assembles them into GraphCast's input structure -- **not yet runnable end to end**: `build_forcings_template()` deliberately raises `NotImplementedError`, since synthesizing a targets/forcings template for genuinely future (not-yet-observed) lead times needs `graphcast.data_utils`' analytic solar-forcing helper, whose exact signature can't be confirmed without the package installed. The GRIB-to-Dataset conversion is also unverified until run against real data -- see inline comments. |
| `query_builder.py` | `run_query(lat, lon, time_str)` -- thin orchestrator. In Colab, the lat/lon/time values come from `#@param` form fields in the notebook cell that calls this, since Colab's form-field rendering only works on code living directly in a notebook cell, not inside an imported module. |
| `requirements-linux-gpu.txt` | Dependency manifest for the Linux/Colab execution side. **Do not install on Windows** -- JAX's CUDA pip wheels are Linux-only and fail silently on Windows. |

## wind_summary contract

```python
{
    "u10": ...,             # m/s, eastward component
    "v10": ...,             # m/s, northward component
    "speed_ms": ...,        # sqrt(u10**2 + v10**2)
    "dir_from_deg": ...,    # meteorological "from" direction: (270 - atan2(v,u)*180/pi) % 360
    "valid_time": ...,      # actual forecast valid-time selected (absolute)
    "cell_lat": ...,        # actual grid cell latitude selected
    "cell_lon": ...,        # actual grid cell longitude selected (0-360 convention)
    "requested_lat": ...,
    "requested_lon": ...,
    "requested_time": ...,
}
```

## Why local Windows execution doesn't work

JAX has no officially supported native-Windows GPU build -- CUDA pip wheels are Linux
x86_64/aarch64 only. The community-maintained Windows CUDA wheel project
(`jax-windows-builder`) is archived and capped at JAX ~0.3.14/CUDA 11.1, while `graphcast`'s
own `setup.py` pins no jax version and just pulls the current release -- there's no
overlapping compatible version. Running via **Google Colab** sidesteps this entirely, since
Colab's runtime is a hosted Linux VM.

## Known limitations

- **Static example batch is not a live forecast.** `prediciton_build_test.py` rolls forward
  from whichever historical date Google's example batch happens to represent, not from
  "now." It proves the pipeline is wired correctly; it does not answer "what's the wind
  right now at these coordinates."
- **Resolution floor.** 0.25 deg is ~28km per cell -- a domain smaller than one cell
  resolves to a single value. GraphCast gives forecast lead time, not sub-cell spatial
  detail; sub-cell inlet variation needs separate downscaling.
- **10m wind only.** A full vertical inlet profile would need U/V across the 13 pressure
  levels plus pressure-to-height conversion via geopotential (Z) -- not implemented here.
- **GPU memory on Colab free tier is unconfirmed** for the full operational model (DeepMind
  only explicitly documents the smaller GenCast Mini as free-tier-Colab-runnable). May need
  Colab Pro (A100) if the free T4 runs out of memory during the rollout.
- **`prediction_build.py`'s live path is unfinished by design.** ECMWF Open Data fetching and
  GRIB-to-Dataset assembly are written, but blind forecasting (no ground-truth future to slice
  a targets/forcings template from, unlike the test version) needs an analytic solar-forcing
  helper from `graphcast.data_utils` that hasn't been confirmed against the real package yet.

## Setup (Colab)

1. `!git clone` this repo, `%cd` into `src/GraphCast Functionality`.
2. `!pip install -r requirements-linux-gpu.txt`.
3. Run a notebook cell with `#@param` fields for lat/lon/time, then call
   `query_builder.run_query(QUERY_LAT, QUERY_LON, QUERY_TIME)`.

(Notebook itself not yet created -- next step in this pipeline's build-out.)
