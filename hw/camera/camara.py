"""Bluetooth control and camera server for Raspberry Pi.

Protocol over Bluetooth RFCOMM/SPP:
  F\n       -> forward command to Arduino
  B\n       -> backward command to Arduino
  S\n       -> stop command to Arduino
  SPD 160\n -> set motor speed, 0..255
  ENC\n     -> request encoder count from Arduino
  US\n      -> request left/front/right HC-SR04 ultrasonic distances from Arduino
  AUTO_ON\n -> start Arduino-local ultrasonic avoidance mode
  AUTO_OFF\n -> stop autonomous mode
  AUTO_STATUS\n -> request autonomous mode state and sensor distances
  PERCEPTION_STATUS\n -> report Raspberry Pi camera/LiDAR integration status
  MAP_STATUS\n -> report map/navigation readiness
  MAP_SCAN\n -> return current local map snapshot status
  NAV_START <x> <y>\n -> request navigation to a map pin in meters
  NAV_STOP\n -> stop navigation and Arduino motors
  PHOTO\n   -> capture a JPEG and send: JPEG <byte_length>\n<jpeg bytes>

Run on Raspberry Pi:
  python3 camera/camara.py --arduino-port /dev/ttyACM0
"""
from __future__ import annotations

import argparse
import base64
from glob import glob
import json
import logging
import math
import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Iterable


SPP_UUID = "00001101-0000-1000-8000-00805F9B34FB"


class PerceptionStatus:
    """Reports high-level perception readiness without taking over safety control."""

    def __init__(self, camera: "Camera | None", lidar: "LD19Reader", detector: "ObjectDetector | None" = None):
        self.camera = camera
        self.lidar = lidar
        self.detector = detector

    def to_json_line(self) -> str:
        camera_state = "ready" if self.camera is not None else "unavailable"
        lidar_state = "ready" if self.lidar.has_recent_scan() else ("configured" if self.lidar.port else "not_configured")
        object_state = "ready" if self.detector and self.detector.ready else ("configured" if self.detector else "not_configured")
        object_count = len(self.detector.latest_detections()) if self.detector else 0
        return (
            '{"command":"perception_status",'
            f'"camera":"{camera_state}",'
            f'"object_detection":"{object_state}",'
            f'"objects":{object_count},'
            f'"lidar":"{lidar_state}",'
            '"safety_controller":"arduino_ultrasonic_3way"}'
        )


class LD19Reader:
    PACKET_SIZE = 47
    HEADER = 0x54
    VERLEN = 0x2C

    def __init__(self, port: str | None, baudrate: int = 230400):
        self.port = port
        self.baudrate = baudrate
        self.serial = None
        self.thread: threading.Thread | None = None
        self.running = False
        self.lock = threading.Lock()
        self.points: list[tuple[float, float, int]] = []
        self.last_scan_at = 0.0
        self.packet_count = 0

    def start(self) -> None:
        if not self.port:
            logging.info("LD19 LiDAR port not configured")
            return
        try:
            import serial  # type: ignore

            self.serial = serial.Serial(self.port, self.baudrate, timeout=0.2)
            self.running = True
            self.thread = threading.Thread(target=self._read_loop, name="LD19Reader", daemon=True)
            self.thread.start()
            logging.info("LD19 LiDAR reader started on %s at %s baud", self.port, self.baudrate)
        except Exception as exc:
            logging.warning("LD19 LiDAR unavailable on %s: %s", self.port, exc)
            self.serial = None
            self.running = False

    def stop(self) -> None:
        self.running = False
        if self.thread is not None:
            self.thread.join(timeout=1.0)
            self.thread = None
        if self.serial is not None:
            self.serial.close()
            self.serial = None

    def has_recent_scan(self, max_age_s: float = 1.5) -> bool:
        return time.monotonic() - self.last_scan_at <= max_age_s and bool(self.points)

    def snapshot(self) -> list[tuple[float, float, int]]:
        with self.lock:
            return list(self.points)

    def _read_loop(self) -> None:
        assert self.serial is not None
        while self.running:
            header = self.serial.read(1)
            if not header or header[0] != self.HEADER:
                continue
            rest = self.serial.read(self.PACKET_SIZE - 1)
            if len(rest) != self.PACKET_SIZE - 1:
                continue
            packet = bytes([self.HEADER]) + rest
            parsed = self._parse_packet(packet)
            if not parsed:
                continue
            with self.lock:
                self.points.extend(parsed)
                if len(self.points) > 720:
                    self.points = self.points[-720:]
                self.last_scan_at = time.monotonic()
                self.packet_count += 1

    def _parse_packet(self, packet: bytes) -> list[tuple[float, float, int]]:
        if len(packet) != self.PACKET_SIZE or packet[0] != self.HEADER or packet[1] != self.VERLEN:
            return []
        count = packet[1] & 0x1F
        if count != 12:
            return []
        start_angle = int.from_bytes(packet[4:6], "little") / 100.0
        end_angle = int.from_bytes(packet[42:44], "little") / 100.0
        angle_span = end_angle - start_angle
        if angle_span < 0:
            angle_span += 360.0
        step = angle_span / (count - 1)

        points: list[tuple[float, float, int]] = []
        offset = 6
        for index in range(count):
            distance_mm = int.from_bytes(packet[offset:offset + 2], "little")
            confidence = packet[offset + 2]
            offset += 3
            if distance_mm <= 0:
                continue
            angle = (start_angle + step * index) % 360.0
            points.append((angle, distance_mm / 1000.0, confidence))
        return points

    def scan_json(self) -> str:
        if not self.port:
            return (
                '{"command":"map_scan","ok":false,'
                '"error":"lidar_not_configured",'
                '"message":"Run camara.py with --lidar-port /dev/ttyUSB0 or the detected LD19 port."}'
            )
        if not self.has_recent_scan():
            return (
                '{"command":"map_scan","ok":false,'
                '"error":"no_recent_lidar_scan",'
                '"message":"LD19 is configured but no recent packets were decoded."}'
            )
        points = self.snapshot()
        sectors = {
            "front_m": self._sector_min(points, 330.0, 30.0),
            "left_m": self._sector_min(points, 45.0, 135.0),
            "right_m": self._sector_min(points, 225.0, 315.0),
            "rear_m": self._sector_min(points, 150.0, 210.0),
        }
        bins = self._sector_bins(points, bin_count=36)
        return (
            '{"command":"map_scan","ok":true,'
            f'"points":{len(points)},'
            f'"packets":{self.packet_count},'
            f'"front_m":{sectors["front_m"]:.2f},'
            f'"left_m":{sectors["left_m"]:.2f},'
            f'"right_m":{sectors["right_m"]:.2f},'
            f'"rear_m":{sectors["rear_m"]:.2f},'
            f'"bins_m":[{",".join(f"{value:.2f}" for value in bins)}]}}'
        )

    def _sector_min(self, points: list[tuple[float, float, int]], start: float, end: float) -> float:
        distances: list[float] = []
        for angle, distance_m, confidence in points:
            if confidence == 0:
                continue
            if self._angle_in_sector(angle, start, end):
                distances.append(distance_m)
        return min(distances) if distances else -1.0

    def _angle_in_sector(self, angle: float, start: float, end: float) -> bool:
        if start <= end:
            return start <= angle <= end
        return angle >= start or angle <= end

    def _sector_bins(self, points: list[tuple[float, float, int]], bin_count: int) -> list[float]:
        bins: list[list[float]] = [[] for _ in range(bin_count)]
        for angle, distance_m, confidence in points:
            if confidence == 0:
                continue
            index = int((angle % 360.0) / 360.0 * bin_count)
            if 0 <= index < bin_count:
                bins[index].append(distance_m)
        return [min(values) if values else -1.0 for values in bins]


