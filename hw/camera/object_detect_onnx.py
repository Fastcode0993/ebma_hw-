"""Lightweight YOLOv8 ONNX object detection for Raspberry Pi.

Uses OpenCV DNN only. This avoids installing PyTorch/Ultralytics on the Pi.
Expected model: YOLOv8 detection ONNX with output shape 1x84x8400.
"""
from __future__ import annotations

import argparse
import json
import time

import cv2  # type: ignore
import numpy as np  # type: ignore


COCO_NAMES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
    "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
    "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
    "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run lightweight ONNX object detection.")
    parser.add_argument("--model", default="camera/yolov8n.onnx")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.35)
    parser.add_argument("--nms", type=float, default=0.45)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--warmup", type=int, default=5, help="Drop initial camera frames before detection.")
    return parser.parse_args()


class FrameSource:
    def __init__(self, camera_index: int):
        self.camera_index = camera_index
        self.picamera = None
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

        capture = cv2.VideoCapture(self.camera_index)
        if not capture.isOpened():
            raise RuntimeError(f"Camera index {self.camera_index} did not open")
        self.capture = capture

    def read(self) -> np.ndarray:
        if self.picamera is not None:
            frame = self.picamera.capture_array()
            return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
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


def detect(net, frame: np.ndarray, imgsz: int, conf_threshold: float, nms_threshold: float) -> list[dict]:
    height, width = frame.shape[:2]
    input_image = cv2.resize(frame, (imgsz, imgsz))
    blob = cv2.dnn.blobFromImage(input_image, 1.0 / 255.0, (imgsz, imgsz), swapRB=True, crop=False)
    net.setInput(blob)
    outputs = net.forward()

    predictions = np.squeeze(outputs)
    if predictions.ndim != 2:
        return []
    if predictions.shape[0] < predictions.shape[1]:
        predictions = predictions.T

    boxes = []
    scores = []
    class_ids = []
    x_scale = width / float(imgsz)
    y_scale = height / float(imgsz)

    for row in predictions:
        class_scores = row[4:]
        class_id = int(np.argmax(class_scores))
        score = float(class_scores[class_id])
        if score < conf_threshold:
            continue
        cx, cy, box_w, box_h = [float(value) for value in row[:4]]
        x = int((cx - box_w / 2.0) * x_scale)
        y = int((cy - box_h / 2.0) * y_scale)
        w = int(box_w * x_scale)
        h = int(box_h * y_scale)
        boxes.append([x, y, w, h])
        scores.append(score)
        class_ids.append(class_id)

    indices = cv2.dnn.NMSBoxes(boxes, scores, conf_threshold, nms_threshold)
    detections = []
    for i in np.array(indices).flatten():
        x, y, w, h = boxes[int(i)]
        class_id = class_ids[int(i)]
        detections.append(
            {
                "label": COCO_NAMES[class_id] if 0 <= class_id < len(COCO_NAMES) else str(class_id),
                "confidence": round(scores[int(i)], 3),
                "box": [x, y, x + w, y + h],
                "center": [round(x + w / 2.0, 1), round(y + h / 2.0, 1)],
            }
        )
    return detections


def main() -> None:
    args = parse_args()
    net = cv2.dnn.readNetFromONNX(args.model)
    source = FrameSource(args.camera_index)
    source.start()
    try:
        for _ in range(max(0, args.warmup)):
            source.read()
            time.sleep(0.05)
        while True:
            frame = source.read()
            detections = detect(net, frame, args.imgsz, args.conf, args.nms)
            print(
                json.dumps(
                    {
                        "command": "object_detect",
                        "ok": True,
                        "detections": detections,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            if args.once:
                break
            time.sleep(args.interval)
    finally:
        source.stop()


if __name__ == "__main__":
    main()
