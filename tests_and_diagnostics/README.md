# Tests & Diagnostics Archive

This folder contains standalone diagnostic scripts, test harnesses, and historical debug crops used during development and tuning.

None of the files in this directory are required by `app.py` for live detection or production dashboard execution.

---

## Folder Structure

* **`debug_crops_archive/`**: Contains historical image crops from previous debugging sessions (`debug_crops/`, `debug_helmet_crops/`, `debug_traffic/`).
* **Standalone Diagnostic Scripts**:
  * `debug_helmet.py` / `debug_helmet_run.py`: Standalone CLI testing for the fine-tuned helmet YOLO models.
  * `debug_vehicles.py`: Diagnostic script for testing vehicle classification on test images.
  * `find_violation.py`: CLI pipeline run that scans video frames for violation triggers without launching Streamlit.
  * `test_traffic_light.py` / `calibrate.py`: Historical scripts for testing HSV color ranges and coordinate extraction on traffic light footage.
  * `test_calibration_ui.py`: Standalone prototype test for `streamlit-image-coordinates`.
  * `run_debug.py` / `run_test.py`: Standalone execution wrappers.

---

## Running a Diagnostic Script

To run any script from this directory while preserving root project imports, execute from the project root:

```bash
python tests_and_diagnostics/<script_name>.py
```
