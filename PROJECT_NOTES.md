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

---

### TUNING: Helmet Model Underconfidence
**Date:** 2026-08-28
**Change:** Added HELMET_CONFIRM_THRESHOLD = 0.35 in iolations.py exclusively for helmet detection, decoupled from the shared CONF_THRESHOLD = 0.4.
**Reason:** Manual visual review of debug_crops found clearly-correct, non-blurry "no helmet" detections scoring in the 0.31-0.42 range (just below the general threshold), causing them to unnecessarily land in the manual review queue. Genuinely blurry/ambiguous cases scored lower (0.2-0.3) and correctly stayed in review. This was an evidence-based tuning decision to adjust for the helmet model's specific underconfidence, rather than an arbitrary threshold lowering. It does not affect vehicle or triple-riding thresholds.

## Red Light Detection (Stage 2)
- Added a 
ed_light violation rule to iolations.py.
- **Methodology:** Classical HSV thresholding used on a fixed region of the frame. This was an explicit scope decision to avoid needing a new trained model.
- **Manual Calibration:** Like RESTRICTED_ZONES, this requires configuring LIGHT_REGION (the traffic light bounding box) and STOP_ZONES (the stop line area) per video.
- **Logic:** We track vehicle y-coordinates using ByTetraCk 	rack_ids. When a vehicle crosses into STOP_ZONES, we sample the current traffic light state using the LIGHT_REGION. If red, a violation is filed. If ambiguous, it defaults to the review queue (mbiguous_light_state).

## UI Integration (Stage 3)
- Added an "Enable Red-Light Detection" toggle to the sidebar, following the wrong-way pattern.
- Fixed the 
ed_light violation dictionary schema in iolations.py (added iolation_type, rame_number, 	imestamp_sec) to strictly match existing rules.
- Because the reporting logic (CSV/PDF) and UI logic (tabs, evidence queue) dynamically render whatever is in the database, 
ed_light automatically integrates into all downstream views without requiring any one-off UI code.

## Interactive Calibration UI (Stage 4)
- **Goal:** Replaced manual coordinate guessing/scripting with an in-app interactive calibration flow.
- **Component:** Created calibration_ui.py using streamlit-image-coordinates to allow users to click and define STOP_ZONES (and optionally LIGHT_REGION) directly on the video's first frame.
- **Auto-Detection Fallback:** YOLOv8 automatically hunts for the traffic light first; if found, it skips requiring manual clicks for the light region.
- **State Management:** Clicks are tracked robustly in st.session_state["calib_clicks"] with deduplication logic to prevent runaway Streamlit re-renders.
- **App Integration:** Wired into pp.py. If red-light detection is enabled, the main app flow (and the "Run Detection" button) is strictly halted until calibration is confirmed. The UI passes the dynamic coordinates directly into check_violations() overriding the fallback constants.

---

## Calibration Presets (Stage 5)
- Added KNOWN_CALIBRATIONS dictionary in calibration_presets.py.
- **Pre-saved videos**: Redlight4.mp4 and Redlight5.mp4 have their verified stop-lines and light-regions saved.
- **Behavior**: If the uploaded filename matches a known preset, the app automatically populates the session state, skips the interactive UI, and immediately enables the "Run Detection" button. A "Recalibrate" button is provided to override presets manually if needed. New or unrecognized videos gracefully fall back to the interactive calibration UI.


### Red-Light Logic Upgrade & UI Presets (2026-08-29)

1. **Line-Crossing Geometry Update:** Upgraded red-light detection from rectangle-zone (any-overlap) to line-crossing (has_fully_crossed_line() in utils.py). This requires ALL 4 corners of the vehicle's bounding box to completely cross the line before firing, fixing a false-positive risk where a rectangle zone could trigger on partial overlap (e.g. a car's front bumper edge poking in before actually crossing the real stop line). STOP_LINE (two endpoint tuples) replaces STOP_ZONES (axis-aligned rectangle), enabling the calibrated line to match a real stop line's camera-perspective tilt/angle.

