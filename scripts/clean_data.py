"""
clean_data.py - removes only GENUINE repeats for one day. Raw files are
only read, never changed.

CHANGED from v1: v1 kept one row per train/date/station, which threw away
earlier predictions. That history is exactly what you need to judge how
accurate Irish Rail's predictions are, so now:

  * boards     : a row is a repeat only if it has the same collection time,
                 train, date and station (same poll, listed twice).
                 Every different snapshot of a train is KEPT.
  * movements  : one row per train, date and stop. If the journey was
                 fetched more than once (a manual re-run) the newest wins.

Usage:  python scripts/clean_data.py 2026-11-20     (default: yesterday)
"""

import sys

from common import RAW, CLEAN, day_from_args, read_text_csv


def clean_file(raw_path, out_path, key, label):
    if not raw_path.exists():
        print(f"{label}: no raw file for this day, skipped.")
        return
    df = read_text_csv(raw_path)
    key = [c for c in key if c in df.columns]
    # Oldest first, so keep="last" keeps the newest copy.
    df = df.sort_values("CollectedAtUTC", kind="stable")
    clean = df.drop_duplicates(subset=key, keep="last")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    clean.to_csv(out_path, index=False)
    print(f"{label}: raw {len(df)} -> clean {len(clean)} ({len(df) - len(clean)} repeats removed)")


def main():
    day = day_from_args(sys.argv, default="yesterday")
    clean_file(RAW / "trains" / f"trains_{day}.csv",
               CLEAN / f"trains_clean_{day}.csv",
               ["CollectedAtUTC", "Traincode", "Traindate", "Stationcode"],
               "boards")
    clean_file(RAW / "movements" / f"movements_{day}.csv",
               CLEAN / f"movements_clean_{day}.csv",
               ["TrainCode", "TrainDate", "LocationCode", "LocationOrder"],
               "movements")


if __name__ == "__main__":
    main()
