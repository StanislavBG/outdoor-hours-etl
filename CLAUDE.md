# Weather project — agent notes

Multi-zone ERA5 weather + CAMS air-quality tracker, published to bilko.run (OutdoorHours). See README.md for the data flow.

## Commands (run from /home/bilko/Projects/Weather)
- Add a zone: `uv run python -m etl.add_region --region-id miami_fl --label "Miami, FL" --short MIA --place "Miami, Florida, United States"` (`--dry-run`, `--no-backfill`, `--publish`, `--point 'id|Name|lat|lon[|elev|tz]'`)
- Fill gaps: `uv run python -m etl.sync [--dry-run|--check] [--max-requests N]`
- Weekly refresh + publish: `bash scripts/weekly_refresh.sh` (`SKIP_PUBLISH=1` to skip publishing)
- Publish web UI: `bash scripts/publish_web.sh` (`SKIP_PUBLISH=1` to build only); check live: `bash scripts/verify_web_live.sh '<text>'`
- Install cron: `bash scripts/install_cron.sh`
- Health: `uv run python -m etl.health`
- Tests: `uv run pytest -q`

## Frontend (web/)
- `web/` is the bilko.run page source (Vite + React); all UI work happens here, not in the old ~/Projects/Outdoor-Hours repo.
- `pnpm --dir web install` / `pnpm --dir web dev` / `pnpm --dir web build` (from repo root).
- `base` in `web/vite.config.ts` must stay `/projects/outdoor-hours/`.

## Rules
- Add zones ONLY via `etl.add_region`; never hand-edit Python or regions.yaml to add one.
- `data/` is gitignored and lives only in /home/bilko/Projects/Weather; never expect it in a worktree or clone.
- Publishing pushes the Bilko repo (/home/bilko/Projects/Bilko, `public/outdoor-hours`) to origin and content-grade; Render auto-deploys. Use `SKIP_PUBLISH=1` when testing.
- `ts_local` / daily buckets use each point's own timezone.
- Open-Meteo free tier rate-limits big backfills: use `--max-requests` and rerun `etl.sync` to resume.
- Last run status: `logs/weekly/last_status.json`.