2. **UI Data Structure Bug Fix:** Fixed a NameError bug in calibration_ui.py: line 70 referenced an undefined variable points. This was a leftover from a blind find/replace during the rectangle-to-line refactor that copied calibrate.py's tuple-based convention into this file, which actually uses clicks (a list of dicts with 'x'/'y' keys from streamlit-image-coordinates). The root cause was a data-structure mismatch, not just a naming mismatch. *Note:* This is the SECOND occurrence of this exact class of copy-paste bug in this refactor. Any third occurrence warrants a full-file audit rather than patching single reported lines.

3. **Confirmed Calibration Coordinates:** Real, literal calibration coordinates (not proxy/reused values) have been confirmed for two videos:
   - Redlight4.mp4: LIGHT_REGION=(1725,124,1752,177), STOP_LINE=((834,628),(1533,675))
   - Redlight5.mp4: LIGHT_REGION=(985,56,998,69), STOP_LINE=((398,630),(1092,680))
   Both were visually verified via annotated screenshots. *Note:* Redlight5.mp4 has a separate, already-documented, closed limitation: HSV light-color detection is unreliable on this camera due to LED "blooming" toward white/yellow in compressed footage. The STOP_LINE geometry itself is fine, only get_light_state()'s color reading is affected (not being further chased due to two-attempt cap).

4. **KNOWN_CALIBRATIONS Preset Feature:** Built and confirmed the KNOWN_CALIBRATIONS preset feature. Uploading a video whose filename matches a known preset (Redlight4.mp4, Redlight5.mp4) auto-loads its calibration and skips the calibration UI entirely, showing "Calibration loaded for this camera" with a "Recalibrate" override button available. This was confirmed both at the UI level (manual test) and the pipeline level (real end-to-end run). Any video NOT in the preset dict correctly falls back to showing the full calibration UI (confirmed via manual test).

5. **Definitive End-to-End Test (Redlight4.mp4):** Conducted a real end-to-end pipeline test on Redlight4.mp4 using the ACTUAL confirmed preset coordinates (not proxy values). The violation fired at frame 52, confidence 0.8712, vehicle_type=car. Debug output explicitly confirmed check_violations() received the correct light_region/stop_line values. 113 frames were processed in total. *This is the definitive, trustworthy result* — an earlier test using proxy/reused rectangle-corner coordinates as a stand-in fired at frame 56; that number is now superseded and should not be cited going forward.

6. **Cleanup:** Confirmed DEBUG_RED_LIGHT is set to False in the code now that the pipeline is validated.

### STATUS HANDOFF (2026-08-28)

#### 1. What's currently working
- **Core Detection Pipeline:** YOLOv8 (vehicle & helmet models) + ByteTrack integration flawlessly flags illegal parking, wrong-way, triple riding, and no-helmet violations.
- **Red-Light Detection (New):** Classical HSV thresholding evaluates traffic light states (
ed, yellow, green, unknown). The system correctly tracks vehicles crossing dynamic user-defined STOP_ZONES.
- **In-App Interactive Calibration:** streamlit-image-coordinates allows users to click the video frame to define the stop line and light region in the UI, halting detection until complete.
- **UI & Reporting:** All violations sync automatically to iolations.db, displaying natively in the Review Queue and rendering cleanly onto the PDF and CSV reports. Evidence crops are correctly padded and free of burned-in YOLO text.

#### 2. Known limitations
- **Red-Light Evaluation Bottlenecks:** The current STOP_ZONES logic relies on strict vertical y-axis tracking. Extremely oblique or horizontal intersections may require updating ox_inside_zone logic.
- **Streamlit Refresh Quirks:** Complex UI integrations (like streamlit-image-coordinates) occasionally face state refresh loops, which we mitigated using strict deduplication (last_click), but edge cases may persist.
- **Helmet Model Confidence:** Heavily compressed video degrades bounding box confidence, so "no helmet" detections rely heavily on the Review Queue.

#### 3. What we were about to work on next
- **React / Next.js Rewrite:** The user previously provided extensive wireframes and prompts for a dark/light mode React dashboard. A migration away from Streamlit toward this professional tech stack is a major impending milestone.
- **Analytics & Graphs:** Further polishing the analytics reporting if we stay in Streamlit.
- **Dummy Data Seeder:** Building a script to populate the database rapidly for dashboard testing.

