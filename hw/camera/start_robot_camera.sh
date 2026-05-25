#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIDAR_PORT="${ROBOT_LIDAR_PORT:-}"
ARDUINO_PORT="${ROBOT_ARDUINO_PORT:-}"
ADMIN_TOKEN="${ADMIN_TOKEN:-apptest}"
ENABLE_CAMERA="${ROBOT_ENABLE_CAMERA:-1}"

if [ -z "${LIDAR_PORT}" ]; then
    for candidate in /dev/serial/by-id/*; do
        [ -e "${candidate}" ] || continue
        case "${candidate}" in
            *Silicon_Labs_CP2102*|*CP2102*)
                LIDAR_PORT="${candidate}"
                break
                ;;
        esac
    done
fi

if [ -z "${LIDAR_PORT}" ]; then
    LIDAR_PORT="$(ls /dev/ttyUSB* 2>/dev/null | head -n1 || true)"
fi

LIDAR_REAL=""
if [ -n "${LIDAR_PORT}" ]; then
    LIDAR_REAL="$(readlink -f "${LIDAR_PORT}")"
fi

if [ -z "${ARDUINO_PORT}" ]; then
    for candidate in /dev/serial/by-id/* /dev/ttyACM* /dev/ttyUSB*; do
        [ -e "${candidate}" ] || continue
        candidate_real="$(readlink -f "${candidate}")"
        if [ -n "${LIDAR_REAL}" ] && [ "${candidate_real}" = "${LIDAR_REAL}" ]; then
            continue
        fi
        ARDUINO_PORT="${candidate}"
        break
    done
fi

ARGS=(
    "${BASE_DIR}/camera/camara.py"
    --admin-token "${ADMIN_TOKEN}"
)

if [ -n "${ARDUINO_PORT}" ]; then
    ARGS+=(--arduino-port "${ARDUINO_PORT}")
fi

if [ -n "${LIDAR_PORT}" ]; then
    ARGS+=(--lidar-port "${LIDAR_PORT}" --lidar-baudrate 230400)
fi

if [ "${ENABLE_CAMERA}" = "1" ]; then
    ARGS+=(--object-model "${BASE_DIR}/camera/yolov8n.onnx")
else
    ARGS+=(--no-camera)
fi

exec /usr/bin/python3 "${ARGS[@]}"
