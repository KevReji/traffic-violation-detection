"""
violations.py -- Violation detection rules applied per frame.

Rules:
  1. Helmet Violation  -- motorcycle + person, runs the fine-tuned helmet YOLO model
                         on each associated rider crop to detect missing helmets.
  2. Triple Riding     -- 3+ persons sharing a single motorcycle bounding box.
  3. Illegal Parking   -- vehicle stationary inside a restricted zone > PARKING_TIMEOUT.
  4. Wrong-Way Driving -- vehicle bounding box growing consistently over N frames.

Call check_violations(frame_data, helmet_model=...) each frame.

DEBUG FLAGS
-----------
DEBUG_HELMET        -- prints per-rider crop + model output for helmet rule.
DEBUG_TRIPLE_RIDING -- prints per-frame IoU association details for triple-riding.
"""

from utils import compute_iou, box_inside_zone, has_fully_crossed_line, get_center, draw_box
from confidence import evaluate_confidence
from detection import CONF_THRESHOLD, REVIEW_CONF_THRESHOLD
from traffic_light import get_light_state

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Helmet model shows underconfidence on some clean, unambiguous crops relative to the general 
# 0.4 threshold - lowered specifically for this violation type based on manual review of 
# debug_crops confidence scores. Does not apply to other violation types.
HELMET_CONFIRM_THRESHOLD = 0.35


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


# ---------------------------------------------------------------------------
# Red Light settings
# ---------------------------------------------------------------------------
DEBUG_RED_LIGHT = False
LIGHT_REGION = (1720, 120, 1760, 180)
STOP_LINE = ((0, 600), (1920, 650)) # Same pattern as RESTRICTED_ZONES

# Restricted zones: list of (x1, y1, x2, y2) rectangles in pixel coordinates.
# Leave empty [] while testing; set real zone coords from your video later.
RESTRICTED_ZONES = []


# ---------------------------------------------------------------------------
# Wrong-way driving settings
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Helmet detection settings
# ---------------------------------------------------------------------------
# Minimum confidence from the helmet model for a "no helmet" prediction to fire.
# Raise if you're getting too many false positives; lower if missing real violations.


# Set True to print per-rider crop geometry and model output while debugging.
DEBUG_HELMET = False

# ---------------------------------------------------------------------------
# Debug flag -- set True to diagnose missed triple-riding detections

# ---------------------------------------------------------------------------
DEBUG_TRIPLE_RIDING = False   # <-- flip to True when investigating missed detections

# ---------------------------------------------------------------------------
# Internal state (module-level so it persists across frames)
# ---------------------------------------------------------------------------
_parking_state = {}    # {(zone_idx, v_id): first_seen_timestamp_sec}
_last_logged_time = {} # {violation_type: last_logged_timestamp_sec}
_red_light_history = {}    # {track_id: [(frame_number, area), ...]}


