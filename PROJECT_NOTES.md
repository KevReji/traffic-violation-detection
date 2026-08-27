# CURRENT STATE (As of 2026-08-27)

> **READ THIS FIRST at the start of every new session.**

---

## Fully Working & Tested

| Module | Status | Notes |
|--------|--------|-------|
| `detection.py` | ✅ Working | YOLOv8n/s/m selectable, ByteTrack persistent tracking, frame-skip (default 3), two-tier confidence (`CONF_THRESHOLD=0.4`, `REVIEW_CONF_THRESHOLD=0.15`), yields both `original_frame` (clean) and `annotated_frame` |
| `violations.py` | ✅ Working | triple_riding, illegal_parking, wrong_way + **helmet detection (LIVE — not placeholder)**. `detect_helmet_violation()` crops each rider and runs the selected fine-tuned model. Class matching handles `With Helmet` / `Without Helmet` labels. `HELMET_CONF_THRESHOLD=0.50`, `DEBUG_HELMET=False`. |
| `confidence.py` | ✅ Working | Reusable `evaluate_confidence()` wired into all 4 violation types |
| `database.py` | ✅ Working | SQLite with `review_needed` + `review_reason` columns; safe migration via `ALTER TABLE` |
| `anpr.py` | ✅ Working (best-effort) | Plate crop from within vehicle bbox (bottom 35%, centre 60%), EasyOCR, fed clean unannotated frames with 20% padding |
| `report.py` | ✅ Working | PDF (ReportLab) + CSV report generation |
| `app.py` | ✅ Working | Wide-layout dashboard — sidebar has **two independent model dropdowns**: Vehicle Detection Model (n/s/m) and Helmet Detection Model (n/s, default s). Completion summary shows both. |
| `style.css` | ✅ Working | Isolated dark-mode CSS; injected at runtime |
| `models/helmet_yolov8n_v1_map74.pt.pt` | ✅ Available | Fine-tuned helmet model — YOLOv8n. mAP50: 0.746, Without-Helmet AP: 0.622. Classes: `{0: 'With Helmet', 1: 'Without Helmet'}` |
| `models/helmet_yolov8s_v1_map74.pt` | ✅ Available | Fine-tuned helmet model — YOLOv8s. mAP50: 0.755, Without-Helmet AP: 0.649. **Default selection in UI.** |

## Recent UI / Architecture Work

- **Wide-layout dashboard**: `st.set_page_config(layout="wide")`, all controls moved to `st.sidebar` (model selector, wrong-way toggle, video uploader).
- **Isolated styling**: All CSS moved to `style.css` and injected via `st.markdown`. Backend Python contains zero styling code. Dark-mode command-center theme with neon cyan/magenta accents, styled metric cards, badge pill classes, animated blinking LIVE indicator.
- **Live CCTV preview**: During processing, every inferred frame is converted BGR→RGB and pushed to an `st.empty()` placeholder wrapped in a `.cctv-feed` div (styled border + LIVE badge). Cleared after processing ends.
- **Persistent results / state-bug fix**: The results section (metrics, tabs, downloads, evidence) lives **outside** the `if run_btn:` block and queries the DB on every Streamlit rerun. Clicking a download button no longer wipes the screen.
- **3-tab results panel**: "📋 Database & Reports", "🖼️ Confirmed Evidence" (green badges, 4-column grid), "🔍 Review Queue" (amber badges, review_reason shown per image).
- **Evidence crops**: 20% padded, taken from the clean `original_frame` — no YOLO label text burned in. ANPR also uses the clean frame.

## Known Limitations

### Helmet Detection
Two fine-tuned models available in `models/`. Both wired in and selectable via UI.
- YOLOv8n: mAP50 0.746, Without-Helmet AP 0.622
- YOLOv8s: mAP50 0.755, Without-Helmet AP 0.649 ← default
- `HELMET_CONF_THRESHOLD = 0.50` — tune up if too many false positives, down if missing real violations
- `DEBUG_HELMET = False` in `violations.py` — set True to print per-rider inference output

### Wrong-Way Detection — Three Documented Failure Modes
1. **Fisheye / wide-angle lens distortion** — barrel distortion causes bounding boxes to appear to grow even for stationary or receding vehicles. Toggle is OFF by default in the UI for this reason.
2. **Small / unstable tracking on distant objects** — ByteTrack drops tracks after 1–3 frames on small CCTV detections; the 15-frame history window is never filled. The review-bypass path (MIN_REVIEW_TRACKING_FRAMES=3) partially mitigates this.
3. **Dense traffic + moving camera (dashcam)** — nearly all nearby vehicles appear to "approach" simultaneously, producing many simultaneous flags. Best suited to sparse, single-lane scenarios.

