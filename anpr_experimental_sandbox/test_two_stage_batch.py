import os
import glob
import cv2
import numpy as np
from ultralytics import YOLO

# 1. Pipeline Models
VEHICLE_MODEL_PATH = "yolov8n.pt"  # Pre-trained COCO model
PLATE_MODEL_PATH = "license_plate_detector1.pt"

# 2. Directory Setup
IMAGE_DIR = r"dataset\numberplates"
OUTPUT_DIR = r"debug_results\two_stage"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Validate models
for mp in [VEHICLE_MODEL_PATH, PLATE_MODEL_PATH]:
    if not os.path.exists(mp):
        print(f"Error: Required model '{mp}' not found in project directory.")
        exit()

print("Loading models...")
vehicle_model = YOLO(VEHICLE_MODEL_PATH)
plate_model = YOLO(PLATE_MODEL_PATH)

# COCO Class IDs for vehicles: 2=Car, 3=Motorcycle, 5=Bus, 7=Truck
VEHICLE_CLASSES = [2, 3, 5, 7]

valid_extensions = ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.webp")
image_paths = []
for ext in valid_extensions:
    image_paths.extend(glob.glob(os.path.join(IMAGE_DIR, ext)))

if not image_paths:
    print(f"Error: No images found in '{IMAGE_DIR}'.")
    exit()

print(f"Found {len(image_paths)} images. Starting Two-Stage Pipeline...\n")

for img_path in image_paths:
    filename = os.path.basename(img_path)
    base_name, _ = os.path.splitext(filename)
    
    img = cv2.imread(img_path)
    if img is None:
        continue
        
    img_h, img_w = img.shape[:2]
    annotated_img = img.copy()
    
    print(f"--- Processing {filename} ---")
    
    # ==========================================
    # STAGE 1: VEHICLE DETECTION
    # ==========================================
    vehicle_results = vehicle_model(img, classes=VEHICLE_CLASSES, conf=0.30, verbose=False)[0]
    vehicles = vehicle_results.boxes
    
    plates_found_in_image = 0
    
    for v_idx, v_box in enumerate(vehicles):
        vx1, vy1, vx2, vy2 = v_box.xyxy[0].cpu().numpy().astype(int)
        v_conf = float(v_box.conf[0])
        
        # Apply 5% Safety Padding
        vw, vh = vx2 - vx1, vy2 - vy1
        pad_w, pad_h = int(vw * 0.05), int(vh * 0.05)
        
        pvx1 = max(0, vx1 - pad_w)
        pvy1 = max(0, vy1 - pad_h)
        pvx2 = min(img_w, vx2 + pad_w)
        pvy2 = min(img_h, vy2 + pad_h)
        
        vehicle_crop = img[pvy1:pvy2, pvx1:pvx2]
        if vehicle_crop.size == 0:
            continue
            
        # Draw vehicle bounding box (Green)
        cv2.rectangle(annotated_img, (pvx1, pvy1), (pvx2, pvy2), (0, 255, 0), 2)
        cv2.putText(annotated_img, f"Vehicle {v_conf:.2f}", (pvx1, max(pvy1 - 10, 15)), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                    
        # Save vehicle crop for debugging
        v_crop_filename = f"{base_name}_v{v_idx + 1}.jpg"
        cv2.imwrite(os.path.join(OUTPUT_DIR, v_crop_filename), vehicle_crop)
        
        # ==========================================
        # STAGE 2: PLATE DETECTION (ON CROP)
        # ==========================================
        # Run plate detector strictly on the padded vehicle crop
        plate_results = plate_model(vehicle_crop, conf=0.25, verbose=False)[0]
        plates = plate_results.boxes
        
        for p_idx, p_box in enumerate(plates):
            px1, py1, px2, py2 = p_box.xyxy[0].cpu().numpy().astype(int)
            p_conf = float(p_box.conf[0])
            
            # Aspect Ratio Filter (1.2 to 5.0)
            pw = px2 - px1
            ph = py2 - py1
            aspect_ratio = float(pw) / float(ph) if ph > 0 else 0
            
            if not (1.2 <= aspect_ratio <= 5.0):
                continue
                
            plates_found_in_image += 1
            
            # Extract high-res plate crop
            plate_crop = vehicle_crop[py1:py2, px1:px2]
            p_crop_filename = f"{base_name}_v{v_idx + 1}_plate{p_idx + 1}.jpg"
            cv2.imwrite(os.path.join(OUTPUT_DIR, p_crop_filename), plate_crop)
            
            # Global Coordinate Remapping
            # Map the local crop coordinates back to the full 1080p frame
            global_px1 = pvx1 + px1
            global_py1 = pvy1 + py1
            global_px2 = pvx1 + px2
            global_py2 = pvy1 + py2
            
            # Draw plate bounding box (Blue)
            cv2.rectangle(annotated_img, (global_px1, global_py1), (global_px2, global_py2), (255, 0, 0), 2)
            cv2.putText(annotated_img, f"Plate {p_conf:.2f}", (global_px1, max(global_py1 - 10, 15)), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

    print(f"  Vehicles Found: {len(vehicles)} | Valid Plates Found: {plates_found_in_image}")
    
    # Save full annotated scene
    annotated_filename = f"annotated_{filename}"
    cv2.imwrite(os.path.join(OUTPUT_DIR, annotated_filename), annotated_img)

print("\nPipeline execution complete! Check 'debug_results\\two_stage' for full annotated images and isolated crops.")
