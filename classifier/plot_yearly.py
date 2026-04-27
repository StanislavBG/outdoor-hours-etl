"""Primary dashboard plot: yearly Stay-Outside hours per region, 1940→present.

Full-page, heavily labelled, annotated. Writes PNG + SVG to data/plots/.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import pandas as pd

from classifier.aggregate import to_point_year, to_region_year
from classifier.personal import COLD_C, HOT_C, UV_MAX

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PARQUET = ROOT / "data" / "curated" / "hourly_full.parquet"
OUT_DIR = ROOT / "data" / "plots"

REGION_LABEL = {
    "santa_clara_ca": "Santa Clara County, CA",
    "eastside_king_wa": "Eastside King County, WA",
}
REGION_COLOR = {
    "santa_clara_ca": "#d95f02",
    "eastside_king_wa": "#1b9e77",
}


def _annotate_extremes(ax, years, values, color, label):
    if len(values) == 0:
        return
    imax = int(values.idxmax())
    imin = int(values.idxmin())
    ilast = years.index[-1]
    for idx, tag in ((imax, "max"), (imin, "min"), (ilast, "latest")):
        y, v = int(years.loc[idx]), float(values.loc[idx])
        ax.annotate(
            f"{label} {tag}\n{y}: {v:,.0f} h",
            xy=(y, v),
            xytext=(0, 18 if tag == "max" else -28 if tag == "min" else 10),
            textcoords="offset points",
            ha="center",
            fontsize=9,
            color=color,
            arrowprops=dict(arrowstyle="-", color=color, lw=0.8, alpha=0.7),
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=color, alpha=0.9),
        )


def plot(parquet: Path, out_png: Path, out_svg: Path | None = None) -> dict:
    hourly = pd.read_parquet(parquet)
    point_year = to_point_year(hourly)
    region_year = to_region_year(point_year)

    # Only full-data years for the trend lines; partial years annotated separately.
    full = region_year[region_year["is_full_year"]].copy()
    partial = region_year[~region_year["is_full_year"]].copy()

    fig, ax = plt.subplots(figsize=(20, 11), dpi=140)
    fig.subplots_adjust(left=0.07, right=0.985, top=0.86, bottom=0.18)

    for region, grp in full.groupby("region"):
        grp = grp.sort_values("year").reset_index(drop=True)
        color = REGION_COLOR[region]
        label = REGION_LABEL[region]
        ax.plot(
            grp["year"], grp["stay_outside_hours"],
            color=color, linewidth=2.2, marker="o", markersize=4.5,
            label=label,
        )
        # Rolling 10-year mean as a lighter companion line.
        rolling = grp["stay_outside_hours"].rolling(10, min_periods=3, center=True).mean()
        ax.plot(grp["year"], rolling, color=color, linewidth=1.0, linestyle="--", alpha=0.55,
                label=f"{label} — 10-yr rolling mean")
        _annotate_extremes(ax, grp["year"], grp["stay_outside_hours"], color, label.split(",")[0])

    # Partial-year ticks (e.g. current year) plotted as hollow markers.
    for region, grp in partial.groupby("region"):
        ax.scatter(
            grp["year"], grp["stay_outside_hours"],
            facecolors="none", edgecolors=REGION_COLOR[region], s=55, linewidths=1.4,
            label=f"{REGION_LABEL[region]} — partial year",
        )

    ax.set_title(
        "Where is the Weather Better?\n"
        "Annual 'Stay Outside' hours — ERA5 reanalysis, 1940 → present",
        fontsize=18, fontweight="bold", loc="left", pad=16,
    )

    # Subtitle with formula.
    formula = (
        f"stay_outside = 1  ⇔  sun is up  AND  {COLD_C:.0f}°C ≤ temperature_2m ≤ {HOT_C:.0f}°C  "
        f"AND  uv_index_est ≤ {UV_MAX:.0f}\n"
        "Per point we sum hours where the rule fires across a calendar year, then average "
        "the three sample points within each region to yield a 'typical location' score."
    )
    fig.text(0.07, 0.905, formula, fontsize=11, color="#333333",
             bbox=dict(boxstyle="round,pad=0.5", fc="#f4f4f4", ec="#cccccc"))

    ax.set_xlabel("Year (local calendar, America/Los_Angeles)", fontsize=12, labelpad=8)
    ax.set_ylabel("Stay-Outside hours per year (mean of 3 points in region)",
                  fontsize=12, labelpad=10)
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.grid(which="major", axis="both", linestyle=":", alpha=0.45)
    ax.set_axisbelow(True)

    # Reference bands (percent of daytime hours ≈ 4380 for a mid-lat year).
    ax.axhspan(0, 1000, color="#f8d7da", alpha=0.25)
    ax.axhspan(1000, 2500, color="#fff3cd", alpha=0.25)
    ax.axhspan(2500, 4500, color="#d1e7dd", alpha=0.25)
    for y_, lbl in [(500, "poor (<1,000 h)"), (1750, "moderate (1–2.5k h)"),
                    (3300, "strong (2.5–4.5k h)")]:
        ax.text(ax.get_xlim()[0] + 0.5, y_, lbl, fontsize=8, color="#777", alpha=0.9)

    ax.legend(loc="upper left", framealpha=0.9, ncol=2, fontsize=10, bbox_to_anchor=(0.0, -0.08))

    # Footer — compute provenance.
    footer_lines = [
        f"Source:  Open-Meteo Historical Weather API (ERA5 reanalysis + ERA5T for recent days).  "
        f"Points: San Jose, Palo Alto, Morgan Hill (SCC); Bellevue, Redmond, Woodinville (Eastside King).",
        f"Compute:  per-hour rule → per-year sum per point → mean across 3 points in the region.  "
        f"UV index is an estimate from solar geometry × cloud attenuation (UVI ≈ 12·sin(alt)^1.7·(1 − 0.75·cloud)).",
        f"Full-year points require ≥ 8,760 rows (accounts for leap years). "
        f"Partial years shown as hollow markers and excluded from the trend line.",
    ]
    for i, line in enumerate(footer_lines):
        fig.text(0.07, 0.04 - i * 0.025, line, fontsize=9, color="#555555")

    # Headline region comparison (last full year).
    last_full_year = full["year"].max()
    headline = full[full["year"] == last_full_year]
    if not headline.empty:
        scc_h = headline.loc[headline["region"] == "santa_clara_ca", "stay_outside_hours"]
        wa_h = headline.loc[headline["region"] == "eastside_king_wa", "stay_outside_hours"]
        if len(scc_h) and len(wa_h):
            delta = float(scc_h.iloc[0]) - float(wa_h.iloc[0])
            winner = "Santa Clara" if delta > 0 else "Eastside King"
            fig.text(
                0.985, 0.89,
                f"Latest full year ({last_full_year})\n"
                f"  SCC: {float(scc_h.iloc[0]):,.0f} h\n"
                f"  King: {float(wa_h.iloc[0]):,.0f} h\n"
                f"  Δ = {abs(delta):,.0f} h → {winner}",
                ha="right", va="top", fontsize=11,
                bbox=dict(boxstyle="round,pad=0.5", fc="#ffffff", ec="#888888"),
            )

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, bbox_inches="tight")
    if out_svg:
        fig.savefig(out_svg, bbox_inches="tight")
    plt.close(fig)

    return {
        "png": str(out_png),
        "years_full": [int(y) for y in sorted(full["year"].unique())],
        "years_partial": [int(y) for y in sorted(partial["year"].unique())],
        "region_year_rows": len(region_year),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet", default=str(DEFAULT_PARQUET))
    parser.add_argument("--out", default=str(OUT_DIR / "yearly_stay_outside.png"))
    parser.add_argument("--svg", default=str(OUT_DIR / "yearly_stay_outside.svg"))
    args = parser.parse_args()
    res = plot(Path(args.parquet), Path(args.out), Path(args.svg))
    print(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
