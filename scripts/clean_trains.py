
import pandas as pd

from common import RAW, CLEAN, day_from_args


def main():
    day = day_from_args()
    raw_path = RAW / "trains" / f"trains_{day}.csv"

    if not raw_path.exists():
        print(f"No train data found for {day}")
        return

    trains = pd.read_csv(raw_path, dtype=str, keep_default_na=False)

    # Keep hourly snapshots but remove repeated rows from the same run.
    keys = ["Traincode", "Traindate", "Stationcode", "CollectedAtUTC"]

    trains = trains.sort_values("CollectedAtUTC")
    trains = trains.drop_duplicates(subset=keys, keep="last")

    # Irish Rail reports how many minutes late each train is.
    # Invalid or missing values are kept as missing, not changed to zero.
    trains["DelayMinutes"] = pd.to_numeric(
        trains["Late"], errors="coerce"
    ).astype("Int64")

    out_path = CLEAN / f"trains_clean_{day}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    trains.to_csv(out_path, index=False)

    print(f"Raw rows: {len(pd.read_csv(raw_path))}")
    print(f"Clean rows: {len(trains)}")
    print(f"Missing delay values: {trains['DelayMinutes'].isna().sum()}")
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
