"""
common.py - small helpers shared by every script.

CHANGED from v1: the folder layout is the same (data/raw, clean, merged,
logs, reports) but everything now lives inside this project folder, and the
helpers are trimmed to what the Dublin version needs.
"""

import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Folders. ROOT is the project folder (the one that contains scripts/ and
# data/), found from this file's position, so the scripts work from anywhere.
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
CLEAN = DATA / "clean"
MERGED = DATA / "merged"
LOGS = DATA / "logs"
REPORTS = DATA / "reports"
DUBLIN_STATIONS_FILE = DATA / "dublin_stations.csv"
MET_COORDS_FILE = DATA / "met_station_coords.csv"
TRAIN_IDS_FILE = DATA / "train_ids.csv"

BOARD_URL = "https://api.irishrail.ie/realtime/realtime.asmx/getStationDataByCodeXML"
MOVEMENTS_URL = "https://api.irishrail.ie/realtime/realtime.asmx/getTrainMovementsXML"

# NEW: scope is Heuston + Connolly only (your decision).
DUBLIN_STATIONS = ["HSTON", "CNLLY"]

# Written out by hand so a computer set to another language cannot change
# "Nov" into something else.
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------
def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    """2026-11-20T14:10:03+00:00. CHANGED: seconds only. In v1 a manual run
    wrote microseconds, which made the time format inconsistent."""
    return dt.replace(microsecond=0).isoformat()


def day_string(dt):
    return dt.strftime("%Y-%m-%d")


def api_date(day):
    """'2026-11-20' -> '20 Nov 2026', the date format Irish Rail uses."""
    d = datetime.strptime(day, "%Y-%m-%d")
    return f"{d.day:02d} {MONTHS[d.month - 1]} {d.year}"


def parse_api_dates(series):
    """Turn '20 Nov 2026' text into real dates (blank/odd values -> NaT)."""
    parts = series.str.strip().str.split(" ", expand=True)
    if parts.shape[1] < 3:
        return pd.to_datetime(pd.Series([None] * len(series), index=series.index))
    month = parts[1].map({m: i + 1 for i, m in enumerate(MONTHS)})
    return pd.to_datetime(
        {"year": pd.to_numeric(parts[2], errors="coerce"),
         "month": month,
         "day": pd.to_numeric(parts[0], errors="coerce")},
        errors="coerce")


def day_from_args(argv, default="yesterday"):
    """
    Day to work on, from the command line:  python scripts/x.py 2026-11-20
    No date -> yesterday (for the daily jobs) or today.
    """
    args = [a for a in argv[1:] if not a.startswith("--")]
    if args:
        datetime.strptime(args[0], "%Y-%m-%d")   # stops with an error if the format is wrong
        return args[0]
    today = now_utc()
    return day_string(today if default == "today" else today - timedelta(days=1))


# ---------------------------------------------------------------------------
# Saving and logging
# ---------------------------------------------------------------------------
def append_to_csv(df, path):
    """
    Add rows to the end of a CSV (creating it, with a header, if new).
    Same idea as v1: the columns are forced to match the file's existing
    header so a changed API can never shift columns out of line.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        header = pd.read_csv(path, nrows=0).columns.tolist()
        extra = [c for c in df.columns if c not in header]
        if extra:
            print(f"WARNING: new columns not in {path.name} were skipped: {extra}")
        df.reindex(columns=header).to_csv(path, mode="a", header=False, index=False)
    else:
        df.to_csv(path, index=False)


def log_failure(source, item, error, when=None):
    """One line per failed call in data/logs/failures_<day>.csv (same as v1)."""
    when = when or now_utc()
    message = str(error).replace("\n", " ").replace("\r", " ")[:300]
    row = pd.DataFrame([{"RunUTC": iso(when), "Source": source,
                         "Item": item, "Error": message}])
    append_to_csv(row, LOGS / f"failures_{day_string(when)}.csv")
    print(f"FAILED [{source}] {item}: {message}")


def read_text_csv(path):
    """Read a CSV with every value as text, so nothing is changed or turned into NaN."""
    return pd.read_csv(path, dtype=str, keep_default_na=False)


# ---------------------------------------------------------------------------
# Reading Irish Rail XML
# ---------------------------------------------------------------------------
def xml_to_rows(content):
    """
    Turn Irish Rail XML into a list of dicts, one per train / stop.
    An empty list means "nothing returned" - for example a station with no
    trains due, or a train that did not run that day. (pd.read_xml raises an
    error in that case, which is the problem found in your notebook cells.)
    Every value is stripped of spaces, so 'A223 ' becomes 'A223'.
    """
    root = ET.fromstring(content)
    rows = []
    for child in root:
        row = {}
        for field in child:
            row[field.tag.split("}")[-1]] = (field.text or "").strip()
        rows.append(row)
    return rows


def fetch_xml(url, params, tries=2, timeout=15):
    """
    Download one Irish Rail XML answer and return its rows.
    NEW: one retry after 2 seconds; a short timeout (15 s) so one slow call
    cannot hold the whole run up.
    """
    for attempt in range(1, tries + 1):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return xml_to_rows(response.content)
        except Exception:
            if attempt == tries:
                raise
            time.sleep(2)
