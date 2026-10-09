from __future__ import annotations

from datetime import date

import httpx
import pandas as pd
import pytest

from etl.points import Point
from etl.sources import _client


def _client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _run(handler):
    sleeps: list[float] = []
    with _client_for(handler) as c:
        out = _client.fetch_json(c, "https://example.test/x", {"a": 1}, sleep=sleeps.append)
    return out, sleeps


def test_404_not_retried():
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(404, json={"error": True})

    sleeps: list[float] = []
    with _client_for(handler) as c:
        with pytest.raises(httpx.HTTPStatusError):
            _client.fetch_json(c, "https://example.test/x", {}, sleep=sleeps.append)
    assert len(calls) == 1
    assert sleeps == []


def test_429_retry_after_sleeps_once():
    seq = [httpx.Response(429, headers={"Retry-After": "3"}), httpx.Response(200, json={"ok": 1})]

    out, sleeps = _run(lambda req: seq.pop(0))
    assert out == {"ok": 1}
    assert sleeps == [3]


def test_429_without_retry_after_uses_backoff():
    seq = [httpx.Response(429), httpx.Response(200, json={"ok": 1})]
    out, sleeps = _run(lambda req: seq.pop(0))
    assert out == {"ok": 1}
    assert sleeps == [8]


def test_503_retried():
    seq = [httpx.Response(503), httpx.Response(503), httpx.Response(200, json={"ok": 2})]
    out, sleeps = _run(lambda req: seq.pop(0))
    assert out == {"ok": 2}
    assert sleeps == [8, 16]


def test_gives_up_after_max_attempts():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(500)

    sleeps: list[float] = []
    with _client_for(handler) as c:
        with pytest.raises(httpx.HTTPStatusError):
            _client.fetch_json(c, "https://example.test/x", {}, sleep=sleeps.append)
    assert len(calls) == _client.MAX_ATTEMPTS
    assert len(sleeps) == _client.MAX_ATTEMPTS - 1


def test_day_chunks_boundaries():
    assert _client.day_chunks(date(2024, 1, 1), date(2024, 1, 10), 5) == [
        (date(2024, 1, 1), date(2024, 1, 5)),
        (date(2024, 1, 6), date(2024, 1, 10)),
    ]
    assert _client.day_chunks(date(2024, 1, 1), date(2024, 1, 7), 5) == [
        (date(2024, 1, 1), date(2024, 1, 5)),
        (date(2024, 1, 6), date(2024, 1, 7)),
    ]
    assert _client.day_chunks(date(2024, 1, 1), date(2024, 1, 1), 5) == [(date(2024, 1, 1), date(2024, 1, 1))]
    assert _client.day_chunks(date(2024, 1, 2), date(2024, 1, 1), 5) == []


def test_write_parquet_atomic_ok(tmp_path):
    target = tmp_path / "a.parquet"
    _client.write_parquet_atomic(pd.DataFrame({"x": [1, 2]}), target)
    assert pd.read_parquet(target)["x"].tolist() == [1, 2]
    assert [p.name for p in tmp_path.iterdir()] == ["a.parquet"]


def test_write_parquet_atomic_failure_leaves_nothing(tmp_path, monkeypatch):
    target = tmp_path / "a.parquet"

    def boom(self, path, *a, **k):
        open(path, "wb").write(b"partial")
        raise RuntimeError("disk full")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", boom)
    with pytest.raises(RuntimeError):
        _client.write_parquet_atomic(pd.DataFrame({"x": [1]}), target)
    assert list(tmp_path.iterdir()) == []


def test_to_dataframe_columns():
    payload = {"hourly": {"time": [0, 3600], "v": [1.0, 2.0]}}
    p = Point(id="p1", name="P", region="r1", lat=1.0, lon=2.0, elevation_m=3, timezone="UTC")
    df = _client.to_dataframe(payload, p, {"lat": p.lat})
    assert list(df.columns) == ["region", "point", "ts_utc", "v", "lat"]
    assert str(df["ts_utc"].dt.tz) == "UTC"
