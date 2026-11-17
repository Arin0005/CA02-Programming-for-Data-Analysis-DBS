# RailPredict – Weather-Based Train Delay Analysis

An MSc AI data collection project combining Irish Rail live station-board data with Open-Meteo and Met Éireann weather observations.

## What runs automatically

- **Data collection:** hourly at **05:07–23:07 Europe/Dublin**, 19 scheduled starts per day. GitHub Actions runs on GitHub's servers; a personal laptop does not need to be on.
- **Daily processing:** **01:30 Europe/Dublin** (next day), cleaning and merging the previous UTC day's data and saving a summary report.
- All records are stored with UTC timestamps. GitHub may delay scheduled workflow starts.

## Files

- `scripts/collect_trains.py`: Irish Rail live station boards.
- `scripts/collect_openmeteo.py`: current weather at station coordinates.
- `scripts/collect_met_eireann.py`: latest Met Éireann observations.
- `scripts/clean_trains.py`: de-duplicate train/station/day records.
- `scripts/merge_data.py`: merge with weather readings.
- `scripts/inspect_data.py`: quality checks and a daily summary.
- `scripts/common.py`: shared code for timestamps, station lists and CSV files.
- `data/met_station_coords.csv`: weather-station coordinate lookup.
- `.github/workflows/`: automated collection and processing.

Raw files, cleaned files, merged files, failure logs and reports are written under `data/` and committed back to the repository.

## Run on a laptop

Install Python 3.12 and run:

```bash
python -m pip install -r requirements.txt
python scripts/collect_trains.py
python scripts/collect_openmeteo.py
python scripts/collect_met_eireann.py
```

To process a particular date (replace the example date with a day you collected):

```bash
python scripts/clean_trains.py 2026-11-16
python scripts/merge_data.py 2026-11-16
python scripts/inspect_data.py 2026-11-16 --save
```

## Notes

- An empty station board does not automatically indicate an API failure.
- Raw data is kept separately from cleaned and merged outputs.
- Weather readings and reported train-board data are observations; they do not establish the cause of a train delay.
- See `CHANGELOG.md` for the changes from the original notebook-based collection.
