"""Lightweight camera object detection for Raspberry Pi bring-up."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class Detection:
    """Detected visual object."""

    label: str
    confidence: float
    box: Tuple[int, int, int, int]


class ObjectDetector:
    """
    OpenCV-based detector that works without model downloads.

    It combines OpenCV's built-in HOG people detector with contour proposals.
    The contour path is intentionally generic: it gives the robot a usable
    "object in view" signal on a fresh Raspberry Pi before a trained model is
    added.
    """

    def __init__(self, min_area: int = 1500):
        try:
            import cv2  # type: ignore
        except Exception as exc:
            raise RuntimeError("OpenCV is required for object detection") from exc

        self.cv2 = cv2
        self.min_area = min_area
        self._hog = cv2.HOGDescriptor()
        self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def detect(self, frame) -> List[Detection]:
        detections: List[Detection] = []
        detections.extend(self._detect_people(frame))
        detections.extend(self._detect_object_contours(frame))
        return self._deduplicate(detections)

    def draw(self, frame, detections: List[Detection]):
        for item in detections:
            x, y, w, h = item.box
            color = (0, 180, 255) if item.label == "object" else (0, 255, 0)
            self.cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            text = f"{item.label} {item.confidence:.2f}"
            self.cv2.putText(
                frame,
                text,
                (x, max(20, y - 8)),
                self.cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                color,
                2,
                self.cv2.LINE_AA,
            )
        return frame

    def _detect_people(self, frame) -> List[Detection]:
        resized = self.cv2.resize(frame, (320, 240))
        boxes, weights = self._hog.detectMultiScale(
            resized,
            winStride=(8, 8),
            padding=(8, 8),
            scale=1.05,
        )

        scale_x = frame.shape[1] / 320
        scale_y = frame.shape[0] / 240
        detections: List[Detection] = []
        for (x, y, w, h), weight in zip(boxes, weights):
            detections.append(
                Detection(
                    label="person",
                    confidence=float(max(0.0, min(1.0, weight))),
                    box=(int(x * scale_x), int(y * scale_y), int(w * scale_x), int(h * scale_y)),
                )
            )
        return detections

    def _detect_object_contours(self, frame) -> List[Detection]:
        gray = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2GRAY)
        gray = self.cv2.GaussianBlur(gray, (7, 7), 0)
        edges = self.cv2.Canny(gray, 50, 150)
        edges = self.cv2.dilate(edges, None, iterations=1)
        contours, _ = self.cv2.findContours(edges, self.cv2.RETR_EXTERNAL, self.cv2.CHAIN_APPROX_SIMPLE)

        detections: List[Detection] = []
        frame_area = frame.shape[0] * frame.shape[1]
        for contour in contours:
            area = self.cv2.contourArea(contour)
            if area < self.min_area or area > frame_area * 0.65:
                continue
            x, y, w, h = self.cv2.boundingRect(contour)
            if w < 25 or h < 25:
                continue
            confidence = min(0.95, max(0.2, area / (frame_area * 0.08)))
            detections.append(Detection(label="object", confidence=float(confidence), box=(x, y, w, h)))
        return detections[:8]

    def _deduplicate(self, detections: List[Detection]) -> List[Detection]:
        result: List[Detection] = []
        for item in sorted(detections, key=lambda d: d.confidence, reverse=True):
            if all(self._iou(item.box, other.box) < 0.35 for other in result):
                result.append(item)
        return result[:10]

    @staticmethod
    def _iou(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        x1 = max(ax, bx)
        y1 = max(ay, by)
        x2 = min(ax + aw, bx + bw)
        y2 = min(ay + ah, by + bh)
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        union = aw * ah + bw * bh - inter
        return inter / union if union else 0.0

