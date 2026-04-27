"""Refresh the (single) trailing AQ chunk per point.

Air-quality archive data lives in ONE chunk per point starting at the
common AQ-coverage start date (2022-09-01). Every week we delete the
existing chunk and re-fetch it from start through today-LAG_DAYS.
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from etl.points import POINTS

ROOT = Path(__file__).resolve().parents[1]
RAW_AQ_BASE = ROOT / "data" / "raw" / "open_meteo_aq"
TAG = "last10y"
LAG_DAYS = 5  # CAMS AQ archive lag

CHUNK_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.parquet$")


def latest_chunk(pdir: Path):
    best = None
    for f in pdir.glob("*.parquet"):
        m = CHUNK_RE.match(f.name)
        if not m:
            continue
        s, e = date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))
        if best is None or e > best[2]:
            best = (f, s, e)
    return best


def main() -> int:
    target = date.today() - timedelta(days=LAG_DAYS)
    chunk_start: date | None = None
    deleted: list[str] = []

    for p in POINTS:
        pdir = RAW_AQ_BASE / p.region / p.id / TAG
        if not pdir.exists():
            print(f"  warn: no AQ dir for {p.id} (skipped)")
            continue
        latest = latest_chunk(pdir)
        if latest is None:
            print(f"  warn: no AQ chunk for {p.id} (skipped)")
            continue
        fpath, cstart, cend = latest
        if cend >= target:
            print(f"  ok    {p.id}: AQ chunk through {cend} (target {target})")
            continue
        if chunk_start is None:
            chunk_start = cstart
        elif chunk_start != cstart:
            print(f"  warn: {p.id} AQ chunk starts {cstart}, expected {chunk_start}; skipping")
            continue
        fpath.unlink()
        deleted.append(p.id)
        print(f"  refresh {p.id}: AQ {cend} → {target}")

    if not deleted:
        print("\nnothing to refresh — all AQ chunks already cover the latest available data")
        return 0
    if chunk_start is None:
        print("nothing fetched", file=sys.stderr)
        return 1

    print(f"\nrunning open_meteo_aq for {len(deleted)} points: {chunk_start} → {target}")
    cp = subprocess.run(
        ["uv", "run", "python", "-m", "etl.sources.open_meteo_aq",
         "--start", chunk_start.isoformat(),
         "--end",   target.isoformat(),
         "--tag",   TAG],
        cwd=str(ROOT),
    )
    return cp.returncode


if __name__ == "__main__":
    sys.exit(main())
