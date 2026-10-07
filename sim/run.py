#!/usr/bin/env python3
"""Simulate piezo hits through the protection circuit with ngspice.

Runs sweeps over hit strength, hit shape and part tolerances, prints the
results as Markdown tables and writes SVG plots to sim/out/.

    python3 sim/run.py            # all sweeps
    python3 sim/run.py --quick    # fewer points

Needs ngspice on the PATH. Models: sim/body808.lib, explained in sim/README.md.
"""

import argparse
import math
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "body808.lib")
OUT = os.path.join(HERE, "out")

VCC = 5.0
ADC_MAX = 1023
THRESHOLD = 40   # default pad threshold in body808.ino (ADC counts)
MASK_MS = 30     # MASK_US in body808.ino
PIN_MIN, PIN_MAX = -0.5, 5.5   # ATmega2560 absolute maximum on a pin
CLAMP_SAFE = 0.5e-3            # clamp diode current hardware.md promises

# Hit shape: force half-sine of length T_MS, disc resonance F, quality factor Q.
# wiper: R1 as a trimmer, R2 on its wiper; fraction of the disc voltage passed
# on (1 = plain R1 resistor, the board as built). cpar: capacitor across the
# disc on the board, divides the voltage by (C0 + cpar) / C0. csm: smoothing
# capacitor from the R2/R3 junction to GND.
DEFAULT_HIT = dict(t_ms=1.0, f=4600.0, q=30.0, c0=20e-9, cable=0.3e-9, zener="1N4733A", wiper=1.0,
                   r1=1e6, cpar=0.0, csm=0.0)

# Same models as body808.lib, with BV as a parameter for the tolerance sweep.
ZENER_MODELS = {
    "1N4733A": "IS=1e-14 N=1 BV={bv} IBV=49m NBV=3 RS=2.5 CJO=200p M=0.33 VJ=0.75",
    "BZX55C5V1": "IS=1e-15 N=1 BV={bv} IBV=4.9m NBV=3 RS=25 CJO=60p M=0.33 VJ=0.75",
}
ZENER_BV = 4.98
ZENER_VARIANTS = {
    # name: (model, shift of the whole curve in volts)
    "1N4733A": ("1N4733A", 0.0),
    "1N4733A at −5 % (4.85 V)": ("1N4733A", -0.25),
    "1N4733A at +5 % (5.36 V)": ("1N4733A", +0.26),
    "1N4732A (4.7 V)": ("1N4733A", -0.4),
    "BZX55C5V1": ("BZX55C5V1", 0.0),
    "BZX55C5V1 at 4.8 V (low tol.)": ("BZX55C5V1", -0.3),
    "BZX55C5V1 at 5.4 V (high tol.)": ("BZX55C5V1", +0.3),
}

NETLIST = """body808 hit
.include {lib}
.model ZSIM D({zmodel})
VCC vcc 0 {vcc}
BF force 0 V = {amp} * ((time > 1m && time < {t_end}) ? sin(3.14159265*(time-1m)/{t_len}) : 0)
+ + {amp2} * ((time > {t2} && time < {t2_end}) ? sin(3.14159265*(time-{t2})/{t_len}) : 0)

* reference: disc + cable + R1 only, what a scope probe on the jack sees
XPR ref 0 force PIEZO C0={c0} CM={cm} F={f} Q={q}
CCR ref 0 {cable}
R1R ref 0 1Meg

* the real board
XPB tip 0 force PIEZO C0={c0} CM={cm} F={f} Q={q}
CCB tip 0 {cable_cpar}
R1A tip wiper {r1a}
R1B wiper 0 {r1b}
R2 wiper mid 10k
VIZ mid zk 0
DZ 0 zk ZSIM
CSM mid 0 {csm}
R3 mid pin 1k
XPIN pin vcc 0 AVRPIN

.options reltol=1e-4
.tran 2u {t_stop} 0 2u
.control
set wr_singlescale
set wr_vecnames
run
let izener = i(viz)
let iclo = v.xpin.viclo#branch
let ichi = v.xpin.vichi#branch
wrdata {data} v(ref) v(tip) v(mid) v(pin) izener iclo ichi
.endc
.end
"""


def zener_model(variant):
    model, shift = ZENER_VARIANTS[variant]
    return ZENER_MODELS[model].format(bv=ZENER_BV + shift)


