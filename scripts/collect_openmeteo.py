"""
collect_openmeteo.py - cell 2 of your notebook, as a script.

Asks Open-Meteo for the current weather at the coordinates of every
Republic of Ireland station and appends it to
data/raw/openmeteo/openmeteo_<day>.csv
"""

import sys
import time

import pandas as pd
import requests

from common import (RAW, run_day, run_iso, append_to_csv, log_failure,
                    get_roi_stations)

URL = "https://api.open-meteo.com/v1/forecast"
CURRENT = "temperature_2m,precipitation,wind_speed_10m,wind_gusts_10m,relative_humidity_2m"


def main():
    stations = get_roi_stations()

    # CHANGED: your code removed stations with missing coordinates. The Irish
    # Rail list can also contain 0 / 0, which is "off the coast of Africa"
    # and would give meaningless weather, so those are removed too.
    stations["StationLatitude"] = pd.to_numeric(stations["StationLatitude"], errors="coerce")
    stations["StationLongitude"] = pd.to_numeric(stations["StationLongitude"], errors="coerce")
    stations = stations.dropna(subset=["StationLatitude", "StationLongitude"])
    stations = stations[(stations["StationLatitude"] != 0) | (stations["StationLongitude"] != 0)]
    stations = stations.reset_index(drop=True)
    print("Stations with coordinates:", len(stations))

    collected_at = run_iso()   # CHANGED: one time for the whole run
    weather_rows = []
    failed_batches = 0
    batches = 0

    # Same batching of 10 as your original (Open-Meteo accepts many locations per call)
    for start in range(0, len(stations), 10):
        batch = stations.iloc[start:start + 10]
        batches += 1
        params = {
            "latitude": ",".join(batch["StationLatitude"].astype(str)),
            "longitude": ",".join(batch["StationLongitude"].astype(str)),
            "current": CURRENT,
            "timezone": "UTC",
        }

        for attempt in (1, 2):   # NEW: one retry, same reason as the train script
            try:
                response = requests.get(URL, params=params, timeout=30)
                response.raise_for_status()
                results = response.json()

                if isinstance(results, dict):   # a batch of 1 comes back as a single dict
                    results = [results]

                # NEW: results are matched to stations BY ORDER, so if the count
                # is wrong we must not guess - treat the batch as failed.
                if len(results) != len(batch):
                    raise ValueError(f"expected {len(batch)} results, got {len(results)}")

                for i, result in enumerate(results):
                    row = result["current"].copy()
                    row["StationCode"] = batch.iloc[i]["StationCode"]
                    row["StationDesc"] = batch.iloc[i]["StationDesc"]
                    row["StationLatitude"] = batch.iloc[i]["StationLatitude"]
                    row["StationLongitude"] = batch.iloc[i]["StationLongitude"]
                    row["CollectedAtUTC"] = collected_at
                    weather_rows.append(row)
                break

            except Exception as error:
                if attempt == 2:
                    failed_batches += 1
                    # CHANGED: saved to the failures file, with the station codes
                    log_failure("open_meteo", ",".join(batch["StationCode"].tolist()), error)
                else:
                    time.sleep(2)

        time.sleep(1)   # same pause as your original

    print("Weather records collected:", len(weather_rows))

    if weather_rows:
        append_to_csv(pd.DataFrame(weather_rows),
                      RAW / "openmeteo" / f"openmeteo_{run_day()}.csv")

    # NEW: all batches failed -> show the run as failed in GitHub
    if batches and failed_batches == batches:
        sys.exit(1)


if __name__ == "__main__":
    main()
