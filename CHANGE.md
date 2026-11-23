# CHANGE.md – RailPredict Dublin (v2)

Everything that changed compared with your v1 repo and your notebook cells, the reason for each change, and how the new system works. New entries go at the **top** of section 11.

---

## 1. What v2 does (plain language)

**Goal:** record every train that starts or ends at **Dublin Heuston or Dublin Connolly**, keep Irish Rail's live *prediction* for each one as it changes, then fetch the *actual* arrival/departure times afterwards, so you can measure how accurate the predictions are and whether weather helps.

1. **Every 10 minutes** one job reads the Heuston and Connolly boards. Each board lists trains due in roughly the next 90 minutes with Irish Rail's current prediction (`Exparrival`, `Expdepart`, `Late`). We keep trains that **start (O) or end (D)** at the station and skip trains that just pass through (S). **Every snapshot is kept**, because the way a prediction changes is your data.
2. **Once a day (03:30 UTC)**, for yesterday:
   - `getTrainMovementsXML` is called for every train code ever seen on the boards. It returns the whole journey with **scheduled and actual times**.
   - Hourly weather is collected (Open-Meteo model + Met Éireann measured).
   - Genuine repeats are removed, everything is joined, and a check report is written.
3. Raw files are **never edited**.

```
Heuston + Connolly boards ──► collect_boards.py (every 10 min) ──► data/raw/trains/trains_DAY.csv ─┐
        │                                                                                          │
        └─ train codes seen ──► data/train_ids.csv                                                 │
                                       │                                                           ▼
                          collect_movements.py (daily) ──► data/raw/movements/movements_DAY.csv ──► clean_data.py ──► data/clean/
Open-Meteo  ┐                                                                                       │
Met Éireann ┴─ collect_weather.py (daily) ──► data/raw/openmeteo/ , data/raw/met_eireann/ ──────────┤
                                                                                                    ▼
                                                              merge_data.py ──► data/merged/merged_DAY.csv
                                                              inspect_data.py ──► data/reports/summary_DAY.txt
                          any failed call ──► data/logs/failures_DAY.csv
```
DAY is the **UTC date** (e.g. `2026-11-20`).

---

## 2. How it runs on GitHub (and why it is different from v1)

**v1 problem:** a cron timer asked GitHub to start a short job every hour. GitHub dropped most of them (12 runs in 5 days instead of about 110).

**v2:** `railpredict_collect.yml` starts **one job that stays alive** for up to 5 h 40 min and does the waiting itself (`poll_loop.py`):
- polls every 10 minutes on a fixed grid (a slow poll does not make later polls drift),
- saves to GitHub every 30 minutes,
- near GitHub's 6-hour limit it **starts the next run itself** (`gh workflow run`),
- the service window is **04:45 – 00:45 UTC**; outside it nothing runs,
- the cron lines in the workflow are only a **safety net**: if the chain ever breaks, the next cron restarts it. If a loop is already running, the new run waits in the queue instead of running twice.

`railpredict_daily.yml` is a separate workflow with its own queue, so a long loop never blocks it.

Needs a **public repo** (free unlimited minutes). A private repo has 2,000 free minutes a month and this uses about 19 hours a day.

---

## 3. Files

| File | Where | Purpose |
|---|---|---|
| `railpredict_collect.yml` | `.github/workflows/` (repo root) | the 10-minute loop + self-restart |
| `railpredict_daily.yml` | `.github/workflows/` (repo root) | daily actuals, weather, clean, merge, report |
| `scripts/common.py` | project folder | shared helpers (folders, times, saving, failure log, XML reading) |
| `scripts/collect_boards.py` | | one poll of the two boards |
| `scripts/poll_loop.py` | | the 10-minute loop, saving, hand-over |
| `scripts/collect_movements.py` | | actual times for every known train code |
| `scripts/collect_weather.py` | | daily Open-Meteo + Met Éireann |
| `scripts/clean_data.py` | | removes genuine repeats only |
| `scripts/merge_data.py` | | joins boards + actuals + weather |
| `scripts/inspect_data.py` | | read-only check; run it yourself |
| `data/dublin_stations.csv` | | Heuston and Connolly coordinates (for Open-Meteo and the nearest-station search) |
| `data/met_station_coords.csv` | | coordinates of the 2 Met stations we collect (used only to find the nearest; **not** copied into the merged file) |
| `requirements.txt` | | pandas, requests |
| `CHANGE.md` | | this file |

