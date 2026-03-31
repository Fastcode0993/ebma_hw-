"""
Abstract ROS2 Bridge Interface for robot control system.

This module defines the abstract interface for ROS2 integration.
Implementations should handle:
- LiDAR data subscription and publishing
- Motor control commands
- Sensor data (IMU, ultrasonic, load cell)
- Status broadcasting
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
import asyncio


class ROS2BridgeInterface(ABC):
    """
    Abstract base class for ROS2 bridge implementation.
    
    This interface defines the contract for ROS2 communication without
    importing ROS2 dependencies in the main application.
    """
    
    def __init__(self):
        """Initialize the ROS2 bridge."""
        self._initialized = False
        self._callbacks: Dict[str, List[Callable]] = {}
    
    @abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize ROS2 connection.
        
        Returns:
            bool: True if initialization successful
        """
        pass
    
    @abstractmethod
    async def shutdown(self):
        """Shutdown ROS2 connection and cleanup resources."""
        pass
    
    @abstractmethod
    async def subscribe_lidar(self, callback: Callable[[Dict[str, Any]], None]):
        """
        Subscribe to LiDAR scan data.
        
        Args:
            callback: Function to call when new LiDAR data is received
                     Expected format: {"points": [{"angle": float, "distance": float}, ...]}
        """
        pass
    
    @abstractmethod
    async def publish_lidar_scan(self, points: List[Dict[str, float]]):
        """
        Publish LiDAR scan data.
        
        Args:
            points: List of LiDAR points with angle and distance
        """
        pass
    
    @abstractmethod
    async def subscribe_imu(self, callback: Callable[[Dict[str, Any]], None]):
        """
        Subscribe to IMU data (MPU-9250).
        
        Args:
            callback: Function to call when new IMU data is received
                     Expected format: {"acceleration": {...}, "gyroscope": {...}, "orientation": {...}}
        """
        pass
    
    @abstractmethod
    async def publish_imu_data(self, data: Dict[str, Any]):
        """
        Publish IMU data.
        
        Args:
            data: IMU sensor data dictionary
        """
        pass
    
    @abstractmethod
    async def subscribe_ultrasonic(self, callback: Callable[[Dict[str, Any]], None]):
        """
        Subscribe to ultrasonic sensor data (HC-SR04).
        
        Args:
            callback: Function to call when new ultrasonic data is received
                     Expected format: {"sensor_id": str, "distance": float, "valid": bool}
        """
        pass
    
    @abstractmethod
    async def publish_ultrasonic_data(self, data: Dict[str, Any]):
        """
        Publish ultrasonic sensor data.
        
        Args:
            data: Ultrasonic sensor data dictionary
        """
        pass
    
    @abstractmethod
    async def subscribe_battery(self, callback: Callable[[Dict[str, Any]], None]):
        """
        Subscribe to battery voltage readings.
        
        Args:
            callback: Function to call when new battery data is received
                     Expected format: {"voltage": float, "current": float, "percentage": float}
        """
        pass
    
    @abstractmethod
    async def publish_battery_status(self, data: Dict[str, float]):
        """
        Publish battery status.
        
        Args:
            data: Battery status dictionary
        """
        pass
    
    @abstractmethod
    async def subscribe_load_cell(self, callback: Callable[[Dict[str, Any]], None]):
        """
        Subscribe to load cell readings (HX711).
        
        Args:
            callback: Function to call when new load cell data is received
                     Expected format: {"sensor_id": str, "weight": float}
        """
        pass
    
    @abstractmethod
    async def publish_load_cell_data(self, data: Dict[str, Any]):
        """
        Publish load cell data.
        
        Args:
            data: Load cell data dictionary
        """
        pass
    
    @abstractmethod
    async def set_motor_speed(self, left_speed: float, right_speed: float):
        """
        Set motor speeds for differential drive.
        
        Args:
            left_speed: Left motor speed (-1.0 to 1.0)
            right_speed: Right motor speed (-1.0 to 1.0)
        """
        pass
    
    @abstractmethod
    async def stop_motors(self):
        """Stop all motors immediately."""
        pass
    
    @abstractmethod
    async def get_robot_position(self) -> Dict[str, float]:
        """
        Get current robot position.
        
        Returns:
            Dict with x, y, heading keys
        """
        pass
    
    @abstractmethod
    async def get_obstacle_distances(self) -> List[Dict[str, Any]]:
        """
        Get distances to detected obstacles.
        
        Returns:
            List of obstacle information dictionaries
        """
        pass
    
    @abstractmethod
    async def calculate_path(self, start: Dict[str, float], goal: Dict[str, float]) -> List[Dict[str, float]]:
        """
        Calculate navigation path using A* or DWA algorithm.
        
        Args:
            start: Starting position {x, y}
            goal: Goal position {x, y}
        
        Returns:
            List of waypoints for the path
        """
        pass
    
    @abstractmethod
    async def get_system_status(self) -> Dict[str, Any]:
        """
        Get comprehensive system status.
        
        Returns:
            Dictionary containing all system status information
        """
        pass
    
    @abstractmethod
    async def test_connection(self) -> bool:
        """
        Test ROS2 connection.
        
        Returns:
            bool: True if connection is healthy
        """
        pass
    
    @abstractmethod
    def get_node_name(self) -> str:
        """
        Get the ROS2 node name.
        
        Returns:
            str: Node name
        """
        pass
    
    @abstractmethod
    def get_node_namespace(self) -> str:
        """
        Get the ROS2 node namespace.
        
        Returns:
            str: Node namespace
        """
        pass
    
    def add_callback(self, topic: str, callback: Callable):
        """
        Register a callback for a topic.
        
        Args:
            topic: Topic name
            callback: Callback function
        """
        if topic not in self._callbacks:
            self._callbacks[topic] = []
        self._callbacks[topic].append(callback)
    
    def remove_callback(self, topic: str, callback: Callable):
        """
        Remove a callback for a topic.
        
        Args:
            topic: Topic name
            callback: Callback function to remove
        """
        if topic in self._callbacks:
            if callback in self._callbacks[topic]:
                self._callbacks[topic].remove(callback)
    
    def clear_callbacks(self, topic: str):
        """
        Clear all callbacks for a topic.
        
        Args:
            topic: Topic name
        """
        if topic in self._callbacks:
            self._callbacks[topic] = []
    
    def is_initialized(self) -> bool:
        """Check if ROS2 bridge is initialized."""
        return self._initialized