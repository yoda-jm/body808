#!/usr/bin/env python3
"""Tune the firmware's retrigger settings on simulated hits.

    python3 sim/tuning.py           # simulate (cached in sim/out/report/), replay, draw
    python3 sim/tuning.py --redo    # ignore the cache

For each board configuration, the pin voltage of single hits (every shape and
strength) and of soft-after-loud pairs is replayed through the firmware with
lower RETRIGGER_RATIO, DECAY_US and MASK_US values:
  - a single hit must give exactly one note (no ringing or tail retrigger),
  - a pair should give two notes (the soft hit is not swallowed).
Prints the results as Markdown and draws docs/sim/tuning.svg.
"""

import argparse
import itertools
import json
import os
from multiprocessing import Pool

import report
import run

CONFIGS = ("built", "cap100", "cap200")
SINGLE_SHAPES = report.SHAPES                  # 0.2 / 1 / 3 ms x Q 10 / 30 / 90
SINGLE_V = (5, 20, 60, 100)
PAIR_SHAPES = ((0.2, 30), (1.0, 30))
PAIR_FIRST = 20
PAIR_DELAYS = (35, 45, 60, 80, 110)           # ms between the two hits
PAIR_RATIOS = (0.5, 0.25, 0.1)                # second hit / first hit, in disc volts
RATIOS = (0.5, 0.35, 0.25, 0.15, 0.1)
DECAYS = (80, 50, 30, 15)
MASKS = (30, 20, 15)
PHASES = (0.0, 0.1)                            # firmware sampling offset, ms
CURRENT = (0.5, 80, 30)        # before tuning
RECOMMENDED = (0.25, 50, 30)   # now in body808.ino


def trace(r):
    """The run's time and pin voltage every 10 us, enough for the 0.2 ms replay."""
    return {"t": r["t"][::5], "pin": r["pin"][::5]}


def alone(key, res):
    """Each pair's second hit on its own: does the firmware play it at all?"""
    hit = dict(run.DEFAULT_HIT, **report.CONFIGS[key][1])
    out = {}
    for t_ms, q in PAIR_SHAPES:
        h = dict(hit, t_ms=t_ms, q=q)
        u = report.unit(h)
        for k in PAIR_RATIOS:
            r = run.simulate(k * PAIR_FIRST / u, h)
            out[f"{t_ms}/{k}"] = all(len(run.firmware_trace(r, phase_ms=ph)[1]) == 1 for ph in PHASES)
    res["alone"] = out
    return res


def compute(key):
    path = os.path.join(report.CACHE, f"tuning-{key}.json")
    if os.path.exists(path):
        with open(path) as f:
            res = json.load(f)
        if "alone" not in res:
            res = alone(key, res)
            with open(path, "w") as f:
                json.dump(res, f)
        return res
    hit = dict(run.DEFAULT_HIT, **report.CONFIGS[key][1])
    singles, pairs = [], []
    for t_ms, q in SINGLE_SHAPES:
        h = dict(hit, t_ms=t_ms, q=q)
        u = report.unit(h)
        for v in SINGLE_V:
            singles.append({"t_ms": t_ms, "q": q, "v": v, **trace(run.simulate(v / u, h))})
    for t_ms, q in PAIR_SHAPES:
        h = dict(hit, t_ms=t_ms, q=q)
        u = report.unit(h)
        for d in PAIR_DELAYS:
            for k in PAIR_RATIOS:
                r = run.simulate(PAIR_FIRST / u, h, t_stop_ms=d + 50, second=(d, k * PAIR_FIRST / u))
                pairs.append({"t_ms": t_ms, "q": q, "delay": d, "ratio": k, **trace(r)})
    res = alone(key, {"key": key, "singles": singles, "pairs": pairs})
    os.makedirs(report.CACHE, exist_ok=True)
    with open(path, "w") as f:
        json.dump(res, f)
    return res


def playable(res):
    """Pairs whose second hit would play on its own: the ones that count."""
    return [p for p in res["pairs"] if res["alone"][f"{p['t_ms']}/{p['ratio']}"]]


def score(res, ratio, decay, mask):
    """(single hits not giving exactly 1 note, playable pairs not giving 2 notes)."""
    bad_single, missed = 0, []
    for s in res["singles"]:
        if any(len(run.firmware_trace(s, ratio, decay, mask, ph)[1]) != 1 for ph in PHASES):
            bad_single += 1
    for p in res["pairs"]:
        if not res["alone"][f"{p['t_ms']}/{p['ratio']}"]:
            continue  # too soft to play even on its own
        if any(len(run.firmware_trace(p, ratio, decay, mask, ph)[1]) != 2 for ph in PHASES):
            missed.append(p)
    return bad_single, missed


def grid(res):
    out = {}
    for ratio, decay, mask in itertools.product(RATIOS, DECAYS, MASKS):
        bad, missed = score(res, ratio, decay, mask)
        out[(ratio, decay, mask)] = (bad, missed)
    return out


# --- figure -----------------------------------------------------------------

