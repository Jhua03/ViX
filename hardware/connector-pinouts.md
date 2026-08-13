# Connector and Pico pinouts

## Pico 2 pins used by the included firmware

The firmware uses GPIO numbers, not header pin numbers. For the standard non-wireless Raspberry Pi Pico 2 board:

| Function | GPIO | Pico physical header pin |
|---|---:|---:|
| STEP logic | GP2 | 4 |
| DIR logic | GP3 | 5 |
| Encoder A | GP4 | 6 |
| Encoder B | GP5 | 7 |
| Encoder Z | GP6 | 9 |
| Positive limit | GP7 | 10 |
| Negative limit | GP8 | 11 |
| Home | GP9 | 12 |
| ViX fault | GP10 | 14 |
| Drive enable command | GP11 | 15 |
| E-stop auxiliary | GP12 | 16 |
| 3.3 V output | 3V3(OUT) | 36 |
| Ground | GND | 3, 8, 13, 18, 23, 28, 33, or 38 |

## ViX X3 - RS-232

X3 is a 9-way D-sub **socket** on the drive.

| X3 pin | Function | Use here |
|---:|---|---|
| 1 | Reserved | No connection |
| 2 | Drive reset/mode input | **Do not connect** during normal operation |
| 3 | RS-232 GND | Special cable ground |
| 4 | RS-232 Rx | From USB-RS232 adapter TX |
| 5 | RS-232 Tx | To USB-RS232 adapter RX |
| 6 | Reserved | No connection |
| 7 | RS-232 Tx (D-loop) | No connection for a single drive |
| 8 | Do not connect | **No connection** |
| 9 | +5 V output | **No connection** |

See [`../docs/serial-x3.md`](../docs/serial-x3.md) for the special cable.

## ViX X4 - STEP/DIR, encoder copy, fault and energise

X4 is a high-density 15-way D-sub socket. Use a **male HD15** mating connector or screw-terminal breakout.

| X4 pin | With `EI=0` / `EO=2` | Pico interface |
|---:|---|---|
| 3 | Control 0 V | Pico/interface GND |
| 4 | /Z encoder output | U2 receiver Z- |
| 5 | Z encoder output | U2 receiver Z+ |
| 6 | Fault, NPN open collector | GP10 + 10 kΩ pull-up to 3.3 V |
| 7 | STEP- input | U1 STEP- |
| 8 | DIR- input | U1 DIR- |
| 9 | A- encoder output | U2 A- |
| 10 | B- encoder output | U2 B- |
| 11 | Energise input | Q1 collector; active-low when `ES=0` |
| 12 | STEP+ input | U1 STEP+ |
| 13 | DIR+ input | U1 DIR+ |
| 14 | A+ encoder output | U2 A+ |
| 15 | B+ encoder output | U2 B+ |

X4 pins 1 and 2 are analogue-input pins and are not used by this controller.

## U1 - AM26LV31E wiring

| U1 pin | Name | Connection |
|---:|---|---|
| 1 | 1A | Pico GP2 STEP |
| 2 | 1Y | X4 pin 12 STEP+ |
| 3 | 1Z | X4 pin 7 STEP- |
| 4 | G | 3.3 V (enable drivers) |
| 5 | 2Z | X4 pin 8 DIR- |
| 6 | 2Y | X4 pin 13 DIR+ |
| 7 | 2A | Pico GP3 DIR |
| 8 | GND | GND |
| 9 | 3A | GND (unused channel input) |
| 10, 11 | 3Y, 3Z | No connection |
| 12 | /G | GND (enable drivers) |
| 13, 14 | 4Z, 4Y | No connection |
| 15 | 4A | GND (unused channel input) |
| 16 | VCC | 3.3 V + 100 nF to GND |

## U2 - AM26LV32E wiring

| U2 pin | Name | Connection |
|---:|---|---|
| 1 | 1B | X4 pin 9 A- |
| 2 | 1A | X4 pin 14 A+ |
| 3 | 1Y | Pico GP4 encoder A |
| 4 | G | 3.3 V (enable receivers) |
| 5 | 2Y | Pico GP5 encoder B |
| 6 | 2A | X4 pin 15 B+ |
| 7 | 2B | X4 pin 10 B- |
| 8 | GND | GND |
| 9 | 3B | X4 pin 4 Z- |
| 10 | 3A | X4 pin 5 Z+ |
| 11 | 3Y | Pico GP6 encoder Z |
| 12 | /G | GND (enable receivers) |
| 13 | 4Y | No connection |
| 14, 15 | 4A, 4B | No connection |
| 16 | VCC | 3.3 V + 100 nF to GND |
