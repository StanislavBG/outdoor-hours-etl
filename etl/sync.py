"""Gap-aware raw-data sync for ERA5 weather and CAMS air quality.

For every point and source, find the dates in the expected window that have no
raw chunk on disk and fetch only those ranges, one <start>_<end>.parquet per
Task (<= PIECE_DAYS days). Resumable: rerun after a HALT or --max-requests.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import etl.sources.open_meteo as om
import etl.sources.open_meteo_aq as aq
from etl.points import POINTS

TAG = "last10y"
WEATHER_START = date(2016, 4, 20)
AQ_START = date(2022, 9, 1)
LAG_DAYS = 5  # ERA5 reanalysis lag
PIECE_DAYS = 365

CHUNK_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.parquet$")
SOURCES = ("weather", "aq")


@dataclass(frozen=True)
class Task:
    source: str
    point: object
    start: date
    end: date


def _raw_root(source: str) -> Path:
    # Read at call time so tests can monkeypatch RAW_DIR.
    return om.RAW_DIR if source == "weather" else aq.RAW_DIR


def _window_start(source: str) -> date:
    return WEATHER_START if source == "weather" else AQ_START


def covered_ranges(pdir: Path) -> list[tuple[date, date]]:
    out: list[tuple[date, date]] = []
    if not pdir.is_dir():
        return out
    for f in pdir.iterdir():
        m = CHUNK_RE.match(f.name)
        if not m:
            continue
        try:
            out.append((date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))))
        except ValueError:
            continue
    return sorted(out)


def missing_ranges(covered, start: date, end: date) -> list[tuple[date, date]]:
    one = timedelta(days=1)
    gaps: list[tuple[date, date]] = []
    cur = start
    for s, e in sorted(covered):
        if e < cur:
            continue
        if s > end:
            break
        if s > cur:
            gaps.append((cur, s - one))
        cur = max(cur, e + one)
        if cur > end:
            break
    if cur <= end:
        gaps.append((cur, end))
    return gaps


def plan_tasks(points, sources, target: date) -> list[Task]:
    tasks: list[Task] = []
    for source in sources:
        for p in points:
            pdir = _raw_root(source) / p.region / p.id / TAG
            for gs, ge in missing_ranges(covered_ranges(pdir), _window_start(source), target):
                cur = gs
                while cur <= ge:
                    nxt = min(cur + timedelta(days=PIECE_DAYS - 1), ge)
                    tasks.append(Task(source, p, cur, nxt))
                    cur = nxt + timedelta(days=1)
    return tasks


def _fmt(t: Task) -> str:
    return f"{t.source} {t.point.id} {t.start}..{t.end}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m etl.sync", description=__doc__)
    ap.add_argument("--points", nargs="*", default=None, help="point ids (default: all)")
    ap.add_argument("--source", choices=["weather", "aq", "all"], default="all")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, fetch nothing")
    ap.add_argument("--check", action="store_true", help="exit 1 and list gaps if any, never fetches")
    ap.add_argument("--max-requests", type=int, default=None, help="stop cleanly after N fetches")
    ap.add_argument("--delay", type=float, default=8.0, help="seconds between requests")
    ap.add_argument("--target", type=date.fromisoformat, default=None,
                    help="YYYY-MM-DD (default today - LAG_DAYS)")
    args = ap.parse_args(argv)

    target = args.target or (date.today() - timedelta(days=LAG_DAYS))
    points = list(POINTS)
    if args.points:
        known = {p.id for p in POINTS}
        unknown = [i for i in args.points if i not in known]
        if unknown:
            print(f"unknown point id(s): {', '.join(unknown)}", file=sys.stderr)
            return 2
        points = [p for p in POINTS if p.id in set(args.points)]
    sources = SOURCES if args.source == "all" else (args.source,)

    tasks = plan_tasks(points, sources, target)

    if args.check:
        if tasks:
            print(f"{len(tasks)} gap piece(s):")
            for t in tasks:
                print(f"  {_fmt(t)}")
            return 1
        print("no gaps")
        return 0

    if args.dry_run:
        for t in tasks:
            print(f"  plan {_fmt(t)}")
        print(f"planned {len(tasks)}, fetched 0, remaining {len(tasks)}")
        return 0

    fetched = 0
    for t in tasks:
        if args.max_requests is not None and fetched >= args.max_requests:
            break
        download = om.download if t.source == "weather" else aq.download
        try:
            download(t.point, t.start, t.end, tag=TAG,
                     max_days_per_call=PIECE_DAYS, inter_call_delay_s=args.delay)
        except Exception as e:
            print(f"HALT: {_fmt(t)}: {e} — rerun to resume")
            return 1
        fetched += 1

    print(f"planned {len(tasks)}, fetched {fetched}, remaining {len(tasks) - fetched}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
