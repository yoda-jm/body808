# Firmware

`body808.ino` reads the 6 piezos, detects hits and sends MIDI drum notes.

## Build and upload

Arduino IDE (or the VS Code Arduino extension, already configured in `.vscode/`):
board **Arduino Mega or Mega 2560**, processor **ATmega2560**. No library needed.

## Settings at the top of the sketch

### Output mode

```cpp
#define MIDI_MODE MIDI_MODE_DISPLAY
```

| Flag | Output | Use |
|------|--------|-----|
| `MIDI_MODE_DISPLAY` | Text on the USB serial monitor (115200) | Test the hits |
| `MIDI_MODE_SERIAL` | Real MIDI on TX1 / pin 18, 31250 baud | DIN socket, radio |
| `MIDI_MODE_USB_SERIAL` | Raw MIDI bytes on USB serial (115200) | Wired to the PC via `tools/serial_midi_bridge.py` |

Flags can be combined with `|`, for example `(MIDI_MODE_DISPLAY | MIDI_MODE_SERIAL)` to
watch hits while using the radio. `DISPLAY` and `USB_SERIAL` both use the USB port and
can't be combined. The sketch refuses to compile if you try.

### Calibration mode

```cpp
#define CALIBRATE 1
```

Streams the peak of each pad every 10 ms to **Tools → Serial Plotter** (115200),
one line per pad. No MIDI is sent in this mode.

### Sensitivity knob (optional)

```cpp
#define SENSITIVITY_KNOB 1
const uint8_t SENSITIVITY_PIN = A6;
```

A 10 kΩ potentiometer on A6 (wiring in [hardware.md](hardware.md#sensitivity-knob-optional))
scales the `threshold` and `maxLevel` of **all** pads together, to adapt live to a
softer or harder playing style, or a noisier stage, without reflashing:

| Knob | Effect | kick threshold / maxLevel (40 / 600 configured) |
|------|--------|------------------------------------------------|
| fully left | half as sensitive (× 2) | 80 / 1023 |
| middle | as calibrated | 40 / 600 |
| fully right | twice as sensitive (× 0.5) | 20 / 300 |

Calibrate with the knob in the middle. It's read every 20 ms; in `MIDI_MODE_DISPLAY`
the Serial Monitor shows `sensitivity: 141%` when it moves. Leave
`SENSITIVITY_KNOB 0` when no knob is wired: an unconnected pin reads random values.

The knob only changes **when a hit triggers** and how velocity is scaled. **How loud**
each sound plays is set in the sampler (Hydrogen mixer and instrument volumes).

### Pads

```cpp
Pad pads[] = {
  // name    pin note threshold maxLevel
  { "kick",  A0, 36,  40,       600 },
  { "snare", A1, 38,  40,       600 },
  ...
};
```

The firmware only knows sounds, not body places: input A0 always plays the kick,
whatever the pad plugged into it is strapped to. The thresholds belong to the
input, so if you move the foot pad to another input, recalibrate that input.

- **note**: General MIDI drum note. Same order and notes as `PADS` in `tools/make_hydrogen_kit.py`.
- **threshold**: raw ADC value (0–1023, 1023 = 5 V) under which nothing triggers.
- **maxLevel**: raw value that gives velocity 127. Harder hits are capped.

Remove lines to use fewer pads, or add lines with A6, A7… for more.

### Hit detection tuning

| Constant | Default | Increase if… | Decrease if… |
|----------|---------|--------------|--------------|
| `SCAN_US` | 2500 µs | velocity is random / too low (peak missed) | you feel latency |
| `MASK_US` | 30000 µs | one hit plays twice | fast rolls lose notes |
| `DECAY_US` | 80000 µs | ringing after loud hits retriggers | soft hit right after a loud one is lost |
| `RETRIGGER_RATIO` | 0.5 | same as DECAY_US | same as DECAY_US |
| `XTALK_RATIO` | 0.4 | hitting a pad also plays another one | two simultaneous hits drop the softer one |
| `XTALK_US` | 8000 µs | crosstalk still plays a bit late | — |
| `VELOCITY_CURVE` | 0.6 | soft hits are too loud | you must hit too hard to get loud notes |
| `NOTE_LEN_US` | 60000 µs | a sampler cuts samples on Note Off | — |

## Calibration procedure

1. `CALIBRATE 1`, upload, open the Serial Plotter.
2. Wear the pads and **move without hitting** (walk, wave the arms): note the highest
   value per pad. Set `threshold` 20–30 above it.
3. Hit each pad as hard as you'll play: set `maxLevel` a bit below the typical peak.
4. Hit one pad and watch the others: what they show is crosstalk. If it goes above
   their threshold, the `XTALK_RATIO` filter has to remove it. Better foam fixes it at
   the source.
5. `CALIBRATE 0`, `MIDI_MODE_DISPLAY`, upload, and check the Serial Monitor: one line
   per hit, with velocity following how hard you hit.

## How it works

Each loop reads all pads (about every 0.2 ms; the ADC clock is set 8× faster than the
Arduino default). Each pad is a small state machine:

```
IDLE --value > threshold--> SCANNING --after SCAN_US--> MASKED --after MASK_US--> IDLE
                            (track the peak)  |
                                              +--> crosstalk? drop : send Note On
```

- **Peak → velocity**: `(peak − threshold) / (maxLevel − threshold)`, raised to
  `VELOCITY_CURVE`, scaled to 1–127.
- **Retrigger protection**: after `MASK_US`, the threshold starts at
  `RETRIGGER_RATIO × last peak` and falls back to `threshold` over `DECAY_US`, so the
  piezo's ringing doesn't fire again.
- **Crosstalk**: a hit is dropped if another pad fired in the last `XTALK_US` with a peak
  more than `1 / XTALK_RATIO` times stronger.
- **ADC crosstalk**: each pin is read twice and the first value thrown away. The ADC
  shares one sampling capacitor between pins, and the high-impedance piezo can't
  recharge it fast enough after switching from another pin.
- **Note Off** is sent `NOTE_LEN_US` after Note On. The built-in LED is on while any
  note is on.

## MIDI messages

Channel 10 (`MIDI_CHANNEL = 9`, zero-based), 3-byte messages, no running status:

| Message | Bytes |
|---------|-------|
| Note On | `0x99 note velocity` |
| Note Off | `0x89 note 0` |
