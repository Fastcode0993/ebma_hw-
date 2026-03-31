/**
 * LiDAR Canvas Component
 * 
 * Renders LiDAR scan data on HTML5 Canvas
 * Shows 180° forward-facing scan points
 */
import React, { memo, useEffect, useRef, useState } from 'react';
import type { LiDARPoint, Obstacle } from '../../types/robot.types';

interface LiDARCanvasProps {
  lidarPoints: LiDARPoint[];
  robotHeading: number;
  maxRange: number;
  showRobotHeading?: boolean;
}

export const LiDARCanvas: React.FC<LidarCanvasProps> = memo(({
  lidarPoints,
  robotHeading,
  maxRange,
  showRobotHeading = true,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [obstacles, setObstacles] = useState<Obstacle[]>([]);

  // Extract obstacles from lidar points
  useEffect(() => {
    const obstacleThreshold = 2.0; // meters
    const newObstacles: Obstacle[] = lidarPoints
      .filter(point => point.distance < obstacleThreshold && point.distance > 0.5)
      .map(point => ({
        angle: point.angle,
        distance: point.distance,
        confidence: Math.min(1, (obstacleThreshold - point.distance) / obstacleThreshold),
      }));
    setObstacles(newObstacles);
  }, [lidarPoints]);

  // Draw on canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Center point
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;

    // Draw range circle
    ctx.beginPath();
    ctx.arc(centerX, centerY, maxRange, -Math.PI / 4, Math.PI * 3 / 4);
    ctx.strokeStyle = 'rgba(14, 165, 233, 0.2)';
    ctx.lineWidth = 1;
    ctx.stroke();

    // Draw forward arc
    ctx.beginPath();
    ctx.arc(centerX, centerY, maxRange, -Math.PI / 4, Math.PI * 3 / 4);
    ctx.strokeStyle = 'rgba(14, 165, 233, 0.5)';
    ctx.lineWidth = 2;
    ctx.stroke();

    // Draw lidar points
    lidarPoints.forEach(point => {
      // Convert polar to cartesian coordinates
      const angleRad = (point.angle * Math.PI) / 180;
      const x = centerX + point.distance * Math.cos(angleRad);
      const y = centerY + point.distance * Math.sin(angleRad);

      // Color based on distance
      const distanceRatio = point.distance / maxRange;
      const hue = 180 - (distanceRatio * 120); // Blue to red
      const alpha = 1 - distanceRatio;

      ctx.beginPath();
      ctx.arc(x, y, 2, 0, Math.PI * 2);
      ctx.fillStyle = `hsla(${hue}, 70%, 50%, ${alpha})`;
      ctx.fill();
    });

    // Draw obstacles
    obstacles.forEach(obstacle => {
      const angleRad = (obstacle.angle * Math.PI) / 180;
      const x = centerX + obstacle.distance * Math.cos(angleRad);
      const y = centerY + obstacle.distance * Math.sin(angleRad);

      ctx.beginPath();
      ctx.arc(x, y, 6, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(239, 68, 68, ${obstacle.confidence})`;
      ctx.fill();
      ctx.strokeStyle = 'rgba(239, 68, 68, 0.8)';
      ctx.lineWidth = 2;
      ctx.stroke();
    });

    // Draw robot heading indicator
    if (showRobotHeading) {
      const headingRad = (robotHeading * Math.PI) / 180;
      const headingLength = maxRange * 0.8;
      const headingX = centerX + headingLength * Math.cos(headingRad);
      const headingY = centerY + headingLength * Math.sin(headingRad);

      // Draw heading line
      ctx.beginPath();
      ctx.moveTo(centerX, centerY);
      ctx.lineTo(headingX, headingY);
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.8)';
      ctx.lineWidth = 2;
      ctx.stroke();

      // Draw heading arrow
      const arrowLength = 10;
      const arrowAngle = headingRad + Math.PI / 2;
      const arrowX1 = headingX - arrowLength * Math.cos(arrowAngle);
      const arrowY1 = headingY - arrowLength * Math.sin(arrowAngle);
      const arrowX2 = headingX - arrowLength * Math.cos(arrowAngle + Math.PI / 6);
      const arrowY2 = headingY - arrowLength * Math.sin(arrowAngle + Math.PI / 6);
      const arrowX3 = headingX - arrowLength * Math.cos(arrowAngle - Math.PI / 6);
      const arrowY3 = headingY - arrowLength * Math.sin(arrowAngle - Math.PI / 6);

      ctx.beginPath();
      ctx.moveTo(headingX, headingY);
      ctx.lineTo(arrowX1, arrowY1);
      ctx.lineTo(arrowX2, arrowY2);
      ctx.lineTo(arrowX3, arrowY3);
      ctx.closePath();
      ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
      ctx.fill();
    }

    // Draw center crosshair
    ctx.beginPath();
    ctx.moveTo(centerX - 5, centerY);
    ctx.lineTo(centerX + 5, centerY);
    ctx.moveTo(centerX, centerY - 5);
    ctx.lineTo(centerX, centerY + 5);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
    ctx.lineWidth = 1;
    ctx.stroke();
  }, [lidarPoints, obstacles, robotHeading, maxRange, showRobotHeading]);

  return (
    <div className="relative">
      <canvas
        ref={canvasRef}
        width={300}
        height={300}
        className="w-full h-full"
        aria-label="LiDAR scan visualization"
        role="img"
      />
      <div className="absolute top-2 left-2 text-xs text-slate-400">
        <div>LiDAR Scan (180°)</div>
        <div>Range: {maxRange}m</div>
      </div>
      <div className="absolute bottom-2 left-2 text-xs text-slate-400">
        <div>Points: {lidarPoints.length}</div>
        <div>Obstacles: {obstacles.length}</div>
      </div>
    </div>
  );
});

LiDARCanvas.displayName = 'LiDARCanvas';