def simulate(amp, hit, t_stop_ms=80, second=None):
    """Run one hit, return dict of column lists.

    second: optional (delay_ms, amp) for a second hit of the same shape.
    """
    with tempfile.TemporaryDirectory() as tmp:
        data = os.path.join(tmp, "out.txt")
        cir = os.path.join(tmp, "hit.cir")
        t_len = hit["t_ms"] * 1e-3
        with open(cir, "w") as f:
            f.write(NETLIST.format(
                lib=LIB, vcc=VCC, amp=amp,
                zmodel=zener_model(hit["zener"]),
                t_len=t_len, t_end=1e-3 + t_len,
                amp2=second[1] if second else 0, t2=1e-3 + (second[0] if second else 0) * 1e-3,
                t2_end=1e-3 + (second[0] if second else 0) * 1e-3 + t_len, c0=hit["c0"], cm=hit["c0"] / 10,
                f=hit["f"], q=hit["q"], cable=hit["cable"], data=data,
                r1a=max(1e-3, (1 - hit["wiper"]) * hit["r1"]), r1b=max(1e-3, hit["wiper"] * hit["r1"]),
                cable_cpar=hit["cable"] + hit["cpar"], csm=max(1e-15, hit["csm"]),
                t_stop=t_stop_ms * 1e-3))
        res = subprocess.run(["ngspice", "-b", cir], capture_output=True, text=True)
        if res.returncode != 0 or not os.path.exists(data):
            sys.exit(f"ngspice failed:\n{res.stdout}\n{res.stderr}")
        with open(data) as f:
            names = f.readline().split()
            cols = [[] for _ in names]
            for line in f:
                for i, v in enumerate(line.split()):
                    cols[i].append(float(v))
    keys = ["t", "ref", "tip", "mid", "pin", "iz", "iclo", "ichi"]
    return dict(zip(keys, cols))


_unit_cache = {}


def hit_for_peak(vpk, polarity, hit):
    """Scale the force so the reference node peaks at polarity * vpk.

    The reference node is linear, so a unit-force run gives the scale. A
    negative force gives the mirror image, so the same scale applies.
    """
    shape = tuple(sorted((k, v) for k, v in hit.items() if k not in ("zener", "wiper", "r1", "cpar", "csm")))
    if shape not in _unit_cache:
        _unit_cache[shape] = max(simulate(1.0, hit, t_stop_ms=10)["ref"])
    return simulate(polarity * vpk / _unit_cache[shape], hit)


def adc(v):
    return max(0, min(ADC_MAX, round(v / VCC * ADC_MAX)))


def firmware_notes(r):
    """(time ms, ADC peak) of each Note On, see firmware_trace()."""
    return firmware_trace(r)[1]


def firmware_trace(r):
    """Replay the pin voltage through body808.ino's detector for one pad.

    Same rules as updatePad(): threshold, 2.5 ms peak scan, 30 ms mask, then a
    retrigger threshold of half the last peak decaying over 80 ms. Samples
    every 0.2 ms, the firmware's scan period for 6 pads. Returns the samples
    as (time ms, ADC value, threshold or None while masked) and the
    (time ms, ADC peak) of each Note On.
    """
    scan_ms, decay_ms, period_ms = 2.5, 80.0, 0.2
    samples, notes, state, peak, start, last_hit, last_peak = [], [], "idle", 0, 0.0, 0.0, 0
    t_s = r["t"]
    i = 0
    t = t_s[0] * 1e3
    while t <= t_s[-1] * 1e3:
        while i + 1 < len(t_s) and t_s[i + 1] * 1e3 <= t:
            i += 1
        value = adc(r["pin"][i])
        thr = None
        if state == "idle":
            thr = THRESHOLD
            since = t - last_hit
            if last_peak and since < MASK_MS + decay_ms:
                thr = max(THRESHOLD, int(last_peak * 0.5 * (1 - (since - MASK_MS) / decay_ms)))
            samples.append((t, value, thr))
            if value > thr:
                state, start, peak = "scan", t, value
        elif state == "scan":
            samples.append((t, value, thr))
            peak = max(peak, value)
            if t - start >= scan_ms:
                notes.append((t, peak))
                state, last_hit, last_peak = "masked", t, peak
        else:
            samples.append((t, value, thr))
            if t - last_hit >= MASK_MS:
                state = "idle"
        t += period_ms
    return samples, notes


def analyse(r):
    pin = r["pin"]
    thr_v = THRESHOLD * VCC / ADC_MAX
    above = [t for t, v in zip(r["t"], pin) if v > thr_v]
    first = above[0] if above else None
    last = above[-1] if above else None
    # zener power: current times voltage across it
    pz = max(abs(i * v) for i, v in zip(r["iz"], r["mid"]))
    return dict(
        ref_max=max(r["ref"]), ref_min=min(r["ref"]),
        pin_max=max(pin), pin_min=min(pin), adc=adc(max(pin)),
        iclo=max(r["iclo"]), ichi=max(r["ichi"]),
        iz=max(abs(i) for i in r["iz"]), pz=pz,
        ring_ms=(last - first) * 1e3 if above else 0.0,
    )


