import sys, os
sys.path.append(r"c:\Users\steff\Desktop\traffic-violation-detection")
os.chdir(r"c:\Users\steff\Desktop\traffic-violation-detection")
import cv2
from detection import load_model, process_single_frame
from violations import check_violations, _find_associated_persons, detect_helmet_violation

img_path = r"C:\Users\steff\.gemini\antigravity\brain\f31d302d-5582-4f24-a04d-d07dd4982901\.user_uploaded\media_1792691706169_aca8ff81.jpg"
frame = cv2.imread(img_path)

v_model = load_model("yolov8m.pt")
h_model = load_model(os.path.join("models", "helmet_yolov8s_v2_motorcycle.pt"))

frame_data = process_single_frame(frame, v_model, 0, 0.0)
motos = [d for d in frame_data["detections"] if d["class_name"] == "motorcycle"]
persons = [d for d in frame_data["detections"] if d["class_name"] == "person"]
print("Total Detections:", len(frame_data["detections"]))
print("Motorcycles:", len(motos), "Persons:", len(persons))

for i, m in enumerate(motos):
    riders = _find_associated_persons(m["box"], persons)
    print(f"Moto {i}: box={m['box']}, conf={m['confidence']:.2f}, riders={len(riders)}")
    for j, r in enumerate(riders):
        h_res = detect_helmet_violation(r, m, frame=frame_data["original_frame"], helmet_model=h_model, frame_number=0)
        print(f"   Rider {j}: box={r['box']}, res={h_res}")

viols = check_violations(frame_data, helmet_model=h_model)
print(f"\nFinal violations returned: {len(viols)}")
for v in viols:
    print("  VIOLATION:", v["violation_type"], "conf=", v["confidence"], "review_needed=", v["review_needed"], "reason=", v["review_reason"], "box=", v["box"])
