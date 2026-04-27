"""Local FastAPI dashboard for the Weather Compare project.

Run:
    uv run python -m app.server
    # → http://127.0.0.1:8000/

Routes:
    GET /                     → dashboard HTML
    GET /api/tags             → datasets available on disk (by tag)
    GET /api/metrics          → metric catalog (human-friendly labels per grain)
    GET /api/series           → JSON time series for a given (tag, grain, metric)
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Literal

import duckdb
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
CURATED = ROOT / "data" / "curated"
STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Weather Compare")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


# ---------------------------------------------------------------------------
# Metric catalog
# ---------------------------------------------------------------------------

# key = column name in the grain parquet.
# Each entry declares which grains support it, the UI label, and the axis/unit.
# Sum-style metrics (stay_outside_hours, precipitation_sum, sunshine_hours) only make
# sense per grain — e.g. "sum of stay-outside hours in a day/month/year".
# Mean-style metrics are meaningful at any grain.
METRICS: list[dict] = [
    {"key": "stay_outside_hours",   "label": "Good-for-outdoors hours",        "unit": "hours",  "kind": "sum"},
    {"key": "pct_daytime_outside",  "label": "% of daylight that's comfortable", "unit": "%",    "kind": "pct"},
    {"key": "temperature_2m_mean",  "label": "Average temperature",            "unit": "°C",     "kind": "mean"},
    {"key": "temperature_2m_max",   "label": "Hottest point",                  "unit": "°C",     "kind": "max"},
    {"key": "apparent_temperature_mean", "label": "Average feels-like temperature", "unit": "°C", "kind": "mean"},
    {"key": "uv_index_est_mean",    "label": "Average UV",                     "unit": "UV",     "kind": "mean"},
    {"key": "uv_index_est_max",     "label": "Strongest UV",                   "unit": "UV",     "kind": "max"},
    {"key": "cloud_cover_mean",     "label": "Cloudiness",                     "unit": "%",      "kind": "mean"},
    {"key": "precipitation_sum",    "label": "Total rain",                     "unit": "mm",     "kind": "sum"},
    {"key": "wind_speed_10m_mean",  "label": "Average wind",                   "unit": "m/s",    "kind": "mean"},
    {"key": "wind_gusts_10m_max",   "label": "Strongest gust",                 "unit": "m/s",    "kind": "max"},
    {"key": "sunshine_hours",       "label": "Sunshine hours",                 "unit": "hours",  "kind": "sum"},
    {"key": "relative_humidity_2m_mean", "label": "Humidity",                  "unit": "%",      "kind": "mean"},
    {"key": "pressure_msl_mean",    "label": "Air pressure",                   "unit": "hPa",    "kind": "mean"},
]
_METRIC_KEYS = {m["key"] for m in METRICS}

from etl.points import REGIONS as REGION_REGISTRY  # noqa: E402

REGION_LABEL = {k: v["label"] for k, v in REGION_REGISTRY.items()}
REGION_ORDER = list(REGION_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _available_tags() -> list[str]:
    """Find tags for which the region_daily parquet exists (minimum needed for dashboard)."""
    tags = sorted({
        p.stem.removeprefix("region_daily_")
        for p in CURATED.glob("region_daily_*.parquet")
    })
    return tags


def _load(tag: str, grain: Literal["daily", "monthly", "yearly"]) -> pd.DataFrame:
    path = CURATED / f"region_{grain}_{tag}.parquet"
    if not path.exists():
        raise HTTPException(404, f"no {grain} rollup for tag={tag}")
    return pd.read_parquet(path)


def _x_column(grain: str) -> str:
    return {"daily": "local_date", "monthly": "month_start", "yearly": "year"}[grain]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/tags")
def tags() -> JSONResponse:
    return JSONResponse({"tags": _available_tags()})


@app.get("/api/metrics")
def metrics() -> JSONResponse:
    return JSONResponse({
        "metrics": METRICS,
        "regions": REGION_LABEL,
        "region_registry": REGION_REGISTRY,
        "region_order": REGION_ORDER,
    })


@app.get("/api/series")
def series(
    tag: str = Query("sample_last30"),
    grain: Literal["daily", "monthly", "yearly"] = Query("daily"),
    metric: str = Query("stay_outside_hours"),
) -> JSONResponse:
    if metric not in _METRIC_KEYS:
        raise HTTPException(400, f"unknown metric: {metric}")

    df = _load(tag, grain)
    if metric not in df.columns:
        raise HTTPException(404, f"metric {metric} not present in {grain}_{tag}")

    x = _x_column(grain)
    series_out: dict[str, dict] = {}
    for region, grp in df.groupby("region"):
        grp = grp.sort_values(x).reset_index(drop=True)
        if grain == "yearly":
            xs = grp[x].astype(int).tolist()
        else:
            xs = [v.isoformat() if hasattr(v, "isoformat") else str(v) for v in grp[x]]
        ys = [None if pd.isna(v) else float(v) for v in grp[metric]]
        series_out[region] = {
            "label": REGION_LABEL.get(region, region),
            "x": xs,
            "y": ys,
            "n_points": grp["n_points"].tolist() if "n_points" in grp.columns else None,
        }

    meta = next(m for m in METRICS if m["key"] == metric)
    return JSONResponse({
        "tag": tag,
        "grain": grain,
        "metric": metric,
        "metric_label": meta["label"],
        "unit": meta["unit"],
        "series": series_out,
        "row_counts": {r: len(v["x"]) for r, v in series_out.items()},
    })


# ---------------------------------------------------------------------------
# Drill-down detail endpoint
# ---------------------------------------------------------------------------
#
# Click on a chart point → return the next-finer grain rows for that region:
#   yearly  → monthly  (12 rows / year)
#   monthly → daily    (~30 rows / month)
#   daily   → hourly   (~24h × 3 points = ~72 rows / day) with classifier flags

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


def _to_primitive(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            pass
    return v


def _pair_rows(df: pd.DataFrame, cols: list[dict], x_key: str) -> list[dict]:
    """Pivot a long-format (rows per region) dataframe into one row per x with
    `santa_clara_ca` / `eastside_king_wa` sub-dicts for each paired column.
    """
    keyed: dict = {}
    paired_keys = [c["key"] for c in cols if c.get("paired")]
    shared_keys = [c["key"] for c in cols if not c.get("paired")]
    for _, r in df.iterrows():
        xv = _to_primitive(r.get(x_key))
        # Use a string key for the dict so identical x across regions collapses.
        xk = xv if isinstance(xv, (str, int)) else str(xv)
        slot = keyed.setdefault(xk, {"_x": xv})
        region = r["region"]
        slot.setdefault(region, {})
        for k in paired_keys:
            if k in df.columns:
                slot[region][k] = _to_primitive(r.get(k))
        for k in shared_keys:
            if k in df.columns and k not in slot:
                slot[k] = _to_primitive(r.get(k))
    # Preserve input order of x (first appearance wins).
    rows = []
    seen: set = set()
    for _, r in df.iterrows():
        xv = _to_primitive(r.get(x_key))
        xk = xv if isinstance(xv, (str, int)) else str(xv)
        if xk in seen:
            continue
        seen.add(xk)
        rows.append(keyed[xk])
    return rows


@app.get("/api/detail")
def detail(
    tag: str = Query(...),
    grain: Literal["daily", "monthly", "yearly"] = Query(...),
    bucket: str = Query(..., description="ISO date for daily/monthly buckets, integer year for yearly"),
) -> JSONResponse:
    if grain == "daily":
        # Hourly drill: aggregate per (hour, region) across the 3 points so each
        # row shows one timestamp with SCC + WA side-by-side. stay_outside becomes
        # a "N of 3 points passed" score instead of a per-point bool.
        path = CURATED / f"hourly_{tag}.parquet"
        if not path.exists():
            raise HTTPException(404, f"no hourly rollup for tag={tag}")
        try:
            d = date.fromisoformat(bucket[:10])
        except ValueError as e:
            raise HTTPException(400, f"bad daily bucket: {bucket}") from e

        raw = duckdb.connect().execute(
            """
            SELECT ts_local, region, is_day, temperature_2m, uv_index_est,
                   cloud_cover, precipitation, wind_speed_10m, wind_gusts_10m
              FROM read_parquet(?)
             WHERE CAST(ts_local AS DATE) = ?
             ORDER BY ts_local, region
            """,
            [str(path), d],
        ).fetchdf()

        is_day  = raw["is_day"].eq(1)
        temp_ok = raw["temperature_2m"].between(7.0, 30.0)
        uv_ok   = raw["uv_index_est"].le(6.0)
        prec_ok = raw["precipitation"].le(1.0)
        raw["stay_outside"] = (is_day & temp_ok & uv_ok & prec_ok).astype("int8")
        raw["is_day_int"]   = is_day.astype("int8")

        df = (
            raw.groupby(["ts_local", "region"], as_index=False)
            .agg(
                stay_outside_pts=("stay_outside", "sum"),  # 0..3
                n_points=("stay_outside", "size"),
                ok_day=("is_day_int", "max"),
                temperature_2m=("temperature_2m", "mean"),
                uv_index_est=("uv_index_est", "mean"),
                precipitation=("precipitation", "mean"),
                cloud_cover=("cloud_cover", "mean"),
                wind_gusts_10m=("wind_gusts_10m", "max"),
            )
            .sort_values(["ts_local", "region"])
            .reset_index(drop=True)
        )
        detail_grain = "hourly"
        x_key = "ts_local"

    elif grain == "monthly":
        try:
            d = date.fromisoformat(bucket[:10])
        except ValueError as e:
            raise HTTPException(400, f"bad monthly bucket: {bucket}") from e
        df = _load(tag, "daily")
        ld = pd.to_datetime(df["local_date"])
        df = df[(ld.dt.year == d.year) & (ld.dt.month == d.month)].sort_values(["local_date", "region"]).reset_index(drop=True)
        detail_grain = "daily"
        x_key = "local_date"

    else:  # yearly
        try:
            y = int(bucket)
        except ValueError as e:
            raise HTTPException(400, f"bad yearly bucket: {bucket}") from e
        df = _load(tag, "monthly")
        df = df[df["year"] == y].sort_values(["month", "region"]).reset_index(drop=True)
        df["month_label"] = df.apply(lambda r: f"{int(r['year']):04d}-{int(r['month']):02d}", axis=1)
        detail_grain = "monthly"
        x_key = "month_label"

    cols = DETAIL_COLS[detail_grain]
    return JSONResponse({
        "tag": tag,
        "grain": grain,
        "bucket": bucket,
        "detail_grain": detail_grain,
        "columns": cols,
        "regions": REGION_LABEL,
        "region_registry": REGION_REGISTRY,
        "region_order": REGION_ORDER,
        "x_key": x_key,
        "rows": _pair_rows(df, cols, x_key),
        "n_rows": int(df[x_key].nunique()) if x_key in df.columns else len(df),
    })


def main() -> None:
    import uvicorn
    uvicorn.run("app.server:app", host="127.0.0.1", port=8000, reload=False, log_level="info")


if __name__ == "__main__":
    main()
