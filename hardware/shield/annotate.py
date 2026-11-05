"""Annotate the top view of the shield: labels in the margins, lines to the parts.
    python3 annotate.py OUT.png TOP.png   (TOP.png: 2400 px wide top view from make_fab.sh)"""
import subprocess, sys
S = 2400 / 99.0                       # px per mm in .work/top.png
L, R, B, T = 640, 760, 230, 70        # margins
TOP = 29.66

def px(x, y):
    return L + (x - 100.0) * S, T + (y - TOP) * S

left = [  # (label, label_y_px, feature mm)
    ("GND line, through all jack sleeves", None, (109.0, 31.16)),
    ("jack tip = signal in", None, (105, 36.66)),
    ("jack switch = GND", None, (105, 41.16)),
    ("(input at 0 V when unplugged)", None, None),
    ("1M: signal line to GND line", None, (105, 48.8)),
    ("10k: in the signal line", None, (102.4, 54.8)),
    ("ZENER 5V1: signal to GND", None, (105, 60.0)),
    ("1k: in the signal line", None, (102.4, 67.5)),
    ("signal goes down to A0", None, (102.4, 74.0)),
    ("GND from the Mega (J1),", None, (101.0, 86.0)),
    ("up the left edge", None, None),
]
right = [
    ("MIDI OUT socket (WIDI Master)", 200, (185.5, 36.0)),
    ("R1 220: 5V to MIDI pin 4", 300, (172.46, 44.66)),
    ("R2 220: TX1 to MIDI pin 5", 380, (190.0, 49.5)),
    ("J6 into the Mega: TX1 only", 460, (178.74, 49.2)),
    ("J7 into the Mega: 5V", 540, (195.25, 49.2)),
    ("5V down to the knob", 900, (196.52, 70.0)),
    ("KNOB connector: GND 5V A8", 1420, (190.0, 89.0)),
    ("GND to the knob: from J1, under A0-A7", 1520, (160.0, 99.0)),
    ("J5 into the Mega: A8 only", 1620, (173.66, 97.46)),
    ("TEST pads: GND and 5V", 1720, (195.5, 96.3)),
]
bottom = [
    ("J1 into the Mega: GND only", (141.91, 97.46)),
    ("J3 into the Mega: A0 ... A7", (159.69, 97.46)),
]
W, H = 2400 + L + R, 1706 + T + B
cmd = ["magick", sys.argv[2] if len(sys.argv) > 2 else ".work/top.png", "-background", "white", "-gravity", "northwest",
       "-splice", f"{L}x{T}", "-gravity", "southeast", "-splice", f"{R}x{B}", "-gravity", "northwest",
       "-font", "/usr/share/fonts/dejavu/DejaVuSans.ttf", "-pointsize", "30", "-strokewidth", "3"]
draw = []
y = T + 30
for label, _, feat in left:
    if feat:
        fx, fy = px(*feat)
        ly = max(y, fy)
        draw += ["-stroke", "#1f6feb", "-fill", "none", "-draw", f"line {L - 20},{ly} {fx},{fy}",
                 "-fill", "#1f6feb", "-draw", f"circle {fx},{fy} {fx + 7},{fy}"]
    else:
        ly = y
    draw += ["-stroke", "none", "-fill", "black", "-draw", f"text 15,{ly + 10} '{label}'"]
    y = ly + 70
for label, ly, feat in right:
    fx, fy = px(*feat)
    x0 = L + 2400 + 20
    draw += ["-stroke", "#1f6feb", "-fill", "none", "-draw", f"line {fx},{fy} {x0},{ly}",
             "-fill", "#1f6feb", "-draw", f"circle {fx},{fy} {fx + 7},{fy}",
             "-stroke", "none", "-fill", "black", "-draw", f"text {x0 + 10},{ly + 10} '{label}'"]
for i, (label, feat) in enumerate(bottom):
    fx, fy = px(*feat)
    ly = T + 1706 + 70 + 60 * i
    draw += ["-stroke", "#1f6feb", "-fill", "none", "-draw", f"line {fx},{fy} {fx},{ly - 25}",
             "-fill", "#1f6feb", "-draw", f"circle {fx},{fy} {fx + 7},{fy}",
             "-stroke", "none", "-fill", "black", "-draw", f"text {fx - 200},{ly} '{label}'"]
draw += ["-stroke", "none", "-fill", "#444444", "-pointsize", "28",
         "-draw", f"text 15,{T + 1706 + 150} 'Each lane: left red line = signal (jack tip > 10k > 1k > Mega),'",
         "-draw", f"text 15,{T + 1706 + 190} 'right red line = GND. Everything is on this side; the underside is empty.'"]
subprocess.run(cmd + draw + [sys.argv[1]], check=True)
