/**
 * Robot Map Component
 * 
 * Displays indoor map with robot position and destination marker
 * Uses HTML5 Canvas for custom rendering
 */
import React, { memo, useEffect, useRef } from 'react';
import type { RobotPosition, Destination } from '../../types/robot.types';

interface RobotMapProps {
  robotPosition: RobotPosition;
  destination: Destination | null;
  mapSize: { width: number; height: number };
  showGrid?: boolean;
  showRobotHeading?: boolean;
}

export const RobotMap: React.FC<RobotMapProps> = memo(({
  robotPosition,
  destination,
  mapSize,
  showGrid = true,
  showRobotHeading = true,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Draw on canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const { width, height } = mapSize;
    const centerX = width / 2;
    const centerY = height / 2;

    // Clear canvas
    ctx.clearRect(0, 0, width, height);

    // Draw grid
    if (showGrid) {
      ctx.strokeStyle = 'rgba(148, 163, 184, 0.3)';
      ctx.lineWidth = 1;

      const gridSize = 1; // meters

      // Vertical lines
      for (let x = centerX % gridSize; x < width; x += gridSize) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }

      // Horizontal lines
      for (let y = centerY % gridSize; y < height; y += gridSize) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }

      // Draw grid labels
      ctx.fillStyle = 'rgba(148, 163, 184, 0.6)';
      ctx.font = '10px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';

      for (let x = centerX % gridSize; x < width; x += gridSize) {
        ctx.fillText(`${(x - centerX) / gridSize}m`, x, centerY + gridSize / 2);
      }

      for (let y = centerY % gridSize; y < height; y += gridSize) {
        ctx.fillText(`${(y - centerY) / gridSize}m`, centerX + gridSize / 2, y);
      }
    }

    // Draw robot
    const robotRadius = 8;
    const robotX = centerX + robotPosition.x * 2; // Scale factor
    const robotY = centerY - robotPosition.y * 2; // Invert Y axis

    // Robot body
    ctx.beginPath();
    ctx.arc(robotX, robotY, robotRadius, 0, Math.PI * 2);
    ctx.fillStyle = '#0ea5e9';
    ctx.fill();
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 2;
    ctx.stroke();

    // Robot heading indicator
    if (showRobotHeading) {
      const headingRad = (robotPosition.heading || 0) * Math.PI / 180;
      const headingLength = robotRadius * 1.5;
      const headingX = robotX + headingLength * Math.cos(headingRad);
      const headingY = robotY - headingLength * Math.sin(headingRad);

      ctx.beginPath();
      ctx.moveTo(robotX, robotY);
      ctx.lineTo(headingX, headingY);
      ctx.strokeStyle = '#0ea5e9';
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    // Draw destination marker
    if (destination) {
      const destX = centerX + destination.x * 2;
      const destY = centerY - destination.y * 2;

      // Destination circle
      ctx.beginPath();
      ctx.arc(destX, destY, 12, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(239, 68, 68, 0.3)';
      ctx.fill();
      ctx.strokeStyle = '#ef4444';
      ctx.lineWidth = 2;
      ctx.stroke();

      // Destination pulse effect
      const pulseSize = 12 + Math.sin(Date.now() / 500) * 3;
      ctx.beginPath();
      ctx.arc(destX, destY, pulseSize, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(239, 68, 68, 0.5)';
      ctx.lineWidth = 1;
      ctx.stroke();

      // Destination label
      ctx.fillStyle = '#ef4444';
      ctx.font = 'bold 12px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('DEST', destX, destY);
    }

    // Draw origin marker
    ctx.beginPath();
    ctx.arc(centerX, centerY, 4, 0, Math.PI * 2);
    ctx.fillStyle = '#10b981';
    ctx.fill();
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 1;
    ctx.stroke();

    // Origin label
    ctx.fillStyle = '#64748b';
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('START', centerX, centerY + 20);
  }, [robotPosition, destination, mapSize, showGrid, showRobotHeading]);

  return (
    <div className="relative">
      <canvas
        ref={canvasRef}
        width={mapSize.width}
        height={mapSize.height}
        className="w-full h-full"
        aria-label="Robot map with position and destination"
        role="img"
      />
      <div className="absolute top-2 left-2 text-xs text-slate-400">
        <div>Indoor Map</div>
        <div>Scale: 1m = 2px</div>
      </div>
    </div>
  );
});

RobotMap.displayName = 'RobotMap';