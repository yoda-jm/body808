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

The protection below keeps every analog pin between −0.3 V and 5.3 V, whatever
the piezo does.

## Protection circuit (one per pad)

![Protection circuit](protection-circuit.svg)

| Part | Value | Role |
|------|-------|------|
| R1 | 1 MΩ | Across the piezo. Drains its charge so the signal returns to 0 V between hits, and sets how fast the pulse decays. Lower values (470 kΩ) give a shorter pulse and less sensitivity. |
| R2 | 10 kΩ | In series. Limits the current that flows into the diodes on a big spike (100 V / 10 kΩ = 10 mA, for well under a millisecond). |
| D1 | BAT85 Schottky | Anode on the signal, band (cathode) on +5V. Clamps positive spikes to about 5.3 V. |
| D2 | BAT85 Schottky | Band (cathode) on the signal, anode on GND. Clamps negative spikes to about −0.3 V. |

Notes:

- **Schottky, not regular diodes.** A 1N4148 only conducts at about 0.6–0.7 V,
  which is past the −0.5 V limit, so the chip's internal diodes would conduct
  first. BAT85, BAT43, 1N5817 or the dual BAT54S (SMD) all work.
- The +5V for D1 comes from the Mega's **5V pin**. All six D1s share it.
- The diodes leak a little current, which adds a small offset to the readings at
  rest (a few ADC counts). Calibration takes care of it, see [firmware.md](firmware.md).
- An alternative you'll often see online is a 5.1 V zener in place of D1+D2.
  It also works with R2, but it starts conducting softly from about 4 V and
  compresses loud hits. The Schottky clamp is sharper.

## Bill of materials

Per pad (×6):

| Qty | Part |
|-----|------|
| 1 | Piezo disc, 27 mm or 35 mm, with leads |
| 1 | 1 MΩ resistor, ¼ W |
| 1 | 10 kΩ resistor, ¼ W |
| 2 | BAT85 Schottky diode (DO-35) |
| 1 | 3.5 mm mono jack socket (panel or PCB) and a mono plug |
| ~1.5 m | thin shielded cable (1 core + shield), or a twisted pair |
| 1 | stiff disc (coin, 3 mm plastic or plywood) and foam (EVA / neoprene) |

Shared:

| Qty | Part |
|-----|------|
| 1 | Arduino Mega 2560 |
| 1 | Perfboard or a Mega proto shield for the protection board |
| 1 | 5-pin DIN female socket + 2 × 220 Ω (MIDI out, if your radio takes DIN) |
| 1 | Power when worn: 9 V battery with a barrel plug, or a USB power bank |
| | Velcro/elastic straps, a glove for the hand pads, an insole or ankle strap for the foot |

## Building the protection board

1. Draw two rails along the board: **+5V** (red wire to the Mega 5V pin) and
   **GND** (black wire to a Mega GND pin).
2. For each channel solder R1, R2, D1 and D2 as in the schematic. Mind the
   **band** on the diodes: D1's band goes to +5V, D2's band goes to the signal.
3. Wire each jack: tip to the R1/R2 junction, sleeve to GND.
4. Wire each channel output (the R2/D1/D2 junction) to A0 … A5.

### Check before plugging into the Mega

Do this with the board **not connected** to the Mega, using a multimeter:

1. **Rails not shorted**: resistance between +5V and GND should be high (it reads
   through the diodes and resistors, but never near 0 Ω).
2. **Diode mode, each channel** (probe on the R2/D1/D2 junction, "out"):
   - red probe on *out*, black on *+5V* → about 0.2–0.4 V (D1 conducts)
   - red on *+5V*, black on *out* → OL (open)
   - red on *GND*, black on *out* → about 0.2–0.4 V (D2 conducts)
   - red on *out*, black on *GND* → OL
   If a channel reads ~0.3 V in both directions or 0 V, a diode is reversed or shorted.
3. **Resistance from tip to GND** (piezo unplugged): about 1 MΩ.

Then connect the board, power the Mega from USB, and measure 5 V between the +5V
and GND rails. Start with `CALIBRATE 1` and **tap softly first**.

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

## MIDI out (DIN-5) for the radio

In `MIDI_MODE_SERIAL` the Mega sends standard MIDI on **TX1 (pin 18)** at 31250 baud.
For a DIN socket (seen from the back of a female socket, pins 1–5 are numbered
1, 4, 2, 5, 3 left to right along the arc; check your socket's markings):

| DIN pin | Connect to |
|---------|------------|
| 4 | 220 Ω → Mega 5V |
| 5 | 220 Ω → Mega TX1 (pin 18) |
| 2 | Mega GND (shield) |
| 1, 3 | not connected |

If the radio transmitter has a DIN plug, it plugs straight into this socket. If it
takes a logic-level serial input instead (nRF24/HC-12 adapter, XBee…), wire TX1
directly to its RX (check that it accepts 5 V logic) and GND to GND.
