"""
Log schemas for the robot control system.
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class LogEntry(BaseModel):
    """Driving log entry."""
    id: int = Field(..., description="Log entry ID")
    timestamp: datetime = Field(..., description="Log timestamp")
    event_type: str = Field(..., description="Event type: navigation, obstacle_detected, status_change")
    message: str = Field(..., description="Event message")
    position: Optional[Dict[str, float]] = Field(default=None, description="Position at event")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Additional event data")


class PaginatedLogs(BaseModel):
    """Paginated logs response."""
    logs: list[LogEntry] = Field(..., description="List of log entries")
    total: int = Field(..., description="Total number of logs")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of logs per page")
    total_pages: int = Field(..., description="Total number of pages")