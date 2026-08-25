"""
detection.py -- YOLOv8 detection pipeline.

Run as standalone test:  python detection.py --video path/to/video.mp4
"""

import cv2
import argparse
import os
from ultralytics import YOLO
from utils import ensure_dirs, draw_box, OUTPUT_DIR

# ---------------------------------------------------------------------------
# Configuration -- change these to tune the pipeline
# ---------------------------------------------------------------------------
MODEL_PATH     = "yolov8n.pt"   # YOLOv8 nano; swap to yolov8s/m for accuracy
CONF_THRESHOLD = 0.4            # ignore detections below this confidence
IOU_THRESHOLD  = 0.5            # NMS overlap threshold

# COCO class IDs we care about; everything else is filtered out
RELEVANT_CLASSES = {
    0: "person",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

# BGR draw colours per class
CLASS_COLORS = {
    "person":     (0, 255, 0),
    "car":        (255, 165, 0),
    "motorcycle": (0, 0, 255),
    "bus":        (255, 0, 255),
    "truck":      (0, 255, 255),
}


def load_model(model_path=MODEL_PATH):
    # Loads (and caches) the YOLOv8 model; downloads weights on first run
    print(f"[detection] Loading model: {model_path}")
    return YOLO(model_path)


def run_detection(video_path, model=None, save_output=True):
    """
    Generator: yields one dict per frame with detection results.

    Each yielded dict:
        frame_number   : int
        timestamp_sec  : float   -- seconds from video start
        fps            : float   -- video fps (needed by parking timer)
        detections     : list of {class_name, confidence, box=(x1,y1,x2,y2)}
        annotated_frame: np.ndarray  -- BGR frame with bounding boxes drawn
    """
    ensure_dirs()
    if model is None:
        model = load_model()

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video_path}")

    fps          = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width        = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height       = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"[detection] {width}x{height} @ {fps:.1f} fps  {total_frames} frames total")

    writer = None
    if save_output:
        out_path = os.path.join(OUTPUT_DIR, "annotated_output.mp4")
        fourcc   = cv2.VideoWriter_fourcc(*"mp4v")
        writer   = cv2.VideoWriter(out_path, fourcc, fps, (width, height))
        print(f"[detection] Annotated video -> {out_path}")

    frame_number = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break   # end of video

            timestamp_sec = frame_number / fps

            # Run YOLOv8; verbose=False suppresses per-frame console noise
            results    = model(frame, conf=CONF_THRESHOLD, iou=IOU_THRESHOLD, verbose=False)
            detections = []

            for box_obj in results[0].boxes:
                cls_id = int(box_obj.cls[0])
                if cls_id not in RELEVANT_CLASSES:
                    continue                        # skip irrelevant objects

                class_name = RELEVANT_CLASSES[cls_id]
                conf       = float(box_obj.conf[0])
                x1, y1, x2, y2 = box_obj.xyxy[0].tolist()
                box = (int(x1), int(y1), int(x2), int(y2))

                detections.append({
                    "class_name": class_name,
                    "confidence": conf,
                    "box":        box,
                })

                # Draw box + label on the annotated frame
                color = CLASS_COLORS.get(class_name, (200, 200, 200))
                draw_box(frame, box, f"{class_name} {conf:.2f}", color=color)

            # Frame-number overlay (top-left corner)
            cv2.putText(frame, f"Frame {frame_number}",
                        (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            if writer:
                writer.write(frame)

            yield {
                "frame_number":    frame_number,
                "timestamp_sec":   timestamp_sec,
                "fps":             fps,
                "detections":      detections,
                "annotated_frame": frame,
            }

            frame_number += 1
            if frame_number % 100 == 0:
                print(f"[detection] {frame_number}/{total_frames} frames processed")

    finally:
        cap.release()
        if writer:
            writer.release()
        print(f"[detection] Done. Processed {frame_number} frames.")


# ---------------------------------------------------------------------------
# Standalone test -- run:  python detection.py --video my_clip.mp4
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Test YOLOv8 detection")
    ap.add_argument("--video", required=True, help="Path to input video")
    args = ap.parse_args()

    model       = load_model()
    frame_count = 0
    total_dets  = 0

    for fd in run_detection(args.video, model=model, save_output=True):
        frame_count += 1
        total_dets  += len(fd["detections"])

        # Show first 5 frames for a quick sanity-check
        if frame_count <= 5:
            print(f"  Frame {fd['frame_number']:>4}  "
                  f"{len(fd['detections'])} dets  "
                  f"@ {fd['timestamp_sec']:.2f}s")
            for d in fd["detections"]:
                print(f"    {d['class_name']:12} conf={d['confidence']:.2f}  box={d['box']}")

    print(f"\n[test] Finished. frames={frame_count}  total_detections={total_dets}")
    print("[test] Check output/annotated_output.mp4 to verify visually.")
