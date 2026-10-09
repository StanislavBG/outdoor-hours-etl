import numpy as np
import pandas as pd
import pytest

from classifier.hourly import region_hourly
from classifier.personal import PROFILES, stay_outside_for

_GOLDILOCKS = next(p for p in PROFILES if p.id == "goldilocks")


def _frame(with_aqi=True):
    rows = []
    for region, n_points in (("a", 3), ("b", 3)):
        for hour in (10, 11):
            for p in range(n_points):
                r = {
                    "ts_local": pd.Timestamp(f"2024-06-01 {hour}:00"),
                    "region": region,
                    "point_id": f"{region}{p}",
                    "is_day": 1,
                    "temperature_2m": 20.0 + p,
                    "uv_index_est": 3.0,
                    "precipitation": 0.0,
                    "cloud_cover": 10.0,
                    "relative_humidity_2m": 40.0,
                    "wind_gusts_10m": 5.0 + p,
                }
                if with_aqi:
                    r["us_aqi"] = 20.0
                rows.append(r)
    return pd.DataFrame(rows)


def test_two_regions_three_points_two_hours():
    out = region_hourly(_frame())
    assert len(out) == 4
    assert list(out["region"]) == ["a", "a", "b", "b"] or list(out["region"]) == ["a", "b", "a", "b"]
    assert out.sort_values(["ts_local", "region"]).index.tolist() == list(out.index)
    assert (out["n_points"] == 3).all()
    assert (out["stay_outside_pts"] == 3).all()
    assert (out["ok_day"] == 1).all()
    assert (out["wind_gusts_10m"] == 7.0).all()
    assert out["temperature_2m"].iloc[0] == pytest.approx(21.0)
    for c in ("stay_outside_pts", "n_points", "ok_day"):
        assert pd.api.types.is_integer_dtype(out[c])


def test_single_point_region():
    df = _frame()
    df = df[~((df["region"] == "b") & (df["point_id"] != "b0"))]
    out = region_hourly(df)
    b = out[out["region"] == "b"]
    assert (b["n_points"] == 1).all()
    assert (out[out["region"] == "a"]["n_points"] == 3).all()


def test_missing_optional_columns_are_nan():
    df = _frame(with_aqi=False).drop(columns=["cloud_cover", "wind_gusts_10m"])
    out = region_hourly(df)
    assert out["us_aqi"].isna().all()
    assert out["cloud_cover"].isna().all()
    assert out["wind_gusts_10m"].isna().all()
    assert (out["stay_outside_pts"] == 3).all()


def test_does_not_mutate_input():
    df = _frame(with_aqi=False)
    before = df.copy()
    region_hourly(df)
    pd.testing.assert_frame_equal(df, before)


def test_aqi_only_failure_counts_zero_under_goldilocks():
    df = _frame()
    df["us_aqi"] = 150.0
    out = region_hourly(df)
    assert (out["stay_outside_pts"] == 0).all()
    assert (out["ok_day"] == 1).all()


def test_missing_required_column_raises():
    with pytest.raises(ValueError, match="uv_index_est"):
        region_hourly(_frame().drop(columns=["uv_index_est"]))


def test_parity_with_per_point_stay_outside():
    df = _frame()
    df.loc[::4, "temperature_2m"] = 40.0
    out = region_hourly(df)
    per_point = stay_outside_for(df, _GOLDILOCKS)
    for region, g in out.groupby("region"):
        expected = per_point[df["region"] == region].mean()
        assert g["stay_outside_pts"].sum() / g["n_points"].sum() == pytest.approx(expected)
