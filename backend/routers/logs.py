"""
Log management endpoints for the robot control system.
"""
from fastapi import APIRouter, Query, HTTPException, status
from typing import Optional
from datetime import datetime, timedelta

from ..schemas.log_schemas import LogEntry, PaginatedLogs

router = APIRouter(prefix="/logs", tags=["logs"])


# In-memory log storage (replace with database in production)
class LogStorage:
    def __init__(self):
        self._logs: list[LogEntry] = []
        self._counter = 0
    
    def add_log(self, event_type: str, message: str, position: Optional[dict] = None, data: Optional[dict] = None):
        """Add a new log entry."""
        self._counter += 1
        log = LogEntry(
            id=self._counter,
            timestamp=datetime.utcnow(),
            event_type=event_type,
            message=message,
            position=position,
            data=data
        )
        self._logs.append(log)
        return log
    
    def get_logs(self, page: int = 1, page_size: int = 20, 
                 event_type: Optional[str] = None, 
                 start_time: Optional[datetime] = None,
                 end_time: Optional[datetime] = None):
        """Get paginated logs with optional filters."""
        filtered_logs = self._logs
        
        # Apply filters
        if event_type:
            filtered_logs = [log for log in filtered_logs if log.event_type == event_type]
        
        if start_time:
            filtered_logs = [log for log in filtered_logs if log.timestamp >= start_time]
        
        if end_time:
            filtered_logs = [log for log in filtered_logs if log.timestamp <= end_time]
        
        # Sort by timestamp descending
        filtered_logs = sorted(filtered_logs, key=lambda x: x.timestamp, reverse=True)
        
        # Pagination
        total = len(filtered_logs)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_logs = filtered_logs[start_idx:end_idx]
        
        return {
            "logs": paginated_logs,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
    
    def clear_logs(self):
        """Clear all logs."""
        self._logs.clear()
        self._counter = 0


log_storage = LogStorage()


@router.get("/")
async def get_logs(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Number of logs per page"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)")
):
    """Return paginated driving logs."""
    try:
        start_dt = datetime.fromisoformat(start_time) if start_time else None
        end_dt = datetime.fromisoformat(end_time) if end_time else None
        
        result = log_storage.get_logs(
            page=page,
            page_size=page_size,
            event_type=event_type,
            start_time=start_dt,
            end_time=end_dt
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/")
async def add_log(
    event_type: str,
    message: str,
    position: Optional[dict] = None,
    data: Optional[dict] = None
):
    """Add a new log entry."""
    log = log_storage.add_log(event_type, message, position, data)
    return log


@router.delete("/")
async def clear_logs():
    """Clear all logs."""
    log_storage.clear_logs()
    return {"success": True, "message": "All logs cleared"}