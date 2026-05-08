"""Camera access with Raspberry Pi Picamera2 and USB/OpenCV fallback."""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class CameraError(RuntimeError):
    """Raised when the camera cannot be opened or read."""


class CameraModule:
    """Small adapter that hides Picamera2 vs. OpenCV camera details."""

    def __init__(self, camera_index: int = 0, width: int = 640, height: int = 480):
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self._picamera = None
        self._capture = None
        self._cv2 = None

    def start(self) -> None:
        """Open the first available camera backend."""
        try:
            from picamera2 import Picamera2  # type: ignore

            camera = Picamera2()
            config = camera.create_preview_configuration(
                main={"size": (self.width, self.height), "format": "RGB888"}
            )
            camera.configure(config)
            camera.start()
            self._picamera = camera
            logger.info("Camera started with Picamera2")
            return
        except Exception as exc:
            logger.info("Picamera2 unavailable, trying OpenCV camera: %s", exc)

        try:
            import cv2  # type: ignore

            capture = cv2.VideoCapture(self.camera_index)
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            if not capture.isOpened():
                raise CameraError(f"OpenCV camera index {self.camera_index} did not open")
            self._cv2 = cv2
            self._capture = capture
            logger.info("Camera started with OpenCV VideoCapture(%s)", self.camera_index)
        except Exception as exc:
            raise CameraError(f"Unable to start camera: {exc}") from exc

    def read(self):
        """Read one frame as a NumPy array."""
        if self._picamera is not None:
            return self._picamera.capture_array()

        if self._capture is None:
            raise CameraError("Camera is not started")

        ok, frame = self._capture.read()
        if not ok or frame is None:
            raise CameraError("Camera frame read failed")
        return frame

    def stop(self) -> None:
        """Release camera resources."""
        if self._picamera is not None:
            self._picamera.stop()
            self._picamera.close()
            self._picamera = None

        if self._capture is not None:
            self._capture.release()
            self._capture = None

    @property
    def cv2(self) -> Optional[object]:
        """Return the imported cv2 module if OpenCV is available."""
        if self._cv2 is not None:
            return self._cv2
        try:
            import cv2  # type: ignore

            self._cv2 = cv2
            return cv2
        except Exception:
            return None

