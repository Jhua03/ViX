#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

root = Path.home() / "vix100nm_runs"
if not root.exists():
    raise SystemExit(f"No run directory: {root}")

finals = sorted(root.glob("*/FINAL_100NM_VERDICT.json"), key=lambda p: p.stat().st_mtime)
if finals:
    path = finals[-1]
    print(f"Latest final verdict: {path}")
    print(json.dumps(json.loads(path.read_text()), indent=2))
    raise SystemExit(0)

summaries = sorted(root.glob("*/*summary.json"), key=lambda p: p.stat().st_mtime)
if summaries:
    path = summaries[-1]
    print(f"No final verdict yet. Latest summary: {path}")
    print(json.dumps(json.loads(path.read_text()), indent=2))
else:
    print("No stage summaries found.")
