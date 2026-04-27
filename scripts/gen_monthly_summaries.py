"""Generate one-sentence KOUT-7 narrative summaries for each monthly bucket in
the last10y rollup, via `claude -p`. Saves progressively so interruption only
loses the current month.

Writes: data/summaries/monthly_last10y.json  {"YYYY-MM": "sentence", ...}
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

from etl.points import REGIONS

ROOT = Path(__file__).resolve().parents[1]
CURATED = ROOT / "data" / "curated"
OUT_DIR = ROOT / "data" / "summaries"
OUT = OUT_DIR / "monthly_last10y.json"

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def build_prompt(year: int, month: int, rows: pd.DataFrame) -> str:
    rows = rows.sort_values("stay_outside_hours", ascending=False).reset_index(drop=True)
    stats_lines = []
    for _, r in rows.iterrows():
        label = REGIONS.get(r["region"], {}).get("label", r["region"])
        soh = r["stay_outside_hours"]
        pct = r["pct_daytime_outside"]
        t_mean = r["temperature_2m_mean"]
        t_max = r["temperature_2m_max"]
        uv_max = r["uv_index_est_max"]
        rain = r["precipitation_sum"]
        stats_lines.append(
            f"- {label}: {soh:.0f}h good-outdoor ({pct:.0f}% of daytime). "
            f"Temp avg {t_mean:.0f}°C, peak {t_max:.0f}°C. "
            f"Strongest UV {uv_max:.1f}. "
            f"Total rain {rain:.0f}mm."
        )
    stats = "\n".join(stats_lines)
    month_name = f"{MONTH_NAMES[month-1]} {year}"
    return (
        'You are a weather writer for local TV news (KOUT-7 "Outdoor Hours"). '
        'Write ONE plain-English sentence (max 30 words) about ' + month_name + ', '
        'comparing these counties on "good-for-outdoors hours" '
        "(hours when it was daytime, 45-86°F, UV ≤6, ≤1 mm/h rain). "
        "No greetings, no preamble — just the sentence. "
        "Name the winner and, if there's a clear reason for the spread "
        "(heat, rain, UV, cold), call it out. If counties are near-tied, say so.\n\n"
        f"{month_name} stats:\n{stats}\n"
    )


def call_claude(prompt: str, timeout: int = 90) -> str:
    r = subprocess.run(
        ["claude", "-p"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if r.returncode != 0:
        raise RuntimeError(f"claude -p failed rc={r.returncode}: {r.stderr[:200]}")
    text = r.stdout.strip()
    if not text:
        raise RuntimeError("claude -p returned empty")
    return text


def main() -> None:
    df = pd.read_parquet(CURATED / "region_monthly_last10y.parquet")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Resume support: load existing summaries and skip those already done.
    done: dict[str, str] = {}
    if OUT.exists():
        done = json.loads(OUT.read_text())
        print(f"resuming with {len(done)} summaries already cached")

    months = sorted({(r.year, r.month) for r in df.itertuples()})
    total = len(months)
    t0 = time.time()

    for i, (y, m) in enumerate(months, 1):
        key = f"{y:04d}-{m:02d}"
        if key in done:
            continue
        rows = df[(df.year == y) & (df.month == m)]
        if rows.empty:
            continue
        prompt = build_prompt(y, m, rows)
        try:
            t_call = time.time()
            text = call_claude(prompt)
            elapsed = time.time() - t_call
        except Exception as e:
            print(f"  {key}: FAILED — {e}", file=sys.stderr)
            continue
        done[key] = text
        total_elapsed = time.time() - t0
        remaining = (total - i) * (total_elapsed / max(i, 1))
        print(f"[{i:>3}/{total}] {key} ({elapsed:.1f}s, eta {remaining/60:.1f}min): {text[:100]}")
        OUT.write_text(json.dumps(done, indent=2))

    print(f"\ndone — {len(done)}/{total} summaries in {OUT}")


if __name__ == "__main__":
    main()
