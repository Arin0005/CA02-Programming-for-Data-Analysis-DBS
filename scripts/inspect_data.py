"""
inspect_data.py - NEW. A read-only health check of one day's collected data.

It changes nothing. It prints (and with --save also writes to
data/reports/summary_<day>.txt):
  * how many rows / runs each source has for the day
  * failed calls, grouped by source and error
  * missing values per column (blank, or "-" for Met Eireann)
  * duplicates in the raw trains
  * stations that never had a train that day
  * a few sample rows

Usage:
  python scripts/inspect_data.py                  (today, UTC)
  python scripts/inspect_data.py 2026-11-15       (a chosen day)
  python scripts/inspect_data.py 2026-11-15 --save
"""

import sys

import pandas as pd

from common import RAW, CLEAN, MERGED, LOGS, REPORTS, STATIONS_FILE, day_from_args

lines = []   # everything we print is also kept here for --save


def say(text=""):
    print(text)
    lines.append(text)


def load(path):
    if path.exists():
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    return None


def missing_report(df, name):
    """Count empty values and Met Eireann's '-' placeholders per column."""
    say(f"  Missing values in {name} (blank or '-'):")
    for col in df.columns:
        n = int(df[col].isin(["", "-"]).sum())
        if n:
            say(f"    {col}: {n} of {len(df)}")


def main():
    day = day_from_args()
    say(f"===== Data check for {day} (UTC) =====")

    # ---- Trains
    trains = load(RAW / "trains" / f"trains_{day}.csv")
    say("\n[Trains - raw]")
    if trains is None:
        say("  no file")
    else:
        say(f"  rows: {len(trains)} | runs (hours collected): {trains['CollectedAtUTC'].nunique()}")
        say(f"  first run: {trains['CollectedAtUTC'].min()} | last run: {trains['CollectedAtUTC'].max()}")
        dupes = len(trains) - len(trains.drop_duplicates(["Traincode", "Traindate", "Stationcode"]))
        say(f"  duplicate rows (same train/date/station): {dupes}")
        missing_report(trains, "trains")

        stations = load(STATIONS_FILE)
        if stations is not None:
            never = sorted(set(stations["StationCode"]) - set(trains["Stationcode"]))
            say(f"  stations with no trains all day: {len(never)} of {len(stations)}")
            if never:
                say("    " + ", ".join(never))

    # ---- Open-Meteo
    om = load(RAW / "openmeteo" / f"openmeteo_{day}.csv")
    say("\n[Open-Meteo - raw]")
    if om is None:
        say("  no file")
    else:
        say(f"  rows: {len(om)} | runs: {om['CollectedAtUTC'].nunique()} | stations: {om['StationCode'].nunique()}")
        missing_report(om, "open-meteo")

    # ---- Met Eireann
    met = load(RAW / "met_eireann" / f"met_eireann_{day}.csv")
    say("\n[Met Eireann - raw]")
    if met is None:
        say("  no file")
    else:
        say(f"  rows: {len(met)} | runs: {met['CollectedAtUTC'].nunique()} | stations: {met['Station'].nunique()}")
        missing_report(met, "met eireann")

    # ---- Failures
    fails = load(LOGS / f"failures_{day}.csv")
    say("\n[Failed calls]")
    if fails is None or fails.empty:
        say("  none logged")
    else:
        say(f"  total: {len(fails)}")
        for (source, error), n in fails.groupby(["Source", "Error"]).size().sort_values(ascending=False).head(10).items():
            say(f"    {n} x {source}: {error[:100]}")

    # ---- Clean and merged
    clean = load(CLEAN / f"trains_clean_{day}.csv")
    merged = load(MERGED / f"merged_{day}.csv")
    say("\n[Clean and merged]")
    say(f"  clean rows: {len(clean) if clean is not None else 'no file'}")
    say(f"  merged rows: {len(merged) if merged is not None else 'no file'}")
    if merged is not None:
        say("  sample merged rows:")
        say(merged.head(5).to_string(index=False)[:2500])

    if "--save" in sys.argv:
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / f"summary_{day}.txt").write_text("\n".join(lines), encoding="utf-8")
        print(f"\nSaved to data/reports/summary_{day}.txt")


if __name__ == "__main__":
    main()
