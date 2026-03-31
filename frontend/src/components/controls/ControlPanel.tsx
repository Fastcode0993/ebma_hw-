/**
 * Control Panel Component
 * 
 * Provides control buttons and coordinate input form
 * Includes Start/Stop/Emergency Stop controls
 */
import React, { memo, useState } from 'react';
import type { Destination } from '../../types/robot.types';

interface ControlPanelProps {
  onNavigate: (target: { x: number; y: number }) => void;
  onEmergencyStop: () => void;
  onStop: () => void;
  isConnecting: boolean;
  isConnected: boolean;
  errorMessage?: string;
}

export const ControlPanel: React.FC<ControlPanelProps> = memo(({
  onNavigate,
  onEmergencyStop,
  onStop,
  isConnecting,
  isConnected,
  errorMessage,
}) => {
  const [targetX, setTargetX] = useState<string>('');
  const [targetY, setTargetY] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    const x = parseFloat(targetX);
    const y = parseFloat(targetY);

    if (!isNaN(x) && !isNaN(y)) {
      onNavigate({ x, y });
    }

    setIsSubmitting(false);
    setTargetX('');
    setTargetY('');
  };

  const handleEmergencyStop = () => {
    onEmergencyStop();
  };

  const handleStop = () => {
    onStop();
  };

  return (
    <div className="bg-white dark:bg-slate-800 rounded-lg shadow-md p-4" aria-labelledby="control-panel-title">
      <h2 id="control-panel-title" className="text-lg font-semibold text-slate-800 dark:text-white mb-4">
        Control Panel
      </h2>

      {/* Connection Status */}
      <div className="mb-4">
        <div className="flex items-center gap-2">
          <div className={`w-3 h-3 rounded-full ${
            isConnected ? 'bg-green-500' : isConnecting ? 'bg-yellow-500' : 'bg-red-500'
          }`} aria-hidden="true" />
          <span className="text-sm text-slate-600 dark:text-slate-300">
            {isConnected ? 'Connected' : isConnecting ? 'Connecting...' : 'Disconnected'}
          </span>
        </div>
        {errorMessage && (
          <p className="text-sm text-red-500 mt-1" role="alert">
            {errorMessage}
          </p>
        )}
      </div>

      {/* Navigation Form */}
      <form onSubmit={handleSubmit} className="mb-4" aria-label="Destination input form">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="target-x" className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              X Coordinate (m)
            </label>
            <input
              type="number"
              id="target-x"
              step="0.1"
              min="-10"
              max="10"
              value={targetX}
              onChange={(e) => setTargetX(e.target.value)}
              disabled={isSubmitting || !isConnected}
              className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-md 
                       bg-white dark:bg-slate-700 text-slate-900 dark:text-white
                       focus:outline-none focus:ring-2 focus:ring-cyan-500
                       disabled:opacity-50 disabled:cursor-not-allowed"
              placeholder="0.0"
              aria-describedby="target-x-help"
            />
            <p id="target-x-help" className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              Range: -10 to 10m
            </p>
          </div>
          <div>
            <label htmlFor="target-y" className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              Y Coordinate (m)
            </label>
            <input
              type="number"
              id="target-y"
              step="0.1"
              min="-10"
              max="10"
              value={targetY}
              onChange={(e) => setTargetY(e.target.value)}
              disabled={isSubmitting || !isConnected}
              className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-md 
                       bg-white dark:bg-slate-700 text-slate-900 dark:text-white
                       focus:outline-none focus:ring-2 focus:ring-cyan-500
                       disabled:opacity-50 disabled:cursor-not-allowed"
              placeholder="0.0"
              aria-describedby="target-y-help"
            />
            <p id="target-y-help" className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              Range: -10 to 10m
            </p>
          </div>
        </div>
        <button
          type="submit"
          disabled={isSubmitting || !isConnected || !targetX || !targetY}
          className="mt-3 w-full px-4 py-2 bg-cyan-600 hover:bg-cyan-700 text-white rounded-md
                   focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:ring-offset-2
                   disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          aria-label="Navigate to destination"
        >
          {isSubmitting ? 'Navigating...' : 'Navigate'}
        </button>
      </form>

      {/* Control Buttons */}
      <div className="grid grid-cols-3 gap-2" role="group" aria-label="Robot control buttons">
        <button
          onClick={handleStop}
          disabled={!isConnected}
          className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-md
                   focus:outline-none focus:ring-2 focus:ring-amber-500 focus:ring-offset-2
                   disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          aria-label="Stop robot"
        >
          Stop
        </button>
        <button
          onClick={handleEmergencyStop}
          disabled={!isConnected}
          className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-md
                   focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2
                   disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          aria-label="Emergency stop robot"
        >
          E-Stop
        </button>
        <button
          onClick={() => onNavigate({ x: 0, y: 0 })}
          disabled={!isConnected}
          className="px-4 py-2 bg-slate-600 hover:bg-slate-700 text-white rounded-md
                   focus:outline-none focus:ring-2 focus:ring-slate-500 focus:ring-offset-2
                   disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          aria-label="Return to start"
        >
          Return
        </button>
      </div>
    </div>
  );
});

ControlPanel.displayName = 'ControlPanel';