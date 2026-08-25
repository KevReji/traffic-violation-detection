"""
violations.py -- Violation detection rules applied per frame.

Three rules:
  1. Helmet Violation  -- motorcycle + person, helmet check via placeholder
  2. Triple Riding     -- 3+ persons sharing a single motorcycle bounding box
  3. Illegal Parking   -- vehicle inside a restricted zone for > PARKING_TIMEOUT seconds

Call check_violations(frame_data) each frame; it returns a list of violation dicts.
"""

from utils import compute_iou, box_inside_zone, get_center

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# How many seconds a vehicle must be stationary inside a zone to be flagged
PARKING_TIMEOUT = 5.0   # seconds  (change this as needed)

# IoU threshold: how much overlap a person box must have with a motorcycle box
# to be considered "on" that motorcycle
PERSON_MOTO_IOU_THRESHOLD = 0.15

# Restricted zones: list of (x1, y1, x2, y2) rectangles in pixel coordinates.
# Leave empty [] while testing; set real zone coords from your video later.
RESTRICTED_ZONES = []

# ---------------------------------------------------------------------------
# Internal state (module-level so it persists across frames)
# ---------------------------------------------------------------------------
# Tracks how long each vehicle has been inside each zone.
# Key: (zone_index, vehicle_id)  where vehicle_id = rounded (cx, cy) pair
# Value: first_seen_sec (float)
_parking_state = {}    # {(zone_idx, v_id): first_seen_timestamp_sec}


def reset_state():
    """Call this at the start of each new video to clear parking state."""
    global _parking_state
    _parking_state = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_violations(frame_data):
    """
    Analyse one frame's detections and return all violations found.

    Parameters
    ----------
    frame_data : dict  -- the dict yielded by run_detection() in detection.py

    Returns
    -------
    list of dicts, each with:
        violation_type  : str   -- "helmet" | "triple_riding" | "illegal_parking"
        vehicle_type    : str   -- detected class name
        confidence      : float -- detection confidence of primary vehicle
        box             : (x1,y1,x2,y2)  -- bounding box of the vehicle
        frame_number    : int
        timestamp_sec   : float
    """
    detections    = frame_data["detections"]
    frame_number  = frame_data["frame_number"]
    timestamp_sec = frame_data["timestamp_sec"]
    fps           = frame_data.get("fps", 25.0)

    violations = []

    # Separate detections by class for convenience
    persons     = [d for d in detections if d["class_name"] == "person"]
    motorcycles = [d for d in detections if d["class_name"] == "motorcycle"]
    vehicles    = [d for d in detections if d["class_name"] in ("car","bus","truck","motorcycle")]

    # -- Rule 1: Helmet Violation -----------------------------------------
    for moto in motorcycles:
        riders = _find_associated_persons(moto["box"], persons)
        for rider in riders:
            if detect_helmet_violation(rider, moto, frame_data.get("annotated_frame")):
                violations.append({
                    "violation_type": "helmet",
                    "vehicle_type":   "motorcycle",
                    "confidence":     moto["confidence"],
                    "box":            moto["box"],
                    "frame_number":   frame_number,
                    "timestamp_sec":  timestamp_sec,
                })

    # -- Rule 2: Triple Riding -------------------------------------------
    for moto in motorcycles:
        riders = _find_associated_persons(moto["box"], persons)
        if len(riders) >= 3:
            violations.append({
                "violation_type": "triple_riding",
                "vehicle_type":   "motorcycle",
                "confidence":     moto["confidence"],
                "box":            moto["box"],
                "frame_number":   frame_number,
                "timestamp_sec":  timestamp_sec,
            })

    # -- Rule 3: Illegal Parking -----------------------------------------
    for v in vehicles:
        v_id = _make_vehicle_id(v["box"])
        for zone_idx, zone in enumerate(RESTRICTED_ZONES):
            if box_inside_zone(v["box"], zone):
                key = (zone_idx, v_id)
                if key not in _parking_state:
                    _parking_state[key] = timestamp_sec   # first time seen
                elif timestamp_sec - _parking_state[key] >= PARKING_TIMEOUT:
                    violations.append({
                        "violation_type": "illegal_parking",
                        "vehicle_type":   v["class_name"],
                        "confidence":     v["confidence"],
                        "box":            v["box"],
                        "frame_number":   frame_number,
                        "timestamp_sec":  timestamp_sec,
                    })
                    # Reset timer so we don't spam violations every frame
                    _parking_state[key] = timestamp_sec
            else:
                # Vehicle left the zone -- remove from tracking
                _parking_state.pop((zone_idx, v_id), None)

    return violations


# ---------------------------------------------------------------------------
# Placeholder -- REPLACE with your own trained model later
# ---------------------------------------------------------------------------

def detect_helmet_violation(rider_det, moto_det, frame=None):
    """
    PLACEHOLDER: always returns False (no violation detected).

    Replace the body of this function with your own fine-tuned model
    inference code.  The function must return True if the rider is NOT
    wearing a helmet, False otherwise.

    Parameters
    ----------
    rider_det : dict  -- person detection {class_name, confidence, box}
    moto_det  : dict  -- motorcycle detection {class_name, confidence, box}
    frame     : np.ndarray or None  -- the current BGR frame (for cropping)
    """
    return False   # <-- your model goes here


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_associated_persons(moto_box, persons):
    """
    Return all person detections whose bounding box overlaps the motorcycle
    box with IoU >= PERSON_MOTO_IOU_THRESHOLD.
    """
    associated = []
    for p in persons:
        iou = compute_iou(moto_box, p["box"])
        if iou >= PERSON_MOTO_IOU_THRESHOLD:
            associated.append(p)
    return associated


def _make_vehicle_id(box):
    """
    Create a coarse unique ID for a vehicle based on its centre point.
    Rounded to nearest 20 pixels to handle minor jitter between frames.
    """
    cx, cy = get_center(box)
    return (round(cx / 20) * 20, round(cy / 20) * 20)
