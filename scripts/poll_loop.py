"""
poll_loop.py - NEW. Keeps polling the boards every 10 minutes for up to
5 hours 40 minutes, saving to GitHub every 30 minutes.

WHY: GitHub's own hourly timer (cron) skipped most of your runs (about 12 of
roughly 110 in 5 days). So instead of asking GitHub to start a short job
every time, ONE job now stays alive and does the waiting itself. When it is
close to GitHub's 6-hour limit it starts the next run itself
(see railpredict_collect.yml). The cron in that file is only a safety net.

Service window: 04:45 to 00:45 UTC (Irish time in winter). Outside it there
are no trains, so the loop stops, and the first safety-net cron after
04:45 starts the day again.
"""

import os
import subprocess
import time
from datetime import timedelta

import common
import collect_boards

POLL_EVERY_MIN = 10        # your decision
MAX_RUN_MIN = 340          # 5h40m; GitHub cancels a job at 6h
COMMIT_EVERY_POLLS = 3     # save to GitHub every 3 polls = every 30 minutes
START_MIN = 4 * 60 + 45    # 04:45 UTC
END_MIN = 0 * 60 + 45      # 00:45 UTC (the window crosses midnight)


def in_service(dt):
    minutes = dt.hour * 60 + dt.minute
    return minutes >= START_MIN or minutes < END_MIN


def run_git(*args):
    return subprocess.run(["git", *args], cwd=common.ROOT, capture_output=True, text=True)


def save_to_github(message):
    """
    Commit data/ and push it. Only does anything on GitHub itself, so you
    can run this script on your own computer without it touching git.

    CHANGED from v1: v1 used 'git pull --rebase -X ours || true', which on a
    clash keeps the other side and silently drops your new rows. Here a
    failed pull/push is retried, and if it still fails the commit stays on
    the runner and is pushed with the next save - nothing is hidden.
    """
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    run_git("add", "-A", "data")
    if run_git("diff", "--cached", "--quiet").returncode == 0:
        return                                    # nothing new
    run_git("commit", "-m", message)
    for _ in range(4):
        if run_git("pull", "--rebase").returncode == 0 and run_git("push").returncode == 0:
            return
        run_git("rebase", "--abort")
        time.sleep(5)
    print("WARNING: could not push this time; will try again at the next save.")


def tell_workflow(start_next_run):
    """Pass 'next=true/false' to the workflow so it knows whether to start another run."""
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            f.write(f"next={'true' if start_next_run else 'false'}\n")


def main():
    start = common.now_utc()
    if not in_service(start):
        print("Outside the service window - nothing to do.")
        tell_workflow(False)
        return

    polls = 0
    next_tick = start
    start_next_run = False

    while True:
        now = common.now_utc()
        if not in_service(now):
            print("Service window is over.")
            break
        if (now - start).total_seconds() / 60 >= MAX_RUN_MIN:
            print("Time limit reached - handing over to a new run.")
            start_next_run = True
            break

        try:
            saved, failed = collect_boards.collect_once(now)
            print(f"{common.iso(now)}  rows saved: {saved}  stations failed: {failed}")
        except Exception as error:               # one bad poll must never stop the loop
            common.log_failure("poll_loop", "collect_once", error, now)

        polls += 1
        if polls % COMMIT_EVERY_POLLS == 0:
            save_to_github(f"Boards {common.iso(now)}")

        # Wait for the next 10-minute tick. Ticks are on a fixed grid, so a
        # slow poll does not make every later poll drift.
        next_tick += timedelta(minutes=POLL_EVERY_MIN)
        wait = (next_tick - common.now_utc()).total_seconds()
        if wait < 0:                              # we fell behind - restart the grid
            next_tick = common.now_utc()
            wait = 0
        time.sleep(wait)

    save_to_github(f"Boards {common.iso(common.now_utc())} (end of run)")
    tell_workflow(start_next_run)


if __name__ == "__main__":
    main()
