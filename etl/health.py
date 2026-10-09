"""One-command pipeline health rollup: raw gaps, curated freshness, last weekly run, published bundle.

Exit 0 and print HEALTHY when everything is fine; otherwise print a FAIL line per problem and exit 1.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb

import etl.sources.open_meteo as om
import etl.sources.open_meteo_aq as aq
from etl import sync
from etl.points import POINTS

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BILKO_DIR = Path("/home/bilko/Projects/Bilko/public/outdoor-hours")
CURATED_REL = Path("data/curated/hourly_last10y.parquet")
STATUS_REL = Path("logs/weekly/last_status.json")


def _today() -> date:
    return date.today()


def _raw_gaps(root: Path, points, today: date) -> dict[str, dict[str, int]]:
    """Gap piece count per region and source, with sync pointed at <root>/data/raw."""
    saved = om.RAW_DIR, aq.RAW_DIR
    om.RAW_DIR = root / "data/raw/open_meteo"
    aq.RAW_DIR = root / "data/raw/open_meteo_aq"
    try:
        tasks = sync.plan_tasks(points, sync.SOURCES, today - timedelta(days=sync.LAG_DAYS))
    finally:
        om.RAW_DIR, aq.RAW_DIR = saved
    out = {p.region: {s: 0 for s in sync.SOURCES} for p in points}
    for t in tasks:
        out[t.point.region][t.source] += 1
    return out


def _curated_latest(path: Path) -> dict[str, date]:
    if not path.is_file():
        return {}
    con = duckdb.connect()
    try:
        rows = con.execute(
            "select region, max(ts_utc) from read_parquet(?) group by region", [str(path)]
        ).fetchall()
    finally:
        con.close()
    return {r: ts.date() for r, ts in rows if ts is not None}


def _read_json(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _pubdate_age(raw, today: date) -> int | None:
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (today - dt.astimezone().date()).days


def collect(root: Path, bilko_dir: Path, max_stale_days: int, today: date | None = None,
            points=None) -> dict:
    root, bilko_dir = Path(root), Path(bilko_dir)
    today = today or _today()
    points = list(POINTS if points is None else points)
    failures: list[str] = []

    gaps = _raw_gaps(root, points, today)
    latest = _curated_latest(root / CURATED_REL)
    curated_ok = (root / CURATED_REL).is_file()
    if not curated_ok:
        failures.append(f"curated parquet missing: {root / CURATED_REL}")

    regions: dict[str, dict] = {}
    limit = max_stale_days + sync.LAG_DAYS
    for region in dict.fromkeys(p.region for p in points):
        last = latest.get(region)
        stale = (today - last).days if last else None
        regions[region] = {
            "points": sum(1 for p in points if p.region == region),
            "gaps": gaps[region],
            "latest_ts_utc": last.isoformat() if last else None,
            "days_stale": stale,
        }
        for src, n in gaps[region].items():
            if n:
                failures.append(f"{region}: {n} raw {src} gap piece(s)")
        if curated_ok and (stale is None or stale > limit):
            what = "no curated rows" if stale is None else f"curated data {stale} days stale (limit {limit})"
            failures.append(f"{region}: {what}")

    raw_status = _read_json(root / STATUS_REL)
    status = {k: (raw_status or {}).get(k) for k in ("ts", "ok", "failed_step", "published")}
    if raw_status is None:
        failures.append(f"weekly status missing or unreadable: {root / STATUS_REL}")
    elif raw_status.get("ok") is not True:
        failures.append(f"last weekly run failed (failed_step={raw_status.get('failed_step')})")

    bundle = _read_json(bilko_dir / "last1m.json")
    pubdate = (bundle or {}).get("pubdate")
    pub_age = _pubdate_age(pubdate, today) if pubdate else None
    if pub_age is None:
        failures.append(f"pubdate missing or unreadable in {bilko_dir / 'last1m.json'}")
    elif pub_age > max_stale_days:
        failures.append(f"published bundle pubdate {pub_age} days old (limit {max_stale_days})")

    return {
        "today": today.isoformat(),
        "regions": regions,
        "status": status,
        "pubdate": pubdate,
        "pubdate_age_days": pub_age,
        "failures": failures,
    }


def _table(rep: dict) -> str:
    head = ("region", "points", "gaps_weather", "gaps_aq", "latest_ts_utc", "days_stale")
    rows = [head] + [
        (r, str(v["points"]), str(v["gaps"]["weather"]), str(v["gaps"]["aq"]),
         str(v["latest_ts_utc"] or "-"), str(v["days_stale"] if v["days_stale"] is not None else "-"))
        for r, v in rep["regions"].items()
    ]
    widths = [max(len(row[i]) for row in rows) for i in range(len(head))]
    lines = ["  ".join(c.ljust(w) for c, w in zip(row, widths)).rstrip() for row in rows]
    s = rep["status"]
    lines.append(f"weekly: ts={s['ts']} ok={s['ok']} failed_step={s['failed_step']} published={s['published']}")
    lines.append(f"bundle pubdate: {rep['pubdate']} ({rep['pubdate_age_days']} days old)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m etl.health", description=__doc__)
    ap.add_argument("--root", type=Path, default=REPO_ROOT, help="project root (default: repo root)")
    ap.add_argument("--bilko-dir", type=Path, default=DEFAULT_BILKO_DIR,
                    help="published bundle dir containing last1m.json")
    ap.add_argument("--max-stale-days", type=int, default=14)
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    args = ap.parse_args(argv)

    rep = collect(args.root, args.bilko_dir, args.max_stale_days)
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        print(_table(rep))
        for f in rep["failures"]:
            print(f"FAIL {f}")
        if not rep["failures"]:
            print("HEALTHY")
    return 1 if rep["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
