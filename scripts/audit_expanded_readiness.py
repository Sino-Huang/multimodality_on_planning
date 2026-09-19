#!/usr/bin/env python
"""CPU completion hook for checkpoint readiness coverage."""

import json
import os
from pathlib import Path

terminal = json.loads(Path(os.environ["EXPANDED_TERMINAL_PATH"]).read_text())
assert terminal["status"] == "succeeded", terminal
report = json.loads(Path("docs/experiments/expanded-study/readiness.json").read_text())
cells = report["checkpoints"]
assert report["outcome"] == "PASS"
assert len(cells) == len({(c["modality"], c["algorithm"]) for c in cells}) == 12
assert all(c["provenance_passed"] and c["all_tensors_finite"] and c["steps"] == 16 for c in cells)
assert report["started"] >= terminal["started"]
progress = json.loads((Path(terminal["directory"]) / "progress.json").read_text())
assert progress["completed"] == terminal["total"] == 12
print("PASS: all twelve checkpoint validations belong to this completed attempt")
