"""
common.py - small helpers that every other script uses.

WHY THIS FILE EXISTS (NEW - your Colab cells had no shared code):
Your three cells each repeated the same things (station list, timestamps,
saving). Putting them in one place means each script stays short and they
all behave the same way.
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Folder layout. ROOT is the top folder of the repo, found from this file's
# location, so scripts work no matter which folder you run them from.
# NEW: your cells saved files next to the notebook; now everything is sorted
# into folders so 5 weeks of files do not become a mess.
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"            # untouched collected data (never edited)
CLEAN = DATA / "clean"        # de-duplicated train data
MERGED = DATA / "merged"      # trains + weather
LOGS = DATA / "logs"          # failed calls
REPORTS = DATA / "reports"    # end-of-day summaries
STATIONS_FILE = DATA / "stations_roi.csv"
MET_COORDS_FILE = DATA / "met_station_coords.csv"

# Same Northern Ireland list as your cell 1 (unchanged on purpose - see CHANGELOG)
NI_STATIONS = [
    "Belfast", "Newry", "Portadown", "Lisburn",
    "Lurgan", "Scarva", "Poyntzpass", "Moira",
]

STATIONS_URL = "https://api.irishrail.ie/realtime/realtime.asmx/getAllStationsXML"


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------
def run_time():
    """
    The time stamp for this whole run.

    NEW: in your cells every station got its own slightly different
    datetime.now(). Now the GitHub workflow sets ONE time (RUN_UTC) at the
    start and all three scripts use it, so all data from one run carries
    the same time. That makes joining trains to weather reliable.
    If RUN_UTC is not set (e.g. you run a script by hand) it uses "now".
    """
    env_value = os.environ.get("RUN_UTC")
    if env_value:
        return datetime.fromisoformat(env_value)
    return datetime.now(timezone.utc)


def run_iso():
    return run_time().isoformat()          # e.g. 2026-11-15T21:07:03+00:00


def run_day():
    return run_time().strftime("%Y-%m-%d")  # used in daily file names (UTC date)


def day_from_args():
    """
    Day to work on for the clean / merge / inspect scripts.
    Usage:  python scripts/clean_trains.py 2026-11-15
    No date given -> today's UTC date.
    """
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        datetime.strptime(args[0], "%Y-%m-%d")  # stops with an error if the format is wrong
        return args[0]
    return run_day()


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------
def append_to_csv(df, path):
    """
    Add rows to the end of a CSV (create it with a header if it is new).

    NEW: your cells overwrote or created a new file each time. This keeps
    ONE file per day and adds to it.
    The columns are forced to match the file's existing header, so if a
    source ever adds or reorders a column the file does not get misaligned.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        header = pd.read_csv(path, nrows=0).columns.tolist()
        extra = [c for c in df.columns if c not in header]
        if extra:
            # Printed (shows in the GitHub Actions log). Not logged to the
            # failures file to avoid a loop.
            print(f"WARNING: new columns not in {path.name} were skipped: {extra}")
        df = df.reindex(columns=header)
        df.to_csv(path, mode="a", header=False, index=False)
    else:
        df.to_csv(path, index=False)


def log_failure(source, item, error):
    """
    Write one line to data/logs/failures_<day>.csv.

    NEW: your cells did print("Could not collect:", code) and threw the
    real error away. Now the source, the station and the actual error
    message are saved, so after 5 weeks you can see what failed and why.
    """
    message = str(error).replace("\n", " ").replace("\r", " ")[:300]
    row = pd.DataFrame([{
        "RunUTC": run_iso(),
        "Source": source,
        "Item": item,
        "Error": message,
    }])
    append_to_csv(row, LOGS / f"failures_{run_day()}.csv")
    print(f"FAILED [{source}] {item}: {message}")


# ---------------------------------------------------------------------------
# Reading Irish Rail XML
# ---------------------------------------------------------------------------
def xml_to_rows(content):
    """
    Turn Irish Rail XML into a list of dicts (one per child element).

    CHANGED: your cell used pd.read_xml(), which raises an error when the
    XML has no rows. That is exactly what an EMPTY station board looks like,
    so empty boards were being counted as failures. Reading the XML by hand
    returns an empty list instead, which we can treat as "no trains due".
    """
    root = ET.fromstring(content)
    rows = []
    for child in root:
        row = {}
        for field in child:
            tag = field.tag.split("}")[-1]   # drop the XML namespace prefix
            row[tag] = (field.text or "").strip()
        rows.append(row)
    return rows


def get_roi_stations():
    """
    Download the station list and remove Northern Ireland stations.
    Same idea as your cell 1, with two additions:
      * the list is saved to data/stations_roi.csv (the merge script needs
        station coordinates later)
      * if the download fails, the last saved copy is used instead of the
        whole run stopping
    """
    try:
        response = requests.get(STATIONS_URL, timeout=30)
        response.raise_for_status()
        stations = pd.DataFrame(xml_to_rows(response.content))

        # Same filter as your original code
        stations = stations[
            ~stations["StationDesc"].str.contains(
                "|".join(NI_STATIONS), case=False, na=False
            )
        ].drop_duplicates(subset="StationCode").reset_index(drop=True)

        STATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        stations.to_csv(STATIONS_FILE, index=False)
        return stations

    except Exception as error:
        log_failure("stations", "getAllStationsXML", error)
        if STATIONS_FILE.exists():
            print("Using the last saved station list.")
            return pd.read_csv(STATIONS_FILE, dtype=str)
        raise
