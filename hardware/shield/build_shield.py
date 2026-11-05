#!/usr/bin/env python3
"""Generate the body808 shield PCB for KiCad 10.

The shield plugs on top of an Arduino Mega 2560 and overhangs it on the
digital-pin side: the new edge carries the MIDI OUT socket and 8 side-entry
3.5 mm jacks. Each jack feeds one protection channel (1M, 10k, 5.1 V zener,
1k) wired to A0-A7. A JST-XH connector brings out 5V / A8 / GND for the
optional sensitivity knob.

The same run writes the schematic (schematic.py) from the board's own nets,
and the project libraries for the two parts KiCad doesn't have (body808.pretty,
body808.kicad_sym).

Run inside KiCad's Python (Flatpak):
    flatpak run --command=python3 org.kicad.KiCad hardware/shield/build_shield.py

Coordinates are in mm, in the frame of KiCad's Arduino_Mega template
(Mega outline x 100-201.7, y 46.66-100; digital header row y=49.2,
power/analog row y=97.46).
"""
import os

import pcbnew

import schematic

LIB = "/app/extensions/Library/Footprints/footprints"
TPL = "/app/extensions/Library/Templates/template/Arduino_Mega/Arduino_Mega.kicad_pcb"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("SHIELD_OUT", os.path.join(HERE, "body808-shield.kicad_pcb"))
PROJECT_LIB = os.path.join(HERE, "body808.pretty")

MEGA_TOP = 46.66          # Mega edge on the digital-pin side
OVERHANG = 17.0           # deepest connector pin (DIN pins 4/5) is 15 mm behind the edge
TOP = MEGA_TOP - OVERHANG
BOTTOM, LEFT, RIGHT = 100.0, 100.0, 199.0

TRACK = 0.3
VIA_D, VIA_DRILL = 0.8, 0.4

# Mega areas the shield must not touch from below: no THT pads, vias or
# bottom copper over them (template's User.Drawings, plus margins).
KEEPOUTS = {
    "USB + 16U2 ICSP": (100.0, MEGA_TOP, 120.5, 70.0),
    "power jack": (100.0, 86.0, 112.0, BOTTOM),
    "2560 ICSP": (161.3, 67.2, 168.5, 76.9),
}

CHANNELS = 8
J3_X0 = 150.80            # A0 pin; A0..A7 every 2.54 mm on y=97.46
HDR_Y = 97.46             # power / analog header row
DIG_Y = 49.20             # digital header row
PITCH = 8.0               # jack spacing along the edge (PJ-316 body is 7.0 wide)
BLOCK_TOP = 53.0          # protection parts start below the digital header row
LANE_Y = (48.8, 54.8, 60.0, 67.5)   # part centres down a lane: 1M, 10k, zener, 1k
DIN_X = 185.5             # MIDI socket centre (top-right corner)
KNOB_PIN1 = (186.06, 91.5)   # knob connector pin 1 (lower right, opening toward the right edge)

# LCSC part numbers (JLCPCB assembly)
LCSC = {
    "1M": "C17927", "10k": "C17902", "1k": "C4410", "220": "C17957",
    "zener": "C19077476", "jack": "C5123139",
    "din": "C6216157", "jst": "C157928", "header": "C492407",
}


def mm(v):
    return pcbnew.FromMM(v)


