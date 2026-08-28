import cv2
import numpy as np

RED_LOWER1 = np.array([0, 20, 150])
RED_UPPER1 = np.array([10, 255, 255])
RED_LOWER2 = np.array([160, 20, 150])
RED_UPPER2 = np.array([179, 255, 255])

YELLOW_LOWER = np.array([15, 20, 150])
YELLOW_UPPER = np.array([35, 255, 255])

GREEN_LOWER = np.array([40, 20, 150])
GREEN_UPPER = np.array([90, 255, 255])

MIN_PIXEL_COUNT = 5
DEBUG_TRAFFIC_LIGHT = False

def get_light_state(frame, light_region):
    x1, y1, x2, y2 = light_region
    h, w = frame.shape[:2]
    
    x1, y1 = max(0, int(x1)), max(0, int(y1))
    x2, y2 = min(w, int(x2)), min(h, int(y2))
    
    if x2 <= x1 or y2 <= y1:
        return "unknown"
        
    crop = frame[y1:y2, x1:x2]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    
    mask_r1 = cv2.inRange(hsv, RED_LOWER1, RED_UPPER1)
    mask_r2 = cv2.inRange(hsv, RED_LOWER2, RED_UPPER2)
    mask_r = cv2.bitwise_or(mask_r1, mask_r2)
    
    mask_y = cv2.inRange(hsv, YELLOW_LOWER, YELLOW_UPPER)
    mask_g = cv2.inRange(hsv, GREEN_LOWER, GREEN_UPPER)
    
    count_r = cv2.countNonZero(mask_r)
    count_y = cv2.countNonZero(mask_y)
    count_g = cv2.countNonZero(mask_g)
    
    if DEBUG_TRAFFIC_LIGHT:
        print(f"[DEBUG TRAFFIC_LIGHT] R:{count_r} Y:{count_y} G:{count_g}")
        import os
        os.makedirs("debug_traffic", exist_ok=True)
        cv2.imwrite("debug_traffic/crop.jpg", crop)
        
    counts = {"red": count_r, "yellow": count_y, "green": count_g}
    dominant = max(counts, key=counts.get)
    
    if counts[dominant] >= MIN_PIXEL_COUNT:
        return dominant
    return "unknown"
