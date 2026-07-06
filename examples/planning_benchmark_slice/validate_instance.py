from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .blocksworld import BlocksworldParseError, BlocksworldProblem, parse_blocksworld


class InstanceValidationError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass(frozen=True)
class FixturePayload:
    path: Path
    payload: dict[str, Any]
    domain_pddl: str
    problem_pddl: str


def _resolve_fixture_path(raw_path: str, *, fixture_path: Path) -> Path:
    path = Path(raw_path)
    if path.exists():
        return path
    candidate = fixture_path.parent / raw_path
    if candidate.exists():
        return candidate
    return path


def load_fixture(path: Path) -> FixturePayload:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise InstanceValidationError("malformed_fixture", f"fixture JSON is malformed: {error}") from error
    if not isinstance(payload, dict):
        raise InstanceValidationError("malformed_fixture", "fixture must contain a JSON object")

    domain_pddl = payload.get("domain_pddl")
    problem_pddl = payload.get("problem_pddl")

    if domain_pddl is None:
        domain_path = payload.get("domain_path") or payload.get("domain_pddl_path")
        if not domain_path:
            raise InstanceValidationError("malformed_fixture", "fixture is missing domain_pddl or domain_path")
        resolved_domain_path = _resolve_fixture_path(str(domain_path), fixture_path=path)
        if not resolved_domain_path.exists():
            raise InstanceValidationError("missing_pddl", f"domain PDDL path is missing: {domain_path}")
        domain_pddl = resolved_domain_path.read_text(encoding="utf-8")

    if problem_pddl is None:
        problem_path = payload.get("problem_path") or payload.get("problem_pddl_path")
        if not problem_path:
            raise InstanceValidationError("malformed_fixture", "fixture is missing problem_pddl or problem_path")
        resolved_problem_path = _resolve_fixture_path(str(problem_path), fixture_path=path)
        if not resolved_problem_path.exists():
            raise InstanceValidationError("missing_pddl", f"problem PDDL path is missing: {problem_path}")
        problem_pddl = resolved_problem_path.read_text(encoding="utf-8")

    if not isinstance(domain_pddl, str) or not isinstance(problem_pddl, str):
        raise InstanceValidationError("malformed_fixture", "domain_pddl and problem_pddl must be strings")
    return FixturePayload(path=path, payload=payload, domain_pddl=domain_pddl, problem_pddl=problem_pddl)


def validate_fixture(
    fixture_path: Path,
    *,
    min_plan_length: int = 0,
    require_non_empty_goal: bool = False,
    require_render_artifacts: bool = False,
) -> dict[str, Any]:
    fixture = load_fixture(fixture_path)
    try:
        problem = parse_blocksworld(fixture.domain_pddl, fixture.problem_pddl)
    except BlocksworldParseError as error:
        message = str(error)
        code = "malformed_pddl"
        if "missing required Blocksworld actions" in message or "unsupported Blocksworld actions" in message:
            code = "missing_action_vocabulary"
        raise InstanceValidationError(code, message) from error

    if require_non_empty_goal and problem.goal_is_empty:
        raise InstanceValidationError("empty_goal", "Blocksworld problem has an empty goal")

    already_solved = problem.is_goal(problem.initial_atoms)
    if already_solved:
        raise InstanceValidationError("already_solved", "initial state already satisfies the goal")

    if require_render_artifacts:
        _validate_render_artifacts(fixture.payload, fixture_path=fixture_path)

    shortest_plan_length = problem.shortest_plan_length(max_depth=max(64, min_plan_length + 8))
    if min_plan_length > 0:
        if shortest_plan_length is None:
            raise InstanceValidationError(
                "unsolved_within_depth",
                "no plan was found within the local Blocksworld search depth",
                details={"min_plan_length": min_plan_length},
            )
        if shortest_plan_length < min_plan_length:
            raise InstanceValidationError(
                "below_min_plan_length",
                f"shortest plan length {shortest_plan_length} is below requested minimum {min_plan_length}",
                details={"min_plan_length": min_plan_length, "shortest_plan_length": shortest_plan_length},
            )

    legal_actions = problem.legal_action_strings(problem.initial_atoms)
    if not legal_actions:
        raise InstanceValidationError("no_legal_actions", "initial state has no legal Blocksworld actions")

    return _success_payload(
        fixture_path=fixture_path,
        problem=problem,
        already_solved=already_solved,
        min_plan_length=min_plan_length,
        shortest_plan_length=shortest_plan_length,
    )


