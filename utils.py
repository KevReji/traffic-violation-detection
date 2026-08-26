"""
utils.py -- Shared helper functions used across all modules.
"""

import os
import cv2
import numpy as np


# ── Folder paths (change here to move evidence/output) ──────────────────────
EVIDENCE_DIR = "evidence"
OUTPUT_DIR = "output"


def ensure_dirs():
    """Create evidence/ and output/ folders if they do not already exist."""
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def crop_region(frame, box, padding_pct=0.0):
    """
    Crop a rectangular region from a frame.
    box: (x1, y1, x2, y2) in pixel coords (integers).
    padding_pct: fraction of width/height to add as margin (e.g. 0.20 = 20% on each side).
    Returns the cropped numpy array, or None if coords are invalid.
    """
    x1, y1, x2, y2 = [int(v) for v in box]
    h, w = frame.shape[:2]
    
    bw = x2 - x1
    bh = y2 - y1
    px = int(bw * padding_pct)
    py = int(bh * padding_pct)
    
    x1 = x1 - px
    y1 = y1 - py
    x2 = x2 + px
    y2 = y2 + py
    
    # Clamp to frame bounds so we never go out of range
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 <= x1 or y2 <= y1:
        return None
    return frame[y1:y2, x1:x2].copy()


def save_image(img, path):
    """Save a numpy image (BGR) to disk. Returns True on success."""
    if img is None or img.size == 0:
        return False
    return cv2.imwrite(path, img)


def compute_iou(boxA, boxB):
    """
    Compute Intersection-over-Union between two boxes.
    Each box is (x1, y1, x2, y2).
    Used to associate persons with motorcycles.
    """
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    inter_w = max(0, xB - xA)
    inter_h = max(0, yB - yA)
    inter_area = inter_w * inter_h

    if inter_area == 0:
        return 0.0

    areaA = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    areaB = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    union_area = areaA + areaB - inter_area
    return inter_area / union_area if union_area > 0 else 0.0


def box_inside_zone(box, zone):
    """
    Check whether a bounding box overlaps (even partially) with a zone rect.
    box and zone are both (x1, y1, x2, y2).
    Returns True if there is any overlap.
    """
    bx1, by1, bx2, by2 = box
    zx1, zy1, zx2, zy2 = zone
    # No overlap if one rect is fully to the side / above / below the other
    if bx2 < zx1 or bx1 > zx2 or by2 < zy1 or by1 > zy2:
        return False
    return True


def draw_box(frame, box, label, color=(0, 255, 0), thickness=2):
    """
    Draw a labeled bounding box on a frame (in-place).
    color: BGR tuple.
    """
    x1, y1, x2, y2 = [int(v) for v in box]
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
    # Small filled rect behind text for readability
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    cv2.rectangle(frame, (x1, y1 - th - 4), (x1 + tw + 2, y1), color, -1)
    cv2.putText(frame, label, (x1 + 1, y1 - 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)


def get_center(box):
    """Return the (cx, cy) center point of a bounding box."""
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2, (y1 + y2) / 2)
