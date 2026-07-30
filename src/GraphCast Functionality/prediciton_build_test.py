# Script for running a smoke-test GraphCast_operational rollout against Google's static
# example batch, then extracting a hardcoded test point from the result to prove the full
# pipeline works end to end. This does NOT produce a real current-conditions forecast -- the
# example batch is a frozen historical snapshot, not live data. See prediction_build.py for
# the (not yet implemented) live-data version.
# 1. Load the pretrained model via build_GraphCast.load_model()
# 2. Load an example batch from GCS that's compatible with the operational model (HRES
#    source, matching resolution/pressure levels)
# 3. Build eval inputs/targets/forcings and run the autoregressive rollout
# 4. Extract a hardcoded test lat/lon/time from the rollout via data_extractor and print it

# Key library imports
import dataclasses  # for unpacking task_config into extract_inputs_targets_forcings
import json  # for printing the wind_summary readably
import numpy as np  # for the NaN-filled targets template
import xarray  # for loading the example batch file
from google.cloud import storage  # for locating a compatible example batch on the public bucket
from graphcast import data_utils  # for splitting the batch into inputs/targets/forcings
from graphcast import rollout  # for the chunked autoregressive prediction loop
import jax  # for the PRNG key the rollout call expects

import build_GraphCast
import data_extractor

# Hardcoded test point -- only this constant needs to change to test elsewhere, the
# extraction logic itself doesn't assume this specific value
QUERY_LAT = 34.05
QUERY_LON = -118.25
QUERY_TIME = "2019-03-29T18:00"  # only meaningful relative to whichever example batch date gets picked below

# Key GCS paths (same bucket/prefix as build_GraphCast.py, but the dataset/ subfolder instead of params/)
GCS_BUCKET_NAME = "dm_graphcast"
DIR_PREFIX = "graphcast/"
EVAL_STEPS = 4  # number of 6-hour rollout steps to run (24h) -- enough to exercise the pipeline


def parse_file_parts(file_name):
    # Dataset filenames encode metadata like "source-hres_res-0.25_levels-13_steps-04",
    # parsed here into a dict of {"source": "hres", "res": "0.25", ...}
    return dict(part.split("-", 1) for part in file_name.split("_"))


def dataset_valid_for_model(file_name, model_config, task_config):
    file_parts = parse_file_parts(file_name.removesuffix(".nc"))

    resolution_matches = model_config.resolution in (0, float(file_parts["res"]))
    levels_match = len(task_config.pressure_levels) == int(file_parts["levels"])

    # GraphCast_operational is fine-tuned on HRES and doesn't take precipitation input,
    # so it needs an "hres" (or "fake") source example batch rather than an "era5" one
    source_matches = "total_precipitation_6hr" not in task_config.input_variables and file_parts["source"] in ("hres", "fake")

    return resolution_matches and levels_match and source_matches


def find_compatible_dataset_blob(bucket, model_config, task_config):
    blobs = bucket.list_blobs(prefix=DIR_PREFIX + "dataset/")
    matches = [
        blob.name for blob in blobs
        if dataset_valid_for_model(blob.name.removeprefix(DIR_PREFIX + "dataset/"), model_config, task_config)
    ]

    if not matches:
        raise RuntimeError("No example dataset file compatible with the operational model was found")

    return matches[0]


def load_example_batch(model_config, task_config):
    client = storage.Client.create_anonymous_client()
    bucket = client.get_bucket(GCS_BUCKET_NAME)

    blob_name = find_compatible_dataset_blob(bucket, model_config, task_config)
    with bucket.blob(blob_name).open("rb") as f:
        return xarray.load_dataset(f).compute()


def run_rollout(run_forward_jitted, model_config, task_config):
    example_batch = load_example_batch(model_config, task_config)

    eval_inputs, eval_targets, eval_forcings = data_utils.extract_inputs_targets_forcings(
        example_batch,
        target_lead_times=slice("6h", f"{EVAL_STEPS * 6}h"),
        **dataclasses.asdict(task_config),
    )

    predictions = rollout.chunked_prediction(
        run_forward_jitted,
        rng=jax.random.PRNGKey(0),
        inputs=eval_inputs,
        targets_template=eval_targets * np.nan,
        forcings=eval_forcings,
    )

    return predictions


def main():
    run_forward_jitted, model_config, task_config = build_GraphCast.load_model()

    predictions = run_rollout(run_forward_jitted, model_config, task_config)

    wind_summary = data_extractor.extract_point(predictions, QUERY_LAT, QUERY_LON, QUERY_TIME)

    print("Pipeline smoke test complete -- wind_summary:")
    print(json.dumps(wind_summary, indent=2))

    return wind_summary


if __name__ == "__main__":
    main()
