import os
import glob
import cv2
from ultralytics import YOLO

# 1. List all model weights you want to compare
MODELS_TO_TEST = [
    "license_plate_detector1.pt",
    "license_plate_detector2.pt",
    "license_plate_detector3.pt"
]

# 2. Input directory and confidence threshold settings
IMAGE_DIR = r"dataset\numberplates"
BASE_OUTPUT_DIR = r"debug_results"
CONF_THRESHOLD = 0.30  # Lowered to 0.30 to catch blurry/hard plates

# Collect test images
valid_extensions = ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.webp")
image_paths = []
for ext in valid_extensions:
    image_paths.extend(glob.glob(os.path.join(IMAGE_DIR, ext)))

if not image_paths:
    print(f"Error: No images found in '{IMAGE_DIR}'. Please check your path.")
    exit()

print(f"Found {len(image_paths)} test images. Comparing {len(MODELS_TO_TEST)} models...\n")

summary_stats = {}

# 3. Run comparison benchmark
for model_path in MODELS_TO_TEST:
    if not os.path.exists(model_path):
        print(f"⚠️ Model file '{model_path}' not found in project folder. Skipping...")
        continue

    model_name = os.path.splitext(os.path.basename(model_path))[0]
    model_output_dir = os.path.join(BASE_OUTPUT_DIR, model_name)
    os.makedirs(model_output_dir, exist_ok=True)

    print(f"========================================")
    print(f" Running Evaluation: {model_name}")
    print(f" Output Folder:     {model_output_dir}")
    print(f"========================================")

    model = YOLO(model_path)
    
    total_plates_detected = 0
    confidences = []
    images_with_detections = 0

    for img_path in image_paths:
        filename = os.path.basename(img_path)
        base_name, _ = os.path.splitext(filename)
        
        img = cv2.imread(img_path)
        if img is None:
            continue

        results = model(img, conf=CONF_THRESHOLD)[0]
        boxes = results.boxes

        annotated_img = img.copy()
        valid_boxes_in_image = 0

        for idx, box in enumerate(boxes):
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
            w = x2 - x1
            h = y2 - y1
            
            # --- ASPECT RATIO FILTER ---
            # Most real license plates have an aspect ratio between 1.2 and 5.0
            # A completely square bounding box (AR ~ 1.0) like the foot/sandal false positive will be rejected here.
            aspect_ratio = float(w) / float(h) if h > 0 else 0
            if not (1.2 <= aspect_ratio <= 5.0):
                print(f"  [Filtered Out] Rejected box in {filename} due to Aspect Ratio: {aspect_ratio:.2f}")
                continue
                
            confidence = float(box.conf[0])
            confidences.append(confidence)
            total_plates_detected += 1
            valid_boxes_in_image += 1

            # Save individual plate crop
            crop = img[y1:y2, x1:x2]
            if crop.size > 0:
                crop_filename = f"crop_{base_name}_plate{idx + 1}.jpg"
                cv2.imwrite(os.path.join(model_output_dir, crop_filename), crop)

            # Draw green bounding box and confidence score
            cv2.rectangle(annotated_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(annotated_img, f"{confidence:.2f}", (x1, max(y1 - 10, 15)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        if valid_boxes_in_image > 0:
            images_with_detections += 1

        # Save annotated image (even if no plates, so we can verify empty frames)
        annotated_filename = f"annotated_{filename}"
        cv2.imwrite(os.path.join(model_output_dir, annotated_filename), annotated_img)

    avg_conf = (sum(confidences) / len(confidences)) if confidences else 0.0
    summary_stats[model_name] = {
        "images_matched": f"{images_with_detections}/{len(image_paths)}",
        "total_plates": total_plates_detected,
        "avg_confidence": f"{avg_conf * 100:.1f}%"
    }
    print(f"Done evaluating {model_name}.\n")

# 4. Print final benchmark comparison table
print("\n" + "=" * 55)
print("             MODEL BENCHMARK SUMMARY             ")
print("=" * 55)
for m_name, stats in summary_stats.items():
    print(f"Model: {m_name}")
    print(f"  • Images with Detections: {stats['images_matched']}")
    print(f"  • Total Plates Detected:  {stats['total_plates']}")
    print(f"  • Average Confidence:     {stats['avg_confidence']}")
    print("-" * 55)
