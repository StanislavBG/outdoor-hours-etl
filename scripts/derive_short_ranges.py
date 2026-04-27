"""Derive `last1m`, `last1y`, `last5y` tagged parquets from `last10y` curated hourly.

The curate step writes hourly_<tag>.parquet; precompute then rolls up daily/monthly/yearly.
This script slices subsets off the last10y hourly, writes new hourly_last{N}.parquet,
then re-runs precompute for each derived tag so the dashboard sees them as first-class datasets.

`last1m` is the prior complete calendar month (e.g. on 2026-04-24 → March 2026).
`last1y` / `last5y` are rolling windows of N years ending at the latest hour available.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from etl.precompute import build as precompute_build

ROOT = Path(__file__).resolve().parents[1]
CURATED = ROOT / "data" / "curated"

ROLLING_YEARS = {
    "last1y": 1,
    "last5y": 5,
}


def _prior_calendar_month(today: date) -> tuple[pd.Timestamp, pd.Timestamp]:
    first_of_this = pd.Timestamp(today.year, today.month, 1, tz="UTC")
    last_of_prior = first_of_this - pd.Timedelta(seconds=1)
    first_of_prior = pd.Timestamp(last_of_prior.year, last_of_prior.month, 1, tz="UTC")
    return first_of_prior, first_of_this  # [first_of_prior, first_of_this)


def derive(src_tag: str = "last10y") -> None:
    src = CURATED / f"hourly_{src_tag}.parquet"
    if not src.exists():
        raise SystemExit(f"source not found: {src}")
    full = pd.read_parquet(src)
    full["ts_utc"] = pd.to_datetime(full["ts_utc"], utc=True)
    end = full["ts_utc"].max()

    for tag, years in ROLLING_YEARS.items():
        cutoff = end - pd.Timedelta(days=365 * years)
        window = full[full["ts_utc"] > cutoff].reset_index(drop=True)
        out = CURATED / f"hourly_{tag}.parquet"
        window.to_parquet(out, index=False, compression="zstd")
        print(f"{tag}: {len(window):>7,} rows ({window['ts_utc'].min().date()} → {window['ts_utc'].max().date()}) → {out.name}")
        precompute_build(tag)

    # last1m — prior complete calendar month, anchored to today's UTC date.
    start_m, end_m_excl = _prior_calendar_month(date.today())
    window = full[(full["ts_utc"] >= start_m) & (full["ts_utc"] < end_m_excl)].reset_index(drop=True)
    out = CURATED / "hourly_last1m.parquet"
    window.to_parquet(out, index=False, compression="zstd")
    print(f"last1m: {len(window):>7,} rows ({start_m.date()} → {(end_m_excl - pd.Timedelta(days=1)).date()}) → {out.name}")
    precompute_build("last1m")


if __name__ == "__main__":
    derive()
