#!/usr/bin/env bash
# Weekly OutdoorHours refresh.
#
# Cron suggestion (Mon 9 AM PDT):
#   0 9 * * 1 /home/bilko/Projects/Weather/scripts/weekly_refresh.sh
# (install idempotently with scripts/install_cron.sh)
#
# Open-Meteo ERA5 lags ~5 days, so a Monday morning run picks up data through
# the previous Wednesday. The full prior Mon-Sun week becomes complete on the
# *following* week's run. That's fine — every week we catch up another 7 days.
#
# Steps:
#   1. etl.sync fetches every gap in the raw weather + AQ chunks; etl.sync
#      --check then fails the run if any gap remains (nothing is published).
#   2. Re-curate hourly_last10y.parquet.
#   3. Pre-compute daily/monthly/yearly + region rollups.
#   4. Derive last1m / last1y / last5y subsets from last10y.
#   5. Re-export JSON bundles into Bilko/public/ (embeds pubdate).
#   6. Build Bilko, commit only public/outdoor-hours, push to both remotes
#      (content-grade master auto-deploys via Render). Skipped when SKIP_PUBLISH=1.
#
# Every exit writes logs/weekly/last_status.json.
#
# LLM narrative steps (range-overview, monthly summaries) are intentionally
# omitted — they are not required for the live data publish path.

set -euo pipefail

WEATHER_ROOT="/home/bilko/Projects/Weather"
BILKO_ROOT="/home/bilko/Projects/Bilko"
LOG_DIR="$WEATHER_ROOT/logs/weekly"
TS=$(date +'%Y-%m-%d_%H-%M')
LOG="$LOG_DIR/$TS.log"
STATUS_FILE="$LOG_DIR/last_status.json"
CURRENT_STEP="startup"
PUBLISHED=false

mkdir -p "$LOG_DIR"

write_status() {
    local rc=$?
    local ok=true failed_step=null step_json
    if [ "$rc" -ne 0 ]; then
        ok=false
        step_json=$(printf '%s' "$CURRENT_STEP" | tr -d '"\\')
        failed_step="\"$step_json\""
    fi
    printf '{"ts": "%s", "ok": %s, "failed_step": %s, "published": %s, "log": "%s"}\n' \
        "$(date -Iseconds)" "$ok" "$failed_step" "$PUBLISHED" "$LOG" > "$STATUS_FILE"
    if [ "$rc" -ne 0 ] && command -v notify-send >/dev/null 2>&1; then
        notify-send "Weather weekly refresh FAILED" "step: $CURRENT_STEP — see $LOG" || true
    fi
}
trap write_status EXIT

exec > "$LOG" 2>&1
echo "===== weekly refresh $TS ====="
echo "host: $(hostname) · pwd: $(pwd)"

# cron's PATH is minimal: uv lives in ~/.local/bin, pnpm in ~/.npm-global/bin.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$HOME/.npm-global/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

cd "$WEATHER_ROOT"

step() { CURRENT_STEP="$*"; echo; echo "----- $* -----"; }

step "1a. sync raw weather + AQ gaps"
uv run python -m etl.sync

step "1b. verify no gaps remain"
uv run python -m etl.sync --check

step "2. curate hourly_last10y (joins weather + AQ)"
uv run python -m etl.curate --tag last10y

step "3. precompute rollups"
uv run python -m etl.precompute --tag last10y

step "4. derive last1m + last1y + last5y"
uv run python -m scripts.derive_short_ranges

step "5. export JSON bundles"
uv run python -m scripts.export_outdoor_hours

if [ "${SKIP_PUBLISH:-0}" = "1" ]; then
    step "6. publish skipped (SKIP_PUBLISH=1)"
else
    step "6. build + commit + push Bilko"
    cd "$BILKO_ROOT"

    branch=$(git rev-parse --abbrev-ref HEAD)
    if [ "$branch" != "main" ]; then
        echo "HALT: Bilko is on '$branch', not main; refusing to publish"
        exit 1
    fi
    if ! git fetch origin; then
        echo "HALT: git fetch origin failed"
        exit 1
    fi
    if ! git merge --ff-only origin/main; then
        echo "HALT: cannot fast-forward Bilko main to origin/main"
        exit 1
    fi

    pnpm build

    if [ -z "$(git status --porcelain -- public/outdoor-hours)" ]; then
        echo "no public/outdoor-hours changes; skipping commit/push"
    else
        git add public/outdoor-hours
        # Pathspec-limited commit: other staged files are left untouched.
        git -c user.email=cron@bilko.run -c user.name='OutdoorHours Cron' \
            commit -m "Weekly OutdoorHours refresh — $TS" -- public/outdoor-hours
        git push origin main
        git push content-grade main:master
        PUBLISHED=true
        echo "pushed."
    fi
fi

CURRENT_STEP="done"
echo
echo "===== weekly refresh DONE $(date) ====="
