# Hardware

How to build the pads, the protection board, and wire them to the Arduino Mega
without damaging it.

![Wiring overview](wiring-overview.svg)

## Why the protection is mandatory

A piezo disc is a voltage generator. A soft tap gives a few hundred millivolts,
but a hand slap gives 10–20 V and a foot stomp can exceed 50–100 V for a fraction
of a millisecond, in both polarities.

The ATmega2560 datasheet limits any I/O pin to **−0.5 V … Vcc + 0.5 V** (−0.5 … 5.5 V).
Wiring a piezo straight to an analog pin works for a while, because the chip's
internal clamp diodes absorb the spikes. Each stomp stresses them, though, and
they eventually fail. The first symptom is usually one analog input reading wrong,
or the whole ADC drifting. A strong enough spike can also latch up the chip.

The protection below keeps every analog pin inside its limits, whatever the
piezo does.

## Protection circuit (one per pad)

![Protection circuit](protection-circuit.svg)

```
piezo red ──┬──[ R2 10k ]──┬──[ R3 1k ]──> A0..A5
            │              │
          R1 1M         D1 zener 5.1 V (BZX55C5V1), band → signal
            │              │
piezo black ┴──────────────┴─────────────> GND
```

| Part | Value | Role |
|------|-------|------|
| R1 | 1 MΩ | Across the piezo. Drains its charge so the signal returns to 0 V between hits, and sets how fast the pulse decays. Lower values (470 kΩ) give a shorter pulse and less sensitivity. |
| R2 | 10 kΩ | In series. Limits the current into the zener on a big spike (100 V / 10 kΩ = 10 mA, for well under a millisecond). |
| D1 | BZX55C5V1 zener, 5.1 V | Band (cathode) on the signal, anode on GND. Positive spikes: conducts at ~5.1 V. Negative spikes: conducts forward at ~−0.7 V. |
| R3 | 1 kΩ | Between the zener and the pin. The zener's −0.7 V is a bit past the pin's −0.5 V limit, so the chip's own protection diodes conduct a little: R3 keeps that current under ~0.5 mA, which they handle forever. It also covers the zener's tolerance (4.8–5.4 V) on the positive side. |

Notes:

- **Check the zener's value before soldering it.** In an assortment pack they all
  look the same: read the tiny print on the glass body (`5V1` / `C5V1`), or test it:
  9 V battery → 1 kΩ → zener (band towards +) → battery −, and measure about 5.1 V across
  the zener. A 12 V zener by mistake gives **no protection at all**.
- A **4.7 V zener** (`4V7`, likely in your pack) works too, with more safety margin, but it
  starts compressing loud hits earlier.
- A zener starts leaking softly from about 4 V, so very loud hits are slightly
  compressed near the top of the range. Calibration takes care of it: `maxLevel`
  will end up around 800–900 rather than 1023.
- No +5V wire is needed: everything is between the signal and GND.

### Alternative: two Schottky diodes

If you have BAT85 (or BAT43, 1N5817, BAT54S) Schottky diodes, they make a sharper
clamp: replace D1 and R3 with **D1 from the signal to +5V (band to +5V)** and **D2
from GND to the signal (band to the signal)**. Schottky diodes conduct at ~0.3 V,
before the chip's own diodes, so R3 isn't needed, but the board then needs a +5V
wire from the Mega's 5V pin. Regular silicon diodes (1N4148) are **not** a
substitute: they conduct at 0.6–0.7 V, like the zener, so they'd still need R3.

## Bill of materials

Per pad (×6):

| Qty | Part |
|-----|------|
| 1 | Piezo disc, 27 mm or 35 mm, with leads |
| 1 | 1 MΩ resistor, ¼ W |
| 1 | 10 kΩ resistor, ¼ W |
| 1 | 1 kΩ resistor, ¼ W |
| 1 | BZX55C5V1 zener diode (5.1 V, 0.5 W) |
| 1 | 3.5 mm mono jack socket (panel or PCB) and a mono plug |
| ~1.5 m | thin shielded cable (1 core + shield), or a twisted pair |
| 1 | stiff disc (coin, 3 mm plastic or plywood) and foam (EVA / neoprene) |

Shared:

| Qty | Part |
|-----|------|
| 1 | Arduino Mega 2560 |
| 1 | Perfboard or a Mega proto shield for the protection board |
| 1 | 5-pin DIN female socket + 2 × 220 Ω (MIDI OUT for the WIDI Master) |
| 1 | CME WIDI Master (Bluetooth MIDI radio, powered by the MIDI OUT) |
| 1 | Power when worn: 9 V battery with a barrel plug, or a USB power bank |
| | Velcro/elastic straps, a glove for the hand pads, an insole or ankle strap for the foot |

## Building the protection board

1. Run a **GND** rail along the board (black wire to a Mega GND pin).
2. For each channel solder R1, R2, D1 and R3 as in the schematic. Mind the **band**
   on the zener: it goes to the signal side (the R2/R3 junction), the other end to GND.
3. Wire each jack: tip to the R1/R2 junction, sleeve to GND.
4. Wire each channel output (the far end of R3) to A0 … A5.

### Check before plugging into the Mega

Do this with the board **not connected** to the Mega, using a multimeter:

