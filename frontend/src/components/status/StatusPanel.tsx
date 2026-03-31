/**
 * Status Panel Component
 * 
 * Displays real-time robot status information
 * Includes battery, speed, obstacle distance, and system status
 */
import React, { memo } from 'react';
import type { RobotStatus } from '../../types/robot.types';

interface StatusPanelProps {
  status: RobotStatus;
}

export const StatusPanel: React.FC<StatusPanelProps> = memo(({ status }) => {
  const batteryPercentage = Math.round(((status.battery - 10.8) / (13.2 - 10.8)) * 100);
  const batteryPercentage = Math.max(0, Math.min(100, batteryPercentage));

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'moving': return 'bg-green-500';
      case 'stopped': return 'bg-amber-500';
      case 'error': return 'bg-red-500';
      default: return 'bg-slate-500';
    }
  };

  const getStatusText = (status: string) => {
    switch (status) {
      case 'moving': return 'Moving';
      case 'stopped': return 'Stopped';
      case 'error': return 'Error';
      default: return 'Idle';
    }
  };

  return (
    <div className="bg-white dark:bg-slate-800 rounded-lg shadow-md p-4" aria-labelledby="status-panel-title">
      <h2 id="status-panel-title" className="text-lg font-semibold text-slate-800 dark:text-white mb-4">
        Status
      </h2>

      {/* Battery Status */}
      <div className="mb-4">
        <div className="flex justify-between items-center mb-1">
          <span className="text-sm font-medium text-slate-700 dark:text-slate-300">Battery</span>
          <span className="text-sm text-slate-600 dark:text-slate-400">
            {status.battery.toFixed(1)}V ({batteryPercentage}%)
          </span>
        </div>
        <div className="w-full bg-slate-200 dark:bg-slate-700 rounded-full h-2">
          <div
            className={`h-2 rounded-full transition-all duration-500 ${
              batteryPercentage > 80 ? 'bg-green-500' :
              batteryPercentage > 30 ? 'bg-yellow-500' : 'bg-red-500'
            }`}
            style={{ width: `${batteryPercentage}%` }}
            role="progressbar"
            aria-valuenow={batteryPercentage}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Battery level"
          />
        </div>
      </div>

      {/* Speed */}
      <div className="mb-4">
        <div className="flex justify-between items-center">
          <span className="text-sm text-slate-600 dark:text-slate-400">Speed</span>
          <span className="text-sm font-medium text-slate-800 dark:text-white">
            {status.speed.toFixed(2)} m/s
          </span>
        </div>
      </div>

      {/* Obstacle Distance */}
      <div className="mb-4">
        <div className="flex justify-between items-center">
          <span className="text-sm text-slate-600 dark:text-slate-400">Nearest Obstacle</span>
          <span className={`text-sm font-medium ${
            status.obstacleAhead ? 'text-red-500' : 'text-slate-800 dark:text-white'
          }`}>
            {status.obstacleAhead ? 'Detected' : 'Clear'}
          </span>
        </div>
        <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          {status.obstacleAhead 
            ? `${(12 - status.battery).toFixed(1)}m ahead` 
            : 'No obstacles in range'}
        </div>
      </div>

      {/* System Status */}
      <div className="mb-4">
        <div className="flex justify-between items-center">
          <span className="text-sm text-slate-600 dark:text-slate-400">Status</span>
          <span className="text-sm font-medium text-slate-800 dark:text-white">
            {getStatusText(status.status)}
          </span>
        </div>
        <div className="mt-1">
          <span className={`inline-block w-2 h-2 rounded-full ${getStatusColor(status.status)}`} />
        </div>
      </div>

      {/* Timestamp */}
      <div className="pt-4 border-t border-slate-200 dark:border-slate-700">
        <span className="text-xs text-slate-500 dark:text-slate-400">
          Updated: {new Date(status.timestamp).toLocaleTimeString()}
        </span>
      </div>
    </div>
  );
});

StatusPanel.displayName = 'StatusPanel';