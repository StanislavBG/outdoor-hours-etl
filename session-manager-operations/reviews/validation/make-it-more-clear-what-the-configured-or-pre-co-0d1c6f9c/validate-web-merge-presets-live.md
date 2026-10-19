# Validation: web merge, preset thresholds, live publish

Base: 98a7d3ce (8 commits, 85aee18..f7ac850). Scope: PRDs 25, 26, 28, 29, 30, 31, 32, 33. Reviewed against the job worktree at HEAD f7ac850 plus the live site.
Gates re-run: `node --experimental-strip-types --test web/tests/*.test.ts` (20/20 pass); `pnpm --dir web install --frozen-lockfile && pnpm --dir web build` (ok, `emit-manifest: ... kit 0.9.0`); `bash -n` on both scripts; `SKIP_PUBLISH=1 bash scripts/publish_web.sh` (rc 0, "would publish index-BDyZ7jKe.js"); `bash scripts/verify_web_live.sh 'Last 30 days' 'profile-customize' 'outdoor-hours'` (rc 0, `live ok: .../index-BDyZ7jKe.js`).

## 25-import-web-frontend — VERIFIED
- Files present: web/{index.html,package.json,pnpm-lock.yaml,tsconfig.json,vite.config.ts,scripts/emit-manifest.mjs,src/main.tsx,src/OutdoorHoursPage.tsx,src/index.css,README.md}.
- src byte-identical at import: `git show 85aee18:web/src/OutdoorHoursPage.tsx` and `index.css` diff clean against Outdoor-Hours HEAD.
- `sync` script absent: web/package.json scripts = dev, build, preview.
- web/scripts/emit-manifest.mjs:26 matches the required `??` chain.
- .gitignore:14-16 has web/dist/, *.tsbuildinfo, logs/.
- CLAUDE.md "Frontend (web/)" section present; README.md data-flow item 5 mentions web/; web/README.md says "now lives in outdoor-hours-etl/web".
- Gate green (above).

## 26-publish-web-script — VERIFIED
- scripts/publish_web.sh:44-46 install+build; :49-54 HALT on missing dist/index.html or manifest.json.
- :69-74 SKIP_PUBLISH=1 prints asset and exits before touching Bilko (run confirmed).
- :80-93 main-branch check, `git fetch origin`, `merge --ff-only`; :95-96 replace bundle; :98 `pnpm build`; :100-111 pathspec-limited commit, skipped when unchanged, push origin main and content-grade main:master; :114-123 Weather main check and push with HALT.
- :126-138 poll 20x, 15 s, `--max-time 15`, HALT exit 1 if never live.
- :28-30 trap writes logs/publish_web/last_status.json with ts, ok, failed_step, published, asset, bilko_sha, weather_sha.
- scripts/verify_web_live.sh: `curl --max-time 15`, 3-try retry, asset discovery, per-string grep, exit 1 on MISSING.

## 28-web-default-view — VERIFIED
- web/src/lib/view.ts: imports nothing; RANGE_ORDER last1m = {label '30 days', long 'Last 30 days'}; DEFAULT_VIEW exact; rangeLabel, rangeLongLabel, readInitialView, viewToParams exported.
- OutdoorHoursPage.tsx:20 imports from lib/view; grep finds no RANGE_ORDER definition or DEFAULT_TAG; :384 readInitialView; :435-436 viewToParams with defaults overridden by payload.default_profile; :473 profile follows payload.default_profile when not in URL. Remaining 'daily' literals are grain comparisons, not defaults.
- No "1mo"/"1 mo" left in the page (grep clean).
- web/tests/view.test.ts passes (empty URL, overrides, omit/keep, labels).
- Long-label use in hero/stat tile/leaderboard/deep-dive: not individually traced; supported by the live bundle containing 'Last 30 days'.

## 29-web-preset-thresholds — VERIFIED
- web/src/lib/rules.ts: no imports; ProfileRule, ruleItems(rule,{includeUnlimited}), ruleSummary exported; null caps → 'No limit', limited:false.
- OutdoorHoursPage.tsx:1146 ProfileRulesStrip under the profile bar (Custom drawer branch at the same spot); :1657-1685 shows temp °F + °C, UV, rain, cloud, humidity, AQI; :1676-1681 "✨ Customize from this preset" button; :1148 sets customRule from the preset and switches to Custom.
- :1111 tooltip `${p.desc} — ${ruleSummary(p.rule)}`; :1301 Rules card uses ruleItems(rule,{includeUnlimited:false}).
- web/tests/rules.test.ts passes.

