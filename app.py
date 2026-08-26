"""
app.py -- Streamlit UI.  No styling -- bare-bones functional interface.

Run with:  streamlit run app.py
"""

import os
import datetime
import tempfile
import streamlit as st
import pandas as pd

from detection import load_model, run_detection
from violations import check_violations, reset_state
from anpr import detect_and_read_plate
from database import init_db, insert_violation, get_all_violations, clear_db
from report import generate_reports
from utils import ensure_dirs, crop_region, save_image, EVIDENCE_DIR

# Initialise DB and folders on startup
init_db()
ensure_dirs()


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.title("Traffic Violation Detection System")

uploaded = st.file_uploader("Upload a traffic video (.mp4)", type=["mp4", "avi", "mov"])

if uploaded:
    # Save the upload to a temp file so OpenCV can open it
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
        tmp.write(uploaded.read())
        tmp_path = tmp.name

    st.write(f"Uploaded: **{uploaded.name}** ({os.path.getsize(tmp_path)//1024} KB)")

    if st.button("Run Detection"):
        clear_db()   # fresh run -- clear previous results
        reset_state()

        model        = load_model()
        progress_bar = st.progress(0)
        status_text  = st.empty()

        # We need total frame count for progress bar
        import cv2
        cap  = cv2.VideoCapture(tmp_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        cap.release()

        violation_count = 0

        for frame_data in run_detection(tmp_path, model=model, save_output=True):
            fn = frame_data["frame_number"]

            # Update progress bar every 10 frames
            if fn % 10 == 0:
                pct = min(int(fn / total * 100), 100)
                progress_bar.progress(pct)
                status_text.text(f"Processing frame {fn}/{total} ...")

            # Check for violations this frame
            violations = check_violations(frame_data)

            for v in violations:
                # Crop evidence image of the vehicle
                crop = crop_region(frame_data["annotated_frame"], v["box"])
                ts   = datetime.datetime.fromtimestamp(
                    datetime.datetime.now().timestamp()
                ).isoformat()

                # Insert a preliminary row to get the ID for file naming
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
                    frame_data["annotated_frame"], v["box"], vid)

                # Update the row with image paths + plate text
                import sqlite3
                conn = sqlite3.connect("violations.db")
                conn.execute(
                    "UPDATE violations SET evidence_image_path=?, plate_text=?, "
                    "plate_image_path=? WHERE id=?",
                    (ev_path,
                     anpr_result["plate_text"],
                     anpr_result["plate_image_path"],
                     vid)
                )
                conn.commit()
                conn.close()

                violation_count += 1

        progress_bar.progress(100)
        status_text.text(f"Done! {violation_count} violations detected.")

        # Show violations table
        st.subheader("Violations Found")
        rows = get_all_violations()
        if rows:
            df = pd.DataFrame([dict(r) for r in rows])
            st.dataframe(df)

            # Generate and offer download of reports
            csv_path, pdf_path = generate_reports()

            col1, col2 = st.columns(2)
            with col1:
                if csv_path and os.path.exists(csv_path):
                    with open(csv_path, "rb") as f:
                        st.download_button("Download CSV", f, file_name="violations_report.csv")
            with col2:
                if pdf_path and os.path.exists(pdf_path):
                    with open(pdf_path, "rb") as f:
                        st.download_button("Download PDF", f, file_name="violations_report.pdf")

            # Show evidence thumbnails
            st.subheader("Evidence Images")
            for row in rows:
                ep = row["evidence_image_path"]
                if ep and os.path.exists(ep):
                    st.image(ep, caption=f"ID {row['id']} | {row['violation_type']} | {row['plate_text'] or 'No plate'}", width=200)
        else:
            st.info("No violations detected in this video.")

    # Clean up temp file
    try:
        os.unlink(tmp_path)
    except Exception:
        pass
