"""Dump every classified hourly row to CSV. No aggregation."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from classifier.personal import apply

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PARQUET = ROOT / "data" / "curated" / "hourly_sample_last30.parquet"
OUT = ROOT / "data" / "samples" / "hourly_sample_last30_classified.csv"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet", default=str(DEFAULT_PARQUET))
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--print", type=int, default=60,
                        help="How many rows to echo to stdout (0 = none)")
    args = parser.parse_args()

    pd.set_option("display.max_rows", None)
    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", None)

    df = pd.read_parquet(args.parquet)
    df = apply(df)
    df = df.sort_values(["region", "point", "ts_utc"]).reset_index(drop=True)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)

    cols = [
        "region", "point", "ts_local", "hour_of_day",
        "temperature_2m", "temp_f", "uv_index_est", "cloud_cover", "is_day",
        "stay_outside", "stay_outside_reason",
    ]
    if args.print:
        print(df[cols].head(args.print).to_string(index=False))
    print(f"\n{len(df):,} rows  →  {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
