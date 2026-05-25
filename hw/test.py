"""Simple Raspberry Pi forward/stop test for the Arduino L298N bridge.

Runs forward for 3 seconds, stops for 1 second, then repeats until Ctrl+C.
"""
from __future__ import annotations

import argparse
from glob import glob
import time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test Arduino L298N bridge forward/stop motion.")
    parser.add_argument("--port", default=None, help="Arduino serial port. Auto-detected if omitted.")
    parser.add_argument("--baudrate", type=int, default=115200, help="Arduino serial baudrate.")
    parser.add_argument("--forward", type=float, default=3.0, help="Seconds to drive forward.")
    parser.add_argument("--stop", type=float, default=1.0, help="Seconds to stop between forward pulses.")
    return parser.parse_args()


def find_serial_port() -> str | None:
    candidates = []
    for pattern in ("/dev/ttyACM*", "/dev/ttyUSB*"):
        candidates.extend(sorted(glob(pattern)))
    return candidates[0] if candidates else None


def available_ports_text() -> str:
    candidates = []
    for pattern in ("/dev/ttyACM*", "/dev/ttyUSB*"):
        candidates.extend(sorted(glob(pattern)))
    if not candidates:
        return "No /dev/ttyACM* or /dev/ttyUSB* ports found."
    return "Available serial ports: " + ", ".join(candidates)


def write_command(serial_port, command: str) -> None:
    print(command, flush=True)
    serial_port.write((command + "\n").encode("ascii"))
    serial_port.flush()
    drain_serial(serial_port, duration_s=0.03)


def drain_serial(serial_port, duration_s: float = 0.5) -> None:
    deadline = time.monotonic() + duration_s
    while time.monotonic() < deadline:
        raw = serial_port.readline()
        if raw:
            print("<", raw.decode("utf-8", errors="replace").strip(), flush=True)
        else:
            time.sleep(0.01)


def main() -> None:
    args = parse_args()
    port = args.port or find_serial_port()
    if port is None:
        raise SystemExit(
            "Arduino serial port was not found.\n"
            f"{available_ports_text()}\n"
            "Check the USB cable, Arduino power, and run: ls /dev/ttyACM* /dev/ttyUSB*"
        )

    try:
        import serial  # type: ignore
    except Exception as exc:
        raise SystemExit(f"pyserial is required. Install it with: pip install pyserial\n{exc}") from exc

    try:
        arduino = serial.Serial(port, args.baudrate, timeout=0.1, write_timeout=0.5)
    except Exception as exc:
        raise SystemExit(
            f"Could not open {port}: {exc}\n"
            f"{available_ports_text()}\n"
            "Try another port with: python3 test.py --port /dev/ttyUSB0"
        ) from exc

    with arduino:
        time.sleep(2.0)
        print(f"Connected to {port} at {args.baudrate} baud")
        drain_serial(arduino, duration_s=1.0)
        print("Press Ctrl+C to stop.")

        try:
            while True:
                write_command(arduino, "F")
                time.sleep(args.forward)

                write_command(arduino, "S")
                time.sleep(args.stop)
        except KeyboardInterrupt:
            print("\nStopping motors.")
        finally:
            write_command(arduino, "S")


if __name__ == "__main__":
    main()
