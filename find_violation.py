from detection import run_detection, load_model
from violations import check_violations, reset_state
import os

vehicle_model = load_model('yolov8s.pt')
helmet_model = load_model(os.path.join('models', 'helmet_yolov8s_v2_motorcycle.pt'))

reset_state()

for frame_data in run_detection('test_videos/TripleHelm1.mp4', model=vehicle_model, save_output=False, frame_skip=1):
    v = check_violations(frame_data, helmet_model=helmet_model, enable_red_light=False)
    if v:
        print(f"Violation found at frame {frame_data['frame_number']}!")
        break
    if frame_data['frame_number'] > 300:
        break
