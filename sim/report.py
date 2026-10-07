#!/usr/bin/env python3
"""Simulate each tested board configuration and draw the figures of docs/simulation.md.

    python3 sim/report.py           # simulate (cached in sim/out/report/) and draw
    python3 sim/report.py --redo    # ignore the cache

Figures go to docs/sim/, the numbers quoted in the doc to sim/out/report/summary.md.
Needs ngspice. Uses the models and the firmware replay of sim/run.py.
"""

import argparse
import json
import math
import os
from multiprocessing import Pool

import run

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "out", "report")
FIGS = os.path.join(HERE, "..", "docs", "sim")

# key: (title, changes to run.DEFAULT_HIT)
CONFIGS = {
    "built": ("As built: R1 1 MΩ, 1N4733A", {}),
    "bzx55": ("As built with the BZX55C5V1", {"zener": "BZX55C5V1"}),
    "cap100": ("100 nF across the disc, R1 100 kΩ", {"cpar": 100e-9, "r1": 100e3}),
    "cap200": ("200 nF across the disc, R1 100 kΩ", {"cpar": 200e-9, "r1": 100e3}),
    "cap100s": ("100 nF across the disc, R1 100 kΩ, 22 nF after R2",
                {"cpar": 100e-9, "r1": 100e3, "csm": 22e-9}),
    "trim03": ("R1 as 1 MΩ trimmer, wiper at 0.3", {"wiper": 0.3}),
    "trim01": ("R1 as 1 MΩ trimmer, wiper at 0.1", {"wiper": 0.1}),
}

TRANSFER_V = (0.2, 0.3, 0.5, 0.7, 1, 1.5, 2, 3, 4, 5, 6, 8, 10, 15, 20, 30, 40, 50, 60, 80, 100)
STRESS_V = (5, 20, 100, 200)
WAVE_V = (5, 20, 60)
SHAPES = [(t, q) for t in (0.2, 1.0, 3.0) for q in (10, 30, 90)]
RING_V = (5, 20, 60)
# detection test: a hard short hit, then a softer one DOUBLE_MS later
FIRST_V, SECOND_V, DOUBLE_MS = 20, 5, 60
VEL_CURVE = 0.6
MAX_LEVEL = 600


def unit(hit):
    """Disc peak voltage per unit of force for this hit shape (linear)."""
    return max(run.simulate(1.0, hit, t_stop_ms=10)["ref"])


def velocity(adc):
    """body808.ino's peakToVelocity() for the default pad; 0 = no note."""
    if adc <= run.THRESHOLD:
        return 0
    x = min(1.0, max(0.0, (adc - run.THRESHOLD) / (MAX_LEVEL - run.THRESHOLD)))
    return 1 + int(x ** VEL_CURVE * 126 + 0.5)


def thin(r, t_max_ms, step_us):
    """Every step_us of the run up to t_max_ms: (t ms, disc V, pin V)."""
    every = max(1, int(step_us / 2))
    out = []
    for i in range(0, len(r["t"]), every):
        t = r["t"][i] * 1e3 - 1.0  # the hit starts at 1 ms
        if t > t_max_ms:
            break
        if t >= -0.5:
            out.append((round(t, 3), r["ref"][i], r["pin"][i]))
    return out


def envelope(r, t_max_ms, bin_ms):
    """Per bin: (t, min pin, max pin, min disc, max disc), for whole-hit plots."""
    out, cur, start = [], [], None
    for t_s, d, p in zip(r["t"], r["ref"], r["pin"]):
        t = t_s * 1e3 - 1.0
        if t < -0.5:
            continue
        if t > t_max_ms:
            break
        b = math.floor(t / bin_ms)
        if start is None:
            start = b
        if b != start:
            out.append((start * bin_ms, min(c[1] for c in cur), max(c[1] for c in cur),
                        min(c[0] for c in cur), max(c[0] for c in cur)))
            cur, start = [], b
        cur.append((d, p))
    return out


