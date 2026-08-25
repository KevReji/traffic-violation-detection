"""
anpr.py -- Automatic Number Plate Recognition (ANPR).

Strategy:
  1. Receive the vehicle's bounding box (x1, y1, x2, y2) from YOLOv8 detection.
  2. Crop the plate search region from WITHIN that vehicle box:
       - Vertical  : bottom 35% of the vehicle's own height
       - Horizontal: centre 60% of the vehicle's own width
     This is correct regardless of where in the frame the vehicle sits.
  3. Pre-process the crop and run EasyOCR on it.
  4. Return the best text string and the saved crop image path.

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
    frame        : np.ndarray  -- full BGR video frame (any size)
    vehicle_box  : tuple       -- (x1, y1, x2, y2) pixel coords of the vehicle
                                  as returned by YOLOv8 via detection.py.
                                  The crop is done RELATIVE to this box, so
                                  the vehicle can be anywhere in the frame.
    violation_id : int         -- DB row id, used to name saved images

    Returns
    -------
    dict with:
        plate_text       : str or None   -- OCR result (may be empty/wrong)
        plate_image_path : str or None   -- path to saved plate crop image
        plate_crop       : np.ndarray or None -- the raw (unprocessed) crop
    """
    ensure_dirs()

    x1, y1, x2, y2 = [int(v) for v in vehicle_box]
    fh, fw = frame.shape[:2]

    # Clamp vehicle box to frame bounds to handle edge detections
    x1 = max(0, x1); y1 = max(0, y1)
    x2 = min(fw, x2); y2 = min(fh, y2)

    if x2 <= x1 or y2 <= y1:
        return {"plate_text": None, "plate_image_path": None, "plate_crop": None}

    # -- Step 1: crop plate search region from WITHIN the vehicle box --------
    #
    # Number plates sit in the bottom ~35% of the vehicle's own height.
    # Horizontally, plates occupy roughly the centre 60% of the vehicle width
    # (bumpers extend further left/right than the plate).
    #
    # All offsets are computed relative to the vehicle box top-left corner,
    # so this is correct no matter where the vehicle appears in the frame.
    #
    veh_h = y2 - y1   # vehicle box height in pixels
    veh_w = x2 - x1   # vehicle box width  in pixels

    # Vertical: start 65% down from the top of the vehicle box
    plate_y1 = y1 + int(veh_h * 0.65)
    plate_y2 = y2                         # bottom edge of the vehicle box

    # Horizontal: take the centre 60% (20% margin each side)
    h_margin = int(veh_w * 0.20)
    plate_x1 = x1 + h_margin
    plate_x2 = x2 - h_margin

    # Safety: if margins collapse the box (tiny detection), use full vehicle width
    if plate_x2 <= plate_x1:
        plate_x1, plate_x2 = x1, x2

    plate_region = frame[plate_y1:plate_y2, plate_x1:plate_x2].copy()

    if plate_region.size == 0:
        return {"plate_text": None, "plate_image_path": None, "plate_crop": None}

    # -- Step 2: pre-process to help OCR ------------------------------------
    processed = _preprocess_plate(plate_region)

    # -- Step 3: run EasyOCR ------------------------------------------------
    reader  = _get_reader()
    results = reader.readtext(processed, detail=1, paragraph=False)

    # Pick the highest-confidence text segment
    plate_text = None
    if results:
        best     = max(results, key=lambda r: r[2])   # r[2] is confidence score
        raw_text = best[1].strip().upper()
        if raw_text:
            plate_text = raw_text

    # -- Step 4: save the raw plate crop (before processing) ----------------
    plate_image_path = None
    fname = os.path.join(EVIDENCE_DIR, "plate_{:04d}.jpg".format(violation_id))
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
    Resizes to a fixed height, sharpens, then binarises with Otsu threshold.
    """
    target_h = 64
    h, w = img.shape[:2]
    if h == 0 or w == 0:
        return img

    scale   = target_h / h
    new_w   = max(1, int(w * scale))
    resized = cv2.resize(img, (new_w, target_h), interpolation=cv2.INTER_CUBIC)

    grey = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

    # Sharpen
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    sharp  = cv2.filter2D(grey, -1, kernel)

    # Otsu binarisation -- good for high-contrast plate text
    _, binary = cv2.threshold(sharp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)


# ---------------------------------------------------------------------------
# Standalone test
#
# Usage examples:
#
#   # Whole image IS the vehicle (tightly-cropped vehicle photo):
#   python anpr.py --image car.jpg
#
#   # Vehicle is a sub-region of a wider scene (pass the YOLOv8 box coords):
#   python anpr.py --image scene.jpg --box 50 30 620 460
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Test ANPR on a single image")
    ap.add_argument("--image", required=True, help="Path to input image")
    ap.add_argument("--box",   nargs=4, type=int, metavar=("X1", "Y1", "X2", "Y2"),
                    help="Vehicle bounding box coords (default: full image)")
    args = ap.parse_args()

    frame = cv2.imread(args.image)
    if frame is None:
        print("ERROR: cannot read image:", args.image)
        raise SystemExit(1)

    fh, fw = frame.shape[:2]

    # Use the provided --box, or default to the whole image (works for tightly-cropped vehicle photos)
    box = tuple(args.box) if args.box else (0, 0, fw, fh)
    bx1, by1, bx2, by2 = [int(v) for v in box]

    # Mirror the crop logic so we can print what region will be searched
    veh_h = by2 - by1
    veh_w = bx2 - bx1
    px1 = bx1 + int(veh_w * 0.20)
    px2 = bx2 - int(veh_w * 0.20)
    py1 = by1 + int(veh_h * 0.65)
    py2 = by2

    print("[test] Image size        : {}x{}".format(fw, fh))
    print("[test] Vehicle box       : {}".format(box))
    print("[test] Plate search rgn  : x=[{}, {}]  y=[{}, {}]  ({}x{} px)".format(
          px1, px2, py1, py2, px2 - px1, py2 - py1))

    result = detect_and_read_plate(frame, box, violation_id=9999)
    print("[test] plate_text        :", result["plate_text"])
    print("[test] plate_image_path  :", result["plate_image_path"])

    # Save a debug overlay so you can visually confirm the boxes are correct
    import os
    os.makedirs("evidence", exist_ok=True)
    debug = frame.copy()
    cv2.rectangle(debug, (bx1, by1), (bx2, by2), (0, 255, 0), 2)   # green = vehicle box
    cv2.rectangle(debug, (px1, py1), (px2, py2), (0, 0, 255), 2)    # red   = plate search region
    cv2.putText(debug, "vehicle box",  (bx1, max(by1 - 6, 12)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    cv2.putText(debug, "plate search", (px1, max(py1 - 6, 12)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)
    debug_path = "evidence/anpr_debug_9999.jpg"
    cv2.imwrite(debug_path, debug)
    print("[test] Debug overlay     :", debug_path)
    print("[test] Open it to confirm the RED box sits over the number plate.")

