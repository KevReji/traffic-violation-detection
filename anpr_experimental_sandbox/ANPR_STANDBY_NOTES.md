# ANPR & License Plate Detection — Standby & Architecture Notes

**Status:** Safely Archived for Demo / Presentation Standby  
**Date:** 2026-10-14  
**Sandbox Location:** `anpr_experimental_sandbox/`

---

## 1. Current Pipeline Decision: Two-Stage Detector Architecture

Instead of running a single YOLO plate detector across a full 1080p frame, the system has adopted a **Two-Stage Detection Pipeline**:

```
[Full CCTV / Dashcam Frame]
           │
           ▼
Stage 1: Vehicle Detection (YOLOv8n)
  - Classes: Car (2), Motorcycle (3), Bus (5), Truck (7)
  - Add 5% safety padding around vehicle bounding box
           │
           ▼
[High-Resolution Vehicle Crop]
           │
           ▼
Stage 2: License Plate Detection (Custom YOLO Weights in weights/)
  - Evaluates only the isolated vehicle crop
  - Re-scales vehicle crop to 640x640, massively boosting plate pixel density
  - Filters out false positives with Aspect Ratio gate (1.2 <= AR <= 5.0)
           │
           ▼
[Isolated Plate Crop] ───► Global Coordinate Remapping (to full frame)
           │
           ▼
Stage 3: OCR Engine (PaddleOCR / Preprocessed EasyOCR)
```

---

## 2. Key Discoveries, Blockers & Diagnostic Learnings

### A. The "Resolution Squish" Factor
* When a full 1920x1080 traffic image is fed into a single-stage YOLO model, it is downsampled to 640x640.
* A distant motorcycle license plate that was 40x20 pixels shrinks down to ~8x4 blurry pixels, making plate detection and OCR mathematically impossible.
* **Solution Verified:** Cropping the vehicle first forces the 640x640 input tensor to focus 100% of its resolution on the vehicle, multiplying effective plate resolution by 3x–6x.

### B. Indian Motorcycle Plate Geometry (Curved Mudguards & Stickers)
* Standard open-source license plate models are heavily trained on flat, rectangular car bumper plates.
* Indian motorcycle plates are frequently:
  * Stickers applied directly onto curved front/rear mudguards.
  * Tilted or mounted on narrow mudflap brackets.
  * Double-line vertical formats rather than standard horizontal rectangles.
* This causes lower raw confidence scores (`0.15`–`0.28`), requiring slightly relaxed detector thresholds (`conf=0.18`–`0.20`) rather than default `0.40+`.

### C. False Positive "Barcode" Hallucinations & The Aspect Ratio Fix
* Plate detectors frequently hallucinated plates on motorcycle engine ribs, tire treads, and sandals (rider's feet) due to alternating high-contrast stripes mimicking text.
* **Solution Verified:** Added an **Aspect Ratio Filter** (`1.2 <= AR <= 5.0`). Because sandals and tire patches are roughly square (`AR ≈ 0.9`–`1.1`), this filter eliminated 100% of false positives across the test dataset.

### D. Model Evaluation Matrix
Across 36 extracted vehicle crops from the test dataset:
* **`license_plate_detector1.pt`:** Detected 13 plates (High recall on motorcycle crops).
* **`license_plate_detector2.pt`:** Detected 8 plates.
* **`license_plate_detector3.pt`:** Detected 13 plates.

---

## 3. Directory Layout Inside Sandbox

```
anpr_experimental_sandbox/
├── ANPR_STANDBY_NOTES.md       # This reference document
├── test_two_stage_batch.py     # Standalone two-stage pipeline script
├── test_easyocr.py             # Preprocessing & EasyOCR experimental script
├── batch_test_yolo.py          # Batch detection runner
├── benchmark_models.py         # Multi-model evaluation & comparison matrix
├── weights/                    # Isolated plate detector model weights
│   ├── license_plate_detector1.pt
│   ├── license_plate_detector2.pt
│   └── license_plate_detector3.pt
└── debug_results/              # All evaluation outputs & saved crops
    ├── two_stage/              # Padded vehicle crops, plate crops, annotated frames
    ├── license_plate_detector1/
    ├── license_plate_detector2/
    └── license_plate_detector3/
```

---

## 4. How to Resume Work After the Presentation

When ready to resume ANPR work:

### Step 1: Install PaddleOCR
PaddleOCR provides significantly better small-text and angled-text recognition on Indian plates than raw EasyOCR:
```bash
pip install paddlepaddle paddleocr
```

### Step 2: Run Two-Stage Pipeline
The script `test_two_stage_batch.py` is configured with:
* Vehicle detection threshold: `0.25`
* Plate detection threshold: `0.18` (matches `license_plate_detector1.pt` sweet spot)
* Aspect ratio gate: `1.2` to `5.0`

Run from the project root:
```bash
python anpr_experimental_sandbox/test_two_stage_batch.py
```
*(Note: If running directly from inside `anpr_experimental_sandbox/`, update the relative weight path to `weights/license_plate_detector1.pt`).*

### Step 3: Wire OCR to Plate Crops
1. Connect `PaddleOCR(use_angle_cls=True, lang='en')` to process the cropped plates from `debug_results/two_stage/`.
2. Apply string cleanup regex (`^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$` or standard state code filters like `MH`, `DL`, `KA`, `TN`, `KL`, `AP`, `TS`).
3. Once fully verified, integrate the two-stage logic into `anpr.py` and replace the demo `PLATE_LOOKUP` in `app.py`.
