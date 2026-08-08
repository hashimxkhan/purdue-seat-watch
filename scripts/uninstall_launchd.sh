#!/usr/bin/env bash
# Stops and removes the purdue-seat-watch launchd agent installed by
# install_launchd.sh.
set -euo pipefail

PLIST_LABEL="com.purdueseatwatch.watch"
PLIST_DEST="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

if [[ -f "$PLIST_DEST" ]]; then
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
    rm "$PLIST_DEST"
    echo "Uninstalled $PLIST_LABEL."
else
    echo "$PLIST_DEST not found; nothing to do."
fi