> **Toggle verification (confirmed functional, not cosmetic):** When `enable_wrong_way=False`, the entire `if enable_wrong_way:` block in `check_violations()` is skipped — `_track_history` is **never written to**. Tested programmatically: 5 frames with enabled=True → 5 history entries; same 5 frames with enabled=False → 0 history entries. ✅

### ANPR
Best-effort OCR. Frequently returns no result on blurry, angled, or very small plates. This is expected behaviour, not a bug.

### Illegal Parking Zones
`RESTRICTED_ZONES = []` by default. Must be set to real pixel coordinates for the specific video/camera angle before `illegal_parking` fires meaningfully.

---

## IMMEDIATE NEXT TASK

**Test helmet detection on real motorcycle footage:**
1. Run the app on a video with riders with and without helmets.
2. Enable `DEBUG_HELMET = True` in `violations.py` to see per-rider model output.
3. If confidence is too low (missing real violations), lower `HELMET_CONF_THRESHOLD` (try 0.35).
4. If false positives fire, raise `HELMET_CONF_THRESHOLD` (try 0.65).
5. Confirm `review_needed` correctly fires for low-confidence helmet detections.
6. Update PROJECT_NOTES.md with tuning results and commit.

---

## Deprioritized / Optional Future Work
*(Do NOT attempt before helmet integration is complete)*
- FastAPI + React full rewrite
- `calibrate_zone.py` polygon-drawing tool for parking zones
- Plotly analytics charts in the dashboard
- Dummy data seeding script for demo/testing
- Per-video RESTRICTED_ZONES UI configurator

---


---

﻿# PROJECT NOTES — AI Traffic Violation Detection System

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
**Status:** COMPLETE
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

## NEXT: MILESTONE 2 -- violations.py (full integration test)

---

### MILESTONE 2 -- violations.py + database.py integration
**Status:** COMPLETE
**Date:** 2026-08-25
**What was tested:**
- 10 synthetic frames, frame 5 has 3 persons on motorcycle
- check_violations() correctly fires triple_riding on frame 5 only
- insert_violation() stores the record, evidence image saved to evidence/
- get_all_violations() retrieves row correctly
- All assertions pass

**What to test:**
- Run detection.py on a real traffic video
- Pipe frame_data into check_violations() each frame
- Insert every violation into SQLite via insert_violation()
- Verify rows appear in DB
- Triple riding logic already verified in isolation (PASS)

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
| FRAME_SKIP               | detection.py           | 3                |
| Enable Wrong-Way Detection | app.py UI checkbox   | True (enabled)   |

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

### MILESTONE 3 -- report.py (PDF + CSV)
**Status:** COMPLETE
**Date:** 2026-08-25
**What was tested:**
- generate_reports() called with 1 violation in DB
- CSV saved to output/violations_report.csv -- headers + data row correct
- PDF saved to output/violations_report.pdf -- 4.3 KB, builds without errors

**Bug fixed:**
- ReportLab v5.0 removed the Small stylesheet style -- replaced with Normal

---

### MILESTONE 4 -- anpr.py (plate crop + OCR)
**Status:** PENDING (needs real vehicle image to test EasyOCR properly)

### MILESTONE 5 -- app.py (Streamlit full integration)
**Status:** PENDING

---

---

## Bug Log

### BUG-001: ANPR cropped from wrong region (FIXED)
**Found:** 2026-08-26
**Symptom:** detect_and_read_plate() was described as cropping from the bottom 35%
of the vehicle box, but the standalone test defaulted the vehicle box to the entire
frame -- meaning for any scene where the vehicle is not the whole image, the plate
crop would be taken from the bottom of the FRAME, not the bottom of the VEHICLE.

**Root cause:** The crop logic itself was relative to vehicle_box (correct), but:
1. The standalone test passed (0, 0, w, h) as the box -- so it worked fine for
   tightly-cropped vehicle photos but silently wrong for full scene images.
2. There was no horizontal centering -- it used the full vehicle width even though
   plates only occupy ~60% of the vehicle width horizontally.

