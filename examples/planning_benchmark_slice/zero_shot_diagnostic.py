from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .zero_shot import ZeroShotError, score_model_output_payload, validate_model_output_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate and score zero-shot diagnostic model outputs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate-schema", help="Validate model output JSON schema.")
    validate_parser.add_argument("--input", required=True, type=Path, help="JSON fixture containing model output.")
    validate_parser.add_argument("--json", action="store_true", help="Emit JSON. This is also the default output.")

    score_parser = subparsers.add_parser("score", help="Score model output against gold diagnostic metadata.")
    score_parser.add_argument("--input", required=True, type=Path, help="JSON fixture containing model output and gold metadata.")
    score_parser.add_argument("--json", action="store_true", help="Emit JSON. This is also the default output.")
    return parser


def load_input(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ZeroShotError("fixture_json_parse_error", f"input fixture JSON is malformed: {error}") from error
    if not isinstance(payload, dict):
        raise ZeroShotError("fixture_not_object", "input fixture must contain a JSON object")
    return payload


def _error_payload(error: Exception, code: str = "zero_shot_diagnostic_error") -> dict[str, Any]:
    details = getattr(error, "details", {})
    return {"error": {"code": code, "details": details, "message": str(error)}, "valid": False}


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = load_input(args.input)
        if args.command == "validate-schema":
            result = validate_model_output_payload(payload)
            exit_code = 0 if result["valid"] else 1
            if exit_code:
                print(f"schema invalid: {result['error']['code']}: {result['error']['message']}", file=sys.stderr)
        elif args.command == "score":
            result = score_model_output_payload(payload)
            exit_code = 0
        else:  # pragma: no cover - argparse enforces command choices.
            parser.error(f"unsupported command: {args.command}")
    except ZeroShotError as error:
        result = _error_payload(error, error.code)
        print(f"{error.code}: {error}", file=sys.stderr)
        exit_code = 1
    except OSError as error:
        result = _error_payload(error)
        print(str(error), file=sys.stderr)
        exit_code = 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "load_input", "main"]
