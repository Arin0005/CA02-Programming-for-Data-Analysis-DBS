"""
collect_boards.py - one poll of the Heuston and Connolly station boards.

This is your notebook cell 3 (the live station board for HSTON) turned into a
script and used for both stations.

Each board lists the trains due in roughly the next 90 minutes, including
Irish Rail's CURRENT PREDICTION (Exparrival / Expdepart / Late). We keep
every snapshot - the history of how a prediction changes is the data you
want for judging how accurate the predictions are.

Only trains that START (Locationtype O) or END (Locationtype D) at the
station are kept. Trains that just pass through (Locationtype S, e.g. DARTs
at Connolly) are skipped. That is your rule: "every service starting and
ending at Heuston and Connolly".

Saved to: data/raw/trains/trains_<day>.csv   (one file per UTC day, appended)
"""

import sys

import pandas as pd

from common import (DUBLIN_STATIONS, BOARD_URL, RAW, now_utc, iso, day_string,
                    append_to_csv, log_failure, fetch_xml)


def collect_once(when=None):
    """Do one poll. Returns (rows_saved, stations_failed)."""
    when = when or now_utc()
    collected_at = iso(when)       # ONE time stamp for the whole poll
    rows = []
    failed = 0

    for code in DUBLIN_STATIONS:
        try:
            board = fetch_xml(BOARD_URL, {"StationCode": code})
        except Exception as error:
            failed += 1
            log_failure("board", code, error, when)
            continue

        # An empty board (no trains due) simply gives an empty list.
        # It is NOT a failure and nothing is logged.
        for row in board:
            if not row.get("Traincode"):
                continue
            if row.get("Locationtype") not in ("O", "D"):
                continue                      # passing through - not in scope
            row["CollectedAtUTC"] = collected_at
            rows.append(row)

    if rows:
        append_to_csv(pd.DataFrame(rows),
                      RAW / "trains" / f"trains_{day_string(when)}.csv")
    return len(rows), failed


def main():
    saved, failed = collect_once()
    print(f"Rows saved: {saved} | stations failed: {failed}")
    # If BOTH boards failed, make the run show as failed so you notice.
    if failed == len(DUBLIN_STATIONS):
        sys.exit(1)


if __name__ == "__main__":
    main()
