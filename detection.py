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
CONF_THRESHOLD = 0.4
REVIEW_CONF_THRESHOLD = 0.15            # ignore detections below this confidence
IOU_THRESHOLD  = 0.5            # NMS overlap threshold

# FRAME_SKIP: process every Nth frame.
#   1 = every frame (full accuracy, slowest)
#   3 = every 3rd frame (default -- good balance for 25-30 fps video)
#   5 = every 5th frame (fastest, may miss short events)
# Skipped frames are still written to the output video (last annotated frame
# is re-used) so the output video plays at the original speed.
FRAME_SKIP = 3

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


def process_single_frame(frame, model, frame_number=0, timestamp_sec=0.0, fps=25.0):
    """Run detection and annotation on a single frame."""
    results = model.track(frame, persist=True, tracker="bytetrack.yaml", conf=REVIEW_CONF_THRESHOLD, iou=IOU_THRESHOLD, verbose=False)
    detections = []
    original_frame = frame.copy()
    height, width = frame.shape[:2]

    for box_obj in results[0].boxes:
        cls_id = int(box_obj.cls[0])
        if cls_id not in RELEVANT_CLASSES:
            continue

        class_name = RELEVANT_CLASSES[cls_id]
        conf       = float(box_obj.conf[0])
        x1, y1, x2, y2 = box_obj.xyxy[0].tolist()
        box = (int(x1), int(y1), int(x2), int(y2))
        track_id   = int(box_obj.id[0]) if box_obj.id is not None else None

        detections.append({
            "track_id":   track_id,
            "class_name": class_name,
            "confidence": conf,
            "box":        box,
            "low_confidence_detection": conf < CONF_THRESHOLD,
        })

        color = CLASS_COLORS.get(class_name, (200, 200, 200))
        label = f"{class_name} [#{track_id}] {conf:.2f}" if track_id else f"{class_name} {conf:.2f}"
        draw_box(frame, box, label, color=color)

    cv2.putText(frame, f"Frame {frame_number}",
                (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    return {
        "frame_number":    frame_number,
        "timestamp_sec":   timestamp_sec,
        "fps":             fps,
        "frame_width":     width,
        "frame_height":    height,
        "detections":      detections,
        "annotated_frame": frame,
        "original_frame":  original_frame,
    }

def run_detection(video_path, model=None, save_output=True, frame_skip=FRAME_SKIP):
    """
    Generator: yields one dict per PROCESSED frame with detection results.
    Skipped frames are written to the output video but not yielded.

    Parameters
    ----------
    video_path  : str  -- path to input video
    model       : YOLO -- pre-loaded model (loaded here if None)
    save_output : bool -- write annotated video to output/
    frame_skip  : int  -- process every Nth frame (1 = every frame)

    Each yielded dict:
        frame_number   : int   -- absolute frame index in the video
        timestamp_sec  : float -- seconds from video start
        fps            : float -- video fps (needed by parking timer)
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
    print(f"[detection] frame_skip={frame_skip}  "
          f"(will run inference on ~{total_frames // frame_skip} frames)")

    writer       = None
    last_frame   = None   # last annotated frame, re-used for skipped frames in output video

    if save_output:
        out_path = os.path.join(OUTPUT_DIR, "annotated_output.mp4")
        fourcc   = cv2.VideoWriter_fourcc(*"mp4v")
        writer   = cv2.VideoWriter(out_path, fourcc, fps, (width, height))
        print(f"[detection] Annotated video -> {out_path}")

    frame_number    = 0
    frames_inferred = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break   # end of video

            timestamp_sec = frame_number / fps

            if frame_number % frame_skip == 0:
                # ── Inference frame: run YOLOv8 ──────────────────────────
                frame_data = process_single_frame(frame, model, frame_number, timestamp_sec, fps)
                last_frame = frame_data["annotated_frame"]
                frames_inferred += 1
                
                if writer:
                    writer.write(last_frame)
                
                yield frame_data

            else:
                # ── Skipped frame: write last annotated frame to video ────
                # (keeps output video at correct speed without re-running YOLO)
                if writer and last_frame is not None:
                    writer.write(last_frame)

            frame_number += 1
            if frame_number % 100 == 0:
                print(f"[detection] {frame_number}/{total_frames} frames read  "
                      f"({frames_inferred} inferred)")

    finally:
        cap.release()
        if writer:
            writer.release()
        print(f"[detection] Done. {frame_number} frames read, {frames_inferred} inferred.")


# ---------------------------------------------------------------------------
# Standalone test -- run:  python detection.py --video my_clip.mp4
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Test YOLOv8 detection")
    ap.add_argument("--video",      required=True, help="Path to input video")
    ap.add_argument("--frame_skip", type=int, default=FRAME_SKIP,
                    help=f"Process every Nth frame (default: {FRAME_SKIP})")
    args = ap.parse_args()

    model       = load_model()
    frame_count = 0
    total_dets  = 0

    for fd in run_detection(args.video, model=model, save_output=True,
                            frame_skip=args.frame_skip):
        frame_count += 1
        total_dets  += len(fd["detections"])

        # Show first 5 processed frames for a quick sanity-check
        if frame_count <= 5:
            print(f"  Frame {fd['frame_number']:>4}  "
                  f"{len(fd['detections'])} dets  "
                  f"@ {fd['timestamp_sec']:.2f}s")
            for d in fd["detections"]:
                print(f"    {d['class_name']:12} conf={d['confidence']:.2f}  box={d['box']}")

    print(f"\n[test] Finished. processed_frames={frame_count}  total_detections={total_dets}")
    print("[test] Check output/annotated_output.mp4 to verify visually.")
