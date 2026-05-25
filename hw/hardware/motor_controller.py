"""Optional Arduino serial motor controller for differential drive."""
from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class MotorTelemetry:
    """Latest optional telemetry received from the Arduino bridge."""

    updated_at: float
    raw: Dict[str, Any]


class ArduinoMotorController:
    """
    Send left/right wheel commands to an Arduino Mega over serial.

    The paired Arduino sketch in ``hw/arduino/motor_bridge`` accepts:
    - ``D <left_pwm> <right_pwm>`` where each PWM is -255..255
    - ``S`` for an immediate stop

    Incoming Arduino JSON lines are optional and stored as telemetry.
    """

    def __init__(self, port: str = "/dev/ttyACM0", baudrate: int = 115200, command_timeout_s: float = 0.5):
        self.port = port
        self.baudrate = baudrate
        self.command_timeout_s = command_timeout_s
        self._serial = None
        self._reader: Optional[threading.Thread] = None
        self._running = threading.Event()
        self._lock = threading.Lock()
        self.telemetry: Optional[MotorTelemetry] = None
        self.last_command = (0.0, 0.0)
        self.available = False

    def start(self) -> bool:
        try:
            import serial  # type: ignore
        except Exception as exc:
            logger.warning("pyserial is required for Arduino motor control: %s", exc)
            return False

        try:
            self._serial = serial.Serial(self.port, self.baudrate, timeout=0.05, write_timeout=0.2)
            time.sleep(2.0)
        except Exception as exc:
            logger.warning("Arduino motor controller unavailable on %s: %s", self.port, exc)
            self._serial = None
            return False

        self.available = True
        self._running.set()
        self._reader = threading.Thread(target=self._read_loop, name="ArduinoMotorTelemetry", daemon=True)
        self._reader.start()
        self.stop()
        logger.info("Arduino motor controller started on %s at %s baud", self.port, self.baudrate)
        return True

    def close(self) -> None:
        self._running.clear()
        try:
            self.stop()
        except Exception:
            pass

        if self._reader is not None:
            self._reader.join(timeout=1.0)
            self._reader = None

        if self._serial is not None:
            self._serial.close()
            self._serial = None
        self.available = False

    def set_speed(self, left: float, right: float) -> None:
        left = self._clamp(left)
        right = self._clamp(right)
        left_pwm = int(round(left * 255))
        right_pwm = int(round(right * 255))
        self._write_line(f"D {left_pwm} {right_pwm}")
        self.last_command = (left, right)

    def stop(self) -> None:
        self._write_line("S")
        self.last_command = (0.0, 0.0)

    def get_status(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "connected": self.available,
            "port": self.port,
            "baudrate": self.baudrate,
            "last_command": {
                "left": round(self.last_command[0], 3),
                "right": round(self.last_command[1], 3),
            },
        }
        if self.telemetry is not None:
            payload["telemetry"] = {
                "age_s": round(time.monotonic() - self.telemetry.updated_at, 3),
                "data": self.telemetry.raw,
            }
        return payload

    def _write_line(self, line: str) -> None:
        if self._serial is None:
            return
        try:
            with self._lock:
                self._serial.write((line + "\n").encode("ascii"))
                self._serial.flush()
        except Exception as exc:
            logger.warning("Motor command failed; disabling motor controller: %s", exc)
            self.available = False

    def _read_loop(self) -> None:
        while self._running.is_set():
            if self._serial is None:
                break
            try:
                raw = self._serial.readline()
                if not raw:
                    continue
                text = raw.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                if text.startswith("{"):
                    self.telemetry = MotorTelemetry(updated_at=time.monotonic(), raw=json.loads(text))
                else:
                    logger.debug("Arduino motor bridge: %s", text)
            except Exception as exc:
                logger.debug("Motor telemetry read skipped: %s", exc)

    @staticmethod
    def _clamp(value: float) -> float:
        return max(-1.0, min(1.0, float(value)))
