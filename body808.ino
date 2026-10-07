/*
  body808 — body percussion with piezo sensors -> MIDI

  Board: Arduino Mega 2560
  Up to 6 piezo discs on A0..A5. Each hit becomes a MIDI Note On whose
  velocity follows how hard you hit, on MIDI channel 10 (drums).

  Wiring per piezo (repeat for each analog pin). The protection is NOT
  optional: a hard hit gives tens of volts, the pin survives -0.5..5.5 V.
  See docs/hardware.md and docs/protection-circuit.svg.

      piezo red ---+----[ R2 10k ]----+-----------> A0..A5
                   |                  |
                R1 1M     D1 BAT85: anode on this node, band (cathode) to +5V
                   |      D2 BAT85: band (cathode) on this node, anode to GND
                   |                  |
      piezo black -+------------------+-----------> GND

  Output (pick with MIDI_MODE below):
    MIDI_MODE_DISPLAY     human-readable hits on the USB serial monitor (115200)
    MIDI_MODE_SERIAL      real MIDI bytes on Serial1 / TX1 (pin 18) at 31250 baud,
                          for a 5-pin DIN socket or a wireless MIDI transmitter
    MIDI_MODE_USB_SERIAL  raw MIDI bytes on the USB serial port (115200), for
                          tools/serial_midi_bridge.py on the PC
  DISPLAY and USB_SERIAL both use the USB port, so don't enable both.

  Set CALIBRATE to 1 to stream the raw sensor values to the Arduino
  Serial Plotter, then tune threshold / maxLevel for each pad.
*/

#define MIDI_MODE_DISPLAY (1 << 0)
#define MIDI_MODE_SERIAL (1 << 1)
#define MIDI_MODE_USB_SERIAL (1 << 2)

//#define MIDI_MODE (MIDI_MODE_DISPLAY | MIDI_MODE_SERIAL)
#define MIDI_MODE MIDI_MODE_DISPLAY

#define CALIBRATE 0

#if (MIDI_MODE & MIDI_MODE_DISPLAY) && (MIDI_MODE & MIDI_MODE_USB_SERIAL)
#error "MIDI_MODE_DISPLAY and MIDI_MODE_USB_SERIAL both use the USB serial port"
#endif

const uint8_t MIDI_CHANNEL = 9;  // 0-based: 9 = MIDI channel 10, the drum channel

// Timing of the hit detector (all in microseconds)
const unsigned long SCAN_US = 2500;       // after crossing threshold, look this long for the peak
const unsigned long MASK_US = 30000;      // ignore the pad this long after a hit (ringing)
const unsigned long DECAY_US = 80000;     // then the retrigger threshold decays over this long
const unsigned long NOTE_LEN_US = 60000;  // Note Off this long after Note On
const unsigned long XTALK_US = 8000;      // crosstalk window between pads

const float RETRIGGER_RATIO = 0.5;  // right after a hit, need this fraction of its peak to retrigger
const float XTALK_RATIO = 0.4;      // drop a hit weaker than this fraction of a near-simultaneous hit on another pad
const float VELOCITY_CURVE = 0.6;   // <1 = soft hits louder, 1 = linear, >1 = need to hit harder

enum class MidiCommand {
  NOTE_OFF = 0x80,
  NOTE_ON = 0x90,
  POLY_PRESSURE = 0xA0,
  CONTROL_CHANGE = 0xB0,
  PROGRAM_CHANGE = 0xC0,
  CHANNEL_PRESSURE = 0xD0,
  PITCH_BEND = 0xE0
};

enum class PadState { IDLE, SCANNING, MASKED };

struct Pad {
  // configuration
  const char *name;
  uint8_t pin;
  uint8_t note;       // General MIDI drum map
  int threshold;      // raw ADC value (0..1023) below which nothing happens
  int maxLevel;       // raw ADC value that gives velocity 127
  // runtime
  PadState state;
  int peak;
  unsigned long scanStart;
  unsigned long lastHit;
  int lastPeak;
  bool noteIsOn;
};

// One pad per sound, in a fixed order. Where each pad sits on the body is up to
// you: plug it into the input of the sound you want, then calibrate. Notes follow
// the GM drum map, so any drum kit or sampler works before you load beatbox samples.
// Same order and notes as PADS in tools/make_hydrogen_kit.py.
Pad pads[] = {
  { "kick", A0, 36, 40, 600 },
  { "snare", A1, 38, 40, 600 },
  { "hihat", A2, 42, 40, 600 },
  { "bass", A3, 35, 40, 600 },
  { "clap", A4, 39, 40, 600 },
  { "openhat", A5, 46, 40, 600 },
};
const uint8_t PAD_COUNT = sizeof(pads) / sizeof(pads[0]);

void midiSend(uint8_t status, uint8_t data1, uint8_t data2) {
  if (MIDI_MODE & MIDI_MODE_SERIAL) {
    Serial1.write(status);
    Serial1.write(data1);
    Serial1.write(data2);
  }
  if (MIDI_MODE & MIDI_MODE_USB_SERIAL) {
    Serial.write(status);
    Serial.write(data1);
    Serial.write(data2);
  }
}

