# CHANGELOG – Irish Rail delays + weather dataset

This file records every change made to your original three Colab cells, the logic behind each change, and how the whole system works. New entries go at the **top** of the "Change history" section.

---

## 1. How the system works (plain language)

1. **Every hour** (minute 7, UTC) GitHub starts a small Linux computer in the cloud. Your laptop is not involved.
2. That computer runs three collection scripts, one per source. Each one **adds rows to that day's CSV file**.
3. It then **commits** the new rows to your repo, so the data is stored in GitHub.
4. **Once a day at 00:30 UTC** a second workflow takes yesterday's data and:
   - removes duplicate trains (clean),
   - joins trains with weather (merge),
   - writes a check report (inspect).
5. Raw files are **never edited** after they are written.

```
Irish Rail API ──► collect_trains.py ──────► data/raw/trains/trains_DAY.csv ──► clean_trains.py ──► data/clean/trains_clean_DAY.csv ─┐
Open-Meteo API ──► collect_openmeteo.py ───► data/raw/openmeteo/openmeteo_DAY.csv ───────────────────────────────────────────────────┼─► merge_data.py ──► data/merged/merged_DAY.csv
Met Éireann CSV ─► collect_met_eireann.py ─► data/raw/met_eireann/met_eireann_DAY.csv ──────────────────────────────────────────────────┘
                   (any failure)  ───────► data/logs/failures_DAY.csv
                                                                              inspect_data.py ──► data/reports/summary_DAY.txt
```

DAY is the **UTC date** (e.g. `2026-11-15`).

---

## 2. Files and what each one does

| File | Purpose |
|---|---|
| `.github/workflows/collect.yml` | Hourly schedule: runs the 3 collection scripts and commits the data |
| `.github/workflows/end_of_day.yml` | Daily schedule: clean → merge → report → commit |
| `scripts/common.py` | Shared helpers (folders, run time, saving, failure log, station list) |
| `scripts/collect_trains.py` | Your cell 1 as a script |
| `scripts/collect_openmeteo.py` | Your cell 2 as a script |
| `scripts/collect_met_eireann.py` | Your cell 3 as a script |
| `scripts/clean_trains.py` | Removes duplicate trains (raw kept) |
| `scripts/merge_data.py` | Joins trains with Open-Meteo and Met Éireann |
| `scripts/inspect_data.py` | Read-only check of a day's data (you run it yourself) |
| `data/met_station_coords.csv` | Coordinates of the 25 Met Éireann stations (used only to find the nearest one) |
| `requirements.txt` | The two Python packages needed: pandas and requests |
| `CHANGELOG.md` | This file |

Created automatically by the scripts: `data/stations_roi.csv`, `data/raw/...`, `data/clean/...`, `data/merged/...`, `data/logs/...`, `data/reports/...`.

---

## 3. What was wrong in your original code, and what changed

### Cell 1 – trains
| Original | Problem | Change |
|---|---|---|
| `pd.read_xml(...)` on each station board | An empty board has no XML rows, which makes `read_xml` raise an error. The `except` then printed "Could not collect", so a quiet station looked broken. | XML is read by hand (`xml_to_rows` in `common.py`). No rows = empty board = counted, **not** a failure. A row only counts as a train if it has a `Traincode`. |
| `except Exception: print("Could not collect:", code)` | The real error was thrown away and nothing was saved. | Source, station and the actual error go to `data/logs/failures_DAY.csv`. |
| `datetime.now()` inside the loop | Every station got a slightly different time. | One shared time per run (`RUN_UTC`), set by the workflow. |
| One attempt per station | One timeout lost that station for the hour. | One retry after 2 seconds. |
| Saved to one overwritten file | No history. | Appends to one file per day. |
| Hand-typed Northern Ireland name list | May miss a station. | **Left exactly as you wrote it.** Check `data/stations_roi.csv` after the first run. |
| `display(...)` | Only works in Colab. | Removed; progress is printed instead. |
| – | If the API blocked GitHub, the run would look fine. | If **every** call fails, the script exits with an error so the run shows red in GitHub. |

### Cell 2 – Open-Meteo
| Original | Change |
|---|---|
| Batches of 10 stations, results matched by order | **Kept.** Added a check that the number of results equals the number of stations; otherwise the batch is logged as failed (matching by order would be wrong otherwise). |
| Removed stations with missing coordinates | Also removes stations at 0, 0 (no real position). |
| `files.download` / `display` (Colab only) | Removed. Saves to `data/raw/openmeteo/openmeteo_DAY.csv`. |
| `print("Failed:", ...)` | Logged to the failures file. One retry added. |

### Cell 3 – Met Éireann
| Original | Change |
|---|---|
| `pd.read_csv(url)` | Replaced with `requests` plus a User-Agent header, a timeout, and a check that the answer really is the CSV (not a block page). A failure is logged. |
| pandas default reading | Values are read **as text** (`dtype=str`, `keep_default_na=False`) so `03` stays `03` and `-` stays `-`. Nothing is converted or filled in. |
| Original column names such as `Temperature (ºC)` | Renamed to plain names (the **values** are unchanged): `Station, Temperature_C, Weather, WindSpeed_Kts, WindGust_Kts, WindDirection, Humidity_Pct, Rainfall_mm, Pressure_hPa`. Columns are always saved in this order. |
| – | The file has no observation time, so each row is stamped with `CollectedAtUTC` (the time we downloaded it). |

---

## 4. Decisions you made, and how they were applied

