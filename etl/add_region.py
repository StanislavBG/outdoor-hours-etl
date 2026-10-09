"""Add a region to etl/regions.yaml and backfill its history.

    uv run python -m etl.add_region --region-id miami_fl --label "Miami, FL" \
        --short MIA --place "Miami, Florida, United States" --publish
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
import yaml

from etl import sync
from etl.points import REGIONS_YAML, load_registry

ROOT = Path(__file__).resolve().parent.parent
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REGION_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,40}$")
SHORT_RE = re.compile(r"^[A-Z]{2,4}$")

# (color, ink) pairs; first block mirrors regions.yaml, rest are new distinct hues.
PALETTE: list[tuple[str, str]] = [
    ("#e45c3a", "#b43f21"),
    ("#0e8f74", "#096a56"),
    ("#8e54c4", "#6d2d85"),
    ("#cc8a1a", "#8a5b0e"),
    ("#ec4899", "#a12553"),
    ("#16a34a", "#0f6d31"),
    ("#3b82f6", "#1d4ed8"),
    ("#06b6d4", "#0e7490"),
    ("#f59e0b", "#a26508"),
    ("#64748b", "#334155"),
    ("#14b8a6", "#0f766e"),
    ("#a16207", "#713f12"),
    ("#d55e00", "#9a4300"),
    ("#0072b2", "#00507d"),
    ("#009e73", "#006e50"),
    ("#c2410c", "#7c2d12"),
    ("#7c3aed", "#5b21b6"),
    ("#be123c", "#881337"),
]


class NoMatch(Exception):
    pass


def fail(msg: str) -> "None":
    print(msg, file=sys.stderr)
    raise SystemExit(2)


def geocode(place: str) -> dict:
    """Top Open-Meteo geocoding result for the place's leading name segment."""
    name = place.split(",")[0].strip()
    r = httpx.get(GEOCODE_URL, params={"name": name, "count": 1}, timeout=15)
    r.raise_for_status()
    results = r.json().get("results") or []
    if not results:
        raise NoMatch(place)
    return results[0]


def lookup_meta(lat: float, lon: float) -> tuple[int, str]:
    """Elevation (m) and IANA timezone for explicit coordinates."""
    r = httpx.get(FORECAST_URL, params={"latitude": lat, "longitude": lon, "timezone": "auto",
                                        "current": "temperature_2m"}, timeout=15)
    r.raise_for_status()
    j = r.json()
    return int(round(j.get("elevation") or 0)), j["timezone"]


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def parse_point(spec: str) -> dict:
    parts = spec.split("|")
    if len(parts) not in (4, 6):
        fail(f"bad --point {spec!r}: expected 'id|Name|lat|lon[|elevation|timezone]'")
    pid, name = parts[0].strip(), parts[1].strip()
    try:
        lat, lon = float(parts[2]), float(parts[3])
    except ValueError:
        fail(f"bad --point {spec!r}: lat/lon must be numbers")
    check_coords(pid, lat, lon)
    if len(parts) == 6:
        elev, tz = int(round(float(parts[4]))), parts[5].strip()
    else:
        elev, tz = lookup_meta(lat, lon)
    return {"id": pid, "name": name, "lat": lat, "lon": lon, "elevation_m": elev, "timezone": tz}


def check_coords(pid: str, lat: float, lon: float) -> None:
    if not -90 <= lat <= 90:
        fail(f"point {pid!r}: lat {lat} out of range [-90, 90]")
    if not -180 <= lon <= 180:
        fail(f"point {pid!r}: lon {lon} out of range [-180, 180]")


def resolve_place(place: str) -> dict:
    try:
        g = geocode(place)
    except NoMatch:
        fail(f"no geocoding match for {place}")
    name = g["name"]
    lat, lon = g["latitude"], g["longitude"]
    check_coords(slugify(name), lat, lon)
    return {"id": slugify(name), "name": name, "lat": lat, "lon": lon,
            "elevation_m": int(round(g.get("elevation") or 0)), "timezone": g["timezone"]}


def build_region(args, registry) -> dict:
    """Validated region mapping (without its id key). registry = load_registry() result."""
    existing_points, existing_regions = registry
    if not REGION_ID_RE.match(args.region_id):
        fail(f"invalid region id {args.region_id!r}: must match {REGION_ID_RE.pattern}")
    if args.region_id in existing_regions:
        fail(f"duplicate region id {args.region_id!r}")
    if not SHORT_RE.match(args.short):
        fail(f"invalid --short {args.short!r}: must be 2-4 uppercase letters")
    specs = [("place", p) for p in args.place] + [("point", p) for p in args.point]
    if not 1 <= len(specs) <= 3:
        fail(f"need 1-3 points, got {len(specs)}")

    pts = [resolve_place(v) if k == "place" else parse_point(v) for k, v in specs]
    taken = {p.id for p in existing_points}
    for p in pts:
        if p["id"] in taken:
            fail(f"duplicate point id {p['id']!r}")
        taken.add(p["id"])
        try:
            ZoneInfo(p["timezone"])
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            fail(f"point {p['id']!r}: invalid timezone {p['timezone']!r}")
        check_coords(p["id"], p["lat"], p["lon"])

    used = {r["color"] for r in existing_regions.values()}
    color, ink = next(((c, i) for c, i in PALETTE if c not in used), PALETTE[-1])
    return {
        "label": args.label,
        "short": args.short,
        "color": color,
        "ink": ink,
        "default_on": False,
        "description": f"{args.label} — " + ", ".join(p["name"] for p in pts),
        "points": pts,
    }


def render_block(region_id: str, region: dict) -> str:
    dumped = yaml.safe_dump({region_id: region}, sort_keys=False, allow_unicode=True)
    return "".join("  " + line if line.strip() else line for line in dumped.splitlines(True))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="etl.add_region", description=__doc__.split("\n\n")[0])
    ap.add_argument("--region-id", required=True, help="snake_case id")
    ap.add_argument("--label", required=True)
    ap.add_argument("--short", required=True, help="2-4 uppercase letters")
    ap.add_argument("--place", action="append", default=[], help="'Name, Admin, Country'")
    ap.add_argument("--point", action="append", default=[],
                    help="'id|Name|lat|lon[|elevation|timezone]'")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-backfill", action="store_true")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--regions-file", type=Path, default=REGIONS_YAML)
    args = ap.parse_args(argv)

    path = args.regions_file
    try:
        registry = load_registry(path)
    except (ValueError, OSError) as e:
        fail(f"cannot load {path}: {e}")
    region = build_region(args, registry)
    block = render_block(args.region_id, region)
    new_ids = [p["id"] for p in region["points"]]

    if args.dry_run:
        print(block, end="")
        return 0

    original = path.read_text(encoding="utf-8")
    path.write_text(original.rstrip("\n") + "\n" + block, encoding="utf-8")
    try:
        load_registry(path)
    except Exception as e:
        path.write_text(original, encoding="utf-8")
        fail(f"generated region failed validation, nothing written: {e}")

    print(f"added region {args.region_id}")
    for p in region["points"]:
        print(f"  {p['id']}: {p['lat']}, {p['lon']} ({p['timezone']})")
    if args.no_backfill:
        print("backfill skipped; run: uv run python -m etl.sync --points " + " ".join(new_ids))
        return 0

    rc = sync.main(["--points", *new_ids])
    print(f"sync exit code: {rc}")
    if rc != 0:
        return rc
    if args.publish:
        rc = subprocess.run(["bash", str(ROOT / "scripts" / "weekly_refresh.sh")]).returncode
        print(f"publish exit code: {rc}")
        return rc
    print("next: bash scripts/weekly_refresh.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
