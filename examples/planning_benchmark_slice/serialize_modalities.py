from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .modality_serializers import ModalitySerializationError, serialize_modalities
from .trajectory_schema import TrajectorySchemaError
from .zero_shot import MODALITIES, ZeroShotError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serialize expert trajectories into modality-specific JSONL datasets.")
    parser.add_argument("--input", required=True, type=Path, help="Trajectory JSON/JSONL file or directory from generate_experts.")
    parser.add_argument("--output", required=True, type=Path, help="Output directory for modality JSONL files.")
    parser.add_argument("--modalities", nargs="+", default=list(MODALITIES), help="Modalities to serialize.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON. This is also the default output.")
    return parser


def _error_payload(error: Exception, code: str | None = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code or getattr(error, "code", "modality_serialization_error"),
            "details": getattr(error, "details", {}),
            "message": str(error),
        },
        "valid": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = serialize_modalities(input_path=args.input, output_dir=args.output, modalities=args.modalities)
    except ZeroShotError as error:
        print(json.dumps(_error_payload(error, error.code), indent=2, sort_keys=True))
        print(f"{error.code}: {error}", file=sys.stderr)
        return 1
    except (ModalitySerializationError, TrajectorySchemaError, OSError, ValueError) as error:
        print(json.dumps(_error_payload(error), indent=2, sort_keys=True))
        print(f"{getattr(error, 'code', 'modality_serialization_error')}: {error}", file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["valid"]:
        print("modality leakage detected", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
