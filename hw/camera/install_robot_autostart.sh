#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ADMIN_TOKEN="${ADMIN_TOKEN:-apptest}"
START_SCRIPT="${BASE_DIR}/camera/start_robot_camera.sh"

if [ "$(id -u)" -ne 0 ]; then
    echo "Run with sudo: sudo bash camera/install_robot_autostart.sh" >&2
    exit 1
fi

apt install -y bluetooth bluez python3-bluez python3-opencv python3-picamera2 python3-numpy python3-dbus python3-gi
rfkill unblock bluetooth
systemctl enable bluetooth
systemctl daemon-reload

for service in robot-bluetooth-agent.service robot.service embabot.service emba.service; do
    systemctl stop "${service}" 2>/dev/null || true
    systemctl disable "${service}" 2>/dev/null || true
done

mkdir -p /etc/systemd/system/bluetooth.service.d
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

cat >/etc/systemd/system/bluetooth.service.d/compat.conf <<EOF
[Service]
ExecStart=
ExecStart=${BLUETOOTHD} --compat
EOF

systemctl restart bluetooth
chmod 777 /run/sdp 2>/dev/null || true
chmod +x "${START_SCRIPT}"

cat >/etc/systemd/system/robot-camera.service <<EOF
[Unit]
Description=EMBA robot Bluetooth LiDAR camera server
After=bluetooth.service
Requires=bluetooth.service

[Service]
Type=simple
WorkingDirectory=${BASE_DIR}
ExecStartPre=-/bin/sh -c 'command -v rfkill >/dev/null 2>&1 && rfkill unblock bluetooth || true'
ExecStartPre=-/bin/chmod 777 /run/sdp
Environment=ADMIN_TOKEN=${ADMIN_TOKEN}
Environment=ROBOT_ENABLE_CAMERA=1
ExecStart=/bin/bash ${START_SCRIPT}
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable robot-camera.service
systemctl restart robot-camera.service
systemctl --no-pager --full status robot-camera.service
