import re

with open('calibration_ui.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Add the 'Clear Auto-Detection' button near 'Clear Clicks'
replacement = '''    col1, col2 = st.columns(2)
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
'''

text = re.sub(r'    if st\.button\("Clear Clicks"\):\n        st\.session_state\["calib_clicks"\] = \[\]\n        st\.session_state\["last_click"\] = None\n        st\.rerun\(\)\n', replacement, text)

with open('calibration_ui.py', 'w', encoding='utf-8') as f:
    f.write(text)
