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
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from classifier.hourly import region_hourly
from classifier.personal import PROFILES, DEFAULT_PROFILE_ID
from etl.catalog import METRICS, X_COL, json_scalar
from etl.points import REGIONS

ROOT = Path(__file__).resolve().parents[1]
CURATED = ROOT / "data" / "curated"
OUT = Path(os.environ.get("OUTDOOR_HOURS_OUT", "/home/bilko/Projects/Bilko/public/outdoor-hours"))

REGION_LABEL = {k: v["label"] for k, v in REGIONS.items()}
REGION_ORDER = list(REGIONS.keys())

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
            xs = [json_scalar(v) for v in grp[x_col]]
        series = {}
        for m in METRICS:
            if m["key"] in grp.columns:
                series[m["key"]] = [json_scalar(v) for v in grp[m["key"]]]
        # Per-profile good-hours + pct-daylight series for the global toggle.
        for p in PROFILES:
            for col in (f"stay_outside_{p.id}_hours", f"pct_daytime_outside_{p.id}"):
                if col in grp.columns:
                    series[col] = [json_scalar(v) for v in grp[col]]
        out["regions"][region] = {
            "label": REGION_LABEL.get(region, region),
            "x": xs,
            "series": series,
        }
    return out


_HOURLY_COLS = (
    "ts_local", "region", "is_day", "temperature_2m", "uv_index_est", "precipitation",
    "cloud_cover", "relative_humidity_2m", "wind_gusts_10m", "us_aqi",
)
_HOURLY_METRICS = (
    "ok_day", "temperature_2m", "uv_index_est", "precipitation", "cloud_cover",
    "relative_humidity_2m", "us_aqi", "wind_gusts_10m",
)
_REGION_FIELDS = ("stay_outside_pts", "n_points") + _HOURLY_METRICS


def export_hourly_months(tag: str) -> int:
    """Write one JSON per YYYY-MM with all hourly rows for that month, regions paired.
    Enables lazy drill-down on the public site without shipping the whole hourly parquet.
    """
    import duckdb
    hourly_path = CURATED / f"hourly_{tag}.parquet"
    if not hourly_path.exists():
        print(f"skip hourly export: {hourly_path} not found")
        return 0
    hourly_dir = OUT / "hourly"
    hourly_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    have = {r[0] for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(hourly_path)]).fetchall()}
    cols = ", ".join(c for c in _HOURLY_COLS if c in have)
    raw = con.execute(f"SELECT {cols} FROM read_parquet(?)", [str(hourly_path)]).fetchdf()

    agg = region_hourly(raw)
    agg["ok_day"] = agg["ok_day"].astype(int)
    metrics = agg[list(_HOURLY_METRICS)].astype(object)
    agg[list(_HOURLY_METRICS)] = metrics.where(metrics.notna(), None)
    # Format each distinct timestamp once; regions share ts values.
    codes, uniq = pd.factorize(agg["ts_local"])
    agg["ts"] = uniq.strftime("%Y-%m-%dT%H:%M:%S").to_numpy()[codes]
    agg["month"] = agg["ts"].str.slice(0, 7)
    agg = agg.sort_values(["ts", "region"], kind="stable")

    count = 0
    for month, grp in agg.groupby("month", sort=True):
        rows: list[dict] = []
        last_ts = None
        for ts, region, rec in zip(grp["ts"], grp["region"], grp[list(_REGION_FIELDS)].to_dict("records")):
            if ts != last_ts:
                rows.append({"ts": ts})
                last_ts = ts
            rows[-1][region] = rec
        (hourly_dir / f"{month}.json").write_text(
            json.dumps({"month": month, "rows": rows}, separators=(",", ":")))
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
    # Count buckets from the first region found in the daily grain.
    daily_regions = payload["grains"]["daily"]["regions"]
    n = len(next(iter(daily_regions.values()))["x"]) if daily_regions else 0
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
    failures: list[str] = []
    for tag in ("last1m", "last1y", "last5y", "last10y", "last30y"):
        src = CURATED / f"region_daily_{tag}.parquet"
        if not src.exists():
            print(f"skip {tag}: {src.name} not on disk")
            continue
        try:
            export_payload(tag, narratives)
        except Exception as e:
            print(f"export {tag} failed: {e}")
            failures.append(tag)

    # Hourly monthlies: only for the longest tag we have (saves disk).
    for tag in ("last30y", "last10y", "last5y"):
        if (CURATED / f"hourly_{tag}.parquet").exists():
            n_months = export_hourly_months(tag)
            print(f"wrote {n_months} hourly monthly files from {tag} to {OUT / 'hourly'}")
            break

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