1. **Diode mode, each channel**, probes on the zener's two ends (R2/R3 junction and GND):
   - red probe on *GND*, black on the junction → about 0.6–0.8 V (zener conducts forward)
   - red on the junction, black on *GND* → OL (a meter's diode test can't reach 5.1 V)
   If you read ~0 V either way, the zener is shorted or there's a solder bridge. If you
   read ~0.7 V the other way round, the zener is reversed.
2. **Resistance from tip to GND** (piezo unplugged): about 1 MΩ.
3. **Resistance from tip to the channel output**: about 11 kΩ (R2 + R3).
4. **No short between neighbouring channels**: resistance between two outputs is high.

Then connect the board, power the Mega from USB, start with `CALIBRATE 1` and
**tap softly first**.

## The pads

A bare piezo stuck on skin is a poor sensor: it clicks, picks up every movement
and the brass edge can cut. Make a sandwich instead:

```
   strap / glove / insole
   foam 3-5 mm            <- spreads the hit, protects against stomps
   stiff disc (coin)      <- collects the hit over the whole surface
   piezo disc, brass side glued to the disc (hot glue or epoxy)
   foam 2-3 mm            <- against the body, decouples from neighbour pads
```

- **Strain relief**: the piezo's leads break at the solder joint. Glue the cable
  to the disc with a blob of hot glue right after the solder points, and tape it
  again a few cm further.
- **Insulate** the solder points (hot glue or tape). Sweat on bare joints creates
  noise and corrosion.
- **Feet**: put the pad under the heel or the ball of the foot in an insole, with
  thick foam above and below. Stomps are by far the strongest signals: they need
  the protection the most. Give the input a foot pad is plugged into a higher
  `threshold`/`maxLevel` in the firmware (for example 80 / 900).
- **Hands**: in the palm of a fingerless glove, or on the back of the hand.
  The signal is weaker than the feet.
- **Chest / legs**: on a strap, over a bone or a firm spot (sternum, outer thigh).
  Soft areas absorb the hit.
- **Crosstalk**: a stomp also shakes the legs and the chest. The foam layers and
  the firmware crosstalk filter deal with it, but keep pads apart and well
  decoupled.

## Cables and connectors

- 3.5 mm mono jacks make the pads detachable and replaceable. Tip = piezo red,
  sleeve = piezo black = GND.
- Plugging a jack in briefly shorts tip and sleeve. That's harmless here thanks to R2.
- Use shielded cable, or at least twist the signal and GND wires together. Long
  untwisted wires on the body pick up hum and pick up crosstalk from each other.
- Bundle the 6 cables along the body to the Mega (in a belt bag or on the back).

## Power and electrical safety

- **When worn, run from a battery**: a 9 V battery on the barrel jack (or 7–12 V
  on VIN), or a USB power bank on the USB port. The Mega switches between USB and
  VIN automatically, so having both connected is fine.
- **Never** put a battery on the **5V pin**: it bypasses the regulator.
- While the Mega is on USB to a laptop, your body is electrically connected
  (through the piezos and GND) to the laptop. Prefer the laptop running on battery
  rather than on its charger, or use the radio link. The pads are insulated by
  the foam anyway, and the circuit only carries 5 V.
- Unused analog pins (A6–A15) can be left unconnected.

## Radio: MIDI out (DIN-5) + CME WIDI Master

The radio link is a **CME WIDI Master**, a Bluetooth (BLE) MIDI adapter that plugs
into a standard 5-pin DIN **MIDI OUT** socket. So the Mega only needs a normal MIDI
OUT socket; no radio code, no extra library.

In `MIDI_MODE_SERIAL` the Mega sends standard MIDI on **TX1 (pin 18)** at 31250 baud.
Wire a female DIN-5 socket like this (the standard 5 V MIDI OUT circuit):

| DIN pin | Connect to |
|---------|------------|
| 4 | 220 Ω → Mega 5V |
| 5 | 220 Ω → Mega TX1 (pin 18) |
| 2 | Mega GND (shield) |
| 1, 3 | not connected |

Pins 1–5 are not in order around the arc (it goes 3, 5, 2, 4, 1 from one end):
use the numbers molded on the socket, and check with a multimeter before plugging
anything in.

About the WIDI Master:

- **Plug only the main adapter** (the one with the button and LED) into this MIDI OUT
  socket. The sub adapter (MIDI IN) isn't needed: body808 only sends.
- **It is powered by the MIDI OUT socket itself** (CME: 3.3–5 V from the MIDI OUT),
  through pins 4 and 5. That's why the two 220 Ω resistors must be there and pin 4
  must go to 5 V: a "data-only" MIDI out with pin 4 unconnected won't power it.
  If the LED stays off, check pin 4 first.
- **LED**: blue slow flashing = waiting for a connection, blue steady = connected,
  blue fast flashing = MIDI going through. Each hit should flash it.
- **Pairing is automatic** with another WIDI device or a Bluetooth MIDI host. See
  [sampler.md](sampler.md#radio-cme-widi-master) for the PC side.
- Don't press its button during normal use: holding it 3 s forces "peripheral" mode,
  and on old firmware it can switch to a test mode. The WIDI app (iOS/Android) updates
  the firmware and can rename the unit.
- The WIDI Master sticks out of the DIN socket by a few centimetres. On the body, mount
  the socket so the adapter is protected (inside the belt bag, pointing up) and can't be
  knocked off by an arm swing.

If you later use another radio with a logic-level serial input (nRF24/HC-12 adapter,
XBee…), wire TX1 directly to its RX (check that it accepts 5 V logic) and GND to GND.
