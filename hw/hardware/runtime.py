"""Integrated Raspberry Pi robot runtime for sensing and optional autonomy."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import signal
import time
from typing import List

from .autonomy import AutonomyConfig, DriveDecision, ObstacleAvoidanceNavigator
from .camera import CameraModule
from .lidar_ld19 import LD19Lidar, LidarPoint
from .lidar_objects import LD19_MAX_RANGE_M, LidarObject, LidarObjectLocalizer
from .motor_controller import ArduinoMotorController
from .object_detection import Detection, ObjectDetector

logger = logging.getLogger(__name__)


@dataclass
class RuntimeConfig:
    camera_index: int = 0
    camera_width: int = 640
    camera_height: int = 480
    lidar_port: str = "/dev/ttyUSB0"
    lidar_baudrate: int = 230400
    motor_port: str = "/dev/ttyACM0"
    motor_baudrate: int = 115200
    show_window: bool = False
    disable_camera: bool = False
    disable_lidar: bool = False
    disable_motor: bool = False
    autonomous_enabled: bool = False
    status_interval: float = 1.0
    lidar_max_range_m: float = LD19_MAX_RANGE_M
    autonomy: AutonomyConfig = field(default_factory=AutonomyConfig)


class RobotRuntime:
    """Owns sensor, motor, and autonomous driving lifecycle."""

    def __init__(self, config: RuntimeConfig):
        self.config = config
        self.running = True
        self.camera = None
        self.detector = None
        self.lidar = None if config.disable_lidar else LD19Lidar(config.lidar_port, config.lidar_baudrate)
        self.motor = None if config.disable_motor else ArduinoMotorController(config.motor_port, config.motor_baudrate)
        self.navigator = ObstacleAvoidanceNavigator(config.autonomy)
        self.lidar_localizer = LidarObjectLocalizer(max_range_m=config.lidar_max_range_m)
        self.latest_lidar_points: List[LidarPoint] = []
        self.latest_lidar_objects: List[LidarObject] = []
        self.latest_detections: List[Detection] = []
        self.latest_drive_decision: DriveDecision | None = None

    def run(self) -> None:
        signal.signal(signal.SIGINT, self._stop_signal)
        signal.signal(signal.SIGTERM, self._stop_signal)

        self._start_camera()
        self._start_lidar()
        self._start_motor()

        logger.info("Robot runtime started. Press Ctrl+C to stop.")
        last_status = 0.0

        try:
            while self.running:
                self._read_camera()

                if self.config.autonomous_enabled:
                    self._run_autonomy()

                now = time.monotonic()
                if now - last_status >= self.config.status_interval:
                    self._print_status()
                    last_status = now

                time.sleep(0.02)
        finally:
            self.stop()

    def stop(self) -> None:
        self.running = False
        if self.motor:
            self.motor.close()
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

    def _start_camera(self) -> None:
        if self.config.disable_camera:
            return
        camera = None
        try:
            camera = CameraModule(self.config.camera_index, self.config.camera_width, self.config.camera_height)
            camera.start()
            self.camera = camera
            self.detector = ObjectDetector()
        except Exception as exc:
            logger.warning("Camera unavailable; continuing without camera: %s", exc)
            if camera is not None:
                try:
                    camera.stop()
                except Exception:
                    pass
            self.camera = None
            self.detector = None

    def _start_lidar(self) -> None:
        if self.lidar is None:
            return
        try:
            self.lidar.start(self._on_lidar_points)
        except Exception as exc:
            logger.warning("LiDAR unavailable; continuing without LiDAR: %s", exc)
            self.lidar = None

    def _start_motor(self) -> None:
        if self.motor is None:
            return
        if not self.motor.start():
            self.motor = None
            if self.config.autonomous_enabled:
                logger.warning("Autonomous mode requested, but motor controller is unavailable.")

    def _read_camera(self) -> None:
        if not self.camera or not self.detector:
            return
        try:
            frame = self.camera.read()
            self.latest_detections = self.detector.detect(frame)
            if self.config.show_window:
                self._show_frame(frame)
        except Exception as exc:
            logger.warning("Camera read failed; disabling camera: %s", exc)
            self.latest_detections = []
            self.camera.stop()
            self.camera = None
            self.detector = None

    def _run_autonomy(self) -> None:
        motor_available = bool(self.motor and self.motor.available)
        decision = self.navigator.decide(
            self.latest_lidar_points,
            self.latest_detections,
            motor_available=motor_available,
        )
        self.latest_drive_decision = decision

        if not self.motor:
            return
        if decision.left == 0.0 and decision.right == 0.0:
            self.motor.stop()
        else:
            self.motor.set_speed(decision.left, decision.right)

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
            "motor": self.motor.get_status() if self.motor else {"connected": False},
            "autonomous_enabled": self.config.autonomous_enabled,
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
        if self.latest_drive_decision is not None:
            decision = self.latest_drive_decision
            payload["autonomy"] = {
                "state": decision.state.value,
                "reason": decision.reason,
                "obstacle_ahead": decision.obstacle_ahead,
                "front_distance_m": round(decision.front_distance_m, 3)
                if decision.front_distance_m is not None
                else None,
                "left_clearance_m": round(decision.left_clearance_m, 3)
                if decision.left_clearance_m is not None
                else None,
                "right_clearance_m": round(decision.right_clearance_m, 3)
                if decision.right_clearance_m is not None
                else None,
                "command": {
                    "left": round(decision.left, 3),
                    "right": round(decision.right, 3),
                },
            }
        print(json.dumps(payload, ensure_ascii=False), flush=True)