**Fix applied (anpr.py):**
- Vertical : crop bottom 35% of vehicle box height (unchanged, but now explicit)
- Horizontal: crop centre 60% of vehicle box width (20% margin each side) -- NEW
- Standalone test now accepts --box X1 Y1 X2 Y2 so you can simulate real detections
- Debug overlay saved to evidence/anpr_debug_9999.jpg for visual verification
- Safety fallback: if margins collapse the box (tiny vehicle), revert to full width

**Test result:**
  python anpr.py --image test_scene.jpg --box 200 150 700 500
  plate_text: AP2? AN 0074   (synthetic "AP29 AN 0074" -- 9 OCR-d as ? on rendered font)
  Crop geometry check: PASS (predicted region fully contains drawn plate)
  EasyOCR model: downloaded on first run, cached after

---

### BUG-002: Triple-riding not detected on real video (UNDER INVESTIGATION)
**Found:** 2026-08-26
**Symptom:** 240 frames of real motorcycle-with-3-riders video processed, 0 violations detected.

**Debug tooling added (violations.py):**
Set DEBUG_TRIPLE_RIDING = True in violations.py to get per-frame output like:

  [DBG TR] Frame   42 @1.68s | moto conf=0.76 box=(120,180,310,400) | 2 person(s) in frame | 1 associated (need 3)
             person[0] conf=0.81  IoU=0.312  -> ASSOC  box=(130,190,250,395)
             person[1] conf=0.44  IoU=0.003  -> miss   box=(320,180,420,400)

This tells you IMMEDIATELY whether it is:
  (a) Detection problem: YOLOv8 sees fewer than 3 persons in frame
  (b) Logic problem: 3 persons detected but IoU too low to associate

**Fixes already applied proactively:**
- PERSON_MOTO_IOU_THRESHOLD lowered from 0.15 -> 0.10
  (3-person motorcycle boxes often have partial overlap not full overlap)
- If debug shows IoU still too low, try 0.05

**How to investigate your video:**
1. In violations.py, set DEBUG_TRIPLE_RIDING = True
2. Run: python detection.py --video your_video.mp4 --frame_skip 1
   (pipe violations logic inline, or add a quick wrapper script)
3. Look at a handful of frames where the 3 persons are clearly visible
4. Check: are person confs above 0.40? Are IoU values > 0.10?
5. If person confs are low (e.g. 0.38-0.42) -> lower CONF_THRESHOLD in detection.py
   If IoU values are low (e.g. 0.03-0.08) -> lower PERSON_MOTO_IOU_THRESHOLD further

---

### FEATURE: Frame-skipping added to detection.py
**Date:** 2026-08-26
**Change:** run_detection() now accepts frame_skip parameter (default=3).
- Every Nth frame runs YOLOv8 inference
- Skipped frames are still written to annotated output video (last annotated frame
  re-used), so output video plays at original speed without judder
- Also exposed as --frame_skip CLI arg in standalone test
- Speedup: ~3x on CPU for default frame_skip=3
- Set frame_skip=1 for maximum accuracy on short/fast events

**Configuration reference update:**

| Setting        | Where          | Default |
|----------------|----------------|---------|
| FRAME_SKIP     | detection.py   | 3       |

**Test result:**
  python detection.py --video test_clip.mp4 --frame_skip 3
  -> 30 frames read, 10 inferred (frames 0,3,6,9,...) -- PASS

---

### BUG-003: Spamming repeated violations (FIXED)
**Found:** 2026-08-26
**Symptom:** Triple-riding (and other continuous) violations were being logged every single frame they appeared, resulting in 28+ separate violation records for a 4-second clip of the same event.

**Fix applied (violations.py):**
- Added deduplication/cooldown logic per violation type.
- Added COOLDOWN_SECONDS = 5.0 to the configuration constants at the top of the file.
- _last_logged_time dict now tracks the timestamp of the last logged event for each violation type independently.
- check_violations() now enforces this cooldown using the can_log(v_type) helper, preventing the database from being spammed.

**Test result:**
- Synthetic frame feed confirmed it fires on frame 1, skips frames for the next 5 seconds, and fires exactly once again after the cooldown expires.

---

