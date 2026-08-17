# KiCad schematic

Keep `vix_pico_interface-cache.lib` in the **same directory** as the schematic. The schematic uses the cached custom symbols for the Pico 2, AM26LV31E, AM26LV32E, and the ViX X4 connector.

## Opening it

1. Keep both files together:
   - `vix_pico_interface.sch`
   - `vix_pico_interface-cache.lib`
2. Open `vix_pico_interface.sch` in KiCad Schematic Editor.
3. KiCad 8/9 may offer to convert it to the current `.kicad_sch` format. Save the converted copy if desired.

## What is represented

- GP2/GP3 -> AM26LV31E -> ViX X4 differential STEP/DIR.
- ViX X4 A/B/Z differential encoder outputs -> AM26LV32E -> GP4/GP5/GP6.
- X4 FAULT open-collector output -> GP10 with 10 kOhm pull-up to 3.3 V.
- GP11 -> 4.7 kOhm -> 2N3904 -> X4 ENERGISE input for `ES=0` operation.
- Pico GND is tied to X4 pin 3 control 0 V.
- GP7/GP8/GP9/GP12 are labelled for external limit, home, and E-stop auxiliary inputs.

This sheet is **only the low-voltage X4 interface**. The host computer communicates with the ViX separately through X3 RS-232.
