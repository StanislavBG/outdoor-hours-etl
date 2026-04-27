"""Personal Classifier v4 — `stay_outside` (0/1) per profile.

Five profiles span "perfect-day strict" → "all-weather permissive". For
each row we emit `stay_outside_<profile_id>` (int8 0/1). The legacy
`stay_outside` column is kept as an alias for the goldilocks profile so
existing rollups and frontend code that has not yet adopted the profile
key continue to work.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass(frozen=True)
class Profile:
    id: str           # short slug, used in column names
    name: str         # display name
    label: str        # display label with leading icon
    desc: str         # one-line tagline
    cold_c: float
    hot_c: float
    uv_max: float
    rain_max_mm_h: float
    overcast_max_pct: Optional[float]   # None = no constraint
    humidity_max_pct: Optional[float]   # None = no constraint
    aqi_max: Optional[float]            # None = no constraint (US AQI scale 0-500)


PROFILES: list[Profile] = [
    Profile("sun_seeker",   "Sun Seeker",   "🔆 Sun Seeker",
            "Beach-day strict — clear skies, mild temps, low humidity, clean air.",
            15.0, 28.0, 6.0, 0.5, 40.0, 70.0,  50.0),
    Profile("goldilocks",   "Goldilocks",   "☀ Goldilocks",
            "Default. Mild temps, low UV, dry, not overcast, not muggy, AQI ≤ 100.",
            7.0, 30.0, 6.0, 1.0, 85.0, 80.0, 100.0),
    Profile("classic",      "Classic",      "🌤 Classic",
            "The original 4-rule check: daytime, mild temp, safe UV, dry. No air-quality check.",
            7.0, 30.0, 6.0, 1.0, None, None, None),
    Profile("cool_cloudy",  "Cool & Cloudy", "🌥 Cool & Cloudy",
            "Likes brisk overcast days, hates muggy heat. Tolerates moderate AQI.",
            5.0, 22.0, 6.0, 1.5, None, 90.0, 100.0),
    Profile("all_weather",  "All-Weather",  "🥾 All-Weather",
            "Hikes rain-or-shine — only true extremes count, AQI up to 'unhealthy for sensitive groups'.",
            0.0, 35.0, 9.0, 2.0, None, 95.0, 150.0),
]

DEFAULT_PROFILE_ID: str = "goldilocks"

# Backward-compat scalars (mirror goldilocks, the live default).
_GOLDILOCKS = next(p for p in PROFILES if p.id == DEFAULT_PROFILE_ID)
COLD_C: float = _GOLDILOCKS.cold_c
HOT_C: float = _GOLDILOCKS.hot_c
UV_MAX: float = _GOLDILOCKS.uv_max
RAIN_MAX_MM_H: float = _GOLDILOCKS.rain_max_mm_h
OVERCAST_MAX_PCT: float = _GOLDILOCKS.overcast_max_pct or 100.0
HUMIDITY_MAX_PCT: float = _GOLDILOCKS.humidity_max_pct or 100.0


def stay_outside_for(df: pd.DataFrame, profile: Profile) -> pd.Series:
    """Return 0/1 int8 Series for one profile.

    Required columns: is_day, temperature_2m, uv_index_est, precipitation,
    cloud_cover, relative_humidity_2m. Optional: us_aqi (NULL → treated as
    'no constraint' so pre-AQ-coverage history isn't penalized).
    """
    is_day = df["is_day"].fillna(0).astype("int8") == 1
    temp_ok = df["temperature_2m"].between(profile.cold_c, profile.hot_c, inclusive="both")
    uv_ok = df["uv_index_est"] <= profile.uv_max
    rain_ok = df["precipitation"].fillna(0) <= profile.rain_max_mm_h
    out = is_day & temp_ok & uv_ok & rain_ok
    if profile.overcast_max_pct is not None:
        out = out & (df["cloud_cover"].fillna(0) <= profile.overcast_max_pct)
    if profile.humidity_max_pct is not None:
        out = out & (df["relative_humidity_2m"].fillna(0) <= profile.humidity_max_pct)
    if profile.aqi_max is not None and "us_aqi" in df.columns:
        # NULL AQI → unconstrained (pre-coverage history shouldn't fail this rule).
        aqi = df["us_aqi"]
        aqi_ok = aqi.isna() | (aqi <= profile.aqi_max)
        out = out & aqi_ok
    return out.astype("int8")


def stay_outside(df: pd.DataFrame) -> pd.Series:
    """Backward-compat: goldilocks-profile stay_outside."""
    return stay_outside_for(df, _GOLDILOCKS)


def reason(df: pd.DataFrame) -> pd.Series:
    """First failing condition per row, or 'ok' if all pass — goldilocks profile."""
    out = pd.Series("ok", index=df.index, dtype="object")
    night = df["is_day"].fillna(0).astype("int8") != 1
    too_cold = df["temperature_2m"] < COLD_C
    too_hot = df["temperature_2m"] > HOT_C
    high_uv = df["uv_index_est"] > UV_MAX
    too_wet = df["precipitation"].fillna(0) > RAIN_MAX_MM_H
    too_cloudy = df["cloud_cover"].fillna(0) > OVERCAST_MAX_PCT
    too_humid = df["relative_humidity_2m"].fillna(0) > HUMIDITY_MAX_PCT
    out = out.mask(too_humid, "too_humid")
    out = out.mask(too_cloudy, "too_cloudy")
    out = out.mask(too_wet, "too_wet")
    out = out.mask(high_uv, "uv_too_high")
    out = out.mask(too_hot, "too_hot")
    out = out.mask(too_cold, "too_cold")
    out = out.mask(night, "night")
    return out


def apply(df: pd.DataFrame) -> pd.DataFrame:
    """Add stay_outside_<profile> columns + stay_outside alias + temp_f."""
    out = df.copy()
    out["temp_f"] = out["temperature_2m"] * 9.0 / 5.0 + 32.0
    for p in PROFILES:
        out[f"stay_outside_{p.id}"] = stay_outside_for(out, p)
    out["stay_outside"] = out[f"stay_outside_{DEFAULT_PROFILE_ID}"]
    out["stay_outside_reason"] = reason(out)
    return out
