# Script for loading the pretrained GraphCast_operational model from Google DeepMind's
# public GCS bucket (weights are CC-BY-NC-SA-4.0, non-commercial use only)
# 1. Locate and load the operational checkpoint (params, model config, task config)
# 2. Load the normalization stats needed to build the wrapped predictor
# 3. Assemble the jitted forward function ready for prediction_build_test.py to call

# Key library imports
import functools  # for binding the loaded params/configs into the forward function
import haiku as hk  # for the transform_with_state wrapper around the model
import jax  # for jitting the forward function
import xarray  # for loading the normalization stats files
from google.cloud import storage  # for pulling weights/stats from the public GCS bucket
from graphcast import autoregressive  # wraps the one-step model into an autoregressive rollout predictor
from graphcast import casting  # bfloat16 casting used internally by the pretrained model
from graphcast import checkpoint  # for reading the packaged params/model_config/task_config
from graphcast import graphcast  # core one-step GraphCast architecture
from graphcast import normalization  # residual normalization wrapper using the stats files

# Key GCS paths
GCS_BUCKET_NAME = "dm_graphcast"  # Google's public bucket hosting GraphCast weights/data
DIR_PREFIX = "graphcast/"  # all relevant files live under this subdirectory
OPERATIONAL_KEY = "operational"  # substring used to pick GraphCast_operational out of the params/ listing


def get_bucket():
    # Anonymous client since dm_graphcast is a public, read-only bucket
    client = storage.Client.create_anonymous_client()
    return client.get_bucket(GCS_BUCKET_NAME)


def find_operational_params_blob(bucket):
    # Params filenames aren't documented/stable, so pick the one that identifies itself as the
    # operational variant rather than hardcoding an exact filename that could drift over time
    blobs = bucket.list_blobs(prefix=DIR_PREFIX + "params/")
    matches = [blob.name for blob in blobs if OPERATIONAL_KEY in blob.name.lower()]

    if not matches:
        raise RuntimeError(f"No params file containing '{OPERATIONAL_KEY}' found under gs://{GCS_BUCKET_NAME}/{DIR_PREFIX}params/")

    return matches[0]


def load_checkpoint(bucket):
    # Returns params, model_config and task_config packaged together in the checkpoint file
    blob_name = find_operational_params_blob(bucket)
    with bucket.blob(blob_name).open("rb") as f:
        return checkpoint.load(f, graphcast.CheckPoint)


def load_stats(bucket):
    # Normalization stats used by normalization.InputsAndResiduals when building the predictor
    def load_stat_file(name):
        with bucket.blob(DIR_PREFIX + "stats/" + name).open("rb") as f:
            return xarray.load_dataset(f).compute()

    diffs_stddev_by_level = load_stat_file("diffs_stddev_by_level.nc")
    mean_by_level = load_stat_file("mean_by_level.nc")
    stddev_by_level = load_stat_file("stddev_by_level.nc")

    return diffs_stddev_by_level, mean_by_level, stddev_by_level


def construct_wrapped_graphcast(model_config, task_config, diffs_stddev_by_level, mean_by_level, stddev_by_level):
    # Assembles the full predictor: base architecture -> bfloat16 casting -> normalization -> autoregressive rollout
    predictor = graphcast.GraphCast(model_config, task_config)
    predictor = casting.Bfloat16Cast(predictor)
    predictor = normalization.InputsAndResiduals(
        predictor,
        diffs_stddev_by_level=diffs_stddev_by_level,
        mean_by_level=mean_by_level,
        stddev_by_level=stddev_by_level,
    )
    predictor = autoregressive.Predictor(predictor, gradient_checkpointing=True)

    return predictor


def load_model():
    # Loads pretrained GraphCast_operational weights and returns a ready-to-call jitted forward
    # function plus the model/task configs prediction_build_test.py needs to build eval data
    bucket = get_bucket()

    ckpt = load_checkpoint(bucket)
    params = ckpt.params
    state = {}  # no recurrent state beyond params -- this is inference only, not training
    model_config = ckpt.model_config
    task_config = ckpt.task_config

    diffs_stddev_by_level, mean_by_level, stddev_by_level = load_stats(bucket)

    @hk.transform_with_state
    def run_forward(model_config, task_config, inputs, targets_template, forcings):
        predictor = construct_wrapped_graphcast(model_config, task_config, diffs_stddev_by_level, mean_by_level, stddev_by_level)
        return predictor(inputs, targets_template=targets_template, forcings=forcings)

    # Binds the loaded params/configs into the function so callers only ever pass inputs/targets/forcings
    def with_configs(fn):
        return functools.partial(fn, model_config=model_config, task_config=task_config)

    def with_params(fn):
        return functools.partial(fn, params=params, state=state)

    def drop_state(fn):
        return lambda **kwargs: fn(**kwargs)[0]  # inference only needs the prediction, not the trailing state

    run_forward_jitted = drop_state(with_params(jax.jit(with_configs(run_forward.apply))))

    return run_forward_jitted, model_config, task_config
