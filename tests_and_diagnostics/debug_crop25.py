import cv2
import os
from detection import load_model, process_single_frame
from violations import check_violations, reset_state, compute_iou
import detection
import violations

yolo_model = load_model("yolov8m.pt")
helmet_model = load_model(os.path.join("models", "helmet_yolov8s_v2_motorcycle.pt"))

frame = cv2.imread(r"C:/Users/steff/.gemini/antigravity/brain/f31d302d-5582-4f24-a04d-d07dd4982901/.user_uploaded/media_1790324757253.jpg")
frame_data = process_single_frame(frame, yolo_model, frame_number=1)

persons = [v for v in frame_data["detections"] if v["class_name"] == "person"]
motos = [v for v in frame_data["detections"] if v["class_name"] == "motorcycle"]

print(f"Detected {len(persons)} persons and {len(motos)} motorcycles.")

for i, p in enumerate(persons):
    for j, m in enumerate(motos):
        iou = compute_iou(p["box"], m["box"])
        if iou > 0.01:
            print(f"Person {i} overlaps Moto {j} with IoU: {iou:.3f}")
            x1, y1, x2, y2 = [int(v) for v in p["box"]]
            
            full_crop = frame[max(0, y1-10):min(frame.shape[0], y2+10), max(0, x1-10):min(frame.shape[1], x2+10)]
            h_res = helmet_model(full_crop, verbose=False)[0]
            for box in h_res.boxes:
                print(f"  FULL: {helmet_model.names[int(box.cls[0])]} {float(box.conf[0]):.3f}")
            
            head_y2 = y1 + int((y2 - y1) * 0.25)
            if head_y2 <= y1 or x2 <= x1: continue
            rider_crop = frame[y1:head_y2, x1:x2]
            h_res2 = helmet_model(rider_crop, verbose=False)[0]
            for box in h_res2.boxes:
                print(f"  TOP 25%: {helmet_model.names[int(box.cls[0])]} {float(box.conf[0]):.3f}")
