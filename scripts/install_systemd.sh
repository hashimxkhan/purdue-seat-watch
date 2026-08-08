#!/usr/bin/env bash
# Installs purdue-seat-watch's web + worker processes as systemd services on a
# Linux VPS, so they run in the background, start on boot, and restart on crash.
# Run as root (or via sudo) -- system units live under /etc/systemd/system.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_USER="${DEPLOY_USER:-$(whoami)}"

if [[ ! -f "$REPO_DIR/.env" ]]; then
    echo "error: $REPO_DIR/.env not found." >&2
    echo "Copy deploy/env.example to .env at the repo root and fill in real values first." >&2
    exit 1
fi

# .env holds RESEND_API_KEY in plaintext; keep it readable only by the user the
# services run as, not world-readable (systemd's default umask would otherwise
# leave it at 644).
chown "$DEPLOY_USER" "$REPO_DIR/.env"
chmod 600 "$REPO_DIR/.env"

if [[ ! -x "$REPO_DIR/.venv/bin/uvicorn" ]]; then
    echo "error: $REPO_DIR/.venv/bin/uvicorn not found." >&2
    echo "Run 'python3 -m venv .venv && source .venv/bin/activate && pip install -e \".[web]\"' first." >&2
    exit 1
fi

for name in web worker; do
    dest="/etc/systemd/system/purdue-seat-watch-${name}.service"
    sed -e "s|__REPO_DIR__|$REPO_DIR|g" -e "s|__DEPLOY_USER__|$DEPLOY_USER|g" \
        "$REPO_DIR/deploy/purdue-seat-watch-${name}.service.example" > "$dest"
done

systemctl daemon-reload
systemctl enable --now purdue-seat-watch-web purdue-seat-watch-worker

echo "Installed and started purdue-seat-watch-web and purdue-seat-watch-worker."
echo "Status: systemctl status purdue-seat-watch-web purdue-seat-watch-worker"
echo "Logs: journalctl -u purdue-seat-watch-web -f (or -worker)"
echo "To uninstall: scripts/uninstall_systemd.sh"
