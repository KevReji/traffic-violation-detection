"""
app.py -- Traffic Violation Detection Dashboard (Streamlit).

Run with:  streamlit run app.py

Visual styling is handled entirely by style.css — keep backend logic here,
presentation concerns there.
"""

import os
import datetime
import tempfile
import sqlite3

import cv2
import streamlit as st
import pandas as pd

from detection import load_model, run_detection
from violations import check_violations, reset_state
from anpr import detect_and_read_plate
from database import init_db, insert_violation, get_all_violations, clear_db
from report import generate_reports
from utils import ensure_dirs, crop_region, save_image, EVIDENCE_DIR

# ---------------------------------------------------------------------------
# One-time startup
# ---------------------------------------------------------------------------
init_db()
ensure_dirs()

# ---------------------------------------------------------------------------
# Page config — MUST be the first Streamlit call in the script
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Traffic Violation Detection",
    page_icon="🚦",
    layout="wide",
)

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
    st.title("🚦 Traffic Violation\nDetection System")
    st.markdown("---")

    uploaded = st.file_uploader(
        "Upload a traffic video",
        type=["mp4", "avi", "mov"],
        help="Supported formats: MP4, AVI, MOV",
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
        ["YOLOv8n (Fast)", "YOLOv8s (Balanced)"],
        index=1,   # default to YOLOv8s — higher mAP50 (0.755 vs 0.746)
        help=(
            "YOLOv8s has slightly higher accuracy (mAP50 0.755, Without-Helmet 0.649) "
            "vs YOLOv8n (mAP50 0.746, Without-Helmet 0.622). "
            "Use YOLOv8n if speed matters more than accuracy."
        ),
    )

    # Default False for CCTV compatibility.
    # The bounding-box growth heuristic produces false positives on
    # fisheye / wide-angle lenses due to barrel distortion.
    enable_wrong_way = st.checkbox(
        "Enable Wrong-Way Detection",
        value=False,
        help=(
            "Flags vehicles whose bounding box grows consistently over 15 frames "
            "(proxy for approaching the camera). Works reliably on dashcams and "
            "straight CCTV angles. Disable for fisheye / wide-angle cameras."
        ),
    )

    st.markdown("---")
    run_btn = st.button("▶  Run Detection", use_container_width=True, type="primary")

# ---------------------------------------------------------------------------
# Main area — title + file info
# ---------------------------------------------------------------------------
st.title("Traffic Violation Detection System")

if not uploaded:
    st.info("👈  Upload a video in the sidebar to get started.")
    st.stop()

# Save the upload to a temp file so OpenCV can open it by path
with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as _tmp:
    _tmp.write(uploaded.read())
    tmp_path = _tmp.name

st.caption(f"📁 **{uploaded.name}**  ·  {os.path.getsize(tmp_path) // 1024} KB")

