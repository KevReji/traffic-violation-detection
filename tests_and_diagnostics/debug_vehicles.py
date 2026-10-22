import cv2
import os
from detection import load_model, process_single_frame
import detection
detection.REVIEW_CONF_THRESHOLD = 0.1
from violations import check_violations, reset_state

def main():
    yolo_model = load_model("yolov8m.pt")
    helmet_model = load_model(os.path.join("models", "helmet_yolov8s_v2_motorcycle.pt"))
    
    test_files = ["2.jpg", "4.jpeg", "6.jpg", "9.png"]
    base_dir = "dataset/numberplates"
    
    for filename in test_files:
        path = os.path.join(base_dir, filename)
        frame = cv2.imread(path)
        if frame is None:
            continue
            
        reset_state()
        frame_data = process_single_frame(frame, yolo_model, frame_number=1)
        
        helmet_results = helmet_model(frame, verbose=False)[0]
        for box in helmet_results.boxes:
            cls = int(box.cls[0])
            name = helmet_model.names[cls]
            conf = float(box.conf[0])
            print(f" Helmet model detected: {name} ({conf:.2f}) at {[round(x,1) for x in box.xyxy[0].tolist()]}")
            
        violations = check_violations(
            frame_data, 
            helmet_model=helmet_model, 
            enable_red_light=False
        )
        
        for i, v in enumerate(violations):
            box_rounded = [round(b, 1) for b in v['box']]
            print(f"DEBUG: file={filename} index={i} box={box_rounded} type={v['violation_type']}")

if __name__ == "__main__":
    main()
