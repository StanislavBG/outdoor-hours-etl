"""Open-Meteo Air Quality archive downloader.

Mirrors etl.sources.open_meteo (ERA5 weather) but hits the AQ endpoint and
fetches us_aqi + pm2_5 + pm10. CAMS-backed AQ archive coverage is patchy
before mid-2022 for North American points, so we fetch only from
2022-09-01 (clean month boundary, confirmed available globally).

On-disk layout:
    data/raw/open_meteo_aq/<region>/<point>/last10y/<start>_<end>.parquet
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx
import pandas as pd

from etl.points import POINTS, Point
from etl.sources import _client

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "open_meteo_aq"
ENDPOINT = "https://air-quality-api.open-meteo.com/v1/air-quality"

HOURLY_VARS = ["us_aqi", "pm2_5", "pm10"]


def _fetch_df(client: httpx.Client, point: Point, start: date, end: date) -> pd.DataFrame:
    params = {
        "latitude": point.lat,
        "longitude": point.lon,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": ",".join(HOURLY_VARS),
        "timezone": "UTC",
        "timeformat": "unixtime",
    }
    return _client.to_dataframe(_client.fetch_json(client, ENDPOINT, params), point)


def download(
    point: Point,
    start: date,
    end: date,
    *,
    max_days_per_call: int = 1830,
    tag: str = "last10y",
    overwrite: bool = False,
    inter_call_delay_s: float = 2.0,
) -> list[Path]:
    out_dir = RAW_DIR / point.region / point.id / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client() as client:
        return _client.download_chunks(
            client, point, start, end, out_dir,
            max_days=max_days_per_call, overwrite=overwrite, delay_s=inter_call_delay_s,
            fetch=lambda cs, ce: _fetch_df(client, point, cs, ce),
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=date.fromisoformat, default=date(2022, 9, 1),
                        help="YYYY-MM-DD (inclusive). Default 2022-09-01 (CAMS AQ coverage start).")
    parser.add_argument("--end", type=date.fromisoformat,
                        default=date.today() - timedelta(days=5),
                        help="YYYY-MM-DD (inclusive). Default today-5.")
    parser.add_argument("--tag", default="last10y")
    parser.add_argument("--points", nargs="*", help="Subset of point ids; default = all")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--delay", type=float, default=2.0)
    args = parser.parse_args()

    points = POINTS if not args.points else [p for p in POINTS if p.id in set(args.points)]
    print(f"AQ range: {args.start} → {args.end}  tag={args.tag}  points={len(points)}")
    for p in points:
        download(p, args.start, args.end, tag=args.tag,
                 overwrite=args.overwrite, inter_call_delay_s=args.delay)
    return 0


if __name__ == "__main__":
    sys.exit(main())
