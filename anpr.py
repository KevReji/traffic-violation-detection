"""
anpr.py -- Automatic Number Plate Recognition (ANPR).

Strategy:
  1. Crop the lower portion of the vehicle bounding box (plates are usually
     in the bottom 30-40% of the vehicle).
  2. Run EasyOCR on that crop.
  3. Return the best text string and the crop image.

Note: OCR accuracy on Indian plates is best-effort.  The raw text is stored
as-is; the system does not try to validate or correct it.
"""

import cv2
import numpy as np
import os
import easyocr

from utils import ensure_dirs, save_image, EVIDENCE_DIR

# ---------------------------------------------------------------------------
# EasyOCR reader -- initialised lazily on first call to avoid startup cost
# ---------------------------------------------------------------------------
_reader = None

def _get_reader():
    """Return a cached EasyOCR reader (English).  Downloads model on first use."""
    global _reader
    if _reader is None:
        print("[anpr] Initialising EasyOCR (may download model ~100 MB on first run)...")
        _reader = easyocr.Reader(["en"], gpu=False)   # set gpu=True if you have CUDA
        print("[anpr] EasyOCR ready.")
    return _reader


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_and_read_plate(frame, vehicle_box, violation_id):
    """
    Attempt to detect the number plate in a vehicle's bounding box and
    read its text via OCR.

    Parameters
    ----------
    frame        : np.ndarray  -- full BGR video frame
    vehicle_box  : tuple       -- (x1, y1, x2, y2) of the vehicle
    violation_id : int         -- DB row id, used to name saved images

    Returns
    -------
    dict with:
        plate_text       : str or None   -- OCR result (may be empty/wrong)
        plate_image_path : str or None   -- path to saved plate crop image
        plate_crop       : np.ndarray or None -- the crop itself
    """
    ensure_dirs()

    x1, y1, x2, y2 = [int(v) for v in vehicle_box]
    h, w = frame.shape[:2]

    # Clamp to frame bounds
    x1 = max(0, x1); y1 = max(0, y1)
    x2 = min(w, x2); y2 = min(h, y2)

    if x2 <= x1 or y2 <= y1:
        return {"plate_text": None, "plate_image_path": None, "plate_crop": None}

    # ?? Step 1: crop the bottom 35% of the vehicle box ??????????????????
    crop_y1 = y1 + int((y2 - y1) * 0.65)   # 65% down from top
    plate_region = frame[crop_y1:y2, x1:x2].copy()

    if plate_region.size == 0:
        return {"plate_text": None, "plate_image_path": None, "plate_crop": None}

    # ?? Step 2: pre-process to help OCR ?????????????????????????????????
    processed = _preprocess_plate(plate_region)

    # ?? Step 3: run EasyOCR ?????????????????????????????????????????????
    reader  = _get_reader()
    results = reader.readtext(processed, detail=1, paragraph=False)

    # Pick the highest-confidence text segment
    plate_text = None
    if results:
        best = max(results, key=lambda r: r[2])   # r[2] is confidence
        raw_text = best[1].strip().upper()
        if raw_text:
            plate_text = raw_text

    # ?? Step 4: save the plate crop ?????????????????????????????????????
    plate_image_path = None
    if plate_region is not None:
        fname = os.path.join(EVIDENCE_DIR, f"plate_{violation_id:04d}.jpg")
        if save_image(plate_region, fname):
            plate_image_path = fname

    return {
        "plate_text":       plate_text,
        "plate_image_path": plate_image_path,
        "plate_crop":       plate_region,
    }


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _preprocess_plate(img):
    """
    Light pre-processing to improve OCR accuracy.
    Converts to greyscale, applies slight sharpening and threshold.
    """
    # Resize to a fixed height for consistent OCR behaviour
    target_h = 64
    h, w = img.shape[:2]
    if h == 0 or w == 0:
        return img
    scale   = target_h / h
    new_w   = max(1, int(w * scale))
    resized = cv2.resize(img, (new_w, target_h), interpolation=cv2.INTER_CUBIC)

    grey = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

    # Sharpen with a simple kernel
    kernel  = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    sharp   = cv2.filter2D(grey, -1, kernel)

    # Otsu binarisation to get clean black-on-white text
    _, binary = cv2.threshold(sharp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Convert back to BGR so EasyOCR gets a 3-channel image (it also accepts grey)
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)


# ---------------------------------------------------------------------------
# Standalone test -- python anpr.py --image path/to/plate_crop.jpg
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True, help="Path to a cropped vehicle/plate image")
    args = ap.parse_args()

    frame = cv2.imread(args.image)
    if frame is None:
        print("ERROR: cannot read image")
        raise SystemExit(1)

    h, w = frame.shape[:2]
    result = detect_and_read_plate(frame, (0, 0, w, h), violation_id=9999)
    print(f"[test] plate_text       : {result['plate_text']}")
    print(f"[test] plate_image_path : {result['plate_image_path']}")
