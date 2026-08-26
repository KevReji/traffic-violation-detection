"""
confidence.py -- Generic confidence and review-flagging system for violations.

Provides a reusable layer that ANY violation type can use to determine
whether a violation is confirmed or needs manual human review.
"""

# ---------------------------------------------------------------------------
# Configuration Thresholds
# ---------------------------------------------------------------------------
# If the detection confidence (e.g. YOLO score) is below this, flag for review.
LOW_CONFIDENCE_THRESHOLD = 0.5

# If the bounding box area is smaller than this fraction of the total frame area,
# the object is considered too small/far away and should be flagged for review.
MIN_OBJECT_AREA_RATIO = 0.01

# If tracking stability (number of consecutive frames the object was tracked)
# is provided and is below this, flag for review.
TRACKING_STABILITY_MIN_FRAMES = 5

def evaluate_confidence(detection_confidence, box_area, frame_area, tracking_stability=None):
    """
    Evaluates detection metrics against generic thresholds to determine if a 
    violation should be 'confirmed' or flagged as 'review_needed'.
    
    Parameters:
    -----------
    detection_confidence : float
        Confidence score of the primary detection (e.g. YOLO confidence).
    box_area : float or int
        Area (width * height) of the detected object's bounding box.
    frame_area : float or int
        Total area (width * height) of the video frame.
    tracking_stability : int, optional
        Number of consecutive frames this object has been successfully tracked.
        
    Returns:
    --------
    review_needed : bool
        True if the violation needs manual review, False if it is confirmed.
    review_reason : str or None
        Reason for review (e.g., 'low_confidence', 'small_object', 'unstable_tracking'),
        or None if confirmed.
    """
    if detection_confidence < LOW_CONFIDENCE_THRESHOLD:
        return True, "low_confidence"
        
    if frame_area > 0 and (box_area / frame_area) < MIN_OBJECT_AREA_RATIO:
        return True, "small_object"
        
    if tracking_stability is not None and tracking_stability < TRACKING_STABILITY_MIN_FRAMES:
        return True, "unstable_tracking"
        
    return False, None
