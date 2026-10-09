"""Merge raw Open-Meteo parquet files into a single curated hourly table.

Usage:
  uv run python -m etl.curate --tag sample_last30
  uv run python -m etl.curate --tag full
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from etl.points import POINTS

ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "data" / "raw" / "open_meteo"
RAW_AQ_ROOT = ROOT / "data" / "raw" / "open_meteo_aq"
CURATED_DIR = ROOT / "data" / "curated"


def _solar_altitude_deg(lat: float, lon: float, ts_utc: pd.Series) -> np.ndarray:
    """Rough solar altitude angle in degrees. NOAA simplified algorithm, no refraction."""
    doy = ts_utc.dt.dayofyear.to_numpy()
    hour_utc = ts_utc.dt.hour.to_numpy() + ts_utc.dt.minute.to_numpy() / 60.0
    frac_year = 2 * math.pi / 365.0 * (doy - 1 + (hour_utc - 12) / 24.0)
    decl = (
        0.006918
        - 0.399912 * np.cos(frac_year)
        + 0.070257 * np.sin(frac_year)
        - 0.006758 * np.cos(2 * frac_year)
        + 0.000907 * np.sin(2 * frac_year)
        - 0.002697 * np.cos(3 * frac_year)
        + 0.00148 * np.sin(3 * frac_year)
    )
    eqtime = 229.18 * (
        0.000075
        + 0.001868 * np.cos(frac_year)
        - 0.032077 * np.sin(frac_year)
        - 0.014615 * np.cos(2 * frac_year)
        - 0.040849 * np.sin(2 * frac_year)
    )
    solar_time_min = hour_utc * 60 + eqtime + 4 * lon
    hour_angle = np.deg2rad((solar_time_min / 4.0) - 180.0)
    lat_r = math.radians(lat)
    sin_alt = np.sin(lat_r) * np.sin(decl) + np.cos(lat_r) * np.cos(decl) * np.cos(hour_angle)
    return np.rad2deg(np.arcsin(np.clip(sin_alt, -1, 1)))


def _uv_index_estimate(df: pd.DataFrame, lat: float, lon: float) -> np.ndarray:
    """Proxy UV index from solar geometry + cloud attenuation.

    UVI_clear ≈ 12 * sin(altitude)^1.7 is a standard mid-latitude sea-level envelope
    (Madronich-style). Cloud attenuation: overcast drops UV to ~25% of clear-sky.
    ERA5 does not publish UV; swap in OpenUV/NOAA Brewer for measured values later.
    """
    alt_deg = _solar_altitude_deg(lat, lon, df["ts_utc"])
    sin_alt = np.sin(np.deg2rad(np.clip(alt_deg, 0, 90)))
    uvi_clear = 12.0 * np.power(np.maximum(sin_alt, 0.0), 1.7)
    cloud_frac = df["cloud_cover"].fillna(0).to_numpy() / 100.0
    cloud_factor = 1.0 - 0.75 * cloud_frac
    uvi = uvi_clear * cloud_factor
    uvi = np.where(alt_deg <= 0, 0.0, uvi)
    return np.clip(uvi, 0, 14)


def _load_aq_frame(tag: str) -> pd.DataFrame | None:
    """Load all AQ parquets across points; returns df keyed on (point, ts_utc).

    Returns None if the AQ tree doesn't exist yet (legacy / first-run scenarios).
    """
    aq_frames: list[pd.DataFrame] = []
    for p in POINTS:
        pdir = RAW_AQ_ROOT / p.region / p.id / tag
        if not pdir.exists():
            continue
        for fpath in sorted(pdir.glob("*.parquet")):
            aq_frames.append(pd.read_parquet(fpath, columns=["point", "ts_utc", "us_aqi", "pm2_5", "pm10"]))
    if not aq_frames:
        return None
    aq = pd.concat(aq_frames, ignore_index=True)
    aq["ts_utc"] = pd.to_datetime(aq["ts_utc"], utc=True)
    return aq.drop_duplicates(["point", "ts_utc"])


def build(tag: str) -> Path:
    frames: list[pd.DataFrame] = []
    for p in POINTS:
        pdir = RAW_ROOT / p.region / p.id / tag
        if not pdir.exists():
            print(f"  warn: no data for {p.id} tag={tag}")
            continue
        for fpath in sorted(pdir.glob("*.parquet")):
            df = pd.read_parquet(fpath)
            df["uv_index_est"] = _uv_index_estimate(df, p.lat, p.lon)
            frames.append(df)

    if not frames:
        raise SystemExit(f"no raw data found for tag={tag}")

    full = pd.concat(frames, ignore_index=True)
    full["ts_utc"] = pd.to_datetime(full["ts_utc"], utc=True)
    full = full.drop_duplicates(["point", "ts_utc"])

    # Left-join air-quality on (point, ts_utc). AQ archive only goes back to
    # ~Aug 2022 globally — pre-coverage rows get NULL us_aqi/pm columns,
    # which the classifier treats as "no constraint" (no false negatives).
    aq = _load_aq_frame(tag)
    if aq is not None:
        full = full.merge(aq, on=["point", "ts_utc"], how="left")
        n_with_aqi = full["us_aqi"].notna().sum()
        print(f"  AQ join: {n_with_aqi:,}/{len(full):,} rows have us_aqi")
    else:
        full["us_aqi"] = pd.NA
        full["pm2_5"] = pd.NA
        full["pm10"] = pd.NA
        print("  AQ join: no AQ data on disk (skipped)")
    # Each point's own local wall-clock time, stored tz-naive (one dtype for the frame).
    tz_by_point = {p.id: p.timezone for p in POINTS}
    ts_local = pd.Series(pd.NaT, index=full.index, dtype="datetime64[ns]")
    for pid, tz in tz_by_point.items():
        mask = full["point"] == pid
        if mask.any():
            ts_local[mask] = full.loc[mask, "ts_utc"].dt.tz_convert(tz).dt.tz_localize(None).astype("datetime64[ns]")
    full["ts_local"] = ts_local
    full["year"] = full["ts_local"].dt.year.astype("int16")
    full["month"] = full["ts_local"].dt.month.astype("int8")
    full["day"] = full["ts_local"].dt.day.astype("int8")
    full["hour_of_day"] = full["ts_local"].dt.hour.astype("int8")
    full["dow"] = full["ts_local"].dt.dayofweek.astype("int8")

    lead = ["region", "point", "ts_utc", "ts_local", "year", "month", "day", "hour_of_day", "dow"]
    other = [c for c in full.columns if c not in lead]
    full = full[lead + other].sort_values(["region", "point", "ts_utc"]).reset_index(drop=True)

    CURATED_DIR.mkdir(parents=True, exist_ok=True)
    out = CURATED_DIR / f"hourly_{tag}.parquet"
    full.to_parquet(out, index=False, compression="zstd")

    # Quick DuckDB sanity checks.
    con = duckdb.connect()
    summary = con.execute(
        f"""
        select region, point,
               count(*) as rows,
               min(ts_utc) as first_ts,
               max(ts_utc) as last_ts,
               count(*) filter (where temperature_2m is null) as null_temp
          from read_parquet('{out}')
         group by 1,2
         order by 1,2
        """
    ).df()
    print(summary.to_string(index=False))
    print(f"\nwrote {out}  ({out.stat().st_size/1e6:.2f} MB, {len(full):,} rows)")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True, help="e.g. sample_last30 or full")
    args = parser.parse_args()
    build(args.tag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