def pt(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


def set_fields(fp, fields):
    """Extra footprint fields (LCSC part number...), kept off the silkscreen."""
    for k, v in fields.items():
        fp.SetField(k, v)
        fp.GetField(k).SetVisible(False)


class Board:
    def __init__(self):
        self.b = pcbnew.CreateEmptyBoard()
        self.nets = {}
        self.tpl = pcbnew.LoadBoard(TPL)
        self.mega = {}              # header ref -> {pad: the Mega's name for that pin}

    def net(self, name):
        if name not in ("GND", "+5V") and not name.startswith("unconnected-"):
            name = "/" + name           # KiCad's name for a net set by a label on the root sheet
        if name not in self.nets:
            n = pcbnew.NETINFO_ITEM(self.b, name)
            self.b.Add(n)
            self.nets[name] = n
        return self.nets[name]

    def footprint(self, lib, name, ref, value, x, y, rot=0, back=False, fields=None, dnp=False):
        fp = pcbnew.FootprintLoad(PROJECT_LIB if lib == "body808" else f"{LIB}/{lib}.pretty", name)
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        # Same UUID as the symbol, so KiCad pairs them (schematic parity, "Update PCB").
        fp.SetPath(pcbnew.KIID_PATH("/" + schematic.uid("symbol", ref)))
        fp.SetSheetname("/")
        fp.SetSheetfile("body808-shield.kicad_sch")
        fp.SetReference(ref)
        fp.SetValue(value)
        self.b.Add(fp)
        fp.SetPosition(pt(x, y))
        fp.SetOrientationDegrees(rot)
        if back:
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        set_fields(fp, fields or {})
        fp.Reference().SetVisible(False)
        if dnp:
            fp.SetDNP(True)
            fp.SetExcludedFromBOM(True)
            fp.SetExcludedFromPosFiles(True)
        return fp

    def pad(self, fp, number):
        pads = [p for p in fp.Pads() if p.GetNumber() == str(number)]
        assert pads, f"{fp.GetReference()} has no pad {number}"
        return pads

    def connect(self, fp, number, netname):
        for p in self.pad(fp, number):
            p.SetNet(self.net(netname))

    def pad_xy(self, fp, number):
        p = self.pad(fp, number)[0].GetPosition()
        return pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)

    def track(self, points, netname, layer=pcbnew.F_Cu, width=TRACK):
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            if (x0, y0) == (x1, y1):
                continue
            t = pcbnew.PCB_TRACK(self.b)
            t.SetStart(pt(x0, y0))
            t.SetEnd(pt(x1, y1))
            t.SetWidth(mm(width))
            t.SetLayer(layer)
            t.SetNet(self.net(netname))
            self.b.Add(t)

    def via(self, x, y, netname):
        v = pcbnew.PCB_VIA(self.b)
        v.SetPosition(pt(x, y))
        v.SetWidth(mm(VIA_D))
        v.SetDrill(mm(VIA_DRILL))
        v.SetNet(self.net(netname))
        self.b.Add(v)

    def polygon_zone(self, poly, layer, netname=None, rule=False, name=""):
        z = pcbnew.ZONE(self.b)
        z.SetLayer(layer)
        z.SetZoneName(name)
        o = z.Outline()
        o.NewOutline()
        for x, y in poly:
            o.Append(mm(x), mm(y))
        if rule:
            z.SetIsRuleArea(True)
            z.SetDoNotAllowZoneFills(True)
            z.SetDoNotAllowVias(True)
            z.SetDoNotAllowTracks(True)
            z.SetDoNotAllowPads(True)
            z.SetDoNotAllowFootprints(False)
        else:
            z.SetNet(self.net(netname))
            z.SetLocalClearance(mm(0.3))
            z.SetMinThickness(mm(0.25))
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
            z.SetThermalReliefGap(mm(0.4))
            z.SetThermalReliefSpokeWidth(mm(0.4))
        self.b.Add(z)
        return z

    def text(self, s, x, y, size=1.0, layer=pcbnew.F_SilkS, rot=0, align="center", width=None):
        t = pcbnew.PCB_TEXT(self.b)
        t.SetText(s)
        if align == "left":
            t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
        if layer == pcbnew.B_SilkS:
            t.SetMirrored(True)
        t.SetPosition(pt(x, y))
        t.SetLayer(layer)
        t.SetTextSize(pcbnew.VECTOR2I(mm(width or size), mm(size)))
        t.SetTextThickness(mm(size * 0.15))
        t.SetTextAngleDegrees(rot)
        self.b.Add(t)

    def line(self, x0, y0, x1, y1, layer=pcbnew.Edge_Cuts, width=0.1):
        s = pcbnew.PCB_SHAPE(self.b)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pt(x0, y0))
        s.SetEnd(pt(x1, y1))
        s.SetLayer(layer)
        s.SetWidth(mm(width))
        self.b.Add(s)

    def rect(self, x0, y0, x1, y1, layer, width=0.1):
        for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
            self.line(*a, *b, layer=layer, width=width)


def template_header_nets(board):
    """{(x, y) rounded: net name} for every pad of the template's Mega sockets."""
    out = {}
    for fp in board.tpl.GetFootprints():
        for p in fp.Pads():
            q = p.GetPosition()
            out[(round(pcbnew.ToMM(q.x), 2), round(pcbnew.ToMM(q.y), 2))] = (fp.GetReference(), p.GetNetname())
    return out