class NavigationManager:
    """LiDAR-first navigation with ultrasonic validation and COCO camera classification assist."""

    FRONT_CLEAR_M = 0.85
    FRONT_DANGER_M = 0.35
    LOW_DANGER_CM = 22.0
    LOW_CLEAR_CM = 45.0
    GOAL_ALIGN_DEG = 18.0
    NORMAL_SPEED = 170
    CAUTION_SPEED = 130
    TURN_SPEED = 165
    GOAL_REACHED_M = 0.22
    FORWARD_MPS_AT_NORMAL = 0.13
    CAUTION_MPS_AT_CAUTION = 0.07
    STEER_DEG_PER_S_AT_TURN = 55.0
    BLOCKING_LABELS = {
        "person", "bicycle", "car", "motorcycle", "bus", "truck", "bench",
        "backpack", "handbag", "suitcase", "chair", "couch", "potted plant",
        "bed", "dining table", "toilet", "tv", "laptop", "cell phone",
        "book", "bottle",
    }
    OVERHANG_CANDIDATE_LABELS = {"chair", "bench", "dining table"}

    def __init__(self, arduino: "ArduinoBridge", lidar: LD19Reader, detector: "ObjectDetector | None" = None):
        self.arduino = arduino
        self.lidar = lidar
        self.detector = detector
        self.active_goal: tuple[float, float] | None = None
        self.running = False
        self.thread: threading.Thread | None = None
        self.lock = threading.Lock()
        self.state = "idle"
        self.started_at = 0.0
        self.stop_at = 0.0
        self.last_action_at = 0.0
        self.last_drive_action = ""
        self.last_drive_speed = -1
        self.last_drive_command_at = 0.0
        self.pose_x = 0.0
        self.pose_y = 0.0
        self.heading_deg = 0.0
        self.last_pose_update_at = 0.0
        self.last_snapshot: dict = {}
        self.last_decision: dict = {}

    @property
    def lidar_ready(self) -> bool:
        return self.lidar.has_recent_scan()

    def status_json(self) -> str:
        goal = "null"
        if self.active_goal is not None:
            goal = f'{{"x":{self.active_goal[0]:.2f},"y":{self.active_goal[1]:.2f}}}'
        object_count = len(self.detector.latest_detections()) if self.detector else 0
        pose = (
            f'{{"x":{self.pose_x:.2f},"y":{self.pose_y:.2f},'
            f'"heading_deg":{self.heading_deg:.1f}}}'
        )
        decision = self._json_fragment(self.last_decision)
        return (
            '{"command":"map_status",'
            f'"lidar":"{"ready" if self.lidar_ready else ("configured" if self.lidar.port else "not_configured")}",'
            f'"map_ready":{str(self.lidar_ready).lower()},'
            f'"navigating":{str(self.active_goal is not None).lower()},'
            f'"goal":{goal},'
            f'"pose":{pose},'
            f'"objects":{object_count},'
            '"planner":"lidar_ultrasonic_camera_fusion",'
            f'"state":"{self.state}",'
            f'"decision":{decision},'
            '"priority":"lidar_map_then_ultrasonic_validation_then_coco_classification"}'
        )

    def scan_json(self) -> str:
        return self.lidar.scan_json()

    def start_navigation(self, x: float, y: float) -> str:
        if not self.lidar_ready:
            with self.lock:
                self.running = False
                self.active_goal = None
                self.state = "lidar_required"
            self.arduino.send_no_wait("S")
            return (
                '{"command":"nav_start","ok":false,'
                f'"goal":{{"x":{x:.2f},"y":{y:.2f}}},'
                '"planner":"lidar_ultrasonic_camera_fusion",'
                '"error":"lidar_not_ready",'
                '"safe_stop":true}'
            )
        distance = math.sqrt(x * x + y * y)
        drive_time = min(max(distance * 4.5, 3.0), 18.0)
        with self.lock:
            self.active_goal = (x, y)
            self.running = True
            self.state = "starting"
            self.started_at = time.monotonic()
            self.stop_at = self.started_at + drive_time
            self.last_action_at = 0.0
            self.last_drive_action = ""
            self.last_drive_speed = -1
            self.last_drive_command_at = 0.0
            self.pose_x = 0.0
            self.pose_y = 0.0
            self.heading_deg = 0.0
            self.last_pose_update_at = self.started_at
            self.last_snapshot = {}
            self.last_decision = {"state": "starting"}
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self._navigation_loop, name="FusionNavigation", daemon=True)
                self.thread.start()
        self.arduino.send_no_wait("AUTO_OFF")
        self.arduino.send_no_wait("S")
        self.arduino.send_no_wait(f"SPD {self.NORMAL_SPEED}")
        return (
            '{"command":"nav_start","ok":true,'
            f'"goal":{{"x":{x:.2f},"y":{y:.2f}}},'
            f'"estimated_drive_s":{drive_time:.1f},'
            '"planner":"lidar_ultrasonic_camera_fusion",'
            '"safe_stop":false}'
        )

    def stop_navigation(self) -> str:
        with self.lock:
            self.running = False
            self.active_goal = None
            self.state = "stopped"
            self.last_drive_action = ""
            self.last_drive_speed = -1
            self.last_drive_command_at = 0.0
            self.last_decision = {"state": "stopped"}
        self.arduino.send_no_wait("AUTO_OFF")
        self.arduino.send_no_wait("S")
        return '{"command":"nav_stop","ok":true,"safe_stop":true}'

    def cancel_for_manual(self) -> None:
        with self.lock:
            if self.running or self.active_goal is not None:
                self.running = False
                self.active_goal = None
                self.state = "manual_override"
                self.last_drive_action = ""
                self.last_drive_speed = -1
                self.last_drive_command_at = 0.0
                self.last_decision = {"state": "manual_override"}

    def _navigation_loop(self) -> None:
        while True:
            with self.lock:
                if not self.running or self.active_goal is None:
                    return
                goal = self.active_goal
                stop_at = self.stop_at
            now = time.monotonic()
            self._update_pose(now)
            distance_to_goal = self._distance_to_goal(goal)
            if distance_to_goal <= self.GOAL_REACHED_M:
                self.arduino.send_no_wait("S")
                with self.lock:
                    self.running = False
                    self.active_goal = None
                    self.state = "goal_reached_by_dead_reckoning"
                    self.last_decision = {
                        "state": self.state,
                        "distance_to_goal_m": round(distance_to_goal, 2),
                    }
                return
            if now >= stop_at:
                self.arduino.send_no_wait("S")
                with self.lock:
                    self.running = False
                    self.active_goal = None
                    self.state = "estimated_goal_reached"
                return
            if now - self.last_action_at < 0.35:
                time.sleep(0.08)
                continue

            snapshot = self._fusion_snapshot(goal)
            action, state, speed = self._decide_action(snapshot)
            self._apply_action(action, speed)
            self.state = state
            self.last_snapshot = snapshot
            self.last_decision = self._decision_debug(snapshot, action, state, speed)
            self.last_action_at = now
            time.sleep(0.08)

    def _fusion_snapshot(self, goal: tuple[float, float]) -> dict:
        ultrasonic = self._read_ultrasonic()
        detection = self._front_camera_object()
        dx = goal[0] - self.pose_x
        dy = goal[1] - self.pose_y
        world_goal_angle = math.degrees(math.atan2(dx, dy if abs(dy) > 0.01 else 0.01))
        goal_angle = self._normalize_angle(world_goal_angle - self.heading_deg)
        distance_to_goal = math.sqrt(dx * dx + dy * dy)
        return {
            "front_m": self._sector_min(335.0, 25.0),
            "front_left_m": self._sector_min(15.0, 65.0),
            "front_right_m": self._sector_min(295.0, 345.0),
            "left_m": self._sector_min(45.0, 135.0),
            "right_m": self._sector_min(225.0, 315.0),
            "ultrasonic": ultrasonic,
            "detection": detection,
            "goal_angle": goal_angle,
            "distance_to_goal_m": distance_to_goal,
        }

    def _decide_action(self, snapshot: dict) -> tuple[str, str, int]:
        front_m = snapshot["front_m"]
        low_front_cm = self._cm_value(snapshot["ultrasonic"].get("front_cm"))
        detection = snapshot["detection"]
        camera_blocks_front = detection is not None and detection["label"] in self.BLOCKING_LABELS

        low_front_blocked = 0.0 < low_front_cm < self.LOW_CLEAR_CM
        low_front_danger = 0.0 < low_front_cm < self.LOW_DANGER_CM
        lidar_front_blocked = 0.0 < front_m < self.FRONT_CLEAR_M
        lidar_front_danger = 0.0 < front_m < self.FRONT_DANGER_M

        if low_front_danger:
            direction = self._best_side(snapshot)
            return direction, f"low_ultrasonic_danger_{direction}", self.TURN_SPEED
        if low_front_blocked and lidar_front_blocked:
            direction = self._best_side(snapshot)
            return direction, f"low_and_lidar_block_{direction}", self.TURN_SPEED
        if camera_blocks_front and self._camera_requires_avoidance(snapshot, lidar_front_blocked, low_front_blocked):
            direction = self._best_side(snapshot)
            return direction, f"camera_{detection['label']}_avoid_{direction}", self.TURN_SPEED
        if lidar_front_danger:
            direction = self._best_side(snapshot)
            return direction, f"lidar_near_block_{direction}", self.TURN_SPEED
        if lidar_front_blocked:
            if self._is_possible_overhang(snapshot):
                return "forward", "lidar_high_object_low_clear_caution", self.CAUTION_SPEED
            direction = self._best_side(snapshot)
            return direction, f"lidar_block_{direction}", self.TURN_SPEED

        goal_angle = snapshot["goal_angle"]
        if goal_angle < -self.GOAL_ALIGN_DEG and self._side_score(snapshot, "left") > 0.25:
            return "left", "goal_align_left", self.TURN_SPEED
        if goal_angle > self.GOAL_ALIGN_DEG and self._side_score(snapshot, "right") > 0.25:
            return "right", "goal_align_right", self.TURN_SPEED
        return "forward", "path_clear_forward", self.NORMAL_SPEED

    def _apply_action(self, action: str, speed: int) -> None:
        now = time.monotonic()
        command = {
            "forward": "F",
            "left": "STEER_L",
            "right": "STEER_R",
        }.get(action, "S")
        same_drive = action == self.last_drive_action and speed == self.last_drive_speed
        if same_drive and now - self.last_drive_command_at < 1.0:
            return
        if speed != self.last_drive_speed:
            self.arduino.send_no_wait(f"SPD {speed}")
        if action == "forward":
            self.arduino.send_no_wait("F")
        elif action == "left":
            self.arduino.send_no_wait("STEER_L")
        elif action == "right":
            self.arduino.send_no_wait("STEER_R")
        else:
            self.arduino.send_no_wait("S")
        self.last_drive_action = action
        self.last_drive_speed = speed
        self.last_drive_command_at = now

    def _read_ultrasonic(self) -> dict:
        response = self.arduino.send("US", timeout_s=0.9)
        if not response or not response.startswith("{"):
            return {}
        try:
            payload = json.loads(response)
        except Exception:
            return {}
        return payload if payload.get("command") == "ultrasonic" else {}

    def _front_camera_object(self) -> dict | None:
        if not self.detector or not self.detector.ready:
            return None
        best = None
        best_score = 0.0
        for detection in self.detector.latest_detections():
            box = detection.get("box") or [0, 0, 0, 0]
            center = detection.get("center") or [0, 0]
            if len(box) != 4 or len(center) != 2:
                continue
            center_x = float(center[0])
            if center_x < 180.0 or center_x > 460.0:
                continue
            width = max(0.0, float(box[2]) - float(box[0]))
            height = max(0.0, float(box[3]) - float(box[1]))
            confidence = float(detection.get("confidence", 0.0))
            score = confidence * max(width * height, 1.0)
            if score > best_score:
                best_score = score
                best = detection
        return best

    def _is_possible_overhang(self, snapshot: dict) -> bool:
        low_front_cm = self._cm_value(snapshot["ultrasonic"].get("front_cm"))
        detection = snapshot["detection"]
        if low_front_cm <= 70.0:
            return False
        if detection is None:
            return True
        return detection.get("label") in self.OVERHANG_CANDIDATE_LABELS

    def _camera_requires_avoidance(self, snapshot: dict, lidar_blocked: bool, low_blocked: bool) -> bool:
        detection = snapshot["detection"]
        if detection is None:
            return False
        label = detection.get("label")
        if label == "person":
            return True
        if label in self.OVERHANG_CANDIDATE_LABELS and self._is_possible_overhang(snapshot):
            return False
        return lidar_blocked or low_blocked

    def _best_side(self, snapshot: dict) -> str:
        goal_angle = snapshot.get("goal_angle", 0.0)
        left_score = self._side_score(snapshot, "left")
        right_score = self._side_score(snapshot, "right")
        if goal_angle < -self.GOAL_ALIGN_DEG and left_score > 0.35:
            return "left"
        if goal_angle > self.GOAL_ALIGN_DEG and right_score > 0.35:
            return "right"
        return "left" if left_score >= right_score else "right"

    def _side_score(self, snapshot: dict, side: str) -> float:
        if side == "left":
            lidar_values = [snapshot["left_m"], snapshot["front_left_m"]]
            ultrasonic_cm = self._cm_value(snapshot["ultrasonic"].get("left_cm"))
        else:
            lidar_values = [snapshot["right_m"], snapshot["front_right_m"]]
            ultrasonic_cm = self._cm_value(snapshot["ultrasonic"].get("right_cm"))
        lidar_score = min([value for value in lidar_values if value > 0.0], default=2.0)
        ultrasonic_score = ultrasonic_cm / 100.0 if ultrasonic_cm > 0.0 else 2.0
        return min(lidar_score, ultrasonic_score)

    def _sector_min(self, start: float, end: float) -> float:
        points = self.lidar.snapshot()
        distances = [
            distance
            for angle, distance, confidence in points
            if confidence > 0 and self.lidar._angle_in_sector(angle, start, end)
        ]
        return min(distances) if distances else -1.0

    def _cm_value(self, value) -> float:
        try:
            return float(value)
        except Exception:
            return -1.0

    def _update_pose(self, now: float) -> None:
        if self.last_pose_update_at <= 0.0:
            self.last_pose_update_at = now
            return
        dt = max(0.0, min(now - self.last_pose_update_at, 0.5))
        self.last_pose_update_at = now
        if dt <= 0.0:
            return
        action = self.last_drive_action
        speed_ratio = max(self.last_drive_speed, 0) / max(float(self.NORMAL_SPEED), 1.0)
        if action == "forward":
            base_speed = self.CAUTION_MPS_AT_CAUTION if self.last_drive_speed <= self.CAUTION_SPEED else self.FORWARD_MPS_AT_NORMAL
            distance = base_speed * max(speed_ratio, 0.45) * dt
            heading_rad = math.radians(self.heading_deg)
            self.pose_x += math.sin(heading_rad) * distance
            self.pose_y += math.cos(heading_rad) * distance
        elif action == "left":
            self.heading_deg = self._normalize_angle(
                self.heading_deg - self.STEER_DEG_PER_S_AT_TURN * max(speed_ratio, 0.5) * dt
            )
        elif action == "right":
            self.heading_deg = self._normalize_angle(
                self.heading_deg + self.STEER_DEG_PER_S_AT_TURN * max(speed_ratio, 0.5) * dt
            )

    def _distance_to_goal(self, goal: tuple[float, float]) -> float:
        dx = goal[0] - self.pose_x
        dy = goal[1] - self.pose_y
        return math.sqrt(dx * dx + dy * dy)

    def _normalize_angle(self, angle: float) -> float:
        while angle > 180.0:
            angle -= 360.0
        while angle < -180.0:
            angle += 360.0
        return angle

    def _decision_debug(self, snapshot: dict, action: str, state: str, speed: int) -> dict:
        detection = snapshot.get("detection")
        return {
            "state": state,
            "action": action,
            "speed": speed,
            "distance_to_goal_m": round(float(snapshot.get("distance_to_goal_m", -1.0)), 2),
            "goal_angle_deg": round(float(snapshot.get("goal_angle", 0.0)), 1),
            "front_m": round(float(snapshot.get("front_m", -1.0)), 2),
            "front_cm": round(self._cm_value(snapshot.get("ultrasonic", {}).get("front_cm")), 1),
            "object": detection.get("label") if isinstance(detection, dict) else None,
        }

    def _json_fragment(self, payload: dict) -> str:
        return json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bluetooth camera/control server for Raspberry Pi.")
    parser.add_argument("--arduino-port", default=None, help="Arduino serial port. Auto-detected if omitted.")
    parser.add_argument("--arduino-baudrate", type=int, default=115200)
    parser.add_argument("--no-arduino", action="store_true", help="Run without Arduino motor bridge.")
    parser.add_argument("--camera-index", type=int, default=0, help="OpenCV fallback camera index.")
    parser.add_argument("--jpeg-quality", type=int, default=80, help="JPEG quality, 1..100.")
    parser.add_argument("--no-camera", action="store_true", help="Start Bluetooth/control server without opening a camera.")
    parser.add_argument("--service-name", default="RobotPiCamera", help="Bluetooth service name.")
    parser.add_argument("--rfcomm-channel", type=int, default=1, help="Bluetooth RFCOMM channel.")
    parser.add_argument("--lidar-port", default=None, help="Future LiDAR serial port, for perception status only.")
    parser.add_argument("--lidar-baudrate", type=int, default=230400, help="LD19 UART baud rate.")
    parser.add_argument("--object-model", default=None, help="Optional YOLOv8 ONNX model for continuous camera object detection.")
    parser.add_argument("--object-interval", type=float, default=0.5, help="Seconds between object detection frames.")
    parser.add_argument("--object-conf", type=float, default=0.35, help="Object detection confidence threshold.")
    parser.add_argument("--admin-token", default="apptest", help="Token required for KERNEL_EXEC Bluetooth admin shell commands.")
    return parser.parse_args()


