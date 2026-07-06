from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .trajectory_schema import TrajectorySchemaError, validate_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate canonical planning expert trajectory JSON/JSONL files.")
    parser.add_argument("--input", required=True, type=Path, help="Trajectory JSON/JSONL file or directory to validate.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON. This is also the default output.")
    return parser


def _error_payload(error: TrajectorySchemaError | OSError) -> dict[str, Any]:
    code = getattr(error, "code", "trajectory_schema_error")
    details = getattr(error, "details", {})
    return {"error": {"code": code, "details": details, "message": str(error)}, "valid": False}


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = validate_path(args.input)
    except (TrajectorySchemaError, OSError) as error:
        print(json.dumps(_error_payload(error), indent=2, sort_keys=True))
        print(f"{getattr(error, 'code', 'trajectory_schema_error')}: {error}", file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["valid"]:
        first_error = payload["errors"][0]
        print(
            f"trajectory schema invalid: {first_error['path']}: {first_error['message']}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
