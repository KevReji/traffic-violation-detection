import cv2
import numpy as np
import easyocr
import re
import os
from ultralytics import YOLO

import urllib.request

def get_plate_crop_yolo(image):
    """
    Uses YOLOv8 to detect the license plate and returns a tightly padded crop.
    Requires a valid YOLOv8 license plate model in the directory.
    """
    model_path = "license_plate_detector.pt"
    
    if not os.path.exists(model_path):
        print(f"\n[ERROR] Model file '{model_path}' not found in the local directory.")
        print("To run this test, you must provide a YOLOv8 license plate detector model.")
        print("1. Download a pre-trained license plate model (e.g., from Roboflow Universe or Kaggle).")
        print("2. Rename the downloaded .pt file to 'license_plate_detector.pt'.")
        print("3. Place it in the root folder: C:\\Users\\steff\\Desktop\\traffic-violation-detection\\")
        print("Then run this script again.\n")
        return None, None
        
    try:
        model = YOLO(model_path)
    except Exception as e:
        print(f"[ERROR] Failed to load YOLO model: {e}")
        return None, None
        
    # Run YOLO detection on the image
    results = model(image, conf=0.10, verbose=False)
    
    best_box = None
    best_conf = 0.0
    
    # Filter detections for confidence > 0.10
    for r in results:
        for box in r.boxes:
            conf = float(box.conf[0])
            if conf > 0.10 and conf > best_conf:
                best_conf = conf
                best_box = [int(v) for v in box.xyxy[0].tolist()]
                
    if best_box is None:
        print("[DEBUG] YOLO found no license plates with confidence > 0.10.")
        return None, None
        
    x1, y1, x2, y2 = best_box
    
    # Apply 5-pixel padding on all sides, clamped to image boundaries
    h, w = image.shape[:2]
    x1 = max(0, x1 - 5)
    y1 = max(0, y1 - 5)
    x2 = min(w, x2 + 5)
    y2 = min(h, y2 + 5)
    
    print(f"[DEBUG] YOLO Plate Detected! Bounding Box (padded): [{x1}, {y1}, {x2}, {y2}] | Confidence: {best_conf:.4f}")
    
    cropped = image[y1:y2, x1:x2]
    return cropped, [x1, y1, x2, y2]

def preprocess_roi(roi):
    """
    Apply requested preprocessing: 3x upscale (INTER_CUBIC) + light sharpening
    """
    if roi is None or roi.size == 0:
        return roi
        
    # 1. Upscale by 3x (INTER_CUBIC)
    h, w = roi.shape[:2]
    upscaled_color = cv2.resize(roi, (w * 3, h * 3), interpolation=cv2.INTER_CUBIC)
    
    # 2. Light Sharpening (Variant 1)
    kernel = np.array([[-1, -1, -1],
                       [-1,  9, -1],
                       [-1, -1, -1]])
    sharpened = cv2.filter2D(upscaled_color, -1, kernel)
    
    return sharpened

def post_process_text(text):
    """
    Strip whitespace and filter with regex
    """
    clean_text = "".join(text.split())
    # Extract only alphanumeric sequences
    clean_text = re.sub(r'[^A-Z0-9]', '', clean_text.upper())
    return clean_text

def main():
    img_path = os.path.join("dataset", "numberplates", "your_photo.jpg")
    
    # Fallback to uppercase Dataset if needed
    if not os.path.exists(img_path):
        img_path = os.path.join("Dataset", "numberplates", "your_photo.jpg")
        
    if not os.path.exists(img_path):
        print(f"Error: Could not find image at {img_path}")
        return

    print(f"Loading image from {img_path}...")
    image = cv2.imread(img_path)
    
    # 1. YOLO Plate Localization
    raw_crop, bbox = get_plate_crop_yolo(image)
    if raw_crop is None or raw_crop.size == 0:
        print("Error: Could not extract a valid crop using YOLO.")
        return
        
    # Save debug image
    cv2.imwrite("debug_yolo_crop.jpg", raw_crop)
    print("\n[DEBUG] Saved raw padded YOLO crop to 'debug_yolo_crop.jpg'\n")
    
    # 2. ROI Preprocessing
    print("Applying preprocessing (3x upscale + light sharpening)...")
    preprocessed_roi = preprocess_roi(raw_crop)
    
    # 3. OCR Execution
    print("Initializing EasyOCR (CPU)...")
    reader = easyocr.Reader(['en'], gpu=False, verbose=False)
    
    print("Running OCR on preprocessed crop...")
    allowlist = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    
    # Using previous settings optimized for two-line plates
    results = reader.readtext(
        preprocessed_roi, 
        allowlist=allowlist,
        paragraph=False,
        text_threshold=0.3, 
        low_text=0.3, 
        link_threshold=0.3,
        mag_ratio=2.0
    )
    
    if not results:
        print("\nNo text detected by EasyOCR.")
        return
        
    # Sort top-to-bottom, left-to-right
    def sort_key(res):
        box = res[0]
        y_coord = box[0][1]
        x_coord = box[0][0]
        return (int(y_coord / 25), x_coord)
        
    results.sort(key=sort_key)
    
    # 4. Post-Processing & Output
    combined_text = " ".join([res[1] for res in results])
    final_processed_text = post_process_text(combined_text)
    
    print("\n" + "="*40)
    print("       FINAL YOLO + OCR RESULT")
    print("="*40)
    print(f"BBox Coordinates: {bbox}")
    print(f"Raw Combined:     '{combined_text}'")
    print(f"Processed:        '{final_processed_text}'")
    print("="*40 + "\n")

if __name__ == "__main__":
    main()