def find_serial_port(exclude: str | None = None) -> str | None:
    candidates: list[str] = []
    for pattern in ("/dev/ttyACM*", "/dev/ttyUSB*"):
        candidates.extend(sorted(glob(pattern)))
    if exclude:
        exclude_real = os.path.realpath(exclude)
        candidates = [
            candidate
            for candidate in candidates
            if candidate != exclude and os.path.realpath(candidate) != exclude_real
        ]
    return candidates[0] if candidates else None


class ArduinoBridge:
    def __init__(self, port: str | None, baudrate: int, exclude_port: str | None = None, disabled: bool = False):
        self.disabled = disabled
        self.port = None if disabled else (port or find_serial_port(exclude=exclude_port))
        self.baudrate = baudrate
        self.serial = None
        self.io_lock = threading.Lock()

    def start(self) -> None:
        if self.disabled:
            logging.info("Arduino bridge disabled by --no-arduino")
            return
        if not self.port:
            logging.warning("Arduino serial port not found; control commands will be ignored")
            return
        try:
            import serial  # type: ignore

            self.serial = serial.Serial(self.port, self.baudrate, timeout=1.0, write_timeout=1.0)
            time.sleep(2.0)
            self._drain_input()
            logging.info("Arduino connected on %s at %s baud", self.port, self.baudrate)
        except Exception as exc:
            logging.warning("Arduino unavailable on %s: %s", self.port, exc)
            self.serial = None

    def _drain_input(self) -> None:
        if self.serial is None:
            return
        deadline = time.monotonic() + 0.3
        while time.monotonic() < deadline:
            waiting = getattr(self.serial, "in_waiting", 0)
            if not waiting:
                time.sleep(0.02)
                continue
            line = self.serial.readline()
            if line:
                text = line.decode("utf-8", errors="replace").strip()
                if self._looks_like_arduino_response(text):
                    logging.info("Arduino stale line: %s", text)
                else:
                    logging.info("Arduino stale binary ignored: bytes=%s", len(line))

    def _read_response_line(self, timeout_s: float = 2.0) -> str | None:
        if self.serial is None:
            return None
        deadline = time.monotonic() + timeout_s
        data = bytearray()
        while time.monotonic() < deadline:
            chunk = self.serial.read(1)
            if not chunk:
                continue
            if chunk in (b"\n", b"\r"):
                if data:
                    text = data.decode("utf-8", errors="replace").strip()
                    if self._looks_like_arduino_response(text):
                        return text
                    logging.warning(
                        "Ignoring invalid Arduino response line: bytes=%s hex=%s text=%r",
                        len(data),
                        bytes(data[:32]).hex(),
                        text[:80],
                    )
                    data.clear()
                continue
            data.extend(chunk)
            if len(data) > 512:
                text = data.decode("utf-8", errors="replace").strip()
                logging.warning(
                    "Ignoring oversized invalid Arduino response: bytes=%s hex=%s text=%r",
                    len(data),
                    bytes(data[:32]).hex(),
                    text[:80],
                )
                data.clear()
        if data:
            text = data.decode("utf-8", errors="replace").strip()
            if self._looks_like_arduino_response(text):
                return text
            logging.warning(
                "Ignoring trailing invalid Arduino response: bytes=%s hex=%s text=%r",
                len(data),
                bytes(data[:32]).hex(),
                text[:80],
            )
        return None

    def _looks_like_arduino_response(self, text: str) -> bool:
        if not text:
            return False
        if text.startswith("{") and text.endswith("}"):
            return True
        if text.startswith("OK ") or text.startswith("ERR "):
            return True
        return False

    def send(self, command: str, timeout_s: float = 2.0) -> str | None:
        with self.io_lock:
            if self.serial is None:
                return None
            self._drain_input()
            self.serial.write((command + "\n").encode("ascii"))
            self.serial.flush()
            response = self._read_response_line(timeout_s=timeout_s)
            logging.info("Arduino response for %s: %s", command, response or "NO_VALID_RESPONSE")
            return response

    def send_no_wait(self, command: str) -> bool:
        with self.io_lock:
            if self.serial is None:
                return False
            try:
                self._drain_input()
                self.serial.write((command + "\n").encode("ascii"))
                self.serial.flush()
                return True
            except Exception as exc:
                logging.warning("Arduino write failed for %s: %s", command, exc)
                return False

    def stop(self) -> None:
        try:
            self.send("S")
        except Exception:
            pass
        if self.serial is not None:
            self.serial.close()
            self.serial = None


