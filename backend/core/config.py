"""
Configuration management for the embedded walking assistant robot backend.
"""
from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Server configuration
    APP_NAME: str = "Walking Assistant Robot Control System"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # WebSocket configuration
    WS_HEARTBEAT_INTERVAL: float = 30.0
    WS_RECONNECT_DELAY: float = 1.0
    WS_MAX_RECONNECT_DELAY: float = 30.0
    
    # Robot navigation bounds (meters)
    NAVIGATION_BOUNDS: dict = {
        "min_x": -10.0,
        "max_x": 10.0,
        "min_y": -10.0,
        "max_y": 10.0
    }
    
    # LiDAR configuration
    LIDAR_SCAN_ANGLE: float = 180.0  # degrees
    LIDAR_MAX_RANGE: float = 12.0  # meters
    LIDAR_MIN_RANGE: float = 0.3  # meters
    
    # Motor control parameters
    MAX_SPEED: float = 0.5  # m/s
    MAX_ACCELERATION: float = 0.1  # m/s^2
    OBSTACLE_AVOIDANCE_THRESHOLD: float = 1.5  # meters
    
    # Database path
    DATABASE_PATH: str = "robot_data.db"
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "robot.log"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()