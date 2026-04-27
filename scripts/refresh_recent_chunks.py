"""Refresh only the trailing raw chunk for each point.

Open-Meteo ERA5 lags real-time by ~5 days. Each point's raw data is split into
~5-year chunks named "<start>_<end>.parquet". The historical chunks never
change; only the one touching "now" needs to grow weekly.

Strategy:
  1. For every point, find its chronologically latest chunk file.
  2. If the file's end-date is older than (today - LAG_DAYS), delete it and
     re-fetch from its start through today-LAG_DAYS so the new file replaces
     it cleanly (no orphaned overlapping files for curate to dedupe).
  3. After marking all points, run a single etl.sources.open_meteo invocation
     covering that date range — it iterates all points, skipping intact
     historical chunks and only writing the new trailing chunk per point.
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from etl.points import POINTS

ROOT = Path(__file__).resolve().parents[1]
RAW_BASE = ROOT / "data" / "raw" / "open_meteo"
TAG = "last10y"
LAG_DAYS = 5  # ERA5 reanalysis lag

CHUNK_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.parquet$")


def latest_chunk(pdir: Path) -> tuple[Path, date, date] | None:
    best: tuple[Path, date, date] | None = None
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
        pdir = RAW_BASE / p.region / p.id / TAG
        if not pdir.exists():
            print(f"  warn: no raw dir for {p.id} (skipped)")
            continue
        latest = latest_chunk(pdir)
        if latest is None:
            print(f"  warn: no chunk found for {p.id} (skipped)")
            continue
        fpath, cstart, cend = latest
        if cend >= target:
            print(f"  ok    {p.id}: latest chunk through {cend} (target {target})")
            continue
        if chunk_start is None:
            chunk_start = cstart
        elif chunk_start != cstart:
            print(f"  warn: {p.id} chunk starts {cstart}, expected {chunk_start}; skipping for safety")
            continue
        fpath.unlink()
        deleted.append(p.id)
        print(f"  refresh {p.id}: {cend} → {target} (deleted {fpath.name})")

    if not deleted:
        print("\nnothing to refresh — all chunks already cover the latest available data")
        return 0

    if chunk_start is None:
        print("nothing fetched", file=sys.stderr)
        return 1

    print(f"\nrunning open_meteo for {len(deleted)} points: {chunk_start} → {target}")
    cp = subprocess.run(
        ["uv", "run", "python", "-m", "etl.sources.open_meteo",
         "--start", chunk_start.isoformat(),
         "--end",   target.isoformat(),
         "--tag",   TAG],
        cwd=str(ROOT),
    )
    return cp.returncode


if __name__ == "__main__":
    sys.exit(main())
