#!/bin/sh
# Rebuild the body808 shield, its schematic and its JLCPCB order files.
#   hardware/shield/make_fab.sh              regenerate board + schematic from build_shield.py, then export
#   hardware/shield/make_fab.sh --no-build   export the board as it is (after editing it in KiCad)
# Needs the KiCad Flatpak: flatpak install --user flathub org.kicad.KiCad
set -e
cd "$(dirname "$0")"
kicad_cli() { flatpak run --command=kicad-cli org.kicad.KiCad "$@"; }
PCB=body808-shield.kicad_pcb
SCH=body808-shield.kicad_sch

if [ "$1" != "--no-build" ]; then
  flatpak run --command=python3 org.kicad.KiCad build_shield.py
  kicad_cli sch upgrade --force "$SCH" >/dev/null      # written in KiCad 9's format, resaved as KiCad 10
fi
mkdir -p .work

# Checks: the schematic's rules (ERC), the board's rules (DRC), and that both describe
# the same circuit (schematic parity).
kicad_cli sch erc --severity-all --exit-code-violations -o .work/erc.rpt "$SCH" >/dev/null \
  || { echo "ERC found problems, see .work/erc.rpt" >&2; exit 1; }
kicad_cli pcb drc --schematic-parity --severity-error --exit-code-violations -o .work/drc.rpt "$PCB" >/dev/null \
  || { echo "DRC found errors, see .work/drc.rpt" >&2; exit 1; }

# fab/ holds only what gets uploaded to JLCPCB: the Gerber zip, the BOM (written by
# build_shield.py) and the placement file.
rm -rf .work/gerbers && mkdir -p .work/gerbers fab
kicad_cli pcb export gerbers -o .work/gerbers/ \
  --layers F.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts "$PCB" >/dev/null
kicad_cli pcb export drill -o .work/gerbers/ --format excellon --excellon-units mm \
  --excellon-separate-th --generate-map --map-format gerberx2 "$PCB" >/dev/null
rm -f fab/gerbers-jlcpcb.zip && (cd .work/gerbers && zip -q -X ../../fab/gerbers-jlcpcb.zip *)

# Placement file in JLCPCB's column names (coordinates match the Gerbers).
kicad_cli pcb export pos -o .work/pos.csv --format csv --units mm --side both --exclude-dnp "$PCB" >/dev/null
python3 - <<'PY'
import csv
rows = list(csv.DictReader(open(".work/pos.csv")))
with open("fab/cpl-jlcpcb.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    for r in rows:
        w.writerow([r["Ref"], r["PosX"] + "mm", r["PosY"] + "mm",
                    "Top" if r["Side"] == "top" else "Bottom", r["Rot"]])
PY

# Schematic as PDF (to print) and PNG (shown in the README; the SVG is 1 MB).
kicad_cli sch export pdf -o body808-shield-schematic.pdf "$SCH" >/dev/null
rm -rf .work/sch-svg && kicad_cli sch export svg -o .work/sch-svg/ "$SCH" >/dev/null
mkdir -p images && magick -density 200 -background white .work/sch-svg/body808-shield.svg -flatten \
  images/shield-schematic.png

kicad_cli pcb render --side top --width 1800 --height 1300 --quality high --background opaque \
  -o images/shield-top.png "$PCB" >/dev/null
kicad_cli pcb render --side bottom --width 1800 --height 1300 --quality high --background opaque \
  -o images/shield-bottom.png "$PCB" >/dev/null
kicad_cli pcb render --side top --rotate '-55,0,-15' --perspective --zoom 0.9 --width 1800 --height 1300 \
  --quality high --background opaque -o images/shield-3d.png "$PCB" >/dev/null
# Annotated top view (images/shield-explained.png): needs ImageMagick and the DejaVu font.
kicad_cli pcb export svg --layers F.Cu,F.SilkS,F.Mask,Edge.Cuts --mode-single --fit-page-to-board \
  --exclude-drawing-sheet -o .work/top.svg "$PCB" >/dev/null
magick -density 300 -background white .work/top.svg -flatten -resize 2400x .work/top.png
python3 annotate.py images/shield-explained.png .work/top.png
echo "done: fab/ (gerbers-jlcpcb.zip, bom-jlcpcb.csv, cpl-jlcpcb.csv), body808-shield-schematic.pdf, images/"