class Camera:
    def __init__(self, camera_index: int, jpeg_quality: int):
        self.camera_index = camera_index
        self.jpeg_quality = max(1, min(100, jpeg_quality))
        self.picamera = None
        self.cv2 = None
        self.capture = None
        self.lock = threading.Lock()

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
        with self.lock:
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

    def capture_frame_bgr(self):
        with self.lock:
            if self.picamera is not None:
                frame = self.picamera.capture_array()
                import cv2  # type: ignore

                return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

            if self.capture is None:
                raise RuntimeError("Camera is not started")

            ok, frame = self.capture.read()
            if not ok or frame is None:
                raise RuntimeError("OpenCV camera frame read failed")
            return frame

    def stop(self) -> None:
        if self.picamera is not None:
            self.picamera.stop()
            self.picamera.close()
            self.picamera = None
        if self.capture is not None:
            self.capture.release()
            self.capture = None


class ObjectDetector:
    def __init__(self, camera: Camera | None, model_path: str | None, interval_s: float, conf: float):
        self.camera = camera
        self.model_path = model_path
        self.interval_s = max(0.1, interval_s)
        self.conf = conf
        self.thread: threading.Thread | None = None
        self.running = False
        self.ready = False
        self.lock = threading.Lock()
        self.detections: list[dict] = []
        self.error: str | None = None

    def start(self) -> None:
        if self.camera is None or not self.model_path:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, name="ObjectDetector", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.running = False
        if self.thread is not None:
            self.thread.join(timeout=1.0)
            self.thread = None

    def latest_detections(self) -> list[dict]:
        with self.lock:
            return list(self.detections)

    def latest_json(self) -> str:
        detections = self.latest_detections()
        error = f',"error":"{self.error}"' if self.error else ""
        return (
            '{"command":"object_detect",'
            f'"ok":{str(self.ready).lower()},'
            f'"detections":{self._detections_json(detections)}'
            f'{error}}}'
        )

    def _loop(self) -> None:
        try:
            from object_detect_onnx import detect  # type: ignore
            import cv2  # type: ignore

            net = cv2.dnn.readNetFromONNX(self.model_path)
            self.ready = True
            logging.info("Object detector started with %s", self.model_path)
            while self.running:
                try:
                    assert self.camera is not None
                    frame = self.camera.capture_frame_bgr()
                    detections = detect(net, frame, 640, self.conf, 0.45)
                    with self.lock:
                        self.detections = detections
                        self.error = None
                except Exception as exc:
                    self.error = str(exc)
                    logging.warning("Object detection frame failed: %s", exc)
                time.sleep(self.interval_s)
        except Exception as exc:
            self.ready = False
            self.error = str(exc)
            logging.warning("Object detector unavailable: %s", exc)

    def _detections_json(self, detections: list[dict]) -> str:
        import json

        return json.dumps(detections, ensure_ascii=False, separators=(",", ":"))