| Your decision | Applied as |
|---|---|
| Add a Met Éireann coordinates file, but do not add it to the merged data | `data/met_station_coords.csv` is read only to find the nearest station. Latitude, longitude and distance are **not** in the merged file. |
| Join on station + hour | The hour comes from `CollectedAtUTC` (e.g. `2026-11-15T21`). The hour is a temporary helper column, removed before saving. |
| Keep raw data | `clean_trains.py` only reads the raw file. |
| Inspect script | `inspect_data.py`, see section 6. |
| Markdown change log | This file. |

### Duplicate rule (question 2 – default applied, one word to change)
One row per **Traincode + Traindate + Stationcode**. The default keeps the **last** snapshot, because the closest snapshot to arrival has the most accurate `Late` value. To keep the first instead, change `KEEP = "last"` to `KEEP = "first"` in `scripts/clean_trains.py`.

### Merge details
* All train columns are kept as they are.
* Open-Meteo columns get an `OM_` prefix and Met Éireann columns a `Met_` prefix. This is **only** so you can tell the sources apart; the data is unchanged. `Met_Station` shows which Met station each row was matched to.
* Left join: no train row is ever removed because weather is missing.
* Nearest Met station = straight-line (haversine) distance from the train station's coordinates, over all 25 stations in the coordinates file.
* If two weather readings fall in the same hour (for example a manual test run), the newest is used so train rows are not duplicated.

---

## 5. Things you must know / check

1. **Not tested against the live APIs.** The tools I used could not reach Irish Rail, Open-Meteo or met.ie. I tested all logic with realistic fake responses (normal boards, an empty board, a failing station, a blocked Met page, an all-403 case). The first real test is clicking **Run workflow** on GitHub (section 7). Irish Rail or met.ie may refuse GitHub's cloud servers; if so the failure log and the red run will say so.
2. **Repo must be public (or watch your minutes).** One hourly run takes roughly 3 to 5 minutes (about 160 stations, 0.5 s pause each). That is 24 runs a day, 35 days, roughly 3,500+ minutes, which is **more than the 2,000 free minutes a month for private repos**. Public repos have unlimited minutes. If you need it private, tell me and I will reduce the frequency or speed it up.
3. **GitHub scheduled runs can start 5 to 20 minutes late**, and occasionally an hour is skipped. That is normal.
4. **Moore Park coordinates are approximate.** I found no published source. Please check them (marked in the Note column). Mace Head uses a corrected point from a forum comment. All other coordinates come from a community-compiled table of the stations (measured from aerial images), not an official Met Éireann list. The error is small for a nearest-station join but should be mentioned in your report.
5. **Met Éireann names are matched to stations by name.** `Cork`, `Dublin` and `Shannon` are the airport stations; `Newport Mayo` is Newport; `Mt Dillon` is Mount Dillon.
6. **Time zones:** Irish Rail times are Irish local time; Open-Meteo is UTC. They are identical until the clocks change on 28 March 2027, so there is no mismatch during your collection.
7. **Midnight edge case:** duplicates are removed within each day's file. A train seen just before and just after midnight UTC can appear once in each day's clean file. Remove that when combining all days: keep the last row per `Traincode, Traindate, Stationcode`.
8. **Open-Meteo is free for non-commercial use** with a daily limit (about 10,000 location-calls); this project uses about 4,000 a day.
9. **Station list** comes from the API every run; if the download fails the last saved copy is used.

---

## 6. How to inspect the data

**On your computer (Colab or local):**
```
git clone https://github.com/YOUR-USERNAME/YOUR-REPO.git
cd YOUR-REPO
pip install -r requirements.txt
python scripts/inspect_data.py 2026-11-15
```
In Colab, put `!` in front of each line and use `%cd YOUR-REPO` instead of `cd`. Run `git pull` any time to get newer data.

It prints, per source: row counts, number of hourly runs, missing values (blank or `-`), duplicates in raw trains, stations with no trains all day, failed calls grouped by error, and sample merged rows. Add `--save` to also write `data/reports/summary_DAY.txt`.

You can also open any CSV straight on GitHub or in Excel. To change something (for example the nearest-station list), edit the CSV or script, then re-run `clean_trains.py` and `merge_data.py` for that day.

---

## 7. Setup steps (first time)

1. Create the repo as **Public** (Settings later if needed) and add all files above, keeping the same folder names. The two workflow files must be exactly at `.github/workflows/collect.yml` and `.github/workflows/end_of_day.yml`.
2. In the repo: **Settings → Actions → General → Workflow permissions →** choose **Read and write permissions** → Save.
3. Go to the **Actions** tab, choose **Collect data**, click **Run workflow**.
4. When it finishes, check `data/` in the repo and the run log. Confirm train rows, weather rows, Met rows, and look at `data/stations_roi.csv` to confirm no Northern Ireland stations are in it.
5. Optionally run **End of day processing** by hand once to test the clean/merge/report steps.
6. Leave it alone. Check the Actions tab once a day for red runs.

---

## 8. Change history

### 2026-11-15 – Version 1 (first build)
* Converted the three notebook cells into scripts that append to daily CSVs.
* Added failure logging, retries, and correct handling of empty station boards.
* Added GitHub Actions workflows for hourly collection and end-of-day processing.
* Added duplicate removal (keep last snapshot), merging with Open-Meteo (station + hour) and Met Éireann (nearest station + hour), and the inspection script.
* Added `met_station_coords.csv` for the nearest-station join only.
