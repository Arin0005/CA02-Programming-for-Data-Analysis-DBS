"""
collect_met_eireann.py - cell 3 of your notebook, as a script.

Downloads the Met Eireann latest-observations CSV and appends it to
data/raw/met_eireann/met_eireann_<day>.csv
The values are saved exactly as Met Eireann gives them (text, with "-"
where they have no value). Nothing is converted or filled in.
"""

import io
import sys

import pandas as pd
import requests

from common import RAW, run_day, run_iso, append_to_csv, log_failure

URL = "https://www.met.ie/latest-reports/observations/download"

# NEW: the real column names contain symbols like the degree sign and
# brackets ("Temperature (ºC)"). Those can break when files are appended
# or opened in other programs. This maps each one, by what it STARTS WITH,
# to a plain-text name. Only the NAME changes, never the values.
COLUMN_NAMES = {
    "station": "Station",
    "temperature": "Temperature_C",
    "weather": "Weather",
    "wind speed": "WindSpeed_Kts",
    "wind gust": "WindGust_Kts",
    "wind direction": "WindDirection",
    "humidity": "Humidity_Pct",
    "rainfall": "Rainfall_mm",
    "pressure": "Pressure_hPa",
}


def main():
    try:
        # CHANGED: your code used pd.read_csv(url). That sends no browser-style
        # header and websites often refuse it (especially from cloud servers).
        # requests lets us send a User-Agent, set a timeout, and catch errors.
        response = requests.get(URL, headers={"User-Agent": "Mozilla/5.0 (student-data-project)"},
                                timeout=30)
        response.raise_for_status()
        text = response.content.decode("utf-8-sig", errors="replace")

        # NEW: if the site answers with a web page instead of the CSV,
        # fail clearly rather than saving rubbish.
        if not text.lstrip().lower().startswith("station"):
            raise ValueError("response is not the expected CSV")

        # CHANGED: dtype=str + keep_default_na=False keeps every value exactly as
        # written ("03" stays "03", "-" stays "-"). pandas would otherwise
        # turn blanks and "-" into NaN and strip leading zeros.
        met = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)

        renamed = {}
        for col in met.columns:
            for start, new_name in COLUMN_NAMES.items():
                if col.strip().lower().startswith(start):
                    renamed[col] = new_name
        met = met.rename(columns=renamed)

        unknown = [c for c in met.columns if c not in COLUMN_NAMES.values()]
        if unknown:
            print("WARNING: unexpected Met Eireann columns ignored:", unknown)

        # fixed column order, so every file looks the same
        met = met.reindex(columns=list(COLUMN_NAMES.values()), fill_value="")
        met["CollectedAtUTC"] = run_iso()

        if met.empty:
            raise ValueError("CSV has no rows")

        append_to_csv(met, RAW / "met_eireann" / f"met_eireann_{run_day()}.csv")
        print("Met Eireann rows saved:", len(met))

    except Exception as error:
        log_failure("met_eireann", URL, error)   # CHANGED: logged instead of crashing the run
        sys.exit(1)


if __name__ == "__main__":
    main()
