# Live-data version of prediciton_build_test.py -- builds the two initial condition frames
# GraphCast_operational needs from ECMWF's free real-time Open Data feed (HRES, "oper" stream)
# instead of Google's static example batch, then runs the same autoregressive rollout.
#
# NOT YET VALIDATED end to end -- this can't be run/tested on this machine (no local JAX/Linux
# GPU environment, see README_GraphCast.md). Two pieces in particular need checking once this
# actually runs against real GRIB data in Colab:
#   1. grib_to_graphcast_dataset() -- cfgrib's default dim/coord/variable names and GraphCast's
#      expected names may not line up one for one the way SURFACE_PARAM_MAP/LEVEL_PARAM_MAP assume
#   2. build_forcings_template() -- deliberately left raising NotImplementedError, see its
#      docstring comment for why this one specifically couldn't be guessed at safely
#
# 1. Work out the two most recent 6h-apart HRES cycles (t-6h, t0)
# 2. Fetch surface + pressure-level fields for both cycles via ecmwf.opendata.Client
# 3. Fetch static fields (land-sea mask, surface geopotential) once
# 4. Assemble all of it into the batch/time/lat/lon/level structure GraphCast expects
# 5. Run the same rollout.chunked_prediction call prediciton_build_test.py uses

# Key library imports
import datetime  # for working out the latest HRES synoptic cycle times
import tempfile  # for scratch GRIB2 download paths
import numpy as np  # for building the relative time / absolute datetime coordinates
import xarray  # for combining the downloaded fields into the model's input structure
from ecmwf.opendata import Client  # free, no-license real-time ECMWF HRES data feed
from graphcast import rollout  # for the chunked autoregressive prediction loop
import jax  # for the PRNG key the rollout call expects

import build_GraphCast

FORECAST_HOURS = 24  # how far ahead to roll the live forecast out -- swappable constant, same pattern as QUERY_TIME elsewhere
SYNOPTIC_CYCLE_HOURS = 6  # HRES open data cycles run every 6h (00/06/12/18 UTC)

# GraphCast variable name -> ECMWF Open Data short param code
SURFACE_PARAM_MAP = {
    "10m_u_component_of_wind": "10u",
    "10m_v_component_of_wind": "10v",
    "2m_temperature": "2t",
    "mean_sea_level_pressure": "msl",
}
LEVEL_PARAM_MAP = {
    "temperature": "t",
    "u_component_of_wind": "u",
    "v_component_of_wind": "v",
    "geopotential": "z",
    "specific_humidity": "q",
    "vertical_velocity": "w",
}


