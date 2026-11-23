"""
inspect_data.py - read-only health check of one day. Changes nothing.

Prints (and with --save also writes data/reports/summary_<day>.txt):
  * how many polls ran, and any gaps longer than 15 minutes
  * board rows, trains seen, status mix
  * movements: how many trains have actual times, and how many are
    "automatic" (Irish Rail's flag for times that were not really measured)
  * weather rows and the columns found
  * failed calls
  * merged row counts
  * a first look at accuracy: how far Irish Rail's prediction and the plain
    timetable are from the actual time

Usage:  python scripts/inspect_data.py 2026-11-20 [--save]   (default: yesterday)
"""

import sys

import pandas as pd

from common import (RAW, CLEAN, MERGED, LOGS, REPORTS, TRAIN_IDS_FILE,
                    day_from_args, read_text_csv)

lines = []


def say(text=""):
    print(text)
    lines.append(text)


def load(path):
    return read_text_csv(path) if path.exists() else None


def to_minutes(series):
    """'14:36' -> 876 (minutes since midnight). Blank/odd -> NaN."""
    s = series.fillna("").str[:5]
    return pd.to_numeric(s.str[:2], errors="coerce") * 60 + pd.to_numeric(s.str[3:5], errors="coerce")


def wrap(diff):
    """Keep a time difference within +-12 hours so a midnight crossing does not give 1,400 minutes."""
    return ((diff + 720) % 1440) - 720


def accuracy(m):
    if "Mov_Arrival" not in m.columns:
        say("  no actual times yet.")
        return
    is_dest = m["Locationtype"] == "D"
    predicted = to_minutes(m["Exparrival"].where(is_dest, m["Expdepart"]))
    scheduled = to_minutes(m["Scharrival"].where(is_dest, m["Schdepart"]))
    actual_text = m["Mov_Arrival"].where(is_dest, m["Mov_Departure"]).fillna("")
    actual = to_minutes(actual_text)
    # "" and "00:00" mean "no actual time recorded" (assumption - check on real data)
    actual[actual_text.isin(["", "00:00"])] = float("nan")

    d = pd.DataFrame({
        "pred_err": wrap(predicted - actual).abs(),
        "sched_err": wrap(scheduled - actual).abs(),
        "ahead": pd.to_numeric(m["Duein"], errors="coerce"),
        "live": m["Status"].ne("No Information"),
    }).dropna(subset=["pred_err", "sched_err", "ahead"])
    if d.empty:
        say("  no rows with both a prediction and an actual time yet.")
        return
    say(f"  rows compared: {len(d)}")
    say("  typical (median) error in minutes, prediction vs timetable:")
    bins = pd.cut(d["ahead"], [-1, 10, 30, 60, 1000], labels=["0-10 min", "10-30", "30-60", "60+"])
    for label, part in d.groupby(bins, observed=True):
        say(f"    {label:>9} before: prediction {part['pred_err'].median():.1f} | "
            f"timetable {part['sched_err'].median():.1f}   (n={len(part)})")
    live = d[d["live"]]
    say(f"  only rows where Irish Rail had live info: prediction {live['pred_err'].median():.1f} | "
        f"timetable {live['sched_err'].median():.1f}   (n={len(live)})")


def main():
    day = day_from_args(sys.argv, default="yesterday")
    say(f"===== Data check for {day} (UTC) =====")

    # ---- Boards
    boards = load(RAW / "trains" / f"trains_{day}.csv")
    say("\n[Boards - raw]")
    if boards is None:
        say("  no file")
    else:
        runs = sorted(pd.to_datetime(boards["CollectedAtUTC"].str[:19]).unique())
        say(f"  rows: {len(boards)} | polls with trains: {len(runs)} (about 114 expected for a full day)")
        gaps = [(runs[i - 1], runs[i]) for i in range(1, len(runs))
                if (runs[i] - runs[i - 1]) > pd.Timedelta(minutes=15)]
        say(f"  gaps over 15 minutes between polls: {len(gaps)}")
        for a, b in gaps[:8]:
            say(f"    {str(a)[11:16]} -> {str(b)[11:16]}")
        say(f"  trains seen: {boards.drop_duplicates(['Traincode', 'Traindate']).shape[0]}")
        say("  by station and type (O = starts here, D = ends here): "
            + str(boards.groupby(["Stationcode", "Locationtype"]).size().to_dict()))
        say("  status mix: " + str(boards["Status"].value_counts().to_dict()))
        say("  NOTE: 'No Information' rows have Late = 0 as a placeholder, not 'on time'.")

    ids = load(TRAIN_IDS_FILE)
    say(f"\n[Known train codes] {len(ids) if ids is not None else 'no file'}")

    # ---- Movements
    mov = load(RAW / "movements" / f"movements_{day}.csv")
    say("\n[Movements - raw]")
    if mov is None:
        say("  no file")
    else:
        trains = mov.drop_duplicates(["TrainCode", "TrainDate"]).shape[0]
        say(f"  stop rows: {len(mov)} | trains: {trains}")
        dest = mov[mov["LocationType"] == "D"]
        have = (~dest["Arrival"].isin(["", "00:00"])).sum() if "Arrival" in dest else 0
        say(f"  trains with an actual arrival at their destination: {int(have)} of {len(dest)}")
        for col in ("AutoArrival", "AutoDepart"):
            if col in mov.columns:
                say(f"  {col}: {mov[col].value_counts().to_dict()}")

    # ---- Weather
    om = load(RAW / "openmeteo" / f"openmeteo_{day}.csv")
    met = load(RAW / "met_eireann" / f"met_eireann_{day}.csv")
    say("\n[Weather]")
    say(f"  Open-Meteo rows: {len(om) if om is not None else 'no file'} (48 expected = 2 stations x 24 h)")
    if met is None:
        say("  Met Eireann: no file")
    else:
        say(f"  Met Eireann rows: {len(met)} | per station: {met['MetSlug'].value_counts().to_dict()}")
        say(f"  Met Eireann columns: {list(met.columns)}")

    # ---- Failures
    fails = load(LOGS / f"failures_{day}.csv")
    say("\n[Failed calls]")
    if fails is None or fails.empty:
        say("  none logged")
    else:
        say(f"  total: {len(fails)}")
        for (source, error), n in fails.groupby(["Source", "Error"]).size().sort_values(ascending=False).head(8).items():
            say(f"    {n} x {source}: {error[:100]}")

    # ---- Merged
    merged = load(MERGED / f"merged_{day}.csv")
    say("\n[Merged]")
    if merged is None:
        say("  no file")
    else:
        say(f"  rows: {len(merged)}")
        for col in ("Mov_Arrival", "OM_temperature_2m"):
            if col in merged.columns:
                say(f"  rows with {col}: {int(merged[col].ne('').sum())}")
        say("\n[Accuracy - first look]")
        accuracy(merged)

    if "--save" in sys.argv:
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / f"summary_{day}.txt").write_text("\n".join(lines), encoding="utf-8")
        print(f"\nSaved to data/reports/summary_{day}.txt")


if __name__ == "__main__":
    main()
