# Validation: weather pipeline plan

Base: c2ce8e019ca419c8925c2bca0e08f50fd77fd09d, HEAD fd592b1. Combined diff: 49 files, +3043/-722. Full suite `uv run pytest -q`: 121 passed. `/code-review` and `/security-review` were not run as separate tools; I self-reviewed the diff for the areas listed under Findings.

## 1-regions-yaml-config — VERIFIED
- `etl/regions.yaml` and `etl/points.py` (`load_registry`, `REGIONS_YAML`) exist, added in 20e1d69.
- Gate `pytest tests/test_points.py`: 12 passed. The POINTS/REGIONS assertion printed `32 12`, exit 0.
- Note: the PRD file is still in `prds/` rather than `prds-archived/` (Minor).

## 2-gap-aware-sync — VERIFIED
- `etl/sync.py` added in 788d45c. `tests/test_sync.py` passes. `python -m etl.sync --help` exits 0.
- Live `cd /home/bilko/Projects/Weather && uv run python -m etl.sync --check` printed `no gaps`, rc=0.

## 3-local-time-buckets — VERIFIED
- `etl/curate.py:121-132` converts `ts_utc` to each point's own timezone (`tz_convert(tz)`), then derives `ts_local`, year, month, day and hour_of_day from it.
- `tests/test_curate_tz.py` passes.

## 4-add-region-cli — VERIFIED
- `etl/add_region.py` added in 5fd8a20. `tests/test_add_region.py` passes. `--help` exits 0.
- `REGION_ID_RE` is validated at `etl/add_region.py:120`. YAML is written with `safe_dump`. The only subprocess call is a fixed argv.

## 5-weekly-pipeline-hardening — VERIFIED
- Gate `bash -n` on both scripts plus `install_cron.sh --dry-run`: exit 0.
- `scripts/weekly_refresh.sh` has `set -euo pipefail`, an EXIT trap that writes `last_status.json`, sync followed by a `--check` gap guard, and a `SKIP_PUBLISH` branch.
- Live `last_status.json`: `ok=true`, `published=true`.

## 6-pipeline-health-check — VERIFIED
- `tests/test_health.py` passes. `python -m etl.health --help` exits 0.

## 7-ops-docs — VERIFIED
- `README.md` covers add_region, sync, weekly_refresh, install_cron, health and the rate-limit note (lines 3-49).
- `CLAUDE.md` lists the commands and rules (lines 6-18).

## 8-backfill-publish-and-schedule — VERIFIED
- `uv run python -m etl.health --root /home/bilko/Projects/Weather` printed HEALTHY for 12 regions with 0 weather gaps and 0 AQ gaps. Exit 0.
- `crontab -l` line 56: `0 9 * * 1 /home/bilko/Projects/Weather/scripts/weekly_refresh.sh # weather-weekly-refresh`. It is the only such line.
- Live `https://bilko.run/outdoor-hours/last1m.json` pubdate is `2026-10-09T21:45:42+00:00`, matching docs/OPERATIONS_LOG.md.
- `docs/OPERATIONS_LOG.md` records the halted attempts, the retry and the successful completion (published, cron installed).

## Findings
### Critical
- none
### Important
- none
### Minor
- `etl/add_region.py:22`: `^...$` with `.match` accepts a trailing newline in the region id. The practical risk is low, since the id comes from the CLI. Use `fullmatch`.
- The 1-regions-yaml-config PRD file is still in `prds/` while PRDs 2-8 are in `prds-archived/`.
- Health reports `days_stale=5` for every region and still says HEALTHY. This is expected, because ERA5 lags about 5 days.
- An untracked stray empty file named `<path>` sits in the repo root. The ops log mentions it and calls it harmless.
- Extra commits beyond the 8 PRDs (shared catalog, vectorized export, app/data.py, JS modules, claude model pinning) are in the combined diff. They are tested and in the full suite pass, and I found nothing wrong with them.
