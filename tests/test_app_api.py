"""API tests for the dashboard server: tag validation, series shape, rollup cache."""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import app.data as data
from app.server import app


def _daily(values: list[float]) -> pd.DataFrame:
    dates = pd.to_datetime(["2024-01-01", "2024-01-02"])
    rows = []
    for region, vals in (("r1", values), ("r2", [1.0, 2.0])):
        for d, v in zip(dates, vals):
            rows.append({"region": region, "local_date": d.date(), "n_points": 3,
                         "stay_outside_hours": v})
    return pd.DataFrame(rows)


@pytest.fixture()
def curated(tmp_path, monkeypatch):
    _daily([5.0, np.nan]).to_parquet(tmp_path / "region_daily_t1.parquet")
    pd.DataFrame({
        "region": ["r1", "r2"],
        "month_start": [pd.Timestamp("2024-01-01").date()] * 2,
        "n_points": [3, 3],
        "stay_outside_hours": [10.0, 20.0],
    }).to_parquet(tmp_path / "region_monthly_t1.parquet")
    monkeypatch.setattr(data, "CURATED", tmp_path)
    data._read.cache_clear()
    return tmp_path


@pytest.fixture()
def client():
    return TestClient(app)


def test_tags(curated, client):
    assert client.get("/api/tags").json() == {"tags": ["t1"]}


def test_metrics_include_better(client):
    ms = client.get("/api/metrics").json()["metrics"]
    assert all("better" in m for m in ms)


def test_series_shape(curated, client):
    r = client.get("/api/series", params={"tag": "t1", "grain": "daily",
                                          "metric": "stay_outside_hours"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"tag", "grain", "metric", "metric_label", "unit", "series", "row_counts"}
    s = body["series"]["r1"]
    assert set(s) == {"label", "x", "y", "n_points"}
    assert s["x"] == ["2024-01-01", "2024-01-02"]
    assert s["y"] == [5.0, None]
    assert s["n_points"] == [3, 3]
    assert body["row_counts"] == {"r1": 2, "r2": 2}


def test_series_monthly(curated, client):
    r = client.get("/api/series", params={"tag": "t1", "grain": "monthly"})
    assert r.status_code == 200
    assert r.json()["series"]["r2"]["y"] == [20.0]


def test_unknown_metric_400(curated, client):
    r = client.get("/api/series", params={"tag": "t1", "metric": "nope"})
    assert r.status_code == 400


@pytest.mark.parametrize("bad", ["../x", "..%2Fx", "missing", "T1", "a/b"])
def test_bad_tag_404(curated, client, bad):
    assert client.get(f"/api/series?tag={bad}").status_code == 404
    assert client.get(f"/api/detail?tag={bad}&grain=daily&bucket=2024-01-01").status_code == 404


def test_cache_rereads_on_mtime_change(curated, client):
    q = {"tag": "t1", "grain": "daily"}
    assert client.get("/api/series", params=q).json()["series"]["r1"]["y"] == [5.0, None]
    path = curated / "region_daily_t1.parquet"
    _daily([7.0, 8.0]).to_parquet(path)
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    assert client.get("/api/series", params=q).json()["series"]["r1"]["y"] == [7.0, 8.0]


def test_cache_bounded_and_hit(curated):
    data.load_rollup("t1", "daily")
    data.load_rollup("t1", "daily")
    info = data._read.cache_info()
    assert info.hits == 1 and info.misses == 1
    assert info.maxsize == 16
