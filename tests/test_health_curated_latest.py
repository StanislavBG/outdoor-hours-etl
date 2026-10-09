from datetime import date

import pandas as pd

from etl.health import _curated_latest


def test_curated_latest_reads_timestamptz(tmp_path):
    path = tmp_path / "hourly.parquet"
    pd.DataFrame(
        {
            "region": ["a", "a", "b"],
            "ts_utc": [
                pd.Timestamp("2026-01-01 00:00", tz="UTC"),
                pd.Timestamp("2026-01-03 12:00", tz="UTC"),
                pd.Timestamp("2026-02-05 23:00", tz="UTC"),
            ],
        }
    ).to_parquet(path)
    assert _curated_latest(path) == {"a": date(2026, 1, 3), "b": date(2026, 2, 5)}
