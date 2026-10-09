"""Generate per-region "character" profiles via local claude.

For each county in the registry, asks claude to write a short profile based
on 10 years of monthly stats: best time of year to be outdoors, strengths,
and what (and when) to avoid.

Outputs JSON like:
  {
    "santa_clara_ca": {
      "best_time": "...",
      "strengths": "...",
      "watch_out": "..."
    },
    ...
  }

Writes: data/summaries/region_profiles.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

from etl.points import REGIONS
from scripts._claude import run_claude

ROOT = Path(__file__).resolve().parents[1]
CURATED = ROOT / "data" / "curated"
OUT = ROOT / "data" / "summaries" / "region_profiles.json"

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def per_month_stats(df_region: pd.DataFrame) -> str:
    """Build a compact monthly-climatology table from 10 years of monthly rollups."""
    g = (
        df_region.groupby("month", as_index=False)
        .agg(
            stay_out_hours=("stay_outside_hours", "mean"),
            pct_daytime_outside=("pct_daytime_outside", "mean"),
            temp_mean=("temperature_2m_mean", "mean"),
            temp_max=("temperature_2m_max", "mean"),
            uv_max=("uv_index_est_max", "mean"),
            rain_mm=("precipitation_sum", "mean"),
        )
        .sort_values("month")
    )
    lines = []
    for _, r in g.iterrows():
        lines.append(
            f"  {MONTH_NAMES[int(r['month'])-1]}: "
            f"{r['stay_out_hours']:.0f}h good ({r['pct_daytime_outside']:.0f}% of daytime), "
            f"avg {r['temp_mean']:.0f}°C / peak {r['temp_max']:.0f}°C, "
            f"UV peak {r['uv_max']:.1f}, rain {r['rain_mm']:.0f}mm"
        )
    return "\n".join(lines)


def build_prompt(region_key: str, label: str, stats: str) -> str:
    return (
        'You are a weather writer for local TV news (KOUT-7 "Outdoor Hours"). '
        f'Write a short profile of {label} based on 10 years of monthly weather data.\n\n'
        "Return EXACTLY this JSON shape — no preamble, no fences, no commentary, just the JSON:\n"
        '{"best_time":"…","strengths":"…","watch_out":"…"}\n\n'
        "Each field is ONE plain-English sentence (max 25 words):\n"
        "  best_time: which months are best for being outdoors and why\n"
        "  strengths: 1–2 things this county does better than most for outdoor weather\n"
        "  watch_out: the worst stretch of the year and why (heat, rain, UV, cold)\n"
        "Skip greetings. Use the data; do not invent.\n\n"
        f"Average per-month stats for {label} (10-year climatology):\n{stats}\n"
    )


def call_claude(prompt: str, timeout: int = 90) -> dict:
    text = run_claude(prompt, timeout=timeout)
    # Strip code fences if claude added them despite instructions.
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        # Last-resort: pull the first {...} block.
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not m:
            raise RuntimeError(f"no JSON object in: {text[:200]}")
        obj = json.loads(m.group(0))
    for key in ("best_time", "strengths", "watch_out"):
        if key not in obj:
            raise RuntimeError(f"missing key '{key}' in: {obj}")
    return {k: str(obj[k]).strip() for k in ("best_time", "strengths", "watch_out")}


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(CURATED / "region_monthly_last10y.parquet")

    out: dict = {}
    if OUT.exists():
        out = json.loads(OUT.read_text())
        print(f"resuming with {len(out)} profiles cached")

    for region, info in REGIONS.items():
        if region in out:
            continue
        sub = df[df["region"] == region]
        if sub.empty:
            print(f"  skip {region}: no data on disk")
            continue
        stats = per_month_stats(sub)
        prompt = build_prompt(region, info["label"], stats)
        print(f"  generating {region}...", flush=True)
        try:
            profile = call_claude(prompt)
        except Exception as e:
            print(f"    FAILED: {e}", file=sys.stderr)
            continue
        out[region] = profile
        OUT.write_text(json.dumps(out, indent=2))
        print(f"    best_time: {profile['best_time']}")
        print(f"    strengths: {profile['strengths']}")
        print(f"    watch_out: {profile['watch_out']}")

    print(f"\ndone — {len(out)} profiles in {OUT}")


if __name__ == "__main__":
    main()
