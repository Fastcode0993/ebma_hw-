"""Start Raspberry Pi robot hardware runtime."""
from __future__ import annotations

import argparse
import logging

from hardware.autonomy import AutonomyConfig
from hardware.runtime import RobotRuntime, RuntimeConfig
from hardware.lidar_objects import LD19_MAX_RANGE_M


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start camera object detection and LD19 LiDAR sensing on Raspberry Pi."
    )
    parser.add_argument("--camera-index", type=int, default=0, help="OpenCV camera index fallback.")
    parser.add_argument("--camera-width", type=int, default=640, help="Camera capture width.")
    parser.add_argument("--camera-height", type=int, default=480, help="Camera capture height.")
    parser.add_argument("--lidar-port", default="/dev/ttyUSB0", help="LD19 serial port.")
    parser.add_argument("--lidar-baudrate", type=int, default=230400, help="LD19 serial baudrate.")
    parser.add_argument("--motor-port", default="/dev/ttyACM0", help="Arduino Mega motor bridge serial port.")
    parser.add_argument("--motor-baudrate", type=int, default=115200, help="Arduino motor bridge baudrate.")
    parser.add_argument(
        "--lidar-max-range",
        type=float,
        default=LD19_MAX_RANGE_M,
        help="LiDAR object localization range in meters.",
    )
    parser.add_argument("--show", action="store_true", help="Show annotated camera window.")
    parser.add_argument("--no-camera", action="store_true", help="Run without camera.")
    parser.add_argument("--no-lidar", action="store_true", help="Run without LiDAR.")
    parser.add_argument("--no-motor", action="store_true", help="Run without Arduino motor control.")
    parser.add_argument("--autonomous", action="store_true", help="Enable obstacle-aware autonomous driving.")
    parser.add_argument("--cruise-speed", type=float, default=0.28, help="Autonomous forward speed, -1.0 to 1.0.")
    parser.add_argument("--turn-speed", type=float, default=0.32, help="Autonomous one-wheel turn speed.")
    parser.add_argument("--stop-distance", type=float, default=0.55, help="Stop if an obstacle is closer than this.")
    parser.add_argument("--caution-distance", type=float, default=0.9, help="Slow down below this front distance.")
    parser.add_argument("--clear-distance", type=float, default=0.75, help="Minimum clear distance after a turn.")
    parser.add_argument("--front-sector", type=float, default=35.0, help="Front LiDAR sector half-width in degrees.")
    parser.add_argument("--stop-duration", type=float, default=0.35, help="Seconds to stay stopped before turning.")
    parser.add_argument("--turn-duration", type=float, default=0.8, help="Seconds to pivot around one wheel.")
    parser.add_argument("--status-interval", type=float, default=1.0, help="Seconds between JSON status logs.")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    args = parse_args()
    config = RuntimeConfig(
        camera_index=args.camera_index,
        camera_width=args.camera_width,
        camera_height=args.camera_height,
        lidar_port=args.lidar_port,
        lidar_baudrate=args.lidar_baudrate,
        motor_port=args.motor_port,
        motor_baudrate=args.motor_baudrate,
        show_window=args.show,
        disable_camera=args.no_camera,
        disable_lidar=args.no_lidar,
        disable_motor=args.no_motor,
        autonomous_enabled=args.autonomous,
        status_interval=args.status_interval,
        lidar_max_range_m=args.lidar_max_range,
        autonomy=AutonomyConfig(
            cruise_speed=args.cruise_speed,
            turn_speed=args.turn_speed,
            stop_distance_m=args.stop_distance,
            caution_distance_m=args.caution_distance,
            clear_distance_m=args.clear_distance,
            front_sector_deg=args.front_sector,
            stop_duration_s=args.stop_duration,
            turn_duration_s=args.turn_duration,
        ),
    )
    RobotRuntime(config).run()


if __name__ == "__main__":
    main()
