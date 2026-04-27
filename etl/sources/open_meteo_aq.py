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
import time
from datetime import date, timedelta
from pathlib import Path

import httpx
import pandas as pd
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from etl.points import POINTS, Point

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "open_meteo_aq"
ENDPOINT = "https://air-quality-api.open-meteo.com/v1/air-quality"

HOURLY_VARS = ["us_aqi", "pm2_5", "pm10"]


@retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
    stop=stop_after_attempt(8),
    wait=wait_exponential(multiplier=4, min=8, max=300),
    reraise=True,
)
def _fetch(client: httpx.Client, point: Point, start: date, end: date) -> dict:
    params = {
        "latitude": point.lat,
        "longitude": point.lon,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": ",".join(HOURLY_VARS),
        "timezone": "UTC",
        "timeformat": "unixtime",
    }
    r = client.get(ENDPOINT, params=params, timeout=180)
    if r.status_code == 429:
        retry_after = int(r.headers.get("Retry-After", "60"))
        print(f"    429 rate-limited; sleeping {retry_after}s then retrying", flush=True)
        time.sleep(retry_after)
        r.raise_for_status()
    r.raise_for_status()
    return r.json()


def _to_dataframe(payload: dict, point: Point) -> pd.DataFrame:
    h = payload["hourly"]
    df = pd.DataFrame(h)
    df["ts_utc"] = pd.to_datetime(df.pop("time"), unit="s", utc=True)
    df["point"] = point.id
    df["region"] = point.region
    cols = ["region", "point", "ts_utc"] + [c for c in df.columns if c not in {"region", "point", "ts_utc"}]
    return df[cols]


def _day_chunks(start: date, end: date, max_days: int) -> list[tuple[date, date]]:
    out: list[tuple[date, date]] = []
    cur = start
    while cur <= end:
        nxt = min(cur + timedelta(days=max_days - 1), end)
        out.append((cur, nxt))
        cur = nxt + timedelta(days=1)
    return out


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
    written: list[Path] = []
    with httpx.Client() as client:
        for cstart, cend in _day_chunks(start, end, max_days_per_call):
            fname = f"{cstart.isoformat()}_{cend.isoformat()}.parquet"
            fpath = out_dir / fname
            if fpath.exists() and not overwrite:
                print(f"  skip {point.id} {fname} (exists)", flush=True)
                written.append(fpath)
                continue
            print(f"  fetch {point.id} {cstart}..{cend}", flush=True)
            payload = _fetch(client, point, cstart, cend)
            df = _to_dataframe(payload, point)
            df.to_parquet(fpath, index=False, compression="zstd")
            written.append(fpath)
            time.sleep(inter_call_delay_s)
    return written


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
