#!/usr/bin/env bash
# Installs purdue-seat-watch as a macOS launchd agent so it runs in the
# background, survives terminal close, and restarts on crash.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST_LABEL="com.purdueseatwatch.watch"
PLIST_DEST="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

if [[ ! -f "$REPO_DIR/watches.yaml" ]]; then
    echo "error: $REPO_DIR/watches.yaml not found." >&2
    echo "Copy watches.example.yaml to watches.yaml and edit it first." >&2
    exit 1
fi

if [[ ! -x "$REPO_DIR/.venv/bin/purdue-seat-watch" ]]; then
    echo "error: $REPO_DIR/.venv/bin/purdue-seat-watch not found." >&2
    echo "Run 'python3 -m venv .venv && source .venv/bin/activate && pip install -e .' first." >&2
    exit 1
fi

mkdir -p "$REPO_DIR/logs"

sed "s|__REPO_DIR__|$REPO_DIR|g" "$REPO_DIR/launchd/com.purdueseatwatch.watch.plist.example" > "$PLIST_DEST"

launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"

echo "Installed and started $PLIST_LABEL."
echo "Logs: $REPO_DIR/logs/watch.out.log (and .err.log)"
echo "To stop: launchctl unload $PLIST_DEST"
echo "To uninstall: scripts/uninstall_launchd.sh"