Created automatically: `data/train_ids.csv`, `data/raw/...`, `data/clean/...`, `data/merged/...`, `data/logs/...`, `data/reports/...`. The folder structure matches v1 (`raw`, `clean`, `merged`, `logs`, `reports`); `raw/movements` is new.

The project folder name is `railpredict_dublin`. If you use another name, change it in the 3 places marked `FOLDER` in the workflow files.

---

## 4. Issues found in the v1 repo

These are issues I found by reading your repo and 12 collection runs. They **may or may not** be the cause of the problems you listed.

| # | Issue | Evidence | Your problem | Status in v2 |
|---|---|---|---|---|
| 1 | Station boards only show trains due soon, so a train is seen once or twice and then disappears. | 1,083 of 1,110 train-days seen in only one run. | 3, 4, 5, 9 | Boards kept only for Heuston/Connolly predictions; **actuals come from `getTrainMovementsXML`**. |
| 2 | Every "No Information" row has `Late = 0`. That is a placeholder, not "on time". v1's cleaning copied `Late` into `DelayMinutes`, so 65% of rows wrongly look on time. | 5,832 of 9,010 rows. | 7, 8, 11 | Raw values are kept as given. v2 never uses `Late` for accuracy; it uses actual times. `inspect_data.py` prints a reminder. |
| 3 | GitHub dropped most scheduled runs. | 12 runs vs roughly 110 scheduled. | 3 | Self-restarting loop (section 2). |
| 4 | **My** retry design: 2 attempts × 30 s timeout per Open-Meteo batch. 8 failed batches on 21 Nov ≈ 8 minutes of waiting, on top of ~9 minutes for the train calls, close to your 15-minute limit. | `failures_2026-11-21.csv`, `Servertime` spread | 2 | 15 s timeouts with one retry for Irish Rail; weather moved out of the 10-minute job into one daily request. |
| 5 | v1 merge joined on the exact `CollectedAtUTC`. The 18 Nov file came from a manual run where each script stamped a different time, so it has 0 weather matches in 977 rows. | `merged_2026-11-18.csv` | 10 | Weather is joined on the **hour of the train's due time**. |
| 6 | `git pull --rebase -X ours \|\| true`: in a rebase, "ours" is the remote side, so on a clash your new rows are dropped silently, and `\|\| true` hides the failure. Unlikely today, but you would never notice. | `collect.yml` | 3 | Pull/push is retried and failure is not hidden. |
| 7 | A manual test run is mixed into the raw data with a different time format (microseconds). | 18 Nov | 10 | Times are written to the second. **If you test locally, delete the `data/` files it creates before you push.** |
| 8 | Open-Meteo returned 429 only on 16 Nov (15 of 17 batches); afterwards the failures were timeouts. | `failures_2026-11-16.csv` | 1 | One request per day, two locations. |
| 9 | README says collection runs at :07 but the cron is :23. | `README.md` | – | Update the README for v2. |

---

## 5. What I changed from your notebook code

| Your cell | What I did | Why |
|---|---|---|
| **Cell 1** `getCurrentTrainsXML` | **Not used.** | The Heuston/Connolly boards already tell us which trains start or end there (`Locationtype` O/D, confirmed in your v1 data; Heuston only has O and D). That removes the need to call movements for every running train just to test whether it touches Dublin. **This is the biggest change from your plan – tell me if you want `getCurrentTrainsXML` back.** |
| **Cell 2** Dublin check with `getTrainMovementsXML` (first 5 trains, name list) | Replaced by `collect_movements.py`: asks for the full journey of **every known Dublin train code** once a day. | Your 2023 test showed old journeys are still available, so we do not need to watch trains finish. Empty answer = no service that day (normal, not a failure). The `range(min(5, …))` test limit is gone. |
| **Cell 3** station board for `HSTON` | Became `collect_boards.py`, for `HSTON` and `CNLLY`, keeping every column the API returns plus `CollectedAtUTC`. | This is where the live prediction comes from. `getTrainMovementsXML` has no expected-time fields. |
| `pd.read_xml(...)` everywhere | Replaced by `xml_to_rows()` in `common.py`. | `read_xml` raises an error when the list is empty (tested). It also turns an all-empty column into NaN numbers. Reading by hand returns an empty list and keeps every value as text. |
| `trains["TrainCode"].str.strip()` | Every value is stripped when the XML is read. | Same goal, applied to all columns. |
| `requests.get(..., timeout=30)` | 15 s timeout, one retry after 2 s. | One slow call must not hold up a poll. |
| Exact-name Dublin list | Not needed. | We use the station codes `HSTON`, `CNLLY`. |

