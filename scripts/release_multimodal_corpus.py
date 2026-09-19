"""Release #74 by replay-checking and referencing the approved #73 records."""

# ruff: noqa: E402
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release_visual_corpus import main

if __name__ == "__main__":
    raise SystemExit(main(issue=74))
