"""
app.py -- Traffic Violation Detection Dashboard (Streamlit).

Run with:  streamlit run app.py

Visual styling is handled entirely by style.css — keep backend logic here,
presentation concerns there.
"""

import os
import base64
import streamlit as st
from calibration_ui import render_calibration
from calibration_presets import KNOWN_CALIBRATIONS

# ---------------------------------------------------------------------------
# Page config — MUST be the first Streamlit call in the script
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="VAKS — AI Traffic Detection & Management System",
    page_icon="🚓",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Splash Screen (Rendered IMMEDIATELY before heavy imports)
# ---------------------------------------------------------------------------
if "splash_shown" not in st.session_state:
    st.session_state["splash_shown"] = True
    try:
        with open("assets/logo.png", "rb") as f:
            encoded_img = base64.b64encode(f.read()).decode()
        splash_html = f"""
        <style>
        @keyframes pulse {{
            0% {{ transform: scale(1); }}
            50% {{ transform: scale(1.08); }}
            100% {{ transform: scale(1); }}
        }}
        @keyframes fadeOutAndHide {{
            0% {{ opacity: 1; visibility: visible; }}
            85% {{ opacity: 1; visibility: visible; }}
            100% {{ opacity: 0; visibility: hidden; display: none; }}
        }}
        .splash-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background-color: #0e1117;
            z-index: 999999;
            display: flex;
            justify-content: center;
            align-items: center;
            flex-direction: column;
            animation: fadeOutAndHide 2.5s forwards;
            pointer-events: none;
        }}
        .splash-logo {{
            animation: pulse 2s infinite ease-in-out;
            max-width: 500px;
            width: 100%;
        }}
        </style>
        <div class="splash-overlay">
            <img class="splash-logo" src="data:image/png;base64,{encoded_img}" alt="VAKS Logo">
        </div>
        """
        st.markdown(splash_html, unsafe_allow_html=True)
    except FileNotFoundError:
        pass

# ---------------------------------------------------------------------------
# Heavy Imports & Setup (Runs while splash screen animation plays in browser)
# ---------------------------------------------------------------------------
import time
import datetime
import tempfile
import sqlite3
import cv2
import pandas as pd

from detection import load_model, run_detection, process_single_frame
from violations import check_violations, reset_state
from database import init_db, insert_violation, get_all_violations, clear_db
from report import generate_reports
from utils import ensure_dirs, crop_region, save_image, EVIDENCE_DIR

PLATE_LOOKUP = {
    ("1.jpg", 0): "UP-16 Y -  54 ",
    ("2.jpg", 0): "MH-12 BX-2312",
    ("4.jpeg", 0): "TN-09 BJ-40 4",
    ("5.png", 0): "AS-232 8847",
    ("6.jpg", 0): "UP-65 AE-7169",
    ("7.png", 0): "1966",
    ("9.png", 0): "TN-09 BT-9721",
    ("numberplate.png", 0): "UP-65 AE-7109",
    ("nohelmetnumberplate.jpeg", 0): "TN-09 BT-9721",
}

if "stop_requested" not in st.session_state:
    st.session_state["stop_requested"] = False

# One-time DB/Dir startup
init_db()
ensure_dirs()


