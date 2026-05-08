"""Integrated Raspberry Pi robot runtime for camera object detection and LiDAR."""
from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import signal
import time
from typing import List

from .camera import CameraModule
from .lidar_ld19 import LD19Lidar, LidarPoint
from .lidar_objects import LD19_MAX_RANGE_M, LidarObject, LidarObjectLocalizer
from .object_detection import Detection, ObjectDetector

logger = logging.getLogger(__name__)


@dataclass
class RuntimeConfig:
    camera_index: int = 0
    camera_width: int = 640
    camera_height: int = 480
    lidar_port: str = "/dev/ttyUSB0"
    lidar_baudrate: int = 230400
    show_window: bool = False
    disable_camera: bool = False
    disable_lidar: bool = False
    status_interval: float = 1.0
    lidar_max_range_m: float = LD19_MAX_RANGE_M


class RobotRuntime:
    """Owns camera, detector, and LiDAR lifecycle."""

    def __init__(self, config: RuntimeConfig):
        self.config = config
        self.running = True
        self.camera = None if config.disable_camera else CameraModule(
            config.camera_index,
            config.camera_width,
            config.camera_height,
        )
        self.detector = None if config.disable_camera else ObjectDetector()
        self.lidar = None if config.disable_lidar else LD19Lidar(config.lidar_port, config.lidar_baudrate)
        self.lidar_localizer = LidarObjectLocalizer(max_range_m=config.lidar_max_range_m)
        self.latest_lidar_points: List[LidarPoint] = []
        self.latest_lidar_objects: List[LidarObject] = []
        self.latest_detections: List[Detection] = []

    def run(self) -> None:
        signal.signal(signal.SIGINT, self._stop_signal)
        signal.signal(signal.SIGTERM, self._stop_signal)

        if self.camera:
            self.camera.start()
        if self.lidar:
            self.lidar.start(self._on_lidar_points)

        logger.info("Robot runtime started. Press Ctrl+C to stop.")
        last_status = 0.0

        try:
            while self.running:
                frame = None
                if self.camera and self.detector:
                    frame = self.camera.read()
                    self.latest_detections = self.detector.detect(frame)
                    if self.config.show_window:
                        self._show_frame(frame)

                now = time.monotonic()
                if now - last_status >= self.config.status_interval:
                    self._print_status()
                    last_status = now

                time.sleep(0.02)
        finally:
            self.stop()

    def stop(self) -> None:
        self.running = False
        if self.lidar:
            self.lidar.stop()
        if self.camera:
            cv2 = self.camera.cv2
            self.camera.stop()
            if self.config.show_window and cv2 is not None:
                cv2.destroyAllWindows()
        logger.info("Robot runtime stopped")

    def _stop_signal(self, *_args) -> None:
        self.running = False

    def _on_lidar_points(self, points: List[LidarPoint]) -> None:
        self.latest_lidar_points = points
        self.latest_lidar_objects = self.lidar_localizer.locate(points)

    def _show_frame(self, frame) -> None:
        if not self.camera or not self.detector:
            return
        cv2 = self.camera.cv2
        if cv2 is None:
            return
        annotated = self.detector.draw(frame, self.latest_detections)
        cv2.imshow("Robot Camera - Object Detection", annotated)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            self.running = False

    def _print_status(self) -> None:
        nearest = min((p.distance for p in self.latest_lidar_points), default=None)
        payload = {
            "camera": "on" if self.camera else "off",
            "lidar": "on" if self.lidar else "off",
            "detections": [
                {"label": d.label, "confidence": round(d.confidence, 2), "box": d.box}
                for d in self.latest_detections
            ],
            "lidar_points": len(self.latest_lidar_points),
            "lidar_max_range_m": self.config.lidar_max_range_m,
            "nearest_lidar_m": round(nearest, 3) if nearest is not None else None,
            "lidar_objects": [
                {
                    "x_m": round(item.x, 3),
                    "y_m": round(item.y, 3),
                    "distance_m": round(item.distance, 3),
                    "angle_deg": round(item.angle, 1),
                    "width_m": round(item.width, 3),
                    "points": item.point_count,
                }
                for item in self.latest_lidar_objects
            ],
        }
        print(json.dumps(payload, ensure_ascii=False), flush=True)
