"""
violations.py -- Violation detection rules applied per frame.

Three rules:
  1. Helmet Violation  -- motorcycle + person, helmet check via placeholder
  2. Triple Riding     -- 3+ persons sharing a single motorcycle bounding box
  3. Illegal Parking   -- vehicle inside a restricted zone for > PARKING_TIMEOUT seconds

Call check_violations(frame_data) each frame; it returns a list of violation dicts.

DEBUG MODE
----------
Set DEBUG_TRIPLE_RIDING = True to print per-frame association diagnostics for the
triple-riding rule.  This tells you whether missed violations are caused by:
  (a) YOLO failing to detect all 3 persons (detection problem), or
  (b) persons being detected but not associated with the motorcycle (logic problem).
Turn it off again (False) once the root cause is identified.
"""

from utils import compute_iou, box_inside_zone, get_center
from confidence import evaluate_confidence

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# How many seconds a vehicle must be stationary inside a zone to be flagged
PARKING_TIMEOUT = 5.0   # seconds  (change this as needed)

# Cooldown (in seconds) to prevent spamming the same violation type every frame
COOLDOWN_SECONDS = 5.0

# IoU threshold: how much overlap a person box must have with a motorcycle box
# to be considered "on" that motorcycle.
# TUNING GUIDE:
#   - If persons are detected but NOT associated -> lower this value (try 0.05)
#   - If unrelated pedestrians are wrongly counted -> raise it (try 0.25)
PERSON_MOTO_IOU_THRESHOLD = 0.10

# Restricted zones: list of (x1, y1, x2, y2) rectangles in pixel coordinates.
# Leave empty [] while testing; set real zone coords from your video later.
RESTRICTED_ZONES = []


# ---------------------------------------------------------------------------
# Wrong-way driving settings
# ---------------------------------------------------------------------------
WRONG_WAY_HISTORY_FRAMES = 15
WRONG_WAY_SIZE_GROWTH_THRESHOLD = 1.4
MIN_REVIEW_TRACKING_FRAMES = 3
DEBUG_WRONG_WAY = True   # <-- set True to test wrong-way detection

# ---------------------------------------------------------------------------
# Debug flag -- set True to diagnose missed triple-riding detections

# ---------------------------------------------------------------------------
DEBUG_TRIPLE_RIDING = False   # <-- flip to True when investigating missed detections

# ---------------------------------------------------------------------------
# Internal state (module-level so it persists across frames)
# ---------------------------------------------------------------------------
_parking_state = {}    # {(zone_idx, v_id): first_seen_timestamp_sec}
_last_logged_time = {} # {violation_type: last_logged_timestamp_sec}
_track_history = {}    # {track_id: [(frame_number, area), ...]}