def header(board, ref, tpl_ref, nets_wanted, pins=8, at=None, strict=False):
    """Male 1xN header on the bottom side, over the template socket tpl_ref (at its
    origin, or at `at` for a few pins of a bigger socket). nets_wanted maps the Mega
    signal name (template net) to our net name. strict: every pin must land on one of
    the wanted Mega signals (used for the 2-pin 5V header)."""
    tpl = next(f for f in board.tpl.GetFootprints() if f.GetReference() == tpl_ref)
    p = tpl.GetPosition()
    x, y = at or (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))
    fields = {"LCSC": LCSC["header"]} if pins == 8 else {}
    fp = board.footprint("Connector_PinHeader_2.54mm", f"PinHeader_1x{pins:02d}_P2.54mm_Vertical", ref,
                         f"1x{pins:02d} male", x, y, tpl.GetOrientationDegrees(), back=True, fields=fields)
    # Soldered by hand: a part on the bottom would move the JLCPCB order to double-sided assembly.
    fp.SetExcludedFromPosFiles(True)
    tplpads = {(round(pcbnew.ToMM(q.GetPosition().x), 2), round(pcbnew.ToMM(q.GetPosition().y), 2)): q.GetNetname()
               for q in tpl.Pads()}

    def key(pad):
        q = pad.GetPosition()
        return round(pcbnew.ToMM(q.x), 2), round(pcbnew.ToMM(q.y), 2)

    def fits(pad):
        return key(pad) in tplpads and (not strict or tplpads[key(pad)] in nets_wanted)

    # Flipping to the bottom mirrors the pin row; turn it until every pin sits on a socket.
    for _ in range(4):
        if all(fits(pad) for pad in fp.Pads()):
            break
        fp.Rotate(fp.GetPosition(), pcbnew.EDA_ANGLE(90, pcbnew.DEGREES_T))
    board.mega[ref] = {}
    for pad in fp.Pads():
        assert fits(pad), f"{ref} pad {pad.GetNumber()} at {key(pad)} doesn't line up with the Mega"
        mega = tplpads[key(pad)]
        if mega in nets_wanted:
            pad.SetNet(board.net(nets_wanted[mega]))
        else:                               # KiCad's name for a pin marked unused in the schematic
            pad.SetNet(board.net(f"unconnected-({ref}-Pin_{pad.GetNumber()}-Pad{pad.GetNumber()})"))
        board.mega[ref][pad.GetNumber()] = mega_pin_name(mega)
    return fp


def mega_pin_name(net):
    """The template's net name for a Mega pin, as printed on the Mega ('/TX1{slash}18' -> 'TX1/18')."""
    if net.startswith("unconnected-") or not net:
        return "n.c."
    return net.lstrip("/").replace("{slash}", "/")


def library_footprint(board, name, pads, courtyard, silk, model, silk_back=True):
    """Footprint built from datasheet numbers, saved into the project library
    (body808.pretty) so that the board and the schematic both name it body808:<name>.
    pads: (number, dx, dy, size_x, size_y, drill_x, drill_y, kind) with kind 'pth' or 'npth'.
    The front face (y = 0) is the board edge."""
    fp = pcbnew.FOOTPRINT(board.b)
    fp.SetFPID(pcbnew.LIB_ID("body808", name))
    fp.SetReference("REF**")
    fp.SetValue(name)
    for number, dx, dy, sx, sy, drx, dry, kind in pads:
        p = pcbnew.PAD(fp)
        p.SetNumber(number)
        p.SetPosition(pt(dx, dy))
        oval = abs(sx - sy) > 1e-6
        p.SetShape(pcbnew.PAD_SHAPE_OVAL if oval else pcbnew.PAD_SHAPE_CIRCLE)
        p.SetSize(pcbnew.VECTOR2I(mm(sx), mm(sy)))
        p.SetDrillShape(pcbnew.PAD_DRILL_SHAPE_OBLONG if abs(drx - dry) > 1e-6 else pcbnew.PAD_DRILL_SHAPE_CIRCLE)
        p.SetDrillSize(pcbnew.VECTOR2I(mm(drx), mm(dry)))
        if kind == "npth":
            p.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
            p.SetLayerSet(pcbnew.PAD.UnplatedHoleMask())
            p.SetSize(pcbnew.VECTOR2I(mm(drx), mm(dry)))
        else:
            p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
            p.SetLayerSet(pcbnew.PAD.PTHMask())
        fp.Add(p)
    for layer, (x0, y0, x1, y1), width in ((pcbnew.F_CrtYd, courtyard, 0.05), (pcbnew.F_SilkS, silk, 0.12)):
        if (x0, y0, x1, y1) is None:
            continue
        sides = (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0)))
        if layer == pcbnew.F_SilkS:
            sides = sides[1:]          # the front side is the board edge
            if not silk_back:
                sides = (sides[0], sides[2])
        for a, b in sides:
            s = pcbnew.PCB_SHAPE(fp)
            s.SetShape(pcbnew.SHAPE_T_SEGMENT)
            s.SetStart(pt(*a))
            s.SetEnd(pt(*b))
            s.SetLayer(layer)
            s.SetWidth(mm(width))
            fp.Add(s)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    add_model(fp, model)
    os.makedirs(PROJECT_LIB, exist_ok=True)
    pcbnew.PCB_IO_KICAD_SEXPR().FootprintSave(PROJECT_LIB, fp)


