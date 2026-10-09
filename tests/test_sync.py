from datetime import date, timedelta

import pytest

import etl.sources.open_meteo as om
import etl.sources.open_meteo_aq as aq
from etl import sync
from etl.points import Point

D = date.fromisoformat


def _pt(pid="p1", region="r1"):
    return Point(id=pid, name=pid, region=region, lat=1.0, lon=2.0, elevation_m=3, timezone="UTC")


def _touch(root, pt, start, end, tag=sync.TAG):
    d = root / pt.region / pt.id / tag
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{start}_{end}.parquet").write_bytes(b"")


# --- missing_ranges -------------------------------------------------------

def test_missing_empty():
    assert sync.missing_ranges([], D("2020-01-01"), D("2020-01-10")) == [(D("2020-01-01"), D("2020-01-10"))]


def test_missing_full():
    assert sync.missing_ranges([(D("2019-12-01"), D("2020-02-01"))], D("2020-01-01"), D("2020-01-10")) == []


def test_missing_interior_hole():
    cov = [(D("2020-01-01"), D("2020-01-03")), (D("2020-01-08"), D("2020-01-10"))]
    assert sync.missing_ranges(cov, D("2020-01-01"), D("2020-01-10")) == [(D("2020-01-04"), D("2020-01-07"))]


def test_missing_adjacent_merge():
    cov = [(D("2020-01-01"), D("2020-01-05")), (D("2020-01-06"), D("2020-01-10"))]
    assert sync.missing_ranges(cov, D("2020-01-01"), D("2020-01-10")) == []


def test_missing_overlap():
    cov = [(D("2020-01-01"), D("2020-01-06")), (D("2020-01-04"), D("2020-01-08"))]
    assert sync.missing_ranges(cov, D("2020-01-01"), D("2020-01-10")) == [(D("2020-01-09"), D("2020-01-10"))]


# --- covered_ranges -------------------------------------------------------

def test_covered_ignores_junk(tmp_path):
    (tmp_path / "2020-01-01_2020-01-05.parquet").write_bytes(b"")
    (tmp_path / "notes.txt").write_bytes(b"")
    (tmp_path / "junk.parquet").write_bytes(b"")
    (tmp_path / "2020-01-01_2020-01-05.parquet.tmp").write_bytes(b"")
    assert sync.covered_ranges(tmp_path) == [(D("2020-01-01"), D("2020-01-05"))]
    assert sync.covered_ranges(tmp_path / "absent") == []


# --- plan_tasks -----------------------------------------------------------

def test_plan_splits_five_year_hole(tmp_path, monkeypatch):
    monkeypatch.setattr(om, "RAW_DIR", tmp_path / "om")
    monkeypatch.setattr(aq, "RAW_DIR", tmp_path / "aq")
    pt = _pt()
    target = D("2026-06-03")
    _touch(om.RAW_DIR, pt, "2016-04-20", "2021-04-23")
    _touch(om.RAW_DIR, pt, "2026-04-28", "2026-06-03")
    tasks = sync.plan_tasks([pt], ["weather"], target)
    assert tasks[0].start == D("2021-04-24")
    assert tasks[-1].end == D("2026-04-27")
    assert len(tasks) == 6  # 1832 days = 5*365 + 7
    for t in tasks:
        assert (t.end - t.start).days + 1 <= sync.PIECE_DAYS
    for a, b in zip(tasks, tasks[1:]):
        assert b.start == a.end + timedelta(days=1)


def test_plan_aq_window(tmp_path, monkeypatch):
    monkeypatch.setattr(om, "RAW_DIR", tmp_path / "om")
    monkeypatch.setattr(aq, "RAW_DIR", tmp_path / "aq")
    tasks = sync.plan_tasks([_pt()], ["aq"], D("2022-09-10"))
    assert [(t.source, t.start, t.end) for t in tasks] == [("aq", sync.AQ_START, D("2022-09-10"))]


# --- CLI ------------------------------------------------------------------

@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(om, "RAW_DIR", tmp_path / "om")
    monkeypatch.setattr(aq, "RAW_DIR", tmp_path / "aq")
    pts = [_pt("p1"), _pt("p2")]
    monkeypatch.setattr(sync, "POINTS", pts)
    calls = []

    def make(root):
        def fake(point, start, end, *, tag, max_days_per_call, inter_call_delay_s, **kw):
            calls.append((point.id, start, end))
            _touch(root, point, start, end, tag)
            return []
        return fake

    monkeypatch.setattr(om, "download", make(om.RAW_DIR))
    monkeypatch.setattr(aq, "download", make(aq.RAW_DIR))
    return pts, calls


ARGS = ["--target", "2022-09-30", "--delay", "0"]


def test_check_exit_codes(env, capsys):
    pts, calls = env
    assert sync.main(ARGS + ["--check"]) == 1
    assert "p1" in capsys.readouterr().out
    assert calls == []
    assert sync.main(ARGS + ["--source", "aq"]) == 0  # fill AQ only
    assert sync.main(ARGS + ["--check", "--source", "aq"]) == 0


def test_dry_run_fetches_nothing(env):
    _, calls = env
    assert sync.main(ARGS + ["--dry-run"]) == 0
    assert calls == []


def test_unknown_point_exits_2(env):
    assert sync.main(ARGS + ["--points", "nope"]) == 2


def test_max_requests_stops_and_resumes(env):
    _, calls = env
    assert sync.main(ARGS + ["--source", "aq", "--max-requests", "1"]) == 0
    assert len(calls) == 1
    assert sync.main(ARGS + ["--source", "aq"]) == 0
    assert len(calls) == 2


def test_halt_path(env, monkeypatch, capsys):
    _, calls = env

    def boom(point, start, end, **kw):
        raise RuntimeError("429 forever")

    monkeypatch.setattr(aq, "download", boom)
    assert sync.main(ARGS + ["--source", "aq"]) == 1
    out = capsys.readouterr().out
    assert "HALT: aq p1 2022-09-01..2022-09-30: 429 forever — rerun to resume" in out
