# PROJECT NOTES — AI Traffic Violation Detection System

> **READ THIS FIRST at the start of every session.**
> This file is the single source of truth for what is built, what works, and what is next.

---

## Project Overview

Final-year student project. Detects traffic violations from uploaded CCTV/dashcam video using YOLOv8 and OpenCV. Three violation types:
1. **Helmet Violation** -- motorcycle rider without helmet (placeholder hook for custom model)
2. **Triple Riding** -- 3+ persons on one motorcycle in a single frame
3. **Illegal Parking** -- vehicle stationary inside a restricted zone for > X seconds (configurable)

Full pipeline: upload video -> detect objects -> apply rules -> crop evidence -> detect plate -> OCR plate -> store in SQLite -> generate PDF/CSV report -> display in Streamlit.

---

## Tech Stack

| Component        | Library/Tool                              |
|------------------|-------------------------------------------|
| Object Detection | ultralytics (YOLOv8)                      |
| Video Processing | OpenCV (cv2)                              |
| Plate OCR        | EasyOCR                                   |
| Database         | SQLite3 (built-in Python)                 |
| UI               | Streamlit                                 |
| Data             | pandas                                    |
| PDF Report       | reportlab                                 |
| CSV Report       | pandas (.to_csv)                          |

---

## Project Structure

```
traffic-violation-detection/
|-- app.py            # Streamlit UI
|-- detection.py      # YOLOv8 detection loop, frame annotation
|-- violations.py     # Violation rules (helmet, triple riding, illegal parking)
|-- anpr.py           # Plate crop + EasyOCR
|-- database.py       # SQLite schema + insert/query helpers
|-- report.py         # PDF + CSV report generation
|-- utils.py          # Shared helpers (IoU, zone check, image crop, etc.)
|-- evidence/         # Auto-created: cropped violation + plate images
|-- output/           # Auto-created: annotated output video
|-- requirements.txt  # All pip dependencies
+-- PROJECT_NOTES.md  # This file
```

---

## Build Log

### MILESTONE 1 -- Project scaffold + detection.py
**Status:** IN PROGRESS
**Date:** 2026-08-25
**What is built:**
- Full folder structure created
- requirements.txt written
- utils.py -- shared helpers: IoU calculation, zone overlap, image crop, directory setup
- detection.py -- YOLOv8 detection loop; processes video frame by frame, draws bounding boxes, writes annotated output video, yields per-frame detection results for downstream modules

**What is NOT built yet:**
- violations.py, anpr.py, database.py, report.py, app.py

**Key decisions:**
- Using YOLOv8n (nano) by default for speed; configurable via MODEL_PATH constant
- Detections filtered to: person, car, motorcycle, bus, truck (COCO class IDs 0, 2, 3, 5, 7)
- detect_helmet_violation() is a PLACEHOLDER in violations.py -- returns False always until student plugs in their own model
- Illegal parking zone is defined as a list of (x1, y1, x2, y2) rectangles in pixel space -- configurable in violations.py
- Evidence images saved to /evidence/, named {violation_type}_{frame}_{timestamp}.jpg
- Output video saved to /output/

**Known issues / watch out:**
- EasyOCR downloads ~100 MB model on first run (normal)
- YOLOv8 downloads weights on first run if not cached (normal)
- Indian number plates: OCR accuracy is best-effort, not guaranteed

---

## NEXT: MILESTONE 2 -- violations.py (triple riding first)

---

## Configuration Reference

| Setting                  | Where to change        | Default          |
|--------------------------|------------------------|------------------|
| YOLO model               | detection.py           | yolov8n.pt       |
| Detection confidence     | detection.py           | 0.4              |
| Illegal parking timeout  | violations.py          | 5 seconds        |
| Restricted zone rects    | violations.py          | [] (empty list)  |
| Evidence folder          | utils.py               | ./evidence/      |
| Output video folder      | utils.py               | ./output/        |
| DB path                  | database.py            | violations.db    |

---

## How to Run (once complete)

```bash
pip install -r requirements.txt
streamlit run app.py
```

---

## Notes for Future Sessions

- Always check this file first.
- Git history has one commit per milestone -- use `git log --oneline` to see progress.
- detect_helmet_violation() in violations.py is intentionally a stub -- do NOT fill it in without the student custom model.
