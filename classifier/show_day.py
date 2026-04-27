"""Pick one random day + one random point per region, print the 24 raw classified rows."""
from __future__ import annotations

import argparse
import random
from pathlib import Path

import pandas as pd

from classifier.personal import apply

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PARQUET = ROOT / "data" / "curated" / "hourly_sample_last30.parquet"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet", default=str(DEFAULT_PARQUET))
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()
    if args.seed is not None:
        random.seed(args.seed)

    pd.set_option("display.max_rows", 30)
    pd.set_option("display.width", 140)

    df = apply(pd.read_parquet(args.parquet))
    df["local_date"] = df["ts_local"].dt.date
    day = random.choice(sorted(df["local_date"].unique()))

    cols = ["time", "temp_c", "temp_f", "uv", "cloud_pct", "is_day", "stay_outside", "reason"]

    for region in ("santa_clara_ca", "eastside_king_wa"):
        points = df.loc[df["region"] == region, "point"].unique().tolist()
        point = random.choice(points)
        rows = df[(df["region"] == region) & (df["point"] == point) & (df["local_date"] == day)].sort_values("hour_of_day")
        view = pd.DataFrame({
            "time": rows["ts_local"].dt.strftime("%H:%M"),
            "temp_c": rows["temperature_2m"].round(1),
            "temp_f": rows["temp_f"].round(1),
            "uv": rows["uv_index_est"].round(2),
            "cloud_pct": rows["cloud_cover"].round(0).astype(int),
            "is_day": rows["is_day"].astype(int),
            "stay_outside": rows["stay_outside"].astype(int),
            "reason": rows["stay_outside_reason"],
        })[cols]
        print(f"\n=== {region}  /  {point}  /  {day}  ({len(view)} rows) ===")
        print(view.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
