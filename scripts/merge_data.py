"""
merge_data.py - joins one day of board snapshots with
  * the ACTUAL times from the train movements   (columns start with Mov_)
  * Open-Meteo weather at the same station       (columns start with OM_)
  * Met Eireann observations from the NEAREST Met station (columns start with Met_)

Nothing else is added. The prefixes are only so you can tell the sources
apart; the values are untouched. Met station coordinates are used to find
the nearest station but are NOT put in the merged file.

Usage:  python scripts/merge_data.py 2026-11-20     (default: yesterday)
        (run clean_data.py for the same day first)
"""

import sys
from math import radians, sin, cos, asin, sqrt

import pandas as pd

from common import (RAW, CLEAN, MERGED, DUBLIN_STATIONS_FILE, MET_COORDS_FILE,
                    day_from_args, read_text_csv, parse_api_dates)

# Which hour should the weather be matched to?
#   "event"     = the hour the train was DUE (its scheduled arrival, or
#                 departure for a train that starts here)         <- default
#   "collected" = the hour the board snapshot was taken
# CHANGED from v1, which always used the collection hour (your Problem 10).
WEATHER_JOIN_ON = "event"

# The Met Eireann JSON column names for the observation date and time.
# I could not open that API from my tools, so these are my best guess.
# If the first real file uses other names, change them here (the column
# names are printed when collect_weather.py runs).
MET_DATE_COL = "date"
MET_TIME_COL = "reportTime"


def distance_km(lat1, lon1, lat2, lon2):
    """Straight-line distance between two points (haversine formula)."""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


def load_all(folder, pattern):
    """Read and stack every file matching the pattern (weather and movements span several days)."""
    files = sorted(folder.glob(pattern))
    if not files:
        return None
    return pd.concat([read_text_csv(f) for f in files], ignore_index=True)


def event_datetime(b):
    """
    The time the train was due at this station, as a real date-time.
    A train that ENDS here uses its scheduled arrival; one that STARTS here
    uses its scheduled departure.
    If a train ends after midnight (its end time is earlier than its start
    time) the event is on the next calendar day.
    """
    base = parse_api_dates(b["Traindate"])
    is_dest = b["Locationtype"] == "D"
    hhmm = b["Scharrival"].where(is_dest, b["Schdepart"]).str[:5]
    event = base + pd.to_timedelta(hhmm + ":00", errors="coerce")
    crossed_midnight = is_dest & (hhmm < b["Origintime"].str[:5])
    return event.where(~crossed_midnight, event + pd.Timedelta(days=1))


def find_column(df, wanted):
    """Find a column by name ignoring upper/lower case."""
    for c in df.columns:
        if c.lower() == wanted.lower():
            return c
    return None


