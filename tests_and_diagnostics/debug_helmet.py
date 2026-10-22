"""
debug_helmet.py -- Standalone helmet debug script.
Run:  python debug_helmet.py
"""
import os, sys, cv2
import violations
violations.DEBUG_HELMET = True

from detection import load_model, run_detection
from violations import (check_violations, reset_state,
    PERSON_MOTO_IOU_THRESHOLD, HELMET_CONF_THRESHOLD,
    _find_associated_persons)
from utils import compute_iou

VIDEO_PATH    = "1000117981.mp4"
MAX_FRAMES    = 60
CROP_SAVE_DIR = "debug_helmet_crops"
HELMET_PT     = os.path.join("models", "helmet_yolov8s_v1_map74.pt")

os.makedirs(CROP_SAVE_DIR, exist_ok=True)

print("=" * 70)
print(f"Video        : {VIDEO_PATH}")
print(f"Helmet model : {HELMET_PT}")
print(f"Conf thresh  : {HELMET_CONF_THRESHOLD}")
print(f"IoU thresh   : {PERSON_MOTO_IOU_THRESHOLD}")
print("=" * 70)

vehicle_model = load_model("yolov8s.pt")
helmet_model  = load_model(HELMET_PT)
print(f"\nHelmet model classes: {helmet_model.names}\n")

reset_state()
frame_count = crop_count = helmet_hits = helmet_misses = no_boxes_count = 0

for frame_data in run_detection(VIDEO_PATH, model=vehicle_model, save_output=False):
    fn         = frame_data["frame_number"]
    detections = frame_data["detections"]
    orig_frame = frame_data.get("original_frame")
    frame_h    = frame_data.get("frame_height", 0)
    frame_w    = frame_data.get("frame_width",  0)

    persons     = [d for d in detections if d["class_name"] == "person"]
    motorcycles = [d for d in detections if d["class_name"] == "motorcycle"]

    if motorcycles:
        print(f"\n-- Frame {fn}  size={frame_w}x{frame_h}  motos={len(motorcycles)}  persons={len(persons)}")
        for mi, moto in enumerate(motorcycles):
            riders = _find_associated_persons(moto["box"], persons)
            print(f"   Moto[{mi}] box={moto['box']}  conf={moto['confidence']:.3f}  riders_assoc={len(riders)}")
            for p in persons:
                iou = compute_iou(moto["box"], p["box"])
                tag = "ASSOC" if iou >= PERSON_MOTO_IOU_THRESHOLD else "skip "
                print(f"      person box={p['box']}  iou={iou:.4f} -> {tag}")

            for ri, rider in enumerate(riders):
                x1,y1,x2,y2 = [int(c) for c in rider["box"]]
                cx1,cy1 = max(0,x1), max(0,y1)
                cx2,cy2 = min(frame_w,x2), min(frame_h,y2)
                cw, ch  = cx2-cx1, cy2-cy1
                print(f"      Rider[{ri}] raw=({x1},{y1},{x2},{y2}) clamped=({cx1},{cy1},{cx2},{cy2}) size={cw}x{ch}")

                if orig_frame is None:
                    print("      !! original_frame is None")
                    continue
                if cw <= 0 or ch <= 0:
                    print("      !! Degenerate crop")
                    continue

                crop = orig_frame[cy1:cy2, cx1:cx2]
                path = os.path.join(CROP_SAVE_DIR, f"crop_f{fn:04d}_m{mi}_r{ri}.jpg")
                cv2.imwrite(path, crop)
                crop_count += 1
                print(f"      Saved: {path}")

                try:
                    results = helmet_model(crop, verbose=False)
                except Exception as e:
                    print(f"      !! EXCEPTION in helmet_model(): {e}")
                    continue

                n_boxes = sum(len(r.boxes) for r in results)
                print(f"      Helmet model boxes returned: {n_boxes}")
                if n_boxes == 0:
                    no_boxes_count += 1
                    print("      >> Zero detections from helmet model")
                    continue

                for result in results:
                    for box_obj in result.boxes:
                        cls_id   = int(box_obj.cls[0])
                        conf     = float(box_obj.conf[0])
                        cls_name = helmet_model.names.get(cls_id, "?").lower()
                        is_no_h  = ("without" in cls_name and "helmet" in cls_name) or \
                                   ("no" in cls_name and "helmet" in cls_name)
                        if is_no_h:
                            if conf >= HELMET_CONF_THRESHOLD:
                                print(f"      cls={cls_name!r}  conf={conf:.4f}  >>> VIOLATION WOULD FIRE <<<")
                                helmet_hits += 1
                            else:
                                print(f"      cls={cls_name!r}  conf={conf:.4f}  (SUPPRESSED — below {HELMET_CONF_THRESHOLD})")
                                helmet_misses += 1
                        else:
                            print(f"      cls={cls_name!r}  conf={conf:.4f}  (with-helmet — no violation)")

    frame_count += 1
    if frame_count >= MAX_FRAMES:
        break

print("\n" + "=" * 70)
print("SUMMARY")
print(f"  Frames processed           : {frame_count}")
print(f"  Crops saved to {CROP_SAVE_DIR}/ : {crop_count}")
print(f"  Helmet model: 0 boxes      : {no_boxes_count}")
print(f"  No-helmet >= threshold     : {helmet_hits}  (would fire)")
print(f"  No-helmet < threshold      : {helmet_misses}  (suppressed)")
if crop_count == 0:
    print("\nDIAGNOSIS: No rider crops generated. Check IoU association.")
elif no_boxes_count == crop_count:
    print("\nDIAGNOSIS: Model returned 0 boxes for ALL crops. Crops likely too small/empty.")
elif helmet_hits == 0 and helmet_misses == 0:
    print("\nDIAGNOSIS: Model only predicted WITH-HELMET. Inspect saved crop images.")
elif helmet_misses > 0 and helmet_hits == 0:
    print(f"\nDIAGNOSIS: No-helmet detected but ALL below threshold ({HELMET_CONF_THRESHOLD}). Lower HELMET_CONF_THRESHOLD.")
print("=" * 70)