def latest_synoptic_cycle():
    # Rounds down to the most recent 00/06/12/18 UTC cycle time
    now = datetime.datetime.now(datetime.timezone.utc)
    cycle_hour = (now.hour // SYNOPTIC_CYCLE_HOURS) * SYNOPTIC_CYCLE_HOURS

    return now.replace(hour=cycle_hour, minute=0, second=0, microsecond=0)


def get_two_init_cycles():
    # GraphCast needs two 6h-apart snapshots. ECMWF's free Open Data feed doesn't offer a
    # true "an" analysis type, but step=0 of a "fc" request IS the analysis-initialized field
    # for that cycle -- so two consecutive cycles' step=0 gives exactly the pair needed. This
    # two-cycle approach matches what ECMWF's own "run AI models from open data" guidance uses.
    t0_cycle = latest_synoptic_cycle()
    t_minus_6h_cycle = t0_cycle - datetime.timedelta(hours=SYNOPTIC_CYCLE_HOURS)

    return [t_minus_6h_cycle, t0_cycle]


def fetch_cycle_fields(client, cycle_time, param_map, levelist=None):
    target = tempfile.NamedTemporaryFile(suffix=".grib2", delete=False).name

    client.retrieve(
        date=cycle_time.date(),
        time=cycle_time.hour,
        stream="oper",
        type="fc",
        step=0,
        param=list(param_map.values()),
        levelist=levelist,
        target=target,
    )

    return target


def fetch_static_fields(client):
    # Surface geopotential + land-sea mask don't change over time, so these only get fetched once
    target = tempfile.NamedTemporaryFile(suffix=".grib2", delete=False).name

    client.retrieve(
        stream="oper",
        type="fc",
        step=0,
        param=["z", "lsm"],
        target=target,
    )

    return target


def grib_to_graphcast_dataset(surface_paths, level_paths, static_path, cycle_times):
    reverse_surface_map = {v: k for k, v in SURFACE_PARAM_MAP.items()}
    reverse_level_map = {v: k for k, v in LEVEL_PARAM_MAP.items()}

    reference_time = np.datetime64(cycle_times[-1])  # the later of the two init cycles is "t=0"
    time_deltas = [np.datetime64(t) - reference_time for t in cycle_times]

    per_cycle_datasets = []
    for surface_path, level_path, time_delta in zip(surface_paths, level_paths, time_deltas):
        surface_ds = xarray.open_dataset(surface_path, engine="cfgrib").rename(reverse_surface_map)
        level_ds = xarray.open_dataset(level_path, engine="cfgrib").rename(reverse_level_map)

        cycle_ds = xarray.merge([surface_ds, level_ds])
        cycle_ds = cycle_ds.expand_dims(time=[time_delta])
        per_cycle_datasets.append(cycle_ds)

    combined = xarray.concat(per_cycle_datasets, dim="time")
    combined = combined.assign_coords(datetime=("time", [np.datetime64(t) for t in cycle_times]))

    static_ds = xarray.open_dataset(static_path, engine="cfgrib").rename({"z": "geopotential_at_surface", "lsm": "land_sea_mask"})
    combined = xarray.merge([combined, static_ds])

    combined = combined.expand_dims(batch=[0])  # this pipeline only ever runs a single, non-batched query

    return combined


def load_live_inputs(task_config):
    client = Client(source="ecmwf", model="ifs", resol="0p25")

    cycle_times = get_two_init_cycles()

    surface_params = {k: v for k, v in SURFACE_PARAM_MAP.items() if k in task_config.input_variables}
    level_params = {k: v for k, v in LEVEL_PARAM_MAP.items() if k in task_config.input_variables}

    surface_paths = [fetch_cycle_fields(client, t, surface_params) for t in cycle_times]
    level_paths = [fetch_cycle_fields(client, t, level_params, levelist=list(task_config.pressure_levels)) for t in cycle_times]
    static_path = fetch_static_fields(client)

    return grib_to_graphcast_dataset(surface_paths, level_paths, static_path, cycle_times)


def build_forcings_template(task_config):
    # prediciton_build_test.py only gets away with slicing a targets_template/forcings pair out
    # of the static example batch because its "future" is already-recorded history. A genuine
    # live forecast has no real future data to draw that shape from -- it has to be synthesized.
    # The only forcing GraphCast_operational needs beyond the two input frames is incident solar
    # radiation, which is analytically computable from lat/lon/time rather than observed, and
    # graphcast.data_utils is expected to expose a helper for this -- but the exact function name
    # and signature needs to be confirmed by reading the installed package once this actually
    # runs somewhere with graphcast available, rather than guessed at here.
    raise NotImplementedError(
        "Live forcings/targets_template synthesis not implemented -- needs graphcast.data_utils' "
        "analytic solar-forcing helper, to be confirmed against the real installed package."
    )


def run_rollout(run_forward_jitted, model_config, task_config):
    inputs = load_live_inputs(task_config)
    targets_template, forcings = build_forcings_template(task_config)

    predictions = rollout.chunked_prediction(
        run_forward_jitted,
        rng=jax.random.PRNGKey(0),
        inputs=inputs,
        targets_template=targets_template,
        forcings=forcings,
    )

    return predictions


def main():
    run_forward_jitted, model_config, task_config = build_GraphCast.load_model()
    return run_rollout(run_forward_jitted, model_config, task_config)


if __name__ == "__main__":
    main()
