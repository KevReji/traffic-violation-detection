import cv2
import os
import traffic_light

traffic_light.DEBUG_TRAFFIC_LIGHT = False
os.makedirs('debug_traffic', exist_ok=True)

# Using Box 2 from our YOLO discovery, padded slightly
light_region = (1720, 120, 1760, 180)

cap = cv2.VideoCapture('test_videos/Redlight4.mp4')
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
print(f"Total frames in video: {total_frames}")

# Test every 10th frame to see if it changes
frames_to_test = list(range(0, total_frames, max(1, total_frames // 10)))

for f in frames_to_test:
    cap.set(cv2.CAP_PROP_POS_FRAMES, f)
    ret, frame = cap.read()
    if not ret:
        break
        
    state = traffic_light.get_light_state(frame, light_region)
    print(f"Frame {f:>3}: detected color = {state}")
    
    x1, y1, x2, y2 = map(int, light_region)
    crop = frame[y1:y2, x1:x2]
    cv2.imwrite(f"debug_traffic/frame_{f:03d}_crop_{state}.jpg", crop)

cap.release()
