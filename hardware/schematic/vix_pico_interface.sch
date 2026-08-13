EESchema Schematic File Version 4
LIBS:vix_pico_interface-cache
EELAYER 29 0
EELAYER END
$Descr A4 11693 8268
Sheet 1 1
Title "Raspberry Pi Pico 2 to Parker ViX250AH / ViX500AH X4 Interface"
Date "2026-08-12"
Rev "1.0"
Comp "ViX Pico 2 Interface"
Comment1 "Low-voltage interface only. Do not breadboard X1 motor/HV wiring."
Comment2 "AM26LV31E/32E operate at 3.3 V. X4 pin 11 is sunk with NPN when ES=0."
Comment3 "Optional 120R termination resistors are DNP for short bench wiring."
Comment4 "Open in KiCad and save to current .kicad_sch format if desired."
$EndDescr
Text Notes 700 650 0    100  ~ 20
Pico 2 <-> ViX AH X4 interface (STEP/DIR, encoder copy, fault, energise)
$Comp
L PICO2_CTRL U3
U 1 1 66000001
P 1600 3500
F 0 "U3" H 1600 4550 50  0000 C CNN
F 1 "Raspberry_Pi_Pico_2" H 1600 4450 50 0000 C CNN
	1    1600 3500
	1    0    0    -1
$EndComp
$Comp
L AM26LV31E U1
U 1 1 66000002
P 4300 2600
F 0 "U1" H 4300 3650 50 0000 C CNN
F 1 "AM26LV31E" H 4300 3550 50 0000 C CNN
	1    4300 2600
	1    0    0    -1
$EndComp
$Comp
L AM26LV32E U2
U 1 1 66000003
P 4300 5100
F 0 "U2" H 4300 6150 50 0000 C CNN
F 1 "AM26LV32E" H 4300 6050 50 0000 C CNN
	1    4300 5100
	1    0    0    -1
$EndComp
$Comp
L VIX_X4 J1
U 1 1 66000004
P 7900 3800
F 0 "J1" H 7900 4950 50 0000 C CNN
F 1 "ViX_X4_HD15_mating_plug" H 7900 4850 50 0000 C CNN
	1    7900 3800
	1    0    0    -1
$EndComp
$Comp
L Q_NPN Q1
U 1 1 66000005
P 8950 6100
F 0 "Q1" H 9150 6200 50 0000 L CNN
F 1 "2N3904" H 9150 6100 50 0000 L CNN
	1    8950 6100
	1    0    0    -1
$EndComp
$Comp
L R R1
U 1 1 66000006
P 8300 6100
F 0 "R1" V 8200 6100 50 0000 C CNN
F 1 "4.7k" V 8300 6100 50 0000 C CNN
	1    8300 6100
	0    1    1    0
$EndComp
$Comp
L R R2
U 1 1 66000007
P 9500 6400
F 0 "R2" V 9400 6400 50 0000 C CNN
F 1 "100k" V 9500 6400 50 0000 C CNN
	1    9500 6400
	0    1    1    0
$EndComp
$Comp
L R R3
U 1 1 66000008
P 3200 5750
F 0 "R3" H 3280 5750 50 0000 L CNN
F 1 "10k" H 3280 5650 50 0000 L CNN
	1    3200 5750
	1    0    0    -1
$EndComp
$Comp
L C C1
U 1 1 66000009
P 3500 1800
F 0 "C1" H 3600 1850 50 0000 L CNN
F 1 "100nF" H 3600 1750 50 0000 L CNN
	1    3500 1800
	1    0    0    -1
$EndComp
$Comp
L C C2
U 1 1 6600000A
P 3500 4300
F 0 "C2" H 3600 4350 50 0000 L CNN
F 1 "100nF" H 3600 4250 50 0000 L CNN
	1    3500 4300
	1    0    0    -1
$EndComp
Text Notes 3700 1450 0 60 ~ 12
U1: differential command driver
Text Notes 3700 3950 0 60 ~ 12
U2: differential encoder receiver
Text Notes 7400 2500 0 60 ~ 12
X4 is a high-density 15-way D-sub socket on the ViX; use a mating HD15 male plug/breakout.
Text Notes 7750 5700 0 60 ~ 12
Energise: with ES=0, X4-11 must be pulled to X4-3/0V. Q1 provides the sink.
Text Notes 800 6650 0 60 ~ 12
Limits/home: connect GP7/GP8/GP9 to verified external sensor outputs. For NPN open-collector sensors use 4.7k pull-ups to 3V3.
Text Notes 800 6900 0 60 ~ 12
E-stop auxiliary: use an NC auxiliary contact from GP12 to GND. This Pico input monitors the E-stop; it is not a substitute for a safety-rated power interruption circuit.
Text Notes 800 7150 0 60 ~ 12
Use twisted pairs for STEP+/-, DIR+/-, A+/-, B+/-, Z+/-. Connect Pico GND to ViX X4 pin 3 for the single-ended fault/energise circuits.

Wire Wire Line
	2400 2800 3300 2800
Text Label 2550 2800 0 50 ~ 0
STEP_LOGIC
Wire Wire Line
	2400 2950 3300 2950
Text Label 2550 2950 0 50 ~ 0
DIR_LOGIC
Wire Wire Line
	5100 3200 6900 3200
Text Label 5600 3200 0 50 ~ 0
STEP_P
Wire Wire Line
	5100 3100 6900 3100
