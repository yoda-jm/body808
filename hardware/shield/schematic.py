"""Schematic of the body808 shield, written as a KiCad .kicad_sch file.

build_shield.py calls write() after building the board and passes every part
with the nets read back from its pads, so the drawing can't drift from the
board: each lane checks its nets against the board before drawing, symbols
and footprints share their UUIDs, and make_fab.sh runs KiCad's
schematic-parity check on top of the DRC.

The file is written in KiCad 9's format; make_fab.sh resaves it with
`kicad-cli sch upgrade` so it opens in KiCad 10 without a prompt.
"""
import re
import uuid

SYMLIB = "/app/extensions/Library/symbols"
NS = uuid.UUID("5d1f0c2e-4b8a-4c51-9a3e-808808808808")   # fixed, so every run gives the same UUIDs
G = 2.54


def uid(*key):
    return str(uuid.uuid5(NS, "/".join(str(k) for k in key)))


def q(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def sexpr_end(src, start):
    """Index just past the S-expression that opens at src[start]."""
    depth, i, in_str = 0, start, False
    while True:
        ch = src[i]
        if in_str:
            if ch == "\\":
                i += 1
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1


def library_symbol(lib, name):
    """Text of one symbol from KiCad's library, as it appears in the .kicad_sym file."""
    src = open(f"{SYMLIB}/{lib}.kicad_sym").read()
    m = re.search(r'\n\t\(symbol %s\n' % re.escape(q(name)), src)
    assert m, f"{lib}:{name} not found"
    return src[m.start() + 1:sexpr_end(src, m.start() + 1)]


def sds50j_symbol():
    """KiCad's DIN-5 (180 deg) symbol plus the SDS-50J's shield tabs as pin E, at the bottom."""
    s = library_symbol("Connector", "DIN-5_180degree")
    s = s.replace("DIN-5_180degree", "SDS-50J", 1).replace("DIN-5_180degree_", "SDS-50J_")
    s = re.sub(r'\(property "Value" "[^"]*"', '(property "Value" "SDS-50J"', s)
    s = re.sub(r'\(property "Footprint" "[^"]*"', '(property "Footprint" "body808:SDS-50J"', s)
    s = re.sub(r'\(property "Datasheet" "[^"]*"',
               '(property "Datasheet" "https://www.sameskydevices.com/product/resource/sds-50j.pdf"', s)
    s = re.sub(r'\(property "Description" "[^"]*"',
               '(property "Description" "CUI SDS-50J 5-pin 180 deg DIN socket, right angle, shield tabs on E"', s)
    pin_e = ('\t\t\t(pin passive line\n\t\t\t\t(at 0 -7.62 90)\n\t\t\t\t(length 2.54)\n'
             '\t\t\t\t(name "~"\n\t\t\t\t\t(effects\n\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t(size 1.27 1.27)\n'
             '\t\t\t\t\t\t)\n\t\t\t\t\t)\n\t\t\t\t)\n\t\t\t\t(number "E"\n\t\t\t\t\t(effects\n'
             '\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t\t)\n\t\t\t\t\t)\n\t\t\t\t)\n\t\t\t)\n')
    unit = s.index('(symbol "SDS-50J_1_1"')
    end = sexpr_end(s, unit) - 1
    return s[:end] + pin_e + "\t\t" + s[end:]


def write_symbol_library(path):
    """Project symbol library (body808.kicad_sym): the parts KiCad's libraries don't have."""
    with open(path, "w") as f:
        f.write('(kicad_symbol_lib\n\t(version 20251024)\n\t(generator "build_shield.py")\n'
                '\t(generator_version "10.0")\n')
        f.write(sds50j_symbol())
        f.write("\n)\n")


def pin_positions(text):
    """{pin number: (x, y)} in library coordinates (y up), at the pin's connection end."""
    out = {}
    for m in re.finditer(r'\(pin \S+ \S+\s+\(at (\S+) (\S+) \S+\).*?\(number "([^"]*)"', text, re.S):
        out[m.group(3)] = (float(m.group(1)), float(m.group(2)))
    return out


def place(x, y, rot, px, py):
    """Library point (y up) -> sheet point (y down) for a symbol at (x, y) turned by rot degrees."""
    dx, dy = {0: (px, -py), 90: (-py, -px), 180: (-px, py), 270: (py, px)}[rot]
    return round(x + dx, 3), round(y + dy, 3)


class Sheet:
    def __init__(self, project):
        self.project = project
        self.root = uid("root")
        self.libs = {}          # lib_id -> (text, pins)
        self.items = []
        self.n = 0
        self.npwr = 0

    def _id(self):
        self.n += 1
        return uid("item", self.n)

    def lib(self, lib_id):
        if lib_id not in self.libs:
            lib, name = lib_id.split(":")
            text = sds50j_symbol() if lib_id == "body808:SDS-50J" else library_symbol(lib, name)
            text = text.replace(f"(symbol {q(name)}", f"(symbol {q(lib_id)}", 1)
            self.libs[lib_id] = (text, pin_positions(text))
        return self.libs[lib_id]

    def symbol(self, lib_id, ref, value, x, y, rot=0, footprint="", fields=None,
               ref_at=None, value_at=None, hide_value=False, virtual=False, in_bom=True, in_pos_files=True):
        """Place a symbol; returns {pin: (x, y)}. ref_at / value_at: (dx, dy, justify) from (x, y)."""
        _, pins = self.lib(lib_id)
        angle = 90 if rot in (90, 270) else 0      # field angles are relative to the symbol: keep text level

        def prop(name, val, at=None, hide=False):
            dx, dy, just = at or (0, 0, None)
            if rot == 180 and just:             # KiCad mirrors the justification of a turned-over symbol
                just = {"left": "right", "right": "left"}[just]
            eff = "(font (size 1.27 1.27))" + (f" (justify {just})" if just else "") + (" (hide yes)" if hide else "")
            return f"\t\t(property {q(name)} {q(val)} (at {x + dx:g} {y + dy:g} {angle}) (effects {eff}))\n"

        out = [f"\t(symbol (lib_id {q(lib_id)}) (at {x:g} {y:g} {rot}) (unit 1)\n"
               f"\t\t(exclude_from_sim no) (in_bom {'yes' if in_bom and not virtual else 'no'}) (on_board yes)"
               f" (in_pos_files {'yes' if in_pos_files else 'no'}) (dnp no)\n"
               f"\t\t(uuid {q(uid('symbol', ref))})\n"]
        out.append(prop("Reference", ref, ref_at, hide=virtual or ref_at is None))
        out.append(prop("Value", value, value_at, hide=hide_value or value_at is None))
        out.append(prop("Footprint", footprint, hide=True))
        out.append(prop("Datasheet", "~" if not virtual else "", hide=True))
        out.append(prop("Description", "", hide=True))
        for k, v in (fields or {}).items():
            out.append(prop(k, v, hide=True))
        for num in pins:
            out.append(f"\t\t(pin {q(num)} (uuid {q(uid('pin', ref, num))}))\n")
        out.append(f"\t\t(instances (project {q(self.project)} (path {q('/' + self.root)} "
                   f"(reference {q(ref)}) (unit 1))))\n\t)\n")
        self.items.append("".join(out))
        return {num: place(x, y, rot, *p) for num, p in pins.items()}

    def power(self, name, x, y, show=True):
        """GND / +5V / PWR_FLAG symbol with its connection point at (x, y)."""
        self.npwr += 1
        ref = f"#FLG{self.npwr:02d}" if name == "PWR_FLAG" else f"#PWR{self.npwr:02d}"
        dy = {"GND": 3.81, "+5V": -3.81, "PWR_FLAG": -3.81}[name]
        self.symbol(f"power:{name}", ref, name, x, y, value_at=(0, dy, None), hide_value=not show, virtual=True)
        return x, y

    def wire(self, *pts):
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            self.items.append(f"\t(wire (pts (xy {x0:g} {y0:g}) (xy {x1:g} {y1:g})) "
                              f"(stroke (width 0) (type default)) (uuid {q(self._id())}))\n")

    def junction(self, x, y):
        self.items.append(f"\t(junction (at {x:g} {y:g}) (diameter 0) (color 0 0 0 0) (uuid {q(self._id())}))\n")

    def no_connect(self, x, y):
        self.items.append(f"\t(no_connect (at {x:g} {y:g}) (uuid {q(self._id())}))\n")

    def label(self, name, x, y, left=False):
        """Net label on a wire end; the text runs right (or left)."""
        rot, just = (180, "right bottom") if left else (0, "left bottom")
        self.items.append(f"\t(label {q(name.lstrip('/'))} (at {x:g} {y:g} {rot}) "
                          f"(effects (font (size 1.27 1.27)) (justify {just})) (uuid {q(self._id())}))\n")

    def text(self, s, x, y, size=1.27, bold=False, just="left bottom"):
        font = f"(size {size:g} {size:g})" + (" (bold yes)" if bold else "")
        self.items.append(f"\t(text {q(s)} (exclude_from_sim no) (at {x:g} {y:g} 0) "
                          f"(effects (font {font}) (justify {just})) (uuid {q(self._id())}))\n")

    def save(self, path, title, comments):
        head = [f'(kicad_sch (version 20250114) (generator "build_shield.py") (generator_version "9.0")\n'
                f'\t(uuid {q(self.root)})\n\t(paper "A4")\n'
                f'\t(title_block (title {q(title)}) (rev "v1")\n']
        for i, c in enumerate(comments, 1):
            head.append(f"\t\t(comment {i} {q(c)})\n")
        head.append("\t)\n\t(lib_symbols\n")
        for text, _ in self.libs.values():
            head.append("\t\t" + text.replace("\n", "\n\t") + "\n")
        head.append("\t)\n")
        tail = '\t(sheet_instances (path "/" (page "1")))\n\t(embedded_fonts no)\n)\n'
        with open(path, "w") as f:
            f.write("".join(head + self.items) + tail)


# ---------------------------------------------------------------------------------------------

def expect(part, nets):
    for pad, net in nets.items():
        got = part["pads"].get(pad)
        assert got == net, f"{part['ref']} pad {pad}: board has {got!r}, schematic draws {net!r}"


def sym(sheet, part, lib_id, x, y, rot=0, **kw):
    return sheet.symbol(lib_id, part["ref"], part["value"], x, y, rot, part["footprint"], part["fields"],
                        in_bom=part["in_bom"], in_pos_files=part["in_pos_files"], **kw)


def lane(sheet, parts, n, x, y):
    """One input, left to right: jack tip -> 10k -> 1k -> label A0..A7, with the 1M and the
    zener down to GND. The jack's sleeve and switch (TN) go straight to GND."""
    k = n - 1
    inn, clamp, out = f"/IN{n}", f"/CLAMP{n}", f"/A{k}"
    jack, r1, r2, d, r3 = (parts[r] for r in (f"J{20 + n}", f"R{n}01", f"R{n}02", f"D{n}01", f"R{n}03"))
    expect(jack, {"S": "GND", "T": inn, "TN": "GND"})
    expect(r1, {"1": inn, "2": "GND"})
    expect(r2, {"1": inn, "2": clamp})
    expect(d, {"1": clamp, "2": "GND"})
    expect(r3, {"1": clamp, "2": out})

    sheet.text(f"JACK{n} -> A{k}", x - 5.08, y - 6.35, 1.5, bold=True)
    j = sym(sheet, jack, "Connector_Audio:AudioJack2_SwitchT", x, y, 270,
            ref_at=(5.08, -1.27, "left"), value_at=(5.08, 1.27, "left"))
    sheet.power("GND", *j["S"], show=False)
    sheet.power("GND", *j["TN"], show=False)
    yc = y + 12.7
    n1, n2 = (x + 15.24, yc), (x + 35.56, yc)
    sheet.wire(j["T"], (x, yc), n1)
    sheet.label(inn, x + 2.54, yc)
    p = sym(sheet, r1, "Device:R", n1[0], yc + 3.81, 0, ref_at=(2.54, -1.27, "left"), value_at=(2.54, 1.27, "left"))
    sheet.power("GND", *p["2"], show=False)
    p = sym(sheet, r2, "Device:R", x + 21.59, yc, 90, ref_at=(0, -4.45, None), value_at=(0, -2.54, None))
    sheet.wire(n1, p["1"])
    sheet.wire(p["2"], n2)
    sheet.label(clamp, p["2"][0] + 1.27, yc)
    p = sym(sheet, d, "Device:D_Zener", n2[0], yc + 3.81, 270,
            ref_at=(2.54, -1.27, "left"), value_at=(2.54, 1.27, "left"))
    sheet.power("GND", *p["2"], show=False)
    p = sym(sheet, r3, "Device:R", x + 41.91, yc, 90, ref_at=(0, -4.45, None), value_at=(0, -2.54, None))
    sheet.wire(n2, p["1"])
    sheet.wire(p["2"], (x + 50.8, yc))
    sheet.label(out, x + 50.8, yc)
    sheet.junction(*n1)
    sheet.junction(*n2)


def header(sheet, part, x, y, title, mega, flag=False):
    """Pin header into the Mega, pins on its left: a label for each signal, the GND or +5V
    pins joined to one power symbol, X on the pins the shield doesn't use. The Mega's
    name for each pin is printed on the right."""
    n = len(mega)
    pins = sym(sheet, part, f"Connector_Generic:Conn_01x{n:02d}", x, y,
               ref_at=(0, -(n // 2) * G - 2.54, None), value_at=(0, (n + 1) // 2 * G + 2.54, None))
    ys = sorted(py for _, py in pins.values())
    sheet.text(title, x - 15.24, ys[0] - 8.89, 1.27, bold=True)
    power = {}
    for num, (px, py) in pins.items():
        net = part["pads"].get(num, "")
        sheet.text(mega[num], x + 2.54, py + 0.6, 1.0)
        if not net:
            sheet.no_connect(px, py)
        elif net in ("GND", "+5V"):
            power.setdefault(net, []).append(py)
        else:
            sheet.wire((px, py), (px - G, py))
            sheet.label(net, px - G, py, left=True)
    bx = pins["1"][0] - G
    for net, pys in power.items():
        pys.sort()
        # GND leaves below the header, +5V above it
        end = ys[-1] + G if net == "GND" else ys[0] - G
        attach = pys[-1] if net == "GND" else pys[0]
        for py in pys:
            sheet.wire((bx + G, py), (bx, py))
        for a, b in zip(pys, pys[1:]):
            sheet.wire((bx, a), (bx, b))
        sheet.wire((bx, attach), (bx, end))
        for py in pys:
            if len(pys) > 1 and (py == attach or py not in (pys[0], pys[-1])):
                sheet.junction(bx, py)
        sheet.power(net, bx, end)
        if flag:            # the Mega supplies this net
            sheet.wire((bx, end), (bx - 7.62, end))
            sheet.power("PWR_FLAG", bx - 7.62, end)
    return pins


def write(path, parts, mega_pins, project="body808-shield"):
    parts = {p["ref"]: p for p in parts}
    s = Sheet(project)

    # Inputs: 2 columns of 4 lanes.
    s.text("8 drum inputs", 17.78, 21.59, 2.0, bold=True)
    s.text("Piezo on the jack: tip +, sleeve -. With nothing plugged in, the jack's switch (TN) "
           "holds the tip at GND.", 17.78, 25.4, 1.27)
    s.text("1M bleeds the piezo, 10k + 5.1 V zener clamp its spikes, 1k protects the Mega pin.",
           17.78, 27.94, 1.27)
    for n in range(1, 9):
        col, row = divmod(n - 1, 4)
        lane(s, parts, n, 22.86 + 71.12 * col, 40.64 + 38.1 * row)

    # The Mega's headers.
    x0 = 190.5
    s.text("To the Arduino Mega (pin headers under the board)", 160.02, 21.59, 1.5, bold=True)
    header(s, parts["J3"], x0, 45.72, "Mega A0-A7", mega_pins["J3"])
    header(s, parts["J5"], x0, 81.28, "Mega A8-A15", mega_pins["J5"])
    header(s, parts["J1"], x0, 116.84, "Mega POWER", mega_pins["J1"], flag=True)
    header(s, parts["J6"], 251.46, 45.72, "Mega COMMUNICATION", mega_pins["J6"])
    header(s, parts["J7"], 251.46, 78.74, "Mega 5V (end of the 2x18 header)", mega_pins["J7"], flag=True)

    # MIDI OUT.
    din, r1, r2 = parts["J10"], parts["R1"], parts["R2"]
    expect(din, {"2": "GND", "E": "GND", "4": "/MIDI_SRC", "5": "/MIDI_SINK"})
    expect(r1, {"1": "+5V", "2": "/MIDI_SRC"})
    expect(r2, {"1": "/TX1", "2": "/MIDI_SINK"})
    xd, yd = 243.84, 116.84
    s.text("MIDI OUT (to the WIDI Master)", 208.28, 101.6, 1.5, bold=True)
    p = sym(s, din, "body808:SDS-50J", xd, yd, ref_at=(5.08, 6.35, "left"), value_at=(5.08, 8.89, "left"))
    s.no_connect(*p["1"]); s.no_connect(*p["3"])
    s.power("GND", *p["E"])
    s.wire(p["2"], (xd, yd - 10.16), (xd + 5.08, yd - 10.16))
    s.power("GND", xd + 5.08, yd - 10.16, show=False)
    a = sym(s, r1, "Device:R", xd - 24.13, yd - 2.54, 90, ref_at=(0, -4.45, None), value_at=(0, -2.54, None))
    s.wire(a["2"], p["4"])
    s.label("/MIDI_SRC", a["2"][0] + 1.27, yd - 2.54)
    s.wire(a["1"], (a["1"][0] - G, a["1"][1]))
    s.power("+5V", a["1"][0] - G, a["1"][1])
    b = sym(s, r2, "Device:R", xd + 24.13, yd - 2.54, 270, ref_at=(0, -4.45, None), value_at=(0, -2.54, None))
    s.wire(p["5"], b["2"])
    s.label("/MIDI_SINK", p["5"][0] + 1.27, yd - 2.54)
    s.wire(b["1"], (b["1"][0] + G, b["1"][1]))
    s.label("/TX1", b["1"][0] + G, b["1"][1])
    for i, line in enumerate(("Pin 4 = source (5V through R1), pin 5 = sink (TX1 through R2),",
                              "pin 2 and the shell (E) = GND, pins 1 and 3 not used.",
                              "The WIDI Master is powered from pins 4 and 2.")):
        s.text(line, 208.28, yd + 17.78 + 2.03 * i, 1.0)

    # Knob connector and test pads.
    knob = parts["J11"]
    expect(knob, {"1": "/A8", "2": "+5V", "3": "GND"})
    xk, yk = 172.72, 154.94
    s.text("Sensitivity knob", 157.48, 139.7, 1.5, bold=True)
    p = sym(s, knob, "Connector_Generic:Conn_01x03", xk, yk, 270,
            ref_at=(5.08, 1.27, "left"), value_at=(5.08, 3.81, "left"))
    s.power("+5V", *p["2"])
    s.wire(p["1"], (p["1"][0], yk - 7.62), (xk + 7.62, yk - 7.62))
    s.label("/A8", xk + 7.62, yk - 7.62)
    s.wire(p["3"], (p["3"][0], yk - 7.62), (xk - 7.62, yk - 7.62))
    s.power("GND", xk - 7.62, yk - 7.62)
    s.text("10k pot on a cable: ends to 5V and GND, wiper to pin 1 (A8).", 157.48, yk + 8.89, 1.0)

    tp1, tp2 = parts["TP1"], parts["TP2"]
    expect(tp1, {"1": "+5V"}); expect(tp2, {"1": "GND"})
    s.text("Test pads", 208.28, 144.78, 1.5, bold=True)
    p = sym(s, tp1, "Connector:TestPoint", 213.36, 154.94, 180, ref_at=(2.54, 2.54, "left"), value_at=(2.54, 5.08, "left"))
    s.power("+5V", *p["1"])
    p = sym(s, tp2, "Connector:TestPoint", 231.14, 154.94, 0, ref_at=(2.54, -3.81, "left"), value_at=(2.54, -1.27, "left"))
    s.power("GND", *p["1"])

    s.save(path, "body808 shield", [       # comment 1 is the bottom line of the title block
        "Generated by build_shield.py together with the board: edit the script, not this file",
        "Arduino Mega 2560 shield: 8 protected piezo inputs, MIDI OUT, sensitivity knob",
    ])
