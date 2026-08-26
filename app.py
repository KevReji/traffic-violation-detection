"""
app.py -- Streamlit dashboard UI.

Run with:  streamlit run app.py
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
# Page config -- must be the very first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Traffic Violation Detection",
    page_icon="🚦",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Custom CSS -- dark-mode command center theme
# ---------------------------------------------------------------------------

def apply_custom_css():
    """
    Inject custom CSS to style the dashboard as a dark security command center.

    Targets used:
      • div[data-testid="stMetric"]   — Streamlit's metric card container (stable API)
      • .badge-confirmed / .badge-review — pill badges for use in st.markdown()
      • .cctv-feed                     — wrapper div for the live video preview
    """
    st.markdown(
        """
        <style>
        /* ── Global app background ─────────────────────────────────────────── */
        .stApp {
            background-color: #0E1117;
        }

        /* ── Sidebar ───────────────────────────────────────────────────────── */
        section[data-testid="stSidebar"] {
            background-color: #161B22;
            border-right: 1px solid #30363D;
        }

        /* ── Metric cards ──────────────────────────────────────────────────── */
        div[data-testid="stMetric"] {
            background-color: #1E222D;
            border: 1px solid #30363D;
            border-radius: 10px;
            padding: 16px 20px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.45);
        }

        /* Metric label (small text above the number) */
        div[data-testid="stMetric"] label {
            color: #8B949E !important;
            font-size: 0.78rem;
            font-weight: 600;
            letter-spacing: 0.05em;
            text-transform: uppercase;
        }

        /* Metric value (the big number) */
        div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
            color: #E6EDF3 !important;
            font-size: 2rem;
            font-weight: 700;
        }

        /* ── Tab bar ───────────────────────────────────────────────────────── */
        button[data-baseweb="tab"] {
            background-color: transparent;
            color: #8B949E;
            border-bottom: 2px solid transparent;
            font-weight: 600;
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            color: #58A6FF;
            border-bottom: 2px solid #58A6FF;
        }

        /* ── Violation status badge classes ────────────────────────────────── */
        /* Usage in app.py:
               st.markdown('<span class="badge-confirmed">Confirmed</span>',
                           unsafe_allow_html=True)
               st.markdown('<span class="badge-review">Needs Review</span>',
                           unsafe_allow_html=True)
        */
        .badge-confirmed {
            display: inline-block;
            background-color: #196C2E;
            color: #3FB950;
            border: 1px solid #3FB950;
            border-radius: 20px;
            padding: 2px 12px;
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }
        .badge-review {
            display: inline-block;
            background-color: #5A3B00;
            color: #F0883E;
            border: 1px solid #F0883E;
            border-radius: 20px;
            padding: 2px 12px;
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        /* ── CCTV live feed container ──────────────────────────────────────── */
        /* Usage: wrap live_preview with:
               st.markdown('<div class="cctv-feed">', unsafe_allow_html=True)
               live_preview = st.empty()
               st.markdown('</div>', unsafe_allow_html=True)
           (see processing block below)
        */
        .cctv-feed {
            border: 2px solid #1F6FEB;
            border-radius: 8px;
            padding: 4px;
            box-shadow: 0 0 12px rgba(31, 111, 235, 0.4);
            position: relative;
        }
        /* "LIVE" indicator in top-left corner of the feed */
        .cctv-feed::before {
            content: "⬤  LIVE";
            position: absolute;
            top: 8px;
            left: 12px;
            color: #F85149;
            font-size: 0.65rem;
            font-weight: 800;
            letter-spacing: 0.1em;
            z-index: 10;
            text-shadow: 0 0 6px rgba(248, 81, 73, 0.8);
            pointer-events: none;
        }

        /* ── Dataframe table ───────────────────────────────────────────────── */
        div[data-testid="stDataFrame"] {
            border: 1px solid #30363D;
            border-radius: 8px;
            overflow: hidden;
        }

        /* ── Download buttons ──────────────────────────────────────────────── */
        div[data-testid="stDownloadButton"] > button {
            background-color: #1F6FEB;
            color: #FFFFFF;
            border: none;
            border-radius: 6px;
            font-weight: 600;
        }
        div[data-testid="stDownloadButton"] > button:hover {
            background-color: #388BFD;
        }

        /* ── Primary "Run Detection" button ────────────────────────────────── */
        div[data-testid="stButton"] > button[kind="primary"] {
            background-color: #238636;
            color: #FFFFFF;
            border: 1px solid #2EA043;
            border-radius: 6px;
            font-weight: 700;
            font-size: 1rem;
        }
        div[data-testid="stButton"] > button[kind="primary"]:hover {
            background-color: #2EA043;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

apply_custom_css()


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
        "YOLO Model",
        ["YOLOv8n (Fast)", "YOLOv8s (Balanced)", "YOLOv8m (Accurate, Slower)"],
        index=1,
        help="Larger models are more accurate but slower. YOLOv8s is a good default.",
    )

    # Default False for CCTV compatibility -- fisheye lenses cause false positives
    enable_wrong_way = st.checkbox(
        "Enable Wrong-Way Detection",
        value=False,
        help=(
            "Uses bounding-box size growth to flag vehicles approaching the camera. "
            "Works best on straight/undistorted footage (dashcams). "
            "Leave OFF for fisheye/wide-angle CCTV cameras."
        ),
    )

    st.markdown("---")
    run_btn = st.button("▶ Run Detection", use_container_width=True, type="primary")

# ---------------------------------------------------------------------------
# Main area header
# ---------------------------------------------------------------------------
st.title("Traffic Violation Detection System")

if not uploaded:
    st.info("👈  Upload a video in the sidebar to get started.")
    st.stop()

# ---------------------------------------------------------------------------
# Save upload to a temp file (OpenCV needs a real path)
# ---------------------------------------------------------------------------
with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
    tmp.write(uploaded.read())
    tmp_path = tmp.name

file_size_kb = os.path.getsize(tmp_path) // 1024
st.caption(f"📁 {uploaded.name}  ·  {file_size_kb} KB")

# ---------------------------------------------------------------------------
# Processing -- runs only when the button is clicked
# ---------------------------------------------------------------------------
if run_btn:
    clear_db()
    reset_state()

    model_map = {
        "YOLOv8n (Fast)":          "yolov8n.pt",
        "YOLOv8s (Balanced)":      "yolov8s.pt",
        "YOLOv8m (Accurate, Slower)": "yolov8m.pt",
    }
    model_file = model_map[model_choice]
    model      = load_model(model_file)

    # Get total frame count for progress bar
    cap   = cv2.VideoCapture(tmp_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    cap.release()

    progress_bar  = st.progress(0, text="Starting…")
    status_text   = st.empty()
    # Wrap the live feed in a styled div -- CSS defined in apply_custom_css()
    st.markdown('<div class="cctv-feed">', unsafe_allow_html=True)
    live_preview  = st.empty()   # updated every processed frame with annotated BGR→RGB frame
    st.markdown('</div>', unsafe_allow_html=True)

    violation_count = 0

    for frame_data in run_detection(tmp_path, model=model, save_output=True):
        fn = frame_data["frame_number"]

        # ── Progress bar (every 10 frames to avoid Streamlit overhead) ──────
        if fn % 10 == 0:
            pct = min(int(fn / total * 100), 100)
            progress_bar.progress(pct, text=f"Processing frame {fn} / {total}")

        # ── Live video preview (convert BGR→RGB for Streamlit) ───────────────
        annotated_rgb = cv2.cvtColor(frame_data["annotated_frame"], cv2.COLOR_BGR2RGB)
        live_preview.image(annotated_rgb, caption=f"Frame {fn}", use_container_width=True)

        # ── Violation checks ─────────────────────────────────────────────────
        violations = check_violations(frame_data, enable_wrong_way=enable_wrong_way)

        for v in violations:
            # Clean padded crop from the original (unannotated) frame
            crop = crop_region(frame_data["original_frame"], v["box"], padding_pct=0.20)
            ts   = datetime.datetime.now().isoformat()

            # Insert row first to get the auto-increment ID for file naming
            vid = insert_violation(
                timestamp=ts,
                frame_number=v["frame_number"],
                violation_type=v["violation_type"],
                vehicle_type=v["vehicle_type"],
                confidence_score=round(v["confidence"], 4),
                review_needed=v.get("review_needed", False),
                review_reason=v.get("review_reason", None),
            )

            # Save evidence image
            ev_path = None
            if crop is not None:
                ev_path = os.path.join(EVIDENCE_DIR, f"ev_{vid:04d}.jpg")
                save_image(crop, ev_path)

            # ANPR
            anpr_result = detect_and_read_plate(
                frame_data["original_frame"], v["box"], vid)

            # Update row with file paths + plate text
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

    progress_bar.progress(100, text="Done!")
    live_preview.empty()   # clear the preview once processing finishes
    status_text.success(
        f"✅ Processing complete — **{violation_count} violation(s)** detected  "
        f"·  Model: **{model_choice}**"
    )

# ---------------------------------------------------------------------------
# Results section
# Placed OUTSIDE the run_btn block so it persists across reruns
# (e.g. clicking a download button doesn't wipe the screen).
# ---------------------------------------------------------------------------
rows = get_all_violations()

if not rows:
    # Only show this placeholder if we've already tried to run
    if not run_btn:
        pass   # nothing to show yet -- user hasn't run detection
    # else: the success message above already explains 0 violations
else:
    df_all = pd.DataFrame([dict(r) for r in rows])

    # Split into confirmed vs needs-review early so tabs can use them
    df_confirmed = df_all[df_all["review_needed"] != 1]
    df_review    = df_all[df_all["review_needed"] == 1]

    # ── Top-level metrics ────────────────────────────────────────────────────
    st.markdown("---")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Violations",   len(df_all))
    m2.metric("Confirmed",          len(df_confirmed))
    m3.metric("Needs Review",       len(df_review))
    m4.metric("Violation Types",    df_all["violation_type"].nunique())

    st.markdown("---")

    # ── Three tabs ───────────────────────────────────────────────────────────
    tab_db, tab_evidence, tab_review = st.tabs([
        "📋 Database & Reports",
        "🖼️ Confirmed Evidence",
        "🔍 Review Queue",
    ])

    # ── TAB 1: Database & Reports ────────────────────────────────────────────
    with tab_db:
        st.subheader("All Violations")
        st.dataframe(df_all, use_container_width=True)

        csv_path, pdf_path = generate_reports()

        col1, col2 = st.columns(2)
        with col1:
            if csv_path and os.path.exists(csv_path):
                with open(csv_path, "rb") as f:
                    st.download_button(
                        "⬇️ Download CSV",
                        f,
                        file_name="violations_report.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )
        with col2:
            if pdf_path and os.path.exists(pdf_path):
                with open(pdf_path, "rb") as f:
                    st.download_button(
                        "⬇️ Download PDF",
                        f,
                        file_name="violations_report.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )

    # ── TAB 2: Confirmed Evidence ────────────────────────────────────────────
    with tab_evidence:
        if df_confirmed.empty:
            st.info("No confirmed violations in this run.")
        else:
            st.caption(f"{len(df_confirmed)} confirmed violation(s) — review_needed = False")
            # Show in a responsive grid: 4 images per row
            cols_per_row = 4
            rows_list = df_confirmed.to_dict("records")
            for i in range(0, len(rows_list), cols_per_row):
                cols = st.columns(cols_per_row)
                for col, row in zip(cols, rows_list[i : i + cols_per_row]):
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
                        else:
                            st.markdown(
                                f"**ID {row['id']}** — {row['violation_type']}  \n"
                                f"_(no image saved)_"
                            )

    # ── TAB 3: Review Queue ──────────────────────────────────────────────────
    with tab_review:
        if df_review.empty:
            st.success("✅ No violations flagged for manual review.")
        else:
            st.warning(
                f"⚠️ **{len(df_review)} violation(s)** were flagged for manual review. "
                "These detections had low confidence, small object size, or insufficient "
                "tracking history — they require a human decision before enforcement action."
            )
            st.dataframe(
                df_review[["id", "frame_number", "violation_type", "vehicle_type",
                            "confidence_score", "review_reason", "plate_text"]],
                use_container_width=True,
            )
            st.markdown("#### Review Evidence")
            cols_per_row = 4
            rows_list = df_review.to_dict("records")
            for i in range(0, len(rows_list), cols_per_row):
                cols = st.columns(cols_per_row)
                for col, row in zip(cols, rows_list[i : i + cols_per_row]):
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
                        else:
                            st.markdown(
                                f"**ID {row['id']}** — {row['violation_type']}  \n"
                                f"Reason: _{row['review_reason'] or 'N/A'}_  \n"
                                f"_(no image saved)_"
                            )

# ---------------------------------------------------------------------------
# Clean up temp file (best-effort; may already be gone on rerun)
# ---------------------------------------------------------------------------
try:
    os.unlink(tmp_path)
except Exception:
    pass