Text Label 5600 3100 0 50 ~ 0
STEP_N
Wire Wire Line
	5100 2900 6900 3000
Text Label 5600 2950 0 50 ~ 0
DIR_P
Wire Wire Line
	5100 2800 6900 2900
Text Label 5600 2850 0 50 ~ 0
DIR_N
Wire Wire Line
	3500 3150 3300 3150
Text Label 3000 3150 0 50 ~ 0
STEP_LOGIC
Wire Wire Line
	3500 2850 3300 2850
Text Label 3000 2850 0 50 ~ 0
DIR_LOGIC
Wire Wire Line
	3500 2550 3300 2550
Text Label 3000 2550 0 50 ~ 0
GND
Wire Wire Line
	3500 2250 3300 2250
Text Label 3000 2250 0 50 ~ 0
GND
Wire Wire Line
	3500 2100 3300 2100
Text Label 3000 2100 0 50 ~ 0
GND
Wire Wire Line
	3500 1950 3300 1950
Text Label 3000 1950 0 50 ~ 0
3V3
Wire Wire Line
	4400 1600 4400 1500
Text Label 4200 1500 0 50 ~ 0
3V3
Wire Wire Line
	4200 3600 4200 3700
Text Label 4000 3700 0 50 ~ 0
GND

Wire Wire Line
	6900 4350 3500 5700
Text Label 5600 4700 0 50 ~ 0
ENC_A_P
Wire Wire Line
	6900 4250 3500 5600
Text Label 5600 4550 0 50 ~ 0
ENC_A_N
Wire Wire Line
	6900 4150 3500 5400
Text Label 5600 4350 0 50 ~ 0
ENC_B_P
Wire Wire Line
	6900 4050 3500 5300
Text Label 5600 4200 0 50 ~ 0
ENC_B_N
Wire Wire Line
	6900 3450 3500 5100
Text Label 5600 3900 0 50 ~ 0
ENC_Z_P
Wire Wire Line
	6900 3350 3500 5000
Text Label 5600 3750 0 50 ~ 0
ENC_Z_N
Wire Wire Line
	5100 5650 2400 3100
Text Label 2900 3350 0 50 ~ 0
ENC_A_LOGIC
Wire Wire Line
	5100 5350 2400 3250
Text Label 2900 3500 0 50 ~ 0
ENC_B_LOGIC
Wire Wire Line
	5100 5050 2400 3400
Text Label 2900 3650 0 50 ~ 0
ENC_Z_LOGIC
Wire Wire Line
	3500 4600 3300 4600
Text Label 3000 4600 0 50 ~ 0
3V3
Wire Wire Line
	3500 4450 3300 4450
Text Label 3000 4450 0 50 ~ 0
GND
Wire Wire Line
	4400 4100 4400 4000
Text Label 4200 4000 0 50 ~ 0
3V3
Wire Wire Line
	4200 6100 4200 6200
Text Label 4000 6200 0 50 ~ 0
GND

Wire Wire Line
	800 4200 700 4200
Text Label 700 4200 2 50 ~ 0
3V3
Wire Wire Line
	800 4050 700 4050
Text Label 700 4050 2 50 ~ 0
GND

Wire Wire Line
	2400 3700 3000 3700
Text Label 2550 3700 0 50 ~ 0
VIX_FAULT
Wire Wire Line
	6900 4450 6500 4450
Text Label 6500 4450 2 50 ~ 0
VIX_FAULT
Wire Wire Line
	3200 5550 3200 5450
Text Label 3000 5450 0 50 ~ 0
3V3
Wire Wire Line
	3200 5950 3200 6050
Text Label 3000 6050 0 50 ~ 0
VIX_FAULT

Wire Wire Line
	2400 3850 8100 6100
Text Label 2900 3850 0 50 ~ 0
DRIVE_ENABLE
Wire Wire Line
	8500 6100 8650 6100
Wire Wire Line
	9070 5740 9070 5550
Text Label 8900 5550 0 50 ~ 0
ENERGISE
Wire Wire Line
	6900 4550 6500 4550
Text Label 6500 4550 2 50 ~ 0
ENERGISE
Wire Wire Line
	9070 6460 9070 6600
Text Label 8900 6600 0 50 ~ 0
GND
Wire Wire Line
	9300 6400 9070 6400
Wire Wire Line
	9700 6400 9700 6600
Text Label 9550 6600 0 50 ~ 0
GND
Wire Wire Line
	6900 4550 6900 4550
Wire Wire Line
	6900 3050 6500 3050
Text Label 6500 3050 2 50 ~ 0
X4_0V
Wire Wire Line
	700 4050 700 4400
Text Label 700 4400 2 50 ~ 0
X4_0V

Wire Wire Line
	3500 1600 3500 1500
Text Label 3300 1500 0 50 ~ 0
3V3
Wire Wire Line
	3500 2000 3500 2100
Text Label 3300 2100 0 50 ~ 0
GND
Wire Wire Line
	3500 4100 3500 4000
Text Label 3300 4000 0 50 ~ 0
3V3
Wire Wire Line
	3500 4500 3500 4600
Text Label 3300 4600 0 50 ~ 0
GND

Text Notes 800 7500 0 55 ~ 0
Optional termination: add 100-120R across each differential pair at the receiving end if cable length/edge rate requires it. For short bench wiring, leave DNP unless signal integrity testing indicates otherwise.
$EndSCHEMATC
