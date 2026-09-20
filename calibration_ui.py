import streamlit as st
import cv2
import numpy as np
from streamlit_image_coordinates import streamlit_image_coordinates
from ultralytics import YOLO
from PIL import Image

def render_calibration(frame):
    if "calib_auto_light" not in st.session_state:
        model = YOLO("yolov8n.pt")
        results = model(frame, verbose=False)
        auto_light_coords = None
        for box in results[0].boxes:
            cls_id = int(box.cls[0])
            if model.names[cls_id] == 'traffic light' and float(box.conf[0]) > 0.2:
                b = box.xyxy[0].tolist()
                auto_light_coords = (int(b[0]), int(b[1]), int(b[2]), int(b[3]))
                break
        st.session_state["calib_auto_light"] = auto_light_coords
        st.session_state["calib_clicks"] = []

    auto_light = st.session_state["calib_auto_light"]
    clicks = st.session_state["calib_clicks"]
    target_clicks = 2 if auto_light else 4

    display_frame = frame.copy()
    
    if auto_light:
        x1, y1, x2, y2 = auto_light
        cv2.rectangle(display_frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
        cv2.putText(display_frame, "AUTO-LIGHT", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

    for c in clicks:
        cv2.circle(display_frame, (c["x"], c["y"]), 5, (0, 0, 255), -1)

    if len(clicks) >= 2:
        cv2.line(display_frame, (clicks[0]["x"], clicks[0]["y"]), (clicks[1]["x"], clicks[1]["y"]), (0, 0, 255), 2)
        cv2.putText(display_frame, "STOP LINE", (clicks[0]["x"], clicks[0]["y"]-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    if len(clicks) == 4:
        cv2.rectangle(display_frame, (clicks[2]["x"], clicks[2]["y"]), (clicks[3]["x"], clicks[3]["y"]), (0, 165, 255), 2)
        cv2.putText(display_frame, "MANUAL LIGHT", (clicks[2]["x"], clicks[2]["y"]-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)

    display_rgb = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(display_rgb)

    st.write("### Red-Light Calibration")
    if auto_light:
        st.info("A traffic light was **auto-detected** (yellow). Please click **2 points** along the painted stop line to define the STOP LINE.")
    else:
        st.warning("No traffic light auto-detected. Click **2 points** for the STOP LINE, then **2 MORE points** for the LIGHT REGION.")

    value = streamlit_image_coordinates(pil_img, key="calib_image")

    if value is not None:
        if "last_click" not in st.session_state or st.session_state["last_click"] != value:
            if len(clicks) < target_clicks:
                clicks.append(value)
                st.session_state["calib_clicks"] = clicks
                st.session_state["last_click"] = value
                st.rerun()

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Clear Clicks"):
            st.session_state["calib_clicks"] = []
            st.session_state["last_click"] = None
            st.rerun()
    with col2:
        if auto_light and st.button("Clear Auto-Detection & Draw Manually"):
            st.session_state["calib_auto_light"] = None
            st.session_state["calib_clicks"] = []
            st.session_state["last_click"] = None
            st.rerun()

    if len(clicks) == target_clicks:
        if st.button("Confirm Calibration", type="primary"):
            stop_line = ((clicks[0]['x'], clicks[0]['y']), (clicks[1]['x'], clicks[1]['y']))
            light_region = auto_light
            if not auto_light:
                light_region = (clicks[2]["x"], clicks[2]["y"], clicks[3]["x"], clicks[3]["y"])
                
            return {
                "LIGHT_REGION": light_region,
                "STOP_LINE": stop_line
            }

    return None
