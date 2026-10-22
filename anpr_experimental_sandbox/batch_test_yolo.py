import os
import glob
import cv2
from ultralytics import YOLO

# 1. Load YOLO detector model
MODEL_PATH = "license_plate_detector.pt"
model = YOLO(MODEL_PATH)

# 2. Input folder and output results folder
IMAGE_DIR = r"dataset\numberplates"
OUTPUT_DIR = r"debug_results"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 3. Collect all images in directory (.jpg, .jpeg, .png, etc.)
valid_extensions = ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.webp")
image_paths = []
for ext in valid_extensions:
    image_paths.extend(glob.glob(os.path.join(IMAGE_DIR, ext)))

if not image_paths:
    print(f"Error: No images found in '{IMAGE_DIR}'. Please check the directory path.")
    exit()

print(f"Found {len(image_paths)} images in '{IMAGE_DIR}'. Starting batch detection...\n")

CONF_THRESHOLD = 0.30  # Adjusted to catch more conservative detections

for img_path in image_paths:
    filename = os.path.basename(img_path)
    base_name, _ = os.path.splitext(filename)
    
    img = cv2.imread(img_path)
    if img is None:
        print(f"⚠️ Could not load image: {filename}")
        continue

    # Run detection
    results = model(img, conf=CONF_THRESHOLD)[0]
    boxes = results.boxes

    print(f"--- {filename} ---")
    print(f"Plates Found: {len(boxes)}")

    if len(boxes) == 0:
        print(f"  ❌ No plate detected at confidence >= {CONF_THRESHOLD}\n")
        continue

    annotated_img = img.copy()

    for idx, box in enumerate(boxes):
        confidence = float(box.conf[0])
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)

        print(f"  - Plate #{idx + 1}: Conf = {confidence:.4f} ({confidence * 100:.1f}%) | Box = [{x1}, {y1}, {x2}, {y2}]")

        # Save individual crop
        crop = img[y1:y2, x1:x2]
        crop_filename = f"crop_{base_name}_plate{idx + 1}.jpg"
        cv2.imwrite(os.path.join(OUTPUT_DIR, crop_filename), crop)

        # Draw green bounding box and confidence text
        cv2.rectangle(annotated_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(annotated_img, f"Plate {confidence:.2f}", (x1, max(y1 - 10, 15)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    # Save full image with bounding boxes drawn
    annotated_filename = f"annotated_{filename}"
    cv2.imwrite(os.path.join(OUTPUT_DIR, annotated_filename), annotated_img)
    print(f"  Saved: 'crop_{base_name}_plate1.jpg' & 'annotated_{filename}'\n")

print(f"Batch detection complete! Open the '{OUTPUT_DIR}' folder to inspect all crops and annotated images.")