def write_vrml(name, parts):
    """Box/cylinder model in KiCad's VRML units (0.1 inch). parts: (kind, centre_mm, size_mm, rgb)
    with x right, y towards the board edge, z up; box size (x, y, z), cylinder (diameter, length)
    along y. Returns the path KiCad should use."""
    os.makedirs(os.path.join(HERE, "3d"), exist_ok=True)
    out = ["#VRML V2.0 utf8"]
    for kind, (cx, cy, cz), size, rgb in parts:
        u = [v / 2.54 for v in (cx, cy, cz)]
        if kind == "box":
            geo = "Box { size %.4f %.4f %.4f }" % tuple(v / 2.54 for v in size)
        else:
            geo = "Cylinder { radius %.4f height %.4f }" % (size[0] / 2 / 2.54, size[1] / 2.54)
        out.append("Transform { translation %.4f %.4f %.4f children [ Shape { appearance Appearance "
                   "{ material Material { diffuseColor %.2f %.2f %.2f } } geometry %s } ] }"
                   % (*u, *rgb, geo))
    with open(os.path.join(HERE, "3d", name + ".wrl"), "w") as f:
        f.write("\n".join(out) + "\n")
    return "${KIPRJMOD}/3d/" + name + ".wrl"


BLACK, METAL, HOLE = (0.12, 0.12, 0.12), (0.72, 0.72, 0.75), (0.02, 0.02, 0.02)
JACK_3D = [("box", (0, -6.5, 4.1), (7.0, 13.0, 8.2), BLACK),          # body, front face on the edge
           ("cyl", (0, 2.0, 4.8), (6.0, 4.0), METAL),                 # bushing past the edge
           ("cyl", (0, 4.02, 4.8), (3.6, 0.1), HOLE)]
DIN_3D = [("box", (0, -0.9, 10.55), (20.0, 1.8, 21.1), BLACK),       # front plate
          ("box", (0, -8.8, 9.0), (18.0, 14.0, 18.0), BLACK),         # housing
          ("cyl", (0, 0.15, 10.0), (15.0, 0.3), METAL),               # socket ring
          ("cyl", (0, 0.33, 10.0), (13.0, 0.05), HOLE)]


def add_model(fp, path):
    m = pcbnew.FP_3DMODEL()
    m.m_Filename = path
    fp.Models().push_back(m)


def pj316_footprint(board):
    """PJ-316 mono jack with tip switch (Kinghelm KH-PJ-316-3P / CAX PJ-316).
    Body 7.0 wide x 13.0 deep, front face on the board edge, bushing beyond it.
    Slots 2.5 (across) x 1.0 (along the axis) at 1.5 / 7.0 / 11.5 behind the front,
    datasheet pins 1 / 2 / 3, named like KiCad's jack symbol: S = sleeve, T = tip,
    TN = tip switch (closed to the tip when nothing is plugged)."""
    pads = [(n, 0, d, 3.3, 1.8, 2.5, 1.0, "pth") for n, d in (("S", 1.5), ("T", 7.0), ("TN", 11.5))]
    library_footprint(board, "PJ-316", pads, courtyard=(-3.75, -0.25, 3.75, 13.25),
                      silk=(-3.5, 2.6, 3.5, 13.0), model=write_vrml("PJ-316", JACK_3D))


def jack_pj316(board, ref, x):
    return board.footprint("body808", "PJ-316", ref, "PJ-316", x, TOP,
                           fields={"LCSC": LCSC["jack"], "MPN": "KH-PJ-316-3P (or CAX PJ-316, C50176628)"})


def sds50j_footprint(board):
    """CUI SDS-50J right-angle 5-pin 180 deg DIN socket, front face on the board edge.
    Datasheet SDS-J rev 1.08, recommended PCB layout; origin pin 2, which sits 12.5 mm
    behind the front face. In the board frame the mating face points to -y."""
    p2y = 12.5
    pads = [
        ("1", -7.5, p2y, 2.2, 2.2, 1.3, 1.3, "pth"),
        ("2", 0.0, p2y, 2.2, 2.2, 1.3, 1.3, "pth"),
        ("3", 7.5, p2y, 2.2, 2.2, 1.3, 1.3, "pth"),
        ("4", -5.0, p2y + 2.5, 2.2, 2.2, 1.3, 1.3, "pth"),
        ("5", 5.0, p2y + 2.5, 2.2, 2.2, 1.3, 1.3, "pth"),
        ("E", -2.5, p2y - 10.0, 2.2, 2.2, 1.3, 1.3, "pth"),
        ("E", 2.5, p2y - 10.0, 2.2, 2.2, 1.3, 1.3, "pth"),
        ("", -7.5, p2y - 5.0, 2.4, 2.4, 2.4, 2.4, "npth"),
        ("", 7.5, p2y - 5.0, 2.4, 2.4, 2.4, 2.4, "npth"),
    ]
    library_footprint(board, "SDS-50J", pads, courtyard=(-10.25, -0.25, 10.25, 16.05),
                      silk=(-9.8, 1.0, 9.8, 13.0), model=write_vrml("SDS-50J", DIN_3D), silk_back=False)


def din_sds50j(board, ref, x):
    return board.footprint("body808", "SDS-50J", ref, "SDS-50J", x, TOP,
                           fields={"LCSC": LCSC["din"], "MPN": "CUI SDS-50J"})


