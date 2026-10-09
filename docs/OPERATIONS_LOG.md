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
