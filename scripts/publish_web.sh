#!/usr/bin/env bash
# Build web/, publish the bundle into the Bilko repo, push Bilko + this repo,
# and confirm the new bundle is live on bilko.run.
#
#   bash scripts/publish_web.sh              # full publish (pushes to production)
#   SKIP_PUBLISH=1 bash scripts/publish_web.sh   # build only
#
# Every exit writes logs/publish_web/last_status.json.

set -euo pipefail

WEATHER_ROOT="${WEATHER_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
BILKO_ROOT="${BILKO_ROOT:-/home/bilko/Projects/Bilko}"
LOG_DIR="$WEATHER_ROOT/logs/publish_web"
STATUS_FILE="$LOG_DIR/last_status.json"
LIVE_URL="https://bilko.run/projects/outdoor-hours/"
CURRENT_STEP="startup"
PUBLISHED=false
ASSET=""

mkdir -p "$LOG_DIR"

write_status() {
    local rc=$?
    local ok=true failed_step=null step_json bilko_sha weather_sha asset_json
    if [ "$rc" -ne 0 ]; then
        ok=false
        step_json=$(printf '%s' "$CURRENT_STEP" | tr -d '"\\')
        failed_step="\"$step_json\""
    fi
    asset_json=$(printf '%s' "$ASSET" | tr -d '"\\')
    bilko_sha=$(git -C "$BILKO_ROOT" rev-parse --short HEAD 2>/dev/null || echo "")
    weather_sha=$(git -C "$WEATHER_ROOT" rev-parse --short HEAD 2>/dev/null || echo "")
    printf '{"ts": "%s", "ok": %s, "failed_step": %s, "published": %s, "asset": "%s", "bilko_sha": "%s", "weather_sha": "%s"}\n' \
        "$(date -Iseconds)" "$ok" "$failed_step" "$PUBLISHED" "$asset_json" "$bilko_sha" "$weather_sha" > "$STATUS_FILE"
}
trap write_status EXIT

# cron's PATH is minimal: pnpm lives in ~/.npm-global/bin.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$HOME/.npm-global/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

step() { CURRENT_STEP="$*"; echo; echo "----- $* -----"; }

step "1. build web/"
pnpm --dir "$WEATHER_ROOT/web" install --frozen-lockfile
pnpm --dir "$WEATHER_ROOT/web" build

DIST="$WEATHER_ROOT/web/dist"
for f in index.html manifest.json; do
    if [ ! -f "$DIST/$f" ]; then
        echo "HALT: web/dist/$f missing after build"
        exit 1
    fi
done

shopt -s nullglob
assets=("$DIST"/assets/index-*.js)
shopt -u nullglob
if [ "${#assets[@]}" -ne 1 ]; then
    echo "HALT: expected exactly one web/dist/assets/index-*.js, found ${#assets[@]}"
    exit 1
fi
ASSET=$(basename "${assets[0]}")

if [ "${SKIP_PUBLISH:-0}" = "1" ]; then
    step "publish skipped (SKIP_PUBLISH=1)"
    echo "would publish $ASSET"
    CURRENT_STEP="done"
    exit 0
fi

step "2. copy bundle into Bilko, build, commit, push"
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

rm -rf public/projects/outdoor-hours
cp -r "$DIST" public/projects/outdoor-hours

pnpm build

if [ -z "$(git status --porcelain -- public/projects/outdoor-hours public/outdoor-hours)" ]; then
    echo "no bundle/data changes in Bilko; skipping commit/push"
else
    git add public/projects/outdoor-hours public/outdoor-hours
    # Pathspec-limited commit: other staged files are left untouched.
    git -c user.email=cron@bilko.run -c user.name='OutdoorHours Publish' \
        commit -m "OutdoorHours: publish web $(git -C "$WEATHER_ROOT" rev-parse --short HEAD)" \
        -- public/projects/outdoor-hours public/outdoor-hours
    git push origin main
    git push content-grade main:master
    PUBLISHED=true
    echo "pushed Bilko."
fi

step "3. push Weather repo"
wbranch=$(git -C "$WEATHER_ROOT" rev-parse --abbrev-ref HEAD)
if [ "$wbranch" != "main" ]; then
    echo "HALT: Weather repo is on '$wbranch', not main; refusing to push"
    exit 1
fi
if ! git -C "$WEATHER_ROOT" push origin main; then
    echo "HALT: push of Weather main to origin was rejected"
    exit 1
fi

step "4. wait for $ASSET to go live"
live=false
for i in $(seq 1 20); do
    if curl -sf --max-time 15 "$LIVE_URL" | grep -qF "$ASSET"; then
        live=true
        break
    fi
    echo "try $i/20: $ASSET not live yet"
    sleep 15
done
if [ "$live" != "true" ]; then
    echo "HALT: $ASSET not live after 20 tries ($LIVE_URL)"
    exit 1
fi
echo "live: $ASSET"

CURRENT_STEP="done"
