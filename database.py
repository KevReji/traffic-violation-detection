"""
database.py -- SQLite setup and CRUD helpers.

Schema:
  violations(id, timestamp, frame_number, violation_type, vehicle_type,
             confidence_score, plate_text, evidence_image_path, plate_image_path)

Usage:
  from database import init_db, insert_violation, get_all_violations
"""

import sqlite3
import os

DB_PATH = "violations.db"


def get_connection():
    # Returns a connection with row_factory so rows behave like dicts
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the violations table if it does not already exist."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS violations (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp          TEXT NOT NULL,       -- ISO-format datetime string
            frame_number       INTEGER NOT NULL,
            violation_type     TEXT NOT NULL,       -- helmet / triple_riding / illegal_parking
            vehicle_type       TEXT NOT NULL,       -- car / motorcycle / bus / truck
            confidence_score   REAL NOT NULL,
            plate_text         TEXT,                -- OCR result (may be NULL or inaccurate)
            evidence_image_path TEXT,               -- path to cropped vehicle image
            plate_image_path    TEXT,               -- path to cropped plate image (may be NULL)
            review_needed       BOOLEAN DEFAULT 0,  -- 1 if flagged for manual review
            review_reason       TEXT                -- reason for review (e.g. 'low_confidence')
        )
    """)
    conn.commit()
    
    # Safely migrate existing databases
    try:
        conn.execute("ALTER TABLE violations ADD COLUMN review_needed BOOLEAN DEFAULT 0")
        conn.execute("ALTER TABLE violations ADD COLUMN review_reason TEXT")
    except sqlite3.OperationalError:
        pass  # Columns already exist

    conn.close()
    print("[database] DB initialised:", DB_PATH)


def insert_violation(timestamp, frame_number, violation_type, vehicle_type,
                     confidence_score, plate_text=None,
                     evidence_image_path=None, plate_image_path=None,
                     review_needed=False, review_reason=None):
    """
    Insert one violation record and return the new row id.

    Parameters match the table columns exactly.  plate_text and image paths
    are optional (can be None).
    """
    conn = get_connection()
    cur  = conn.execute("""
        INSERT INTO violations
            (timestamp, frame_number, violation_type, vehicle_type,
             confidence_score, plate_text, evidence_image_path, plate_image_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (timestamp, frame_number, violation_type, vehicle_type,
             confidence_score, plate_text, evidence_image_path, plate_image_path))
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def get_all_violations():
    """Return all violation rows as a list of dict-like sqlite3.Row objects."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM violations ORDER BY id").fetchall()
    conn.close()
    return rows


def clear_db():
    """Delete all rows (useful for testing / re-runs)."""
    conn = get_connection()
    conn.execute("DELETE FROM violations")
    conn.commit()
    
    # Safely migrate existing databases
    try:
        conn.execute("ALTER TABLE violations ADD COLUMN review_needed BOOLEAN DEFAULT 0")
        conn.execute("ALTER TABLE violations ADD COLUMN review_reason TEXT")
    except sqlite3.OperationalError:
        pass  # Columns already exist

    conn.close()
    print("[database] All rows deleted.")


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import datetime
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)           # start fresh for test
    init_db()

    # Insert a dummy record
    now = datetime.datetime.now().isoformat()
    vid = insert_violation(
        timestamp="2024-01-01T10:00:00",
        frame_number=42,
        violation_type="triple_riding",
        vehicle_type="motorcycle",
        confidence_score=0.87,
        plate_text="MH12AB1234",
        evidence_image_path="evidence/ev_001.jpg",
        plate_image_path="evidence/plate_001.jpg",
    )
    print(f"[test] Inserted row id={vid}")

    rows = get_all_violations()
    print(f"[test] Total rows: {len(rows)}")
    for r in rows:
        print(dict(r))

    print("[test] database.py OK")
