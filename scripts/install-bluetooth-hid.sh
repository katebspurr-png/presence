#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
DROP_IN_SRC="$REPO_ROOT/systemd/bluetooth.service.d/presence-hid.conf"
DROP_IN_DIR="/etc/systemd/system/bluetooth.service.d"
DROP_IN_DST="$DROP_IN_DIR/presence-hid.conf"

if [[ $EUID -ne 0 ]]; then
    echo "error: must run as root" >&2
    exit 1
fi

if [[ ! -f /usr/lib/bluetooth/bluetoothd ]]; then
    echo "bluetoothd not found at /usr/lib/bluetooth/bluetoothd, installing bluez..."
    apt-get install -y bluez
fi

mkdir -p "$DROP_IN_DIR"
install -m 644 "$DROP_IN_SRC" "$DROP_IN_DST"
echo "installed $DROP_IN_DST"

systemctl daemon-reload
systemctl restart bluetooth
echo "bluetooth service restarted"