def reset_state():
    """Call this at the start of each new video to clear parking state."""
    global _parking_state, _last_logged_time, _red_light_history
    _parking_state = {}
    _last_logged_time = {}
    _red_light_history = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_violations(frame_data, helmet_model=None, enable_red_light=True, light_region=None, stop_line=None):
    if frame_data.get("frame_number", 0) == 0:
        print(f"[DEBUG OVERRIDE] check_violations received light_region={light_region}, stop_line={stop_line}")

    """
    Analyse one frame's detections and return all violations found.

    Parameters
    ----------
    frame_data      : dict -- the dict yielded by run_detection() in detection.py
    helmet_model    : ultralytics YOLO object or None
                      The loaded fine-tuned helmet model.  If None, helmet
                      detection is skipped (no violations will fire for Rule 1).

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
    # Only runs when a helmet model is loaded (helmet_model is not None).
    # Uses the ORIGINAL (unannotated) frame for clean crops.
    if helmet_model is not None:
        for moto in motorcycles:
            riders = _find_associated_persons(moto["box"], persons)
            for rider in riders:
                helmet_result = detect_helmet_violation(
                    rider, moto,
                    frame=frame_data.get("original_frame"),
                    helmet_model=helmet_model,
                    frame_number=frame_number
                )
                if helmet_result and helmet_result.get("no_helmet"):
                    # Translate crop-local coordinates to full-frame coordinates
                    cx1, cy1, cx2, cy2 = helmet_result["crop_box"]
                    ox, oy = helmet_result["crop_offset"]
                    full_box = (cx1 + ox, cy1 + oy, cx2 + ox, cy2 + oy)
                    
                    # Draw directly onto the live feed frame (Orange color)
                    annotated = frame_data.get("annotated_frame")
                    if annotated is not None:
                        label = f"No Helmet {helmet_result['confidence']:.2f}"
                        draw_box(annotated, full_box, label, color=(0, 165, 255))

                    rider_entity_id = rider.get("track_id") or str(rider["box"])
                    if can_log("helmet", entity_id=rider_entity_id):
                        violations.append({
                            "violation_type": "helmet",
                            "vehicle_type":   "motorcycle",
                            "confidence":     helmet_result["confidence"],
                            "box":            rider["box"],   # crop the RIDER, not the moto
                            "frame_number":   frame_number,
                            "timestamp_sec":  timestamp_sec,
                            "review_needed":  helmet_result.get("review_needed", False),
                            "review_reason":  helmet_result.get("review_reason", None)
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


    # -- Rule X: Red Light -----------------------------------------------
    if enable_red_light:
        for v in vehicles:
            track_id = v.get("track_id")
            if track_id is not None:
                curr_box = v["box"]
                prev_box = _red_light_history.get(track_id)
                if prev_box is not None:
                    for zone in [(stop_line if stop_line is not None else STOP_LINE)]:
                        p1, p2 = zone
                        curr_crossed = has_fully_crossed_line(curr_box, p1, p2, 'up')
                        prev_crossed = has_fully_crossed_line(prev_box, p1, p2, 'up')
                        if curr_crossed and not prev_crossed:
                            if DEBUG_RED_LIGHT:
                                print(f"[DEBUG RED_LIGHT] Vehicle {track_id} crossed stop line.")
                            
                            light_state = get_light_state(frame_data["original_frame"], light_region if light_region is not None else LIGHT_REGION)
                            
                            if light_state in ["red", "unknown"]:
                                cooldown_key = f"red_light_{track_id}"
                                if cooldown_key not in _last_logged_time or (timestamp_sec - _last_logged_time[cooldown_key] > 10.0):
                                    is_confirmed = evaluate_confidence(v["confidence"], CONF_THRESHOLD, REVIEW_CONF_THRESHOLD)
                                    
                                    violation = {
                                        "violation_type": "red_light",
                                        "frame_number": frame_number,
                                        "timestamp_sec": timestamp_sec,
                                        "vehicle_type": v["class_name"],
                                        "box": v["box"],
                                        "confidence": v["confidence"],
                                        "review_needed": not is_confirmed or light_state == "unknown",
                                        "review_reason": "ambiguous_light_state" if light_state == "unknown" else ("low_confidence_detection" if not is_confirmed else "")
                                    }
                                    violations.append(violation)
                                    _last_logged_time[cooldown_key] = timestamp_sec
                                    
                                    # Draw annotation
                                    draw_box(
                                        frame_data["annotated_frame"], 
                                        v["box"], 
                                        label=f"Red Light ({light_state})", 
                                        color=(0, 0, 255) if light_state == "red" else (0, 165, 255)
                                    )
                                    
                # Update history
                _red_light_history[track_id] = curr_box

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

    return violations


# ---------------------------------------------------------------------------
# Helmet violation detector — uses the fine-tuned YOLO model
# ---------------------------------------------------------------------------

def detect_helmet_violation(rider_det, moto_det, frame=None, helmet_model=None, frame_number=None):
    """
    Run the fine-tuned helmet model on the rider's bounding-box crop.

    Returns True if the rider is NOT wearing a helmet, False otherwise.
    Returns False immediately (safe no-op) if frame or helmet_model is None.

    Parameters
    ----------
    rider_det    : dict  -- person detection {class_name, confidence, box}
    moto_det     : dict  -- motorcycle detection {class_name, confidence, box}
    frame        : np.ndarray or None  -- the ORIGINAL (unannotated) BGR frame
    helmet_model : ultralytics YOLO or None  -- the loaded fine-tuned helmet model
    """
    if frame is None or helmet_model is None:
        return False

    x1, y1, x2, y2 = [int(c) for c in rider_det["box"]]
    h, w = frame.shape[:2]

    # Clamp to frame bounds
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)

    if x2 <= x1 or y2 <= y1:
        return False   # degenerate box

    # Crop only the top 25% (head/shoulder region)
    head_y2 = y1 + int((y2 - y1) * 0.25)
    rider_crop = frame[y1:head_y2, x1:x2]

    if DEBUG_HELMET:
        import os
        import cv2
        os.makedirs("debug_crops", exist_ok=True)
        debug_path = os.path.join("debug_crops", f"frame{frame_number}_rider{x1}_{y1}.jpg")
        cv2.imwrite(debug_path, rider_crop)

    # Run the helmet model (verbose=False keeps the console quiet)
    results = helmet_model(rider_crop, verbose=False, conf=REVIEW_CONF_THRESHOLD)

    no_helmet_detected = False
    for result in results:
        for box_obj in result.boxes:
            cls_id = int(box_obj.cls[0])
            conf   = float(box_obj.conf[0])
            # The fine-tuned model's class names tell us which index is "no_helmet".
            # We look up the name dynamically so it works regardless of class ordering.
            cls_name = helmet_model.names.get(cls_id, "").lower()

            # Ignore the "licence" class from the v2 model
            if "licence" in cls_name:
                continue

            if DEBUG_HELMET:
                print(
                    f"[DBG HELMET] rider_box={rider_det['box']}  "
                    f"cls={cls_name}  conf={conf:.3f}  "
                    f"thresholds={REVIEW_CONF_THRESHOLD}/{HELMET_CONFIRM_THRESHOLD}"
                )

            is_no_helmet = (
                ("without" in cls_name and "helmet" in cls_name)
                or ("no" in cls_name and "helmet" in cls_name)
            )
            if is_no_helmet:
                crop_box = [int(v) for v in box_obj.xyxy[0].tolist()]
                ret_dict = {
                    "no_helmet": True, 
                    "review_needed": False, 
                    "review_reason": None, 
                    "confidence": conf,
                    "crop_box": crop_box,
                    "crop_offset": (x1, y1)
                }
                
                if conf >= HELMET_CONFIRM_THRESHOLD:
                    return ret_dict
                elif REVIEW_CONF_THRESHOLD <= conf < HELMET_CONFIRM_THRESHOLD:
                    ret_dict["review_needed"] = True
                    ret_dict["review_reason"] = "low_confidence_detection"
                    return ret_dict

    return False



# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_associated_persons(moto_box, persons):
    """
    Return all person detections whose bounding box overlaps the motorcycle
    box with IoU >= PERSON_MOTO_IOU_THRESHOLD, AND whose horizontal center
    falls within the motorcycle's left/right boundaries.
    """
    associated = []
    mx1, my1, mx2, my2 = moto_box
    for p in persons:
        px1, py1, px2, py2 = p["box"]
        iou = compute_iou(moto_box, p["box"])
        
        # Check if the person's spine is physically positioned over the bike
        px_center = (px1 + px2) / 2.0
        is_centered = (mx1 <= px_center <= mx2)
        
        if iou >= PERSON_MOTO_IOU_THRESHOLD and is_centered:
            associated.append(p)
            
    # Deduplicate YOLO "ghost" detections (e.g. model detects both a torso and a full body).
    # If a smaller box is > 85% inside a larger box, they are the same person.
    unique_riders = []
    for p1 in associated:
        b1 = p1["box"]
        a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
        is_ghost = False
        
        for p2 in unique_riders:
            b2 = p2["box"]
            a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
            
            # Compute intersection area
            xA = max(b1[0], b2[0])
            yA = max(b1[1], b2[1])
            xB = min(b1[2], b2[2])
            yB = min(b1[3], b2[3])
            interArea = max(0, xB - xA) * max(0, yB - yA)
            
            # Intersection over the smaller box's area (IoA)
            if interArea / min(a1, a2) > 0.85:
                is_ghost = True
                break
                
        if not is_ghost:
            unique_riders.append(p1)

    return unique_riders


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
