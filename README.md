# Body808

Wearable body percussion: piezo sensors on the feet, chest, legs and hands turn
body hits into MIDI drum notes, sent by radio to a sampler that plays beatbox
sounds.

```
piezo pads ──> protection board ──> Arduino Mega ──> MIDI OUT ──> WIDI Master ~~BLE~~> PC ──> Hydrogen (beatbox kit)
(on the body)   (keeps the Mega alive)  (hit detection)   (DIN-5)    (Bluetooth MIDI)        (or USB cable for testing)
```

Each input plays one fixed sound. Where a pad goes on the body is up to you: plug
it into the input of the sound you want it to play.

| Pin | Sound | MIDI note | Suggested placement |
|-----|-------|-----------|---------------------|
| A0 | kick | 36 | foot (heel stomp) |
| A1 | snare | 38 | leg / thigh |
| A2 | hihat | 42 | other leg |
| A3 | bass | 35 | chest |
| A4 | clap | 39 | hand |
| A5 | openhat | 46 | other hand |

Notes follow the General MIDI drum map, so any drum sampler works out of the box.

![Wiring overview](docs/wiring-overview.svg)

> **Never wire a piezo directly to an analog pin.** A stomp produces tens of volts;
> the pin tolerates −0.5 … 5.5 V. Each input needs the 4-part protection circuit
> described in [docs/hardware.md](docs/hardware.md).

## Documentation

- [docs/hardware.md](docs/hardware.md): protection circuit, parts list, building and
  testing the board, making the pads, power and safety, MIDI DIN out
- [docs/parts.md](docs/parts.md): shopping list with links (amazon.fr searches)
- [docs/firmware.md](docs/firmware.md): output modes, pad settings, calibration, tuning
- [docs/sampler.md](docs/sampler.md): getting MIDI into the PC, Hydrogen setup, making
  the beatbox kit, latency
- [docs/simulation.md](docs/simulation.md): simulated hits through 7 board
  configurations (schematics, waveforms, detection), pros and cons of each, and the
  firmware's retrigger tuning
- [sim/README.md](sim/README.md): the simulation's models, sources and how to run it

## Simulation

The protection board and the hit detector were simulated in ngspice before building
([docs/simulation.md](docs/simulation.md)): a piezo disc model with the real discs'
values, ~60 hits per board configuration from soft to 200 V, and the firmware's
detector replayed on every simulated pin voltage.

- **The pin is safe**: at most 131 µA into the Mega's own protection diodes on a 200 V
  hit (budget 0.5 mA), with the 1N4733A zener.
- **One note per hit**, in every hit shape and every configuration tried.
- **Velocity only works for small signals as built**: 0.2–3 V across the disc. If
  your pads give more (check with `CALIBRATE`), a 100 nF capacitor across the disc
  and R1 = 100 kΩ moves the window to 1–16 V.
- **Retrigger tuning**: `RETRIGGER_RATIO` 0.5 → 0.25 and `DECAY_US` 80 → 50 ms, so a
  soft hit right after a loud one is no longer lost, without ghost notes.

![Velocity vs hit strength, every configuration](docs/sim/transfer.svg)

```
python3 sim/run.py        # sweeps: stress, tolerances, ringing, transfer
python3 sim/report.py     # docs/simulation.md figures, per configuration
python3 sim/tuning.py     # firmware retrigger settings
```

## Quick start

1. Build the protection board and **check it with a multimeter before connecting it**
   ([hardware.md](docs/hardware.md#check-before-plugging-into-the-mega)).
2. Upload with `CALIBRATE 1`, set each pad's `threshold`/`maxLevel` from the Serial
   Plotter ([firmware.md](docs/firmware.md#calibration-procedure)).
3. Upload with `CALIBRATE 0` and `MIDI_MODE_DISPLAY`, check hits in the Serial Monitor.
4. Switch to `MIDI_MODE_USB_SERIAL`, run the bridge, play GMRockKit in Hydrogen
   ([sampler.md](docs/sampler.md)).
5. Record beatbox samples, build the kit with `tools/make_hydrogen_kit.py`.
6. Switch to `MIDI_MODE_SERIAL`, plug the WIDI Master into the MIDI OUT socket, pair it
   with the PC ([sampler.md](docs/sampler.md#radio-cme-widi-master)), run on battery.

## Files

```
body808.ino                    firmware (Arduino Mega 2560)
tools/serial_midi_bridge.py    USB/radio serial port -> ALSA MIDI port
tools/make_hydrogen_kit.py     samples/ folder -> Hydrogen drumkit
sim/                           ngspice models, sweeps, firmware replay and tuning
docs/                          documentation and schematics (SVG)
attic/                         the original Blink/MIDI test sketch
```
