# %%
import cv2
import json
import time
from pathlib import Path
from ultralytics import YOLO

# %%
cap = cv2.VideoCapture("/dev/video0")
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
cap.set(cv2.CAP_PROP_FPS, 5)

model = YOLO("/home/jetson/project/yolo26m.pt")

print("model device:", next(model.model.parameters()).device)
print("model dtype:", next(model.model.parameters()).dtype)

output_dir = Path("/home/jetson/project/tests/output")
output_dir.mkdir(parents=True, exist_ok=True)
video_path = output_dir / "live_capture_raw.mp4"
json_path = output_dir / "live_capture_detections.json"

fps = cap.get(cv2.CAP_PROP_FPS)
if fps <= 0:
    fps = 5.0

writer = None
frame_index = 0
start_time = time.time()
detections_payload = []

while True:
    ret, frame = cap.read()
    if not ret:
        break

    elapsed_seconds = time.time() - start_time
    if elapsed_seconds >= 10:
        break

    if writer is None:
        height, width = frame.shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(video_path), fourcc, fps, (width, height))

    writer.write(frame)

    results = model.track(frame, persist=True, verbose=True)
    r = results[0]

    frame_detections = []
    if r.boxes is not None and len(r.boxes) > 0:
        ids = r.boxes.id.tolist() if r.boxes.id is not None else [None] * len(r.boxes)
        classes = r.boxes.cls.tolist()
        confs = r.boxes.conf.tolist()
        xyxy = r.boxes.xyxy.tolist()
        for det_idx in range(len(r.boxes)):
            frame_detections.append(
                {
                    "track_id": int(ids[det_idx]) if ids[det_idx] is not None else None,
                    "class_id": int(classes[det_idx]),
                    "confidence": float(confs[det_idx]),
                    "bbox_xyxy": [float(v) for v in xyxy[det_idx]],
                }
            )

    detections_payload.append(
        {
            "frame_index": frame_index,
            "elapsed_seconds": elapsed_seconds,
            "detections": frame_detections,
        }
    )

    frame_index += 1

cap.release()
if writer is not None:
    writer.release()

with open(json_path, "w", encoding="utf-8") as f:
    json.dump(
        {
            "video_path": str(video_path),
            "fps": fps,
            "total_frames": frame_index,
            "duration_seconds": min(time.time() - start_time, 10.0),
            "frames": detections_payload,
        },
        f,
        indent=2,
    )

print(f"Saved raw clip to: {video_path}")
print(f"Saved detections JSON to: {json_path}")

# %%



