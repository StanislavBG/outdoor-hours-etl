import numpy as np
import pandas as pd
import pytest

from classifier.personal import (
    PROFILES,
    apply,
    reason,
    reason_for,
    stay_outside_for,
)

_PROFILE = {p.id: p for p in PROFILES}

# is_day, temp, uv, precip, cloud, humidity, aqi
_OK = (1, 20.0, 3.0, 0.0, 10.0, 40.0, 20.0)


def _row(**kw):
    cols = ["is_day", "temperature_2m", "uv_index_est", "precipitation",
            "cloud_cover", "relative_humidity_2m", "us_aqi"]
    row = dict(zip(cols, _OK))
    row.update(kw)
    return row


def _frame() -> pd.DataFrame:
    rows = [
        _row(),
        _row(is_day=0),
        _row(temperature_2m=-5.0),
        _row(temperature_2m=40.0),
        _row(uv_index_est=10.0),
        _row(precipitation=5.0),
        _row(cloud_cover=95.0),
        _row(relative_humidity_2m=99.0),
        _row(us_aqi=120.0),
        _row(us_aqi=300.0),
        _row(us_aqi=np.nan),
        _row(is_day=np.nan, precipitation=np.nan, cloud_cover=np.nan,
             relative_humidity_2m=np.nan),
    ]
    return pd.DataFrame(rows)


@pytest.mark.parametrize("profile", PROFILES, ids=lambda p: p.id)
def test_reason_ok_iff_stay_outside(profile):
    df = _frame()
    ok = reason_for(df, profile) == "ok"
    stay = stay_outside_for(df, profile) == 1
    assert (ok == stay).all()


def test_aqi_only_failure_by_profile():
    df = pd.DataFrame([_row(us_aqi=120.0)])
    assert reason_for(df, _PROFILE["goldilocks"]).iloc[0] == "aqi_too_high"
    assert reason_for(df, _PROFILE["classic"]).iloc[0] == "ok"
    assert reason(df).iloc[0] == "aqi_too_high"


def test_null_aqi_never_aqi_too_high():
    df = pd.DataFrame([_row(us_aqi=np.nan)])
    for p in PROFILES:
        assert reason_for(df, p).iloc[0] != "aqi_too_high"
    assert reason_for(df.drop(columns="us_aqi"), _PROFILE["goldilocks"]).iloc[0] == "ok"


def test_precedence_first_match_wins():
    df = pd.DataFrame([_row(is_day=0, temperature_2m=40.0, us_aqi=300.0)])
    assert reason_for(df, _PROFILE["goldilocks"]).iloc[0] == "night"
    df = pd.DataFrame([_row(relative_humidity_2m=99.0, us_aqi=300.0)])
    assert reason_for(df, _PROFILE["goldilocks"]).iloc[0] == "too_humid"


def test_apply_without_reason():
    df = _frame()
    full = apply(df)
    slim = apply(df, with_reason=False)
    assert "stay_outside_reason" in full.columns
    assert "stay_outside_reason" not in slim.columns
    assert list(slim.columns) == [c for c in full.columns if c != "stay_outside_reason"]
