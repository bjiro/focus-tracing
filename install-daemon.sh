#!/usr/bin/env bash
set -e

SERVICE=focus-tracing
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_FILE="$UNIT_DIR/$SERVICE.service"

mkdir -p "$UNIT_DIR"
cp "$(dirname "$0")/$SERVICE.service" "$UNIT_FILE"

systemctl --user daemon-reload
systemctl --user enable "$SERVICE"
systemctl --user start "$SERVICE"

echo "Daemon installed and started."
echo ""
echo "Useful commands:"
echo "  systemctl --user status $SERVICE"
echo "  systemctl --user stop $SERVICE"
echo "  systemctl --user restart $SERVICE"
echo "  journalctl --user -u $SERVICE -f"
