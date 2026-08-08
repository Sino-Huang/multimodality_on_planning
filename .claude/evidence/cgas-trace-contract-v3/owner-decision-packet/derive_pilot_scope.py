#!/usr/bin/env python
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))


def main() -> int:
    os.chdir(ROOT)
    runpy.run_module("scripts.phase3.cgas_pilot_scope_evidence", run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