---

## 6. Your problems 1–12 and what v2 does

| Problem | v2 |
|---|---|
| 1 Open-Meteo limit | One request a day for 2 locations. Met Éireann added as a measured source. |
| 2 Workflow too slow | 2 board calls per poll (seconds). Movements: ~hundreds of short calls, 4 at once, once a day. |
| 3 Not consistent | Self-restarting loop; every poll stamped with its real time; `inspect_data.py` lists gaps over 15 minutes. |
| 4 Trains disappearing | Journey fetched from `getTrainMovementsXML` by train code and date. |
| 5 Short trips missed | Polling every 10 minutes; actuals fetched afterwards, so a short journey is still complete. |
| 6 Repeated records | A service is `Traincode + Traindate`; each snapshot and each stop is its own row. |
| 7 `Duein` unreliable | `Exparrival`/`Expdepart` history is kept for every snapshot; compare against actuals (needs checking on real data). |
| 8 Missing actuals | `Mov_Arrival`, `Mov_Departure`, plus the `AutoArrival`/`AutoDepart` flags. |
| 9 Small stations | Scope reduced to Dublin. |
| 10 Weather matching | Joined on the hour the train was **due** (`WEATHER_JOIN_ON = "event"` in `merge_data.py`; change to `"collected"` for the snapshot hour). |
| 11 Prediction history | `clean_data.py` removes only repeats from the *same* poll. |
| 12 Incomplete data off the main network | Out of scope for now. Use `Mov_AutoArrival` to flag times that were not really measured. Your notes on priority/signalling remain hypotheses. |

---

## 7. Decisions you made and how they were applied

| Decision | Applied as |
|---|---|
| Record every service that starts or ends at Heuston or Connolly | Boards filtered to `Locationtype` O or D at `HSTON` / `CNLLY`. Trains passing through (e.g. DARTs at Connolly) are skipped. |
| Poll every 10 minutes | `POLL_EVERY_MIN = 10` in `poll_loop.py`. |
| Boards for Heuston and Connolly only | `DUBLIN_STATIONS` in `common.py`. |
| New folder, same structure | `railpredict_dublin/` with `data/raw`, `clean`, `merged`, `logs`, `reports`. Workflows must still live in `.github/workflows/` at the repo root. |
| Self-restarting loop with cron backup | `railpredict_collect.yml` + `poll_loop.py`. |
| Weather: Met Éireann only covers places with stations; look for alternatives | **Met Éireann** (measured): Phoenix Park and Dublin Airport. **Open-Meteo** (model estimate at the exact station coordinates). Each station is matched to the nearest Met station (Phoenix Park for both, since both are closer to it than to the airport). **MET Norway** (api.met.no) is free with no key but needs an identifying User-Agent, caps at 20 requests/s and requires caching; it is forecast-only, so it cannot give yesterday's weather, and I have **not** built it. It is the fallback if Open-Meteo ever blocks you. |
| Do not push or touch the repo | Nothing was pushed. |

---

## 8. Things I could not verify – check these first