def fmt_i(a):
    a = abs(a)
    if a >= 1e-3:
        return f"{a * 1e3:.1f} mA"
    if a >= 1e-6:
        return f"{a * 1e6:.0f} µA"
    return "< 1 µA"


def ok(cond):
    return "ok" if cond else "**FAIL**"


# --- sweeps ----------------------------------------------------------------

def sweep_stress(peaks):
    print("## 1. Stress: hit strength and polarity\n")
    print(f"Hit: {DEFAULT_HIT['t_ms']} ms force pulse, disc {DEFAULT_HIT['f']/1e3:.1f} kHz, "
          f"Q {DEFAULT_HIT['q']:.0f}. `piezo` is the voltage across the disc with only R1 "
          f"(what a scope would show).\n")
    print("| piezo peak | pin max | pin min | ADC | clamp → GND | clamp → 5V | zener peak | zener power | clamp currents < 0.5 mA |")
    print("|---|---|---|---|---|---|---|---|---|")
    worst = None
    for pol in (+1, -1):
        for vpk in peaks:
            a = analyse(hit_for_peak(vpk, pol, DEFAULT_HIT))
            safe = a["iclo"] < CLAMP_SAFE and a["ichi"] < CLAMP_SAFE
            print(f"| {pol * vpk:+g} V | {a['pin_max']:.2f} V | {a['pin_min']:.2f} V | {a['adc']} "
                  f"| {fmt_i(a['iclo'])} | {fmt_i(a['ichi'])} | {fmt_i(a['iz'])} "
                  f"| {a['pz'] * 1e3:.0f} mW | {ok(safe)} |")
            if worst is None or a["iclo"] > worst["iclo"]:
                worst = a
    print(f"\nWorst clamp diode current: {fmt_i(worst['iclo'])} "
          f"({ok(worst['iclo'] < CLAMP_SAFE)} against the {fmt_i(CLAMP_SAFE)} in hardware.md).\n")


def sweep_tolerance():
    print("## 2. Part tolerances at a 100 V hit\n")
    print("| variant | +100 V: pin max | −100 V: pin min | worst clamp current | ADC at +5 V hit | ok |")
    print("|---|---|---|---|---|---|")
    variants = [(z, {"zener": z}) for z in ZENER_VARIANTS]
    variants += [("disc 14 nF (−30 %)", {"c0": 14e-9}), ("disc 26 nF (+30 %)", {"c0": 26e-9}),
                 ("2 m cable (1 nF)", {"cable": 1e-9})]
    for name, change in variants:
        hit = dict(DEFAULT_HIT, **change)
        pos = analyse(hit_for_peak(100, +1, hit))
        neg = analyse(hit_for_peak(100, -1, hit))
        small = analyse(hit_for_peak(5, +1, hit))
        worst = max(pos["iclo"], pos["ichi"], neg["iclo"], neg["ichi"])
        print(f"| {name} | {pos['pin_max']:.2f} V | {neg['pin_min']:.2f} V | {fmt_i(worst)} "
              f"| {small['adc']} | {ok(worst < CLAMP_SAFE)} |")
    print()


def sweep_ringing():
    print("## 3. Ringing and tail: does the firmware play one note per hit?\n")
    print(f"`above thr.`: how long the pin stays above the {THRESHOLD}-count threshold "
          f"({THRESHOLD * VCC / ADC_MAX:.2f} V); MASK_US is {MASK_MS} ms. `notes`: Note Ons "
          f"from replaying the pin voltage through the firmware's detector, should be 1.\n")
    print("| force pulse | Q | 5 V hit | 20 V hit | 60 V hit |")
    print("|---|---|---|---|---|")
    for t_ms in (0.2, 1.0, 3.0):
        for q in (10, 30, 90):
            hit = dict(DEFAULT_HIT, t_ms=t_ms, q=q)
            cells = []
            for vpk in (5, 20, 60):
                r = hit_for_peak(vpk, +1, hit)
                ring = analyse(r)["ring_ms"]
                n = len(firmware_notes(r))
                cells.append(f"{ring:.0f} ms, {n} note" + ("" if n == 1 else "s **FAIL**"))
            print(f"| {t_ms} ms | {q} | " + " | ".join(cells) + " |")
    print()


