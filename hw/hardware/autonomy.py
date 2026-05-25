"""Simple obstacle-aware autonomous driving state machine."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import time
from typing import Iterable, List, Optional, Sequence

from .lidar_ld19 import LidarPoint
from .object_detection import Detection


class AutonomyState(str, Enum):
    """High-level navigation states."""

    DISABLED = "disabled"
    SENSOR_WAIT = "sensor_wait"
    CRUISE = "cruise"
    OBSTACLE_STOP = "obstacle_stop"
    TURN_LEFT = "turn_left"
    TURN_RIGHT = "turn_right"
    BLOCKED = "blocked"


@dataclass
class AutonomyConfig:
    cruise_speed: float = 0.28
    turn_speed: float = 0.32
    stop_distance_m: float = 0.55
    caution_distance_m: float = 0.9
    clear_distance_m: float = 0.75
    front_sector_deg: float = 35.0
    side_sector_deg: float = 65.0
    stop_duration_s: float = 0.35
    turn_duration_s: float = 0.8
    require_lidar: bool = True


@dataclass
class DriveDecision:
    left: float
    right: float
    state: AutonomyState
    obstacle_ahead: bool
    front_distance_m: Optional[float]
    left_clearance_m: Optional[float]
    right_clearance_m: Optional[float]
    reason: str


class ObstacleAvoidanceNavigator:
    """
    Drive forward slowly, stop for obstacles, then pivot around one wheel.

    With the current robot hardware, LD19 LiDAR is the distance authority. Camera
    detections are treated as a visual warning only because they do not provide a
    reliable collision distance.
    """

    def __init__(self, config: AutonomyConfig):
        self.config = config
        self.state = AutonomyState.SENSOR_WAIT
        self._state_started_at = time.monotonic()
        self._turn_until = 0.0

    def decide(
        self,
        lidar_points: Sequence[LidarPoint],
        detections: Sequence[Detection],
        motor_available: bool,
        now: Optional[float] = None,
    ) -> DriveDecision:
        now = time.monotonic() if now is None else now

        front = self._nearest_in_sector(lidar_points, -self.config.front_sector_deg, self.config.front_sector_deg)
        left = self._nearest_in_sector(lidar_points, 15.0, 15.0 + self.config.side_sector_deg)
        right = self._nearest_in_sector(lidar_points, 360.0 - 15.0 - self.config.side_sector_deg, 345.0)
        camera_warning = self._camera_center_warning(detections)

        if not motor_available:
            self._set_state(AutonomyState.DISABLED, now)
            return self._decision(0.0, 0.0, False, front, left, right, "motor_unavailable")

        if self.config.require_lidar and not lidar_points:
            self._set_state(AutonomyState.SENSOR_WAIT, now)
            return self._decision(0.0, 0.0, camera_warning, front, left, right, "waiting_for_lidar")

        obstacle_ahead = front is not None and front <= self.config.stop_distance_m

        if obstacle_ahead and self.state not in {AutonomyState.OBSTACLE_STOP, AutonomyState.TURN_LEFT, AutonomyState.TURN_RIGHT}:
            self._set_state(AutonomyState.OBSTACLE_STOP, now)

        if self.state == AutonomyState.OBSTACLE_STOP:
            if now - self._state_started_at < self.config.stop_duration_s:
                return self._decision(0.0, 0.0, True, front, left, right, "stop_before_avoidance")
            next_state = self._choose_turn_state(left, right)
            self._set_state(next_state, now)
            self._turn_until = now + self.config.turn_duration_s

        if self.state in {AutonomyState.TURN_LEFT, AutonomyState.TURN_RIGHT}:
            if now < self._turn_until:
                if self.state == AutonomyState.TURN_LEFT:
                    return self._decision(0.0, self.config.turn_speed, obstacle_ahead, front, left, right, "turn_left")
                return self._decision(self.config.turn_speed, 0.0, obstacle_ahead, front, left, right, "turn_right")
            if front is not None and front <= self.config.clear_distance_m:
                self._set_state(AutonomyState.BLOCKED, now)
                return self._decision(0.0, 0.0, True, front, left, right, "blocked_after_turn")
            self._set_state(AutonomyState.CRUISE, now)

        if self.state == AutonomyState.BLOCKED:
            if front is None or front > self.config.clear_distance_m:
                self._set_state(AutonomyState.CRUISE, now)
            else:
                return self._decision(0.0, 0.0, True, front, left, right, "blocked")

        if camera_warning and front is None:
            self._set_state(AutonomyState.SENSOR_WAIT, now)
            return self._decision(0.0, 0.0, True, front, left, right, "camera_warning_without_distance")

        self._set_state(AutonomyState.CRUISE, now)
        speed = self._cruise_speed(front)
        return self._decision(speed, speed, bool(camera_warning), front, left, right, "cruise")

    def _decision(
        self,
        left_speed: float,
        right_speed: float,
        obstacle_ahead: bool,
        front_distance: Optional[float],
        left_clearance: Optional[float],
        right_clearance: Optional[float],
        reason: str,
    ) -> DriveDecision:
        return DriveDecision(
            left=left_speed,
            right=right_speed,
            state=self.state,
            obstacle_ahead=obstacle_ahead,
            front_distance_m=front_distance,
            left_clearance_m=left_clearance,
            right_clearance_m=right_clearance,
            reason=reason,
        )

    def _set_state(self, state: AutonomyState, now: float) -> None:
        if self.state != state:
            self.state = state
            self._state_started_at = now

    def _choose_turn_state(self, left_clearance: Optional[float], right_clearance: Optional[float]) -> AutonomyState:
        left_score = left_clearance if left_clearance is not None else math.inf
        right_score = right_clearance if right_clearance is not None else math.inf
        if left_score >= right_score:
            return AutonomyState.TURN_LEFT
        return AutonomyState.TURN_RIGHT

    def _cruise_speed(self, front_distance: Optional[float]) -> float:
        if front_distance is None or front_distance >= self.config.caution_distance_m:
            return self.config.cruise_speed
        span = max(0.01, self.config.caution_distance_m - self.config.stop_distance_m)
        ratio = max(0.35, min(1.0, (front_distance - self.config.stop_distance_m) / span))
        return self.config.cruise_speed * ratio

    def _camera_center_warning(self, detections: Sequence[Detection]) -> bool:
        for item in detections:
            x, _y, w, h = item.box
            center_x = x + w / 2.0
            if item.confidence >= 0.45 and 160 <= center_x <= 480 and h >= 120:
                return True
        return False

    @staticmethod
    def _nearest_in_sector(points: Iterable[LidarPoint], start_deg: float, end_deg: float) -> Optional[float]:
        distances: List[float] = []
        start = start_deg % 360.0
        end = end_deg % 360.0
        for point in points:
            angle = point.angle % 360.0
            if start <= end:
                in_sector = start <= angle <= end
            else:
                in_sector = angle >= start or angle <= end
            if in_sector:
                distances.append(point.distance)
        return min(distances) if distances else None