def compute(key):
    path = os.path.join(CACHE, f"{key}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    hit = dict(run.DEFAULT_HIT, **CONFIGS[key][1])
    u = unit(hit)
    res = {"key": key, "title": CONFIGS[key][0]}

    res["transfer"] = []
    for v in TRANSFER_V:
        a = run.analyse(run.simulate(v / u, hit))
        res["transfer"].append({"v": v, "adc": a["adc"], "vel": velocity(a["adc"])})

    stress = []
    for pol in (1, -1):
        for v in STRESS_V:
            a = run.analyse(run.simulate(pol * v / u, hit))
            stress.append({"v": pol * v, "pin_max": a["pin_max"], "pin_min": a["pin_min"],
                           "iclo": a["iclo"], "ichi": a["ichi"], "iz": a["iz"], "pz": a["pz"]})
    res["stress"] = stress

    ring = []
    for t_ms, q in SHAPES:
        h = dict(hit, t_ms=t_ms, q=q)
        uu = unit(h)
        for v in RING_V:
            r = run.simulate(v / uu, h)
            ring.append({"t_ms": t_ms, "q": q, "v": v, "ring_ms": run.analyse(r)["ring_ms"],
                         "notes": len(run.firmware_notes(r))})
    res["ring"] = ring

    res["waves"] = {}
    for v in WAVE_V:
        r = run.simulate(v / u, hit)
        res["waves"][str(v)] = {"detail": thin(r, 12, 10), "whole": envelope(r, 80, 0.5)}

    h = dict(hit, t_ms=0.2)
    uu = unit(h)
    r = run.simulate(FIRST_V / uu, h, t_stop_ms=DOUBLE_MS + 60, second=(DOUBLE_MS, SECOND_V / uu))
    samples, notes = run.firmware_trace(r)
    res["detect"] = {"samples": [(round(t - 1, 2), v, thr) for t, v, thr in samples if t >= 0.6],
                     "notes": [(round(t - 1, 2), p, velocity(p)) for t, p in notes]}
    # the second hit alone, to know what it would read without the first one
    r2 = run.simulate(SECOND_V / uu, h)
    res["detect"]["second_alone"] = run.analyse(r2)["adc"]

    os.makedirs(CACHE, exist_ok=True)
    with open(path, "w") as f:
        json.dump(res, f)
    return res


# --- figures -------------------------------------------------------------------

INK, INK2, GRID, SURFACE, REF_TINT = "#1f1f1e", "#62615a", "#e4e3dc", "#ffffff", "#f1f0ea"
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#7a5195", "#e87ba4", "#008300"]
BLUES = ["#86b6ef", "#2a78d6", "#104281"]  # an ordered series: light -> dark
ACCENT = "#2a78d6"
FONT = "DejaVu Sans, Arial, sans-serif"


def svg(path, w, h, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
                f'font-family="{FONT}">\n<rect width="{w}" height="{h}" fill="{SURFACE}"/>\n'
                + "\n".join(body) + "\n</svg>\n")


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Plot:
    """One panel: linear or log x, linear y, light grid, labelled axes."""

    def __init__(self, x0, y0, w, h, xr, yr, logx=False):
        self.x0, self.y0, self.w, self.h, self.xr, self.yr, self.logx = x0, y0, w, h, xr, yr, logx
        self.out = []

    def sx(self, x):
        if self.logx:
            lo, hi = math.log10(self.xr[0]), math.log10(self.xr[1])
            return self.x0 + (math.log10(x) - lo) / (hi - lo) * self.w
        return self.x0 + (x - self.xr[0]) / (self.xr[1] - self.xr[0]) * self.w

    def sy(self, y):
        y = max(self.yr[0], min(self.yr[1], y))
        return self.y0 + self.h - (y - self.yr[0]) / (self.yr[1] - self.yr[0]) * self.h

    def title(self, text, sub=None):
        self.out.append(f'<text x="{self.x0 - 50}" y="{self.y0 - (34 if sub else 14)}" font-size="14" '
                        f'font-weight="bold" fill="{INK}">{esc(text)}</text>')
        if sub:
            self.out.append(f'<text x="{self.x0 - 50}" y="{self.y0 - 16}" font-size="11.5" fill="{INK2}">{esc(sub)}</text>')

    def axes(self, xticks, yticks, xlabel, ylabel, xfmt="{:g}"):
        for t in yticks:
            y = self.sy(t)
            self.out.append(f'<line x1="{self.x0}" x2="{self.x0 + self.w}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}"/>')
            self.out.append(f'<text x="{self.x0 - 6}" y="{y + 4:.1f}" font-size="11" fill="{INK2}" text-anchor="end">{t:g}</text>')
        for t in xticks:
            self.out.append(f'<text x="{self.sx(t):.1f}" y="{self.y0 + self.h + 16}" font-size="11" fill="{INK2}" '
                            f'text-anchor="middle">{xfmt.format(t)}</text>')
        zero = self.sy(max(self.yr[0], 0)) if self.yr[0] <= 0 <= self.yr[1] else self.y0 + self.h
        self.out.append(f'<line x1="{self.x0}" x2="{self.x0 + self.w}" y1="{zero:.1f}" y2="{zero:.1f}" stroke="{INK2}"/>')
        self.out.append(f'<text x="{self.x0 + self.w / 2}" y="{self.y0 + self.h + 34}" font-size="11.5" fill="{INK2}" '
                        f'text-anchor="middle">{esc(xlabel)}</text>')
        self.out.append(f'<text x="{self.x0 - 44}" y="{self.y0 + self.h / 2}" font-size="11.5" fill="{INK2}" text-anchor="middle" '
                        f'transform="rotate(-90 {self.x0 - 44} {self.y0 + self.h / 2})">{esc(ylabel)}</text>')

    def hline(self, y, text, side="right", above=True):
        yy = self.sy(y)
        self.out.append(f'<line x1="{self.x0}" x2="{self.x0 + self.w}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="{INK2}" stroke-dasharray="4 3"/>')
        x, anchor = (self.x0 + self.w - 4, "end") if side == "right" else (self.x0 + 4, "start")
        self.out.append(f'<text x="{x}" y="{yy + (-4 if above else 13):.1f}" font-size="10.5" fill="{INK2}" '
                        f'text-anchor="{anchor}">{esc(text)}</text>')

    def band(self, x1, x2, text=None):
        a, b = self.sx(x1), self.sx(x2)
        self.out.append(f'<rect x="{a:.1f}" y="{self.y0}" width="{b - a:.1f}" height="{self.h}" fill="{REF_TINT}"/>')
        if text:
            self.out.append(f'<text x="{(a + b) / 2:.1f}" y="{self.y0 + 14}" font-size="10.5" fill="{INK2}" '
                            f'text-anchor="middle">{esc(text)}</text>')

    def line(self, pts, color, width=1.6, dash=None):
        d = " ".join(f"{self.sx(x):.1f},{self.sy(y):.1f}" for x, y in pts)
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        self.out.append(f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="{width}" '
                        f'stroke-linejoin="round"{extra}/>')

    def area(self, lows, highs, color, opacity=0.35):
        pts = [(x, y) for x, y in highs] + [(x, y) for x, y in reversed(lows)]
        d = " ".join(f"{self.sx(x):.1f},{self.sy(y):.1f}" for x, y in pts)
        self.out.append(f'<polygon points="{d}" fill="{color}" fill-opacity="{opacity}" stroke="{color}" stroke-width="0.8"/>')

    def legend(self, items, x=None, y=None):
        x = self.x0 + self.w if x is None else x
        y = self.y0 - 14 if y is None else y
        for text, color in reversed(items):
            x -= 7 * len(text) + 30
            self.out.append(f'<line x1="{x}" x2="{x + 16}" y1="{y - 4}" y2="{y - 4}" stroke="{color}" stroke-width="2.5"/>')
            self.out.append(f'<text x="{x + 21}" y="{y}" font-size="11" fill="{INK}">{esc(text)}</text>')

    def text(self, x, y, text, color=INK, anchor="start", size=11, bold=False):
        w = ' font-weight="bold"' if bold else ""
        self.out.append(f'<text x="{self.sx(x):.1f}" y="{self.sy(y):.1f}" font-size="{size}" fill="{color}" '
                        f'text-anchor="{anchor}"{w}>{esc(text)}</text>')


def fig_waves(res):
    """Pin voltage for a soft, medium and hard hit: zoom on the hit and the whole 80 ms."""
    labels = [f"{v} V hit" for v in WAVE_V]
    a = Plot(70, 70, 640, 200, (-0.5, 12), (-1, 6))
    a.title("Pin voltage, first 12 ms", "1 ms hit, Q 30: the ringing and what the zener cuts off")
    a.axes(range(0, 13, 2), (-1, 0, 1, 2, 3, 4, 5, 6), "time after the hit (ms)", "volts at the pin")
    a.hline(5.5, "5.5 V pin limit")
    a.hline(-0.5, "−0.5 V pin limit", above=False)
    a.hline(run.THRESHOLD * run.VCC / run.ADC_MAX, "threshold (40)")
    for i, v in enumerate(WAVE_V):
        a.line([(t, p) for t, d, p in res["waves"][str(v)]["detail"]], BLUES[i], 1.4)
    a.legend(list(zip(labels, BLUES)))
    b = Plot(70, 360, 640, 200, (-0.5, 80), (-1, 6))
    b.title("Pin voltage, whole hit (80 ms)", "shaded: lowest to highest value in each 0.5 ms")
    b.axes(range(0, 81, 10), (-1, 0, 1, 2, 3, 4, 5, 6), "time after the hit (ms)", "volts at the pin")
    b.band(0, run.MASK_MS, "mask 30 ms (after the note)")
    b.hline(run.THRESHOLD * run.VCC / run.ADC_MAX, "threshold (40)")
    for i, v in enumerate(WAVE_V):
        env = res["waves"][str(v)]["whole"]
        b.area([(t, lo) for t, lo, hi, dl, dh in env], [(t, hi) for t, lo, hi, dl, dh in env], BLUES[i], 0.25)
    svg(os.path.join(FIGS, f"wave-{res['key']}.svg"), 740, 610, a.out + b.out)


def fig_input(res):
    """Voltage across the disc (R1 only), same for every configuration."""
    labels = [f"{v} V hit" for v in WAVE_V]
    a = Plot(70, 70, 640, 200, (-0.5, 12), (-70, 70))
    a.title("Input: voltage across the disc, first 12 ms", "disc with only R1 attached, 1 ms hit, Q 30 (identical in every configuration)")
    a.axes(range(0, 13, 2), (-60, -40, -20, 0, 20, 40, 60), "time after the hit (ms)", "volts across the disc")
    for i, v in enumerate(WAVE_V):
        a.line([(t, d) for t, d, p in res["waves"][str(v)]["detail"]], BLUES[i], 1.4)
    a.legend(list(zip(labels, BLUES)))
    svg(os.path.join(FIGS, "input.svg"), 740, 320, a.out)


def fig_detect(res):
    d = res["detect"]
    s = d["samples"]
    p = Plot(70, 74, 640, 260, (0, DOUBLE_MS + 58), (0, 1023))
    p.title(f"What the firmware sees: a {FIRST_V} V hit, then a {SECOND_V} V hit {DOUBLE_MS} ms later",
            "pin read every 0.2 ms (grey), threshold a new hit must beat (blue), shaded while the pad is masked")
    p.axes(range(0, DOUBLE_MS + 60, 10), (0, 256, 512, 768, 1023), "time after the first hit (ms)", "ADC counts")
    # masked spans: samples whose threshold is None
    span = None
    for t, v, thr in s + [(s[-1][0] + 1, 0, 0)]:
        if thr is None and span is None:
            span = t
        if thr is not None and span is not None:
            p.band(span, t)
            span = None
    p.line([(t, v) for t, v, thr in s], "#9a998f", 1.0)
    seg = []
    for t, v, thr in s:
        if thr is None:
            if seg:
                p.line(seg, ACCENT, 2)
            seg = []
        else:
            seg.append((t, thr))
    if seg:
        p.line(seg, ACCENT, 2)
    for t, peak, vel in d["notes"]:
        x = p.sx(t)
        p.out.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{p.y0}" y2="{p.y0 + p.h}" stroke="{INK}" stroke-dasharray="3 3"/>')
        p.out.append(f'<text x="{x + 4:.1f}" y="{p.y0 + 28}" font-size="11" font-weight="bold" fill="{INK}">'
                     f'note, velocity {vel}</text>')
    if len(d["notes"]) < 2:
        x = p.sx(DOUBLE_MS)
        p.out.append(f'<text x="{x + 4:.1f}" y="{p.y0 + 28}" font-size="11" font-weight="bold" fill="#b3261e">'
                     f'second hit missed</text>')
    svg(os.path.join(FIGS, f"detect-{res['key']}.svg"), 740, 390, p.out)


def fig_transfer(all_res):
    keys = list(CONFIGS)
    a = Plot(70, 74, 640, 260, (0.2, 100), (0, 1023), logx=True)
    a.title("ADC reading vs hit strength, every configuration", "1 ms hit, Q 30; the shaded band is where velocity changes (40 → 600)")
    a.out.append(f'<rect x="{a.x0}" y="{a.sy(MAX_LEVEL):.1f}" width="{a.w}" height="{a.sy(run.THRESHOLD) - a.sy(MAX_LEVEL):.1f}" fill="{REF_TINT}"/>')
    a.axes((0.2, 0.5, 1, 2, 5, 10, 20, 50, 100), (0, 256, 512, 768, 1023), "peak voltage across the disc (log scale)",
           "ADC counts", xfmt="{:g} V")
    a.hline(MAX_LEVEL, "maxLevel 600: velocity 127", side="left")
    a.hline(run.THRESHOLD, "threshold 40", side="left")
    for i, k in enumerate(keys):
        a.line([(r["v"], r["adc"]) for r in all_res[k]["transfer"]], CATEGORICAL[i], 2)
    b = Plot(70, 430, 640, 220, (0.2, 100), (0, 127), logx=True)
    b.title("Velocity vs hit strength", "what the sampler receives; 0 = no note")
    b.axes((0.2, 0.5, 1, 2, 5, 10, 20, 50, 100), (0, 32, 64, 96, 127), "peak voltage across the disc (log scale)",
           "MIDI velocity", xfmt="{:g} V")
    for i, k in enumerate(keys):
        b.line([(r["v"], r["vel"]) for r in all_res[k]["transfer"]], CATEGORICAL[i], 2)
    legend = [(CONFIGS[k][0], CATEGORICAL[i]) for i, k in enumerate(keys)]
    y = 712
    for i, (text, color) in enumerate(legend):
        x = 70 + (i % 2) * 330
        yy = y + (i // 2) * 20
        b.out.append(f'<line x1="{x}" x2="{x + 18}" y1="{yy - 4}" y2="{yy - 4}" stroke="{color}" stroke-width="2.5"/>')
        b.out.append(f'<text x="{x + 24}" y="{yy}" font-size="11.5" fill="{INK}">{esc(text)}</text>')
    svg(os.path.join(FIGS, "transfer.svg"), 740, 790, a.out + b.out)


# --- schematics ---------------------------------------------------------------

def schematic(key):
    """Protection board drawn like docs/protection-circuit.svg."""
    o = []
    S = 'stroke="#111" stroke-width="2.5" fill="none"'
    title = CONFIGS[key][0]
    o.append(f'<text x="20" y="30" font-size="18" font-weight="bold" fill="#111">{esc(title)}</text>')
    o.append('<rect x="15" y="50" width="150" height="300" fill="#fdf3e6" stroke="#c98a3a" stroke-dasharray="6 4"/>')
    o.append('<text x="25" y="70" font-size="12" fill="#9a6420">ON THE BODY</text>')
    o.append('<rect x="185" y="50" width="555" height="300" fill="#eaf3fb" stroke="#3a7cc9" stroke-dasharray="6 4"/>')
    o.append('<text x="195" y="70" font-size="12" fill="#2a5f9e">PROTECTION BOARD</text>')
    gnd, sig = 310, 150
    # piezo
    o.append(f'<g {S}><line x1="95" y1="{sig}" x2="95" y2="205"/><line x1="70" y1="205" x2="120" y2="205"/>'
             f'<rect x="77" y="211" width="36" height="22" fill="#fff"/><line x1="70" y1="239" x2="120" y2="239"/>'
             f'<line x1="95" y1="239" x2="95" y2="{gnd}"/><line x1="95" y1="{gnd}" x2="760" y2="{gnd}"/></g>')
    o.append('<text x="22" y="135" font-size="13" font-weight="bold" fill="#111">piezo disc</text>')
    o.append('<text x="22" y="270" font-size="11" fill="#444">20 nF</text>')
    lbl = []
    wiper = key.startswith("trim")
    cap = key.startswith("cap")
    zener = "BZX55C5V1" if key == "bzx55" else "1N4733A"
    # signal wire from the jack to R2
    o.append(f'<g {S}><line x1="95" y1="{sig}" x2="{380 if not wiper else 260}" y2="{sig}"/></g>')
    if cap:
        cval = f"{CONFIGS[key][1]['cpar'] * 1e9:g} nF"
        o.append(f'<g {S}><line x1="225" y1="{sig}" x2="225" y2="218"/><line x1="205" y1="218" x2="245" y2="218"/>'
                 f'<line x1="205" y1="230" x2="245" y2="230"/><line x1="225" y1="230" x2="225" y2="{gnd}"/></g>')
        o.append('<g fill="#111"><circle cx="225" cy="150" r="5"/><circle cx="225" cy="310" r="5"/></g>')
        lbl.append(('<text x="232" y="262" font-size="13" font-weight="bold" fill="#b3261e">C ' + cval + '</text>'))
        lbl.append('<text x="232" y="278" font-size="11" fill="#b3261e">ceramic</text>')
    if CONFIGS[key][1].get("csm"):
        o.append(f'<g {S}><line x1="478" y1="{sig}" x2="478" y2="218"/><line x1="460" y1="218" x2="496" y2="218"/>'
                 f'<line x1="460" y1="230" x2="496" y2="230"/><line x1="478" y1="230" x2="478" y2="{gnd}"/></g>')
        o.append('<g fill="#111"><circle cx="478" cy="150" r="5"/><circle cx="478" cy="310" r="5"/></g>')
        lbl.append('<text x="472" y="268" font-size="13" font-weight="bold" fill="#b3261e" text-anchor="end">C2 22 nF</text>')
        lbl.append('<text x="472" y="284" font-size="11" fill="#b3261e" text-anchor="end">smoothing</text>')
    if wiper:
        # trimmer from the jack to GND, wiper to R2
        o.append(f'<g {S}><line x1="260" y1="{sig}" x2="260" y2="190"/><rect x="250" y="190" width="20" height="80" fill="#fff"/>'
                 f'<line x1="260" y1="270" x2="260" y2="{gnd}"/><line x1="300" y1="230" x2="274" y2="230"/>'
                 f'<line x1="300" y1="230" x2="300" y2="{sig}"/><line x1="300" y1="{sig}" x2="380" y2="{sig}"/></g>')
        o.append('<polygon points="272,230 282,224 282,236" fill="#111"/>')
        o.append('<g fill="#111"><circle cx="260" cy="310" r="5"/></g>')
        frac = "0.3" if key == "trim03" else "0.1"
        lbl.append('<text x="178" y="182" font-size="13" font-weight="bold" fill="#b3261e" text-anchor="end">R1 1 MΩ</text>')
        lbl.append('<text x="178" y="198" font-size="11" fill="#b3261e" text-anchor="end">trimmer</text>')
        lbl.append(f'<text x="310" y="214" font-size="11" fill="#b3261e">wiper at {frac}</text>')
        lbl.append(f'<text x="310" y="228" font-size="11" fill="#b3261e">(passes {int(float(frac) * 100)} %)</text>')
    else:
        r1 = "100 kΩ" if cap else "1 MΩ"
        o.append(f'<g {S}><line x1="320" y1="{sig}" x2="320" y2="195"/><rect x="310" y="195" width="20" height="70" fill="#fff"/>'
                 f'<line x1="320" y1="265" x2="320" y2="{gnd}"/></g>')
        o.append('<g fill="#111"><circle cx="320" cy="150" r="5"/><circle cx="320" cy="310" r="5"/></g>')
        color = "#b3261e" if cap else "#111"
        lbl.append(f'<text x="338" y="234" font-size="13" font-weight="bold" fill="{color}">R1 {r1}</text>')
    # R2, zener, R3
    o.append(f'<g {S}><rect x="380" y="140" width="70" height="20" fill="#fff"/><line x1="450" y1="{sig}" x2="580" y2="{sig}"/>'
             f'<line x1="520" y1="{gnd}" x2="520" y2="248"/><line x1="520" y1="212" x2="520" y2="{sig}"/>'
             f'<rect x="580" y="140" width="60" height="20" fill="#fff"/><line x1="640" y1="{sig}" x2="760" y2="{sig}"/></g>')
    o.append('<g stroke="#111" stroke-width="2.5"><polygon points="503,248 537,248 520,216" fill="#111"/>'
             '<polyline points="497,218 503,212 537,212 543,206" fill="none"/></g>')
    o.append('<g fill="#111"><circle cx="520" cy="150" r="5"/><circle cx="520" cy="310" r="5"/></g>')
    lbl.append('<text x="415" y="130" font-size="13" font-weight="bold" fill="#111" text-anchor="middle">R2 10 kΩ</text>')
    lbl.append('<text x="610" y="130" font-size="13" font-weight="bold" fill="#111" text-anchor="middle">R3 1 kΩ</text>')
    zc = "#b3261e" if key == "bzx55" else "#111"
    lbl.append(f'<text x="548" y="230" font-size="13" font-weight="bold" fill="{zc}">D1 {zener}</text>')
    lbl.append(f'<text x="548" y="246" font-size="11" fill="#444">5.1 V zener, band up</text>')
    # Mega
    o.append('<rect x="760" y="50" width="130" height="300" rx="8" fill="#0f6e74"/>')
    o.append('<text x="825" y="190" font-size="15" font-weight="bold" fill="#fff" text-anchor="middle">Arduino</text>')
    o.append('<text x="825" y="210" font-size="15" font-weight="bold" fill="#fff" text-anchor="middle">Mega 2560</text>')
    o.append('<text x="770" y="155" font-size="13" font-weight="bold" fill="#fff">A0…A5</text>')
    o.append('<text x="770" y="315" font-size="13" font-weight="bold" fill="#fff">GND</text>')
    note = {"built": "the board as documented",
            "bzx55": "same board, the 0.5 W zener instead of the 1 W one",
            "cap100": "changed: C added across the disc, R1 1 MΩ → 100 kΩ",
            "cap200": "changed: C added across the disc, R1 1 MΩ → 100 kΩ",
            "cap100s": "changed: C across the disc, R1 → 100 kΩ, C2 from R2/R3 junction to GND",
            "trim03": "changed: R1 replaced by a trimmer, R2 on its wiper",
            "trim01": "changed: R1 replaced by a trimmer, R2 on its wiper"}[key]
    o.append(f'<text x="20" y="378" font-size="12" fill="{"#b3261e" if key != "built" else "#444"}">{esc(note)} (red = differs from as built)</text>')
    svg(os.path.join(FIGS, f"schematic-{key}.svg"), 900, 395, o + lbl)


# --- summary ---------------------------------------------------------------------

def window(res):
    """Disc voltages where the reading crosses 40 and 600 (log interpolation)."""
    pts = res["transfer"]

    def cross(level):
        if pts[0]["adc"] > level:
            return f"< {pts[0]['v']:g}"
        for a, b in zip(pts, pts[1:]):
            if a["adc"] <= level < b["adc"]:
                f = (level - a["adc"]) / (b["adc"] - a["adc"])
                return f"{10 ** (math.log10(a['v']) + f * (math.log10(b['v']) - math.log10(a['v']))):.2g}"
        return f"> {pts[-1]['v']:g}"
    return cross(run.THRESHOLD), cross(MAX_LEVEL)


def summary(all_res):
    lines = ["| config | velocity window | worst pin diode current | pin max | pin min | zener max power | "
             "longest above threshold | notes per hit | second hit (ADC alone / notes) |", "|" + "---|" * 9]
    for k, r in all_res.items():
        lo, hi = window(r)
        st = r["stress"]
        worst = max(max(s["iclo"], s["ichi"]) for s in st)
        ring = max(x["ring_ms"] for x in r["ring"])
        notes = sorted({x["notes"] for x in r["ring"]})
        d = r["detect"]
        lines.append(f"| {k} | {lo} – {hi} V | {worst * 1e6:.0f} µA | {max(s['pin_max'] for s in st):.2f} V "
                     f"| {min(s['pin_min'] for s in st):.2f} V | {max(s['pz'] for s in st) * 1e3:.0f} mW | {ring:.0f} ms "
                     f"| {notes} | {d['second_alone']} / {len(d['notes'])} notes {[(round(t), p, v) for t, p, v in d['notes']]} |")
    lines.append("")
    lines.append("transfer (V: adc/vel):")
    for k, r in all_res.items():
        lines.append(f"{k}: " + ", ".join(f"{x['v']:g}:{x['adc']}/{x['vel']}" for x in r["transfer"]))
    text = "\n".join(lines)
    with open(os.path.join(CACHE, "summary.md"), "w") as f:
        f.write(text + "\n")
    print(text)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--redo", action="store_true", help="ignore cached results")
    args = ap.parse_args()
    if args.redo and os.path.isdir(CACHE):
        for f in os.listdir(CACHE):
            os.remove(os.path.join(CACHE, f))
    os.makedirs(CACHE, exist_ok=True)
    with Pool(len(CONFIGS)) as pool:
        results = pool.map(compute, list(CONFIGS))
    all_res = {r["key"]: r for r in results}
    for k, r in all_res.items():
        schematic(k)
        fig_waves(r)
        fig_detect(r)
    fig_input(all_res["built"])
    fig_transfer(all_res)
    summary(all_res)


if __name__ == "__main__":
    main()
