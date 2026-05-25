"""Tests for the obstacle avoidance navigator."""
from __future__ import annotations

from hardware.autonomy import AutonomyConfig, AutonomyState, ObstacleAvoidanceNavigator
from hardware.lidar_ld19 import LidarPoint


def test_waits_when_lidar_is_missing():
    navigator = ObstacleAvoidanceNavigator(AutonomyConfig())

    decision = navigator.decide([], [], motor_available=True, now=1.0)

    assert decision.left == 0.0
    assert decision.right == 0.0
    assert decision.state == AutonomyState.SENSOR_WAIT
    assert decision.reason == "waiting_for_lidar"


def test_stops_then_turns_toward_clearer_left_side():
    navigator = ObstacleAvoidanceNavigator(
        AutonomyConfig(stop_duration_s=0.2, turn_duration_s=0.5, stop_distance_m=0.55)
    )
    points = [
        LidarPoint(angle=0.0, distance=0.4, confidence=200),
        LidarPoint(angle=45.0, distance=2.0, confidence=200),
        LidarPoint(angle=315.0, distance=0.8, confidence=200),
    ]

    stopped = navigator.decide(points, [], motor_available=True, now=1.0)
    turning = navigator.decide(points, [], motor_available=True, now=1.3)

    assert stopped.state == AutonomyState.OBSTACLE_STOP
    assert stopped.left == 0.0
    assert stopped.right == 0.0
    assert turning.state == AutonomyState.TURN_LEFT
    assert turning.left == 0.0
    assert turning.right > 0.0


def test_cruises_more_slowly_inside_caution_zone():
    navigator = ObstacleAvoidanceNavigator(
        AutonomyConfig(cruise_speed=0.3, stop_distance_m=0.5, caution_distance_m=1.0)
    )
    points = [LidarPoint(angle=0.0, distance=0.75, confidence=200)]

    decision = navigator.decide(points, [], motor_available=True, now=1.0)

    assert decision.state == AutonomyState.CRUISE
    assert 0.0 < decision.left < 0.3
    assert decision.left == decision.right
