# Wiring and runtime input policy

## Pico pins

```text
GP2   STEP logic -> AM26LV31 -> ViX X4 STEP+/-
GP3   DIR logic  -> AM26LV31 -> ViX X4 DIR+/-
GP4   encoder A  <- AM26LV32 <- ViX X4 A+/-
GP5   encoder B  <- AM26LV32 <- ViX X4 B+/-
GP6   encoder Z  <- AM26LV32 <- ViX X4 Z+/-
GP7   Limit+
GP8   Limit- input, physically unavailable/non-working
GP9   Home
GP10  ViX X4 fault
GP11  drive-enable transistor controlling ViX X4 pin 11
GP12  NC E-stop auxiliary contact
```

## Confirmed stage sensor truth table

```text
Limit+ inactive: raw 0
Limit+ active:   raw 1

Limit-:          not working; HAS_LN=0

Home inactive:   raw 0
Home active:     raw 1
```

Runtime Pico configuration:

```text
CONFIG LPOL 1
CONFIG LNPOL 0
CONFIG HPOL 1
CONFIG HAS_LN 0
CONFIG FPOL 1
CONFIG ENCSIGN 1
CONFIG SOFTMIN -50000
CONFIG SOFTMAX 50000
CONFIG WATCHDOG_MS 750
CONFIG CONFIRM_INPUTS 1
```

The ViX X4 fault output is normally low when healthy and rises through the Pico
pull-up when the open-collector output releases on a fault. Therefore:

```text
healthy raw_fault = 0
fault   raw_fault = 1
```

With the recommended NC E-stop auxiliary loop:

```text
safe/open? No: closed contact pulls GP12 low -> raw 0 -> safe
pressed/broken wire: pull-up gives raw 1 -> unsafe
```

## Missing negative limit policy

The commissioning runner does not search for a negative limit and does not home
automatically. It establishes a temporary local zero near mid-travel and limits
command position to +/-50000 counts, equal to +/-0.5 mm.

## X4 energise handshake

With `ES=0`, ViX X4 pin 11 is active-low. GP11 drives an NPN sink:

```text
GP11 low  -> NPN off -> X4-11 released/high -> hardware disabled
GP11 high -> NPN on  -> X4-11 pulled low    -> hardware enabled
```

The ViX still requires the serial `ON` command. The host verifies actual motor
energisation using `R(ST2)` and ST2.1 before accepting any powered result.
