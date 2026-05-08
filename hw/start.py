"""Start Raspberry Pi robot hardware runtime."""
from __future__ import annotations

import argparse
import logging

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
    parser.add_argument(
        "--lidar-max-range",
        type=float,
        default=LD19_MAX_RANGE_M,
        help="LiDAR object localization range in meters.",
    )
    parser.add_argument("--show", action="store_true", help="Show annotated camera window.")
    parser.add_argument("--no-camera", action="store_true", help="Run without camera.")
    parser.add_argument("--no-lidar", action="store_true", help="Run without LiDAR.")
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
        show_window=args.show,
        disable_camera=args.no_camera,
        disable_lidar=args.no_lidar,
        status_interval=args.status_interval,
        lidar_max_range_m=args.lidar_max_range,
    )
    RobotRuntime(config).run()


if __name__ == "__main__":
    main()
