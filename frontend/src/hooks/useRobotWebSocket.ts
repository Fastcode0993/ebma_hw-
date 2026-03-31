/**
 * Robot WebSocket Hook
 * 
 * Custom hook for WebSocket connection to robot control server
 * Features:
 * - Auto-reconnect with exponential backoff
 * - Message queueing during disconnection
 * - Type-safe message parsing
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import type { 
  RobotStatus, 
  RobotPosition, 
  LiDARPoint, 
  Obstacle,
  NavigationCommand 
} from '../types/robot.types';

const WS_URL = 'ws://localhost:8000/ws/robot/control';
const MAX_RECONNECT_ATTEMPTS = 10;
const INITIAL_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 30000;

interface WebSocketState {
  isConnected: boolean;
  isConnecting: boolean;
  errorMessage: string | null;
  reconnectAttempts: number;
}

export function useRobotWebSocket() {
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [state, setState] = useState<WebSocketState>({
    isConnected: false,
    isConnecting: false,
    errorMessage: null,
    reconnectAttempts: 0,
  });

  const messageQueue = useRef<NavigationCommand[]>([]);
  const reconnectTimeout = useRef<NodeJS.Timeout | null>(null);

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (state.isConnecting || state.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      return;
    }

    setState(prev => ({ ...prev, isConnecting: true, errorMessage: null }));

    try {
      const newSocket = new WebSocket(WS_URL);

      newSocket.onopen = () => {
        console.log('WebSocket connected');
        setState({
          isConnected: true,
          isConnecting: false,
          errorMessage: null,
          reconnectAttempts: 0,
        });
        // Send queued messages
        messageQueue.current.forEach(msg => {
          newSocket.send(JSON.stringify(msg));
        });
        messageQueue.current = [];
      };

      newSocket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log('Received message:', data);
          
          // Handle different message types
          if (data.cmd === 'navigate' && data.target) {
            // Navigation command received
            console.log('Navigation command:', data);
          }
        } catch (error) {
          console.error('Failed to parse message:', error);
        }
      };

      newSocket.onerror = (error) => {
        console.error('WebSocket error:', error);
        setState(prev => ({
          ...prev,
          errorMessage: 'WebSocket error occurred',
        }));
      };

      newSocket.onclose = (event) => {
        console.log('WebSocket closed:', event.code, event.reason);
        setState(prev => ({
          ...prev,
          isConnected: false,
          isConnecting: false,
        }));

        // Attempt reconnection
        if (event.code !== 1000) {
          scheduleReconnect();
        }
      };

      setSocket(newSocket);
    } catch (error) {
      console.error('Failed to connect WebSocket:', error);
      setState(prev => ({
        ...prev,
        errorMessage: 'Failed to connect to server',
        isConnecting: false,
      }));
    }
  }, [state.isConnecting, state.reconnectAttempts]);

  // Schedule reconnection with exponential backoff
  const scheduleReconnect = useCallback(() => {
    if (state.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      console.error('Max reconnection attempts reached');
      setState(prev => ({
        ...prev,
        errorMessage: 'Max reconnection attempts reached. Please refresh the page.',
      }));
      return;
    }

    const backoff = Math.min(
      INITIAL_BACKOFF_MS * Math.pow(2, state.reconnectAttempts),
      MAX_BACKOFF_MS
    );

    setState(prev => ({
      ...prev,
      reconnectAttempts: prev.reconnectAttempts + 1,
      errorMessage: `Reconnecting in ${backoff / 1000}s...`,
    }));

    reconnectTimeout.current = setTimeout(connect, backoff);
  }, [state.reconnectAttempts, connect]);

  // Send command through WebSocket
  const sendCommand = useCallback((command: NavigationCommand) => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(command));
    } else {
      // Queue message for later
      messageQueue.current.push(command);
    }
  }, [socket]);

  // Emergency stop command
  const emergencyStop = useCallback(() => {
    sendCommand({ cmd: 'emergency_stop' });
  }, [sendCommand]);

  // Navigation command
  const navigate = useCallback((target: { x: number; y: number }) => {
    sendCommand({ cmd: 'navigate', target });
  }, [sendCommand]);

  // Stop command
  const stop = useCallback(() => {
    sendCommand({ cmd: 'stop' });
  }, [sendCommand]);

  // Reconnect on component mount
  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeout.current) {
        clearTimeout(reconnectTimeout.current);
      }
      if (socket) {
        socket.close();
      }
    };
  }, [connect]);

  return {
    socket,
    ...state,
    sendCommand,
    emergencyStop,
    navigate,
    stop,
  };
}