"""
Robot control WebSocket and REST API endpoints.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from typing import Optional
import asyncio
import json
from datetime import datetime

from ..core.config import settings
from ..schemas.robot_schemas import (
    RobotStatus, NavigationCommand, DestinationRequest, 
    RobotPosition, ObstacleInfo, LiDARPoint
)

router = APIRouter(prefix="/robot", tags=["robot"])


class RobotState:
    """In-memory robot state management."""
    
    def __init__(self):
        self._status: Optional[RobotStatus] = None
        self._destination: Optional[RobotPosition] = None
        self._navigation_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        
        # Initialize with default status
        self._status = RobotStatus(
            status="idle",
            battery=12.0,
            speed=0.0,
            position=RobotPosition(x=0.0, y=0.0, heading=0.0)
        )
    
    async def update_status(self, status: RobotStatus):
        """Update robot status."""
        async with self._lock:
            self._status = status
    
    async def get_status(self) -> RobotStatus:
        """Get current robot status."""
        async with self._lock:
            return self._status.copy() if self._status else RobotStatus(
                status="error", battery=0.0, speed=0.0,
                position=RobotPosition(x=0.0, y=0.0, heading=0.0)
            )
    
    async def set_destination(self, destination: DestinationRequest):
        """Set navigation destination."""
        async with self._lock:
            self._destination = RobotPosition(x=destination.x, y=destination.y, heading=0.0)
            if self._status and self._status.status != "moving":
                self._status.status = "moving"
    
    async def get_destination(self) -> Optional[RobotPosition]:
        """Get current destination."""
        async with self._lock:
            return self._destination.copy() if self._destination else None
    
    async def stop_navigation(self):
        """Stop current navigation."""
        async with self._lock:
            if self._navigation_task:
                self._navigation_task.cancel()
                self._navigation_task = None
            if self._status:
                self._status.status = "stopped"
    
    async def emergency_stop(self):
        """Emergency stop - immediate halt."""
        async with self._lock:
            if self._navigation_task:
                self._navigation_task.cancel()
                self._navigation_task = None
            if self._status:
                self._status.status = "stopped"
                self._status.speed = 0.0


robot_state = RobotState()


@router.websocket("/ws/control")
async def robot_control_ws(websocket: WebSocket):
    """
    WebSocket endpoint for real-time robot control.
    
    - Receive: {"cmd": "navigate", "target": {"x": 2.5, "y": 1.0}}
    - Broadcast: {"battery": 12.4, "obstacle_ahead": false, "status": "moving", "position": {...}}
    """
    await websocket.accept()
    
    # Subscribe to status updates
    status_update_task = asyncio.create_task(_broadcast_status(websocket))
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle commands
            if message.get("cmd") == "navigate" and message.get("target"):
                target = message["target"]
                await robot_state.set_destination(DestinationRequest(
                    x=float(target["x"]),
                    y=float(target["y"])
                ))
                await websocket.send_json({
                    "type": "command_ack",
                    "message": "Navigation command received"
                })
            
            elif message.get("cmd") == "stop":
                await robot_state.stop_navigation()
                await websocket.send_json({
                    "type": "command_ack",
                    "message": "Stop command received"
                })
            
            elif message.get("cmd") == "emergency_stop":
                await robot_state.emergency_stop()
                await websocket.send_json({
                    "type": "emergency_ack",
                    "message": "Emergency stop activated"
                })
            
            # Send heartbeat
            await websocket.send_json({
                "type": "heartbeat",
                "timestamp": datetime.utcnow().isoformat()
            })
            
    except WebSocketDisconnect:
        status_update_task.cancel()
    except Exception as e:
        print(f"WebSocket error: {e}")
        status_update_task.cancel()


async def _broadcast_status(websocket: WebSocket):
    """Broadcast robot status updates to connected clients."""
    while True:
        try:
            status = await robot_state.get_status()
            await websocket.send_json({
                "type": "status",
                "data": {
                    "battery": status.battery,
                    "obstacle_ahead": any(o.distance < settings.OBSTACLE_AVOIDANCE_THRESHOLD for o in status.obstacles),
                    "status": status.status,
                    "position": {
                        "x": status.position.x,
                        "y": status.position.y,
                        "heading": status.position.heading
                    },
                    "speed": status.speed,
                    "obstacles": [
                        {
                            "angle": o.angle,
                            "distance": o.distance,
                            "confidence": o.confidence
                        } for o in status.obstacles
                    ],
                    "lidar_points": [
                        {"angle": p.angle, "distance": p.distance} for p in status.lidar_points
                    ]
                }
            })
            await asyncio.sleep(0.5)  # Update frequency
        except Exception as e:
            print(f"Status broadcast error: {e}")
            await asyncio.sleep(1)


@router.post("/api/destination")
async def set_destination(request: DestinationRequest):
    """Set navigation target (validate x/y bounds)."""
    await robot_state.set_destination(request)
    return {
        "success": True,
        "message": "Destination set",
        "destination": {
            "x": request.x,
            "y": request.y
        }
    }


@router.get("/api/status")
async def get_robot_status():
    """Return current robot state."""
    status = await robot_state.get_status()
    return {
        "status": status.status,
        "battery": status.battery,
        "speed": status.speed,
        "position": {
            "x": status.position.x,
            "y": status.position.y,
            "heading": status.position.heading
        },
        "obstacles": [
            {
                "angle": o.angle,
                "distance": o.distance,
                "confidence": o.confidence
            } for o in status.obstacles
        ],
        "lidar_points": [
            {"angle": p.angle, "distance": p.distance} for p in status.lidar_points
        ],
        "timestamp": status.timestamp.isoformat()
    }


@router.get("/api/logs")
async def get_logs(page: int = 1, page_size: int = 20):
    """Return paginated driving logs."""
    # Placeholder - implement with database
    return {
        "logs": [],
        "total": 0,
        "page": page,
        "page_size": page_size,
        "total_pages": 0
    }


@router.post("/api/emergency_stop")
async def emergency_stop():
    """Immediate halt command."""
    await robot_state.emergency_stop()
    return {
        "success": True,
        "message": "Emergency stop activated"
    }