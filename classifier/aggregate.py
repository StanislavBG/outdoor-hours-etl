"""Roll hourly classified data up to region-year.

One row per (region, year) with the yearly stay_outside-hour totals.
Averaging across the 3 points in a region gives the "typical" yearly hours
a single location in that region offers — more interpretable than summing.
"""
from __future__ import annotations

import pandas as pd

from classifier.personal import apply


def to_point_year(df: pd.DataFrame) -> pd.DataFrame:
    """Per (point, year) yearly hour totals."""
    d = apply(df)
    g = (
        d.groupby(["region", "point", "year"])
        .agg(
            hours=("stay_outside", "size"),
            daytime_hours=("is_day", "sum"),
            stay_outside_hours=("stay_outside", "sum"),
        )
        .reset_index()
    )
    g["pct_of_year"] = (g["stay_outside_hours"] / g["hours"] * 100).round(2)
    g["pct_of_daytime"] = (g["stay_outside_hours"] / g["daytime_hours"] * 100).round(2)
    g["is_full_year"] = g["hours"] >= 8760
    return g


def to_region_year(point_year: pd.DataFrame) -> pd.DataFrame:
    """Average across the points in each region to get typical yearly hours."""
    r = (
        point_year.groupby(["region", "year"])
        .agg(
            n_points=("point", "nunique"),
            min_hours=("hours", "min"),
            max_hours=("hours", "max"),
            stay_outside_hours=("stay_outside_hours", "mean"),
            pct_of_daytime=("pct_of_daytime", "mean"),
        )
        .reset_index()
    )
    r["stay_outside_hours"] = r["stay_outside_hours"].round(1)
    r["pct_of_daytime"] = r["pct_of_daytime"].round(2)
    r["is_full_year"] = r["min_hours"] >= 8760
    return r
