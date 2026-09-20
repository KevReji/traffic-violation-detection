import os
import shutil
import cv2

if os.path.exists('debug_anpr'):
    shutil.rmtree('debug_anpr')
os.makedirs('debug_anpr', exist_ok=True)

from detection import run_detection, load_model
from anpr import detect_and_read_plate

vehicle_model = load_model('yolov8s.pt')

print("Starting ANPR crop investigation on TripleHelm1.mp4...")
for i, frame_data in enumerate(run_detection('test_videos/TripleHelm1.mp4', model=vehicle_model, save_output=False, frame_skip=1)):
    fn = frame_data['frame_number']
    frame = frame_data['original_frame']
    
    for v_idx, v in enumerate(frame_data['detections']):
        v_type = v['class_name']
        box = v['box']
        
        # Call the EXACT detect_and_read_plate function from anpr.py
        result = detect_and_read_plate(frame, box, violation_id=9999)
        plate_region = result.get('plate_crop')
        
        if plate_region is not None and plate_region.size > 0:
            h, w = plate_region.shape[:2]
            fname = f"debug_anpr/frame_{fn}_{v_type}_{v_idx}_crop.jpg"
            cv2.imwrite(fname, plate_region)
            print(f"[ANPR DEBUG] Frame {fn} | Vehicle {v_idx} ({v_type}) | Crop saved to {fname}, dimensions: {w}x{h}")
            
    if fn >= 3:
        break
print("Done processing.")
