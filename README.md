# Weather Compare (OutdoorHours data pipeline)

Hourly weather + air-quality tracker for 12 zones (`etl/regions.yaml`), published as JSON bundles to the OutdoorHours page on bilko.run.

## Data sources
- **Weather**: Open-Meteo ERA5 archive, 10-year window starting 2016-04-20 (lags ~5 days).
- **Air quality**: Open-Meteo CAMS, from 2022-09-01.
- Each zone is a region with several sample points in `etl/regions.yaml`.

## Data flow
```
etl.sync -> etl.curate -> etl.precompute -> scripts/derive_short_ranges.py
  -> scripts/export_outdoor_hours.py -> Bilko public/outdoor-hours -> bilko.run
```
1. `etl.sync` fills gaps in raw per-point Parquet chunks (`data/raw/`).
2. `etl.curate` builds `hourly_last10y.parquet`; `etl.precompute` writes daily/monthly/yearly and region rollups.
3. `derive_short_ranges` derives last1m / last1y / last5y subsets.
4. `export_outdoor_hours` writes JSON bundles into the Bilko repo (`/home/bilko/Projects/Bilko/public/outdoor-hours`).
5. `web/` is the Vite + React page that reads the exported JSON (`pnpm --dir web build`).
6. Publishing commits only that directory, pushes Bilko to `origin` and `content-grade` (`master`); Render auto-deploys on push to bilko.run.

`data/` is gitignored and exists only in this checkout.

## Operations
```bash
uv sync                                   # install deps

# Add a zone (writes etl/regions.yaml, backfills history; --place geocodes)
uv run python -m etl.add_region --region-id miami_fl --label "Miami, FL" --short MIA --place "Miami, Florida, United States"
#   other flags: --point 'id|Name|lat|lon[|elevation|timezone]', --dry-run, --no-backfill, --publish

# Fill gaps in raw data
uv run python -m etl.sync --dry-run       # print plan only
uv run python -m etl.sync --check         # exit 1 and list gaps, never fetches
uv run python -m etl.sync                 # fetch missing ranges (--points, --source weather|aq|all, --max-requests N)

# Weekly refresh + publish
bash scripts/weekly_refresh.sh            # sync, curate, precompute, derive, export, build, push
SKIP_PUBLISH=1 bash scripts/weekly_refresh.sh   # everything except the publish step
bash scripts/install_cron.sh              # idempotent cron install (Mon 9 AM PT)

# Health and tests
uv run python -m etl.health               # HEALTHY or FAIL lines; --json available
uv run pytest -q
```
Each weekly run writes `logs/weekly/last_status.json`.

## Notes
- `ts_local` and daily buckets use each point's own local timezone, not a region-wide one.
- The free Open-Meteo tier rate-limits large backfills (e.g. a new zone). Use `--max-requests N` and rerun `etl.sync`; it is gap-aware and resumes where it stopped.
