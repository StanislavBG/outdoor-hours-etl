"""Quick exploration / sanity summary of a curated parquet.

Shows per-point ranges on every axis so we can sanity-check before designing the
hourly classifier.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]


def run(parquet: Path) -> None:
    con = duckdb.connect()
    con.execute(f"create view h as select * from read_parquet('{parquet}')")

    print("\n=== Coverage ===")
    print(con.execute(
        """
        select region, point, count(*) as hours,
               min(ts_local)::varchar as first_local,
               max(ts_local)::varchar as last_local
          from h group by 1,2 order by 1,2
        """
    ).df().to_string(index=False))

    print("\n=== Temperature (°C) ===")
    print(con.execute(
        """
        select region, point,
               round(avg(temperature_2m),1) as mean,
               round(min(temperature_2m),1) as min,
               round(max(temperature_2m),1) as max,
               round(avg(apparent_temperature),1) as mean_apparent,
               round(avg(dew_point_2m),1) as mean_dew
          from h group by 1,2 order by 1,2
        """
    ).df().to_string(index=False))

    print("\n=== Rain / Precip ===")
    print(con.execute(
        """
        select region, point,
               round(sum(precipitation),1) as total_precip_mm,
               count(*) filter (where precipitation > 0.1) as wet_hours,
               round(max(precipitation),1) as max_hourly_mm,
               round(sum(snowfall),1) as total_snow_cm
          from h group by 1,2 order by 1,2
        """
    ).df().to_string(index=False))

    print("\n=== Sun / Clouds ===")
    print(con.execute(
        """
        select region, point,
               round(avg(cloud_cover),1) as mean_cloud_pct,
               round(avg(shortwave_radiation),1) as mean_sw_wm2,
               round(sum(sunshine_duration)/3600.0,1) as total_sunshine_hrs,
               count(*) filter (where is_day = 1 and cloud_cover < 20) as clear_daytime_hours
          from h group by 1,2 order by 1,2
        """
    ).df().to_string(index=False))

    print("\n=== Wind ===")
    print(con.execute(
        """
        select region, point,
               round(avg(wind_speed_10m),2) as mean_ms,
               round(max(wind_speed_10m),2) as max_ms,
               round(avg(wind_gusts_10m),2) as mean_gust_ms,
               round(max(wind_gusts_10m),2) as max_gust_ms
          from h group by 1,2 order by 1,2
        """
    ).df().to_string(index=False))

    print("\n=== UV (estimated) ===")
    print(con.execute(
        """
        select region, point,
               round(avg(uv_index_est) filter (where is_day=1),2) as mean_uv_daytime,
               round(max(uv_index_est),2) as max_uv,
               count(*) filter (where uv_index_est >= 6) as hours_uv_ge_6
          from h group by 1,2 order by 1,2
        """
    ).df().to_string(index=False))

    print("\n=== Hour-of-day temp profile (region average) ===")
    print(con.execute(
        """
        select hour_of_day,
               round(avg(temperature_2m) filter (where region='santa_clara_ca'),1) as scc_temp,
               round(avg(temperature_2m) filter (where region='eastside_king_wa'),1) as king_temp,
               round(avg(cloud_cover) filter (where region='santa_clara_ca'),0) as scc_cloud,
               round(avg(cloud_cover) filter (where region='eastside_king_wa'),0) as king_cloud
          from h group by 1 order by 1
        """
    ).df().to_string(index=False))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet", default="data/curated/hourly_sample_last30.parquet")
    args = parser.parse_args()
    run(Path(args.parquet))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