# ---------------------------------------------------------------------------
# Processing block — runs only when "Run Detection" is clicked
# ---------------------------------------------------------------------------
if run_btn:
    clear_db()      # wipe previous run from DB
    reset_state()   # clear parking / tracking state in violations.py

    # Vehicle detection model
    vehicle_model_map = {
        "YOLOv8n (Fast)":             "yolov8n.pt",
        "YOLOv8s (Balanced)":         "yolov8s.pt",
        "YOLOv8m (Accurate, Slower)": "yolov8m.pt",
    }
    model = load_model(vehicle_model_map[model_choice])

    # Helmet detection model — separate model, separate .pt file, loaded independently
    helmet_model_map = {
        "YOLOv8n (Fast)":    os.path.join("models", "helmet_yolov8n_v1_map74.pt.pt"),
        "YOLOv8s (Balanced)": os.path.join("models", "helmet_yolov8s_v1_map74.pt"),
    }
    helmet_pt = helmet_model_map[helmet_model_choice]
    helmet_model = load_model(helmet_pt)

    # Total frames needed for progress bar
    _cap   = cv2.VideoCapture(tmp_path)
    total  = int(_cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    _cap.release()

    progress_bar = st.progress(0, text="Starting…")
    status_text  = st.empty()

    # Live CCTV-style video preview
    # The .cctv-feed div is defined in style.css — gives the neon border +
    # blinking LIVE indicator without touching any Python styling code.
    st.markdown('<div class="cctv-feed">', unsafe_allow_html=True)
    live_preview = st.empty()
    st.markdown('</div>', unsafe_allow_html=True)

    violation_count = 0

    for frame_data in run_detection(tmp_path, model=model, save_output=True):
        fn = frame_data["frame_number"]

        # Update progress bar every 10 frames to keep Streamlit overhead low
        if fn % 10 == 0:
            pct = min(int(fn / total * 100), 100)
            progress_bar.progress(pct, text=f"Processing frame {fn} / {total}")

        # Convert BGR (OpenCV default) → RGB (what Streamlit expects) and push
        # the annotated frame to the live preview placeholder
        rgb = cv2.cvtColor(frame_data["annotated_frame"], cv2.COLOR_BGR2RGB)
        live_preview.image(rgb, use_container_width=True)

        # Run violation rules on this frame (vehicle model already ran above via run_detection)
        violations = check_violations(
            frame_data,
            helmet_model=helmet_model,
            enable_wrong_way=enable_wrong_way,
        )

        for v in violations:
            # Crop evidence from the ORIGINAL (unannotated) frame with 20% padding
            crop = crop_region(frame_data["original_frame"], v["box"], padding_pct=0.20)
            ts   = datetime.datetime.now().isoformat()

            # Insert row first so we get the auto-increment ID for file naming
            vid = insert_violation(
                timestamp=ts,
                frame_number=v["frame_number"],
                violation_type=v["violation_type"],
                vehicle_type=v["vehicle_type"],
                confidence_score=round(v["confidence"], 4),
                review_needed=v.get("review_needed", False),
                review_reason=v.get("review_reason", None),
            )

            # Save padded evidence image
            ev_path = None
            if crop is not None:
                ev_path = os.path.join(EVIDENCE_DIR, f"ev_{vid:04d}.jpg")
                save_image(crop, ev_path)

            # ANPR — fed the clean original frame (no YOLO text burned in)
            anpr_result = detect_and_read_plate(
                frame_data["original_frame"], v["box"], vid)

            # Update the DB row with file paths + plate text
            conn = sqlite3.connect("violations.db")
            conn.execute(
                "UPDATE violations SET evidence_image_path=?, plate_text=?, "
                "plate_image_path=? WHERE id=?",
                (ev_path,
                 anpr_result["plate_text"],
                 anpr_result["plate_image_path"],
                 vid),
            )
            conn.commit()
            conn.close()

            violation_count += 1

    # Finalise progress and clear the live preview
    progress_bar.progress(100, text="Done!")
    live_preview.empty()
    status_text.success(
        f"✅ Processing complete — **{violation_count} violation(s)** detected  "
        f"·  Vehicle model: **{model_choice}**  "
        f"·  Helmet model: **{helmet_model_choice}**"
    )

# ---------------------------------------------------------------------------
# Results section
#
# IMPORTANT — this block lives OUTSIDE the `if run_btn:` guard.
# Streamlit re-runs the entire script on every interaction (including
# download-button clicks).  Placing results here means they are re-drawn
# from the database on every rerun, so clicking a download button does NOT
# wipe the screen.
# ---------------------------------------------------------------------------
rows = get_all_violations()

if rows:
    df_all       = pd.DataFrame([dict(r) for r in rows])
    df_confirmed = df_all[df_all["review_needed"] != 1]
    df_review    = df_all[df_all["review_needed"] == 1]

    # ── Top-level metrics ────────────────────────────────────────────────────
    st.markdown("---")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Violations", len(df_all))
    m2.metric("Confirmed",        len(df_confirmed))
    m3.metric("Needs Review",     len(df_review))
    m4.metric("Violation Types",  df_all["violation_type"].nunique())
    st.markdown("---")

    # ── Three-tab results panel ──────────────────────────────────────────────
    tab_db, tab_evidence, tab_review = st.tabs([
        "📋  Database & Reports",
        "🖼️  Confirmed Evidence",
        "🔍  Review Queue",
    ])

    # ── Tab 1: Database & Reports ────────────────────────────────────────────
    with tab_db:
        st.subheader("All Violations")
        st.dataframe(df_all, use_container_width=True)

        # Generate reports from whatever is in the DB right now
        csv_path, pdf_path = generate_reports()

        col1, col2 = st.columns(2)
        with col1:
            if csv_path and os.path.exists(csv_path):
                with open(csv_path, "rb") as f:
                    st.download_button(
                        "⬇️  Download CSV Report",
                        f,
                        file_name="violations_report.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )
        with col2:
            if pdf_path and os.path.exists(pdf_path):
                with open(pdf_path, "rb") as f:
                    st.download_button(
                        "⬇️  Download PDF Report",
                        f,
                        file_name="violations_report.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )

    # ── Tab 2: Confirmed Evidence ────────────────────────────────────────────
    with tab_evidence:
        if df_confirmed.empty:
            st.info("No auto-confirmed violations in this run.")
        else:
            st.caption(
                f"{len(df_confirmed)} confirmed violation(s) — "
                "review_needed = False"
            )
            cols_per_row = 4
            records      = df_confirmed.to_dict("records")
            for i in range(0, len(records), cols_per_row):
                cols = st.columns(cols_per_row)
                for col, row in zip(cols, records[i : i + cols_per_row]):
                    ep = row.get("evidence_image_path")
                    with col:
                        if ep and os.path.exists(ep):
                            st.image(
                                ep,
                                caption=(
                                    f"ID {row['id']}  ·  {row['violation_type']}\n"
                                    f"Plate: {row['plate_text'] or 'N/A'}"
                                ),
                                use_container_width=True,
                            )
                            # Green badge below the image
                            st.markdown(
                                '<span class="badge-confirmed">Confirmed</span>',
                                unsafe_allow_html=True,
                            )
                        else:
                            st.markdown(
                                f"**ID {row['id']}** — {row['violation_type']}  \n"
                                f"_(no image saved)_"
                            )

    # ── Tab 3: Review Queue ──────────────────────────────────────────────────
    with tab_review:
        if df_review.empty:
            st.success("✅  No violations flagged for manual review.")
        else:
            st.warning(
                f"⚠️  **{len(df_review)} violation(s)** require manual review.  "
                "These were flagged due to low detection confidence, a very small "
                "object, or insufficient tracking history — human judgement is needed "
                "before enforcement action."
            )
            # Concise table showing only the review-relevant columns
            st.dataframe(
                df_review[[
                    "id", "frame_number", "violation_type", "vehicle_type",
                    "confidence_score", "review_reason", "plate_text",
                ]],
                use_container_width=True,
            )
            st.markdown("#### Evidence")
            cols_per_row = 4
            records      = df_review.to_dict("records")
            for i in range(0, len(records), cols_per_row):
                cols = st.columns(cols_per_row)
                for col, row in zip(cols, records[i : i + cols_per_row]):
                    ep = row.get("evidence_image_path")
                    with col:
                        if ep and os.path.exists(ep):
                            st.image(
                                ep,
                                caption=(
                                    f"ID {row['id']}  ·  {row['violation_type']}\n"
                                    f"Reason: {row['review_reason'] or 'N/A'}"
                                ),
                                use_container_width=True,
                            )
                            # Amber badge below the image
                            st.markdown(
                                '<span class="badge-review">Needs Review</span>',
                                unsafe_allow_html=True,
                            )
                        else:
                            st.markdown(
                                f"**ID {row['id']}** — {row['violation_type']}  \n"
                                f"Reason: _{row['review_reason'] or 'N/A'}_  \n"
                                f"_(no image saved)_"
                            )

# ---------------------------------------------------------------------------
# Clean up temp file (best-effort — may already be gone on a later rerun)
# ---------------------------------------------------------------------------
try:
    os.unlink(tmp_path)
except Exception:
    pass