def sweep_transfer(peaks):
    print("## 4. Transfer: piezo peak → ADC reading\n")
    print("| piezo peak | ADC (simulated) | ADC without the zener | lost to the zener's knee |")
    print("|---|---|---|---|")
    rows = []
    gain = None  # pin volts per disc volt, from the first (smallest) hit
    for vpk in peaks:
        a = analyse(hit_for_peak(vpk, +1, DEFAULT_HIT))
        if gain is None:
            gain = a["pin_max"] / vpk
        ideal = adc(vpk * gain)
        rows.append((vpk, a["adc"], ideal))
        loss = f"{max(0, 100 * (1 - a['adc'] / ideal)):.0f} %" if ideal else "-"
        print(f"| {vpk:g} V | {a['adc']} | {ideal} | {loss} |")
    print()
    return rows


# --- SVG plots ---------------------------------------------------------------

INK, INK2, GRID, SURFACE = "#1f1f1e", "#62615a", "#e4e3dc", "#fcfcfb"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]


def svg_panel(x0, y0, w, h, xs_list, ys_list, xr, yr, labels, title, ylabel, refs=(),
              xlabel=None, logx=False, xticks=(), yticks=()):
    def sx(x):
        if logx:
            return x0 + (math.log10(x) - math.log10(xr[0])) / (math.log10(xr[1]) - math.log10(xr[0])) * w
        return x0 + (x - xr[0]) / (xr[1] - xr[0]) * w

    def sy(y):
        return y0 + h - (y - yr[0]) / (yr[1] - yr[0]) * h

    out = [f'<text x="{x0}" y="{y0 - 12}" font-size="13" font-weight="600" fill="{INK}">{title}</text>']
    for t in yticks:
        out.append(f'<line x1="{x0}" x2="{x0 + w}" y1="{sy(t):.1f}" y2="{sy(t):.1f}" stroke="{GRID}"/>')
        out.append(f'<text x="{x0 - 6}" y="{sy(t) + 4:.1f}" font-size="11" fill="{INK2}" text-anchor="end">{t:g}</text>')
    for t in xticks:
        out.append(f'<text x="{sx(t):.1f}" y="{y0 + h + 16}" font-size="11" fill="{INK2}" text-anchor="middle">{t:g}</text>')
    out.append(f'<text x="{x0 - 40}" y="{y0 + h / 2}" font-size="11" fill="{INK2}" text-anchor="middle" '
               f'transform="rotate(-90 {x0 - 40} {y0 + h / 2})">{ylabel}</text>')
    if xlabel:
        out.append(f'<text x="{x0 + w / 2}" y="{y0 + h + 34}" font-size="11" fill="{INK2}" text-anchor="middle">{xlabel}</text>')
    for yv, text in refs:
        out.append(f'<line x1="{x0}" x2="{x0 + w}" y1="{sy(yv):.1f}" y2="{sy(yv):.1f}" stroke="{INK2}" stroke-dasharray="4 3"/>')
        out.append(f'<text x="{x0 + w - 4}" y="{sy(yv) - 4:.1f}" font-size="10" fill="{INK2}" text-anchor="end">{text}</text>')
    out.append(f'<line x1="{x0}" x2="{x0 + w}" y1="{y0 + h}" y2="{y0 + h}" stroke="{INK2}"/>')
    for i, (xs, ys) in enumerate(zip(xs_list, ys_list)):
        pts = " ".join(f"{sx(x):.1f},{sy(max(yr[0], min(yr[1], y))):.1f}" for x, y in zip(xs, ys))
        out.append(f'<polyline points="{pts}" fill="none" stroke="{SERIES[i]}" stroke-width="2" stroke-linejoin="round"/>')
    # legend, one row above the plot
    lx = x0 + w
    for i, text in reversed(list(enumerate(labels))):
        lx -= 9 * len(text) + 28
        out.append(f'<line x1="{lx}" x2="{lx + 16}" y1="{y0 - 16}" y2="{y0 - 16}" stroke="{SERIES[i]}" stroke-width="2"/>')
        out.append(f'<text x="{lx + 22}" y="{y0 - 12}" font-size="11" fill="{INK}">{text}</text>')
    return out


def svg_write(path, w, h, body):
    with open(path, "w") as f:
        f.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
                f'font-family="system-ui, -apple-system, Segoe UI, sans-serif">\n'
                f'<rect width="{w}" height="{h}" fill="{SURFACE}"/>\n' + "\n".join(body) + "\n</svg>\n")