def smd(board, kind, ref, value, x, y, netpads, rot=270, dnp=False):
    """1206 resistor/capacitor or SMA zener. rot 270: pad 1 on top; rot 0: pad 1 on the left."""
    lib, name = {"R": ("Resistor_SMD", "R_1206_3216Metric"),
                 "C": ("Capacitor_SMD", "C_1206_3216Metric"),
                 "D": ("Diode_SMD", "D_SMA")}[kind]
    lcsc = LCSC["zener"] if kind == "D" else LCSC[value]
    fp = board.footprint(lib, name, ref, value, x, y, rot, fields={"LCSC": lcsc}, dnp=dnp)
    for num, netname in netpads.items():
        board.connect(fp, num, netname)
    return fp


def in_keepout(x, y, margin=0.6):
    return any(x0 - margin < x < x1 + margin and y0 - margin < y < y1 + margin
               for x0, y0, x1, y1 in KEEPOUTS.values())


def gnd_symbol(board, x, y, layer=pcbnew.F_SilkS):
    """Ground sign on the silkscreen: a stub from (x, y) and three shrinking bars."""
    board.line(x, y, x, y + 0.45, layer, 0.15)
    for i, half in enumerate((0.6, 0.38, 0.16)):
        yy = y + 0.45 + 0.25 * i
        board.line(x - half, yy, x + half, yy, layer, 0.15)


def protection_lane(board, k, c, jack):
    """One input lane, drawn like its schematic.
    Signal line (left, x = c - 2.6): jack tip -> R2 10k -> R3 1k -> Mega pin, straight down.
    GND line (right, x = c + 2.6): drops straight from the GND line that runs across the
    top through all the jack sleeves, and picks up the jack's switch pin on the way.
    The tip carries the piezo's spikes (50-200 V for well under a millisecond), so both
    lines keep 0.8 mm from the jack pins of the other net.
    Parts that go to ground lie flat between the two: R1 1M and the zener D1 (cathode on
    the signal line). Returns (x, y) of the output pad."""
    n = k + 1
    inn, clamp, out = f"IN{n}", f"CLAMP{n}", f"A{k}"
    xs, xr = c - 2.6, c + 2.6
    y1, y2, y3, y4 = LANE_Y
    smd(board, "R", f"R{n}01", "1M", c, y1, {1: inn, 2: "GND"}, rot=0)
    smd(board, "R", f"R{n}02", "10k", xs, y2, {1: inn, 2: clamp})
    smd(board, "D", f"D{n}01", "5V1", c, y3, {1: clamp, 2: "GND"}, rot=0)
    smd(board, "R", f"R{n}03", "1k", xs, y4, {1: clamp, 2: out})
    tip, sleeve, switch = board.pad_xy(jack, "T"), board.pad_xy(jack, "S"), board.pad_xy(jack, "TN")
    # signal line
    board.track([tip, (xs, tip[1]), (xs, y2 - 1.46)], inn)
    board.track([(xs, y1), (c - 1.46, y1)], inn)
    board.track([(xs, y2 + 1.46), (xs, y4 - 1.46)], clamp)
    # GND track
    board.track([(xr, sleeve[1]), (xr, y3)], "GND")
    board.track([switch, (xr, switch[1])], "GND")
    board.track([(c + 1.46, y1), (xr, y1)], "GND")
    # labels
    board.text(f"JACK{n}", c, TOP + 14.2, 0.9, width=0.75)
    board.text(f"A{k}", c, TOP + 15.7, 0.9)
    board.text("GND", xr + 0.75, (y1 + y3) / 2, 0.8, rot=90, width=0.65)
    board.text("1M", c, y1 + 1.8, 0.8, width=0.65)
    board.text("10k", c + 0.3, y2, 0.8, width=0.65)
    board.text("ZENER", c, y3 + 2.6, 0.8, width=0.65)
    board.text("5V1", c, y3 + 3.8, 0.8, width=0.65)
    board.text("1k", c + 0.3, y4, 0.8, width=0.65)
    board.text(f"to A{k}", c + 0.6, y4 + 3.6, 0.8, width=0.65)
    return xs, y4 + 1.46


def gap_x(x, pads_x, pad_w=1.7, track=0.25, clearance=0.25):
    """Nearest x to `x` where a track can cross a header row without touching its pads."""
    def ok(c):
        return all(abs(c - p) >= pad_w / 2 + track / 2 + clearance for p in pads_x)
    if ok(x):
        return x
    gaps = [p + 1.27 for p in pads_x] + [p - 1.27 for p in pads_x]
    return min((g for g in gaps if ok(g)), key=lambda g: abs(g - x))


