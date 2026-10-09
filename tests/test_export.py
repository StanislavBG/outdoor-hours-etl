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
