/**
 * Robot Types
 * 
 * TypeScript interfaces for robot state, messages, and data structures
 */

/**
 * Robot Position
 * 로봇의 2D 위치 좌표
 */
export interface RobotPosition {
  x: number;
  y: number;
  heading?: number; // Heading angle in degrees (0-360)
  velocity?: number; // Current velocity in m/s
}

/**
 * LiDAR Point
 * LiDAR 스캔 포인트
 */
export interface LiDARPoint {
  angle: number; // Angle in degrees (-90 to 90 for forward-facing)
  distance: number; // Distance in meters
  timestamp?: number; // Unix timestamp
}

/**
 * Obstacle
 * 장애물 정보
 */
export interface Obstacle {
  angle: number; // Angle relative to robot heading
  distance: number; // Distance to obstacle in meters
  confidence: number; // Detection confidence (0-1)
}

/**
 * Robot Status
 * 로봇의 현재 상태
 */
export interface RobotStatus {
  battery: number; // Battery voltage in volts
  batteryPercentage?: number; // Battery percentage (0-100)
  obstacleAhead: boolean; // Whether there's an obstacle ahead
  lidarPoints: LiDARPoint[]; // Raw LiDAR scan points
  obstacles: Obstacle[]; // Detected obstacles
  status: 'idle' | 'moving' | 'stopped' | 'error'; // Current robot status
  speed: number; // Current speed in m/s
  error?: string; // Error message if status is 'error'
  timestamp: number; // Unix timestamp
}

/**
 * Navigation Command
 * 내비게이션 명령
 */
export interface NavigationCommand {
  cmd: 'navigate' | 'stop' | 'emergency_stop';
  target?: {
    x: number;
    y: number;
  };
}

/**
 * Log Entry
 * 주행 로그 엔트리
 */
export interface LogEntry {
  id: number;
  timestamp: number;
  event_type: 'start' | 'stop' | 'obstacle_detected' | 'destination_reached' | 'error';
  message: string;
  position?: { x: number; y: number };
  metadata?: Record<string, any>;
}

/**
 * Destination
 * 목적지 정보
 */
export interface Destination {
  x: number;
  y: number;
  name?: string; // Custom name for the destination
  createdAt: number;
}

/**
 * WebSocket Message Types
 * WebSocket 메시지 타입
 */
export type WebSocketMessage = 
  | { type: 'status'; payload: RobotStatus }
  | { type: 'position_update'; payload: RobotPosition }
  | { type: 'lidar_data'; payload: LiDARPoint[] }
  | { type: 'obstacle_alert'; payload: Obstacle }
  | { type: 'navigation_complete'; payload: { x: number; y: number } }
  | { type: 'error'; payload: { message: string; code: string } };

/**
 * Store State
 * Zustand 스토어 상태 인터페이스
 */
export interface RobotStoreState {
  status: RobotStatus;
  position: RobotPosition;
  destination: Destination | null;
  logs: LogEntry[];
  isConnecting: boolean;
  isConnected: boolean;
  errorMessage?: string;
}

/**
 * Store Actions
 * Zustand 스토어 액션 인터페이스
 */
export interface RobotStoreActions {
  setDestination: (x: number, y: number, name?: string) => void;
  emergencyStop: () => void;
  addLog: (entry: Omit<LogEntry, 'id'>) => void;
  updateStatus: (partial: Partial<RobotStatus>) => void;
  updatePosition: (position: Partial<RobotPosition>) => void;
  setConnectionStatus: (isConnected: boolean, errorMessage?: string) => void;
  clearDestination: () => void;
}