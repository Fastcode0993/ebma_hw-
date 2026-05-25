#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

sudo apt install -y bluetooth bluez python3-bluez python3-opencv python3-picamera2 python3-dbus python3-gi
sudo rfkill unblock bluetooth
sudo systemctl enable bluetooth

BLUETOOTHD="$(command -v bluetoothd || true)"
if [ -z "${BLUETOOTHD}" ]; then
    for candidate in /usr/libexec/bluetooth/bluetoothd /usr/lib/bluetooth/bluetoothd /usr/sbin/bluetoothd; do
        if [ -x "${candidate}" ]; then
            BLUETOOTHD="${candidate}"
            break
        fi
    done
fi
if [ -z "${BLUETOOTHD}" ]; then
    echo "bluetoothd executable not found" >&2
    exit 1
fi

sudo mkdir -p /etc/systemd/system/bluetooth.service.d
sudo tee /etc/systemd/system/bluetooth.service.d/compat.conf >/dev/null <<EOF
[Service]
ExecStart=
ExecStart=${BLUETOOTHD} --compat
EOF

sudo systemctl restart bluetooth

if [ -S /run/sdp ]; then
    sudo chmod 777 /run/sdp
fi

sudo tee /etc/systemd/system/robot-bluetooth-agent.service >/dev/null <<EOF
[Unit]
Description=Robot Bluetooth automatic pairing agent
After=bluetooth.service
Requires=bluetooth.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 ${BASE_DIR}/bluetooth_auto_agent.py
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable robot-bluetooth-agent.service
sudo systemctl restart robot-bluetooth-agent.service

echo "Installed Bluetooth auto-pairing agent."
echo "Run server with:"
echo "  sudo python3 ${BASE_DIR}/camara.py --arduino-port /dev/ttyACM0"