def plot_waveforms():
    """A hard stomp, both polarities: disc voltage and pin voltage."""
    hits = [(+50, "+50 V hit"), (-50, "−50 V hit")]
    runs = [hit_for_peak(abs(v), 1 if v > 0 else -1, DEFAULT_HIT) for v, _ in hits]
    t = [x * 1e3 for x in runs[0]["t"]]
    keep = [i for i, x in enumerate(t) if x <= 12][::5]  # 10 us steps, enough for 4.6 kHz
    tk = [t[i] for i in keep]
    labels = [l for _, l in hits]
    body = svg_panel(70, 50, 620, 200, [tk, tk], [[r["ref"][i] for i in keep] for r in runs],
                     (0, 12), (-60, 60), labels, "Voltage across the disc (R1 only, no protection)",
                     "volts", yticks=(-50, -25, 0, 25, 50), xticks=range(0, 13, 2))
    body += svg_panel(70, 330, 620, 200, [tk, tk], [[r["pin"][i] for i in keep] for r in runs],
                      (0, 12), (-1, 6.5), labels, "Voltage at the analog pin (after R2, zener, R3)",
                      "volts", refs=((PIN_MAX, "5.5 V pin limit"), (PIN_MIN, "−0.5 V pin limit"),
                                     (THRESHOLD * VCC / ADC_MAX, "threshold (40)")),
                      xlabel="time (ms)", yticks=(0, 2, 4, 6), xticks=range(0, 13, 2))
    svg_write(os.path.join(OUT, "waveforms.svg"), 720, 580, body)


def plot_transfer(rows):
    xs = [r[0] for r in rows]
    body = svg_panel(70, 50, 620, 260, [xs, xs], [[r[1] for r in rows], [r[2] for r in rows]],
                     (xs[0], xs[-1]), (0, 1100), ["simulated", "perfectly linear"],
                     "ADC reading vs piezo peak", "ADC counts",
                     refs=((THRESHOLD, "threshold"), (600, "maxLevel (velocity 127)")),
                     xlabel="piezo peak voltage (log scale)", logx=True,
                     xticks=[x for x in (0.2, 0.5, 1, 2, 5, 10, 20, 50, 100) if xs[0] <= x <= xs[-1]],
                     yticks=(0, 256, 512, 768, 1023))
    svg_write(os.path.join(OUT, "transfer.svg"), 720, 360, body)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--quick", action="store_true", help="fewer sweep points")
    ap.add_argument("--zener", choices=ZENER_MODELS, default=DEFAULT_HIT["zener"],
                    help="zener on the board (default: %(default)s)")
    ap.add_argument("--wiper", type=float, default=1.0,
                    help="R1 as a 1 Mohm trimmer: fraction of the disc voltage passed on (default 1)")
    ap.add_argument("--r1", type=float, default=1e6, help="R1 in ohm (default 1e6)")
    ap.add_argument("--cpar", type=float, default=0.0,
                    help="capacitor across the disc on the board, in farad (default none)")
    ap.add_argument("--only", choices=("stress", "tolerance", "ringing", "transfer"),
                    help="run one sweep, no plots")
    args = ap.parse_args()
    DEFAULT_HIT["zener"] = args.zener
    DEFAULT_HIT["wiper"] = args.wiper
    DEFAULT_HIT["r1"] = args.r1
    DEFAULT_HIT["cpar"] = args.cpar
    os.makedirs(OUT, exist_ok=True)

    stress = (1, 5, 20, 100) if args.quick else (1, 2, 5, 10, 20, 50, 100, 200)
    transfer = (0.2, 1, 3, 5, 10, 50) if args.quick else \
        (0.2, 0.3, 0.5, 0.7, 1, 1.5, 2, 3, 4, 5, 6, 8, 10, 15, 20, 30, 50, 100)

    trim = f", R1 {args.r1:g} ohm" if args.r1 != 1e6 else ""
    trim += f", R1 trimmer at {args.wiper:g}" if args.wiper < 1 else ""
    trim += f", {args.cpar * 1e9:g} nF across the disc" if args.cpar else ""
    print(f"# body808 protection circuit simulation, {args.zener}{trim}\n")
    if args.only:
        sweeps = dict(stress=lambda: sweep_stress(stress), tolerance=sweep_tolerance,
                      ringing=sweep_ringing, transfer=lambda: sweep_transfer(transfer))
        sweeps[args.only]()
        return
    sweep_stress(stress)
    sweep_tolerance()
    sweep_ringing()
    rows = sweep_transfer(transfer)
    plot_waveforms()
    plot_transfer(rows)
    print(f"Plots: {os.path.relpath(OUT)}/waveforms.svg, transfer.svg")


if __name__ == "__main__":
    main()
