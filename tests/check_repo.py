#!/usr/bin/env python3
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
errors=[]

# All relative Markdown links/images must resolve. Ignore anchors, URLs and mailto.
link_re = re.compile(r'!?\[[^\]]*\]\(([^)]+)\)')
for md in ROOT.rglob('*.md'):
    # Archived historical files intentionally preserve old paths/links verbatim.
    if 'archive/commissioning-history' in md.as_posix():
        continue
    text=md.read_text(encoding='utf-8', errors='replace')
    for raw in link_re.findall(text):
        dest=raw.strip().split()[0].strip('<>')
        if not dest or dest.startswith(('#','http://','https://','mailto:')):
            continue
        dest=dest.split('#',1)[0]
        target=(md.parent/dest).resolve()
        try:
            target.relative_to(ROOT.resolve())
        except ValueError:
            errors.append(f'{md.relative_to(ROOT)}: link escapes repo: {raw}')
            continue
        if not target.exists():
            errors.append(f'{md.relative_to(ROOT)}: missing link target: {raw}')

# The cleaned firmware runtime sources should match the known-good archived v4.78 sources.
critical=[
    'CMakeLists.txt','platformio.ini','src/board_config.h','src/main.c',
    'src/quadrature_encoder.pio','src/stepgen.pio',
    'extra_scripts/normalize_cmake_timestamp.py','extra_scripts/pico_sdk_tasks.py'
]
archive=ROOT/'archive/commissioning-history/v4_78/firmware'
for rel in critical:
    a=ROOT/'firmware'/rel
    b=archive/rel
    if not a.exists() or not b.exists():
        errors.append(f'missing firmware comparison file: {rel}')
    elif a.read_bytes()!=b.read_bytes():
        errors.append(f'top-level firmware behavior source differs from validated archive: {rel}')

# Required public-guide artifacts.
required=[
    'README.md','CHANGELOG.md','docs/hardware-and-wiring.md','docs/serial-x3.md',
    'docs/software-setup.md','docs/commissioning.md','docs/safety.md',
    'hardware/bom.md','hardware/connector-pinouts.md',
    'hardware/schematic/vix_pico_interface.sch','hardware/ViX_AH_Pico2_Wiring.drawio',
    'datasheets/Parker_ViX_AH_User_Guide.pdf','datasheets/TI_AM26LV31E.pdf',
    'datasheets/TI_AM26LV32E.pdf','host/vix.py'
]
for rel in required:
    if not (ROOT/rel).exists():
        errors.append(f'missing required artifact: {rel}')

if errors:
    print('Repository checks FAILED:')
    for e in errors:
        print(' -',e)
    sys.exit(1)
print('Repository structure/link/firmware-source checks PASS')