## 30-web-controls-top — VERIFIED
- OutdoorHoursPage.tsx line order: profile toggle 1095 < Controls 1155 < Hero 1235 < `<Leaderboard payload` 1291.
- :1156 keeps `sticky top-0 z-30`, `mt-4`.
- :793 and :2076 say "Compare counties” above".
- web/tests/layout.test.ts passes.

## 31-web-telemetry-init — VERIFIED
- web/package.json `host-kit: ^0.9.0`; lockfile frozen install ok; build prints kit 0.9.0.
- web/src/main.tsx:9 `initTelemetry({ app: 'outdoor-hours', version: pkg.version })` before createRoot.
- web/src/lib/flow.ts: no imports; isFlowName regex `/^[a-z0-9][a-z0-9-]{0,39}$/`; makeTrackFlow drops invalid names silently, merges props.
- web/tests/flow.test.ts passes.

## 32-web-telemetry-wire — VERIFIED
- data-track present: profile-<id> (:1109), profile-custom (:1121), profile-customize (:1676), range-<tag> (:1167), view-grain/metric/yoy (:1177/1186/1193), region-<key> (:1215), tour-open (:1080), detail-fullscreen/close (:2137/2140).
- :16-22 imports `track, logError` from 'host-kit', makeTrackFlow from './lib/flow.js'; `trackFlow = makeTrackFlow(track)`.
- Flows: profile.select :1110, profile.rules-shown :579, custom.open :1122/:1148, custom.recompute-done :561 (ms), drill.click-point :697 (grain), drill.detail-shown :732 (rows), tour.open :419/:1081, tour.finish :424.
- logError at :489 (payload-fetch), :563 (custom-recompute), :722 (drill/hourly fetch).
- Props are enums/ids/counts only (`auto: true`, grain, rows, ms, profile id).
- web/tests/telemetry-tags.test.ts passes.

## 33-publish-web-live — VERIFIED (one criterion deferred by the PRD's own note)
- last_status.json: `ok:true, published:true, asset index-BDyZ7jKe.js, bilko_sha f11543f6, weather_sha 417f14e`.
- Bilko f11543f6 "OutdoorHours: publish web 417f14e" is on origin/main (`branch -r --contains`) and content-grade master tip equals f11543f6.
- Live re-check: `verify_web_live.sh 'Last 30 days' 'profile-customize' 'outdoor-hours'` → `live ok: /projects/outdoor-hours/assets/index-BDyZ7jKe.js`, same asset name as the local rebuild.
- docs/OPERATIONS_LOG.md has the dated entry (2026-10-18 7:43 PM PDT) with merge, asset, Bilko sha, Weather sha and verify result.
- NOT met: criterion 5 (origin/main includes the log entry). `ls-remote origin main` = 417f14e; main checkout is ahead 1 (f7ac850). PRD implementation note 5 permits this ("next publish or weekly run pushes it").

## Combined diff review
24 files, +4464/-1. No secrets. No path traversal or injection: scripts use fixed paths, quote variables, and `tr -d '"\\'` on JSON status fields. No `--force`. Telemetry props carry no PII. /code-review and /security-review were not run as skills; this was a manual review.

## Findings
### Critical
- none
### Important
- none
### Minor
1. origin/main lacks f7ac850 (the OPERATIONS_LOG entry and the verify_web_live SIGPIPE fix). Run `git push origin main` from the main checkout, or let the next publish do it.
2. scripts/verify_web_live.sh and the PRD-33 commit changed the script after PRD 26 (here-string instead of `printf | grep -q`). It is a real bug fix. PRD 33's Files list named only docs/OPERATIONS_LOG.md, so this was an out-of-list edit.
3. Stray empty untracked file `/home/bilko/Projects/Weather/<path>` (dated Oct 9) and untracked `.claude/` in the main checkout. Neither is from this plan.
4. scripts/publish_web.sh:131 uses `curl | grep -q` under pipefail. Safe today (small HTML); it has the same SIGPIPE pattern that was fixed in verify_web_live.sh.
