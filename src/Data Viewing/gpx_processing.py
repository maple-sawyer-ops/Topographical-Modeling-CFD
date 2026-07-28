"""Parse a GPX track (incl. Garmin TrackPointExtension channels) into a pandas DataFrame."""

import os
import xml.etree.ElementTree as ET

import pandas as pd

GPX_PATH = os.path.join("Data", "files_gpx", "English_Weather_.gpx")
CACHE_DIR = os.path.join("out", "gpx_cache")

GPX_NS = "http://www.topografix.com/GPX/1/1"
TPX_NS = "http://www.garmin.com/xmlschemas/TrackPointExtension/v1"


def _local_tag(element):
    """Strip the namespace off an ElementTree tag, e.g. '{ns}atemp' -> 'atemp'."""
    return element.tag.rsplit("}", 1)[-1]


def parse_gpx_trackpoints(gpx_path):
    """Parse every <trkpt> in a GPX file into a list of dicts (one per point).

    Core fields (lat, lon, ele, time) are always present. Any additional
    channels found inside <extensions> (e.g. gpxtpx:atemp, gpxtpx:hr) are
    picked up generically by tag name, so the parser works on GPX files with
    different extension channels without hardcoding their names.
    """
    tree = ET.parse(gpx_path)
    root = tree.getroot()

    points = []
    for trkpt in root.findall(f".//{{{GPX_NS}}}trkpt"):
        point = {
            "lat": float(trkpt.get("lat")),
            "lon": float(trkpt.get("lon")),
        }

        ele = trkpt.find(f"{{{GPX_NS}}}ele")
        point["ele"] = float(ele.text) if ele is not None else None

        time = trkpt.find(f"{{{GPX_NS}}}time")
        point["time"] = time.text if time is not None else None

        for extensions in trkpt.findall(f"{{{GPX_NS}}}extensions"):
            for child in extensions.iter():
                if child is extensions or list(child):
                    continue  # skip container elements, only keep leaf values
                point[_local_tag(child)] = child.text

        points.append(point)

    return points


def _cache_path(gpx_path, cache_dir):
    stem = os.path.splitext(os.path.basename(gpx_path))[0]
    return os.path.join(cache_dir, f"{stem}.pkl")


def load_gpx(gpx_path=GPX_PATH, use_cache=True, cache_dir=CACHE_DIR):
    """Load a GPX file's track points into a time-sorted pandas DataFrame.

    Parsed results are cached to a pickle next to `cache_dir`, keyed on the
    GPX filename. The cache is reused as long as it is newer than the source
    GPX file (mirrors the cached-download pattern in pull_wind_data.py), so
    repeat loads skip re-parsing the XML.
    """
    cache_path = _cache_path(gpx_path, cache_dir)

    if use_cache and os.path.exists(cache_path) and (
        os.path.getmtime(cache_path) >= os.path.getmtime(gpx_path)
    ):
        return pd.read_pickle(cache_path)

    points = parse_gpx_trackpoints(gpx_path)
    if not points:
        raise ValueError(f"No trackpoints found in {gpx_path}")

    df = pd.DataFrame(points)
    df["time"] = pd.to_datetime(df["time"])

    # Extension channels (e.g. atemp, hr) arrive as text; coerce to numeric.
    known_cols = {"lat", "lon", "ele", "time"}
    for col in df.columns:
        if col not in known_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("time").reset_index(drop=True)

    if use_cache:
        os.makedirs(cache_dir, exist_ok=True)
        df.to_pickle(cache_path)

    return df


def main():
    df = load_gpx()
    print(f"Loaded {len(df)} trackpoints from {GPX_PATH}")
    print(df.dtypes)
    print(df.head())
    return df


if __name__ == "__main__":
    main()
