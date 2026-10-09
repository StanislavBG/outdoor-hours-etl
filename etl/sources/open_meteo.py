"""Open-Meteo ERA5 historical archive downloader.

Two download modes:
  - date-range (used by --sample or explicit --start/--end): one file per point for the range.
  - reverse-monthly (used by --full): iterate months from most-recent backwards; within
    each month fetch ALL points before moving to the prior month. This gives you
    cross-county analytics that grow coherently month by month.

Idempotent: skips files already on disk.
"""
from __future__ import annotations

import argparse
import calendar
import sys
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

import httpx
import pandas as pd
import yaml

from etl.points import POINTS, Point
from etl.sources import _client
from etl.sources._client import FetchBodyError, RateLimitExhausted  # noqa: F401  (re-exported)

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "open_meteo"
VARS_YAML = ROOT / "data" / "variables.yaml"
ENDPOINT = "https://archive-api.open-meteo.com/v1/archive"


def load_hourly_vars() -> list[str]:
    manifest = yaml.safe_load(VARS_YAML.read_text())
    return [v["name"] for v in manifest["hourly_variables"]]


def _fetch_df(client: httpx.Client, point: Point, start: date, end: date, variables: list[str]) -> pd.DataFrame:
    params = {
        "latitude": point.lat,
        "longitude": point.lon,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": ",".join(variables),
        "timezone": "UTC",
        "timeformat": "unixtime",
        "wind_speed_unit": "ms",
    }
    payload = _client.fetch_json(client, ENDPOINT, params)
    return _client.to_dataframe(
        payload, point, {"lat": point.lat, "lon": point.lon, "elevation_m": point.elevation_m}
    )


# -----------------------------------------------------------------------------
# Date-range mode (small fixed window, e.g. sample_last30)
# -----------------------------------------------------------------------------

def download(
    point: Point,
    start: date,
    end: date,
    *,
    max_days_per_call: int = 1830,
    tag: str = "range",
    overwrite: bool = False,
    inter_call_delay_s: float = 1.5,
) -> list[Path]:
    variables = load_hourly_vars()
    out_dir = RAW_DIR / point.region / point.id / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client() as client:
        return _client.download_chunks(
            client, point, start, end, out_dir,
            max_days=max_days_per_call, overwrite=overwrite, delay_s=inter_call_delay_s,
            fetch=lambda cs, ce: _fetch_df(client, point, cs, ce, variables),
        )


# -----------------------------------------------------------------------------
# Reverse-monthly mode (newest first, all-points-per-month)
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class MonthWindow:
    year: int
    month: int
    start: date
    end: date

    @property
    def tag(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


def iter_months_reverse(earliest: date, latest: date) -> Iterable[MonthWindow]:
    """Yield MonthWindow from latest month backwards to earliest (inclusive).

    Clips partial months to the [earliest, latest] bounds.
    """
    y, m = latest.year, latest.month
    earliest_y, earliest_m = earliest.year, earliest.month
    while (y, m) >= (earliest_y, earliest_m):
        last_day = calendar.monthrange(y, m)[1]
        mstart = date(y, m, 1)
        mend = date(y, m, last_day)
        if mstart < earliest:
            mstart = earliest
        if mend > latest:
            mend = latest
        yield MonthWindow(y, m, mstart, mend)
        if m == 1:
            y, m = y - 1, 12
        else:
            m -= 1


def backfill_reverse_monthly(
    points: list[Point],
    earliest: date,
    latest: date,
    *,
    tag: str = "full",
    overwrite: bool = False,
    inter_call_delay_s: float = 2.0,
) -> None:
    """For each month from latest back to earliest, fetch every point before
    moving to the prior month.

    On-disk layout:
        data/raw/open_meteo/<region>/<point>/<tag>/<YYYY-MM>.parquet
    """
    variables = load_hourly_vars()
    months = list(iter_months_reverse(earliest, latest))
    total_calls = len(months) * len(points)
    done = 0
    start_time = time.time()

    print(f"reverse-monthly: {latest} → {earliest}  "
          f"months={len(months)}  points={len(points)}  total_calls={total_calls}", flush=True)

    with httpx.Client() as client:
        for mw in months:
            month_label = f"{mw.year}-{mw.month:02d}"
            print(f"\n== {month_label}  ({mw.start} → {mw.end}) ==", flush=True)
            for p in points:
                out_dir = RAW_DIR / p.region / p.id / tag
                out_dir.mkdir(parents=True, exist_ok=True)
                fpath = out_dir / f"{mw.tag}.parquet"
                done += 1
                if fpath.exists() and not overwrite:
                    print(f"  [{done}/{total_calls}] skip {p.id} {month_label}", flush=True)
                    continue
                elapsed = time.time() - start_time
                rate = done / elapsed if elapsed > 0 else 0
                eta_min = (total_calls - done) / rate / 60 if rate > 0 else float("nan")
                print(f"  [{done}/{total_calls}] fetch {p.id} {month_label}  "
                      f"elapsed={elapsed/60:.1f}m  eta={eta_min:.1f}m", flush=True)
                df = _fetch_df(client, p, mw.start, mw.end, variables)
                _client.write_parquet_atomic(df, fpath)
                time.sleep(inter_call_delay_s)
    print("\ndone.", flush=True)


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=date.fromisoformat, help="YYYY-MM-DD (inclusive)")
    parser.add_argument("--end", type=date.fromisoformat, help="YYYY-MM-DD (inclusive)")
    parser.add_argument("--sample", action="store_true", help="Shortcut: last 30 days, one file per point")
    parser.add_argument("--full", action="store_true",
                        help="Reverse-monthly backfill 1940-01 → today-3, all points per month")
    parser.add_argument("--tag", default=None)
    parser.add_argument("--points", nargs="*", help="Subset of point ids; default = all")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Seconds to sleep between successful calls")
    args = parser.parse_args()

    points = POINTS if not args.points else [p for p in POINTS if p.id in set(args.points)]

    if args.sample:
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=29)
        tag = args.tag or "sample_last30"
        print(f"sample: {start} → {end}  tag={tag}  points={[p.id for p in points]}")
        for p in points:
            download(p, start, end, tag=tag, overwrite=args.overwrite,
                     inter_call_delay_s=args.delay)
        return 0

    if args.full:
        earliest = date(1940, 1, 1)
        latest = date.today() - timedelta(days=3)
        tag = args.tag or "full"
        backfill_reverse_monthly(points, earliest, latest, tag=tag,
                                 overwrite=args.overwrite,
                                 inter_call_delay_s=args.delay)
        return 0

    if not (args.start and args.end):
        print("error: provide --sample, --full, or --start/--end", file=sys.stderr)
        return 2

    tag = args.tag or f"{args.start.isoformat()}_{args.end.isoformat()}"
    print(f"range: {args.start} → {args.end}  tag={tag}  points={[p.id for p in points]}")
    for p in points:
        download(p, args.start, args.end, tag=tag, overwrite=args.overwrite,
                 inter_call_delay_s=args.delay)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
