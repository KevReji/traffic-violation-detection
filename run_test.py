import sys
import os
import shutil

# Make sure debug_crops is empty before running to avoid confusion
if os.path.exists('debug_crops'):
    shutil.rmtree('debug_crops')

from detection import run_detection, load_model
model = load_model('yolov8s.pt')
for frame_data in run_detection('test_videos/dashcam_test.mp4', model=model, save_output=False, frame_skip=1):
    pass
