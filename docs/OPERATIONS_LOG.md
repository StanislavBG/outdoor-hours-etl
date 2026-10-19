# Operations log

## 2026-10-09 — backfill + go-live attempt: HALTED (Open-Meteo rate limiting)

**Live checkout:** /home/bilko/Projects/Weather on `main` at e0abc23 already contained etl/sync.py, add_region.py, health.py and the new weekly_refresh.sh; no merge needed.

**Gap list before the backfill** (`etl.sync --dry-run`): 166 pieces planned.
- Weather: miami_downtown, miami_beach, coral_gables, gabrovo_center, sofia_center, st_johns_town and others missing 2021-04-24..2026-04-27 (yearly chunks) plus trailing 2026-06-04..2026-10-04.
- AQ: all 32 points missing 2026-06-04..2026-10-04.

**Requests / progress:** 3 `etl.sync` attempts (1 killed at the 15 min tool limit, 2 hit `timeout 850` exit 124). Every run spent most of its time in `429 rate-limited; sleeping 60s` loops. Progress persisted to disk: 166 -> 69 pieces remaining (weather: 5 x 7 pieces for miami_downtown, miami_beach, coral_gables, gabrovo_center, sofia_center; 2 for st_johns_town; AQ trailing piece for all 32 points).

**Not done (per PRD: no publish of partial data):**
- `etl.sync --check` not exit 0; `weekly_refresh.sh` not run; nothing published; no Bilko commit/pubdate; live-site check not performed.
- `install_cron.sh` not run (crontab has 0 weather-weekly-refresh lines).
- Curated ranges / year counts after: not re-curated.

**Problem found (not fixed, out of scope):** `etl.health --root /home/bilko/Projects/Weather` crashes with `ModuleNotFoundError: No module named 'pytz'` (duckdb timezone conversion needs pytz; not in the project's dependencies). Needs `pytz` added to pyproject before health can print HEALTHY.

**Next:** rerun `uv run python -m etl.sync` after the rate-limit window resets (resumes from disk), then steps 4-10 of the PRD.

## 2026-10-09 (PDT) — backfill retry: progress, still not complete

**pytz fix landed** (`fix(deps): add pytz for duckdb timestamptz in etl.health`): `pytz` added to `pyproject.toml`/`uv.lock`; regression test `tests/test_health_curated_latest.py` (tz-aware `ts_utc` parquet -> `etl.health._curated_latest`) added; full suite 47 passed. Fast-forwarded into the live checkout.

**Gap list before** (`etl.sync --dry-run`, 2:01 PM PDT): 69 pieces — weather 37 (7 each: miami_downtown, miami_beach, coral_gables, gabrovo_center, sofia_center; 2 st_johns_town), AQ 32 (trailing 2026-06-04..2026-10-04, all points).

**Attempts** (`--delay 20 --max-requests 15`, 4 of 4 used, 2:01-2:17 PM PDT):
1. `--source aq`: 15 fetched, 17 AQ remain (2:01-2:06 PM).
2. all sources: 15 fetched (miami_downtown and miami_beach completed), exit 0 (2:06-2:12 PM).
3. all sources: halted on coral_gables 2021-04-24..2022-04-23 with `Expecting value: line 1 column 1 (char 0)` (empty/non-JSON response, likely rate limiting) (2:12-2:16 PM).
4. same command: same halt on the same piece, within 30 s (2:16 PM).

**Remaining after** (2:17 PM PDT): 31 pieces — weather 14 (coral_gables 7, gabrovo_center 7), AQ 17. sofia_center, st_johns_town, miami_downtown, miami_beach weather complete.

**Not done (per PRD: no publish of partial data):** `etl.sync --check` not exit 0; `weekly_refresh.sh` not run; nothing published (no Bilko commit/pubdate, no live-site check); `install_cron.sh` not run; no re-curation, so no per-region curated range/year counts.

**Observation (not fixed, out of scope):** a non-JSON response in the weather fetcher surfaces as a bare JSON decode error rather than being retried/treated as a rate limit.

**Next:** rerun `uv run python -m etl.sync` after the quota resets (resumes from disk), then steps 4-9 of the PRD.

## 2026-10-09 — backfill completed, cron installed, published (job 08 retry)

- **Gap count before:** 31 pieces (`etl.sync --dry-run`, 2:20 PM PDT): weather coral_gables 7, gabrovo_center 7, AQ 17.
- **Code fix:** `cefc7ab` `fix(etl)`: `_client.fetch_json` now parses 2xx bodies defensively. Empty/non-JSON/`{"error":true}` raises `FetchBodyError` (status, Content-Type, first 200 chars) and is retried with backoff. A `reason` containing "limit" raises `RateLimitExhausted` with no retry; `etl.sync` returns 75 with `RATE_LIMITED:`. New `--piece-days`. Both classes re-exported from `etl.sources.open_meteo` (the shared fetch lives in `_client` since f522965). Tests: `tests/test_fetch_errors.py`.
- **Cron installed before backfill:** `0 9 * * 1 /home/bilko/Projects/Weather/scripts/weekly_refresh.sh # weather-weekly-refresh`
- **Probe** (coral_gables 2021-04-24..30): HTTP 200 `application/json`, valid hourly payload; no quota problem.
- **Attempts** (`--delay 15 --piece-days 92`): 1) rc=124 time cap, 13 remaining by default 365-day planning; 2) rc=0, 26 fetched, 0 remaining. `etl.sync --check`: no gaps.
- **Publish:** `weekly_refresh.sh` rc=0, `last_status.json` ok=true published=true (2:47 PM PDT). Bilko commit `2776c53` (only `public/outdoor-hours`). New pubdate `2026-10-09T21:45:42+00:00`.
- **Live site:** `bilko.run/outdoor-hours/last1m.json` showed the new pubdate after ~4 polls (~2 min).
- **Curated (hourly_last10y)** per region: 2016-04-19/20 → 2026-10-04/05, 11 calendar years each (12 regions).
- **Health:** `etl.health` HEALTHY, exit 0.