def main():
    board = Board()
    b = board.b
    pj316_footprint(board)
    sds50j_footprint(board)

    # Outline: Mega footprint plus the overhang, corners chamfered.
    c = 1.0
    outline = [(LEFT + c, TOP), (RIGHT - c, TOP), (RIGHT, TOP + c), (RIGHT, BOTTOM - c),
               (RIGHT - c, BOTTOM), (LEFT + c, BOTTOM), (LEFT, BOTTOM - c), (LEFT, TOP + c)]
    for a, z in zip(outline, outline[1:] + outline[:1]):
        board.line(*a, *z)
    board.line(LEFT, MEGA_TOP, RIGHT, MEGA_TOP, layer=pcbnew.Dwgs_User, width=0.1)
    board.text("Mega edge", LEFT + 6, MEGA_TOP + 1.0, 0.8, layer=pcbnew.Dwgs_User)

    # Headers into the Mega (bottom side): only where a signal is used.
    header(board, "J1", "J1", {"GND": "GND"})
    header(board, "J3", "J3", {f"/A{k}": f"A{k}" for k in range(8)})
    header(board, "J5", "J5", {"/A8": "A8"})
    j6 = header(board, "J6", "J6", {"/TX1{slash}18": "TX1"})
    j7 = header(board, "J7", "J7", {"+5V": "+5V"}, pins=2, at=(193.98, DIG_Y), strict=True)
    v5 = (193.98, DIG_Y)                       # J7 pin, +5V
    board.track([v5, board.pad_xy(j7, 2)], "+5V")   # both 5V pins (already joined on the Mega)
    tx = board.pad_xy(j6, 5)                   # TX1 (pin 18)

    # 8 lanes: jack on the edge, its protection parts straight below, output fanned into A0-A7.
    xs = [105.0 + PITCH * k for k in range(CHANNELS)]
    outs = []
    for k, x in enumerate(xs):
        n = k + 1
        jack = jack_pj316(board, f"J{20 + n}", x)
        board.connect(jack, "S", "GND")
        board.connect(jack, "TN", "GND")     # unplugged input is held at 0 V
        board.connect(jack, "T", f"IN{n}")
        outs.append(protection_lane(board, k, x, jack))
        for d, name in ((1.5, "GND"), (7.0, "TIP"), (11.5, "GND")):     # jack pins, seen from below
            board.text(name, x - 2.9, TOP + d, 0.8, layer=pcbnew.B_SilkS)
        board.text(f"JACK{n} A{k}", x, TOP + 14.5, 0.8, layer=pcbnew.B_SilkS)
    for k in range(CHANNELS + 1):                                     # white lines between lanes
        sx = xs[0] - PITCH / 2 + PITCH * k
        board.line(sx, TOP + 1.0, sx, LANE_Y[3] + 5.0, pcbnew.F_SilkS, 0.15)

    # Fan-in, all to the right: the further left a lane, the lower its track runs.
    for k, (ox, oy) in enumerate(outs):
        px = J3_X0 + 2.54 * k
        lane = 78.0 - 0.8 * k             # 0.5 mm between tracks
        board.track([(ox, oy), (ox, lane), (px, lane), (px, HDR_Y)], f"A{k}")

    # GND, all on the top face: from the Mega's GND pins (J1) down to the bottom edge, left
    # past the mounting hole, up the left edge, then straight across the top through every
    # jack sleeve to the MIDI socket.
    g6, g7 = (140.64, HDR_Y), (143.18, HDR_Y)
    gl = LEFT + 1.0
    ys = TOP + 1.5                              # sleeve row
    yb = BOTTOM - 1.0                           # along the bottom edge, 0.75 mm from it
    board.track([g7, g6, (g6[0], yb), (121.0, yb), (121.0, 93.5), (gl, 93.5), (gl, ys)],
                "GND", width=0.5)
    board.track([(gl, ys)] + [(x, ys) for x in xs] + [(DIN_X - 2.5, ys), (DIN_X - 2.5, TOP + 2.5)],
                "GND", width=0.6)

    # MIDI OUT in the top-right corner: pin 4 -> R1 220 -> 5V, pin 5 -> R2 220 -> TX1,
    # pin 2 + shield tabs -> GND. TX1 goes round the right side of the socket and enters
    # between its fixing holes and pins 1-3, so it never crosses 5V or GND.
    din = din_sds50j(board, "J10", DIN_X)
    for num, netname in (("2", "GND"), ("E", "GND"), ("4", "MIDI_SRC"), ("5", "MIDI_SINK"),
                         ("1", "unconnected-(J10-Pad1)"), ("3", "unconnected-(J10-Pad3)")):
        board.connect(din, num, netname)
    p4, p5, p2 = board.pad_xy(din, "4"), board.pad_xy(din, "5"), board.pad_xy(din, "2")
    e1, e2 = (DIN_X - 2.5, TOP + 2.5), (DIN_X + 2.5, TOP + 2.5)
    board.track([e1, e2], "GND", width=0.6)                          # shield tabs
    board.track([(DIN_X, e1[1]), p2], "GND")                         # pin 2
    # TX1 runs under the comms header (J6) to R2, which stands between J6 and the 5V pins,
    # then straight up to pin 5. 5V runs under J6 the other way, comes up on its left
    # and enters R1 from the left; R1 then goes straight to pin 4. Nothing crosses.
    r_snk = board.footprint("Resistor_SMD", "R_1206_3216Metric", "R2", "220", 190.0, 49.5, 90,
                            fields={"LCSC": LCSC["220"]})
    board.connect(r_snk, 1, "TX1"); board.connect(r_snk, 2, "MIDI_SINK")
    rk1, rk2 = board.pad_xy(r_snk, 1), board.pad_xy(r_snk, 2)
    board.track([tx, (tx[0], 52.0), (rk1[0], 52.0), rk1], "TX1")
    board.track([rk2, (p5[0], rk2[1] - 0.5), p5], "MIDI_SINK")
    r_src = board.footprint("Resistor_SMD", "R_1206_3216Metric", "R1", "220", 172.46, p4[1], 0,
                            fields={"LCSC": LCSC["220"]})
    board.connect(r_src, 1, "+5V"); board.connect(r_src, 2, "MIDI_SRC")
    rs1, rs2 = board.pad_xy(r_src, 1), board.pad_xy(r_src, 2)
    board.track([rs2, p4], "MIDI_SRC")
    board.track([v5, (v5[0], 53.0), (166.0, 53.0), (166.0, rs1[1]), rs1], "+5V")

    # Knob: flat JST-XH at the lower right, next to A8, opening toward the right edge.
    jst = board.footprint("Connector_JST", "JST_XH_S3B-XH-A_1x03_P2.50mm_Horizontal", "J11", "KNOB",
                          *KNOB_PIN1, 90, fields={"LCSC": LCSC["jst"]})
    board.connect(jst, 1, "A8"); board.connect(jst, 2, "+5V"); board.connect(jst, 3, "GND")
    k1, k2, k3 = (board.pad_xy(jst, i) for i in (1, 2, 3))
    v5b = board.pad_xy(j7, 2)                                         # second 5V pin
    board.track([v5b, (v5b[0], k2[1])], "+5V")
    a8 = (173.66, HDR_Y)
    board.track([a8, (a8[0], 94.0), (k1[0], 94.0), k1], "A8")
    # its GND comes from J1 along the bottom edge, under the A0-A7 pins
    xg = 172.0
    board.track([g7, (g7[0], yb), (xg, yb), (xg, k3[1]), k3], "GND", width=0.5)
    for name, (_, y) in (("A8", k1), ("5V", k2), ("GND", (0, k3[1] - 1.0))):
        board.text(name, k1[0] - 4.2, y, 0.8, width=0.65)
    board.text("KNOB", k1[0] - 5.4, k3[1] - 2.8, 0.9)

    # Test pads at the bottom right: 5V continues down from the knob's 5V line, GND
    # continues along the bottom edge from the knob's GND line.
    ytp = 96.3
    tp5 = board.footprint("TestPoint", "TestPoint_Pad_D1.5mm", "TP1", "5V", 196.9, ytp)
    tpg = board.footprint("TestPoint", "TestPoint_Pad_D1.5mm", "TP2", "GND", 194.2, ytp)
    board.connect(tp5, 1, "+5V"); board.connect(tpg, 1, "GND")
    board.track([k2, (v5b[0], k2[1]), (v5b[0], ytp), (196.9, ytp)], "+5V")
    board.track([(xg, yb), (192.9, yb), (192.9, ytp), (194.2, ytp)], "GND", width=0.5)
    board.text("5V", 196.9, 98.2, 0.8)
    board.text("GND", 194.2, 98.2, 0.8, width=0.65)

    # Labels next to the lines and pins (no legend block).
    board.text("GND", (g6[0] + g7[0]) / 2, 95.0, 0.8)                # J1
    for k in range(8):
        board.text(f"A{k}", J3_X0 + 2.54 * k, 95.6, 0.8)              # J3
    board.text("A8", 173.66, 99.0, 0.8)                                 # J5
    board.text("5V", 195.25, 54.0, 0.8)                                 # J7
    board.text("GND", 111.0, 92.6, 0.8)                                 # GND line, bottom left
    board.text("GND", xg - 1.0, 92.0, 0.8, rot=90, width=0.65)          # GND line to the knob
    board.text("5V", v5b[0] + 1.1, 70.0, 0.8, rot=90)                   # 5V line to the knob
    board.text("5V", 172.0, 54.0, 0.8)                                  # 5V line under J6
    board.text("TX1", 184.5, 51.05, 0.8, width=0.65)                    # TX1 line under J6
    board.text("A8", 180.0, 93.1, 0.8)                                  # A8 line to the knob
    board.text("220", rs1[0] + 1.46, rs1[1] - 1.5, 0.8, width=0.65)     # R1
    board.text("220", rk1[0] - 1.9, (rk1[1] + rk2[1]) / 2, 0.8, rot=90, width=0.65)   # R2
    board.text("4: 5V", p4[0], p4[1] + 1.9, 0.8, width=0.65)            # MIDI pins behind the socket
    board.text("5: TX1", p5[0] + 2.1, p5[1] + 1.9, 0.8, width=0.65)
    board.text("MIDI OUT", 170.5, 36.0, 0.9)
    board.text("body808 v1", 181.0, 67.0, 1.5)

    hole = board.footprint("MountingHole", "MountingHole_3.2mm_M3", "MH2", "M3", 113.97, 97.46)
    hole.SetBoardOnly(True)                 # mechanical only, not in the schematic

    # Bottom side: pin names next to the pads (mirrored, read from below).
    for name, dx, y in (("1 n.c.", 7.5, 40.2), ("2 GND", 0.0, 40.2), ("3 n.c.", -7.5, 40.2),
                        ("4 +5V", 5.0, 46.4), ("5 TX1", -5.0, 46.4), ("SHIELD GND", 0.0, TOP + 4.6)):
        board.text(name, DIN_X - dx, y, 0.8, layer=pcbnew.B_SilkS)
    board.text("MIDI OUT", DIN_X, TOP + 9.4, 1.0, layer=pcbnew.B_SilkS)
    for name, (x, y) in (("A8", k1), ("5V", k2), ("GND", k3)):
        board.text(name, x - 2.8, y, 0.8, layer=pcbnew.B_SilkS)
    board.text("KNOB", k1[0] - 2.8, k3[1] - 2.2, 0.8, layer=pcbnew.B_SilkS)
    board.text("body808 v1", 150.0, 65.0, 1.5, layer=pcbnew.B_SilkS)

    # No copper on the bottom at all; the keep-outs stay as a guard for later edits.
    inset = 0.4
    poly = [(LEFT + inset, TOP + inset), (RIGHT - inset, TOP + inset),
            (RIGHT - inset, BOTTOM - inset), (LEFT + inset, BOTTOM - inset)]
    for name, (x0, y0, x1, y1) in KEEPOUTS.items():
        board.polygon_zone([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], pcbnew.B_Cu, rule=True, name=name)
        board.rect(x0, y0, x1, y1, pcbnew.Cmts_User, 0.1)
        board.text(name, (x0 + x1) / 2, (y0 + y1) / 2, 0.8, layer=pcbnew.Cmts_User)

    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(OUT, b)
    print("saved", OUT)
    if "SHIELD_OUT" not in os.environ:
        write_bom(b, os.path.join(HERE, "fab", "bom-jlcpcb.csv"))
        schematic.write_symbol_library(os.path.join(HERE, "body808.kicad_sym"))
        schematic.write(os.path.join(HERE, "body808-shield.kicad_sch"), parts(b), board.mega)
        print("saved body808-shield.kicad_sch")


