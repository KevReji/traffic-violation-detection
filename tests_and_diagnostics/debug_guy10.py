import cv2
import os
from detection import load_model, process_single_frame
from violations import check_violations, reset_state, compute_iou
import detection
import violations

yolo_model = load_model("yolov8m.pt")
helmet_model = load_model(os.path.join("models", "helmet_yolov8s_v2_motorcycle.pt"))

# The user's image is media_1790324757253.jpg, which corresponds to the same scene 
# where Guy 10 is. Wait, the user said "what about this guy?" and the image is media...
# The image looks like it's from `10.png` or `7.png`? 
# "AP28 R 8104" is the license plate.
# Let me search for AP28 R 8104 or just process all images again.
# Wait, let's just find the file that contains this.
test_files = ["1.jpg", "2.jpg", "3.jpg", "4.jpeg", "5.png", "6.jpg", "7.png", "8.png", "9.png", "10.png"]

for f in test_files:
    frame = cv2.imread(os.path.join("dataset", "numberplates", f))
    if frame is None: continue
    
    frame_data = process_single_frame(frame, yolo_model, frame_number=1)
    
    # We want to find a person bounding box and a motorcycle bounding box that match Guy 10.
    # Person box approx [480, 140, 740, 820]
    # Moto box approx [420, 390, 810, 960]
    
    persons = [v for v in frame_data["detections"] if v["class_name"] == "person"]
    motos = [v for v in frame_data["detections"] if v["class_name"] == "motorcycle"]
    
    for i, p in enumerate(persons):
        for j, m in enumerate(motos):
            iou = compute_iou(p["box"], m["box"])
            if iou > 0.01:
                    print(f"File {f}: Person {i} overlaps Moto {j} with IoU: {iou:.3f}")
                    px1, py1, px2, py2 = [int(v) for v in p["box"]]
                    crop = frame[max(0, py1-10):min(frame.shape[0], py2+10), max(0, px1-10):min(frame.shape[1], px2+10)]
                    if crop.size > 0:
                        h_res = helmet_model(crop, verbose=False)[0]
                        print("Helmet model saw:", len(h_res.boxes))
                        for box in h_res.boxes:
                            cls = int(box.cls[0])
                            name = helmet_model.names[cls]
                            conf = float(box.conf[0])
                            print(f"   -> Helmet Model sees: {name} ({conf:.3f})")