def _success_payload(
    *,
    fixture_path: Path,
    problem: BlocksworldProblem,
    already_solved: bool,
    min_plan_length: int,
    shortest_plan_length: int | None,
) -> dict[str, Any]:
    payload = problem.to_summary()
    payload.update(
        {
            "valid": True,
            "fixture": str(fixture_path),
            "already_solved": already_solved,
            "min_plan_length_requested": min_plan_length,
            "min_plan_length_satisfied": shortest_plan_length is not None and shortest_plan_length >= min_plan_length,
            "shortest_plan_length": shortest_plan_length,
        }
    )
    return payload


def _validate_render_artifacts(payload: dict[str, Any], *, fixture_path: Path) -> None:
    render_paths: list[Path] = []
    trace_path = payload.get("render_trace") or payload.get("trace_path")
    result_path = payload.get("render_result_path")
    frame_paths = payload.get("render_frames") or payload.get("frame_paths") or []
    artifact_paths = payload.get("render_artifact_paths") or []

    if trace_path:
        render_paths.append(_resolve_fixture_path(str(trace_path), fixture_path=fixture_path))
    if result_path:
        render_paths.append(_resolve_fixture_path(str(result_path), fixture_path=fixture_path))
    if isinstance(frame_paths, list):
        render_paths.extend(_resolve_fixture_path(str(path), fixture_path=fixture_path) for path in frame_paths)
    if isinstance(artifact_paths, list):
        render_paths.extend(_resolve_fixture_path(str(path), fixture_path=fixture_path) for path in artifact_paths)

    if not render_paths:
        raise InstanceValidationError("missing_render_artifacts", "vision-required validation needs render artifact paths")

    missing = sorted(str(path) for path in render_paths if not path.exists())
    if missing:
        raise InstanceValidationError(
            "missing_render_artifacts",
            "one or more render artifacts are missing",
            details={"missing_paths": missing},
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a Blocksworld planning fixture.")
    parser.add_argument("--fixture", required=True, type=Path, help="Fixture JSON containing PDDL text or PDDL paths.")
    parser.add_argument("--min-plan-length", type=int, default=0, help="Reject tasks below this shortest-plan length.")
    parser.add_argument("--require-non-empty-goal", action="store_true", help="Reject (:goal (and)) tasks.")
    parser.add_argument(
        "--require-render-artifacts",
        action="store_true",
        help="Require referenced render trace/frame/result files for vision paths.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser


def _error_payload(error: InstanceValidationError) -> dict[str, Any]:
    return {"valid": False, "error": {"code": error.code, "message": str(error), "details": error.details}}


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.min_plan_length < 0:
        parser.exit(status=2, message="--min-plan-length must be non-negative\n")

    try:
        payload = validate_fixture(
            args.fixture,
            min_plan_length=args.min_plan_length,
            require_non_empty_goal=args.require_non_empty_goal,
            require_render_artifacts=args.require_render_artifacts,
        )
    except InstanceValidationError as error:
        if args.json:
            print(json.dumps(_error_payload(error), indent=2, sort_keys=True))
        else:
            print(f"invalid: {error.code}: {error}")
        print(f"{error.code}: {error}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"valid: {args.fixture}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "FixturePayload",
    "InstanceValidationError",
    "build_parser",
    "load_fixture",
    "main",
    "validate_fixture",
]