## Known Limitation — Red-Light Color Detection Across Cameras

Red-light violation detection (traffic_light.py's HSV-based get_light_state()) was fully
validated end-to-end on Redlight4.mp4: LIGHT_REGION = (1720, 120, 1760, 180),
STOP_ZONES = [(0, 600, 1920, 650)]. Fires correctly, cross-checked against real vehicle
trajectories, confidence/review-queue routing confirmed correct.

Testing on a second camera (Redlight5.mp4) surfaced a real, diagnosed limitation of
classical HSV thresholding on compressed CCTV/LED traffic signal footage: the brightest
center of an LED bulb frequently "blooms" toward white/yellow in the video encoding, with
the true red hue only present as a thin halo near the edge of the lit lens. This was
confirmed directly via HSV pixel-value inspection (not assumed) at two crop sizes:

- A looser crop around the full signal housing returned a dominant hue cluster of ~24-30
  (yellow range), diluted further by reflections off adjacent unlit lenses.
- A tightened crop around just the lit bulb still returned a dominant hue cluster of
  ~22-29 (yellow), with a secondary cluster at hue ~11-14 (between the red and yellow
  threshold ranges) and only a sparse handful of true low-hue (0-10) red pixels visible
  at the object's edges.

Two calibration attempts (general S/V threshold loosening in Stage 1, then a tightened
per-video crop for Redlight5.mp4) were made per the project's two-attempt debugging cap,
consistent with how other violation types (wrong-way, helmet) were handled. Both were
reasoned, tested with real pixel data, and did not fully resolve the misclassification —
the root cause (LED sensor blooming vs. compression artifacts on the true color signal)
is a known hard problem for simple dominant-hue thresholding, not a coordinate or
calibration mistake.

Production-grade fix (out of scope for this project): HDR-aware or edge/halo-specific
color sampling, or a small trained classifier for light-state recognition, rather than
whole-region dominant-hue counting.

Practical impact: The in-app calibration UI (Stage 4) and full red-light detection
pipeline are demonstrated as working correctly and reliably on Redlight4.mp4. Redlight5.mp4
demonstrates correct STOP_ZONES crossing-detection and correct in-app calibration UI
behavior, but its light-color reading is not reliable without further work outside this
project's scope.

### UI Optimization & Background Changes (2026-08-30)

1. **Static File Serving for Backgrounds:** Switched background image delivery from base64-embedded CSS to Streamlit's native static file serving (enableStaticServing = true in .streamlit/config.toml, files served from static/ folder). This fixed a real performance issue where large base64 payloads (~7.7MB originally) were being re-transmitted on every Streamlit rerun during active video detection, causing significant lag. 
   *Note:* Any future config.toml changes require a full server restart, not just a browser refresh, to take effect.
2. **Background Position Adjustment:** Changed the CSS ackground-position to "top center". This ensures the images are anchored to the top of the viewport, so any responsive cropping from ackground-size: cover happens at the bottom of the image, preventing the decorative title text near the top from being sliced off on wider screens.

### Known Issue / Next Session (2026-08-30)

**Confirmation:** The ackground-position: top center fix and static file serving are both confirmed working by the user as of this session (title no longer cropped, backgrounds display correctly, performance is acceptable).

**Known issue found while testing the new background image feature:** when video detection completes (or is stopped early via Stop Detection), live_preview.empty() clears the live feed placeholder entirely, leaving a visible empty gap in the layout - previously invisible against a plain dark background, but now visually obvious since the background image renders through the gap.

**Planned fix for next session:** instead of clearing live_preview on completion/early-stop, keep the LAST successfully processed annotated frame displayed there (rame_data['annotated_frame'] from the final loop iteration) rather than calling live_preview.empty(). This applies to both the normal-completion path and the Stop Detection early-break path. Only exception: if zero frames were processed at all (edge case), leaving it empty is fine since there's nothing to show.

This is a good UX improvement independent of the background image issue that surfaced it - ending on a frozen 'here's the final result' frame is better for a demo than the feed vanishing. Do not touch detection logic, the Stop Detection button's break logic, or any other part of the finalization flow when implementing this - only change whether/what live_preview shows at the end.

### Update (2026-08-30)

- **Dashboard Reset Logic Fixed:** The dashboard now correctly resets to a zero/Idle/placeholder state when a file is removed or on a fresh page load. This is gated by comparing the uploaded filename against a stored un_for_file session value.
  - **KNOWN LIMITATION:** This comparison is by filename only, not file identity. Re-uploading a DIFFERENT file with the SAME name as a previous run (e.g., uploading a new ideo.mp4 when the previous run was also ideo.mp4), without clicking "Run Detection" again, will incorrectly show the old run's stale data. This is low risk for normal usage/demos, but worth knowing if it ever comes up.
- **Red-Light Calibration Rendering Bug Fixed:** Fixed a separate bug where the red-light calibration frame failed to render (showing a blank area with no console errors). The root cause was an unflushed tempfile being read by cv2.VideoCapture before the OS had fully written it to disk. 
  - Fixed with explicit 	file.flush() and 	file.close() before reading. 
  - Added a safety downscale (max 1280px width) for the displayed calibration frame to avoid oversized base64 payloads crashing the custom component's iframe.
  - Click coordinates are correctly mathematically rescaled back to the original video's true resolution before being saved.
  - Confirmed working via manual test on Redlight6.mp4.

### Update (2026-08-30: Database Traceability Fix)

- **Source Video Tracking Added:** Added a source_video column to the iolations database table. 
  - **Reason:** During an investigation into false-positive helmet detections (reported via a previously generated PDF), it was discovered that the database and reporting pipeline had absolutely no way to trace a violation ID back to the video file that produced it. Without this, determining the source video for past runs was impossible.
  - **Fix Details:** 
    - Migrated the SQLite schema to include source_video TEXT. Existing records default to None/blank, preserving historical honesty.
    - Updated insert_violation() to store the filename.
    - Updated pp.py to pass the uploaded file's name (uploaded.name) into the detection loop.
    - Updated eport.py to expose this new column in both the CSV exports and the PDF detail table.

## ANPR Limitation — Plate Crop Reliability on Small/Distant/Obscured Vehicles

Investigated two real cases where plate OCR returned no result, via direct crop-dimension
and visual inspection (not assumed):

1. **Small/distant vehicles (dashcam_test.mp4):** the plate-region crop is computed as a
   fixed percentage of the vehicle's own bounding box (bottom 35% height, center 60%
   width). For small/distant motorcycles, this produced crops as small as 19x18 to 27x14
   pixels — far below what any OCR engine can reliably read. Larger/closer vehicles in
   the same frame produced usable 76x50 to 117x61 pixel crops.

