import os
import shutil
import cv2

if os.path.exists('debug_anpr'):
    shutil.rmtree('debug_anpr')
os.makedirs('debug_anpr', exist_ok=True)

from detection import run_detection, load_model

vehicle_model = load_model('yolov8s.pt')

print("Starting generation...")
for i, frame_data in enumerate(run_detection('test_videos/dashcam_test.mp4', model=vehicle_model, save_output=False, frame_skip=1)):
    fn = frame_data['frame_number']
    frame = frame_data['original_frame']
    fh, fw = frame.shape[:2]
    
    for v_idx, v in enumerate(frame_data['detections']):
        x1, y1, x2, y2 = [int(coord) for coord in v['box']]
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
            v_type = v['class_name']
            fname = f"debug_anpr/frame_{fn}_{v_type}_{v_idx}_crop.jpg"
            cv2.imwrite(fname, plate_region)
            print(f"[ANPR DEBUG] Frame {fn} | Vehicle {v_idx} ({v_type}) | Crop saved to {fname}, dimensions: {w}x{h}")
            
    if fn >= 195:
        break
print("Done processing.")