class KernelManager:
    """Small whitelist of privileged Pi maintenance actions over Bluetooth."""

    SERVICES = [
        "robot-camera.service",
        "robot-bluetooth-agent.service",
        "robot.service",
    ]

    def __init__(self, arduino: "ArduinoBridge", admin_token: str):
        self.arduino = arduino
        self.admin_token = admin_token

    def handle(self, command: str) -> str:
        if command == "KERNEL_STATUS":
            return self.status_json()
        if command == "KERNEL_CLEAN_SERVICES":
            return self.clean_services_json()
        if command == "KERNEL_DISABLE_OLD_AUTOSTART":
            return self.disable_old_autostart_json()
        if command == "KERNEL_INSTALL_AUTOSTART":
            return self.install_autostart_json()
        if command == "KERNEL_RESTART_BLUETOOTH":
            return self.restart_bluetooth_json()
        if command == "KERNEL_SAFE_STOP":
            self.arduino.send("S")
            return '{"command":"kernel_safe_stop","ok":true}'
        if command.startswith("KERNEL_EXEC "):
            return self.exec_shell_json(command)
        return '{"command":"kernel","ok":false,"error":"unknown_kernel_command"}'

    def exec_shell_json(self, command: str) -> str:
        parts = command.split(" ", 2)
        if len(parts) != 3:
            return '{"command":"kernel_exec","ok":false,"error":"bad_request"}'
        try:
            token = base64.b64decode(parts[1]).decode("utf-8")
            shell_command = base64.b64decode(parts[2]).decode("utf-8")
        except Exception as exc:
            return self._json({"command": "kernel_exec", "ok": False, "error": f"decode_failed:{exc}"})
        if token != self.admin_token:
            return '{"command":"kernel_exec","ok":false,"error":"bad_token"}'
        if not shell_command.strip():
            return '{"command":"kernel_exec","ok":false,"error":"empty_command"}'
        result = self._run_shell(shell_command)
        return self._json({"command": "kernel_exec", "ok": result["returncode"] == 0, "cmd": shell_command, "result": result})

    def status_json(self) -> str:
        root = os.geteuid() == 0
        payload = {
            "command": "kernel_status",
            "ok": True,
            "root": root,
            "uname": self._run(["uname", "-a"]),
            "user": self._run(["id"]),
            "uptime": self._run(["uptime", "-p"]),
            "bluetooth": self._run(["systemctl", "is-active", "bluetooth"]),
            "disk": self._run(["df", "-h", "/"]),
            "ports": self._run(["bash", "-lc", "ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null"]),
        }
        return self._json(payload)

    def clean_services_json(self) -> str:
        self.arduino.send("S")
        results = {}
        for service in self.SERVICES:
            results[service] = self._run(["systemctl", "stop", service])
        results["rfkill"] = self._run(["rfkill", "unblock", "bluetooth"])
        results["sdp"] = self._run(["chmod", "777", "/run/sdp"])
        return self._json({"command": "kernel_clean_services", "ok": True, "results": results})

    def disable_old_autostart_json(self) -> str:
        self.arduino.send("S")
        services = [
            "robot-bluetooth-agent.service",
            "robot.service",
            "embabot.service",
            "emba.service",
        ]
        results = {}
        for service in services:
            results[f"stop:{service}"] = self._run(["systemctl", "stop", service])
            results[f"disable:{service}"] = self._run(["systemctl", "disable", service])
        return self._json({"command": "kernel_disable_old_autostart", "ok": True, "results": results})

    def install_autostart_json(self) -> str:
        self.arduino.send("S")
        base_dir = Path(__file__).resolve().parents[1]
        start_script = base_dir / "camera" / "start_robot_camera.sh"
        unit = f"""[Unit]
Description=EMBA robot Bluetooth LiDAR camera server
After=bluetooth.service
Requires=bluetooth.service

[Service]
Type=simple
WorkingDirectory={base_dir}
ExecStartPre=-/bin/sh -c 'command -v rfkill >/dev/null 2>&1 && rfkill unblock bluetooth || true'
ExecStartPre=-/bin/chmod 777 /run/sdp
Environment=ADMIN_TOKEN={self.admin_token}
Environment=ROBOT_ENABLE_CAMERA=1
ExecStart=/bin/bash {start_script}
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
"""
        unit_path = Path("/etc/systemd/system/robot-camera.service")
        results = {}
        try:
            unit_path.write_text(unit, encoding="utf-8")
            results["write_unit"] = {"returncode": 0, "stdout": str(unit_path), "stderr": ""}
        except Exception as exc:
            return self._json(
                {
                    "command": "kernel_install_autostart",
                    "ok": False,
                    "error": str(exc),
                    "root": os.geteuid() == 0,
                }
            )
        results["daemon_reload"] = self._run(["systemctl", "daemon-reload"])
        results["enable"] = self._run(["systemctl", "enable", "robot-camera.service"])
        results["restart"] = self._run(["systemctl", "restart", "robot-camera.service"])
        return self._json({"command": "kernel_install_autostart", "ok": True, "unit": str(unit_path), "results": results})

    def restart_bluetooth_json(self) -> str:
        self.arduino.send("S")
        threading.Thread(target=self._delayed_bluetooth_restart, name="BluetoothRestart", daemon=True).start()
        return (
            '{"command":"kernel_restart_bluetooth","ok":true,'
            '"message":"bluetooth_restart_scheduled_connection_will_drop"}'
        )

    def _delayed_bluetooth_restart(self) -> None:
        time.sleep(0.8)
        self._run(["systemctl", "restart", "bluetooth"])
        self._run(["chmod", "777", "/run/sdp"])

    def _run(self, args: list[str]) -> dict:
        try:
            completed = subprocess.run(args, capture_output=True, text=True, timeout=4)
            return {
                "returncode": completed.returncode,
                "stdout": completed.stdout.strip()[-800:],
                "stderr": completed.stderr.strip()[-800:],
            }
        except Exception as exc:
            return {"returncode": -1, "stdout": "", "stderr": str(exc)}

    def _run_shell(self, command: str) -> dict:
        try:
            completed = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=12)
            return {
                "returncode": completed.returncode,
                "stdout": completed.stdout.strip()[-3000:],
                "stderr": completed.stderr.strip()[-3000:],
            }
        except Exception as exc:
            return {"returncode": -1, "stdout": "", "stderr": str(exc)}

    def _json(self, payload: dict) -> str:
        import json

        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def read_line(sock) -> str:
    data = bytearray()
    while True:
        chunk = sock.recv(1)
        if not chunk:
            raise ConnectionError("Bluetooth client disconnected")
        if chunk in (b"\n", b"\r"):
            if data:
                return data.decode("utf-8", errors="replace").strip()
            continue
        data.extend(chunk)
        if len(data) > 4096:
            raise ValueError("Command line too long")


