#!/usr/bin/env python3
"""Turn raw MIDI bytes from a serial port into an ALSA/JACK MIDI port.

Use it when the MIDI stream reaches the PC as a serial port: the Mega's USB
in MIDI_MODE_USB_SERIAL (115200), or a radio receiver that shows up as
/dev/ttyUSB* (often 31250 or 115200, check its docs).

    python3 -m venv ~/.venv/beat-corn
    ~/.venv/beat-corn/bin/pip install pyserial python-rtmidi
    ~/.venv/beat-corn/bin/python tools/serial_midi_bridge.py /dev/ttyACM0

Then connect "beat-corn" to Hydrogen (aconnect -l, or qjackctl's MIDI/ALSA tab).
"""
import argparse
import sys

import rtmidi
import serial


def message_length(status):
    if status >= 0xF0:
        return {0xF1: 2, 0xF2: 3, 0xF3: 2}.get(status, 1)
    return 2 if (status & 0xF0) in (0xC0, 0xD0) else 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("port", help="serial device, e.g. /dev/ttyACM0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--name", default="beat-corn")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    out = rtmidi.MidiOut(rtmidi.API_LINUX_ALSA)
    out.open_virtual_port(args.name)
    ser = serial.Serial(args.port, args.baud)
    print(f"{args.port} @ {args.baud} -> MIDI port '{args.name}' (Ctrl+C to stop)")

    msg, want = [], 0
    try:
        while True:
            for b in ser.read(ser.in_waiting or 1):
                if b & 0x80:  # status byte starts a new message
                    msg, want = [b], message_length(b)
                elif msg:
                    msg.append(b)
                else:
                    continue  # data byte without a status (e.g. boot text), ignore
                if len(msg) == want:
                    out.send_message(msg)
                    if args.verbose:
                        print(" ".join(f"{x:02X}" for x in msg))
                    msg = msg[:1]  # keep status for running status
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
        out.close_port()


if __name__ == "__main__":
    sys.exit(main())
