"""Data access and series shaping for the dashboard API.

Owns the curated-parquet location, tag validation and a bounded, mtime-keyed
cache of region rollups. Cached frames are shared: callers must copy before
adding columns.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import HTTPException

from etl.catalog import METRIC_KEYS, X_COL, json_scalar, metric
from etl.points import REGIONS

ROOT = Path(__file__).resolve().parents[1]
CURATED = ROOT / "data" / "curated"

Grain = Literal["daily", "monthly", "yearly"]

_TAG_RE = re.compile(r"^[a-z0-9_]{1,40}$")
_CACHE_SIZE = 16


def available_tags() -> list[str]:
    """Tags for which the region_daily parquet exists (minimum needed for the dashboard)."""
    return sorted({
        p.stem.removeprefix("region_daily_")
        for p in CURATED.glob("region_daily_*.parquet")
    })


def validate_tag(tag: str) -> str:
    """Return `tag` if it is well-formed and on disk; HTTP 404 otherwise."""
    if not _TAG_RE.fullmatch(tag) or tag not in available_tags():
        raise HTTPException(404, f"unknown tag: {tag}")
    return tag


@lru_cache(maxsize=_CACHE_SIZE)
def _read(path_str: str, mtime_ns: int) -> pd.DataFrame:
    # mtime_ns is part of the cache key only: a rewritten file misses and is re-read.
    return pd.read_parquet(path_str)


def load_rollup(tag: str, grain: Grain) -> pd.DataFrame:
    """Read region_{grain}_{tag}.parquet (cached, read-only: copy before mutating)."""
    path = CURATED / f"region_{grain}_{tag}.parquet"
    try:
        mtime_ns = path.stat().st_mtime_ns
    except FileNotFoundError:
        raise HTTPException(404, f"no {grain} rollup for tag={tag}") from None
    return _read(str(path), mtime_ns)


def series_payload(tag: str, grain: Grain, metric_key: str) -> dict:
    if metric_key not in METRIC_KEYS:
        raise HTTPException(400, f"unknown metric: {metric_key}")

    df = load_rollup(tag, grain)
    if metric_key not in df.columns:
        raise HTTPException(404, f"metric {metric_key} not present in {grain}_{tag}")

    x = X_COL[grain]
    series_out: dict[str, dict] = {}
    for region, grp in df.groupby("region"):
        grp = grp.sort_values(x).reset_index(drop=True)
        if grain == "yearly":
            xs = grp[x].astype(int).tolist()
        else:
            xs = [v.isoformat() if hasattr(v, "isoformat") else str(v) for v in grp[x]]
        series_out[region] = {
            "label": REGIONS.get(region, {}).get("label", region),
            "x": xs,
            "y": [json_scalar(v) for v in grp[metric_key]],
            "n_points": grp["n_points"].tolist() if "n_points" in grp.columns else None,
        }

    meta = metric(metric_key)
    return {
        "tag": tag,
        "grain": grain,
        "metric": metric_key,
        "metric_label": meta["label"],
        "unit": meta["unit"],
        "series": series_out,
        "row_counts": {r: len(v["x"]) for r, v in series_out.items()},
    }
