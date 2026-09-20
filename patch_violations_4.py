import re

with open('violations.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('Call check_violations(frame_data, helmet_model=..., ) each frame.', 'Call check_violations(frame_data, helmet_model=...) each frame.')
text = re.sub(r'\s*\(saves CPU; recommended for fisheye/wide-angle CCTV\s*where lens distortion causes false positives\)\n', '\n', text)

with open('violations.py', 'w', encoding='utf-8') as f:
    f.write(text)
