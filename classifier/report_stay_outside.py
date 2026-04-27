"""Run the Personal Classifier on a curated parquet and print tables.

Usage:
  uv run python -m classifier.report_stay_outside
  uv run python -m classifier.report_stay_outside --parquet data/curated/hourly_sample_last30.parquet
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from classifier.personal import COLD_C, HOT_C, UV_MAX, apply

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PARQUET = ROOT / "data" / "curated" / "hourly_sample_last30.parquet"


def print_header() -> None:
    print("\n" + "=" * 78)
    print(f" Personal Classifier — stay_outside")
    print(f"   Rule: is_day == 1  AND  {COLD_C}°C ≤ temp ≤ {HOT_C}°C  AND  uv_index ≤ {UV_MAX}")
    print("=" * 78)


def region_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Two scores per region: absolute stay_outside hours + % of daytime hours."""
    agg = (
        df.groupby("region")
        .agg(
            total_hours=("stay_outside", "size"),
            daytime_hours=("is_day", "sum"),
            stay_outside_hours=("stay_outside", "sum"),
        )
        .assign(
            pct_of_all=lambda x: (x["stay_outside_hours"] / x["total_hours"] * 100).round(1),
            pct_of_daytime=lambda x: (x["stay_outside_hours"] / x["daytime_hours"] * 100).round(1),
        )
        .reset_index()
    )
    return agg


def hour_of_day_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Per-region average per hour of day."""
    g = (
        df.groupby(["region", "hour_of_day"])
        .agg(
            temp_c=("temperature_2m", "mean"),
            temp_f=("temp_f", "mean"),
            uv=("uv_index_est", "mean"),
            day_frac=("is_day", "mean"),
            stay_outside_rate=("stay_outside", "mean"),
        )
        .reset_index()
    )
    g[["temp_c", "temp_f", "uv"]] = g[["temp_c", "temp_f", "uv"]].round(1)
    g["day_frac"] = g["day_frac"].round(2)
    g["stay_outside_rate"] = (g["stay_outside_rate"] * 100).round(0).astype(int)
    pivot = g.pivot(index="hour_of_day", columns="region",
                    values=["temp_c", "temp_f", "uv", "stay_outside_rate"])
    return pivot


def sample_day(df: pd.DataFrame, point: str, target_date: str | None = None) -> pd.DataFrame:
    """Hourly rows for one point on one day (defaults to most recent)."""
    sub = df[df["point"] == point].copy()
    sub["local_date"] = sub["ts_local"].dt.date
    if target_date is None:
        target = sub["local_date"].max()
    else:
        target = pd.to_datetime(target_date).date()
    day = sub[sub["local_date"] == target].copy()
    cols = [
        "ts_local", "hour_of_day", "temperature_2m", "temp_f",
        "uv_index_est", "is_day", "cloud_cover", "stay_outside", "stay_outside_reason",
    ]
    day = day[cols].sort_values("hour_of_day").reset_index(drop=True)
    day["time_local"] = day["ts_local"].dt.strftime("%H:%M")
    day["temp_c"] = day["temperature_2m"].round(1)
    day["temp_f"] = day["temp_f"].round(1)
    day["uv"] = day["uv_index_est"].round(1)
    day["cloud_pct"] = day["cloud_cover"].round(0).astype(int)
    display = day[["time_local", "temp_c", "temp_f", "uv", "cloud_pct",
                   "is_day", "stay_outside", "stay_outside_reason"]]
    return display, target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet", default=str(DEFAULT_PARQUET))
    args = parser.parse_args()

    pd.set_option("display.max_rows", 80)
    pd.set_option("display.width", 140)
    pd.set_option("display.max_columns", 20)

    df = pd.read_parquet(args.parquet)
    df = apply(df)

    print_header()
    print(f"\nRows: {len(df):,}   Points: {df['point'].nunique()}   "
          f"Window: {df['ts_local'].min()}  →  {df['ts_local'].max()}")

    print("\n--- Score by region (over the sample window) ---")
    scores = region_scores(df)
    print(scores.to_string(index=False))

    print("\n--- Per-point breakdown ---")
    per_point = (
        df.groupby(["region", "point"])
        .agg(
            total_hours=("stay_outside", "size"),
            daytime=("is_day", "sum"),
            stay_outside=("stay_outside", "sum"),
        )
        .assign(pct_of_daytime=lambda x: (x["stay_outside"] / x["daytime"] * 100).round(1))
        .reset_index()
    )
    print(per_point.to_string(index=False))

    print("\n--- Hour-of-day profile (sample averages per region) ---")
    print(hour_of_day_profile(df).to_string())

    # Pick a representative point per region for a single-day table.
    for point_id in ("san_jose", "bellevue"):
        day, target = sample_day(df, point_id)
        print(f"\n--- Hour-by-hour: {point_id}  on  {target} ---")
        print(day.to_string(index=False))

    print("\n--- Why rows failed (reason breakdown) ---")
    reasons = (
        df.groupby(["region", "stay_outside_reason"]).size().unstack(fill_value=0)
    )
    reasons["total"] = reasons.sum(axis=1)
    print(reasons.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
