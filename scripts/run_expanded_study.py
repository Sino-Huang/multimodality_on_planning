#!/usr/bin/env python
"""Run the shared expanded-study scheduler."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.planning_benchmark_slice.expanded_scheduler import main

if __name__ == "__main__":
    main()
