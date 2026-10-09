"""Single source for hourly drill-down rows (used by app/detail and the public export).

Aggregates point-hours into one row per (ts_local, region), classifying each point-hour
with ``classifier.personal.stay_outside_for`` so drill-downs agree with the precomputed rollups.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from classifier.personal import DEFAULT_PROFILE_ID, PROFILES, Profile, stay_outside_for

_REQUIRED = ["ts_local", "region", "is_day", "temperature_2m", "uv_index_est", "precipitation"]
_OPTIONAL = ["cloud_cover", "relative_humidity_2m", "us_aqi", "wind_gusts_10m"]


def region_hourly(raw: pd.DataFrame, profile: Optional[Profile] = None) -> pd.DataFrame:
    missing = [c for c in _REQUIRED if c not in raw.columns]
    if missing:
        raise ValueError(f"region_hourly: missing required columns: {', '.join(missing)}")
    if profile is None:
        profile = next(p for p in PROFILES if p.id == DEFAULT_PROFILE_ID)

    df = raw.copy()
    for c in _OPTIONAL:
        if c not in df.columns:
            df[c] = np.nan
    df["_stay"] = stay_outside_for(df, profile)
    df["_day"] = (df["is_day"] == 1).astype("int8")

    out = df.groupby(["ts_local", "region"], as_index=False, sort=True).agg(
        stay_outside_pts=("_stay", "sum"),
        n_points=("_stay", "size"),
        ok_day=("_day", "max"),
        temperature_2m=("temperature_2m", "mean"),
        uv_index_est=("uv_index_est", "mean"),
        precipitation=("precipitation", "mean"),
        cloud_cover=("cloud_cover", "mean"),
        relative_humidity_2m=("relative_humidity_2m", "mean"),
        us_aqi=("us_aqi", "mean"),
        wind_gusts_10m=("wind_gusts_10m", "max"),
    )
    for c in ("stay_outside_pts", "n_points", "ok_day"):
        out[c] = out[c].astype(int)
    return out