def main():
    day = day_from_args(sys.argv, default="yesterday")
    boards_path = CLEAN / f"trains_clean_{day}.csv"
    if not boards_path.exists():
        print(f"No clean board file for {day}. Run clean_data.py {day} first.")
        return
    boards = read_text_csv(boards_path)
    rows_in = len(boards)

    # Helper columns (starting with "_") are removed before saving.
    boards["_event"] = event_datetime(boards)
    if WEATHER_JOIN_ON == "collected":
        boards["_hour"] = pd.to_datetime(boards["CollectedAtUTC"].str[:19], errors="coerce").dt.floor("h")
    else:
        boards["_hour"] = boards["_event"].dt.floor("h")

    # ================= Actual times (train movements) =================
    mov = load_all(CLEAN, "movements_clean_*.csv")
    if mov is not None:
        mov = mov.rename(columns={"TrainCode": "Traincode", "TrainDate": "Traindate",
                                  "LocationCode": "Stationcode"})
        key = ["Traincode", "Traindate", "Stationcode"]
        mov = mov.sort_values("CollectedAtUTC").drop_duplicates(key, keep="last")
        wanted = [c for c in ["Arrival", "Departure", "AutoArrival", "AutoDepart"] if c in mov.columns]
        mov = mov[key + wanted].rename(columns={c: "Mov_" + c for c in wanted})
        boards = boards.merge(mov, on=key, how="left")
    else:
        print("No movements files yet - actual times skipped.")

    # ================= Open-Meteo =================
    om = load_all(RAW / "openmeteo", "openmeteo_*.csv")
    if om is not None:
        om["_hour"] = pd.to_datetime(om["time"], errors="coerce")
        om = om.sort_values("CollectedAtUTC").drop_duplicates(["StationCode", "_hour"], keep="last")
        cols = [c for c in om.columns if c not in ("StationCode", "time", "CollectedAtUTC", "_hour")]
        om = om[["StationCode", "_hour"] + cols].rename(columns={c: "OM_" + c for c in cols})
        om = om.rename(columns={"StationCode": "Stationcode"})
        boards = boards.merge(om, on=["Stationcode", "_hour"], how="left")
    else:
        print("No Open-Meteo files yet - skipped.")

    # ================= Met Eireann (nearest station) =================
    met = load_all(RAW / "met_eireann", "met_eireann_*.csv")
    if met is not None:
        date_col = find_column(met, MET_DATE_COL)
        time_col = find_column(met, MET_TIME_COL)
        if date_col is None or time_col is None:
            print("WARNING: cannot find the Met Eireann date/time columns. "
                  f"Columns are: {list(met.columns)}. Set MET_DATE_COL / MET_TIME_COL at the top "
                  "of merge_data.py. Met join skipped.")
        else:
            # Nearest Met station for each of our stations (distance, once).
            coords = read_text_csv(MET_COORDS_FILE)
            stations = read_text_csv(DUBLIN_STATIONS_FILE)
            nearest = {}
            for _, s in stations.iterrows():
                dist = coords.apply(lambda m: distance_km(
                    float(s["StationLatitude"]), float(s["StationLongitude"]),
                    float(m["Latitude"]), float(m["Longitude"])), axis=1)
                nearest[s["StationCode"]] = coords.loc[dist.idxmin(), "MetSlug"]
            boards["_met"] = boards["Stationcode"].map(nearest)

            # Observation date + time -> the hour it belongs to.
            iso_dates = met[date_col].str.match(r"^\d{4}-").all()
            met["_hour"] = pd.to_datetime(met[date_col] + " " + met[time_col],
                                          dayfirst=not iso_dates, errors="coerce").dt.floor("h")
            met = met.sort_values("CollectedAtUTC").drop_duplicates(["MetSlug", "_hour"], keep="last")
            cols = [c for c in met.columns if c not in ("MetSlug", "_hour", "CollectedAtUTC")]
            met = met[["MetSlug", "_hour"] + cols].rename(columns={c: "Met_" + c for c in cols})
            met = met.rename(columns={"MetSlug": "_met"})
            boards = boards.merge(met, on=["_met", "_hour"], how="left")
            # Keep the matched station's name so you can see which one was used.
            boards = boards.rename(columns={"_met": "Met_Station"})
    else:
        print("No Met Eireann files yet - skipped.")

    boards = boards.drop(columns=[c for c in boards.columns if c.startswith("_")])
    if len(boards) != rows_in:
        print(f"WARNING: row count changed {rows_in} -> {len(boards)}; a join created duplicates.")

    out = MERGED / f"merged_{day}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    boards.to_csv(out, index=False)

    # Quick check printed so you can see which joins worked.
    print(f"{day}: {len(boards)} merged rows (board rows in: {rows_in})")
    for label, col in [("actual time", "Mov_Arrival"), ("Open-Meteo", "OM_temperature_2m")]:
        if col in boards.columns:
            filled = boards[col].fillna("").ne("").sum()
            print(f"  rows with {label}: {int(filled)}")
    if "Met_Station" in boards.columns:
        others = [c for c in boards.columns if c.startswith("Met_") and c != "Met_Station"]
        if others:
            print("  rows with Met Eireann data:", int(boards[others[0]].fillna("").ne("").sum()))


if __name__ == "__main__":
    main()
