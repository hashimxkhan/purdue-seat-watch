#!/usr/bin/env bash
# Stops and removes the purdue-seat-watch systemd services installed by
# install_systemd.sh. Run as root (or via sudo).
set -euo pipefail

systemctl disable --now purdue-seat-watch-web purdue-seat-watch-worker 2>/dev/null || true

for name in web worker; do
    dest="/etc/systemd/system/purdue-seat-watch-${name}.service"
    if [[ -f "$dest" ]]; then
        rm "$dest"
        echo "Removed $dest."
    fi
done

systemctl daemon-reload
echo "Uninstalled purdue-seat-watch-web and purdue-seat-watch-worker."