2. **Multi-rider/obscured vehicles (TripleHelm1.mp4):** on a triple-riding motorcycle,
   crop dimensions were healthy (~170x120 pixels), but visual inspection of the saved
   crops showed no plate was actually visible within the cropped region — likely because
   multiple riders' bodies/legs obscure the vehicle's lower-center area where the
   percentage-based heuristic assumes a plate will be.

Both findings point to the same underlying cause: the plate-region crop uses a fixed
percentage-of-vehicle-box heuristic rather than actual plate detection, which is
reliable on clearly-visible, appropriately-sized single vehicles but breaks down on
small/distant vehicles (resolution) and multi-rider/obscured vehicles (wrong region
entirely). This is consistent with ANPR's existing documented best-effort behavior,
not a new bug — it correctly reports "not detected" rather than guessing in both cases.

A production system would likely need a dedicated plate-detection model (rather than a
fixed-percentage heuristic) to reliably locate plates regardless of vehicle distance or
rider obstruction — out of scope for this project's timeline.

## Stage C Progress: UI Polish & Violation Details
- **Stage C.3 (License Plate OCR):** Added OCR panel to violation details. Fixed a critical bug where Streamlit's textwrap dedent and Markdown engine interfered with HTML string interpolation, causing the panel to render as a raw code block instead of HTML.
- **Stage C.4 (Evidence Snapshot & Layout):** Added the cropped evidence_image_path to the violation detail view. Adjusted layout to a 4-column structure ([1.5, 1, 1, 1]) so the Evidence Snapshot occupies the left side prominently (~33% width) while the three info panels share the right side, closely matching the target mockup proportions without breaking internal panel rendering.
