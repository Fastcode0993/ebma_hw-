/**
 * Main Layout Component
 * 
 * Main layout structure with left, center, and right panels
 * Responsive design with mobile breakpoints
 */
import React from 'react';
import { LiDARCanvas } from '../lidar/LidarCanvas';
import { RobotMap } from '../map/RobotMap';
import { ControlPanel } from '../controls/ControlPanel';
import { StatusPanel } from '../status/StatusPanel';
import type { RobotPosition, LiDARPoint, RobotStatus } from '../../types/robot.types';

interface MainLayoutProps {
  lidarPoints: LiDARPoint[];
  robotPosition: RobotPosition;
  robotStatus: RobotStatus;
  destination: { x: number; y: number } | null;
  robotHeading: number;
  onNavigate: (target: { x: number; y: number }) => void;
  onEmergencyStop: () => void;
  onStop: () => void;
  isConnecting: boolean;
  isConnected: boolean;
  errorMessage?: string;
}

export const MainLayout: React.FC<MainLayoutProps> = ({
  lidarPoints,
  robotPosition,
  robotStatus,
  destination,
  robotHeading,
  onNavigate,
  onEmergencyStop,
  onStop,
  isConnecting,
  isConnected,
  errorMessage,
}) => {
  const mapSize = { width: 400, height: 400 };
  const maxRange = 12; // LiDAR range in meters

  return (
    <div className="min-h-screen bg-slate-100 dark:bg-slate-900">
      {/* Header */}
      <header className="bg-white dark:bg-slate-800 shadow-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-slate-800 dark:text-white">
                Walking Assistant Robot
              </h1>
              <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
                Semi-autonomous Indoor Navigation System
              </p>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-right">
                <div className="text-sm font-medium text-slate-800 dark:text-white">
                  Robot Controller
                </div>
                <div className="text-xs text-slate-500 dark:text-slate-400">
                  v1.0.0
                </div>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Panel - LiDAR */}
          <div className="lg:col-span-1">
            <div className="bg-white dark:bg-slate-800 rounded-lg shadow-md p-4">
              <h2 className="text-lg font-semibold text-slate-800 dark:text-white mb-4">
                LiDAR Scan
              </h2>
              <div className="aspect-square bg-slate-900 rounded-lg overflow-hidden">
                <LiDARCanvas
                  lidarPoints={lidarPoints}
                  robotHeading={robotHeading}
                  maxRange={maxRange}
                />
              </div>
            </div>
          </div>

          {/* Center Panel - Map */}
          <div className="lg:col-span-1">
            <div className="bg-white dark:bg-slate-800 rounded-lg shadow-md p-4">
              <h2 className="text-lg font-semibold text-slate-800 dark:text-white mb-4">
                Robot Map
              </h2>
              <div className="aspect-square bg-slate-100 dark:bg-slate-700 rounded-lg overflow-hidden">
                <RobotMap
                  robotPosition={robotPosition}
                  destination={destination ? {
                    x: destination.x,
                    y: destination.y,
                    createdAt: Date.now(),
                  } : null}
                  mapSize={mapSize}
                />
              </div>
            </div>
          </div>

          {/* Right Panel - Status */}
          <div className="lg:col-span-1">
            <StatusPanel status={robotStatus} />
          </div>
        </div>

        {/* Bottom Panel - Controls */}
        <div className="mt-6">
          <ControlPanel
            onNavigate={onNavigate}
            onEmergencyStop={onEmergencyStop}
            onStop={onStop}
            isConnecting={isConnecting}
            isConnected={isConnected}
            errorMessage={errorMessage}
          />
        </div>
      </main>

      {/* Footer */}
      <footer className="bg-white dark:bg-slate-800 mt-auto">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between text-sm text-slate-600 dark:text-slate-400">
            <div>
              <span className="font-medium">Hardware:</span>
              <span className="ml-2">Raspberry Pi 4 + Arduino Mega 2560</span>
            </div>
            <div>
              <span className="font-medium">Sensors:</span>
              <span className="ml-2">LD19 LiDAR, MPU-9250, HX711 ×2</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
};