#!/usr/bin/env bash
# Idempotently install the weekly refresh cron line into the user crontab.
# Usage: scripts/install_cron.sh [--dry-run]   (--dry-run prints, changes nothing)

set -euo pipefail

TAG="weather-weekly-refresh"
LINE="0 9 * * 1 /home/bilko/Projects/Weather/scripts/weekly_refresh.sh # $TAG"

dry_run=false
case "${1:-}" in
    "") ;;
    --dry-run) dry_run=true ;;
    *) echo "usage: $0 [--dry-run]" >&2; exit 2 ;;
esac

# An empty/missing crontab makes `crontab -l` exit 1, which is fine here.
current=$(crontab -l 2>/dev/null || true)

# grep -v exits 1 when nothing remains; that is also fine.
kept=$(printf '%s\n' "$current" | grep -vF "# $TAG" || true)

if [ -n "$kept" ]; then
    new=$(printf '%s\n%s\n' "$kept" "$LINE")
else
    new=$(printf '%s\n' "$LINE")
fi

if $dry_run; then
    printf '%s\n' "$new"
else
    printf '%s\n' "$new" | crontab -
    echo "installed: $LINE"
fi