def send_all(sock, payload: bytes) -> None:
    data = bytes(payload)
    offset = 0
    while offset < len(data):
        sent = sock.send(data[offset:])
        if sent <= 0:
            raise ConnectionError("Bluetooth send failed")
        offset += sent


def safe_arduino_send(arduino: "ArduinoBridge", command: str, timeout_s: float) -> str:
    try:
        response = arduino.send(command, timeout_s=timeout_s)
    except Exception as exc:
        logging.exception("Arduino command failed without closing Bluetooth: %s", command)
        return f"ERR arduino_exception {command} {type(exc).__name__}: {exc}"
    return response or f"ERR arduino_no_ack {command}"


def run_server(args: argparse.Namespace) -> None:
    import bluetooth  # type: ignore

    arduino = ArduinoBridge(
        args.arduino_port,
        args.arduino_baudrate,
        exclude_port=args.lidar_port,
        disabled=args.no_arduino,
    )
    arduino.start()
    lidar = LD19Reader(args.lidar_port, args.lidar_baudrate)
    lidar.start()

    server_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
    server_sock.bind(("", args.rfcomm_channel))
    server_sock.listen(1)
    port = server_sock.getsockname()[1]

    try:
        bluetooth.advertise_service(
            server_sock,
            args.service_name,
            service_id=SPP_UUID,
            service_classes=[SPP_UUID, bluetooth.SERIAL_PORT_CLASS],
            profiles=[bluetooth.SERIAL_PORT_PROFILE],
        )
    except Exception as exc:
        logging.warning("Bluetooth SDP advertise failed; continuing on fixed RFCOMM channel %s: %s", port, exc)

    logging.info("Bluetooth service '%s' listening on RFCOMM channel %s", args.service_name, port)

    camera = None
    if args.no_camera:
        logging.warning("Camera disabled by --no-camera; PHOTO will return an error")
    else:
        camera = Camera(args.camera_index, args.jpeg_quality)
        try:
            camera.start()
        except Exception as exc:
            logging.warning("Camera unavailable; PHOTO will return an error: %s", exc)
            camera = None

    detector = ObjectDetector(camera, args.object_model, args.object_interval, args.object_conf)
    detector.start()
    perception = PerceptionStatus(camera, lidar, detector)
    navigation = NavigationManager(arduino, lidar, detector)
    kernel = KernelManager(arduino, args.admin_token)

    try:
        while True:
            client_sock = None
            try:
                logging.info("Waiting for phone connection...")
                client_sock, client_info = server_sock.accept()
                logging.info("Accepted connection from %s", client_info)

                while True:
                    raw_command = read_line(client_sock)
                    command = raw_command.upper()
                    logging.info("Command: %s", command)
                    manual_motor_command = command in {"F", "B", "L", "R", "S"} or command.startswith("SPD ")
                    if manual_motor_command or command in {
                        "AUTO_ON",
                        "AUTO_OFF",
                        "MOTOR_TEST",
                        "LEFTF",
                        "LEFTB",
                        "RIGHTF",
                        "RIGHTB",
                    }:
                        navigation.cancel_for_manual()

                    if command in {
                        "F",
                        "B",
                        "L",
                        "R",
                        "S",
                        "ENC",
                        "US",
                        "DIST",
                        "ULTRA",
                        "PING",
                        "MOTOR_STATUS",
                        "MOTOR_TEST",
                        "LEFTF",
                        "LEFTB",
                        "RIGHTF",
                        "RIGHTB",
                        "AUTO_ON",
                        "AUTO_OFF",
                        "AUTO_STATUS",
                    } or command.startswith("SPD "):
                        if manual_motor_command:
                            timeout_s = 2.2 if command in {"B", "L", "R"} else 0.8
                            response = safe_arduino_send(arduino, command, timeout_s=timeout_s)
                        else:
                            timeout_s = 3.0 if command == "MOTOR_TEST" else 2.0
                            response = safe_arduino_send(arduino, command, timeout_s=timeout_s)
                        send_all(client_sock, f"{response}\n".encode("utf-8"))
                    elif command == "PHOTO":
                        if camera is None:
                            send_all(client_sock, b"ERR camera_unavailable\n")
                        else:
                            jpeg = camera.capture_jpeg()
                            send_all(client_sock, f"JPEG {len(jpeg)}\n".encode("ascii"))
                            send_all(client_sock, jpeg)
                    elif command == "PERCEPTION_STATUS":
                        send_all(client_sock, f"{perception.to_json_line()}\n".encode("utf-8"))
                    elif command == "OBJECT_DETECT":
                        send_all(client_sock, f"{detector.latest_json()}\n".encode("utf-8"))
                    elif command.startswith("KERNEL_"):
                        send_all(client_sock, f"{kernel.handle(raw_command)}\n".encode("utf-8"))
                    elif command == "MAP_STATUS":
                        send_all(client_sock, f"{navigation.status_json()}\n".encode("utf-8"))
                    elif command == "MAP_SCAN":
                        send_all(client_sock, f"{navigation.scan_json()}\n".encode("utf-8"))
                    elif command == "NAV_STOP":
                        send_all(client_sock, f"{navigation.stop_navigation()}\n".encode("utf-8"))
                    elif command.startswith("NAV_START "):
                        parts = command.split()
                        if len(parts) != 3:
                            send_all(client_sock, b'{"command":"nav_start","ok":false,"error":"bad_goal"}\n')
                        else:
                            try:
                                x = float(parts[1])
                                y = float(parts[2])
                                send_all(client_sock, f"{navigation.start_navigation(x, y)}\n".encode("utf-8"))
                            except ValueError:
                                send_all(client_sock, b'{"command":"nav_start","ok":false,"error":"bad_goal"}\n')
                    else:
                        navigation.cancel_for_manual()
                        arduino.send_no_wait("S")
                        send_all(client_sock, b"ERR unknown_command\n")
            except Exception as exc:
                logging.warning("Client session ended: %s", exc)
                navigation.cancel_for_manual()
                arduino.send_no_wait("S")
            finally:
                if client_sock is not None:
                    client_sock.close()
    finally:
        arduino.stop()
        detector.stop()
        lidar.stop()
        if camera is not None:
            camera.stop()
        server_sock.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_server(parse_args())


if __name__ == "__main__":
    main()
