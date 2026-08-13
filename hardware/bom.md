# Pico 2 / ViX AH interface BOM

This is the low-voltage interface between a **Raspberry Pi Pico 2** and the **X4 connector of a Parker ViX250AH or ViX500AH**. X1 motor/HV and X2 motor-feedback wiring are intentionally outside this BOM.

## Required interface parts

| Qty | Ref | Part | Purpose | Package / build note | DigiKey Canada |
|---:|---|---|---|---|---|
| 1 | U1 | Texas Instruments **AM26LV31EIDR** | 3.3 V differential line driver for STEP and DIR | 16-SOIC | https://www.digikey.ca/en/products/detail/texas-instruments/AM26LV31EIDR/1895997 |
| 1 | U2 | Texas Instruments **AM26LV32EIDR** | 3.3 V differential receiver for encoder A/B/Z | 16-SOIC | https://www.digikey.ca/en/products/detail/texas-instruments/AM26LV32EIDR/1896009 |
| 1 | Q1 | 2N3904 or equivalent small-signal NPN | Pulls X4 pin 11 low to energise when `ES=0` | TO-92 is easiest for breadboard | Any reputable 2N3904 |
| 1 | R1 | 4.7 kΩ | Pico GP11 to Q1 base | 1/4 W through-hole or SMD | — |
| 1 | R2 | 100 kΩ | Q1 base-to-emitter pull-down | 1/4 W through-hole or SMD | — |
| 1 | R3 | 10 kΩ | ViX X4 fault pull-up to 3.3 V | 1/4 W through-hole or SMD | — |
| 2 | C1, C2 | 100 nF ceramic | Local decoupling at U1/U2 | Place directly at VCC/GND | — |
| 0–5 | RTERM | 100–120 Ω | Optional differential termination at receiving end | DNP for short bench wiring unless needed | — |
| 1 | J1 | HD15 male connector/breakout | Mates with ViX X4 high-density 15-way socket | VGA-style 3-row HD15, **male** | — |
| 1 | — | Raspberry Pi Pico 2 | Pulse generation, encoder counting, safety supervisor | Pico 2 only | — |

The included TI datasheets are in [`../datasheets/`](../datasheets/).

## SOIC-to-DIP option for breadboard wiring

U1 and U2 are easy to use without designing a PCB. Buy two generic **SOIC-16 to DIP-16 adapter/breakout boards**, solder one IC onto each adapter, then either:

- plug the adapters directly into a solderless breadboard;
- solder wires directly to the breakout-board through-holes and heat-shrink the connections; or
- mount the breakout boards on perfboard if you want a more permanent prototype.

A separate perfboard is **not required**. For a compact prototype, the SOIC-to-DIP board itself can be the wiring point: solder the chip to it and solder the X4/Pico wires directly to its 0.1-inch pads.

## PCB implementation

For a PCB, place U1/U2 close to the X4 connector, keep each differential pair routed together, and place the 100 nF decoupling capacitors directly beside pins 16 and 8. Provide optional 120 Ω termination footprints so they can be populated only if signal-integrity testing requires them.

## Why these line-interface ICs

The ViX AH manual shows 26LS32-family differential receivers on the X4 inputs and 26LS31-family differential drivers on the X4 encoder outputs. AM26LV31E and AM26LV32E provide the corresponding RS-422-style functions while operating from a 3.3 V supply, making them convenient for Pico 2 GPIO.
