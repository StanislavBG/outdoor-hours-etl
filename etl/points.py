from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Point:
    id: str
    name: str
    region: str
    lat: float
    lon: float
    elevation_m: int
    timezone: str


REGIONS_YAML = Path(__file__).with_name("regions.yaml")

_REGION_FIELDS = ("label", "short", "color", "ink", "default_on")
_POINT_FIELDS = ("id", "name", "lat", "lon", "elevation_m", "timezone")


def _check_duplicate_region_ids(text: str, path: Path) -> None:
    # yaml.safe_load silently keeps the last of duplicate keys, so inspect the node tree.
    root = yaml.compose(text)
    if not isinstance(root, yaml.MappingNode):
        return
    for k, v in root.value:
        if k.value == "regions" and isinstance(v, yaml.MappingNode):
            seen: set[str] = set()
            for rk, _ in v.value:
                if rk.value in seen:
                    raise ValueError(f"{path}: duplicate region id {rk.value!r}")
                seen.add(rk.value)


def load_registry(path: Path = REGIONS_YAML) -> tuple[list[Point], dict[str, dict]]:
    """Load points and region metadata from a regions YAML file."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    _check_duplicate_region_ids(text, path)
    data = yaml.safe_load(text)
    if not isinstance(data, dict) or not isinstance(data.get("regions"), dict):
        raise ValueError(f"{path}: expected a top-level 'regions' mapping")

    points: list[Point] = []
    regions: dict[str, dict] = {}
    seen_ids: set[str] = set()
    for rid, r in data["regions"].items():
        if not isinstance(r, dict):
            raise ValueError(f"{path}: region {rid!r} must be a mapping")
        for f in _REGION_FIELDS:
            if f not in r:
                raise ValueError(f"{path}: region {rid!r} missing required field {f!r}")
        regions[rid] = {f: r[f] for f in _REGION_FIELDS}
        for i, p in enumerate(r.get("points") or []):
            if not isinstance(p, dict):
                raise ValueError(f"{path}: region {rid!r} point #{i} must be a mapping")
            for f in _POINT_FIELDS:
                if f not in p:
                    raise ValueError(
                        f"{path}: region {rid!r} point {p.get('id', f'#{i}')!r} "
                        f"missing required field {f!r}"
                    )
            if p["id"] in seen_ids:
                raise ValueError(f"{path}: duplicate point id {p['id']!r}")
            seen_ids.add(p["id"])
            if not -90 <= p["lat"] <= 90:
                raise ValueError(f"{path}: point {p['id']!r} lat {p['lat']} out of range [-90, 90]")
            if not -180 <= p["lon"] <= 180:
                raise ValueError(f"{path}: point {p['id']!r} lon {p['lon']} out of range [-180, 180]")
            points.append(Point(
                id=p["id"], name=p["name"], region=rid, lat=p["lat"], lon=p["lon"],
                elevation_m=p["elevation_m"], timezone=p["timezone"],
            ))
    return points, regions


# Region registry — friendly labels + colors + display order (YAML order).
# Palette chosen for colorblind safety (Wong palette).
POINTS, REGIONS = load_registry(REGIONS_YAML)


def by_id(point_id: str) -> Point:
    for p in POINTS:
        if p.id == point_id:
            return p
    raise KeyError(point_id)