## 2026-10-09 (3:00 PM PDT) — re-verification (job 08 final pass)

Nothing re-run; pipeline state re-checked in /home/bilko/Projects/Weather: `etl.sync --check` -> `no gaps` (rc 0); `crontab -l` has exactly one `weather-weekly-refresh` line; `last_status.json` ok=true published=true (2:47 PM PDT); `etl.health` HEALTHY; https://bilko.run/outdoor-hours/last1m.json pubdate `2026-10-09T21:45:42+00:00` (matches Bilko publish commit `2776c53`; Bilko HEAD has since advanced with unrelated commits). Stray empty file `<path>` remains untracked in the live checkout root (harmless).

## 2026-10-18 (7:43 PM PDT) — web/ merge published live (job 33)

- **Merge:** the Vite + React frontend from the old Outdoor-Hours repo now lives in `web/` (`85aee18`), followed by `scripts/publish_web.sh` / `verify_web_live.sh` (`353c11a`) and the view/rules/controls/telemetry commits (through `417f14e`).
- **Publish:** `bash /home/bilko/Projects/Weather/scripts/publish_web.sh` rc=0; `logs/publish_web/last_status.json` ok=true published=true at 7:42 PM PDT. Asset `index-BDyZ7jKe.js` (css `index-CLiWMfWr.css`). Bilko commit `f11543f6` (`OutdoorHours: publish web 417f14e`) on origin/main and content-grade/master. Weather sha `417f14e` pushed to origin/main. Live after 14 polls.
- **verify_web_live:** passes for `'Last 30 days' 'profile-customize' 'outdoor-hours'`; live bundle is byte-identical to Bilko's built asset.
- **Script fix:** `verify_web_live.sh` gave a false `MISSING` because `printf | grep -q` under `pipefail` fails on SIGPIPE for a large bundle. It now uses a here-string.
