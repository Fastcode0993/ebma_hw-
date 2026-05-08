"""LDROBOT LD19 LiDAR serial reader."""
from __future__ import annotations

from dataclasses import dataclass
import logging
import struct
import threading
from typing import Callable, Iterable, List, Optional

logger = logging.getLogger(__name__)

LD19_PACKET_SIZE = 47
LD19_HEADER = 0x54
LD19_VER_LEN = 0x2C
LD19_POINTS_PER_PACKET = 12


@dataclass
class LidarPoint:
    """One LiDAR point in polar coordinates."""

    angle: float
    distance: float
    confidence: int


class LD19Lidar:
    """Read LD19 scan packets from a serial port in a background thread."""

    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 230400):
        self.port = port
        self.baudrate = baudrate
        self._serial = None
        self._thread: Optional[threading.Thread] = None
        self._running = threading.Event()
        self._callback: Optional[Callable[[List[LidarPoint]], None]] = None

    def start(self, callback: Callable[[List[LidarPoint]], None]) -> None:
        try:
            import serial  # type: ignore
        except Exception as exc:
            raise RuntimeError("pyserial is required for LD19 LiDAR") from exc

        self._callback = callback
        self._serial = serial.Serial(self.port, self.baudrate, timeout=1)
        self._running.set()
        self._thread = threading.Thread(target=self._read_loop, name="LD19Lidar", daemon=True)
        self._thread.start()
        logger.info("LD19 LiDAR started on %s at %s baud", self.port, self.baudrate)

    def stop(self) -> None:
        self._running.clear()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    def _read_loop(self) -> None:
        buffer = bytearray()
        while self._running.is_set():
            try:
                chunk = self._serial.read(128) if self._serial else b""
                if not chunk:
                    continue
                buffer.extend(chunk)
                for points in self._parse_buffer(buffer):
                    if points and self._callback:
                        self._callback(points)
            except Exception as exc:
                logger.warning("LiDAR read error: %s", exc)

    def _parse_buffer(self, buffer: bytearray) -> Iterable[List[LidarPoint]]:
        while len(buffer) >= LD19_PACKET_SIZE:
            if buffer[0] != LD19_HEADER:
                del buffer[0]
                continue
            if buffer[1] != LD19_VER_LEN:
                del buffer[0]
                continue

            packet = bytes(buffer[:LD19_PACKET_SIZE])
            del buffer[:LD19_PACKET_SIZE]
            points = self.parse_packet(packet)
            if points:
                yield points

    @staticmethod
    def parse_packet(packet: bytes) -> List[LidarPoint]:
        """Parse one 47-byte LD19 packet into points."""
        if len(packet) != LD19_PACKET_SIZE:
            return []
        if packet[0] != LD19_HEADER or packet[1] != LD19_VER_LEN:
            return []

        start_angle = struct.unpack_from("<H", packet, 4)[0] / 100.0
        end_angle = struct.unpack_from("<H", packet, 42)[0] / 100.0
        span = (end_angle - start_angle) % 360.0
        step = span / (LD19_POINTS_PER_PACKET - 1)

        points: List[LidarPoint] = []
        offset = 6
        for index in range(LD19_POINTS_PER_PACKET):
            distance_mm = struct.unpack_from("<H", packet, offset)[0]
            confidence = packet[offset + 2]
            offset += 3
            if distance_mm <= 0:
                continue
            angle = (start_angle + step * index) % 360.0
            points.append(LidarPoint(angle=angle, distance=distance_mm / 1000.0, confidence=confidence))
        return points

