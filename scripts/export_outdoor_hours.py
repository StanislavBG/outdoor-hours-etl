"""Export last10y region rollups as JSON for the bilko.run/projects/outdoor-hours static page.

Writes three files (one per grain) to ~/Projects/Bilko/public/outdoor-hours/:
  - last10y_yearly.json   ~5 KB
  - last10y_monthly.json  ~50 KB
  - last10y_daily.json    ~1.5 MB

Each file packs all numeric columns for both regions so the React page can
serve every (metric, grain) combo locally without a backend.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from classifier.personal import PROFILES, DEFAULT_PROFILE_ID
from etl.points import REGIONS

ROOT = Path(__file__).resolve().parents[1]
CURATED = ROOT / "data" / "curated"
OUT = Path("/home/bilko/Projects/Bilko/public/outdoor-hours")

REGION_LABEL = {k: v["label"] for k, v in REGIONS.items()}
REGION_ORDER = list(REGIONS.keys())

# Mirror app/server.py METRICS list — keep keys/labels/units in sync.
# stay_outside_hours / pct_daytime_outside are aliases for the default profile;
# the frontend swaps to stay_outside_<profile>_hours when the user picks a
# different profile.
METRICS = [
    {"key": "stay_outside_hours",          "label": "Good-for-outdoors hours",          "unit": "hours", "kind": "sum",  "profile_aware": True},
    {"key": "pct_daytime_outside",         "label": "% of daylight that's comfortable", "unit": "%",     "kind": "pct",  "profile_aware": True},
    {"key": "temperature_2m_mean",         "label": "Average temperature",              "unit": "°C",    "kind": "mean"},
    {"key": "temperature_2m_max",          "label": "Hottest point",                    "unit": "°C",    "kind": "max"},
    {"key": "apparent_temperature_mean",   "label": "Average feels-like temperature",   "unit": "°C",    "kind": "mean"},
    {"key": "uv_index_est_mean",           "label": "Average UV",                       "unit": "UV",    "kind": "mean"},
    {"key": "uv_index_est_max",            "label": "Strongest UV",                     "unit": "UV",    "kind": "max"},
    {"key": "cloud_cover_mean",            "label": "Cloudiness",                       "unit": "%",     "kind": "mean"},
    {"key": "precipitation_sum",           "label": "Total rain",                       "unit": "mm",    "kind": "sum"},
    {"key": "wind_speed_10m_mean",         "label": "Average wind",                     "unit": "m/s",   "kind": "mean"},
    {"key": "wind_gusts_10m_max",          "label": "Strongest gust",                   "unit": "m/s",   "kind": "max"},
    {"key": "sunshine_hours",              "label": "Sunshine hours",                   "unit": "hours", "kind": "sum"},
    {"key": "relative_humidity_2m_mean",   "label": "Humidity",                         "unit": "%",     "kind": "mean"},
    {"key": "pressure_msl_mean",           "label": "Air pressure",                     "unit": "hPa",   "kind": "mean"},
    {"key": "us_aqi_mean",                 "label": "Air quality (US AQI)",             "unit": "AQI",   "kind": "mean"},
    {"key": "us_aqi_max",                  "label": "Worst-hour AQI",                   "unit": "AQI",   "kind": "max"},
    {"key": "pm2_5_mean",                  "label": "PM2.5",                            "unit": "µg/m³", "kind": "mean"},
]

X_COL = {"daily": "local_date", "monthly": "month_start", "yearly": "year"}


def _clean(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            pass
    return v


def export_grain(tag: str, grain: str) -> dict:
    df = pd.read_parquet(CURATED / f"region_{grain}_{tag}.parquet")
    x_col = X_COL[grain]
    out = {
        "tag": tag,
        "grain": grain,
        "x_label": "Year" if grain == "yearly" else "Local date",
        "regions": {},
    }
    for region, grp in df.groupby("region"):
        grp = grp.sort_values(x_col).reset_index(drop=True)
        if grain == "yearly":
            xs = [int(v) for v in grp[x_col]]
        else:
            xs = [_clean(v) for v in grp[x_col]]
        series = {}
        for m in METRICS:
            if m["key"] in grp.columns:
                series[m["key"]] = [_clean(v) for v in grp[m["key"]]]
        # Per-profile good-hours + pct-daylight series for the global toggle.
        for p in PROFILES:
            for col in (f"stay_outside_{p.id}_hours", f"pct_daytime_outside_{p.id}"):
                if col in grp.columns:
                    series[col] = [_clean(v) for v in grp[col]]
        out["regions"][region] = {
            "label": REGION_LABEL.get(region, region),
            "x": xs,
            "series": series,
        }
    return out


def export_hourly_months(tag: str) -> int:
    """Write one JSON per YYYY-MM with all hourly rows for that month, both regions paired.
    Enables lazy drill-down on the public site without shipping the whole 14 MB hourly parquet.
    """
    import duckdb
    hourly_path = ROOT / "data" / "curated" / f"hourly_{tag}.parquet"
    if not hourly_path.exists():
        print(f"skip hourly export: {hourly_path} not found")
        return 0
    hourly_dir = OUT / "hourly"
    hourly_dir.mkdir(parents=True, exist_ok=True)

    raw = duckdb.connect().execute(
        """
        SELECT CAST(ts_local AS DATE) AS d, ts_local, region,
               is_day, temperature_2m, uv_index_est, precipitation, cloud_cover,
               relative_humidity_2m, wind_gusts_10m, us_aqi
          FROM read_parquet(?)
         ORDER BY ts_local, region
        """,
        [str(hourly_path)],
    ).fetchdf()

    # Compute classifier flags + per-row ok_day (Int). Mirrors classifier/personal.py.
    from classifier.personal import (
        COLD_C, HOT_C, UV_MAX, RAIN_MAX_MM_H, OVERCAST_MAX_PCT, HUMIDITY_MAX_PCT,
    )
    raw["is_day_ok"] = (raw["is_day"] == 1).astype(int)
    temp_ok  = raw["temperature_2m"].between(COLD_C, HOT_C)
    uv_ok    = raw["uv_index_est"] <= UV_MAX
    prec_ok  = raw["precipitation"] <= RAIN_MAX_MM_H
    cloud_ok = raw["cloud_cover"].fillna(0) <= OVERCAST_MAX_PCT
    humid_ok = raw["relative_humidity_2m"].fillna(0) <= HUMIDITY_MAX_PCT
    raw["stay"] = ((raw["is_day"] == 1) & temp_ok & uv_ok & prec_ok & cloud_ok & humid_ok).astype(int)

    # Aggregate per (ts_local, region) across the 3 sample points.
    agg = (
        raw.groupby(["ts_local", "region"], as_index=False)
        .agg(
            stay_outside_pts=("stay", "sum"),
            ok_day=("is_day_ok", "max"),
            temperature_2m=("temperature_2m", "mean"),
            uv_index_est=("uv_index_est", "mean"),
            precipitation=("precipitation", "mean"),
            cloud_cover=("cloud_cover", "mean"),
            relative_humidity_2m=("relative_humidity_2m", "mean"),
            us_aqi=("us_aqi", "mean"),
            wind_gusts_10m=("wind_gusts_10m", "max"),
        )
    )
    agg["month"] = pd.to_datetime(agg["ts_local"]).dt.strftime("%Y-%m")

    count = 0
    for month, grp in agg.groupby("month"):
        # Pivot to {ts: {region: {...metric: val}}}
        by_ts: dict = {}
        for _, r in grp.iterrows():
            ts = r["ts_local"].isoformat() if hasattr(r["ts_local"], "isoformat") else str(r["ts_local"])
            slot = by_ts.setdefault(ts, {"ts": ts})
            slot[r["region"]] = {
                "stay_outside_pts": int(r["stay_outside_pts"]),
                "ok_day":           int(r["ok_day"]),
                "temperature_2m":   _clean(r["temperature_2m"]),
                "uv_index_est":     _clean(r["uv_index_est"]),
                "precipitation":    _clean(r["precipitation"]),
                "cloud_cover":      _clean(r["cloud_cover"]),
                "relative_humidity_2m": _clean(r["relative_humidity_2m"]),
                "us_aqi":           _clean(r["us_aqi"]),
                "wind_gusts_10m":   _clean(r["wind_gusts_10m"]),
            }
        rows = sorted(by_ts.values(), key=lambda x: x["ts"])
        out_f = hourly_dir / f"{month}.json"
        out_f.write_text(json.dumps({"month": month, "rows": rows}, separators=(",", ":")))
        count += 1
    return count


def export_payload(tag: str, narratives: dict | None = None) -> None:
    grains = {g: export_grain(tag, g) for g in ("yearly", "monthly", "daily")}
    # Only publish regions that actually have data in the daily rollup for this
    # tag — keeps the picker honest (no empty traces, no broken chips).
    present = set(grains["daily"]["regions"].keys())
    region_registry = {k: v for k, v in REGIONS.items() if k in present}
    region_order = [r for r in REGION_ORDER if r in present]
    region_label = {k: v for k, v in REGION_LABEL.items() if k in present}
    profiles_payload = [
        {
            "id": p.id,
            "name": p.name,
            "label": p.label,
            "desc": p.desc,
            "rule": {
                "temp_min_c": p.cold_c, "temp_max_c": p.hot_c,
                "temp_min_f": round(p.cold_c * 9 / 5 + 32),
                "temp_max_f": round(p.hot_c * 9 / 5 + 32),
                "uv_max": p.uv_max,
                "rain_max_mm_h": p.rain_max_mm_h,
                "cloud_max_pct": p.overcast_max_pct,
                "humidity_max_pct": p.humidity_max_pct,
                "aqi_max": getattr(p, "aqi_max", None),
            },
        }
        for p in PROFILES
    ]
    default_profile = next(p for p in profiles_payload if p["id"] == DEFAULT_PROFILE_ID)
    payload = {
        "tag": tag,
        "pubdate": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "metrics": METRICS,
        "regions": region_label,
        "region_registry": region_registry,
        "region_order": region_order,
        "grains": grains,
        "summaries": narratives or {},
        "profiles": profiles_payload,
        "default_profile": DEFAULT_PROFILE_ID,
        # Legacy 'rule' kept for back-compat with already-cached frontend bundles.
        "rule": default_profile["rule"],
    }
    target = OUT / f"{tag}.json"
    target.write_text(json.dumps(payload, separators=(",", ":")))
    size_kb = target.stat().st_size / 1024
    # Count buckets from the first region found (in case some regions missing).
    first = next((p["regions"][next(iter(p["regions"]))]["x"] for p in payload["grains"].values() if p["regions"]), [])
    n = len(first)
    print(f"wrote {target} — {size_kb:.1f} KB, {n} daily buckets/region")


def load_summaries() -> dict:
    """Load any pre-generated narrative summaries (LLM-written one-liners)."""
    sums_dir = ROOT / "data" / "summaries"
    out = {}
    monthly = sums_dir / "monthly_last10y.json"
    if monthly.exists():
        out["monthly"] = json.loads(monthly.read_text())
    range_overview = sums_dir / "range_overview.json"
    if range_overview.exists():
        out["range_overview"] = json.loads(range_overview.read_text())
    region_profiles = sums_dir / "region_profiles.json"
    if region_profiles.exists():
        out["region_profiles"] = json.loads(region_profiles.read_text())
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    narratives = load_summaries()
    for tag in ("last1m", "last1y", "last5y", "last10y", "last30y"):
        src = CURATED / f"region_daily_{tag}.parquet"
        if not src.exists():
            print(f"skip {tag}: {src.name} not on disk")
            continue
        try:
            export_payload(tag, narratives)
        except Exception as e:
            print(f"export {tag} failed: {e}")

    # Hourly monthlies: only for the longest tag we have (saves disk).
    for tag in ("last30y", "last10y", "last5y"):
        if (CURATED / f"hourly_{tag}.parquet").exists():
            n_months = export_hourly_months(tag)
            print(f"wrote {n_months} hourly monthly files from {tag} to {OUT / 'hourly'}")
            break


if __name__ == "__main__":
    main()
