#!/usr/bin/env python3
"""Offline import/parser test without requiring pyserial to be installed."""
import importlib.util
from pathlib import Path
import sys
import types

root=Path(__file__).resolve().parents[1]
fake=types.ModuleType('serial')
class SerialException(Exception): pass
class Serial: pass
fake.SerialException=SerialException
fake.Serial=Serial
sys.modules['serial']=fake
spec=importlib.util.spec_from_file_location('vix_cli', root/'host/vix.py')
mod=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=mod
spec.loader.exec_module(mod)
parser=mod.build_parser()
for argv in [
    ['info'], ['status'], ['configure'], ['disable'],
    ['jog','--um','1','--confirm-inputs','--i-understand']
]:
    ns=parser.parse_args(argv)
    assert callable(ns.func)
assert mod.MX80L.counts_per_mm == 100_000
assert mod.MX80L.gi == 0.2
print('Host CLI import/parser checks PASS')
