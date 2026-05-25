"""Raspberry Pi Bluetooth camera-only test server.

Run on the Raspberry Pi with:
  sudo python3 /home/test/test/ebma_hw-/hw/camera/testcc.py

This script puts the Pi into an isolated Bluetooth camera test mode:
  - keeps SSH/system Bluetooth alive, but stops known robot test daemons
  - sets the Bluetooth adapter alias to "apptest"
  - enables pairable/discoverable mode and registers a no-input auto-pair agent
  - starts an RFCOMM/SPP server compatible with the Android app
  - logs setup, pairing, connection, command, and camera events
"""
from __future__ import annotations

import argparse
import atexit
from glob import glob
import logging
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback
from typing import Iterable


APPTEST_NAME = "apptest"
SPP_UUID = "00001101-0000-1000-8000-00805F9B34FB"
DEFAULT_LOG_FILE = "/tmp/apptest_bluetooth_camera.log"
KNOWN_CONFLICT_SERVICES = (
    "robot-bluetooth-agent.service",
    "robot-camera.service",
    "robot.service",
    "embabot.service",
    "emba.service",
)
KNOWN_CONFLICT_PROCESS_MARKERS = (
    "testcc.py",
    "camara.py",
    "bluetooth_auto_agent.py",
    "/hw/start.py",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bluetooth SPP camera test mode for Raspberry Pi.")
    parser.add_argument("--name", default=APPTEST_NAME, help="Bluetooth adapter alias/name.")
    parser.add_argument("--channel", type=int, default=1, help="RFCOMM channel to listen on.")
    parser.add_argument("--camera-index", type=int, default=0, help="OpenCV fallback camera index.")
    parser.add_argument("--jpeg-quality", type=int, default=80, help="JPEG quality, 1..100.")
    parser.add_argument("--no-camera", action="store_true", help="Run Bluetooth server without opening a camera.")
    parser.add_argument("--no-isolate", action="store_true", help="Do not stop known robot services/processes.")
    parser.add_argument("--forget-old-devices", action="store_true", help="Remove existing Bluetooth pairings first.")
    parser.add_argument("--log-file", default=DEFAULT_LOG_FILE, help="Log file path.")
    return parser.parse_args()


def setup_logging(log_file: str) -> None:
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


def require_root() -> None:
    if os.name != "posix" or os.geteuid() != 0:
        raise SystemExit("Run with sudo: sudo python3 testcc.py")


def run(
    command: list[str],
    *,
    check: bool = False,
    timeout: float = 20.0,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    logging.info("$ %s", " ".join(command))
    try:
        completed = subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        logging.warning("Command failed to start: %s: %s", command[0], exc)
        if check:
            raise
        return subprocess.CompletedProcess(command, 127, "", str(exc))

    if completed.stdout.strip():
        logging.info("stdout: %s", completed.stdout.strip())
    if completed.stderr.strip():
        logging.info("stderr: %s", completed.stderr.strip())
    if check and completed.returncode != 0:
        raise RuntimeError(f"{' '.join(command)} failed with {completed.returncode}")
    return completed


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def current_process_tree_pids() -> set[int]:
    protected: set[int] = set()
    pid = os.getpid()
    while pid > 1 and pid not in protected:
        protected.add(pid)
        status_path = Path(f"/proc/{pid}/status")
        try:
            for line in status_path.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("PPid:"):
                    pid = int(line.split()[1])
                    break
            else:
                break
        except Exception:
            break
    return protected


def stop_known_conflicts() -> None:
    logging.info("Entering isolated camera test mode.")
    for service in KNOWN_CONFLICT_SERVICES:
        exists = run(["systemctl", "list-unit-files", service], timeout=8.0).stdout
        if service in exists:
            run(["systemctl", "stop", service], timeout=15.0)

    pgrep = run(["pgrep", "-af", "python"], timeout=8.0)
    protected_pids = current_process_tree_pids()
    for line in pgrep.stdout.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) != 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        command_line = parts[1]
        if pid in protected_pids:
            continue
        if any(marker in command_line for marker in KNOWN_CONFLICT_PROCESS_MARKERS):
            logging.info("Stopping conflicting process pid=%s cmd=%s", pid, command_line)
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    time.sleep(1.0)


def find_bluetoothd() -> str:
    for candidate in (
        shutil.which("bluetoothd"),
        "/usr/libexec/bluetooth/bluetoothd",
        "/usr/lib/bluetooth/bluetoothd",
        "/usr/sbin/bluetoothd",
    ):
        if candidate and Path(candidate).exists():
            return candidate
    raise RuntimeError("bluetoothd executable not found. Install bluez first.")


def ensure_bluetooth_compat() -> None:
    if not command_exists("systemctl"):
        logging.warning("systemctl not found; skipping bluetoothd --compat setup")
        return
    bluetoothd = find_bluetoothd()
    dropin = Path("/etc/systemd/system/bluetooth.service.d/apptest-compat.conf")
    dropin.parent.mkdir(parents=True, exist_ok=True)
    desired = (
        "[Service]\n"
        "ExecStart=\n"
        f"ExecStart={bluetoothd} --compat\n"
    )
    if not dropin.exists() or dropin.read_text(encoding="utf-8", errors="replace") != desired:
        logging.info("Writing bluetoothd compatibility drop-in: %s", dropin)
        dropin.write_text(desired, encoding="utf-8")
        run(["systemctl", "daemon-reload"], check=True, timeout=20.0)
    run(["rfkill", "unblock", "bluetooth"], timeout=10.0)
    run(["systemctl", "enable", "bluetooth"], timeout=20.0)
    run(["systemctl", "restart", "bluetooth"], check=True, timeout=30.0)
    time.sleep(2.0)
    if Path("/run/sdp").exists():
        run(["chmod", "777", "/run/sdp"], timeout=10.0)


def bluetoothctl(commands: Iterable[str], timeout: float = 12.0) -> str:
    if not command_exists("bluetoothctl"):
        logging.warning("bluetoothctl not found")
        return ""
    script = "\n".join(commands) + "\n"
    completed = run(["bluetoothctl"], timeout=timeout, input_text=script)
    return completed.stdout + completed.stderr


def list_paired_devices() -> str:
    output = bluetoothctl(["devices Paired"], timeout=8.0)
    if "Invalid command" in output:
        output = bluetoothctl(["paired-devices"], timeout=8.0)
    return output


def configure_adapter_cli(name: str, forget_old_devices: bool) -> None:
    commands = [
        "power on",
        f"system-alias {name}",
        "pairable on",
        "discoverable on",
        "show",
        "devices Paired",
    ]
    output = bluetoothctl(commands)
    logging.info("bluetoothctl setup complete")
    if "Invalid command" in output:
        output = list_paired_devices()
    if forget_old_devices:
        for line in output.splitlines():
            if line.startswith("Device "):
                address = line.split()[1]
                bluetoothctl([f"remove {address}"], timeout=8.0)
        list_paired_devices()


def import_dbus_agent():
    try:
        import dbus  # type: ignore
        import dbus.mainloop.glib  # type: ignore
        import dbus.service  # type: ignore
        from gi.repository import GLib  # type: ignore
    except Exception as exc:
        logging.warning("D-Bus auto-pair agent unavailable: %s", exc)
        logging.warning("Install with: sudo apt install -y python3-dbus python3-gi")
        return None
    return dbus, GLib


def start_auto_pair_agent(name: str) -> threading.Thread | None:
    imported = import_dbus_agent()
    if imported is None:
        return None
    dbus, GLib = imported

    bus_name = "org.bluez"
    agent_interface = "org.bluez.Agent1"
    agent_manager_interface = "org.bluez.AgentManager1"
    adapter_interface = "org.bluez.Adapter1"
    device_interface = "org.bluez.Device1"
    properties_interface = "org.freedesktop.DBus.Properties"
    agent_path = "/apptest/AutoPairAgent"

    class AutoPairAgent(dbus.service.Object):  # type: ignore[name-defined]
        def __init__(self, bus):
            super().__init__(bus, agent_path)
            self.bus = bus

        def trust_device(self, device_path: str) -> None:
            try:
                props = dbus.Interface(self.bus.get_object(bus_name, device_path), properties_interface)
                props.Set(device_interface, "Trusted", dbus.Boolean(1))
                logging.info("Trusted device path=%s", device_path)
            except Exception as exc:
                logging.warning("Failed to trust device path=%s: %s", device_path, exc)

        @dbus.service.method(agent_interface, in_signature="", out_signature="")
        def Release(self):
            logging.info("Agent released")

        @dbus.service.method(agent_interface, in_signature="os", out_signature="")
        def AuthorizeService(self, device, uuid):
            logging.info("AuthorizeService device=%s uuid=%s", device, uuid)
            self.trust_device(device)

        @dbus.service.method(agent_interface, in_signature="o", out_signature="s")
        def RequestPinCode(self, device):
            logging.info("RequestPinCode device=%s -> 0000", device)
            self.trust_device(device)
            return "0000"

        @dbus.service.method(agent_interface, in_signature="o", out_signature="u")
        def RequestPasskey(self, device):
            logging.info("RequestPasskey device=%s -> 000000", device)
            self.trust_device(device)
            return dbus.UInt32(0)

        @dbus.service.method(agent_interface, in_signature="ouq", out_signature="")
        def DisplayPasskey(self, device, passkey, entered):
            logging.info("DisplayPasskey device=%s passkey=%06d entered=%d", device, passkey, entered)

        @dbus.service.method(agent_interface, in_signature="os", out_signature="")
        def DisplayPinCode(self, device, pincode):
            logging.info("DisplayPinCode device=%s pincode=%s", device, pincode)

        @dbus.service.method(agent_interface, in_signature="ou", out_signature="")
        def RequestConfirmation(self, device, passkey):
            logging.info("Auto-confirm pairing device=%s passkey=%06d", device, passkey)
            self.trust_device(device)

        @dbus.service.method(agent_interface, in_signature="o", out_signature="")
        def RequestAuthorization(self, device):
            logging.info("Auto-authorize device=%s", device)
            self.trust_device(device)

        @dbus.service.method(agent_interface, in_signature="", out_signature="")
        def Cancel(self):
            logging.info("Agent request cancelled")

    def agent_loop() -> None:
        try:
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            bus = dbus.SystemBus()
            manager = dbus.Interface(bus.get_object(bus_name, "/"), "org.freedesktop.DBus.ObjectManager")
            objects = manager.GetManagedObjects()
            adapter_path = None
            for path, interfaces in objects.items():
                if adapter_interface in interfaces:
                    adapter_path = path
                    break
            if adapter_path is None:
                raise RuntimeError("Bluetooth adapter not found")
            adapter_props = dbus.Interface(bus.get_object(bus_name, adapter_path), properties_interface)
            adapter_props.Set(adapter_interface, "Powered", dbus.Boolean(1))
            adapter_props.Set(adapter_interface, "Alias", dbus.String(name))
            adapter_props.Set(adapter_interface, "Pairable", dbus.Boolean(1))
            adapter_props.Set(adapter_interface, "DiscoverableTimeout", dbus.UInt32(0))
            adapter_props.Set(adapter_interface, "Discoverable", dbus.Boolean(1))

            AutoPairAgent(bus)
            agent_manager = dbus.Interface(bus.get_object(bus_name, "/org/bluez"), agent_manager_interface)
            try:
                agent_manager.UnregisterAgent(agent_path)
            except Exception:
                pass
            agent_manager.RegisterAgent(agent_path, "NoInputNoOutput")
            agent_manager.RequestDefaultAgent(agent_path)
            logging.info("Auto-pair agent registered. adapter=%s alias=%s", adapter_path, name)
            GLib.MainLoop().run()
        except Exception:
            logging.error("Auto-pair agent stopped unexpectedly:\n%s", traceback.format_exc())

    thread = threading.Thread(target=agent_loop, name="AutoPairAgent", daemon=True)
    thread.start()
    time.sleep(1.0)
    return thread


class Camera:
    def __init__(self, camera_index: int, jpeg_quality: int):
        self.camera_index = camera_index
        self.jpeg_quality = max(1, min(100, jpeg_quality))
        self.picamera = None
        self.cv2 = None
        self.capture = None

    def start(self) -> None:
        try:
            from picamera2 import Picamera2  # type: ignore

            camera = Picamera2()
            config = camera.create_still_configuration(main={"size": (640, 480), "format": "RGB888"})
            camera.configure(config)
            camera.start()
            self.picamera = camera
            logging.info("Camera started with Picamera2")
            return
        except Exception as exc:
            logging.info("Picamera2 unavailable, trying OpenCV: %s", exc)

        import cv2  # type: ignore

        capture = cv2.VideoCapture(self.camera_index)
        if not capture.isOpened():
            raise RuntimeError(f"OpenCV camera index {self.camera_index} did not open")
        self.cv2 = cv2
        self.capture = capture
        logging.info("Camera started with OpenCV VideoCapture(%s)", self.camera_index)

    def capture_jpeg(self) -> bytes:
        if self.picamera is not None:
            frame = self.picamera.capture_array()
            import cv2  # type: ignore

            ok, encoded = cv2.imencode(
                ".jpg",
                frame,
                [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
            )
            if not ok:
                raise RuntimeError("Picamera2 JPEG encode failed")
            return encoded.tobytes()

        if self.capture is None or self.cv2 is None:
            raise RuntimeError("Camera is not started")

        ok, frame = self.capture.read()
        if not ok or frame is None:
            raise RuntimeError("OpenCV camera frame read failed")
        ok, encoded = self.cv2.imencode(
            ".jpg",
            frame,
            [int(self.cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
        )
        if not ok:
            raise RuntimeError("OpenCV JPEG encode failed")
        return encoded.tobytes()

    def stop(self) -> None:
        if self.picamera is not None:
            self.picamera.stop()
            self.picamera.close()
            self.picamera = None
        if self.capture is not None:
            self.capture.release()
            self.capture = None


def read_line(sock) -> str:
    data = bytearray()
    while True:
        chunk = sock.recv(1)
        if not chunk:
            raise ConnectionError("Bluetooth client disconnected while reading")
        if chunk in (b"\n", b"\r"):
            if data:
                return data.decode("utf-8", errors="replace").strip()
            continue
        data.extend(chunk)
        if len(data) > 256:
            raise ValueError("Command line too long")


def send_all(sock, payload: bytes) -> None:
    data = bytes(payload)
    offset = 0
    while offset < len(data):
        sent = sock.send(data[offset:])
        if sent <= 0:
            raise ConnectionError("Bluetooth send failed")
        offset += sent


def log_system_snapshot() -> None:
    logging.info("===== Bluetooth system snapshot =====")
    for command in (
        ["uname", "-a"],
        ["hciconfig", "-a"],
        ["bluetoothctl", "show"],
        ["bluetoothctl", "devices", "Paired"],
        ["systemctl", "--no-pager", "--full", "status", "bluetooth"],
    ):
        if command_exists(command[0]):
            run(command, timeout=10.0)


def start_spp_server(args: argparse.Namespace) -> None:
    try:
        import bluetooth  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "Python bluetooth module is missing. Install with: "
            "sudo apt install -y python3-bluez"
        ) from exc

    camera = None
    if args.no_camera:
        logging.warning("Camera disabled by --no-camera; PHOTO will return ERR camera_unavailable")
    else:
        camera = Camera(args.camera_index, args.jpeg_quality)
        try:
            camera.start()
        except Exception as exc:
            logging.warning("Camera unavailable; PHOTO will return ERR camera_unavailable: %s", exc)
            camera = None
    if camera is not None:
        atexit.register(camera.stop)

    server_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
    server_sock.bind(("", args.channel))
    server_sock.listen(1)
    port = server_sock.getsockname()[1]
    atexit.register(server_sock.close)

    try:
        bluetooth.advertise_service(
            server_sock,
            "apptest-camera",
            service_id=SPP_UUID,
            service_classes=[SPP_UUID, bluetooth.SERIAL_PORT_CLASS],
            profiles=[bluetooth.SERIAL_PORT_PROFILE],
        )
        logging.info("SPP SDP service advertised. uuid=%s channel=%s", SPP_UUID, port)
    except Exception as exc:
        logging.warning("SPP SDP advertise failed; fixed RFCOMM channel still active: %s", exc)
        logging.warning("If Android cannot connect, verify bluetoothd is running with --compat and /run/sdp is writable.")

    logging.info("Ready. Android should scan for Bluetooth name '%s' and connect to RFCOMM channel %s.", args.name, port)
    logging.info("Log file: %s", args.log_file)

    while True:
        client_sock = None
        try:
            logging.info("Waiting for Android connection...")
            client_sock, client_info = server_sock.accept()
            logging.info("Accepted Android connection from %s", client_info)
            while True:
                command = read_line(client_sock).upper()
                logging.info("Command from Android: %s", command)
                if command in {"F", "FORWARD"}:
                    send_all(client_sock, b"OK F camera_test_only\n")
                elif command in {"B", "R", "BACK", "BACKWARD"}:
                    send_all(client_sock, b"OK B camera_test_only\n")
                elif command in {"S", "STOP"}:
                    send_all(client_sock, b"OK S camera_test_only\n")
                elif command.startswith("SPD "):
                    send_all(client_sock, f"OK {command} camera_test_only\n".encode("ascii"))
                elif command == "ENC":
                    send_all(client_sock, b"OK ENC 0 camera_test_only\n")
                elif command in {"US", "DIST", "ULTRA"}:
                    send_all(client_sock, b"{\"command\":\"ultrasonic\",\"trig\":52,\"echo\":53,\"distance_cm\":42.0,\"camera_test_only\":true}\n")
                elif command == "PHOTO":
                    if camera is None:
                        send_all(client_sock, b"ERR camera_unavailable\n")
                    else:
                        jpeg = camera.capture_jpeg()
                        logging.info("Sending JPEG bytes=%s", len(jpeg))
                        send_all(client_sock, f"JPEG {len(jpeg)}\n".encode("ascii"))
                        send_all(client_sock, jpeg)
                elif command in {"PING", "HELLO"}:
                    send_all(client_sock, b"OK READY apptest\n")
                else:
                    send_all(client_sock, b"ERR unknown_command\n")
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            logging.warning("Client session ended: %s", exc)
            logging.info("Session traceback:\n%s", traceback.format_exc())
        finally:
            if client_sock is not None:
                try:
                    client_sock.close()
                except Exception:
                    pass


def main() -> None:
    args = parse_args()
    setup_logging(args.log_file)
    require_root()
    logging.info("Starting apptest Bluetooth camera test server")
    logging.info("Arguments: %s", args)
    if not args.no_isolate:
        stop_known_conflicts()
    ensure_bluetooth_compat()
    configure_adapter_cli(args.name, args.forget_old_devices)
    start_auto_pair_agent(args.name)
    log_system_snapshot()
    start_spp_server(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Stopped by Ctrl+C")
