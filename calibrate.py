import cv2
import os
from ultralytics import YOLO

VIDEO_PATH = "test_videos/Redlight5.mp4"
model = YOLO("yolov8n.pt")
MAX_DISPLAY_HEIGHT = 900

def main():
    if not os.path.exists(VIDEO_PATH):
        print(f"Video {VIDEO_PATH} not found.")
        return
        
    cap = cv2.VideoCapture(VIDEO_PATH)
    ret, frame = cap.read()
    cap.release()
    
    if not ret:
        print("Failed to read frame.")
        return
        
    orig_h, orig_w = frame.shape[:2]
    scale = min(1.0, MAX_DISPLAY_HEIGHT / orig_h)
    
    results = model(frame, verbose=False)
    auto_light_coords = None
    for box in results[0].boxes:
        cls_id = int(box.cls[0])
        if model.names[cls_id] == 'traffic light' and float(box.conf[0]) > 0.2:
            b = box.xyxy[0].tolist()
            auto_light_coords = (int(b[0]), int(b[1]), int(b[2]), int(b[3]))
            break
            
    points = []
    
    def mouse_callback(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            if len(points) < 4:
                # Convert the clicked window coordinates back to original image resolution
                orig_x = int(x / scale)
                orig_y = int(y / scale)
                points.append((orig_x, orig_y))
    
    cv2.namedWindow("Calibration")
    cv2.setMouseCallback("Calibration", mouse_callback)
    
    print("INSTRUCTIONS:")
    print("1. Click 2 points to define the STOP_ZONES rectangle (top-left, bottom-right).")
    if auto_light_coords:
        print("   A traffic light was AUTO-DETECTED (yellow box).")
    else:
        print("   NO traffic light auto-detected. Click 2 MORE points to define LIGHT_REGION.")
    print("2. Press 's' to save and print results.")
    print("3. Press 'q' to quit.")
    
    while True:
        # Draw on a copy of the ORIGINAL high-resolution frame
        canvas = frame.copy()
        
        if auto_light_coords:
            x1, y1, x2, y2 = auto_light_coords
            cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 255, 255), 2)
            cv2.putText(canvas, "AUTO-LIGHT", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            
        for p in points:
            cv2.circle(canvas, p, 4, (0, 0, 255), -1)
            
        if len(points) >= 2:
            cv2.rectangle(canvas, points[0], points[1], (0, 0, 255), 2)
            cv2.putText(canvas, "STOP ZONE", (points[0][0], points[0][1]-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
        if len(points) == 4:
            cv2.rectangle(canvas, points[2], points[3], (0, 165, 255), 2)
            cv2.putText(canvas, "MANUAL LIGHT", (points[2][0], points[2][1]-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
            
        # Resize the fully annotated high-res canvas down to screen-friendly size for display
        new_w = int(orig_w * scale)
        new_h = int(orig_h * scale)
        display_frame = cv2.resize(canvas, (new_w, new_h))
        
        cv2.imshow("Calibration", display_frame)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('s'):
            stop_zone = (points[0][0], points[0][1], points[1][0], points[1][1]) if len(points) >= 2 else None
            light_region = auto_light_coords
            if len(points) == 4:
                light_region = (points[2][0], points[2][1], points[3][0], points[3][1])
                
            print("\n--- CALIBRATION RESULTS ---")
            if light_region:
                print(f"LIGHT_REGION = {light_region}")
            if stop_zone:
                print(f"STOP_ZONES = [{stop_zone}]")
                
            os.makedirs("debug_traffic", exist_ok=True)
            vid_name = os.path.basename(VIDEO_PATH).split('.')[0]
            out_path = f"debug_traffic/calibration_{vid_name}.jpg"
            cv2.imwrite(out_path, canvas) # Save the high-res canvas, not the resized display
            print(f"Screenshot saved to {out_path}")
            break
            
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
