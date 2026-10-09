"""Drill-down tests: hourly/daily/monthly detail, regions filter, default_profile."""
from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import app.data as data
from app.server import app
from etl.points import REGIONS

R1, R2 = list(REGIONS)[:2]
# registry order is the reverse of request order below on purpose
GOOD = dict(is_day=1, temperature_2m=20.0, uv_index_est=2.0, precipitation=0.0,
            cloud_cover=10.0, relative_humidity_2m=40.0, wind_gusts_10m=3.0)


def _hourly() -> pd.DataFrame:
    rows = []
    for h in (9, 10):
        ts = pd.Timestamp(f"2024-03-05 {h:02d}:00")
        base = dict(ts_local=ts, year=2024, month=3, day=5)
        # R1: 2 points, one passes; AQI-only failure on the other
        rows.append({**GOOD, **base, "region": R1, "point": "a", "us_aqi": 10.0 if h == 9 else 400.0})
        rows.append({**GOOD, **base, "region": R1, "point": "b", "us_aqi": 400.0})
        # R2: single point, passes
        rows.append({**GOOD, **base, "region": R2, "point": "a", "us_aqi": 10.0})
    other = pd.Timestamp("2024-03-06 09:00")
    rows.append({**GOOD, "ts_local": other, "year": 2024, "month": 3, "day": 6,
                 "region": R1, "point": "a", "us_aqi": 10.0})
    return pd.DataFrame(rows)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    _hourly().to_parquet(tmp_path / "hourly_t1.parquet")
    dates = [pd.Timestamp("2024-03-05").date(), pd.Timestamp("2024-03-06").date(),
             pd.Timestamp("2024-04-01").date()]
    pd.DataFrame([
        {"region": r, "local_date": d, "n_points": 2, "stay_outside_hours": 5.0}
        for r in (R1, R2) for d in dates
    ]).to_parquet(tmp_path / "region_daily_t1.parquet")
    pd.DataFrame([
        {"region": r, "year": y, "month": m, "month_start": pd.Timestamp(y, m, 1).date(),
         "n_points": 2, "stay_outside_hours": 7.0}
        for r in (R1, R2) for y, m in ((2024, 3), (2024, 4), (2023, 12))
    ]).to_parquet(tmp_path / "region_monthly_t1.parquet")
    monkeypatch.setattr(data, "CURATED", tmp_path)
    data._read.cache_clear()
    return TestClient(app)


def _get(client, **kw):
    return client.get("/api/detail", params={"tag": "t1", **kw})


def test_hourly_drill(client):
    r = _get(client, grain="daily", bucket="2024-03-05")
    assert r.status_code == 200
    b = r.json()
    assert set(b) == {"tag", "grain", "bucket", "detail_grain", "columns", "regions",
                      "region_registry", "region_order", "x_key", "rows", "n_rows"}
    assert b["detail_grain"] == "hourly" and b["x_key"] == "ts_local"
    assert b["n_rows"] == len(b["rows"]) == 2
    row = b["rows"][0]
    assert row["_x"].startswith("2024-03-05T09")
    assert row[R1]["n_points"] == 2 and row[R2]["n_points"] == 1
    assert row[R2]["stay_outside_pts"] == 1


def test_aqi_only_failures_count_zero(client):
    row = _get(client, grain="daily", bucket="2024-03-05").json()["rows"][0]
    # R1 has two points: the AQI-400 point fails, the other passes
    assert row[R1]["stay_outside_pts"] == 1
    later = _get(client, grain="daily", bucket="2024-03-05").json()["rows"][1]
    assert later[R1]["stay_outside_pts"] == 0 and later[R1]["temperature_2m"] == 20.0


def test_regions_filter(client):
    b = _get(client, grain="daily", bucket="2024-03-05", regions=f"{R2},{R1}").json()
    assert b["region_order"] == [r for r in REGIONS if r in (R1, R2)]
    b = _get(client, grain="daily", bucket="2024-03-05", regions=R2).json()
    assert b["region_order"] == [R2] and list(b["region_registry"]) == [R2]
    assert R1 not in b["rows"][0] and R2 in b["rows"][0]


def test_regions_filter_monthly(client):
    b = _get(client, grain="monthly", bucket="2024-03-01", regions=R1).json()
    assert b["detail_grain"] == "daily" and b["n_rows"] == 2
    assert all(R2 not in r for r in b["rows"])


def test_unknown_region_400(client):
    assert _get(client, grain="daily", bucket="2024-03-05", regions="nope").status_code == 400


@pytest.mark.parametrize("grain,bucket", [("daily", "x"), ("monthly", "bad"), ("yearly", "20x4")])
def test_bad_bucket_400(client, grain, bucket):
    assert _get(client, grain=grain, bucket=bucket).status_code == 400


def test_monthly_drill(client):
    b = _get(client, grain="monthly", bucket="2024-03-01").json()
    assert b["detail_grain"] == "daily" and b["x_key"] == "local_date"
    assert [r["_x"] for r in b["rows"]] == ["2024-03-05", "2024-03-06"]
    assert b["rows"][0][R1]["stay_outside_hours"] == 5.0


def test_yearly_drill_does_not_mutate_cache(client):
    b = _get(client, grain="yearly", bucket="2024").json()
    assert b["detail_grain"] == "monthly" and b["x_key"] == "month_label"
    assert [r["_x"] for r in b["rows"]] == ["2024-03", "2024-04"]
    assert "month_label" not in data.load_rollup("t1", "monthly").columns


def test_no_hourly_file_404(client, tmp_path):
    (tmp_path / "hourly_t1.parquet").unlink()
    assert _get(client, grain="daily", bucket="2024-03-05").status_code == 404


def test_default_profile(client):
    p = client.get("/api/metrics").json()["default_profile"]
    assert {"id", "name", "label", "desc", "rule"} <= set(p)
    assert set(p["rule"]) == {"temp_min_c", "temp_max_c", "temp_min_f", "temp_max_f", "uv_max",
                              "rain_max_mm_h", "cloud_max_pct", "humidity_max_pct", "aqi_max"}
