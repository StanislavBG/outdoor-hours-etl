import shutil
import subprocess

import pytest

from etl import add_region, points as points_mod, sync

MIAMI = {"name": "Miami", "latitude": 25.77427, "longitude": -80.19366,
         "elevation": 1.4, "timezone": "America/New_York"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    f = tmp_path / "regions.yaml"
    shutil.copy(points_mod.REGIONS_YAML, f)
    calls = {"sync": [], "run": []}

    def fake_sync(argv):
        calls["sync"].append(argv)
        return 0

    monkeypatch.setattr(sync, "main", fake_sync)
    monkeypatch.setattr(add_region, "geocode", lambda place: MIAMI)
    monkeypatch.setattr(add_region, "lookup_meta", lambda lat, lon: (2, "America/New_York"))
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, *a, **k: calls["run"].append(cmd) or subprocess.CompletedProcess(cmd, 0),
    )
    return f, calls


def base(f, *extra):
    return ["--region-id", "miami_fl", "--label", "Miami, FL", "--short", "MIA",
            "--regions-file", str(f), *extra]


def test_happy_path_place(env):
    f, calls = env
    assert add_region.main(base(f, "--place", "Miami, Florida, United States")) == 0
    _, regions = points_mod.load_registry(f)
    pts, _ = points_mod.load_registry(f)
    assert "miami_fl" in regions and regions["miami_fl"]["default_on"] is False
    p = [x for x in pts if x.region == "miami_fl"][0]
    assert (p.id, p.elevation_m, p.timezone) == ("miami", 1, "America/New_York")


def test_explicit_point(env):
    f, calls = env
    assert add_region.main(base(f, "--point", "wynwood|Wynwood|25.80|-80.20")) == 0
    pts, _ = points_mod.load_registry(f)
    assert any(p.id == "wynwood" and p.region == "miami_fl" for p in pts)
    assert calls["sync"] == [["--points", "wynwood"]]


def test_dry_run_writes_nothing(env, capsys):
    f, calls = env
    before = f.read_text()
    assert add_region.main(base(f, "--place", "Miami", "--dry-run")) == 0
    assert f.read_text() == before
    assert "miami_fl" in capsys.readouterr().out
    assert calls["sync"] == []


def test_duplicate_region_id(env):
    f, _ = env
    before = f.read_text()
    argv = base(f, "--point", "x|X|1|2")
    argv[1] = "santa_clara_ca"
    with pytest.raises(SystemExit) as e:
        add_region.main(argv)
    assert e.value.code == 2
    assert f.read_text() == before


def test_no_geocoding_match(env, monkeypatch, capsys):
    f, _ = env

    def boom(place):
        raise add_region.NoMatch(place)

    monkeypatch.setattr(add_region, "geocode", boom)
    before = f.read_text()
    with pytest.raises(SystemExit) as e:
        add_region.main(base(f, "--place", "Nowhereville"))
    assert e.value.code == 2
    assert "no geocoding match for Nowhereville" in capsys.readouterr().err
    assert f.read_text() == before


def test_palette_picks_unused_color(env):
    f, _ = env
    _, regions = points_mod.load_registry(f)
    used = {r["color"] for r in regions.values()}
    add_region.main(base(f, "--place", "Miami", "--no-backfill"))
    _, regions = points_mod.load_registry(f)
    new = regions["miami_fl"]["color"]
    assert new not in used
    expected = next(c for c, _ in add_region.PALETTE if c not in used)
    assert new == expected


def test_sync_called_with_exactly_new_ids_and_publish(env):
    f, calls = env
    rc = add_region.main(base(f, "--point", "a_pt|A|25.1|-80.1",
                              "--point", "b_pt|B|25.2|-80.2", "--publish"))
    assert rc == 0
    assert calls["sync"] == [["--points", "a_pt", "b_pt"]]
    assert len(calls["run"]) == 1 and calls["run"][0][0] == "bash"


def test_invalid_timezone_and_range(env):
    f, _ = env
    before = f.read_text()
    for pt in ("z|Z|95|10", "z|Z|10|200"):
        with pytest.raises(SystemExit) as e:
            add_region.main(base(f, "--point", pt))
        assert e.value.code == 2
    assert f.read_text() == before
