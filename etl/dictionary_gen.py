"""Generate data/DICTIONARY.md from data/variables.yaml and a curated parquet schema."""
from __future__ import annotations

import argparse
from pathlib import Path
from textwrap import dedent

import duckdb
import yaml

ROOT = Path(__file__).resolve().parents[1]
VARS_YAML = ROOT / "data" / "variables.yaml"
OUT = ROOT / "data" / "DICTIONARY.md"


def schema(parquet_path: Path) -> list[tuple[str, str]]:
    con = duckdb.connect()
    rows = con.execute(f"describe select * from read_parquet('{parquet_path}')").fetchall()
    return [(r[0], r[1]) for r in rows]


def render(manifest: dict, schema_rows: list[tuple[str, str]]) -> str:
    meta = {v["name"]: v for v in manifest["hourly_variables"]}
    derived = {v["name"]: v for v in manifest.get("derived_variables", [])}

    identity = {
        "region": ("string", "County region id (santa_clara_ca | eastside_king_wa)"),
        "point": ("string", "Point id (san_jose, palo_alto, morgan_hill, bellevue, redmond, woodinville)"),
        "ts_utc": ("timestamp UTC", "Start of hour, UTC"),
        "ts_local": ("timestamp local", "Start of hour, local wall-clock time of the point's own timezone (naive)"),
        "lat": ("float", "Point latitude (degrees)"),
        "lon": ("float", "Point longitude (degrees)"),
        "elevation_m": ("int", "Point elevation (meters, approximate)"),
        "year": ("int16", "Local year"),
        "month": ("int8", "Local month (1-12)"),
        "day": ("int8", "Local day-of-month"),
        "hour_of_day": ("int8", "Local hour (0-23)"),
        "dow": ("int8", "Day of week (Mon=0)"),
    }

    lines = [
        "# Data dictionary — hourly weather comparison\n",
        f"**Source:** {manifest['source']}  ",
        f"**Endpoint:** {manifest['endpoint']}  ",
        f"**Reanalysis:** {manifest['reanalysis']}  ",
        f"**Grid resolution:** {manifest['grid_resolution_km']} km  ",
        f"**Temporal resolution:** {manifest['temporal_resolution']}\n",
        "## Table: `data/curated/hourly_<tag>.parquet`\n",
        "One row per (point, hour). Grain: hour beginning at `ts_utc`.\n",
        "### Columns\n",
        "| column | type | axis | unit | description |",
        "|---|---|---|---|---|",
    ]

    for col, dtype in schema_rows:
        if col in identity:
            axis = "meta"
            unit, desc = identity[col]
            unit = ""
        elif col in meta:
            m = meta[col]
            axis = m.get("axis", "")
            unit = m.get("unit", "")
            desc = m["description"]
        elif col in derived:
            m = derived[col]
            axis = m.get("axis", "")
            unit = m.get("unit", "")
            desc = m["description"].strip().replace("\n", " ")
        else:
            axis, unit, desc = "", "", ""
        lines.append(f"| `{col}` | `{dtype}` | {axis} | {unit} | {desc} |")

    lines.append("\n### Axes\n")
    lines.append(dedent(
        """\
        The five comparison axes that feed the weighted scoring formula:

        | axis | variables |
        |---|---|
        | **temp** | temperature_2m, apparent_temperature, dew_point_2m, relative_humidity_2m |
        | **rain** | precipitation, rain, snowfall, snow_depth |
        | **sun**  | cloud_cover, cloud_cover_low/mid/high, shortwave_radiation, direct_radiation, diffuse_radiation, direct_normal_irradiance, sunshine_duration, is_day |
        | **wind** | wind_speed_10m, wind_speed_100m, wind_direction_10m, wind_direction_100m, wind_gusts_10m |
        | **uv**   | uv_index_est (derived) |
        """
    ))

    lines.append("### Notes\n")
    lines.append("- ERA5 has an ~5-day lag; the most recent hours may come from ERA5T (near-real-time).\n")
    lines.append("- `uv_index_est` is a geometric proxy from shortwave radiation — not a measured UV index.\n")
    lines.append("- Units are Open-Meteo defaults: wind in m/s (explicitly requested), temperature in °C, precipitation in mm.\n")
    lines.append("- Timestamps are hour-beginning. `ts_utc` is the canonical key; `ts_local` is derived for convenience.\n")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet", required=True, help="Path to a curated parquet to introspect")
    args = parser.parse_args()
    manifest = yaml.safe_load(VARS_YAML.read_text())
    rows = schema(Path(args.parquet))
    OUT.write_text(render(manifest, rows))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
