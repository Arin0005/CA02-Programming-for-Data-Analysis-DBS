"""
collect_weather.py - NEW. Runs ONCE A DAY and collects a full day of hourly
weather, so weather no longer slows down or breaks the train collection.

Two sources, both for Dublin only:
  1. Open-Meteo  - a weather MODEL estimate at the exact Heuston and Connolly
                   coordinates. Only 2 locations in ONE request per day, so the
                   "request limit exceeded" problem from v1 (about 320 requests
                   a day) goes away.
  2. Met Eireann - real MEASURED hourly observations from the weather stations
                   at Phoenix Park and Dublin Airport. The observations come with
                   a date and a time, which the old CSV download did not have.

Saved to: data/raw/openmeteo/openmeteo_<day>.csv
          data/raw/met_eireann/met_eireann_<day>.csv

Usage:  python scripts/collect_weather.py 2026-11-20     (default: yesterday)
"""

import sys
import time
from datetime import datetime, timedelta

import pandas as pd
import requests

from common import (RAW, DUBLIN_STATIONS_FILE, iso, now_utc, day_string,
                    day_from_args, append_to_csv, log_failure, read_text_csv)

OM_URL = "https://api.open-meteo.com/v1/forecast"
OM_VARIABLES = "temperature_2m,precipitation,wind_speed_10m,wind_gusts_10m,relative_humidity_2m"

MET_URL = "https://prodapi.met.ie/observations/{slug}/{which}"
MET_SLUGS = ["phoenix-park", "dublin"]          # "dublin" = Dublin Airport


def get_with_retries(url, params=None, headers=None):
    """
    CHANGED: v1 retried straight away with a 30 s timeout, which just kept
    hitting the limit. This waits 30 s, then 90 s before giving up, which is
    fine for a job that runs once a day.
    """
    last_error = None
    for wait in (0, 30, 90):
        time.sleep(wait)
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            return response
        except Exception as error:
            last_error = error
    raise last_error


def collect_open_meteo(day):
    stations = read_text_csv(DUBLIN_STATIONS_FILE)
    age_days = (now_utc().date() - datetime.strptime(day, "%Y-%m-%d").date()).days
    if age_days < 0 or age_days > 90:
        print("Open-Meteo: day is in the future or too old - skipped.")
        return False

    params = {
        "latitude": ",".join(stations["StationLatitude"]),
        "longitude": ",".join(stations["StationLongitude"]),
        "hourly": OM_VARIABLES,
        "past_days": age_days + 1,     # reach back far enough to include the chosen day
        "forecast_days": 1,
        "timezone": "UTC",
    }
    try:
        results = get_with_retries(OM_URL, params=params).json()
        if isinstance(results, dict):               # one location comes back as a dict
            results = [results]
        # Results are matched to stations BY ORDER, so a wrong count must not be guessed.
        if len(results) != len(stations):
            raise ValueError(f"expected {len(stations)} results, got {len(results)}")

        collected_at = iso(now_utc())
        rows = []
        for i, station in stations.iterrows():
            hourly = results[i]["hourly"]
            for k, hour in enumerate(hourly["time"]):
                if hour[:10] != day:                # keep only the chosen day
                    continue
                row = {"StationCode": station["StationCode"], "time": hour}
                for name in OM_VARIABLES.split(","):
                    row[name] = hourly[name][k]
                row["CollectedAtUTC"] = collected_at
                rows.append(row)
        if not rows:
            raise ValueError("no hourly rows for that day")
        append_to_csv(pd.DataFrame(rows), RAW / "openmeteo" / f"openmeteo_{day}.csv")
        print(f"Open-Meteo: {len(rows)} hourly rows saved")
        return True
    except Exception as error:
        log_failure("open_meteo", day, error)
        return False


def collect_met_eireann(day):
    today = day_string(now_utc())
    yesterday = day_string(now_utc() - timedelta(days=1))
    which = "today" if day == today else "yesterday" if day == yesterday else None
    if which is None:
        print("Met Eireann only offers today and yesterday - skipped.")
        return False

    ok = False
    for slug in MET_SLUGS:
        try:
            response = get_with_retries(MET_URL.format(slug=slug, which=which),
                                        headers={"User-Agent": "Mozilla/5.0 (student-data-project)"})
            data = response.json()
            if isinstance(data, dict):
                data = [data]
            # Saved exactly as given (every value as text). Nothing is renamed or converted.
            df = pd.json_normalize(data).fillna("").astype(str)
            if df.empty:
                raise ValueError("no observations returned")
            df.insert(0, "MetSlug", slug)
            df["CollectedAtUTC"] = iso(now_utc())
            append_to_csv(df, RAW / "met_eireann" / f"met_eireann_{day}.csv")
            print(f"Met Eireann {slug}: {len(df)} observations saved. Columns: {list(df.columns)}")
            ok = True
        except Exception as error:
            log_failure("met_eireann", slug, error)
    return ok


def main():
    day = day_from_args(sys.argv, default="yesterday")
    om_ok = collect_open_meteo(day)
    met_ok = collect_met_eireann(day)
    if not om_ok and not met_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
