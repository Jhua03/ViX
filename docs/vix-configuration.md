# ViX250AH / ViX500AH configuration

## 1. What is generic and what is motor-specific

The X4 I/O mode is generic to this repository's ViX AH architecture. Servo gains, current limits, encoder scale, tracking limits, and motion acceptance criteria depend on the attached motor/stage.

The supported CLI therefore offers:

- `--profile io-only`: configure the ViX X4 interface only;
- `--profile mx80l-10nm`: additionally apply the included tested MX80L example tuning.

## 2. X4 interface configuration

The host sets the drive OFF before applying configuration and uses:

```text
MP
W(ES,0)
W(EI,0)
W(EO,2)
```

Meaning:

| Setting | Meaning in this project |
|---|---|
| `MP` | position mode for external pulse/direction control |
| `ES=0` | X4 energise input is active-low |
| `EI=0` | X4 command input uses STEP/DIR |
| `EO=2` | X4 encoder copy provides A/B quadrature outputs |

The host reads these values back before it will proceed with a motion transaction.

## 3. Volatile setup policy

The simple host utility intentionally does **not** issue:

```text
SV
MOTOR
SETUPFB
RFS
```

The guide assumes a drive whose motor/feedback base configuration has already been established correctly. Experiment-specific I/O/tuning values are applied volatilely so a commissioning mistake does not silently become the drive's permanent boot configuration.

## 4. Typical serial commands

Commands are prefixed with the ViX software axis address. Examples shown for axis 1:

```text
1R(RV)       read software revision
1STATUS      status report
1R(DF)       drive-fault word
1R(UF)       user-fault word (be aware of clear-on-read behavior in the ViX manual)
1OFF         de-energise
1ON          energise, only after the Pico hardware-enable path is safe and active
```

## 5. MX80L 10 nm example profile

Only use this profile with a machine whose motor/encoder/stage has actually been validated for it:

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

The CLI applies these after setting `MP`, `ES=0`, `EI=0`, and `EO=2` when `--profile mx80l-10nm` is selected.

See [Tuning and performance](tuning-and-performance.md) for the example machine's scale and measured limitations.