### FEATURE: Wrong-Way Driving Detection
**Date:** 2026-08-26
**Change:** Switched from per-frame detection to persistent tracking and added a wrong-way driving heuristic based on bounding box growth.
- **Tracking**: `detection.py` now uses `model.track(..., persist=True, tracker="bytetrack.yaml")` to assign consistent `track_id`s to vehicles across frames.
- **Rule added**: `check_wrong_way()` added to `violations.py` (inline). It maintains a sliding history window (`WRONG_WAY_HISTORY_FRAMES = 15`) of the vehicle's bounding box area.
- **Heuristic**: If the bounding box area grows by a threshold (`WRONG_WAY_SIZE_GROWTH_THRESHOLD = 1.4x`) over the history window, it is flagged as "wrong_way".
  - *Note & Limitations*: This is a simplified heuristic using size-growth as a proxy for "approaching the camera". It is suitable for a single forward-facing dashcam or CCTV on a one-way path where vehicles should only be moving *away* from the camera (shrinking box).
- **Deduplication**: Cooldown applies per `track_id` specifically for this rule, meaning multiple different wrong-way vehicles can each trigger a violation once.
- **Testing**: Confirmed on `test_videos/dashcam_test.mp4` with debug logs showing track IDs growing (e.g., track_id 44, ratio > 1.42) and successfully logging violations.

---

### FEATURE: Generic Confidence/Review System (Foundational)
**Date:** 2026-08-26
**Change:** Built a reusable confidence-evaluation layer (confidence.py) to systematically flag marginal violations for human review.
- **Layer:** confidence.py exports evaluate_confidence(), a single pure function to classify a detection as confirmed or 
eview_needed.
- **Thresholds (Configurable):**
  - LOW_CONFIDENCE_THRESHOLD = 0.5 (if YOLO confidence drops below this)
  - MIN_OBJECT_AREA_RATIO = 0.01 (if object box area / frame area drops below this, i.e., too small/distant)
  - TRACKING_STABILITY_MIN_FRAMES = 5 (if a tracking ID survives fewer than 5 frames)
- **Database updates:** database.py modified to support two new columns in the iolations table: 
eview_needed (BOOLEAN DEFAULT 0) and 
eview_reason (TEXT). It also contains a safe migration script to upgrade existing databases seamlessly.
- **Status:** Unit tested in isolation. *Not yet wired into specific violation types* (helmet, triple_riding, etc.) -- this acts as the generic engine ready for the next integration step.

---

### FEATURE: Two-Tier Confidence & Review Bypass Logic
**Date:** 2026-08-26
**Change:** Updated detection.py and iolations.py to route borderline/weak detections to the review pipeline rather than silently dropping them.
- **detection.py (Two-Tier Threshold):** Introduced a second threshold REVIEW_CONF_THRESHOLD = 0.15 (down from the strict CONF_THRESHOLD = 0.4). Detections in this borderline window are now kept but tagged with "low_confidence_detection": True.
- **iolations.py (Bypass Paths):** The rule engine now evaluates two paths for each violation:
  1. *Strict Path:* The standard rules (e.g. 15 frames tracking, 10s parking, >0.4 confidence). This triggers a standard 
eview_needed=False (or True if it fails generic evaluations like being too small).
  2. *Review Path:* If a detection is marked "low_confidence_detection": True, or if tracking history is too short but at least 3 frames (MIN_REVIEW_TRACKING_FRAMES = 3), the violation is explicitly allowed to fire but is **forced** to 
eview_needed=True with reasons like "low_confidence_detection" or "insufficient_tracking_history".
- **Result:** Successfully tested on cctv_wrongway_test.mp4. Vehicles that were previously completely lost due to tracking instability now fire and are correctly routed to the database tagged with "insufficient_tracking_history", without polluting the strict automated enforcement data.

---

### FIX + FEATURE: App.py Model Mismatch Bug + Model Selector Dropdown
**Date:** 2026-08-26
**Issue:** pp.py was silently defaulting to yolov8n.pt, overriding the yolov8s.pt testing configuration we used to validate the CCTV logic. Additionally, the SQL statement in database.py's insert_violation() had not been successfully updated to store the new 
eview_needed and 
eview_reason flags due to a string-replacement bug, causing them to silently fail to log to the DB even when flagged correctly by the engine.
**Resolution:**
- **App.py Model Selector UI:** Added a st.selectbox right above the 'Run Detection' button allowing the user to select from YOLOv8n (Fast), YOLOv8s (Balanced) (New Default), and YOLOv8m (Accurate, Slower).
- **Pipeline Integration:** pp.py now maps the UI choice to the correct .pt file and passes it directly to detection.py's load_model(). The status text output also now explicitly prints which model was used in the final summary (e.g. Processed using YOLOv8s (Balanced)).
- **Database Insert Fix:** Patched the underlying SQL INSERT INTO violations query in database.py so the 
eview_needed and 
eview_reason columns are correctly populated in the database.
- **Verification:** Ran a full end-to-end simulated run on cctv_wrongway_test.mp4. Confirmed the SQL DB now successfully captures row items matching {'review_needed': 1, 'review_reason': 'insufficient_tracking_history'} exactly as expected.

