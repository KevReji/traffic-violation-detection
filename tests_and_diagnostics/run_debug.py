import os
import shutil

# Make sure debug_crops is clean
if os.path.exists('debug_crops'):
    shutil.rmtree('debug_crops')
os.makedirs('debug_crops', exist_ok=True)

from detection import run_detection, load_model
from violations import check_violations, reset_state

# We use yolov8s.pt and helmet_yolov8s_v2_motorcycle.pt
vehicle_model = load_model('yolov8s.pt')
helmet_model = load_model(os.path.join('models', 'helmet_yolov8s_v2_motorcycle.pt'))

reset_state()

print("Starting generation...")
for i, frame_data in enumerate(run_detection('test_videos/dashcam_test.mp4', model=vehicle_model, save_output=False, frame_skip=1)):
    # Run check_violations
    v = check_violations(frame_data, helmet_model=helmet_model, enable_red_light=False)
    if frame_data['frame_number'] >= 195:
        break
print("Done processing.")
