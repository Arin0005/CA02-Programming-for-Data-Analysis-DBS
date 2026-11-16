"""
collect_trains.py - cell 1 of your notebook, as a script.

Asks the Irish Rail API for the live board of every Republic of Ireland
station and appends the rows to data/raw/trains/trains_<day>.csv
"""

import sys
import time

import requests

from common import (RAW, run_day, run_iso, append_to_csv, log_failure,
                    get_roi_stations, xml_to_rows)

BOARD_URL = "https://api.irishrail.ie/realtime/realtime.asmx/getStationDataByCodeXML"


def main():
    stations = get_roi_stations()
    codes = stations["StationCode"].dropna().unique()
    print("Stations selected:", len(codes))

    collected_at = run_iso()   # CHANGED: one time for the whole run (was one per station)
    all_rows = []
    empty_boards = 0
    failed = 0

    for code in codes:
        rows = None

        # NEW: try each station twice. A single timeout should not lose an
        # hour of data for that station.
        for attempt in (1, 2):
            try:
                response = requests.get(BOARD_URL, params={"StationCode": code}, timeout=15)
                response.raise_for_status()
                rows = xml_to_rows(response.content)

                # NEW: a real train always has a Traincode. This ignores any
                # placeholder row the API might send for a quiet station.
                rows = [r for r in rows if r.get("Traincode")]
                break
            except Exception as error:
                if attempt == 2:
                    failed += 1
                    log_failure("irish_rail_board", code, error)   # CHANGED: real error is saved
                else:
                    time.sleep(2)

        if rows is not None:
            if not rows:
                # CHANGED: no trains due is NORMAL (e.g. at night). It is counted,
                # not logged as a failure.
                empty_boards += 1
            else:
                for r in rows:
                    r["CollectedAtUTC"] = collected_at
                all_rows.extend(rows)

        time.sleep(0.5)   # same polite pause as your original

    print(f"Train rows: {len(all_rows)} | empty boards: {empty_boards} | failed calls: {failed}")

    if all_rows:
        import pandas as pd
        append_to_csv(pd.DataFrame(all_rows), RAW / "trains" / f"trains_{run_day()}.csv")
        print("Data saved!")
    else:
        print("No train data collected.")

    # NEW: if EVERY call failed (e.g. the API blocks GitHub), make the run
    # show as failed (red) in GitHub so you notice. Quiet boards alone never do this.
    if failed == len(codes):
        sys.exit(1)


if __name__ == "__main__":
    main()
