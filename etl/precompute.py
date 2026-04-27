"""Pre-compute daily / monthly / yearly rollups from the curated hourly parquet.

Writes to data/curated/ :
    daily_<tag>.parquet     per (region, point, local_date)
    monthly_<tag>.parquet   per (region, point, year, month)
    yearly_<tag>.parquet    per (region, point, year)
    region_daily_<tag>.parquet, region_monthly_<tag>.parquet, region_yearly_<tag>.parquet
        (means across the points in a region, + is_full flag where coverage is complete)

Each grain carries the same metric columns so the dashboard can swap metrics cheaply.
"""
from __future__ import annotations

import argparse
import calendar
from pathlib import Path

import pandas as pd

from classifier.personal import apply, PROFILES

ROOT = Path(__file__).resolve().parents[1]
CURATED = ROOT / "data" / "curated"


# Columns to carry through every grain (plus stay_outside metrics).
# Each entry: (column, aggregation-at-this-grain)
_POINT_HOURLY_AGGS: dict[str, str] = {
    "temperature_2m": "mean",
    "apparent_temperature": "mean",
    "dew_point_2m": "mean",
    "relative_humidity_2m": "mean",
    "uv_index_est": "mean",
    "cloud_cover": "mean",
    "shortwave_radiation": "mean",
    "wind_speed_10m": "mean",
    "wind_gusts_10m": "max",
    "pressure_msl": "mean",
    "us_aqi": "mean",
    "pm2_5": "mean",
    "pm10": "mean",
}
# Sums meaningful at every grain
_POINT_SUM: dict[str, str] = {
    "precipitation": "sum",
    "rain": "sum",
    "snowfall": "sum",
    "sunshine_duration": "sum",   # seconds
}


def _per_point(hourly: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    """Aggregate hourly rows per (region, point, + group_cols)."""
    aggs = {
        "hours": ("stay_outside", "size"),
        "daytime_hours": ("is_day", "sum"),
        "stay_outside_hours": ("stay_outside", "sum"),
        # One stay_outside_<profile>_hours per profile.
        **{f"stay_outside_{p.id}_hours": (f"stay_outside_{p.id}", "sum") for p in PROFILES},
        **{f"{c}_mean": (c, "mean") for c in _POINT_HOURLY_AGGS},
        **{f"{c}_max": (c, "max") for c in ("temperature_2m", "uv_index_est", "wind_gusts_10m", "us_aqi")},
        **{f"{c}_min": (c, "min") for c in ("temperature_2m",)},
        **{f"{c}_sum": (c, "sum") for c in _POINT_SUM},
    }
    g = hourly.groupby(["region", "point"] + group_cols, as_index=False).agg(**aggs)
    g["pct_daytime_outside"] = (g["stay_outside_hours"] / g["daytime_hours"] * 100).round(2)
    for p in PROFILES:
        g[f"pct_daytime_outside_{p.id}"] = (
            g[f"stay_outside_{p.id}_hours"] / g["daytime_hours"] * 100
        ).round(2)
    # Sunshine sum is seconds; add hours for readability.
    g["sunshine_hours"] = (g["sunshine_duration_sum"] / 3600.0).round(2)
    return g


def _per_region(point_grain: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    """Average across the points within a region. Flag when coverage is complete."""
    mean_cols = [
        c for c in point_grain.columns
        if c not in {"region", "point", *group_cols}
        and pd.api.types.is_numeric_dtype(point_grain[c])
    ]
    g = (
        point_grain
        .groupby(["region"] + group_cols, as_index=False)
        .agg({**{c: "mean" for c in mean_cols}, "point": "nunique"})
        .rename(columns={"point": "n_points"})
    )
    return g


def build(tag: str) -> dict[str, Path]:
    """Read curated hourly parquet, write all grains, return paths written."""
    hourly_path = CURATED / f"hourly_{tag}.parquet"
    if not hourly_path.exists():
        raise SystemExit(f"missing {hourly_path}")

    hourly = pd.read_parquet(hourly_path)
    hourly = apply(hourly)  # adds stay_outside, reason, temp_f

    # local calendar helpers
    hourly["local_date"] = hourly["ts_local"].dt.date
    # year / month / hour_of_day already present from curate.py

    out: dict[str, Path] = {}

    # ----- per-point grains -----
    daily_pt = _per_point(hourly, ["local_date"])
    # A "full" local day has 24 hours of data.
    daily_pt["is_full"] = daily_pt["hours"] >= 24

    monthly_pt = _per_point(hourly, ["year", "month"])
    monthly_pt["month_start"] = pd.to_datetime(
        monthly_pt[["year", "month"]].assign(day=1)
    ).dt.date
    monthly_pt["is_full"] = monthly_pt.apply(
        lambda r: r["hours"] >= 24 * calendar.monthrange(int(r["year"]), int(r["month"]))[1],
        axis=1,
    )

    yearly_pt = _per_point(hourly, ["year"])
    yearly_pt["is_full"] = yearly_pt["hours"] >= 8760  # leap years get 8784; full enough

    # ----- per-region grains (mean across the 3 points in a region) -----
    daily_rg = _per_region(daily_pt, ["local_date"])
    monthly_rg = _per_region(monthly_pt, ["year", "month"])
    monthly_rg["month_start"] = pd.to_datetime(
        monthly_rg[["year", "month"]].assign(day=1)
    ).dt.date
    yearly_rg = _per_region(yearly_pt, ["year"])

    # ----- write parquet + report -----
    mapping = {
        "daily": daily_pt,
        "monthly": monthly_pt,
        "yearly": yearly_pt,
        "region_daily": daily_rg,
        "region_monthly": monthly_rg,
        "region_yearly": yearly_rg,
    }
    CURATED.mkdir(parents=True, exist_ok=True)
    for name, df in mapping.items():
        p = CURATED / f"{name}_{tag}.parquet"
        df.to_parquet(p, index=False, compression="zstd")
        out[name] = p
        print(f"  {name:14s}  {len(df):>7,} rows  →  {p.name}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True, help="e.g. sample_last30 or full")
    args = parser.parse_args()
    build(args.tag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
