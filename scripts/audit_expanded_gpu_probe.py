#!/usr/bin/env python
"""Completion hook for the bounded hardware probe."""

import json
import os
from pathlib import Path

terminal = json.loads(Path(os.environ["EXPANDED_TERMINAL_PATH"]).read_text())
folder = Path(terminal["directory"])
if terminal["status"] != "succeeded":
    raise RuntimeError(f"hardware probe failed; inspect {folder / 'worker.log'}")
report = json.loads((folder / "hardware.json").read_text())
assert report["outcome"] == "PASS"
assert int(report["master_port"]) == terminal["master_port"]
assert report["cuda_visible_devices"] == ",".join(map(str, terminal["gpus"]))
assert report["total_bytes"] >= 80_000_000_000
assert json.loads((folder / "progress.json").read_text())["completed"] == terminal["total"]
print("PASS: hardware, device/port binding and full probe coverage")