1. **Live APIs:** my tools cannot reach Irish Rail, Open-Meteo or Met Éireann. I tested all logic with realistic fake responses (normal and empty boards, a failing call, a train that does not run, a train that ends after midnight, repeated rows, API down, missing sources) and on pandas 2.2.3 and 3.x. Field names for the **boards** come from your real v1 data. Field names for **movements** come from Irish Rail's documentation.
2. **Met Éireann JSON keys:** the documentation lists a date and a time of observation but not the exact key names. I guessed `date` and `reportTime`. If the first real file differs, `merge_data.py` prints the real column names and skips the Met join (it does not crash); set `MET_DATE_COL` / `MET_TIME_COL` at the top.
3. **Blank actuals:** I assume a not-yet-happened actual time is blank or `00:00`. `inspect_data.py` treats both as "missing", so a genuine 00:00 arrival is ignored in its accuracy summary (the merged file keeps it).
4. **Yesterday's movements:** you tested 2023; I assume yesterday's journey has its actual times by 03:30 UTC.
5. **Your 70% coverage estimate** is not measured.
6. **Open-Meteo** values are a model, not a sensor. The free API is for non-commercial use and requires attribution, so mention it in your report.
7. **GitHub's terms:** I have not checked how they treat a job that runs about 19 hours a day. The window is limited to service hours for that reason.
8. **Time zones:** Irish time equals UTC until 28 March 2027, so there is no mismatch while you collect.
9. **Limits to know about:**
   - A train due just after midnight is joined with the next day's weather. The daily job therefore merges the **day before again** to fill that in.
   - The boards show roughly 90 minutes ahead, so predictions are only seen within that window.
   - A cancelled train's behaviour is unknown.
   - About 40 commits a day will be added to the repo (`COMMIT_EVERY_POLLS` in `poll_loop.py` changes this).

---

## 9. First-time setup and checks

1. Create the folder `railpredict_dublin` at the top of the repo and add the files exactly as listed in section 3. Add `__pycache__/` to `.gitignore`.
2. Create `.github/workflows/railpredict_collect.yml` and `.github/workflows/railpredict_daily.yml` **at the repo root**.
3. **Disable the v1 workflows** (Actions tab → "Collect data" → ⋯ → Disable workflow; the same for "End of day processing"), otherwise v1 keeps calling the APIs every hour.
4. On your own computer: `cd railpredict_dublin`, `pip install -r requirements.txt`, `python scripts/collect_boards.py`. Expect `Rows saved: N`. Then **delete `data/raw` and `data/logs`** that it created, so test rows do not go to GitHub.
5. Two quick checks in Colab (they confirm the two things I could not):
   ```python
   import requests, pandas as pd
   r = requests.get("https://prodapi.met.ie/observations/phoenix-park/yesterday",
                    headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
   print(r.status_code); print(pd.json_normalize(r.json()).head(3).T)   # which column is the date? the time?

   r = requests.get("https://api.irishrail.ie/realtime/realtime.asmx/getTrainMovementsXML",
                    params={"TrainId": "A223", "TrainDate": "20 Nov 2026"}, timeout=30)
   print(r.text[:1800])   # are Arrival/Departure filled for a finished journey? blank or 00:00 when not?
   ```
6. Settings → Actions → General → Workflow permissions → **Read and write**.
7. **Always `git pull` before you `git push` from VS Code.** The bot pushes data about every 30 minutes, so your push will be rejected otherwise.
8. Actions tab → **RailPredict collect** → **Run workflow**. After about 30 minutes a data commit should appear.
9. The day after, check `data/reports/summary_<day>.txt`. To process a specific day by hand: Actions → **RailPredict daily** → Run workflow → enter the day.

---

## 10. Looking at the data

```
git pull
python scripts/inspect_data.py 2026-11-20          # print
python scripts/inspect_data.py 2026-11-20 --save   # print and save to data/reports/
```
It shows polls and gaps, trains seen, status mix, actual times found, weather rows and columns, failed calls, merged row counts, and a first look at accuracy (median error in minutes of Irish Rail's prediction versus the plain timetable, grouped by how long before arrival the snapshot was taken).

To change something, edit the script or a CSV, then re-run `clean_data.py` and `merge_data.py` for that day.

Column prefixes in the merged file: `Mov_` = actual times from the movements, `OM_` = Open-Meteo, `Met_` = Met Éireann (`Met_Station` shows which station was matched). The prefixes only tell the sources apart; the values are untouched.

---

## 11. Change history

### 2026-11-21 – v2 (first draft, not yet pushed)
* Scope reduced to services starting or ending at Heuston and Connolly.
* Added the 10-minute self-restarting loop and the daily workflow.
* Added `collect_movements.py` for actual times; boards kept as the prediction history.
* Weather moved to a daily job; Met Éireann measured observations added; Open-Meteo reduced to one request a day.
* Cleaning changed to keep all snapshots; weather joined on the hour the train was due.
* Added the `inspect_data.py` accuracy preview.
* Documented the issues found in v1 (section 4).
