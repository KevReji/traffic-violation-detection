import cv2
import os
import shutil
from detection import load_model

if os.path.exists('debug_anpr'):
    shutil.rmtree('debug_anpr')
os.makedirs('debug_anpr', exist_ok=True)

vehicle_model = load_model('yolov8s.pt')
cap = cv2.VideoCapture('test_videos/dashcam_test.mp4')
fn = 0
while True:
    ret, frame = cap.read()
    if not ret: break
    
    if fn >= 190 and fn <= 192:
        results = vehicle_model.predict(frame, verbose=False)
        boxes = results[0].boxes
        fh, fw = frame.shape[:2]
        
        for v_idx, box in enumerate(boxes):
            cls_id = int(box.cls[0].item())
            v_type = vehicle_model.names[cls_id]
            
            if v_type not in ['car', 'motorcycle', 'bus', 'truck']:
                continue
                
            x1, y1, x2, y2 = [int(coord) for coord in box.xyxy[0]]
            x1 = max(0, x1); y1 = max(0, y1)
            x2 = min(fw, x2); y2 = min(fh, y2)
            
            if x2 <= x1 or y2 <= y1:
                continue
                
            veh_h = y2 - y1
            veh_w = x2 - x1
            
            plate_y1 = y1 + int(veh_h * 0.65)
            plate_y2 = y2
            
            h_margin = int(veh_w * 0.20)
            plate_x1 = x1 + h_margin
            plate_x2 = x2 - h_margin
            
            if plate_x2 <= plate_x1:
                plate_x1, plate_x2 = x1, x2
                
            plate_region = frame[plate_y1:plate_y2, plate_x1:plate_x2].copy()
            
            if plate_region.size > 0:
                h, w = plate_region.shape[:2]
                fname = f"debug_anpr/frame_{fn}_{v_type}_{v_idx}_crop.jpg"
                cv2.imwrite(fname, plate_region)
                print(f"[ANPR DEBUG] Frame {fn} | Vehicle {v_idx} ({v_type}) | Crop saved to {fname}, dimensions: {w}x{h}")
                
    if fn > 192:
        break
    fn += 1
cap.release()
print("Done.")
