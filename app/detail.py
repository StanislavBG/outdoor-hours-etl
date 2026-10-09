"""Drill-down detail: next-finer grain rows for one chart bucket, paired per region.

    yearly  → monthly  (12 rows / year)
    monthly → daily    (~30 rows / month)
    daily   → hourly   (24 rows / day) via classifier.hourly.region_hourly, so the
              pass/fail count uses the same profile rules as the headline rollups.
"""
from __future__ import annotations

from datetime import date

import duckdb
import pandas as pd
from fastapi import HTTPException

from app import data
from app.data import load_rollup
from classifier.hourly import region_hourly
from etl.catalog import json_scalar
from etl.points import REGIONS as REGION_REGISTRY

REGION_ORDER = list(REGION_REGISTRY)

# One shared connection; each call works on its own .cursor().
_CON = duckdb.connect()

# Columns region_hourly can use; only those present in the file are selected.
_HOURLY_SRC = [
    "ts_local", "region", "is_day", "temperature_2m", "uv_index_est", "precipitation",
    "cloud_cover", "relative_humidity_2m", "us_aqi", "wind_speed_10m", "wind_gusts_10m",
]

# Paired-columns: `paired: true` renders per-region columns, `paired: false` is a
# shared column (the x-axis bucket label). `leading` columns are shown first.
# Paired-columns: the classification metric leads; everything else follows.
# `leading: true` means "show in both regions side-by-side at the front of the
# table". `paired: true` means "render per-region columns"; `paired: false`
# means "shared column" (only used for the x-axis bucket label).
DETAIL_COLS: dict[str, list[dict]] = {
    "hourly": [
        {"key": "ts_local",             "label": "Local time",        "fmt": "time", "paired": False},
        {"key": "stay_outside_pts",     "label": "Stay-out",          "fmt": "pts",  "paired": True, "leading": True},
        {"key": "ok_day",               "label": "Day?",              "fmt": "bool", "paired": True, "leading": True},
        {"key": "temperature_2m",       "label": "Temp (°C)",         "fmt": "num1", "paired": True},
        {"key": "uv_index_est",         "label": "UV",                "fmt": "num2", "paired": True},
        {"key": "precipitation",        "label": "Rain (mm/h)",       "fmt": "num2", "paired": True},
        {"key": "cloud_cover",          "label": "Cloud (%)",         "fmt": "num0", "paired": True},
        {"key": "wind_gusts_10m",       "label": "Gust (m/s)",        "fmt": "num1", "paired": True},
    ],
    "daily": [
        {"key": "local_date",           "label": "Date",              "paired": False},
        {"key": "stay_outside_hours",   "label": "Stay-out (h)",      "fmt": "num1", "paired": True, "leading": True},
        {"key": "pct_daytime_outside",  "label": "% daylight usable", "fmt": "num1", "paired": True, "leading": True},
        {"key": "temperature_2m_mean",  "label": "Temp avg (°C)",     "fmt": "num1", "paired": True},
        {"key": "temperature_2m_max",   "label": "Temp max",          "fmt": "num1", "paired": True},
        {"key": "uv_index_est_max",     "label": "UV max",            "fmt": "num2", "paired": True},
        {"key": "precipitation_sum",    "label": "Rain (mm)",         "fmt": "num2", "paired": True},
        {"key": "cloud_cover_mean",     "label": "Cloud (%)",         "fmt": "num0", "paired": True},
        {"key": "wind_gusts_10m_max",   "label": "Peak gust (m/s)",   "fmt": "num1", "paired": True},
    ],
    "monthly": [
        {"key": "month_label",          "label": "Month",             "paired": False},
        {"key": "stay_outside_hours",   "label": "Stay-out (h)",      "fmt": "num0", "paired": True, "leading": True},
        {"key": "pct_daytime_outside",  "label": "% daylight usable", "fmt": "num1", "paired": True, "leading": True},
        {"key": "temperature_2m_mean",  "label": "Temp avg (°C)",     "fmt": "num1", "paired": True},
        {"key": "temperature_2m_max",   "label": "Temp max",          "fmt": "num1", "paired": True},
        {"key": "uv_index_est_mean",    "label": "UV avg",            "fmt": "num2", "paired": True},
        {"key": "precipitation_sum",    "label": "Rain (mm)",         "fmt": "num1", "paired": True},
        {"key": "wind_gusts_10m_max",   "label": "Peak gust (m/s)",   "fmt": "num1", "paired": True},
    ],
}


