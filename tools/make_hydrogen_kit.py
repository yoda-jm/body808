#!/usr/bin/env python3
"""Build a Hydrogen drumkit from a folder of beatbox samples.

Layout of the samples folder (one sub-folder per pad, names as in PADS):

    samples/
      kick/      boots_soft.wav  boots_med.wav  boots_hard.wav
      snare/     pff.wav
      hihat/     ts_1.wav ts_2.wav
      ...

Files in a pad folder are sorted by name and used as velocity layers,
softest first, splitting the velocity range evenly. A single file is fine.

    python3 tools/make_hydrogen_kit.py samples/            # -> ~/.hydrogen/data/drumkits/Body808
    python3 tools/make_hydrogen_kit.py samples/ --name MyBox

In Hydrogen: Preferences > MIDI System > tick "Use output note as input note",
then load the kit from the Sound Library.
"""
import argparse
import shutil
import sys
from pathlib import Path
from xml.sax.saxutils import escape

# Must match the notes in body808.ino
PADS = [
    ("kick", 36),
    ("snare", 38),
    ("hihat", 42),
    ("bass", 35),
    ("clap", 39),
    ("openhat", 46),
]
AUDIO_EXT = {".wav", ".flac", ".aif", ".aiff"}


def instrument_xml(index, name, note, files):
    layers = []
    for i, f in enumerate(files):
        lo, hi = i / len(files), (i + 1) / len(files)
        layers.append(f"""    <layer>
     <filename>{escape(f)}</filename>
     <min>{lo:.6f}</min>
     <max>{hi:.6f}</max>
     <gain>1</gain>
     <pitch>0</pitch>
    </layer>""")
    # open and closed hihat choke each other like a real hihat
    mute_group = 1 if name in ("hihat", "openhat") else -1
    return f"""  <instrument>
   <id>{index}</id>
   <name>{escape(name)}</name>
   <volume>1</volume>
   <isMuted>false</isMuted>
   <isSoloed>false</isSoloed>
   <pan>0</pan>
   <pitchOffset>0</pitchOffset>
   <randomPitchFactor>0</randomPitchFactor>
   <gain>1</gain>
   <applyVelocity>true</applyVelocity>
   <filterActive>false</filterActive>
   <filterCutoff>1</filterCutoff>
   <filterResonance>0</filterResonance>
   <Attack>0</Attack>
   <Decay>0</Decay>
   <Sustain>1</Sustain>
   <Release>1000</Release>
   <muteGroup>{mute_group}</muteGroup>
   <midiOutChannel>-1</midiOutChannel>
   <midiOutNote>{note}</midiOutNote>
   <isStopNote>false</isStopNote>
   <sampleSelectionAlgo>VELOCITY</sampleSelectionAlgo>
   <isHihat>-1</isHihat>
   <lower_cc>0</lower_cc>
   <higher_cc>127</higher_cc>
   <FX1Level>0</FX1Level>
   <FX2Level>0</FX2Level>
   <FX3Level>0</FX3Level>
   <FX4Level>0</FX4Level>
   <instrumentComponent>
    <component_id>0</component_id>
    <gain>1</gain>
{chr(10).join(layers)}
   </instrumentComponent>
  </instrument>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("samples", type=Path)
    ap.add_argument("--name", default="Body808")
    ap.add_argument("--dest", type=Path, default=Path.home() / ".hydrogen/data/drumkits")
    args = ap.parse_args()

    kit_dir = args.dest / args.name
    kit_dir.mkdir(parents=True, exist_ok=True)

    instruments = []
    for name, note in PADS:
        pad_dir = args.samples / name
        files = sorted(p for p in pad_dir.glob("*") if p.suffix.lower() in AUDIO_EXT) if pad_dir.is_dir() else []
        if not files:
            print(f"skip {name}: no samples in {pad_dir}", file=sys.stderr)
            continue
        copied = []
        for f in files:
            target = f"{name}_{f.name}"
            shutil.copy2(f, kit_dir / target)
            copied.append(target)
        instruments.append(instrument_xml(len(instruments), name, note, copied))
        print(f"{name:8} note {note}: {len(copied)} layer(s)")

    if not instruments:
        sys.exit("no samples found, nothing written")

    (kit_dir / "drumkit.xml").write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<drumkit_info xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="http://www.hydrogen-music.org/drumkit">
 <name>{escape(args.name)}</name>
 <author>body808</author>
 <info>Beatbox kit for the body808 body percussion</info>
 <license>undefined license</license>
 <image></image>
 <imageLicense>undefined license</imageLicense>
 <componentList>
  <drumkitComponent>
   <id>0</id>
   <name>Main</name>
   <volume>1</volume>
  </drumkitComponent>
 </componentList>
 <instrumentList>
{chr(10).join(instruments)}
 </instrumentList>
</drumkit_info>
""")
    print(f"wrote {kit_dir / 'drumkit.xml'}")


if __name__ == "__main__":
    main()