void writeMidiNote(MidiCommand command, const Pad &pad, uint8_t velocity) {
  midiSend((uint8_t)command | MIDI_CHANNEL, pad.note, velocity);

  if (MIDI_MODE & MIDI_MODE_DISPLAY) {
    if (command == MidiCommand::NOTE_ON) {
      Serial.print(F("Note On : "));
      Serial.print(pad.name);
      Serial.print(F(" note="));
      Serial.print(pad.note);
      Serial.print(F(" vel="));
      Serial.print(velocity);
      Serial.print(F(" peak="));
      Serial.println(pad.peak);
    }
  }
}

uint8_t peakToVelocity(const Pad &pad, int peak) {
  float x = float(peak - pad.threshold) / float(pad.maxLevel - pad.threshold);
  x = constrain(x, 0.0, 1.0);
  return 1 + (uint8_t)(pow(x, VELOCITY_CURVE) * 126.0 + 0.5);
}

// Piezos are a high impedance source, so the ADC sample-and-hold still holds
// the previous channel's voltage after switching the multiplexer. Throwing
// away the first conversion removes most of the electrical crosstalk.
int readPiezo(uint8_t pin) {
  analogRead(pin);
  return analogRead(pin);
}

// The threshold is raised right after a hit so the pad's own ringing
// doesn't retrigger it, then decays back to the configured value.
int currentThreshold(const Pad &pad, unsigned long now) {
  unsigned long since = now - pad.lastHit;
  if (pad.lastPeak == 0 || since >= MASK_US + DECAY_US) return pad.threshold;
  float left = 1.0 - float(since - MASK_US) / float(DECAY_US);
  int dynamic = (int)(pad.lastPeak * RETRIGGER_RATIO * left);
  return max(pad.threshold, dynamic);
}

// A hit on one pad shakes the body and shows up, weaker, on the others.
// Drop this hit if another pad fired a much stronger hit just now.
bool isCrosstalk(uint8_t index, unsigned long now) {
  for (uint8_t i = 0; i < PAD_COUNT; i++) {
    if (i == index || pads[i].lastPeak == 0) continue;
    if (now - pads[i].lastHit < XTALK_US && pads[index].peak < pads[i].lastPeak * XTALK_RATIO) {
      return true;
    }
  }
  return false;
}

void updatePad(uint8_t index, int value, unsigned long now) {
  Pad &pad = pads[index];

  if (pad.noteIsOn && now - pad.lastHit >= NOTE_LEN_US) {
    writeMidiNote(MidiCommand::NOTE_OFF, pad, 0);
    pad.noteIsOn = false;
  }

  switch (pad.state) {
    case PadState::IDLE:
      if (value > currentThreshold(pad, now)) {
        pad.state = PadState::SCANNING;
        pad.scanStart = now;
        pad.peak = value;
      }
      break;

    case PadState::SCANNING:
      if (value > pad.peak) pad.peak = value;
      if (now - pad.scanStart >= SCAN_US) {
        if (isCrosstalk(index, now)) {
          pad.state = PadState::IDLE;
          break;
        }
        if (pad.noteIsOn) writeMidiNote(MidiCommand::NOTE_OFF, pad, 0);
        writeMidiNote(MidiCommand::NOTE_ON, pad, peakToVelocity(pad, pad.peak));
        pad.noteIsOn = true;
        pad.lastHit = now;
        pad.lastPeak = pad.peak;
        pad.state = PadState::MASKED;
      }
      break;

    case PadState::MASKED:
      if (now - pad.lastHit >= MASK_US) pad.state = PadState::IDLE;
      break;
  }
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);

  // ADC clock prescaler 16 instead of 128: ~16 us per conversion instead of
  // ~110 us, so all 6 pads are sampled every ~0.2 ms. Accuracy stays fine.
  ADCSRA = (ADCSRA & ~0x07) | 0x04;

  if (MIDI_MODE & MIDI_MODE_SERIAL) Serial1.begin(31250);
  if (CALIBRATE || (MIDI_MODE & (MIDI_MODE_DISPLAY | MIDI_MODE_USB_SERIAL))) Serial.begin(115200);

  for (uint8_t i = 0; i < PAD_COUNT; i++) {
    pads[i].state = PadState::IDLE;
    pads[i].lastPeak = 0;
    pads[i].noteIsOn = false;
  }

  if (MIDI_MODE & MIDI_MODE_DISPLAY) {
    Serial.print(F("body808 ready, pads: "));
    Serial.println(PAD_COUNT);
  }
}

#if CALIBRATE
// Serial Plotter: one line per scan, peak of each pad over ~10 ms
void loop() {
  static int peaks[PAD_COUNT];
  static unsigned long last = 0;
  for (uint8_t i = 0; i < PAD_COUNT; i++) {
    peaks[i] = max(peaks[i], readPiezo(pads[i].pin));
  }
  if (millis() - last >= 10) {
    last = millis();
    for (uint8_t i = 0; i < PAD_COUNT; i++) {
      Serial.print(peaks[i]);
      Serial.print(i + 1 < PAD_COUNT ? ' ' : '\n');
      peaks[i] = 0;
    }
  }
}
#else
void loop() {
  bool anyActive = false;
  for (uint8_t i = 0; i < PAD_COUNT; i++) {
    int value = readPiezo(pads[i].pin);
    updatePad(i, value, micros());
    anyActive |= pads[i].noteIsOn;
  }
  digitalWrite(LED_BUILTIN, anyActive ? HIGH : LOW);
}
#endif
