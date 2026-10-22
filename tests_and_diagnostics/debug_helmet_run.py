import sys, os, cv2
import violations
violations.DEBUG_HELMET = True

from detection import load_model, run_detection
from violations import (reset_state, PERSON_MOTO_IOU_THRESHOLD,
    HELMET_CONF_THRESHOLD, _find_associated_persons)
from utils import compute_iou

VIDEO       = "tripleriding.mp4"
MAX_FRAMES  = 60
CROP_DIR    = "debug_helmet_crops"
HELMET_PT   = os.path.join("models", "helmet_yolov8s_v1_map74.pt")

os.makedirs(CROP_DIR, exist_ok=True)
print("Video:", VIDEO)
print("Helmet PT:", HELMET_PT)
print("Conf thresh:", HELMET_CONF_THRESHOLD)
print("IoU thresh:", PERSON_MOTO_IOU_THRESHOLD)

vm = load_model("yolov8s.pt")
hm = load_model(HELMET_PT)
print("Helmet classes:", hm.names)

reset_state()
fc = crop_c = hits = misses = zeros = 0

for fd in run_detection(VIDEO, model=vm, save_output=False):
    fn   = fd["frame_number"]
    dets = fd["detections"]
    orig = fd.get("original_frame")
    fh   = fd.get("frame_height", 0)
    fw   = fd.get("frame_width",  0)

    persons = [d for d in dets if d["class_name"] == "person"]
    motos   = [d for d in dets if d["class_name"] == "motorcycle"]

    if motos:
        print(f"\nFRAME {fn}  {fw}x{fh}  motos={len(motos)}  persons={len(persons)}")
        for mi, moto in enumerate(motos):
            riders = _find_associated_persons(moto["box"], persons)
            print(f"  Moto[{mi}] box={moto['box']} conf={moto['confidence']:.3f} riders={len(riders)}")
            for p in persons:
                iou = compute_iou(moto["box"], p["box"])
                tag = "ASSOC" if iou >= PERSON_MOTO_IOU_THRESHOLD else "skip"
                print(f"    person box={p['box']} iou={iou:.4f} {tag}")

            for ri, rider in enumerate(riders):
                b = rider["box"]
                x1,y1,x2,y2 = int(b[0]),int(b[1]),int(b[2]),int(b[3])
                cx1 = max(0,x1); cy1 = max(0,y1)
                cx2 = min(fw,x2); cy2 = min(fh,y2)
                cw = cx2-cx1; ch = cy2-cy1
                print(f"    Rider[{ri}] raw=({x1},{y1},{x2},{y2}) clamped=({cx1},{cy1},{cx2},{cy2}) size={cw}x{ch}")

                if orig is None or cw<=0 or ch<=0:
                    print("    !! bad crop - skipping")
                    continue

                head_cy2 = cy1 + int((cy2-cy1)*0.25); crop = orig[cy1:head_cy2, cx1:cx2]
                path = os.path.join(CROP_DIR, f"crop_f{fn:04d}_m{mi}_r{ri}.jpg")
                cv2.imwrite(path, crop)
                crop_c += 1
                print(f"    SAVED: {path}")

                try:
                    res = hm(crop, verbose=False)
                except Exception as e:
                    print(f"    !! EXCEPTION: {e}")
                    continue

                nb = sum(len(r.boxes) for r in res)
                print(f"    Helmet boxes: {nb}")
                if nb == 0:
                    zeros += 1
                    print("    >> ZERO detections from helmet model")
                    continue

                for r in res:
                    for box in r.boxes:
                        cid  = int(box.cls[0])
                        conf = float(box.conf[0])
                        cn   = hm.names.get(cid,"?").lower()
                        is_nh = ("without" in cn and "helmet" in cn) or ("no" in cn and "helmet" in cn)
                        if is_nh:
                            if conf >= HELMET_CONF_THRESHOLD:
                                print(f"    cls={cn} conf={conf:.4f} >>> FIRE <<<")
                                hits += 1
                            else:
                                print(f"    cls={cn} conf={conf:.4f} SUPPRESSED (thresh={HELMET_CONF_THRESHOLD})")
                                misses += 1
                        else:
                            print(f"    cls={cn} conf={conf:.4f} (with-helmet - no violation)")

    fc += 1
    if fc >= MAX_FRAMES:
        break

print("\n=== SUMMARY ===")
print(f"Frames: {fc}  Crops: {crop_c}  ZeroBoxes: {zeros}  Hits: {hits}  Suppressed: {misses}")
if crop_c == 0:
    print("DIAGNOSIS: No rider crops generated. Check IoU threshold.")
elif zeros == crop_c:
    print("DIAGNOSIS: Helmet model returned ZERO boxes for ALL crops.")
    print("  Likely cause: crops too small, wrong region, or below model's internal conf threshold.")
elif hits == 0 and misses == 0:
    print("DIAGNOSIS: Model only predicted with-helmet for every crop.")
    print("  Inspect the saved crop images to check what the model is seeing.")
elif hits == 0 and misses > 0:
    print(f"DIAGNOSIS: No-helmet detected but ALL below HELMET_CONF_THRESHOLD={HELMET_CONF_THRESHOLD}.")
    print("  FIX: Lower HELMET_CONF_THRESHOLD.")
else:
    print(f"DIAGNOSIS: {hits} crops would fire, {misses} suppressed. Looks functional.")
