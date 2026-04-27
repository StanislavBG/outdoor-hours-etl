#!/usr/bin/env bash
# Weekly OutdoorHours refresh.
#
# Cron suggestion (Mon 9 AM PDT):
#   0 9 * * 1 /home/bilko/Projects/Weather/scripts/weekly_refresh.sh
#
# Open-Meteo ERA5 lags ~5 days, so a Monday morning run picks up data through
# the previous Wednesday. The full prior Mon-Sun week becomes complete on the
# *following* week's run. That's fine — every week we catch up another 7 days.
#
# Steps:
#   1. Refresh the trailing raw chunk for each point.
#   2. Re-curate hourly_last10y.parquet.
#   3. Pre-compute daily/monthly/yearly + region rollups.
#   4. Derive last1m / last1y / last5y subsets from last10y.
#   5. Re-export JSON bundles into Bilko/public/ (embeds pubdate).
#   6. Build Bilko, commit if anything changed, push to both remotes
#      (content-grade master auto-deploys via Render).
#
# LLM narrative steps (range-overview, monthly summaries) are intentionally
# omitted — they are not required for the live data publish path.

set -euo pipefail

WEATHER_ROOT="/home/bilko/Projects/Weather"
BILKO_ROOT="/home/bilko/Projects/Bilko"
LOG_DIR="$WEATHER_ROOT/logs/weekly"
TS=$(date +'%Y-%m-%d_%H-%M')
LOG="$LOG_DIR/$TS.log"

mkdir -p "$LOG_DIR"
exec > "$LOG" 2>&1
echo "===== weekly refresh $TS ====="
echo "host: $(hostname) · pwd: $(pwd)"

# uv lives in ~/.local/bin or similar; make sure it's on PATH for cron.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

cd "$WEATHER_ROOT"

step() { echo; echo "----- $* -----"; }

step "1a. refresh trailing weather chunks"
uv run python -m scripts.refresh_recent_chunks

step "1b. refresh trailing AQ chunks"
uv run python -m scripts.refresh_recent_aq_chunks

step "2. curate hourly_last10y (joins weather + AQ)"
uv run python -m etl.curate --tag last10y

step "3. precompute rollups"
uv run python -m etl.precompute --tag last10y

step "4. derive last1m + last1y + last5y"
uv run python -m scripts.derive_short_ranges

step "5. export JSON bundles"
uv run python -m scripts.export_outdoor_hours

step "6. build + commit + push Bilko"
cd "$BILKO_ROOT"
pnpm build

if git diff --quiet -- public/outdoor-hours; then
    echo "no public/outdoor-hours changes; skipping commit/push"
else
    git add public/outdoor-hours
    git -c user.email=cron@bilko.run -c user.name='OutdoorHours Cron' \
        commit -m "Weekly OutdoorHours refresh — $TS"
    git push origin main
    git push content-grade main:master
    echo "pushed."
fi

echo
echo "===== weekly refresh DONE $(date) ====="
