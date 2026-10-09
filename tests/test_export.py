import json

import pandas as pd
import pytest

from etl.catalog import METRICS
from etl.points import REGIONS
from scripts import export_outdoor_hours as exp

REGION = next(iter(REGIONS))


def _write_tag(curated, tag):
    base = {
        "region": [REGION, REGION],
        "n_points": [3, 3],
        "stay_outside_hours": [5.0, float("nan")],
        "pct_daytime_outside": [40.0, 50.0],
        "temperature_2m_mean": [10.0, 12.0],
    }
    pd.DataFrame({**base, "local_date": pd.to_datetime(["2024-01-01", "2024-01-02"])}).to_parquet(
        curated / f"region_daily_{tag}.parquet")
    pd.DataFrame({**base, "month_start": pd.to_datetime(["2024-01-01", "2024-02-01"])}).to_parquet(
        curated / f"region_monthly_{tag}.parquet")
    pd.DataFrame({**base, "year": [2023, 2024]}).to_parquet(
        curated / f"region_yearly_{tag}.parquet")


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    curated = tmp_path / "curated"
    out = tmp_path / "out"
    curated.mkdir()
    monkeypatch.setattr(exp, "CURATED", curated)
    monkeypatch.setattr(exp, "OUT", out)
    return curated, out


def test_payload_metrics_and_nan_null(dirs):
    curated, out = dirs
    out.mkdir()
    _write_tag(curated, "last1y")
    exp.export_payload("last1y", {})
    payload = json.loads((out / "last1y.json").read_text())
    assert payload["metrics"] == METRICS
    series = payload["grains"]["daily"]["regions"][REGION]["series"]
    assert series["stay_outside_hours"] == [5.0, None]


def test_main_exits_1_on_corrupt_tag_but_writes_good_one(dirs, monkeypatch, capsys):
    curated, out = dirs
    _write_tag(curated, "last1y")
    _write_tag(curated, "last5y")
    (curated / "region_daily_last5y.parquet").write_bytes(b"garbage")
    monkeypatch.setattr(exp, "export_hourly_months", lambda tag: 0)
    with pytest.raises(SystemExit) as ei:
        exp.main()
    assert ei.value.code == 1
    assert (out / "last1y.json").exists()
    assert "export last5y failed:" in capsys.readouterr().out


def test_main_returns_none_when_all_succeed(dirs, monkeypatch):
    curated, out = dirs
    _write_tag(curated, "last1y")
    monkeypatch.setattr(exp, "export_hourly_months", lambda tag: 0)
    assert exp.main() is None
    assert (out / "last1y.json").exists()


def _write_hourly(curated, tag, with_optional=True):
    idx = pd.date_range("2024-01-31 22:00", periods=6, freq="h")
    rows = []
    for ts in idx:
        for p in range(3):
            rows.append({
                "ts_local": ts, "region": REGION, "point_id": f"p{p}",
                "is_day": 1 if p < 2 else 0,
                "temperature_2m": 18.0 + p, "uv_index_est": 2.0, "precipitation": 0.0,
                "cloud_cover": 20.0, "wind_gusts_10m": 5.0 + p,
                **({"relative_humidity_2m": 50.0, "us_aqi": 40.0 + 70 * (p == 1)}
                   if with_optional else {}),
            })
    rows[0]["cloud_cover"] = float("nan")
    df = pd.DataFrame(rows)
    df.to_parquet(curated / f"hourly_{tag}.parquet")
    return df


def test_hourly_months_shape_nan_and_ts(dirs):
    curated, out = dirs
    _write_hourly(curated, "last1y")
    assert exp.export_hourly_months("last1y") == 2
    jan = json.loads((out / "hourly" / "2024-01.json").read_text())
    assert jan["month"] == "2024-01"
    ts = [r["ts"] for r in jan["rows"]]
    assert ts == sorted(ts)
    assert ts[0] == pd.Timestamp("2024-01-31 22:00").isoformat() == "2024-01-31T22:00:00"
    reg = jan["rows"][0][REGION]
    assert set(reg) == {"stay_outside_pts", "n_points", "ok_day", "temperature_2m",
                        "uv_index_est", "precipitation", "cloud_cover",
                        "relative_humidity_2m", "us_aqi", "wind_gusts_10m"}
    assert reg["n_points"] == 3 and isinstance(reg["stay_outside_pts"], int)
    assert reg["cloud_cover"] == 20.0  # NaN point ignored by mean
    feb = json.loads((out / "hourly" / "2024-02.json").read_text())
    assert feb["rows"][0]["ts"] == "2024-02-01T00:00:00"


def test_hourly_nan_becomes_null_and_missing_columns(dirs):
    curated, out = dirs
    df = _write_hourly(curated, "last1y", with_optional=False)
    df.loc[df["ts_local"] == df["ts_local"].min(), "cloud_cover"] = float("nan")
    df.to_parquet(curated / "hourly_last1y.parquet")
    exp.export_hourly_months("last1y")
    reg = json.loads((out / "hourly" / "2024-01.json").read_text())["rows"][0][REGION]
    assert reg["cloud_cover"] is None
    assert reg["us_aqi"] is None and reg["relative_humidity_2m"] is None


def test_hourly_parity_with_per_point_classifier(dirs):
    from classifier.personal import DEFAULT_PROFILE_ID, PROFILES, stay_outside_for
    curated, out = dirs
    raw = _write_hourly(curated, "last1y")
    exp.export_hourly_months("last1y")
    profile = next(p for p in PROFILES if p.id == DEFAULT_PROFILE_ID)
    raw = raw.assign(stay=stay_outside_for(raw, profile).astype(int),
                     day=raw["ts_local"].dt.date)
    expected = (raw.groupby("day")["stay"].sum() / raw.groupby("day")["point_id"].nunique()
                / 1).rename("exp")
    got = {}
    for f in (out / "hourly").glob("*.json"):
        for r in json.loads(f.read_text())["rows"]:
            reg = r[REGION]
            d = pd.Timestamp(r["ts"]).date()
            got[d] = got.get(d, 0) + reg["stay_outside_pts"] / reg["n_points"]
    for d, v in got.items():
        assert v == pytest.approx(expected.loc[d])
    assert any(v > 0 for v in got.values())
