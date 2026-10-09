# Validation: code quality, UI isolation, performance (PRDs 10-23)

Base: b6070d85252b2f2e08e4ac47304797cb894067d9. Branch HEAD 5fcc29a. Commits for the PRDs are in `git log b6070d8..HEAD` (c06ed58 … 5fcc29a); combined diff is 46 files, +2753/-1077.

Gates re-run in the foreground on HEAD:
- `uv run pytest -q` → 133 passed.
- `node --test tests/js/*.test.mjs` (format, takeaway, detail, chart, copy) → 28 pass, 0 fail.
- PRD 23 index.html string check → `hardcoded: []`, exit 0.

Note: PRD 11's file is still in `prds/` (not archived); the code and tests landed (2e76921), so this is Minor bookkeeping.

## Per-PRD verdicts

- **10-classifier-reason-per-profile — VERIFIED.** `reason_for` and `apply(with_reason=)` in classifier/personal.py (c06ed58); tests/test_personal.py passes; precompute calls `apply(hourly, with_reason=False)` (etl/precompute.py).
- **11-region-hourly-primitive — VERIFIED.** classifier/hourly.py `region_hourly` (2e76921); tests/test_region_hourly.py passes (parity, 1-point region, missing us_aqi, AQI-only failure). Used by app/detail.py:18,99 and scripts/export_outdoor_hours.py:20,92.
- **12-metric-catalog-primitive — VERIFIED.** etl/catalog.py defines METRICS (17, with `better`), METRIC_KEYS, `metric()`, X_COL, `json_scalar`; tests/test_catalog.py passes.
- **13-sources-shared-client — VERIFIED.** etl/sources/_client.py (f522965); both source modules use it; tests/test_sources_client.py passes (404 no retry, Retry-After, 503, chunks, atomic write); test_sync/test_health/test_add_region pass.
- **14-pin-claude-model — VERIFIED.** scripts/_claude.py:12 `["claude","-p","--model",CLAUDE_MODEL]`; `grep` finds no other `claude` subprocess call in *.py/*.sh; tests/test_claude_cli.py passes.
- **15-ui-format-module — VERIFIED.** app/static/js/format.js, js/package.json, `<script type="module">` at index.html:120; tests/js/format.test.mjs passes.
- **16-export-use-catalog — VERIFIED.** export_outdoor_hours.py:22 imports METRICS/X_COL/json_scalar; :27 OUT env override; :207 `raise SystemExit(1)` after attempting all tags and the hourly export; tests/test_export.py passes.
- **17-server-data-layer — VERIFIED.** app/data.py: `validate_tag`, `lru_cache(maxsize=16)` keyed on `st_mtime_ns` (data.py:44,54), `series_payload`; server.py calls `validate_tag` before building paths (server.py:90,100); tests/test_app_api.py passes (traversal → 404, mtime re-read).
- **18-export-hourly-vectorized — VERIFIED, with caveat on the time.** No `iterrows`/`apply(axis=1)`/threshold constants in the export script (grep clean); rows come from `region_hourly`; tests pass. Benchmark by absolute path `/home/bilko/Projects/Weather/data/curated`, OUT in a temp dir, `export_hourly_months('last10y')`: run 1 = 19.67 s (system load average ~7), run 2 = 10.17 s. Both runs wrote 127 files, not 123, because the curated data has grown since the PRD was written; the count is stable between runs. The after-time is ≤ 15 s on a quiet machine but not under load. The before/after figures the PRD asked for in the run report are not in the commit message (94631f6 has none) or the repo, so the implementer's reported after-time could not be confirmed. The independent measurement is above.
- **19-server-detail-module — VERIFIED.** app/detail.py owns `build_detail` and DETAIL_COLS; hourly SQL uses `year = ? AND month = ? AND day = ?` with a module-level connection `.cursor()` (detail.py:24,86,94); `regions` filter and `n_points`; `default_profile` in /api/metrics (server.py:80); tests/test_app_detail.py passes. Measured daily drill on real last10y: 56 / 46 / 44 ms (before ≈ 170 ms).
- **20-ui-takeaway-module — VERIFIED.** js/takeaway.js, tests/js/takeaway.test.mjs pass; `HIGHER_BETTER`/`LOWER_BETTER`/`updateTakeaway` absent from app.js (grep clean).
- **21-ui-detail-module — VERIFIED.** js/detail.js exports `renderPairedTable` and `createDetailPanel`; `drillStack`, `drillCtx`, `REGION_CLASS`, `REGION_SHORT`, `REGION_ORDER_DEFAULT` absent from app.js; tests/js/detail.test.mjs passes.
- **22-ui-chart-refresh — VERIFIED.** js/chart.js uses `Plotly.react` (chart.js:68); `AbortController` in app.js:167; tests/js/chart.test.mjs passes.
- **23-ui-registry-driven-copy — VERIFIED.** js/copy.js; index.html gate string check clean; no `dot-scc`/`dot-king`/`.stat.scc` rules left in style.css or index.html; tests/js/copy.test.mjs passes.

## Cross-cutting checks

- Numeric classifier thresholds outside classifier/personal.py: none in app/, scripts/ or etl/ logic. Only legacy imports of `COLD_C/HOT_C/UV_MAX` constants in classifier/report_stay_outside.py:14 and classifier/plot_yearly.py:15 (they import from personal.py, so not a second definition).
- Second METRICS list outside etl/catalog.py: none (`grep` finds only etl/catalog.py:17).
- `claude -p` without `--model`: none.
- Hard-coded region ids in app/static: none in JS/HTML. style.css still has `--scc`/`--king` colour variables (lines 2-5, 39, 55, 106, 192, 429), named after two regions.
- Benchmarks wrote only to a temp dir; nothing was written to /home/bilko/Projects/Bilko.

## Findings

### Critical
- none

### Important
- none

### Minor
- app/server.py:40-56 `_profile_payload` and scripts/export_outdoor_hours.py:~129-143 build the same profile `rule` dict (duplicate with different call shape); the export script should reuse one helper (e.g. in classifier/personal.py or etl/catalog.py) so field names cannot drift.
- app/static/style.css:2-5,39,55,106,192,429 keep region-named CSS variables (`--scc`, `--king`) used for gradients and `.detail .yes`; these are decorative defaults rather than region ids, but they are region-specific styling in a registry-driven UI.
- The PRD 18 after-time (≤ 15 s) is load-sensitive: 19.67 s under load vs 10.17 s idle; the implementer's before/after report is not recorded anywhere in the repo.
- PRD 11 file remains in `prds/` rather than `prds-archived/`.