def _parse_date(bucket: str, kind: str) -> date:
    try:
        return date.fromisoformat(bucket[:10])
    except ValueError as e:
        raise HTTPException(400, f"bad {kind} bucket: {bucket}") from e


def _hourly(tag: str, bucket: str) -> pd.DataFrame:
    path = data.CURATED / f"hourly_{tag}.parquet"
    if not path.exists():
        raise HTTPException(404, f"no hourly rollup for tag={tag}")
    d = _parse_date(bucket, "daily")
    cur = _CON.cursor()
    try:
        have = {r[0] for r in cur.execute(
            "SELECT column_name FROM (DESCRIBE SELECT * FROM read_parquet(?))", [str(path)]
        ).fetchall()}
        sel = ", ".join(c for c in _HOURLY_SRC if c in have)
        raw = cur.execute(
            f"SELECT {sel} FROM read_parquet(?) "
            "WHERE year = ? AND month = ? AND day = ? ORDER BY ts_local, region",
            [str(path), d.year, d.month, d.day],
        ).fetchdf()
    finally:
        cur.close()
    return region_hourly(raw)


def _monthly_drill(tag: str, bucket: str) -> pd.DataFrame:
    d = _parse_date(bucket, "monthly")
    df = load_rollup(tag, "daily")
    ld = pd.to_datetime(df["local_date"])
    keep = df[(ld.dt.year == d.year) & (ld.dt.month == d.month)]
    return keep.sort_values(["local_date", "region"]).reset_index(drop=True)


def _yearly_drill(tag: str, bucket: str) -> pd.DataFrame:
    try:
        y = int(bucket)
    except ValueError as e:
        raise HTTPException(400, f"bad yearly bucket: {bucket}") from e
    df = load_rollup(tag, "monthly")
    keep = df[df["year"] == y].sort_values(["month", "region"]).reset_index(drop=True)
    # assign returns a copy: load_rollup frames are cached and shared
    return keep.assign(
        month_label=keep["year"].astype(int).astype(str).str.zfill(4)
        + "-" + keep["month"].astype(int).astype(str).str.zfill(2)
    )


def pair_rows(df: pd.DataFrame, cols: list[dict], x_key: str) -> list[dict]:
    """Collapse a long frame (one row per x and region) into one dict per x:
    `{"_x": x, <shared>: v, <region>: {col: v}}`, in first-appearance order of x.
    """
    if df.empty:
        return []
    paired = [c["key"] for c in cols if c.get("paired") and c["key"] in df.columns]
    if "n_points" in df.columns and "n_points" not in paired:
        paired.append("n_points")
    shared = [c["key"] for c in cols if not c.get("paired") and c["key"] in df.columns]
    use = list(dict.fromkeys([x_key, "region", *shared, *paired]))
    prim = df[use].astype(object).map(json_scalar)
    rows: dict = {}
    for rec in prim.to_dict("records"):
        slot = rows.get(rec[x_key])
        if slot is None:
            slot = rows[rec[x_key]] = {"_x": rec[x_key], **{k: rec[k] for k in shared}}
        slot[rec["region"]] = {k: rec[k] for k in paired}
    return list(rows.values())


def build_detail(tag: str, grain: str, bucket: str, regions: list[str] | None) -> dict:
    if grain == "daily":
        df, detail_grain, x_key = _hourly(tag, bucket), "hourly", "ts_local"
    elif grain == "monthly":
        df, detail_grain, x_key = _monthly_drill(tag, bucket), "daily", "local_date"
    else:
        df, detail_grain, x_key = _yearly_drill(tag, bucket), "monthly", "month_label"

    if regions is None:
        order = REGION_ORDER
    else:
        wanted = set(regions)
        order = [r for r in REGION_ORDER if r in wanted]
        df = df[df["region"].isin(wanted)]

    cols = DETAIL_COLS[detail_grain]
    return {
        "tag": tag,
        "grain": grain,
        "bucket": bucket,
        "detail_grain": detail_grain,
        "columns": cols,
        "regions": {r: REGION_REGISTRY[r]["label"] for r in order},
        "region_registry": {r: REGION_REGISTRY[r] for r in order},
        "region_order": order,
        "x_key": x_key,
        "rows": pair_rows(df, cols, x_key),
        "n_rows": int(df[x_key].nunique()) if x_key in df.columns else len(df),
    }
