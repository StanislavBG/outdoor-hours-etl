"""Generate one-paragraph KOUT-7 overview summaries per time range (1y/5y/10y).
Much fewer calls than monthly — just 3 — so this runs standalone.

Writes: data/summaries/range_overview.json  {tag: "paragraph", ...}
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd

from etl.points import REGIONS

ROOT = Path(__file__).resolve().parents[1]
CURATED = ROOT / "data" / "curated"
OUT = ROOT / "data" / "summaries" / "range_overview.json"

RANGE_LABEL = {"last1y": "last 12 months", "last5y": "last 5 years", "last10y": "last 10 years"}


def build_prompt(tag: str, df: pd.DataFrame) -> str:
    # Aggregate to one row per region for the full period.
    region_totals = (
        df.groupby("region", as_index=False)
          .agg(stay_outside_hours=("stay_outside_hours", "sum"),
               total_daytime=("daytime_hours", "sum"),
               avg_temp=("temperature_2m_mean", "mean"),
               peak_temp=("temperature_2m_max", "max"),
               total_rain=("precipitation_sum", "sum"))
          .sort_values("stay_outside_hours", ascending=False)
    )
    lines = []
    for _, r in region_totals.iterrows():
        label = REGIONS.get(r["region"], {}).get("label", r["region"])
        pct = 100 * r["stay_outside_hours"] / r["total_daytime"] if r["total_daytime"] else 0
        lines.append(
            f"- {label}: {r['stay_outside_hours']:.0f} good-outdoor hours ({pct:.0f}% of daytime). "
            f"Avg temp {r['avg_temp']:.1f}°C, peak {r['peak_temp']:.0f}°C. "
            f"Total rain {r['total_rain']:.0f}mm."
        )
    stats = "\n".join(lines)
    period = RANGE_LABEL.get(tag, tag)
    return (
        'You are a weather writer for local TV news (KOUT-7 "Outdoor Hours"). '
        f'Write ONE engaging sentence (max 35 words) summarizing the {period} '
        'across these counties on "good-for-outdoors hours" '
        "(hours when it was daytime, 45-86°F, UV ≤6, ≤1 mm/h rain). "
        "No greetings, no preamble — just the sentence. "
        "Name the leader and the laggard, and call out the most interesting driver "
        "(heat, rain, UV, cold, fog, whatever fits).\n\n"
        f"Totals for the {period}:\n{stats}\n"
    )


def call_claude(prompt: str) -> str:
    r = subprocess.run(["claude", "-p"], input=prompt, capture_output=True, text=True, timeout=120, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"claude -p failed: {r.stderr[:200]}")
    return r.stdout.strip()


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out = {}
    for tag in ("last1y", "last5y", "last10y"):
        src = CURATED / f"region_monthly_{tag}.parquet"
        if not src.exists():
            continue
        df = pd.read_parquet(src)
        prompt = build_prompt(tag, df)
        print(f"[{tag}] generating…", flush=True)
        try:
            out[tag] = call_claude(prompt)
            print(f"  → {out[tag]}")
        except Exception as e:
            print(f"  FAILED: {e}")
    OUT.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
