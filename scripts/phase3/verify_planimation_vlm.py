"""Compatibility CLI for Phase 3 Planimation release verification."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.phase3.planimation_release_verification import VerificationFailure, verify_output

__all__ = ("VerificationFailure", "verify_output", "main")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 3 Planimation/VLM pairing artifacts.")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("manifest", "render", "release"), default="manifest")
    args = parser.parse_args()
    try:
        result = verify_output(args.output_root, args.mode)
    except VerificationFailure as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
