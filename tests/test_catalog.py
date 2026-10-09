from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from etl import catalog
from etl.catalog import METRIC_KEYS, METRICS, X_COL, json_scalar, metric

HIGHER = {"stay_outside_hours", "pct_daytime_outside", "sunshine_hours"}
LOWER = {
    "precipitation_sum", "cloud_cover_mean", "wind_gusts_10m_max",
    "relative_humidity_2m_mean", "us_aqi_mean", "us_aqi_max", "pm2_5_mean",
}


def test_unique_keys_and_count():
    keys = [m["key"] for m in METRICS]
    assert len(keys) == len(set(keys)) == 17
    assert METRIC_KEYS == frozenset(keys)


def test_better_values_valid_and_assigned():
    for m in METRICS:
        assert m["better"] in ("higher", "lower", None)
        expected = "higher" if m["key"] in HIGHER else "lower" if m["key"] in LOWER else None
        assert m["better"] == expected


def test_profile_aware_only_first_two():
    aware = [m["key"] for m in METRICS if m.get("profile_aware")]
    assert aware == ["stay_outside_hours", "pct_daytime_outside"]


def test_metric_lookup_and_keyerror():
    assert metric("us_aqi_max")["label"] == "Worst-hour AQI"
    with pytest.raises(KeyError):
        metric("nope")


def test_x_col():
    assert X_COL == {"daily": "local_date", "monthly": "month_start", "yearly": "year"}


@pytest.mark.parametrize("v", [None, float("nan"), pd.NaT, pd.NA, float("inf"), float("-inf"),
                               np.float64("nan"), np.float64("inf")])
def test_json_scalar_nullish(v):
    assert json_scalar(v) is None


def test_json_scalar_dates():
    assert json_scalar(datetime(2024, 1, 2, 3, 4)) == "2024-01-02T03:04:00"
    assert json_scalar(date(2024, 1, 2)) == "2024-01-02"
    assert json_scalar(pd.Timestamp("2024-01-02")) == "2024-01-02T00:00:00"


def test_json_scalar_numpy():
    r = json_scalar(np.int64(5))
    assert r == 5 and type(r) is int
    r = json_scalar(np.float64(1.5))
    assert r == 1.5 and type(r) is float


def test_json_scalar_passthrough():
    assert json_scalar("x") == "x"
    assert json_scalar(3) == 3
    assert json_scalar(2.5) == 2.5
    assert json_scalar(True) is True
