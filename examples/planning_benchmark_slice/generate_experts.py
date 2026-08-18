from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .blocksworld import parse_blocksworld
from .experts import generate_expert_records, validate_supported_expert_algorithms
from .trajectory_schema import SCHEMA_VERSION, TrajectorySchemaError, canonical_json_text, validate_path
from .validate_instance import InstanceValidationError, load_fixture, validate_fixture
from .zero_shot import normalize_algorithm, validate_algorithms

GENERATION_SCHEMA_VERSION = "planning_expert_generation_v1"


class ExpertGenerationError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate local Blocksworld expert trajectory traces.")
    parser.add_argument(
        "--fixture", required=True, type=Path, help="Fixture JSON containing Blocksworld PDDL text or paths."
    )
    parser.add_argument(
        "--algorithms",
        nargs="+",
        required=True,
        help="Expert algorithms to generate. Supported: bfs iterated_width.",
    )
    parser.add_argument(
        "--output", required=True, type=Path, help="Output directory for generated trajectory JSON files."
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON. This is also the default output."
    )
    return parser


def generate_experts(*, fixture_path: Path, algorithms: Sequence[str], output_dir: Path) -> dict[str, Any]:
    normalized_algorithms = tuple(normalize_algorithm(algorithm) for algorithm in algorithms)
    try:
        validate_algorithms(normalized_algorithms)
        validate_supported_expert_algorithms(normalized_algorithms)
    except ValueError as error:
        raise ExpertGenerationError("unsupported_algorithm", str(error)) from error

    validate_fixture(fixture_path, min_plan_length=1, require_non_empty_goal=True)
    fixture = load_fixture(fixture_path)
    problem = parse_blocksworld(fixture.domain_pddl, fixture.problem_pddl)
    instance_id = str(fixture.payload.get("instance_id") or problem.problem_name)

    output_dir.mkdir(parents=True, exist_ok=True)
    by_algorithm: dict[str, dict[str, Any]] = {}

    for algorithm in normalized_algorithms:
        records = generate_expert_records(
            algorithm=algorithm,
            problem=problem,
            instance_id=instance_id,
            fixture_path=fixture_path,
        )
        if not records:
            raise ExpertGenerationError("no_trajectory", f"{algorithm} did not generate any trajectory records")
        trajectory_id = f"{instance_id}__{algorithm}"
        path = output_dir / f"{trajectory_id}.json"
        payload = {
            "algorithm": algorithm,
            "domain": "blocksworld",
            "instance_id": instance_id,
            "metadata": {
                "schema_version": SCHEMA_VERSION,
                "source": "local_expert_generator",
                "world_model": "deterministic_symbolic_v0",
            },
            "schema_version": SCHEMA_VERSION,
            "steps": records,
            "trajectory_id": trajectory_id,
        }
        path.write_text(canonical_json_text(payload), encoding="utf-8")
        algorithm_summary = {
            "files": [str(path)],
            "record_count": len(records),
            "selected_actions": [record["selected_action"] for record in records],
            "trajectory_count": 1,
        }
        by_algorithm[algorithm] = algorithm_summary

    validation = validate_path(output_dir)
    return {
        "algorithms": by_algorithm,
        "fixture": str(fixture_path),
        "output": str(output_dir),
        "schema_version": GENERATION_SCHEMA_VERSION,
        "valid": validation["valid"],
        "validation": validation,
    }


def _error_payload(error: Exception) -> dict[str, Any]:
    return {
        "error": {
            "code": getattr(error, "code", "expert_generation_error"),
            "details": getattr(error, "details", {}),
            "message": str(error),
        },
        "valid": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = generate_experts(fixture_path=args.fixture, algorithms=args.algorithms, output_dir=args.output)
    except (ExpertGenerationError, InstanceValidationError, TrajectorySchemaError, OSError) as error:
        print(json.dumps(_error_payload(error), indent=2, sort_keys=True))
        print(f"{getattr(error, 'code', 'expert_generation_error')}: {error}", file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["valid"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["ExpertGenerationError", "build_parser", "generate_experts", "main"]
