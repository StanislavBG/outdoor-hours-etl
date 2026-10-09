"""Offline tests for defensive body parsing, the quota exit code, and --piece-days."""
from __future__ import annotations

from datetime import date

import httpx
import pytest

import etl.sources.open_meteo as om
import etl.sources.open_meteo_aq as aq
from etl import sync
from etl.points import Point
from etl.sources import _client

D = date.fromisoformat


def _pt(pid="p1", region="r1"):
    return Point(id=pid, name=pid, region=region, lat=1.0, lon=2.0, elevation_m=3, timezone="UTC")


def _fetch(handler):
    sleeps: list[float] = []
    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        out = _client.fetch_json(c, "https://example.test/x", {}, sleep=sleeps.append)
    return out, sleeps


def test_error_classes_shared():
    assert om.FetchBodyError is _client.FetchBodyError
    assert om.RateLimitExhausted is _client.RateLimitExhausted
    assert aq.RateLimitExhausted is om.RateLimitExhausted


@pytest.mark.parametrize("bad", [b"", b"<html>throttled</html>"])
def test_non_json_2xx_is_retried(bad):
    seq = [httpx.Response(200, content=bad, headers={"Content-Type": "text/html"}),
           httpx.Response(200, json={"hourly": {}})]
    calls = []

    def handler(req):
        calls.append(req)
        return seq[len(calls) - 1]

    out, sleeps = _fetch(handler)
    assert out == {"hourly": {}}
    assert len(calls) == 2 and len(sleeps) == 1


def test_non_json_exhausts_with_diagnostics():
    def handler(req):
        return httpx.Response(200, content=b"x" * 500, headers={"Content-Type": "text/plain"})

    with pytest.raises(_client.FetchBodyError) as ei:
        _fetch(handler)
    msg = str(ei.value)
    assert "200" in msg and "text/plain" in msg and "x" * 200 in msg and "x" * 201 not in msg


def test_generic_error_body_is_retried_as_body_error():
    seq = [httpx.Response(200, json={"error": True, "reason": "Something odd"}),
           httpx.Response(200, json={"ok": 1})]
    calls = []

    def handler(req):
        calls.append(req)
        return seq[len(calls) - 1]

    out, _ = _fetch(handler)
    assert out == {"ok": 1} and len(calls) == 2


def test_limit_exceeded_not_retried():
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(200, json={"error": True, "reason": "Daily API request limit exceeded"})

    with pytest.raises(_client.RateLimitExhausted, match="Daily API request limit exceeded"):
        _fetch(handler)
    assert len(calls) == 1


def test_sync_main_returns_75_on_rate_limit(monkeypatch, capsys):
    t = sync.Task("weather", _pt(), D("2020-01-01"), D("2020-01-10"))
    monkeypatch.setattr(sync, "plan_tasks", lambda *a, **k: [t])

    def boom(*a, **k):
        raise _client.RateLimitExhausted("Hourly API request limit exceeded")

    monkeypatch.setattr(om, "download", boom)
    assert sync.main([]) == 75
    assert "RATE_LIMITED" in capsys.readouterr().out


def test_sync_main_generic_halt_is_1(monkeypatch):
    t = sync.Task("weather", _pt(), D("2020-01-01"), D("2020-01-10"))
    monkeypatch.setattr(sync, "plan_tasks", lambda *a, **k: [t])
    monkeypatch.setattr(om, "download", lambda *a, **k: (_ for _ in ()).throw(ValueError("x")))
    assert sync.main([]) == 1


def test_piece_days_plans_smaller_tasks_and_coverage(tmp_path, monkeypatch):
    monkeypatch.setattr(om, "RAW_DIR", tmp_path)
    monkeypatch.setattr(sync, "WEATHER_START", D("2021-04-24"))
    p = _pt()
    target = D("2022-04-23")  # 365-day gap
    assert len(sync.plan_tasks([p], ["weather"], target)) == 1
    tasks = sync.plan_tasks([p], ["weather"], target, piece_days=92)
    assert len(tasks) == 4
    assert all((t.end - t.start).days + 1 <= 92 for t in tasks)
    d = tmp_path / p.region / p.id / sync.TAG
    d.mkdir(parents=True)
    for t in tasks:
        (d / f"{t.start}_{t.end}.parquet").write_bytes(b"")
    assert sync.plan_tasks([p], ["weather"], target) == []


def test_piece_days_passed_as_max_days(monkeypatch):
    t = sync.Task("weather", _pt(), D("2020-01-01"), D("2020-01-10"))
    monkeypatch.setattr(sync, "plan_tasks", lambda *a, **k: [t])
    seen = {}
    monkeypatch.setattr(om, "download", lambda *a, **k: seen.update(k))
    assert sync.main(["--piece-days", "31"]) == 0
    assert seen["max_days_per_call"] == 31
