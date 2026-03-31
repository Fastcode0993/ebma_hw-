/**
 * App Component
 * 
 * Main application component that integrates all sub-components
 * Uses Zustand store for state management
 */
import React, { useEffect, useState } from 'react';
import { useRobotStore } from './store/useRobotStore';
import { useRobotWebSocket } from './hooks/useRobotWebSocket';
import { MainLayout } from './components/layout/MainLayout';
import type { LiDARPoint, RobotPosition, RobotStatus } from './types/robot.types';

export const App: React.FC = () => {
  const {
    status,
    position,
    destination,
    logs,
    isConnecting,
    isConnected,
    setDestination,
    emergencyStop,
    addLog,
    updateStatus,
    updatePosition,
    setConnectionStatus,
    clearDestination,
  } = useRobotStore();

  const {
    socket,
    isConnecting: wsIsConnecting,
    isConnected: wsIsConnected,
    errorMessage,
    sendCommand,
    emergencyStop: wsEmergencyStop,
    navigate: wsNavigate,
    stop: wsStop,
  } = useRobotWebSocket();

  // Sync WebSocket connection status with store
  useEffect(() => {
    setConnectionStatus(wsIsConnected, errorMessage);
  }, [wsIsConnected, errorMessage, setConnectionStatus]);

  // Handle navigation
  const handleNavigate = (target: { x: number; y: number }) => {
    wsNavigate(target);
    addLog({
      type: 'navigation',
      message: `Navigating to (${target.x}, ${target.y})`,
      timestamp: Date.now(),
    });
  };

  // Handle emergency stop
  const handleEmergencyStop = () => {
    wsEmergencyStop();
    emergencyStop();
    addLog({
      type: 'emergency_stop',
      message: 'Emergency stop activated',
      timestamp: Date.now(),
    });
  };

  // Handle stop
  const handleStop = () => {
    wsStop();
    addLog({
      type: 'stop',
      message: 'Robot stopped',
      timestamp: Date.now(),
    });
  };

  // Simulate receiving robot status updates (for demo)
  useEffect(() => {
    if (!isConnected) return;

    const interval = setInterval(() => {
      // Simulate LiDAR points
      const simulatedPoints: LiDARPoint[] = [];
      for (let angle = -45; angle <= 135; angle += 5) {
        const distance = Math.random() * 12;
        simulatedPoints.push({
          angle,
          distance,
          timestamp: Date.now(),
        });
      }

      // Simulate robot position
      const simulatedPosition: RobotPosition = {
        x: (Math.random() - 0.5) * 4,
        y: (Math.random() - 0.5) * 4,
        heading: Math.random() * 360,
        timestamp: Date.now(),
      };

      // Update state
      updateStatus({
        lidarPoints: simulatedPoints,
        obstacleAhead: simulatedPoints.some(p => p.distance < 2),
        speed: Math.random() * 0.5,
      });
      updatePosition(simulatedPosition);

    }, 1000);

    return () => clearInterval(interval);
  }, [isConnected, updateStatus, updatePosition]);

  return (
    <MainLayout
      lidarPoints={status.lidarPoints}
      robotPosition={position}
      robotStatus={status}
      destination={destination}
      robotHeading={position.heading || 0}
      onNavigate={handleNavigate}
      onEmergencyStop={handleEmergencyStop}
      onStop={handleStop}
      isConnecting={isConnecting || wsIsConnecting}
      isConnected={isConnected || wsIsConnected}
      errorMessage={errorMessage}
    />
  );
};