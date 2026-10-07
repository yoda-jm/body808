# Sampler (Hydrogen on Linux)

## Get the MIDI into the PC

| Path | Firmware mode | On the PC |
|------|---------------|-----------|
| USB cable (testing) | `MIDI_MODE_USB_SERIAL` | `tools/serial_midi_bridge.py /dev/ttyACM0` |
| Radio receiver with USB-MIDI | `MIDI_MODE_SERIAL` | Appears directly as a MIDI device (`aconnect -l`) |
| Radio receiver as a USB serial port | `MIDI_MODE_SERIAL` | `tools/serial_midi_bridge.py /dev/ttyUSB0 --baud <receiver baud>` |
| Radio receiver with DIN out | `MIDI_MODE_SERIAL` | Any USB-MIDI interface |

### Serial bridge

```sh
python3 -m venv ~/.venv/beat-corn
~/.venv/beat-corn/bin/pip install pyserial python-rtmidi
~/.venv/beat-corn/bin/python tools/serial_midi_bridge.py /dev/ttyACM0 -v
```

It creates an ALSA MIDI port named `beat-corn`. `-v` prints each message, useful
to check that hits arrive. The Arduino IDE serial monitor must be closed (only one
program can open the port).

## Hydrogen setup

1. **Preferences → Audio System**: JACK (or PipeWire's JACK) with a small buffer.
2. **Preferences → MIDI System**:
   - Driver: ALSA, Input: `beat-corn` (or your radio/USB-MIDI device)
   - Channel: All, or 10
   - Tick **Use output note as input note**. Hydrogen then picks each instrument
     by its MIDI note (36 = kick, 38 = snare…), instead of mapping note 36 to the
     first instrument, 37 to the second, and so on.
3. Load **GMRockKit** from the Sound Library to test with real drums first.

## Make the beatbox kit

Put your samples in one folder per sound:

```
samples/
  kick/     01_soft.wav  02_med.wav  03_hard.wav
  bass/     boom.wav
  snare/    pff_soft.wav  pff_hard.wav
  hihat/    ts.wav
  clap/     clap.wav
  openhat/  tsss.wav
```

Several files in a folder become **velocity layers**, sorted by name, softest first:
soft hits play `01_soft.wav`, hard hits play `03_hard.wav`. One file per sound is fine.

```sh
python3 tools/make_hydrogen_kit.py samples/
# -> ~/.hydrogen/data/drumkits/BeatCorn/drumkit.xml
```

Restart Hydrogen (or reload the Sound Library) and load **BeatCorn**. Open and closed
hi-hat are in the same mute group, so the closed hat cuts the open hat like a real hi-hat.

### Recording your own beatbox samples

- One sound per file, cut **tight at the start** (no silence before the attack, it's
  pure latency), with a short fade-out at the end.
- Record each sound soft, medium and hard for velocity layers.
- Normalize all files to a similar peak level, then balance in Hydrogen's mixer.
- 44.1 or 48 kHz, 16 or 24 bit, mono WAV.
- Audacity: *Edit → Labels → Add label at selection*, then *File → Export → Export
  Multiple* to split one long take into files.

## Latency

Total delay from the hit to the sound:

| Stage | Typical |
|-------|---------|
| Peak scan (`SCAN_US`) | 2.5 ms |
| MIDI on the cable / radio | 1 ms (cable) to 5–15 ms (radio) |
| Audio buffer | 2 × buffer / sample rate, 128 frames @ 48 kHz ≈ 5 ms |

Under ~15 ms feels instant. With PipeWire you can force a small buffer:

```sh
pw-metadata -n settings 0 clock.force-quantum 128
```

(`0` instead of `128` resets it.)