def parts(b):
    """Every part the schematic must show, with its pads' nets as the board has them."""
    out = []
    for fp in b.GetFootprints():
        if fp.IsBoardOnly():
            continue
        pads = {}
        for p in fp.Pads():
            if p.GetNumber():
                net = p.GetNetname()
                pads.setdefault(p.GetNumber(), "" if net.startswith("unconnected-") else net)
        fpid = fp.GetFPID()
        out.append({"ref": fp.GetReference(), "value": fp.GetValue(),
                    "footprint": f"{fpid.GetLibNickname().wx_str()}:{fpid.GetLibItemName().wx_str()}",
                    "fields": {k: fp.GetFieldText(k) for k in ("LCSC", "MPN") if fp.HasField(k)},
                    "in_bom": not fp.IsExcludedFromBOM(),
                    "in_pos_files": not fp.IsExcludedFromPosFiles(),
                    "pads": pads})
    return out


def write_bom(b, path):
    """JLCPCB assembly BOM: one line per (value, footprint, LCSC part). Left out: DNP parts and
    the ones soldered by hand (excluded from the placement file)."""
    import csv
    groups = {}
    for fp in b.GetFootprints():
        if fp.IsDNP() or fp.IsExcludedFromBOM() or fp.IsExcludedFromPosFiles() or not fp.HasField("LCSC"):
            continue
        key = (fp.GetValue(), fp.GetFPID().GetLibItemName().wx_str() or fp.GetValue(), fp.GetFieldText("LCSC"))
        groups.setdefault(key, []).append(fp.GetReference())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (value, footprint, lcsc), refs in sorted(groups.items()):
            w.writerow([value, ",".join(sorted(refs)), footprint, lcsc])
    print("saved", path)


if __name__ == "__main__":
    main()
