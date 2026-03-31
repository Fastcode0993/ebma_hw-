"""
Pydantic v2 schemas for robot control and status data.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


class RobotPosition(BaseModel):
    """Robot position in the navigation space."""
    x: float = Field(..., description="X coordinate in meters")
    y: float = Field(..., description="Y coordinate in meters")
    heading: float = Field(default=0.0, description="Heading angle in degrees")
    
    @field_validator('x', 'y')
    @classmethod
    def validate_bounds(cls, v):
        if v < -10.0 or v > 10.0:
            raise ValueError(f"Coordinate must be between -10 and 10, got {v}")
        return v


class LiDARPoint(BaseModel):
    """Single LiDAR scan point."""
    angle: float = Field(..., description="Angle in degrees from center")
    distance: float = Field(..., description="Distance in meters")
    
    @field_validator('distance')
    @classmethod
    def validate_distance(cls, v):
        if v < 0.3 or v > 12.0:
            raise ValueError(f"Distance must be between 0.3 and 12 meters, got {v}")
        return v


class ObstacleInfo(BaseModel):
    """Obstacle detection information."""
    angle: float = Field(..., description="Angle to obstacle in degrees")
    distance: float = Field(..., description="Distance to obstacle in meters")
    confidence: float = Field(default=1.0, description="Detection confidence 0-1")


class RobotStatus(BaseModel):
    """Current robot status."""
    status: str = Field(..., description="Status: idle, moving, stopped, error")
    battery: float = Field(..., description="Battery voltage in volts")
    speed: float = Field(default=0.0, description="Current speed in m/s")
    position: RobotPosition = Field(..., description="Current robot position")
    obstacles: List[ObstacleInfo] = Field(default_factory=list, description="Detected obstacles")
    lidar_points: List[LiDARPoint] = Field(default_factory=list, description="LiDAR scan points")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Status timestamp")
    
    @field_validator('battery')
    @classmethod
    def validate_battery(cls, v):
        if v < 0 or v > 24:
            raise ValueError(f"Battery voltage must be between 0 and 24V, got {v}")
        return v
    
    @field_validator('speed')
    @classmethod
    def validate_speed(cls, v):
        if v < 0 or v > 0.5:
            raise ValueError(f"Speed must be between 0 and 0.5 m/s, got {v}")
        return v


class NavigationCommand(BaseModel):
    """Navigation command from frontend."""
    cmd: str = Field(..., description="Command type: navigate, stop, emergency_stop")
    target: Optional[RobotPosition] = Field(default=None, description="Target position")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    @field_validator('cmd')
    @classmethod
    def validate_command(cls, v):
        if v not in ['navigate', 'stop', 'emergency_stop']:
            raise ValueError(f"Invalid command: {v}. Must be navigate, stop, or emergency_stop")
        return v


class DestinationRequest(BaseModel):
    """Destination setting request."""
    x: float = Field(..., description="Target X coordinate in meters")
    y: float = Field(..., description="Target Y coordinate in meters")
    
    @field_validator('x', 'y')
    @classmethod
    def validate_bounds(cls, v):
        if v < -10.0 or v > 10.0:
            raise ValueError(f"Coordinate must be between -10 and 10, got {v}")
        return v


class LogEntry(BaseModel):
    """Driving log entry."""
    id: int = Field(..., description="Log entry ID")
    timestamp: datetime = Field(..., description="Log timestamp")
    event_type: str = Field(..., description="Event type: navigation, obstacle_detected, status_change")
    message: str = Field(..., description="Event message")
    position: Optional[RobotPosition] = Field(default=None, description="Position at event")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Additional event data")


class PaginatedLogs(BaseModel):
    """Paginated logs response."""
    logs: List[LogEntry] = Field(..., description="List of log entries")
    total: int = Field(..., description="Total number of logs")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of logs per page")
    total_pages: int = Field(..., description="Total number of pages")