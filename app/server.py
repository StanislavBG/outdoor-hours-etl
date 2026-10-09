"""Local FastAPI dashboard for the Weather Compare project.

Run:
    uv run python -m app.server
    # → http://127.0.0.1:8000/

Routes:
    GET /                     → dashboard HTML
    GET /api/tags             → datasets available on disk (by tag)
    GET /api/metrics          → metric catalog (human-friendly labels per grain)
    GET /api/series           → JSON time series for a given (tag, grain, metric)
    GET /api/detail           → next-finer-grain drill-down rows (optional regions filter)
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.data import available_tags, series_payload, validate_tag
from app.detail import build_detail
from classifier.personal import DEFAULT_PROFILE_ID, PROFILES
from etl.catalog import METRICS
from etl.points import REGIONS as REGION_REGISTRY

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Weather Compare")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")



REGION_LABEL = {k: v["label"] for k, v in REGION_REGISTRY.items()}
REGION_ORDER = list(REGION_REGISTRY.keys())


def _profile_payload(p) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "label": p.label,
        "desc": p.desc,
        "rule": {
            "temp_min_c": p.cold_c, "temp_max_c": p.hot_c,
            "temp_min_f": round(p.cold_c * 9 / 5 + 32),
            "temp_max_f": round(p.hot_c * 9 / 5 + 32),
            "uv_max": p.uv_max,
            "rain_max_mm_h": p.rain_max_mm_h,
            "cloud_max_pct": p.overcast_max_pct,
            "humidity_max_pct": p.humidity_max_pct,
            "aqi_max": getattr(p, "aqi_max", None),
        },
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/tags")
def tags() -> JSONResponse:
    return JSONResponse({"tags": available_tags()})


@app.get("/api/metrics")
def metrics() -> JSONResponse:
    return JSONResponse({
        "metrics": METRICS,
        "regions": REGION_LABEL,
        "region_registry": REGION_REGISTRY,
        "region_order": REGION_ORDER,
        "default_profile": _profile_payload(next(p for p in PROFILES if p.id == DEFAULT_PROFILE_ID)),
    })


@app.get("/api/series")
def series(
    tag: str = Query("sample_last30"),
    grain: Literal["daily", "monthly", "yearly"] = Query("daily"),
    metric: str = Query("stay_outside_hours"),
) -> JSONResponse:
    return JSONResponse(series_payload(validate_tag(tag), grain, metric))


@app.get("/api/detail")
def detail(
    tag: str = Query(...),
    grain: Literal["daily", "monthly", "yearly"] = Query(...),
    bucket: str = Query(..., description="ISO date for daily/monthly buckets, integer year for yearly"),
    regions: str | None = Query(None, description="Comma-separated region ids; default all"),
) -> JSONResponse:
    validate_tag(tag)
    wanted = None
    if regions is not None:
        wanted = [r for r in regions.split(",") if r]
        unknown = [r for r in wanted if r not in REGION_REGISTRY]
        if unknown or not wanted:
            raise HTTPException(400, f"unknown regions: {', '.join(unknown) or regions!r}")
    return JSONResponse(build_detail(tag, grain, bucket, wanted))


def main() -> None:
    import uvicorn
    uvicorn.run("app.server:app", host="127.0.0.1", port=8000, reload=False, log_level="info")


if __name__ == "__main__":
    main()
