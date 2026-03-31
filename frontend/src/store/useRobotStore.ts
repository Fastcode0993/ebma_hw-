/**
 * Robot Store
 * 
 * Zustand-based global state management for robot control system
 */
import { create } from 'zustand';
import type { 
  RobotStatus, 
  RobotPosition, 
  LiDARPoint, 
  Obstacle, 
  LogEntry,
  Destination,
  RobotStoreState,
  RobotStoreActions 
} from '../types/robot.types';

// Initial state
const initialState: RobotStoreState = {
  status: {
    battery: 0,
    obstacleAhead: false,
    lidarPoints: [],
    obstacles: [],
    status: 'idle',
    speed: 0,
    timestamp: Date.now(),
  },
  position: {
    x: 0,
    y: 0,
  },
  destination: null,
  logs: [],
  isConnecting: false,
  isConnected: false,
};

export const useRobotStore = create<RobotStoreState & RobotStoreActions>((set, get) => ({
  // State
  status: initialState.status,
  position: initialState.position,
  destination: initialState.destination,
  logs: initialState.logs,
  isConnecting: initialState.isConnecting,
  isConnected: initialState.isConnected,

  // Actions
  setDestination: (x: number, y: number, name?: string) => {
    set({
      destination: {
        x,
        y,
        name,
        createdAt: Date.now(),
      },
    });
  },

  emergencyStop: () => {
    set({
      status: {
        ...get().status,
        status: 'stopped',
        timestamp: Date.now(),
      },
    });
  },

  addLog: (entry: Omit<LogEntry, 'id'>) => {
    set((state) => ({
      logs: [
        {
          id: Date.now(),
          ...entry,
        },
        ...state.logs.slice(0, 99), // Keep last 100 logs
      ],
    }));
  },

  updateStatus: (partial: Partial<RobotStatus>) => {
    set((state) => ({
      status: {
        ...state.status,
        ...partial,
        timestamp: Date.now(),
      },
    }));
  },

  updatePosition: (position: Partial<RobotPosition>) => {
    set((state) => ({
      position: {
        ...state.position,
        ...position,
      },
    }));
  },

  setConnectionStatus: (isConnected: boolean, errorMessage?: string) => {
    set({
      isConnecting: false,
      isConnected,
      errorMessage,
    });
  },

  clearDestination: () => {
    set({
      destination: null,
    });
  },

  // Helper methods
  calculateBatteryPercentage: (voltage: number): number => {
    // Assuming 12V nominal, 10.8V empty, 13.2V full
    const minVoltage = 10.8;
    const maxVoltage = 13.2;
    const percentage = Math.max(0, Math.min(100, ((voltage - minVoltage) / (maxVoltage - minVoltage)) * 100));
    return Math.round(percentage);
  },

  getNearestObstacle: (): Obstacle | null => {
    const { obstacles } = get();
    if (obstacles.length === 0) return null;
    return obstacles.reduce((nearest, obstacle) => 
      obstacle.distance < nearest.distance ? obstacle : nearest
    );
  },

  hasObstacleInRange: (range: number = 3): boolean => {
    const nearest = get().getNearestObstacle();
    return nearest && nearest.distance < range;
  },
}));