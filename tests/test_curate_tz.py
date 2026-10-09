import pandas as pd
import pytest

from etl import curate, precompute
from etl.points import Point

TAG = "t"
PTS = [
    Point(id="miami", name="Miami", region="mia", lat=25.8, lon=-80.2, elevation_m=2, timezone="America/New_York"),
    Point(id="sofia", name="Sofia", region="sof", lat=42.7, lon=23.3, elevation_m=550, timezone="Europe/Sofia"),
    Point(id="scl", name="Santa Clara", region="scl", lat=37.3, lon=-121.9, elevation_m=25, timezone="America/Los_Angeles"),
]


def _write_raw(root, pts, start, hours):
    ts = pd.date_range(start, periods=hours, freq="h", tz="UTC")
    for p in pts:
        d = root / p.region / p.id / TAG
        d.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({
            "region": p.region, "point": p.id, "ts_utc": ts,
            "is_day": 1, "temperature_2m": 20.0, "apparent_temperature": 20.0,
            "dew_point_2m": 10.0, "relative_humidity_2m": 40.0, "cloud_cover": 10.0,
            "shortwave_radiation": 500.0, "wind_speed_10m": 3.0, "wind_gusts_10m": 6.0,
            "pressure_msl": 1010.0, "precipitation": 0.0, "rain": 0.0, "snowfall": 0.0,
            "sunshine_duration": 3600.0,
        }).to_parquet(d / "chunk.parquet", index=False)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(curate, "RAW_ROOT", tmp_path / "raw")
    monkeypatch.setattr(curate, "RAW_AQ_ROOT", tmp_path / "raw_aq")
    monkeypatch.setattr(curate, "CURATED_DIR", tmp_path / "cur")
    monkeypatch.setattr(curate, "POINTS", PTS)
    monkeypatch.setattr(precompute, "CURATED", tmp_path / "cur")
    return tmp_path


def test_hour_of_day_per_point_timezone(env):
    _write_raw(env / "raw", PTS, "2025-07-01T00:00Z", 48)
    out = pd.read_parquet(curate.build(TAG))
    assert str(out["ts_local"].dtype) == "datetime64[ns]"
    at = pd.Timestamp("2025-07-01T16:00Z")
    row = lambda pid: out[(out["point"] == pid) & (out["ts_utc"] == at)].iloc[0]
    assert row("miami")["ts_local"] == pd.Timestamp("2025-07-01 12:00")
    assert row("miami")["hour_of_day"] == 12
    assert row("sofia")["hour_of_day"] == 19
    assert row("scl")["hour_of_day"] == 9


def test_precompute_daily_rollup_on_naive_ts_local(env):
    _write_raw(env / "raw", PTS[:2], "2025-07-01T00:00Z", 48)
    curate.build(TAG)
    paths = precompute.build(TAG)
    assert len(pd.read_parquet(paths["daily"])) > 0


def test_dst_fall_back_day_does_not_raise(env):
    # 2025-11-02 is the US fall-back day (01:00 local occurs twice).
    _write_raw(env / "raw", PTS, "2025-11-01T12:00Z", 48)
    out = pd.read_parquet(curate.build(TAG))
    assert out["ts_local"].notna().all()
