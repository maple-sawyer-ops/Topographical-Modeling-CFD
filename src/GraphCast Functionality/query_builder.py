# Thin orchestrator for the GraphCast wind-extraction pipeline.
# Colab's #@param form fields (lat/lon/time) will live in the notebook itself, not here --
# this module just takes those values as plain arguments so it works the same whether it's
# called from a notebook cell or run directly as a script.
# 1. Run the model via prediciton_build_test (static data) to get the rollout Dataset
# 2. Extract the requested point/time via data_extractor
# 3. Print the result and write it out as a .json summary

# Key library imports
import json  # for printing and saving the wind_summary
import os  # for creating the output directory and building the output path

import build_GraphCast
import data_extractor
import prediciton_build_test

OUTPUT_DIR = "Outputs/GraphCast"  # wind_summary .json files get written here


def run_query(lat, lon, time_str):
    run_forward_jitted, model_config, task_config = build_GraphCast.load_model()
    predictions = prediciton_build_test.run_rollout(run_forward_jitted, model_config, task_config)

    wind_summary = data_extractor.extract_point(predictions, lat, lon, time_str)

    print("wind_summary:")
    print(json.dumps(wind_summary, indent=2))

    save_summary(wind_summary)

    return wind_summary


def save_summary(wind_summary):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, "wind_summary.json")

    with open(output_path, "w") as f:
        json.dump(wind_summary, f, indent=2)

    print(f"Saved to {output_path}")


if __name__ == "__main__":
    # Fallback for running this file directly outside Colab -- hardcoded test values,
    # swappable in one place just like the other scripts' QUERY_LAT/LON/TIME constants
    QUERY_LAT = 34.05
    QUERY_LON = -118.25
    QUERY_TIME = "2019-03-29T18:00"

    run_query(QUERY_LAT, QUERY_LON, QUERY_TIME)
