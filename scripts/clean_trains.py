"""
clean_trains.py - NEW. Removes duplicate train rows for one day.

Why duplicates exist: we take a snapshot of every station board every hour,
and a train is on the board for up to ~90 minutes, so the SAME train at the
SAME station shows up in several snapshots.

Result: one row per (train, date, station).
The raw file is only READ, never changed, so the raw data is always kept.

Usage:  python scripts/clean_trains.py 2026-11-15
"""

import sys

import pandas as pd

from common import RAW, CLEAN, day_from_args

# The three columns that identify "one train, one date, one station".
# (Names are exactly as the Irish Rail API spells them.)
KEY = ["Traincode", "Traindate", "Stationcode"]

# Which snapshot to keep when a train appears several times:
#   "last"  -> the newest snapshot (closest to the train actually arriving,
#              so its "Late" value is the most accurate). RECOMMENDED.
#   "first" -> the oldest snapshot.
# Change this one word to switch.
KEEP = "last"


def main():
    day = day_from_args()
    raw_path = RAW / "trains" / f"trains_{day}.csv"

    if not raw_path.exists():
        print(f"No raw train file for {day}, nothing to clean.")
        return

    # dtype=str: read everything as text so no value is altered
    raw = pd.read_csv(raw_path, dtype=str, keep_default_na=False)

    # Oldest -> newest, so keep="last" really means the newest snapshot.
    # (The time text is in a fixed format, so sorting it as text is safe.)
    raw = raw.sort_values("CollectedAtUTC", kind="stable")

    clean = raw.drop_duplicates(subset=KEY, keep=KEEP)

    out_path = CLEAN / f"trains_clean_{day}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    clean.to_csv(out_path, index=False)

    print(f"{day}: raw rows {len(raw)} -> clean rows {len(clean)} "
          f"({len(raw) - len(clean)} duplicates removed, keeping the {KEEP} snapshot)")


if __name__ == "__main__":
    main()