def fig(grids, results):
    """Per configuration and mask: missed pairs by ratio x decay, crossed out when singles double-trigger."""
    from report import INK, INK2, svg, esc, CONFIGS as NAMES
    cell, gapx = 34, 36
    left, y0 = 120, 130
    out = [f'<text x="20" y="30" font-size="15" font-weight="bold" fill="{INK}">Lower retrigger settings catch soft hits after loud ones,</text>',
           f'<text x="20" y="49" font-size="15" font-weight="bold" fill="{INK}">until ringing or the zener tail plays a second note</text>',
           f'<text x="20" y="70" font-size="11.5" fill="{INK2}">Number: soft-after-loud pairs missed (second hit 1/2, 1/4 or 1/10 of the first, 35 to 110 ms later).</text>',
           f'<rect x="20" y="80" width="14" height="14" rx="3" fill="#f6d5d1"/><text x="40" y="91" font-size="11.5" fill="{INK2}">a single hit plays twice: unusable</text>',
           f'<rect x="250" y="80" width="14" height="14" rx="3" fill="none" stroke="{INK}" stroke-width="2"/><text x="270" y="91" font-size="11.5" fill="{INK2}">previous firmware</text>',
           f'<rect x="390" y="80" width="14" height="14" rx="3" fill="none" stroke="#1baf7a" stroke-width="2.5"/><text x="410" y="91" font-size="11.5" fill="{INK2}">new firmware (0.25, 50 ms, 30 ms)</text>']
    block_w = len(DECAYS) * cell
    for ci, key in enumerate(CONFIGS):
        g = grids[key]
        by = y0 + ci * (len(RATIOS) * cell + 70)
        total = len(playable(results[key]))
        out.append(f'<text x="20" y="{by + 2}" font-size="13" font-weight="bold" fill="{INK}">{esc(NAMES[key][0])}: '
                   f'missed out of {total} pairs</text>')
        for mi, mask in enumerate(MASKS):
            bx = left + mi * (block_w + gapx)
            out.append(f'<text x="{bx + block_w / 2}" y="{by + 22}" font-size="11" fill="{INK2}" text-anchor="middle">mask {mask} ms · decay (ms) →</text>')
            for di, decay in enumerate(DECAYS):
                out.append(f'<text x="{bx + di * cell + cell / 2}" y="{by + 38}" font-size="10.5" fill="{INK2}" text-anchor="middle">{decay}</text>')
            for ri, ratio in enumerate(RATIOS):
                y = by + 44 + ri * cell
                if mi == 0:
                    out.append(f'<text x="{bx - 8}" y="{y + cell / 2 + 4}" font-size="10.5" fill="{INK2}" text-anchor="end">ratio {ratio:g}</text>')
                for di, decay in enumerate(DECAYS):
                    x = bx + di * cell
                    bad, missed = g[(ratio, decay, mask)]
                    share = len(missed) / total
                    if bad:
                        out.append(f'<rect x="{x + 1}" y="{y + 1}" width="{cell - 2}" height="{cell - 2}" rx="3" fill="#f6d5d1"/>')
                        out.append(f'<text x="{x + cell / 2}" y="{y + cell / 2 + 4}" font-size="10" fill="#b3261e" text-anchor="middle">2×</text>')
                    else:
                        fill = f"rgba(42,120,214,{0.06 + 0.8 * share:.2f})"
                        out.append(f'<rect x="{x + 1}" y="{y + 1}" width="{cell - 2}" height="{cell - 2}" rx="3" fill="{fill}"/>')
                        color = "#fff" if share > 0.55 else INK
                        out.append(f'<text x="{x + cell / 2}" y="{y + cell / 2 + 4}" font-size="11" fill="{color}" text-anchor="middle">{len(missed)}</text>')
                    if (ratio, decay, mask) == CURRENT:
                        out.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3" fill="none" stroke="{INK}" stroke-width="2"/>')
                    if (ratio, decay, mask) == RECOMMENDED:
                        out.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3" fill="none" stroke="#1baf7a" stroke-width="2.5"/>')
    h = y0 + len(CONFIGS) * (len(RATIOS) * cell + 70) - 10
    svg(os.path.join(report.FIGS, "tuning.svg"), max(620, left + len(MASKS) * (block_w + gapx) + 10), h, out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--redo", action="store_true", help="ignore cached simulations")
    args = ap.parse_args()
    if args.redo:
        for k in CONFIGS:
            p = os.path.join(report.CACHE, f"tuning-{k}.json")
            if os.path.exists(p):
                os.remove(p)
    with Pool(len(CONFIGS)) as pool:
        results = pool.map(compute, CONFIGS)
        grids = dict(zip(CONFIGS, pool.map(grid, results)))
    n_single = len(SINGLE_SHAPES) * len(SINGLE_V)
    print(f"Single hits: {n_single} per config; playable pairs: "
          f"{ {k: len(playable(r)) for k, r in zip(CONFIGS, results)} }\n")
    for key in CONFIGS:
        g = grids[key]
        print(f"## {key}\n")
        print("| ratio | decay | mask | singles not 1 note | pairs missed | missed (shape, delay, ratio) |")
        print("|---|---|---|---|---|---|")
        for combo, (bad, missed) in sorted(g.items(), key=lambda kv: (kv[1][0] > 0, len(kv[1][1]), -kv[0][0])):
            ms = ", ".join(f"{p['t_ms']}/{p['delay']}/{p['ratio']}" for p in missed)
            print(f"| {combo[0]} | {combo[1]} | {combo[2]} | {bad} | {len(missed)} | {ms} |")
        print()
    # settings safe on every configuration
    print("## safe everywhere (no single double-triggers), fewest misses summed\n")
    rows = []
    for combo in grids[CONFIGS[0]]:
        if all(grids[k][combo][0] == 0 for k in CONFIGS):
            rows.append((sum(len(grids[k][combo][1]) for k in CONFIGS), combo,
                         [len(grids[k][combo][1]) for k in CONFIGS]))
    for tot, combo, per in sorted(rows, key=lambda r: (r[0], -r[1][0]))[:15]:
        print(f"{combo}: total missed {tot}, per config {dict(zip(CONFIGS, per))}")
    fig(grids, dict(zip(CONFIGS, results)))


if __name__ == "__main__":
    main()
