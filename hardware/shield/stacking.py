#!/usr/bin/env python3
"""Side view of the shield on the Mega, to scale: images/shield-stacking.svg.

Seen from the USB end of the Mega, so both header rows show. Heights from the
datasheets: Mega sockets 8.5 mm, male header plastic 2.5 mm with 6 mm pins
into the socket, USB-B socket about 11 mm, PJ-316 body 8.2 mm.
    python3 hardware/shield/stacking.py
"""
import os

S = 7.0                                   # px per mm
TOP, BOTTOM, MEGA_TOP = 29.66, 100.0, 46.66
ROWS = (49.2, 97.46)                      # digital row, power/analog row
X0, W = 40, (BOTTOM - TOP) * S + 470

out = []


def X(y):
    return X0 + (y - TOP) * S


def rect(y0, y1, z0, z1, base, fill, stroke="none", dash=False, opacity=1):
    out.append(f'<rect x="{X(y0):.1f}" y="{base - z1 * S:.1f}" width="{(y1 - y0) * S:.1f}" '
               f'height="{(z1 - z0) * S:.1f}" fill="{fill}" stroke="{stroke}" fill-opacity="{opacity}"'
               + (' stroke-dasharray="4 3"' if dash else "") + "/>")


def text(s, x, y, size=13, anchor="start", bold=False, color="#222"):
    out.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" fill="{color}"'
               + (' font-weight="bold"' if bold else "") + f">{s}</text>")


def line(x0, y0, x1, y1, color="#555"):
    out.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="{color}" stroke-width="1"/>')


def mega(base):
    rect(MEGA_TOP, BOTTOM, 0, 1.6, base, "#1b6b8f")                        # Mega PCB
    rect(50.5, 62.5, 1.6, 12.5, base, "#bbb", "#777", dash=True, opacity=0.5)   # USB-B, nearest end
    for r in ROWS:
        rect(r - 1.27, r + 1.27, 1.6, 10.1, base, "#222")                  # Mega sockets
    text("Arduino Mega", X(75), base - 0.2 * S + 16, 12, "middle", color="#1b6b8f")
    text("USB", X(56.5), base - 6 * S, 11, "middle", color="#666")
    text("socket", X(56.5), base - 6 * S + 13, 11, "middle", color="#666")


def shield(base, z):
    rect(TOP, BOTTOM, z, z + 1.6, base, "#2e7d32")                         # shield PCB
    rect(TOP, TOP + 13.0, z + 1.6, z + 9.8, base, "#333")                  # jack body
    text("jack", X(TOP + 6.5), base - (z + 6) * S, 11, "middle", color="#eee")
    text("body808 shield", X(75), base - (z + 1.6) * S - 6, 12, "middle", color="#2e7d32")


def panel(base, title, kind):
    text(title, X0, base - 32 * S, 15, bold=True)
    mega(base)
    if kind == "male":
        z = 1.6 + 8.5 + 2.5                                                 # shield rests on the header plastic
        for r in ROWS:
            rect(r - 1.27, r + 1.27, 10.1, 12.6, base, "#555")             # plastic, under the shield
            rect(r - 0.32, r + 0.32, 4.1, z + 1.6 + 1.4, base, "#d4a017")  # pin: 6 mm in the socket
        note = ["Male pins under the shield go into the Mega's sockets.",
                "The plastic strip is under the board, soldered on top.",
                "A part under the board: you solder it, or the factory",
                "does it on its double-sided line (about $60 more)."]
    else:
        z = 10.1 + 2.9                                                      # legs 10.5, 6 mm in the socket
        for r in ROWS:
            rect(r - 1.27, r + 1.27, z + 1.6, z + 10.1, base, "#222")     # socket body, on top
            rect(r - 0.32, r + 0.32, 4.1, z + 1.6, base, "#d4a017")        # long legs
        note = ["A socket strip sits on top; its long legs go through",
                "the board into the Mega's sockets.",
                "Every part is on top: the cheap one-sided factory job."]
    shield(base, z)
    xr = X(BOTTOM) + 18
    for i, s in enumerate(note):
        text(s, xr, base - (z + 6) * S + 16 * i, 12)
    text("overhang: 17 mm", X(TOP + 8.5), base + 18, 11, "middle", color="#666")
    line(X(TOP), base + 6, X(MEGA_TOP), base + 6, "#999")


H1, H2 = 290, 600
panel(H1, "Today: pin headers under the shield", "male")
panel(H2, "Option: stackable headers on top (JLCPCB has none in stock today)", "stack")
text("Seen from the Mega's USB end, to scale. Both boards stay the right way up; the shield sits on top.",
     X0, H2 + 50, 12, color="#555")

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H2 + 70}" '
       f'font-family="DejaVu Sans, sans-serif"><rect width="100%" height="100%" fill="white"/>'
       + "".join(out) + "</svg>\n")
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images", "shield-stacking.svg")
open(path, "w").write(svg)
print("saved", path)
