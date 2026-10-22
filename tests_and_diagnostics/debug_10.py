import cv2
import os
from detection import load_model, process_single_frame
from violations import check_violations, reset_state, compute_iou, _find_associated_persons

yolo_model = load_model("yolov8s.pt")
frame = cv2.imread(os.path.join("dataset", "numberplates", "10.png"))

frame_data = process_single_frame(frame, yolo_model, frame_number=1)
persons = [v for v in frame_data["detections"] if v["class_name"] == "person"]
motos = [v for v in frame_data["detections"] if v["class_name"] == "motorcycle"]

for j, moto in enumerate(motos):
    associated = _find_associated_persons(moto["box"], persons)
    if len(associated) >= 3:
        print(f"\n[TRIPLE RIDING TRIGGERED] Moto {j}")
        for i, p in enumerate(associated):
            iou = compute_iou(moto["box"], p["box"])
            px_center = (p["box"][0] + p["box"][2]) / 2.0
            print(f"  -> Rider {i}: Box {p['box']} | IoU: {iou:.3f} | Center: {px_center:.1f} (in [{moto['box'][0]}, {moto['box'][2]}])")
