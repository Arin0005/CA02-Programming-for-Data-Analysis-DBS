"""
merge_data.py - NEW. Joins the cleaned train data with the two weather sources.

  * Open-Meteo : joined on station code + hour of collection
  * Met Eireann: joined on the NEAREST Met Eireann station (by distance from
                 the train station) + hour of collection

Nothing is added except the weather columns. The coordinates file is only
used to FIND the nearest station - its latitude/longitude are not put in the
merged file, and neither is the distance.

Usage:  python scripts/merge_data.py 2026-11-15
(run clean_trains.py for the same day first)
"""

from math import radians, sin, cos, asin, sqrt

import pandas as pd

from common import RAW, CLEAN, MERGED, STATIONS_FILE, MET_COORDS_FILE, day_from_args


def distance_km(lat1, lon1, lat2, lon2):
    """Straight-line distance between two lat/lon points (haversine formula)."""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


def read_text_csv(path):
    """Read a CSV with every value as text so nothing is changed."""
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def main():
    day = day_from_args()

    trains_path = CLEAN / f"trains_clean_{day}.csv"
    if not trains_path.exists():
        print(f"No clean train file for {day}. Run clean_trains.py {day} first.")
        return
    trains = read_text_csv(trains_path)

    # The train API spells the column "Stationcode"; the station list and
    # Open-Meteo file use "StationCode". Find the right one by name.
    train_code = next(c for c in trains.columns if c.lower() == "stationcode")

    # ----- Hour of collection: "2026-11-15T21:07:03+00:00" -> "2026-11-15T21"
    # We agreed to join on the hour, not the exact second. This is a TEMPORARY
    # helper column and is removed before saving.
    trains["_hour"] = trains["CollectedAtUTC"].str[:13]

    # ================= Open-Meteo =================
    om_path = RAW / "openmeteo" / f"openmeteo_{day}.csv"
    if om_path.exists():
        om = read_text_csv(om_path)
        om["_hour"] = om["CollectedAtUTC"].str[:13]
        # If there are two readings in one hour (e.g. you ran a manual test),
        # keep the newest so the join cannot create extra train rows.
        om = om.sort_values("CollectedAtUTC").drop_duplicates(["StationCode", "_hour"], keep="last")
        # Station name / coordinates / time stamp are already known from the
        # train side or are not weather, so only the weather columns are kept.
        weather_cols = [c for c in om.columns if c not in
                        ("StationCode", "StationDesc", "StationLatitude",
                         "StationLongitude", "CollectedAtUTC", "_hour")]
        om = om[["StationCode", "_hour"] + weather_cols]
        # "OM_" prefix: only so you can tell which source a column came from
        om = om.rename(columns={c: "OM_" + c for c in weather_cols})
        om = om.rename(columns={"StationCode": train_code})
        merged = trains.merge(om, on=[train_code, "_hour"], how="left")
    else:
        print("No Open-Meteo file for this day - skipped.")
        merged = trains
        om_path = None

    # ================= Met Eireann (nearest station) =================
    met_path = RAW / "met_eireann" / f"met_eireann_{day}.csv"
    if met_path.exists() and MET_COORDS_FILE.exists() and STATIONS_FILE.exists():
        met = read_text_csv(met_path)
        met["_hour"] = met["CollectedAtUTC"].str[:13]
        met = met.sort_values("CollectedAtUTC").drop_duplicates(["Station", "_hour"], keep="last")

        coords = read_text_csv(MET_COORDS_FILE)
        coords["Latitude"] = coords["Latitude"].astype(float)
        coords["Longitude"] = coords["Longitude"].astype(float)

        # Tell the user if a name in the Met file is missing from our coordinate file
        unmatched = set(met["Station"]) - set(coords["Station"])
        if unmatched:
            print("WARNING: Met Eireann stations without coordinates:", sorted(unmatched))

        # For each train station, find the closest Met Eireann station (once).
        stations = read_text_csv(STATIONS_FILE)
        nearest = {}
        for _, s in stations.iterrows():
            try:
                lat, lon = float(s["StationLatitude"]), float(s["StationLongitude"])
            except ValueError:
                continue
            if lat == 0 and lon == 0:
                continue   # no real position, so no nearest station
            distances = coords.apply(
                lambda m: distance_km(lat, lon, m["Latitude"], m["Longitude"]), axis=1)
            nearest[s["StationCode"]] = coords.loc[distances.idxmin(), "Station"]

        merged["_met_station"] = merged[train_code].map(nearest)

        met_cols = [c for c in met.columns if c not in ("CollectedAtUTC", "_hour", "Station")]
        met = met[["Station", "_hour"] + met_cols]
        # "Met_" prefix: same reason as "OM_". The Met station name stays as
        # Met_Station so you can see WHICH station each row was matched to.
        met = met.rename(columns={c: "Met_" + c for c in met.columns if c != "_hour"})
        merged = merged.merge(met, left_on=["_met_station", "_hour"],
                              right_on=["Met_Station", "_hour"], how="left")
        merged = merged.drop(columns=["_met_station"])
    else:
        print("Met Eireann file or coordinates missing - skipped.")

    # Remove the temporary helper column and save
    merged = merged.drop(columns=["_hour"])
    out_path = MERGED / f"merged_{day}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out_path, index=False)

    # Quick check printed so you can see the joins worked
    print(f"{day}: {len(merged)} merged rows (train rows in: {len(trains)})")
    if "OM_temperature_2m" in merged.columns:
        print("  rows with Open-Meteo weather:", int((merged["OM_temperature_2m"] != "").sum()))
    if "Met_Station" in merged.columns:
        print("  rows with a Met Eireann match:", int(merged["Met_Station"].notna().sum()))


if __name__ == "__main__":
    main()
