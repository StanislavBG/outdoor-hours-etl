import json
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from etl import health, sync
from etl.points import Point

TODAY = date(2026, 10, 9)


def _pt(pid, region):
    return Point(id=pid, name=pid, region=region, lat=1.0, lon=2.0, elevation_m=3, timezone="UTC")


POINTS = [_pt("a1", "alpha"), _pt("a2", "alpha"), _pt("b1", "beta")]


def _chunk(root, source, pt, start, end):
    sub = "open_meteo" if source == "weather" else "open_meteo_aq"
    d = root / "data" / "raw" / sub / pt.region / pt.id / sync.TAG
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{start}_{end}.parquet").write_bytes(b"")


def _fill_raw(root, points=POINTS):
    for p in points:
        _chunk(root, "weather", p, sync.WEATHER_START, TODAY)
        _chunk(root, "aq", p, sync.AQ_START, TODAY)


def _curated(root, last_by_region):
    rows = []
    for region, last in last_by_region.items():
        for ts in (last - timedelta(hours=2), last):
            rows.append({"region": region, "point": region + "1", "ts_utc": pd.Timestamp(ts)})
    d = root / "data" / "curated"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(d / "hourly_last10y.parquet")


def _status(root, **over):
    st = {"ts": "2026-10-08T03:00:00-07:00", "ok": True, "failed_step": None,
          "published": True, "log": "x.log"}
    st.update(over)
    d = root / "logs" / "weekly"
    d.mkdir(parents=True, exist_ok=True)
    (d / "last_status.json").write_text(json.dumps(st))


def _bundle(bilko, days_old=1):
    bilko.mkdir(parents=True, exist_ok=True)
    pub = datetime(2026, 10, 9, 12, tzinfo=timezone.utc) - timedelta(days=days_old)
    (bilko / "last1m.json").write_text(json.dumps({"pubdate": pub.isoformat()}))


def _healthy(tmp_path):
    root, bilko = tmp_path / "root", tmp_path / "bilko"
    _fill_raw(root)
    last = datetime(2026, 10, 3, 23)
    _curated(root, {"alpha": last, "beta": last})
    _status(root)
    _bundle(bilko)
    return root, bilko


def _run(root, bilko, **kw):
    return health.collect(root, bilko, 14, today=TODAY, points=POINTS, **kw)


def test_healthy(tmp_path):
    root, bilko = _healthy(tmp_path)
    rep = _run(root, bilko)
    assert rep["failures"] == []
    assert rep["regions"]["alpha"]["points"] == 2
    assert rep["regions"]["alpha"]["gaps"] == {"weather": 0, "aq": 0}
    assert rep["regions"]["alpha"]["days_stale"] == 6
    assert rep["status"]["ok"] is True


def test_raw_gap(tmp_path):
    root, bilko = _healthy(tmp_path)
    for f in (root / "data/raw/open_meteo/beta/b1/last10y").iterdir():
        f.unlink()
    _chunk(root, "weather", POINTS[2], sync.WEATHER_START, date(2026, 1, 1))
    rep = _run(root, bilko)
    assert rep["regions"]["beta"]["gaps"]["weather"] >= 1
    assert any("gap" in f and "beta" in f for f in rep["failures"])


def test_stale_curated(tmp_path):
    root, bilko = _healthy(tmp_path)
    _curated(root, {"alpha": datetime(2026, 10, 3, 23), "beta": datetime(2026, 9, 1)})
    rep = _run(root, bilko)
    assert len(rep["failures"]) == 1 and "beta" in rep["failures"][0]


def test_curated_boundary_ok(tmp_path):
    root, bilko = _healthy(tmp_path)
    _curated(root, {"alpha": datetime(2026, 9, 20), "beta": datetime(2026, 9, 20)})  # 19 days
    assert _run(root, bilko)["failures"] == []


def test_missing_curated(tmp_path):
    root, bilko = _healthy(tmp_path)
    (root / "data/curated/hourly_last10y.parquet").unlink()
    assert any("curated" in f for f in _run(root, bilko)["failures"])


def test_status_failed(tmp_path):
    root, bilko = _healthy(tmp_path)
    _status(root, ok=False, failed_step="publish", published=False)
    fails = _run(root, bilko)["failures"]
    assert len(fails) == 1 and "publish" in fails[0]


def test_status_missing(tmp_path):
    root, bilko = _healthy(tmp_path)
    (root / "logs/weekly/last_status.json").unlink()
    assert any("status" in f for f in _run(root, bilko)["failures"])


def test_stale_pubdate(tmp_path):
    root, bilko = _healthy(tmp_path)
    _bundle(bilko, days_old=30)
    assert any("pubdate" in f for f in _run(root, bilko)["failures"])


def test_missing_bundle(tmp_path):
    root, bilko = _healthy(tmp_path)
    (bilko / "last1m.json").unlink()
    assert any("pubdate" in f for f in _run(root, bilko)["failures"])


def test_main_exit_codes_and_json(tmp_path, monkeypatch, capsys):
    root, bilko = _healthy(tmp_path)
    monkeypatch.setattr(health, "POINTS", POINTS)
    monkeypatch.setattr(health, "_today", lambda: TODAY)
    assert health.main(["--root", str(root), "--bilko-dir", str(bilko)]) == 0
    assert "HEALTHY" in capsys.readouterr().out
    assert health.main(["--root", str(root), "--bilko-dir", str(bilko), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["failures"] == []
    _status(root, ok=False, failed_step="sync")
    assert health.main(["--root", str(root), "--bilko-dir", str(bilko)]) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out and "HEALTHY" not in out
