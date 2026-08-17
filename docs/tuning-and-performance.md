# MX80L 10 nm example: tuning and measured performance

This page is deliberately separate from the general ViX250AH/ViX500AH guide. **Do not treat these values as universal ViX AH settings.** They describe the archived MX80L commissioning configuration.

## Encoder/stage scale

```text
100,000 counts = 1 mm
100 counts     = 1 µm
1 count        = 10 nm
```

Therefore:

| Command | Counts |
|---:|---:|
| 1 µm | 100 |
| 500 nm | 50 |
| 400 nm | 40 |
| 300 nm | 30 |
| 100 nm | 10 |


## Example servo profile

The current archived threshold-refinement profile is:

```text
GF = 0
GI = 0.2
GP = 2
GV = 1.5
FT = 0
CL = 2
PC = 100
TL = 13000
IM = 1
IW = 1000
```

The simple CLI exposes this as:

```text
--profile mx80l-10nm
```


## Firmware encoder sign

The latest included firmware/wiring package uses:

```text
ENCSIGN = 1
```

Older notes that recorded `ENCSIGN=-1` are historical and should not override the current `board_config.h` and wiring documentation.

## Where to find the full experiments

The complete sequence of v4.x release notes, audits, validation scripts, raw policies, and threshold-refinement tooling is preserved in:

[`../archive/commissioning-history/v4_78/`](../archive/commissioning-history/v4_78/)

Use that archive when reproducing the research/commissioning process; use the main documentation for a clean new installation.
