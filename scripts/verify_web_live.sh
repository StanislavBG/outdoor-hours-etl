#!/usr/bin/env bash
# Usage: verify_web_live.sh <string>...
# Fetches the live OutdoorHours page, downloads its index-*.js bundle and exits 0
# only if every argument string occurs in the bundle.

set -euo pipefail

BASE="https://bilko.run"
PAGE="$BASE/projects/outdoor-hours/"

if [ "$#" -eq 0 ]; then
    echo "usage: $0 <string>..." >&2
    exit 2
fi

fetch() {
    local url=$1 i
    for i in 1 2 3; do
        if curl -sf --max-time 15 "$url"; then
            return 0
        fi
        sleep 5
    done
    return 1
}

html=$(fetch "$PAGE") || { echo "HALT: cannot fetch $PAGE"; exit 1; }
asset=$(printf '%s' "$html" | grep -o '/projects/outdoor-hours/assets/index-[^"]*\.js' | head -n1 || true)
if [ -z "$asset" ]; then
    echo "HALT: no index-*.js asset referenced by $PAGE"
    exit 1
fi
js=$(fetch "$BASE$asset") || { echo "HALT: cannot fetch $BASE$asset"; exit 1; }

for s in "$@"; do
    if ! grep -qF -- "$s" <<<"$js"; then
        echo "MISSING: $s"
        exit 1
    fi
done
echo "live ok: $asset"
