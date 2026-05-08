"""LiDAR object localization from polar scan points."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, List

from .lidar_ld19 import LidarPoint


LD19_MAX_RANGE_M = 12.0


@dataclass
class LidarObject:
    """Estimated object position in robot-local coordinates."""

    x: float
    y: float
    distance: float
    angle: float
    point_count: int
    width: float


class LidarObjectLocalizer:
    """Cluster LiDAR scan points and estimate object positions."""

    def __init__(
        self,
        max_range_m: float = LD19_MAX_RANGE_M,
        min_range_m: float = 0.05,
        cluster_gap_m: float = 0.25,
        min_cluster_points: int = 2,
    ):
        self.max_range_m = max_range_m
        self.min_range_m = min_range_m
        self.cluster_gap_m = cluster_gap_m
        self.min_cluster_points = min_cluster_points

    def locate(self, points: Iterable[LidarPoint]) -> List[LidarObject]:
        valid_points = [
            point
            for point in points
            if self.min_range_m <= point.distance <= self.max_range_m
        ]
        if not valid_points:
            return []

        cartesian = [
            (point, *self._polar_to_xy(point.angle, point.distance))
            for point in sorted(valid_points, key=lambda item: item.angle)
        ]
        clusters = self._cluster(cartesian)
        objects = [self._cluster_to_object(cluster) for cluster in clusters if len(cluster) >= self.min_cluster_points]
        return sorted(objects, key=lambda item: item.distance)

    def _cluster(self, cartesian):
        clusters = []
        current = [cartesian[0]]

        for item in cartesian[1:]:
            _, prev_x, prev_y = current[-1]
            _, x, y = item
            if math.hypot(x - prev_x, y - prev_y) <= self.cluster_gap_m:
                current.append(item)
            else:
                clusters.append(current)
                current = [item]
        clusters.append(current)

        if len(clusters) > 1 and self._wrap_gap(clusters[0][0], clusters[-1][-1]) <= self.cluster_gap_m:
            clusters[0] = clusters[-1] + clusters[0]
            clusters.pop()

        return clusters

    def _cluster_to_object(self, cluster) -> LidarObject:
        xs = [x for _, x, _ in cluster]
        ys = [y for _, _, y in cluster]
        center_x = sum(xs) / len(xs)
        center_y = sum(ys) / len(ys)
        distance = math.hypot(center_x, center_y)
        angle = math.degrees(math.atan2(center_y, center_x)) % 360.0
        width = max(
            math.hypot(ax - bx, ay - by)
            for _, ax, ay in cluster
            for _, bx, by in cluster
        )
        return LidarObject(
            x=center_x,
            y=center_y,
            distance=distance,
            angle=angle,
            point_count=len(cluster),
            width=width,
        )

    @staticmethod
    def _polar_to_xy(angle_deg: float, distance_m: float) -> tuple[float, float]:
        angle_rad = math.radians(angle_deg)
        return distance_m * math.cos(angle_rad), distance_m * math.sin(angle_rad)

    @staticmethod
    def _wrap_gap(first, last) -> float:
        _, first_x, first_y = first
        _, last_x, last_y = last
        return math.hypot(first_x - last_x, first_y - last_y)

