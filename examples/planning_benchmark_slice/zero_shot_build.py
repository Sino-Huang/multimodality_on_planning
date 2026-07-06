from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .zero_shot import ALGORITHMS, MODALITIES, ZeroShotError, build_prompt_packages, leakage_errors_for_packages, write_prompt_packages


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build offline zero-shot diagnostic prompt packages.")
    parser.add_argument("--fixture", required=True, type=Path, help="Validated Blocksworld fixture JSON.")
    parser.add_argument("--algorithms", nargs="+", default=list(ALGORITHMS), help="Algorithms to package.")
    parser.add_argument("--modalities", nargs="+", default=list(MODALITIES), help="Modalities to package.")
    parser.add_argument("--output", required=True, type=Path, help="Directory to write prompt package JSON files.")
    parser.add_argument("--json", action="store_true", help="Emit JSON. This is also the default output.")
    return parser


def build_zero_shot_artifacts(
    *, fixture: Path, algorithms: Sequence[str], modalities: Sequence[str], output: Path
) -> dict[str, Any]:
    packages = build_prompt_packages(fixture_path=fixture, algorithms=algorithms, modalities=modalities)
    leakage_errors = leakage_errors_for_packages(packages)
    written = write_prompt_packages(packages, output)
    return {
        "algorithms": [package["algorithm"] for package in packages if package["modality"] == packages[0]["modality"]]
        if packages
        else [],
        "fixture": str(fixture),
        "leakage_errors": leakage_errors,
        "modalities": sorted({str(package["modality"]) for package in packages}),
        "output": str(output),
        "package_count": len(packages),
        "packages": written,
        "valid": not leakage_errors,
    }


def _error_payload(error: Exception, code: str = "zero_shot_build_error") -> dict[str, Any]:
    details = getattr(error, "details", {})
    return {"error": {"code": code, "details": details, "message": str(error)}, "valid": False}


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = build_zero_shot_artifacts(
            fixture=args.fixture,
            algorithms=args.algorithms,
            modalities=args.modalities,
            output=args.output,
        )
    except ZeroShotError as error:
        print(json.dumps(_error_payload(error, error.code), indent=2, sort_keys=True))
        print(f"{error.code}: {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        print(json.dumps(_error_payload(error), indent=2, sort_keys=True))
        print(str(error), file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["valid"]:
        print("modality leakage detected", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "build_zero_shot_artifacts", "main"]
