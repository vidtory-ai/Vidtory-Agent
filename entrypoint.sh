#!/bin/sh
# entrypoint.sh — Vidtory-Agent Docker entrypoint
# Checks data dir permissions and auto-runs SQLite migration on first start.

set -e

dir="$HOME/.vidtoryagent"

# Permission check
if [ -d "$dir" ] && [ ! -w "$dir" ]; then
    owner_uid=$(stat -c %u "$dir" 2>/dev/null || stat -f %u "$dir" 2>/dev/null)
    cat >&2 <<EOF
Error: $dir is not writable (owned by UID $owner_uid, running as UID $(id -u)).

Fix (pick one):
  Host:   sudo chown -R 1000:1000 ~/.vidtoryagent
  Docker: docker run --user \$(id -u):\$(id -g) ...
  Podman: podman run --userns=keep-id ...
EOF
    exit 1
fi

# Auto-migrate JSON files to SQLite on startup (idempotent — safe to run always)
if [ -f "$dir/config.json" ] || [ -f "$dir/telegram_keys.json" ]; then
    echo "[entrypoint] Running database migration (idempotent)..."
    vidtoryagent run-migration 2>/dev/null || \
        python -m nanobot.db.migrate_to_sqlite 2>/dev/null || true
fi

exec vidtoryagent "$@"
