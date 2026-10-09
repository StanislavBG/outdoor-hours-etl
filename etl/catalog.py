"""Single metric catalog shared by the local dashboard (app/) and the public export
(scripts/export_outdoor_hours.py).

Owns the metric list (key/label/unit/kind and which direction is "better"), the
grain -> x-column map, and the NaN/Timestamp -> JSON scalar converter.

stay_outside_hours / pct_daytime_outside are aliases for the default profile;
the frontend swaps to stay_outside_<profile>_hours when the user picks a
different profile.
"""
from __future__ import annotations

import math

import pandas as pd

METRICS: list[dict] = [
    {"key": "stay_outside_hours",          "label": "Good-for-outdoors hours",          "unit": "hours", "kind": "sum",  "profile_aware": True, "better": "higher"},
    {"key": "pct_daytime_outside",         "label": "% of daylight that's comfortable", "unit": "%",     "kind": "pct",  "profile_aware": True, "better": "higher"},
    {"key": "temperature_2m_mean",         "label": "Average temperature",              "unit": "°C",    "kind": "mean", "better": None},
    {"key": "temperature_2m_max",          "label": "Hottest point",                    "unit": "°C",    "kind": "max",  "better": None},
    {"key": "apparent_temperature_mean",   "label": "Average feels-like temperature",   "unit": "°C",    "kind": "mean", "better": None},
    {"key": "uv_index_est_mean",           "label": "Average UV",                       "unit": "UV",    "kind": "mean", "better": None},
    {"key": "uv_index_est_max",            "label": "Strongest UV",                     "unit": "UV",    "kind": "max",  "better": None},
    {"key": "cloud_cover_mean",            "label": "Cloudiness",                       "unit": "%",     "kind": "mean", "better": "lower"},
    {"key": "precipitation_sum",           "label": "Total rain",                       "unit": "mm",    "kind": "sum",  "better": "lower"},
    {"key": "wind_speed_10m_mean",         "label": "Average wind",                     "unit": "m/s",   "kind": "mean", "better": None},
    {"key": "wind_gusts_10m_max",          "label": "Strongest gust",                   "unit": "m/s",   "kind": "max",  "better": "lower"},
    {"key": "sunshine_hours",              "label": "Sunshine hours",                   "unit": "hours", "kind": "sum",  "better": "higher"},
    {"key": "relative_humidity_2m_mean",   "label": "Humidity",                         "unit": "%",     "kind": "mean", "better": "lower"},
    {"key": "pressure_msl_mean",           "label": "Air pressure",                     "unit": "hPa",   "kind": "mean", "better": None},
    {"key": "us_aqi_mean",                 "label": "Air quality (US AQI)",             "unit": "AQI",   "kind": "mean", "better": "lower"},
    {"key": "us_aqi_max",                  "label": "Worst-hour AQI",                   "unit": "AQI",   "kind": "max",  "better": "lower"},
    {"key": "pm2_5_mean",                  "label": "PM2.5",                            "unit": "µg/m³", "kind": "mean", "better": "lower"},
]

METRIC_KEYS: frozenset[str] = frozenset(m["key"] for m in METRICS)
_BY_KEY = {m["key"]: m for m in METRICS}

X_COL = {"daily": "local_date", "monthly": "month_start", "yearly": "year"}


def metric(key: str) -> dict:
    """Return the catalog entry for `key`; KeyError if unknown."""
    return _BY_KEY[key]


def json_scalar(v):
    """Convert a pandas/numpy scalar to a JSON-safe Python value."""
    if v is None:
        return None
    if isinstance(v, float) and not math.isfinite(v):
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if hasattr(v, "item"):
        try:
            v = v.item()
        except Exception:
            return v
        if isinstance(v, float) and not math.isfinite(v):
            return None
    return v