---

### BUG FIX: Evidence Cropping Logic
**Date:** 2026-08-26
**Issue:** pp.py and npr.py were cropping evidence images and license plates directly from the nnotated_frame. This meant YOLO bounding boxes and class-name text were permanently burned into the evidence images, obscuring the vehicles and actively interfering with ANPR OCR. Furthermore, the crops were razor-tight, removing visual context.
**Resolution:**
- **Original Frame Passthrough:** Modified detection.py to copy the frame *before* any OpenCV drawing functions occur, and yield it as original_frame alongside nnotated_frame.
- **Padded Cropping:** Updated utils.py crop_region() to accept a padding_pct argument (defaulting to 0.0 but set to 0.20 when called). It expands the bounding box by 20% on all sides before cropping, clamping safely to the video bounds.
- **App Update:** Updated pp.py to pass rame_data["original_frame"] to both the evidence image crop (with padding_pct=0.20) and the detect_and_read_plate ANPR call.
- **Result:** Evidence images are now completely clean (no UI overlays) and provide 20% extra padding for clear context. Number plate OCR is no longer fed YOLO text labels.

---

### MILESTONE 6: Helmet Detection v2 & Image Uploads
**Date:** 2026-08-27
**Status:** COMPLETE
**Summary:**
- **Model Upgraded:** Retrained helmet model on motorcycle-specific dataset (helmet-and-no-helmet-rider-detection v6), producing helmet_yolov8s_v2_motorcycle.pt. Validation mAP50: With Helmet 0.896, Without Helmet 0.754 (a clear improvement over v1's 0.649).
- **Two-Tier Confidence:** Fixed bug where a flat HELMET_CONF_THRESHOLD bypassed the review queue. Wired detect_helmet_violation() into the shared two-tier logic (>= 0.4 confirmed, 0.15-0.4 review, < 0.15 discarded).
- **Per-Rider Cooldown:** Fixed bug where the global "helmet" cooldown in can_log() blocked multiple riders in the same frame from being flagged. Fixed by passing a per-rider entity_id (track_id or bounding box).
- **Class Filtering:** Validated the new "licence" class from the v2 model is explicitly ignored and safely drops out before hitting ANPR.
- **Image Uploads & Compression Observation:** Added single image upload support (jpg/png) to pp.py, cleanly reusing the per-frame pipeline (as frame 0). Diagnostic finding: Video compression measurably degrades helmet detection confidence (e.g. 0.72 on a clean image drops to 0.20-0.36 on compressed video of the same rider). This validates the need for the review queue.
- **Person Detection Bottleneck:** Helmet coverage is bound by upstream person-detection recall. Switching from YOLOv8n to YOLOv8m (vehicle model) doubled detected violations on the same image. Strongly recommended to default to YOLOv8s/m over YOLOv8n for vehicle detection.

---

### BUG FIX: Live Preview Helmet Annotation
**Date:** 2026-08-27
**Issue:** The live video preview did not draw helmet detection boxes/labels because the helmet model operated on a cropped sub-image, returning crop-local coordinates. Furthermore, check_violations() was running *after* pp.py displayed the frame, preventing any drawn boxes from appearing.
**Resolution:**
1. Modified detect_helmet_violation() to return the raw crop_box coordinates and the crop_offset (x1, y1 of the rider crop).
2. Inside check_violations(), translated the crop-local box back to full-frame coordinates and drew it directly onto rame_data["annotated_frame"] using a distinct orange color ((0, 165, 255)).
3. In pp.py, reordered the execution pipeline so check_violations() runs *before* live_preview.image(). The RGB conversion for the display is now recalculated post-violations, ensuring the helmet boxes are visible to the user live.
**Status:** FIXED. No structural overhaul was needed.

---

### NEXT SESSION
**Date:** 2026-08-27
**Notes:** Helmet detection is fully integrated (logic, Review Queue UI, and live annotation rendering). We are ready to move on to the remaining Future Enhancements (React rewrite, analytics charts, dummy data seeder, etc.) or refine existing models as needed.