def reset_state():
    """Call this at the start of each new video to clear parking state."""
    global _parking_state, _last_logged_time, _track_history
    _parking_state = {}
    _last_logged_time = {}
    _track_history = {}


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
    frame_area    = frame_data.get("frame_width", 1920) * frame_data.get("frame_height", 1080)

    violations = []

    def can_log(v_type, entity_id=None):
        key = v_type if entity_id is None else f"{v_type}_{entity_id}"
        last_time = _last_logged_time.get(key, -999999.0)
        if (timestamp_sec - last_time) >= COOLDOWN_SECONDS:
            _last_logged_time[key] = timestamp_sec
            return True
        return False

    # Separate detections by class for convenience
    persons     = [d for d in detections if d["class_name"] == "person"]
    motorcycles = [d for d in detections if d["class_name"] == "motorcycle"]
    vehicles    = [d for d in detections if d["class_name"] in ("car","bus","truck","motorcycle")]

    # -- Rule 1: Helmet Violation -----------------------------------------
    for moto in motorcycles:
        riders = _find_associated_persons(moto["box"], persons)
        for rider in riders:
            if detect_helmet_violation(rider, moto, frame_data.get("annotated_frame")):
                if can_log("helmet"):
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

        # ── DEBUG: print association details so we can diagnose misses ──
        if DEBUG_TRIPLE_RIDING:
            _debug_triple(frame_number, timestamp_sec, moto, persons, riders)

        if len(riders) >= 3:
            if can_log("triple_riding"):
                violations.append({
                    "violation_type": "triple_riding",
                    "vehicle_type":   "motorcycle",
                    "confidence":     moto["confidence"],
                    "box":            moto["box"],
                    "frame_number":   frame_number,
                    "timestamp_sec":  timestamp_sec,
                })

    # ── If debug is on and no motorcycles were detected, still log persons ──
    if DEBUG_TRIPLE_RIDING and not motorcycles and persons:
        print(
            "[DBG TR] Frame {:>4} | NO motorcycle detected | "
            "{} person(s) in frame (conf: {})".format(
                frame_number,
                len(persons),
                ", ".join("{:.2f}".format(p["confidence"]) for p in persons)
            )
        )

    # -- Rule 3: Illegal Parking -----------------------------------------
    for v in vehicles:
        v_id = _make_vehicle_id(v["box"])
        for zone_idx, zone in enumerate(RESTRICTED_ZONES):
            if box_inside_zone(v["box"], zone):
                key = (zone_idx, v_id)
                if key not in _parking_state:
                    _parking_state[key] = timestamp_sec   # first time seen
                elif timestamp_sec - _parking_state[key] >= PARKING_TIMEOUT:
                    if can_log("illegal_parking"):
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

    # -- Rule 4: Wrong Way Driving ---------------------------------------
    for v in vehicles:
        track_id = v.get("track_id")
        if track_id is None:
            continue
            
        x1, y1, x2, y2 = v["box"]
        area = (x2 - x1) * (y2 - y1)
        
        history = _track_history.setdefault(track_id, [])
        history.append((frame_number, area))
        
        if len(history) > WRONG_WAY_HISTORY_FRAMES:
            history.pop(0)
            
        if len(history) >= MIN_REVIEW_TRACKING_FRAMES:
            oldest_area = history[0][1]
            current_area = area
            growth_ratio = current_area / oldest_area if oldest_area > 0 else 0
            
            if DEBUG_WRONG_WAY:
                print(f"[DBG WW] Frame {frame_number:>4} | track_id={track_id} | ratio={growth_ratio:.2f} (old={oldest_area}, new={current_area})")
                
            # If the vehicle bounding box has grown by the threshold over the history window,
            # it indicates the vehicle is approaching the camera. In a forward-facing dashcam 
            # scenario on a one-way path (or single-direction lane), approaching means wrong way.
            is_strict = (growth_ratio >= WRONG_WAY_SIZE_GROWTH_THRESHOLD and len(history) >= WRONG_WAY_HISTORY_FRAMES)
            is_review = (growth_ratio >= 1.1) and (v.get("low_confidence_detection") or len(history) < WRONG_WAY_HISTORY_FRAMES)
            
            if is_strict or is_review:
                if can_log("wrong_way", track_id):
                    bw = v["box"][2] - v["box"][0]
                    bh = v["box"][3] - v["box"][1]
                    rn, rr = evaluate_confidence(v["confidence"], bw*bh, frame_area, len(history))
                    if len(history) < WRONG_WAY_HISTORY_FRAMES:
                        rn, rr = True, "insufficient_tracking_history"
                    elif v.get("low_confidence_detection"):
                        rn, rr = True, "low_confidence_detection"
                    violations.append({
                        "violation_type": "wrong_way",
                        "vehicle_type":   v["class_name"],
                        "confidence":     v["confidence"],
                        "box":            v["box"],
                        "frame_number":   frame_number,
                        "timestamp_sec":  timestamp_sec,
                        "review_needed":  rn,
                        "review_reason":  rr,
                    })
                    if DEBUG_WRONG_WAY:
                        print(f"         >>> WRONG WAY VIOLATION LOGGED for track_id={track_id}")

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


def _debug_triple(frame_number, timestamp_sec, moto, persons, associated):
    """
    Print a detailed per-frame summary for one motorcycle.
    Shows every person's confidence, IoU against this motorcycle, and
    whether they passed the association threshold.
    This helps distinguish detection problems from logic problems.
    """
    moto_box = moto["box"]
    lines = []
    lines.append(
        "[DBG TR] Frame {:>4} @{:.2f}s | moto conf={:.2f} box={} | "
        "{} person(s) in frame | {} associated (need 3)".format(
            frame_number, timestamp_sec,
            moto["confidence"], moto_box,
            len(persons), len(associated)
        )
    )
    for i, p in enumerate(persons):
        iou      = compute_iou(moto_box, p["box"])
        passed   = "ASSOC" if iou >= PERSON_MOTO_IOU_THRESHOLD else "miss "
        lines.append(
            "           person[{}] conf={:.2f}  IoU={:.3f}  -> {}  box={}".format(
                i, p["confidence"], iou, passed, p["box"]
            )
        )
    if not persons:
        lines.append("           (no persons detected in this frame)")
    print("\n".join(lines))


def _make_vehicle_id(box):
    """
    Create a coarse unique ID for a vehicle based on its centre point.
    Rounded to nearest 20 pixels to handle minor jitter between frames.
    """
    cx, cy = get_center(box)
    return (round(cx / 20) * 20, round(cy / 20) * 20)
