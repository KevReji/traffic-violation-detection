import streamlit as st
import cv2
import tempfile
from calibration_ui import render_calibration

st.set_page_config(page_title="Calibration Test", layout="wide")

st.title("Calibration UI Test")

# Add a quick bypass to use a default video if none uploaded for fast testing
use_default = st.checkbox("Use test_videos/Redlight5.mp4 instead of uploading", value=True)
uploaded = st.file_uploader("Upload a video", type=["mp4", "avi", "mov"])

video_path = None
if uploaded and not use_default:
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    tfile.write(uploaded.read())
    video_path = tfile.name
elif use_default:
    video_path = "test_videos/Redlight5.mp4"

if video_path:
    cap = cv2.VideoCapture(video_path)
    ret, frame = cap.read()
    cap.release()
    
    if ret:
        coords = render_calibration(frame)
        if coords:
            st.success("Calibration Confirmed!")
            st.json(coords)
    else:
        st.error(f"Could not read frame 0 from {video_path}.")