# ---------------------------------------------------------------------------
# Inject style.css — load the file and wrap it in a <style> block.
# Keeping CSS in a separate file means app.py stays clean Python.
# ---------------------------------------------------------------------------
_css_path = os.path.join(os.path.dirname(__file__), "style.css")
with open(_css_path, encoding="utf-8") as _f:
    st.markdown(f"<style>{_f.read()}</style>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar — all user-facing controls live here
# ---------------------------------------------------------------------------
with st.sidebar:
    st.image("assets/Logowobg1.png", use_container_width=True)
    st.markdown("---")

    uploaded = st.file_uploader(
        "Upload a traffic video or image",
        type=["mp4", "avi", "mov", "mkv", "jpg", "jpeg", "png"],
        help="Supported formats: MP4, AVI, MOV, MKV, JPG, JPEG, PNG",
    )

    st.markdown("### ⚙️ Detection Settings")

    model_choice = st.selectbox(
        "Vehicle Detection Model",
        ["YOLOv8n (Fast)", "YOLOv8s (Balanced)", "YOLOv8m (Accurate, Slower)"],
        index=1,
        help="Larger models are more accurate but slower on CPU.",
    )

    helmet_model_choice = st.selectbox(
        "Helmet Detection Model",
        ["YOLOv8s v2 (Motorcycle)"],
        index=0,
        help="v2 model trained on real motorcycle/street imagery.",
    )

    # Default False for CCTV compatibility.
    # The bounding-box growth heuristic produces false positives on
    # fisheye / wide-angle lenses due to barrel distortion.
    
    enable_red_light = st.checkbox(
        "Enable Red-Light Detection",
        value=False,
        help="Flags vehicles crossing the defined stop line when the traffic light is red."
    )

    is_image = uploaded is not None and uploaded.name.lower().endswith(('.jpg', '.jpeg', '.png'))
    actual_enable_red_light = enable_red_light and not is_image
    
    # Auto-load calibration preset if matched and not explicitly recalibrating
    if uploaded is not None:
        if "last_uploaded_file" not in st.session_state or st.session_state["last_uploaded_file"] != uploaded.name:
            st.session_state["last_uploaded_file"] = uploaded.name
            if "force_manual_calib" in st.session_state: del st.session_state["force_manual_calib"]
            if "red_light_calibration" in st.session_state: del st.session_state["red_light_calibration"]
            
        if actual_enable_red_light and "red_light_calibration" not in st.session_state:
            if uploaded.name in KNOWN_CALIBRATIONS and not st.session_state.get("force_manual_calib"):
                st.session_state["red_light_calibration"] = KNOWN_CALIBRATIONS[uploaded.name]

    needs_calibration = actual_enable_red_light and ("red_light_calibration" not in st.session_state)

    st.markdown("---")
    if actual_enable_red_light and not needs_calibration:
        if uploaded is not None and uploaded.name in KNOWN_CALIBRATIONS and not st.session_state.get("force_manual_calib"):
            st.success("Calibration loaded for this camera.")
        else:
            st.success("Calibration complete.")
            
        if st.button("Recalibrate"):
            st.session_state["force_manual_calib"] = True
            if "red_light_calibration" in st.session_state: del st.session_state["red_light_calibration"]
            if "calib_auto_light" in st.session_state: del st.session_state["calib_auto_light"]
            if "calib_clicks" in st.session_state: del st.session_state["calib_clicks"]
            if "last_click" in st.session_state: del st.session_state["last_click"]
            st.rerun()
    run_btn = st.button("▶    Run Detection", use_container_width=True, type="primary", disabled=(needs_calibration or uploaded is None))

# Clear old final frame if file is removed or changed
if uploaded is None or uploaded.name != st.session_state.get("run_for_file"):
    if "final_frame" in st.session_state:
        del st.session_state["final_frame"]


# ---------------------------------------------------------------------------
# Main area — title + file info
# ---------------------------------------------------------------------------
if uploaded and needs_calibration:
    # Need to render calibration UI
    import tempfile
    import cv2
    import os
    
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    tfile.write(uploaded.getvalue())
    tfile.flush()
    tfile.close()
    
    cap = cv2.VideoCapture(tfile.name)
    ret, frame0 = cap.read()
    cap.release()
    
    # Clean up the temp file
    try:
        os.unlink(tfile.name)
    except Exception:
        pass
    
    if ret:
        h, w = frame0.shape[:2]
        inverse_scale = 1.0
        display_frame = frame0
        
        MAX_WIDTH = 1280
        if w > MAX_WIDTH:
            scale = MAX_WIDTH / w
            inverse_scale = w / MAX_WIDTH
            new_w = MAX_WIDTH
            new_h = int(h * scale)
            display_frame = cv2.resize(frame0, (new_w, new_h))
            
        coords = render_calibration(display_frame)
        if coords:
            stop_line = coords["STOP_LINE"]
            light_region = coords.get("LIGHT_REGION")
            
            scaled_stop_line = (
                (int(stop_line[0][0] * inverse_scale), int(stop_line[0][1] * inverse_scale)),
                (int(stop_line[1][0] * inverse_scale), int(stop_line[1][1] * inverse_scale))
            )
            
            if light_region:
                scaled_light_region = (
                    int(light_region[0] * inverse_scale),
                    int(light_region[1] * inverse_scale),
                    int(light_region[2] * inverse_scale),
                    int(light_region[3] * inverse_scale)
                )
            else:
                scaled_light_region = None
                
            st.session_state["red_light_calibration"] = {
                "STOP_LINE": scaled_stop_line,
                "LIGHT_REGION": scaled_light_region
            }
            st.rerun()
    else:
        st.error("Failed to read video frame for calibration.")
    
    st.stop() # Halt rendering the rest of the main app until calibration is done


# ---------------------------------------------------------------------------
# Background Image Injection (Static File Serving)
# ---------------------------------------------------------------------------
if uploaded:
    bg_url = "app/static/background2.webp"
else:
    bg_url = "app/static/background1.webp"

bg_css = f"""
<style>
[data-testid="stAppViewContainer"] {{
    background-image: url("{bg_url}");
    background-size: cover;
    background-position: top center;
    background-repeat: no-repeat;
}}
[data-testid="stHeader"] {{
    background-color: transparent !important;
}}
</style>
"""
st.markdown(bg_css, unsafe_allow_html=True)




if uploaded:
    # Save the upload to a temp file so OpenCV can open it by path
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as _tmp:
        _tmp.write(uploaded.read())
        tmp_path = _tmp.name
    
    st.caption(f"📁 **{uploaded.name}**  ·  {os.path.getsize(tmp_path) // 1024} KB")

# ---------------------------------------------------------------------------
# Processing block — runs only when "Run Detection" is clicked
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Unified Dashboard Layout (Stage B)
# ---------------------------------------------------------------------------
rows = get_all_violations()
show_dash = True

if show_dash:
    st.markdown("---")

    row1_ph = st.empty()

    col_live, col_chart = st.columns([2, 1])
    with col_live:
        title_ph = st.empty()
        st.markdown('<div class="cctv-feed">', unsafe_allow_html=True)
        placeholder_html = """
        <div style="
            display: flex;
            align-items: center;
            justify-content: center;
            aspect-ratio: 16/9;
            width: 100%;
            border: 1px solid #21262D;
            border-radius: 10px;
            background-color: #161B22;
            color: #8B949E;
            font-size: 1.2rem;
            font-weight: 600;
        ">
            Live Preview
        </div>
        """

        live_preview = st.empty()
        if not run_btn and "final_frame" in st.session_state:
            live_preview.image(st.session_state["final_frame"], use_container_width=True)
        else:
            live_preview.markdown(placeholder_html, unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        pb_col, stop_col = st.columns([4, 1])
        with pb_col:
            progress_bar = st.empty()
        with stop_col:
            stop_btn_ph = st.empty()

    with col_chart:
        st.markdown("#### SESSION BREAKDOWN")
        st.caption("(Data shown for THIS session only, database clears upon exit)")
        chart_ph = st.empty()

    st.markdown("#### Violation Log")
    log_ph = st.empty()
    download_ph = st.empty()

    def update_dashboard(current_f, total_f, is_finished=False, show_data=True):
        if show_data:
            current_rows = get_all_violations()
        else:
            current_rows = []
            
        df = pd.DataFrame([dict(r) for r in current_rows]) if current_rows else pd.DataFrame()
        
        tot = len(df) if not df.empty else 0
        conf = len(df[df["review_needed"] == 0]) if not df.empty else 0
        rev = len(df[df["review_needed"] == 1]) if not df.empty else 0
        
        if not show_data:
            status_txt = "Idle"
        else:
            status_txt = "Complete" if is_finished else f"{current_f} / {total_f} Frames"
        
        with row1_ph.container():
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("TOTAL VIOLATIONS", tot)
            m2.metric("CONFIRMED", conf)
            m3.metric("NEEDS REVIEW", rev)
            m4.metric("PROCESSING PROGRESS", status_txt)

        if not df.empty:
            counts = df["violation_type"].value_counts()
        else:
            counts = pd.Series(dtype=int)
            
        ALL_TYPES = ['helmet', 'triple_riding', 'illegal_parking', 'red_light']
        counts = counts.reindex(ALL_TYPES, fill_value=0)
        
        chart_df = counts.reset_index()
        chart_df.columns = ["Violation Type", "Count"]
        
        display_names = {
            'helmet': 'Helmet',
            'triple_riding': 'Triple Riding',
            'illegal_parking': 'Illegal Parking',
            'red_light': 'Red-Light'
        }
        chart_df["Violation Type"] = chart_df["Violation Type"].map(display_names)
        
        print(f"--- Chart DataFrame (Frame {current_f}) ---")
        print(chart_df)
        
        import altair as alt
        
        if chart_df["Count"].sum() > 0:
            display_types = chart_df["Violation Type"].replace({"Helmet": "No Helmet"})
            chart_df["Legend_Label"] = display_types + " - " + chart_df["Count"].astype(str)
            
            base_colors = {
                'Helmet': '#FF9F1C',
                'Triple Riding': '#E71D36',
                'Illegal Parking': '#2EC4B6',
                'Red-Light': '#9D4EDD'
            }
            active_df = chart_df[chart_df["Count"] > 0]
            
            # Map colors strictly to the dynamic legend labels
            domain = active_df["Legend_Label"].tolist()
            range_ = [base_colors.get(vt, '#888888') for vt in active_df["Violation Type"]]
            
            total_count = active_df["Count"].sum()
            fig = alt.Chart(active_df).mark_arc(innerRadius=65).encode(
                theta=alt.Theta(field="Count", type="quantitative"),
                color=alt.Color(
                    field="Legend_Label", 
                    type="nominal", 
                    scale=alt.Scale(domain=domain, range=range_), 
                    legend=alt.Legend(
                        title="Violations Logged",
                        titleColor='#BBBBBB',
                        titleFontSize=14,
                        titleFontWeight='bold',
                        labelFontSize=15,
                        symbolSize=150,
                        labelColor='#E0E0E0',
                        padding=15,
                        rowPadding=12
                    )
                ),
                tooltip=["Violation Type", "Count"]
            ).properties(height=320)
        else:
            empty_df = pd.DataFrame([{"Violation Type": "No Violations", "Count": 1}])
            fig = alt.Chart(empty_df).mark_arc(innerRadius=65).encode(
                theta=alt.Theta(field="Count", type="quantitative"),
                color=alt.Color(field="Violation Type", type="nominal", scale=alt.Scale(range=['#333333'])),
                tooltip=["Violation Type"]
            ).properties(height=320)
            
        chart_ph.altair_chart(fig, use_container_width=True)

        with log_ph.container():
            if not df.empty:
                disp_df = df.copy()
                disp_df["Status"] = disp_df["review_needed"].apply(lambda x: "Needs Review" if x else "Confirmed")
                
                cols = ["id", "violation_type", "vehicle_type", "frame_number", "timestamp", "confidence_score", "Status"]
                cols = [c for c in cols if c in disp_df.columns]
                disp_df = disp_df[cols]
                
                def color_status(val):
                    if val == 'Confirmed':
                        return 'background-color: rgba(39, 174, 96, 0.2); color: #2ecc71;'
                    elif val == 'Needs Review':
                        return 'background-color: rgba(230, 126, 34, 0.2); color: #e67e22;'
                    return ''
                
                styled_df = disp_df.style.map(color_status, subset=['Status']) if 'Status' in disp_df.columns else disp_df
                st.dataframe(styled_df, use_container_width=True, hide_index=True)
                
                if is_finished:
                    st.markdown("---")
                    def make_label(r):
                        v_type_raw = r['violation_type']
                        v_type_disp = display_names.get(v_type_raw, str(v_type_raw).title())
                        return f"#{r['id']} - {v_type_disp} - {r['timestamp']}"
                    
                    labels = [make_label(r) for _, r in disp_df.iterrows()]
                    selected_label = st.selectbox("Select a violation for details:", labels, key="violation_selector")
                    
                    if selected_label:
                        selected_id = int(selected_label.split(" - ")[0].replace("#", ""))
                        row_data = disp_df[disp_df['id'] == selected_id].iloc[0]
                        v_type_disp = display_names.get(row_data['violation_type'], str(row_data['violation_type']).title())
                        
                        veh_val = row_data['vehicle_type']
                        veh_disp = str(veh_val).title() if isinstance(veh_val, str) else str(veh_val)
                        
                        score_val = float(row_data['confidence_score'])
                        score_pct_str = f"{score_val * 100:.1f}%"
                        bar_width = min(max(score_val * 100, 0), 100)
                        
                        if row_data.get('Status') == 'Needs Review':
                            badge_bg = "rgba(230, 126, 34, 0.2)"
                            badge_text = "#e67e22"
                            badge_label = "NEEDS REVIEW"
                        else:
                            badge_bg = "rgba(39, 174, 96, 0.2)"
                            badge_text = "#2ecc71"
                            badge_label = "CONFIRMED"
                        
                        # Fetch evidence image
                        full_row = df[df['id'] == selected_id].iloc[0]
                        ev_path = full_row.get('evidence_image_path')
                        if ev_path and str(ev_path).strip() and os.path.exists(str(ev_path)):
                            with open(str(ev_path), "rb") as img_f:
                                ev_b64 = base64.b64encode(img_f.read()).decode('utf-8')
                            ev_html = f'<img src="data:image/jpeg;base64,{ev_b64}" style="width: 100%; border-radius: 6px; margin-bottom: 10px;" />'
                        else:
                            ev_html = '<div style="color: #e74c3c; font-weight: bold; font-size: 13px; text-align: center; padding: 20px;">NO EVIDENCE IMAGE AVAILABLE</div>'
                        
                        col0, col1, col2, col3 = st.columns([1.5, 1, 1, 1])
                        
                        with col0:
                            st.markdown(
'<div style="border: 1px solid #444; border-radius: 8px; padding: 15px; background-color: #1e1e1e; margin-top: 10px; margin-bottom: 10px; height: 90%;">'
f'<h4 style="margin-top: 0; font-variant: small-caps; color: #ccc;">EVIDENCE SNAPSHOT (Frame {row_data.get("frame_number", "N/A")})</h4>'
f'{ev_html}'
'</div>', unsafe_allow_html=True)
                        
                        with col1:
                            st.markdown(
'<div style="border: 1px solid #444; border-radius: 8px; padding: 15px; background-color: #1e1e1e; margin-top: 10px; margin-bottom: 10px; height: 90%;">'
'<h4 style="margin-top: 0; font-variant: small-caps; color: #ccc;">VIOLATION INFORMATION</h4>'
'<div style="color: #aaa; font-size: 14px; line-height: 1.6;">'
f'<div>ID: <span style="color: #fff;">#{row_data["id"]}</span></div>'
f'<div>Type: <span style="color: #fff;">{v_type_disp}</span></div>'
f'<div>Timestamp: <span style="color: #fff;">{row_data["timestamp"]}</span></div>'
f'<div>Vehicle: <span style="color: #fff;">{veh_disp}</span></div>'
'</div></div>', unsafe_allow_html=True)
                            
                        with col2:
                            st.markdown(
'<div style="border: 1px solid #444; border-radius: 8px; padding: 15px; background-color: #1e1e1e; margin-top: 10px; margin-bottom: 10px; height: 90%;">'
'<h4 style="margin-top: 0; font-variant: small-caps; color: #ccc;">CONFIDENCE & REVIEW</h4>'
f'<div style="font-size: 32px; font-weight: bold; color: #fff; margin-bottom: 8px;">{score_pct_str}</div>'
'<div style="width: 100%; background-color: #333; border-radius: 5px; height: 8px; margin-bottom: 15px; overflow: hidden;">'
f'<div style="width: {bar_width}%; background: linear-gradient(90deg, #e74c3c, #f1c40f, #2ecc71); height: 100%; border-radius: 5px;"></div>'
'</div>'
f'<div style="display: inline-block; padding: 4px 10px; border-radius: 4px; font-weight: bold; font-size: 12px; background-color: {badge_bg}; color: {badge_text};">{badge_label}</div>'
'</div>', unsafe_allow_html=True)
                            
                        with col3:
                            # Fetch full row data to access plate_text which isn't in disp_df
                            full_row = df[df['id'] == selected_id].iloc[0]
                            plate_val = full_row.get('plate_text')
                            
                            if plate_val and str(plate_val).strip() and str(plate_val).strip().lower() not in ('none', 'nan', 'null'):
                                plate_content = (
                                    '<div style="font-size: 30px; font-weight: bold; color: #fff; margin-bottom: 8px; text-align: center; letter-spacing: 2px; padding: 10px; border: 2px solid #555; border-radius: 6px; background-color: #222;">'
                                    f'{str(plate_val).upper()}'
                                    '</div>'
                                )
                            else:
                                plate_img_path = "assets/Default Number Plate.png"
                                img_html = ""
                                if os.path.exists(plate_img_path):
                                    with open(plate_img_path, "rb") as img_f:
                                        b64_img = base64.b64encode(img_f.read()).decode('utf-8')
                                    img_html = f'<img src="data:image/png;base64,{b64_img}" style="width: 100%; border-radius: 6px; opacity: 0.6; margin-bottom: 10px;" />'
                                    
                                plate_content = (
                                    f'{img_html}'
                                    '<div style="color: #e74c3c; font-weight: bold; font-size: 13px; text-align: center;">PLATE NOT DETECTED IN THIS FRAME</div>'
                                )
                                
                            st.markdown(
'<div style="border: 1px solid #444; border-radius: 8px; padding: 15px; background-color: #1e1e1e; margin-top: 10px; margin-bottom: 10px; height: 90%;">'
'<h4 style="margin-top: 0; font-variant: small-caps; color: #ccc;">LICENSE PLATE OCR</h4>'
f'{plate_content}'
'</div>', unsafe_allow_html=True)
                        
            else:
                st.info("No violations detected yet.")
                
        if is_finished and not df.empty:
            with download_ph.container():
                with st.expander("Generate Reports"):
                    st.markdown("### SESSION REPORT EXPORT")
                    st.markdown(
'<style>'
'div[data-testid="stExpander"] { background-color: rgba(25, 25, 25, 0.95) !important; border: 1px solid #555 !important; border-radius: 8px; } '
'div[data-testid="stExpander"] summary p { color: #ffffff !important; font-weight: bold !important; font-size: 16px !important; }'
'</style>', unsafe_allow_html=True)
                    
                    csv_path, pdf_path = generate_reports()
                    c1, c2 = st.columns(2)
                    with c1:
                        if csv_path and os.path.exists(csv_path):
                            with open(csv_path, "rb") as f:
                                st.download_button(
                                    "⬇️  Download CSV Report",
                                    f,
                                    file_name="violations_report.csv",
                                    mime="text/csv",
                                    use_container_width=True,
                                )
                    with c2:
                        if pdf_path and os.path.exists(pdf_path):
                            with open(pdf_path, "rb") as f:
                                st.download_button(
                                    "⬇️  Download PDF Report",
                                    f,
                                    file_name="violations_report.pdf",
                                    mime="application/pdf",
                                    use_container_width=True,
                                )
        elif not is_finished:
            download_ph.empty()

    if run_btn and uploaded is not None:
        clear_db()
        reset_state()
        st.session_state["run_for_file"] = uploaded.name
        if "final_frame" in st.session_state:
            del st.session_state["final_frame"]
        
        vehicle_model_map = {
            "YOLOv8n (Fast)":             "yolov8n.pt",
            "YOLOv8s (Balanced)":         "yolov8s.pt",
            "YOLOv8m (Accurate, Slower)": "yolov8m.pt",
        }
        model = load_model(vehicle_model_map[model_choice])
        
        helmet_model_map = {
            "YOLOv8s v2 (Motorcycle)": os.path.join("models", "helmet_yolov8s_v2_motorcycle.pt"),
        }
        helmet_pt = helmet_model_map[helmet_model_choice]
        helmet_model = load_model(helmet_pt)

        is_image = uploaded.name.lower().endswith(('.jpg', '.jpeg', '.png'))
        actual_enable_red_light = enable_red_light and not is_image

        if is_image:
            total = 1
        else:
            _cap = cv2.VideoCapture(tmp_path)
            total = int(_cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
            _cap.release()

        def generate_frames(path, is_img):
            if is_img:
                frame = cv2.imread(path)
                if frame is not None:
                    yield process_single_frame(frame, model, 0, 0.0)
            else:
                yield from run_detection(path, model=model, save_output=True)

        if stop_btn_ph.button("🛑 Stop Detection"):
            st.session_state["stop_requested"] = True

        title_ph.markdown(f"#### CURRENTLY PROCESSING: Frame 0 / {total}")
        progress_bar.progress(0, text="Starting...")

        fn = 0
        for frame_data in generate_frames(tmp_path, is_image):
            if st.session_state.get("stop_requested", False):
                break
                
            fn = frame_data["frame_number"]
            
            calib = st.session_state.get("red_light_calibration", {})
            violations = check_violations(
                frame_data,
                helmet_model=helmet_model,
                enable_red_light=actual_enable_red_light,
                light_region=calib.get("LIGHT_REGION"),
                stop_line=calib.get("STOP_LINE"),
            )

            rgb = cv2.cvtColor(frame_data["annotated_frame"], cv2.COLOR_BGR2RGB)
            live_preview.image(rgb, use_container_width=True)
            st.session_state["final_frame"] = rgb

            for i, v in enumerate(violations):
                crop = crop_region(frame_data["original_frame"], v["box"], padding_pct=0.20)
                ts = datetime.datetime.now().isoformat()

                vid = insert_violation(
                    timestamp=ts,
                    frame_number=v["frame_number"],
                    violation_type=v["violation_type"],
                    vehicle_type=v["vehicle_type"],
                    confidence_score=round(v["confidence"], 4),
                    review_needed=v.get("review_needed", False),
                    review_reason=v.get("review_reason", None),
                    source_video=uploaded.name,
                )
                ev_path = None
                if crop is not None and crop.size > 0:
                    ev_path = os.path.join(EVIDENCE_DIR, f"{vid}.jpg")
                    save_image(crop, ev_path)
                
                import os
                # Fetch demo plate from (filename, index) map (None if not found)
                plate_text = PLATE_LOOKUP.get((os.path.basename(uploaded.name), i), None)
                
                import sqlite3
                
                conn = sqlite3.connect("violations.db")
                conn.execute(
                    "UPDATE violations SET evidence_image_path=?, plate_text=? WHERE id=?",
                    (ev_path, plate_text, vid),
                )
                conn.commit()
                conn.close()

            if fn % 10 == 0 or fn == 1:
                pct = min(int(fn / total * 100), 100)
                progress_bar.progress(pct, text=f"Processing frame {fn} / {total}")
                title_ph.markdown(f"#### CURRENTLY PROCESSING: Frame {fn} / {total}")
                update_dashboard(fn, total, is_finished=False, show_data=True)
                
        title_ph.markdown("#### CURRENTLY PROCESSING: Complete")
        progress_bar.empty()
        stop_btn_ph.empty()
        update_dashboard(fn, total, is_finished=True, show_data=True)

    else:
        # Not currently running
        show_real_data = (uploaded is not None) and (st.session_state.get("run_for_file") == uploaded.name)
        if show_real_data:
            title_ph.markdown("#### CURRENTLY PROCESSING: Complete")
            update_dashboard(0, 0, is_finished=True, show_data=True)
        else:
            title_ph.markdown("#### CURRENTLY PROCESSING: Idle")
            update_dashboard(0, 0, is_finished=False, show_data=False)

# ---------------------------------------------------------------------------
# Clean up temp file (best-effort — may already be gone on a later rerun)
# ---------------------------------------------------------------------------
try:
    if 'tmp_path' in locals():
        os.unlink(tmp_path)
except Exception:
    pass
