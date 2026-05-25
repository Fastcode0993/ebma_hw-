"""Object detection smoke test for the Raspberry Pi camera.

This is intentionally separate from camara.py so camera/model setup can be
verified before object detection is used by navigation.
"""
from __future__ import annotations

import argparse
import json
import time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run YOLO object detection on Raspberry Pi camera frames.")
    parser.add_argument("--model", default="yolo11n.pt", help="Ultralytics model path/name, e.g. yolo11n.pt.")
    parser.add_argument("--camera-index", type=int, default=0, help="OpenCV fallback camera index.")
    parser.add_argument("--imgsz", type=int, default=320, help="Inference image size. Lower is faster on Raspberry Pi.")
    parser.add_argument("--conf", type=float, default=0.35, help="Minimum detection confidence.")
    parser.add_argument("--interval", type=float, default=0.5, help="Seconds between detections.")
    parser.add_argument("--once", action="store_true", help="Run one detection and exit.")
    return parser.parse_args()


class FrameSource:
    def __init__(self, camera_index: int):
        self.camera_index = camera_index
        self.picamera = None
        self.cv2 = None
        self.capture = None

    def start(self) -> None:
        try:
            from picamera2 import Picamera2  # type: ignore

            camera = Picamera2()
            config = camera.create_preview_configuration(main={"size": (640, 480), "format": "RGB888"})
            camera.configure(config)
            camera.start()
            self.picamera = camera
            return
        except Exception:
            pass

        import cv2  # type: ignore

        capture = cv2.VideoCapture(self.camera_index)
        if not capture.isOpened():
            raise RuntimeError(f"Camera index {self.camera_index} did not open")
        self.cv2 = cv2
        self.capture = capture

    def read(self):
        if self.picamera is not None:
            return self.picamera.capture_array()
        if self.capture is None:
            raise RuntimeError("Camera is not started")
        ok, frame = self.capture.read()
        if not ok or frame is None:
            raise RuntimeError("Camera frame read failed")
        return frame

    def stop(self) -> None:
        if self.picamera is not None:
            self.picamera.stop()
            self.picamera.close()
            self.picamera = None
        if self.capture is not None:
            self.capture.release()
            self.capture = None


def result_to_json(result) -> str:
    names = result.names
    detections = []
    if result.boxes is not None:
        for box in result.boxes:
            cls_index = int(box.cls[0])
            x1, y1, x2, y2 = [float(value) for value in box.xyxy[0]]
            detections.append(
                {
                    "label": names.get(cls_index, str(cls_index)),
                    "confidence": round(float(box.conf[0]), 3),
                    "box": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                    "center": [round((x1 + x2) / 2.0, 1), round((y1 + y2) / 2.0, 1)],
                }
            )
    return json.dumps({"command": "object_detect", "ok": True, "detections": detections}, ensure_ascii=False)


def main() -> None:
    args = parse_args()

    from ultralytics import YOLO  # type: ignore

    model = YOLO(args.model)
    source = FrameSource(args.camera_index)
    source.start()
    try:
        while True:
            frame = source.read()
            results = model.predict(frame, imgsz=args.imgsz, conf=args.conf, verbose=False)
            print(result_to_json(results[0]), flush=True)
            if args.once:
                break
            time.sleep(args.interval)
    finally:
        source.stop()


if __name__ == "__main__":
    main()
