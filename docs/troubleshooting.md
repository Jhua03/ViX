# Troubleshooting

## Host cannot open `/dev/ttyUSB0` or `/dev/ttyACM0`

Check enumeration:

```bash
ls -l /dev/ttyUSB* /dev/ttyACM*
```

If the device exists but access is denied, fix Linux serial-group/udev permissions. If it disappears/reappears under a different number, use the new path or create a persistent udev symlink.

## ViX does not answer X3 commands

Check these in order:

1. The adapter is **USB-to-RS232**, not USB-to-TTL UART.
2. The custom cable is not wired as a normal straight-through cable.
3. Adapter TX pin 3 reaches ViX X3 pin 4.
4. Adapter RX pin 2 reaches ViX X3 pin 5.
5. Adapter signal ground pin 5 reaches ViX X3 pin 3.
6. X3 pins 2, 8, and 9 have not been accidentally tied into the cable.
7. The port is 9600 8-N-1 with no flow control.
8. `--axis` matches the ViX software address.

Use a multimeter continuity test before assuming a software problem.

## Pico responds but STEP/DIR does not move the ViX

Check:

- U1 AM26LV31E has 3.3 V at VCC and ground at pin 8;
- both driver-enable pins are asserted as shown in the pin table;
- GP2/GP3 reach U1 inputs;
- U1 differential outputs reach the correct X4 STEP and DIR pins;
- ViX readback says `MP`, `EI=0`, and `ES=0`;
- GP11/NPN is actually pulling X4-11 low during the permitted enable window;
- ViX has also received serial `ON`.

The X4 hardware-enable and serial `ON` conditions are both part of the energisation path.

## Encoder position is missing or wrong direction

Check U2 power/enable and all three differential pairs. A/B polarity or channel swap can reverse/count incorrectly. The current included firmware expects `ENCSIGN=1`; do not change it simply to hide a wiring error. Verify physical direction deliberately.

An increasing `encoder_invalid` counter indicates invalid quadrature transitions and can point to wiring mistakes, noise, poor termination, a bad receiver, or excessive edge rate/speed.

## ViX fault reads active when healthy

The project expects the X4 fault output to be open-collector with a local 3.3 V pull-up. Healthy should read raw low and a fault should release the node high. Check the 10 kΩ pull-up, ground reference, and X4 pin 6 wiring.

## Limit/home is inverted

Do not change firmware polarity blindly. Measure the raw state inactive and active, then set the appropriate Pico polarity. Only set `CONFIRM_INPUTS 1` after the physical behavior has been verified.

## Stage moves on enable or pulls violently

Disable immediately. Possible causes include incorrect feedback setup, wrong encoder/motor direction, invalid motor configuration, unsuitable gains, or wiring problems. The generic X4 interface guide cannot supply a universal motor tuning; return to the Parker motor/feedback setup procedure for the attached motor.

## Small moves do not reach commanded distance

For the archived MX80L setup, digitally representable movement did not equal guaranteed mechanical movement. Stiction, breakaway force and servo deadband can dominate very small commands. Use [Tuning and performance](tuning-and-performance.md) and the archived threshold-refinement tests rather than assuming more current automatically fixes the problem.
