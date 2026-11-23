"""
collect_movements.py - NEW. Runs once a day. Gets the COMPLETE journey,
with scheduled and ACTUAL times, of every Heuston/Connolly train we know.

This is your notebook cell 2 (getTrainMovementsXML) - but used to collect the
actual times, not to test whether a train is a Dublin train.

How it works
 1. Every train code ever seen on the Heuston/Connolly boards (data/raw/trains)
    is collected into data/train_ids.csv. Because train codes are stable
    (your P222 test), this list only ever grows.
 2. For the chosen day, we ask getTrainMovementsXML for each code.
      * an empty answer = that train does not run that day (e.g. Sundays).
        That is normal, NOT a failure.
 3. Saved to data/raw/movements/movements_<day>.csv

Usage:  python scripts/collect_movements.py 2026-11-20     (default: yesterday)
"""

import sys
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from common import (RAW, TRAIN_IDS_FILE, MOVEMENTS_URL, iso, now_utc,
                    api_date, day_from_args, append_to_csv, log_failure,
                    fetch_xml)


def update_train_id_list():
    """Collect every train code seen on the boards so far into train_ids.csv."""
    files = sorted((RAW / "trains").glob("trains_*.csv"))
    frames = []
    for f in files:
        frames.append(pd.read_csv(f, dtype=str, keep_default_na=False,
                                  usecols=["Traincode", "Origin", "Destination", "Traindate"]))
    if not frames:
        return []
    seen = pd.concat(frames, ignore_index=True)
    ids = (seen.groupby("Traincode")
               .agg(Origin=("Origin", "last"), Destination=("Destination", "last"),
                    TimesSeen=("Traindate", "size"))
               .reset_index())
    ids.to_csv(TRAIN_IDS_FILE, index=False)
    return ids["Traincode"].tolist()


def fetch_one(code, day_text):
    """Ask for one train's journey. Returns (code, rows, error)."""
    try:
        rows = fetch_xml(MOVEMENTS_URL, {"TrainId": code, "TrainDate": day_text})
        time.sleep(0.2)                       # small pause so we stay polite to the API
        return code, rows, None
    except Exception as error:
        return code, [], error


def main():
    day = day_from_args(sys.argv, default="yesterday")
    day_text = api_date(day)
    ids = update_train_id_list()
    print(f"{day}: asking for {len(ids)} known train codes")
    if not ids:
        print("No train codes yet - run the board collector first.")
        return

    collected_at = iso(now_utc())
    all_rows, no_service, failed = [], 0, 0

    # 4 calls at the same time keeps this to a minute or two instead of ten.
    with ThreadPoolExecutor(max_workers=4) as pool:
        for code, rows, error in pool.map(lambda c: fetch_one(c, day_text), ids):
            if error is not None:
                failed += 1
                log_failure("movements", f"{code} {day_text}", error)
                continue
            rows = [r for r in rows if r.get("LocationCode")]
            if not rows:
                no_service += 1               # did not run that day - normal
                continue
            for r in rows:
                r["CollectedAtUTC"] = collected_at
            all_rows.extend(rows)

    trains_found = len({(r["TrainCode"]) for r in all_rows})
    print(f"Trains with a journey: {trains_found} | no service that day: {no_service} "
          f"| failed calls: {failed} | stop rows: {len(all_rows)}")

    if all_rows:
        append_to_csv(pd.DataFrame(all_rows), RAW / "movements" / f"movements_{day}.csv")
    if failed == len(ids):
        sys.exit(1)


if __name__ == "__main__":
    main()
