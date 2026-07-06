from __future__ import annotations

import argparse
import json
import re
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from .blocksworld import AtomSet, BlocksworldAction, BlocksworldProblem, IllegalActionError, parse_blocksworld
from .validate_instance import InstanceValidationError, load_fixture, validate_fixture


ACTION_PATTERN = re.compile(r"^\s*([A-Za-z_-]+)\s*\(([^()]*)\)\s*$")


class BenchmarkLoopError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass
class BlocksworldBenchmarkLoop:
    problem: BlocksworldProblem
    instance_id: str
    fixture_path: Path
    max_steps: int
    state: AtomSet = field(init=False)
    step_index: int = field(init=False, default=0)
    step_logs: list[dict[str, Any]] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        if self.max_steps <= 0:
            raise BenchmarkLoopError("invalid_max_steps", "max_steps must be positive")
        self.reset()

    def reset(self) -> dict[str, Any]:
        self.state = self.problem.initial_state()
        self.step_index = 0
        self.step_logs = []
        return self.observe()

    def observe(self) -> dict[str, Any]:
        return build_observation_payload(
            problem=self.problem,
            state=self.state,
            instance_id=self.instance_id,
            fixture_path=self.fixture_path,
            step_index=self.step_index,
            max_steps=self.max_steps,
        )

    def step(self, action_text: str) -> dict[str, Any]:
        if self.is_terminal:
            raise BenchmarkLoopError(
                "terminal_state",
                "cannot step after the benchmark loop reached a terminal state",
                details={"terminal_status": self.terminal_status()},
            )

        observation = self.observe()
        pre_state = self.state
        pre_state_id = self.problem.state_id(pre_state)
        legal_actions = self.problem.legal_action_strings(pre_state)
        action = parse_action_text(action_text)
        action_serialized = action.serialize()
        legal_action_check = {
            "action": action_serialized,
            "is_legal": action_serialized in legal_actions,
            "legal_actions": list(legal_actions),
        }
        if not legal_action_check["is_legal"]:
            raise BenchmarkLoopError(
                "illegal_action",
                f"illegal action in current state: {action_serialized}",
                details={
                    "action": action_serialized,
                    "legal_actions": list(legal_actions),
                    "observation": observation,
                    "pre_state_id": pre_state_id,
                    "step_index": self.step_index,
                },
            )

        try:
            post_state = self.problem.transition(pre_state, action)
        except IllegalActionError as error:  # pragma: no cover - guarded by the explicit legal-action check above.
            raise BenchmarkLoopError("illegal_action", str(error), details=legal_action_check) from error

        self.state = post_state
        self.step_index += 1
        terminal_status = self.terminal_status()
        step_log = {
            "step_index": self.step_index - 1,
            "observation": observation,
            "action": action_serialized,
            "pre_state_id": pre_state_id,
            "post_state_id": self.problem.state_id(post_state),
            "post_state_atoms": sorted(post_state),
            "legal_action_check": legal_action_check,
            "terminal_status": terminal_status,
        }
        self.step_logs.append(step_log)
        return step_log

    @property
    def is_terminal(self) -> bool:
        return self.problem.is_goal(self.state) or self.step_index >= self.max_steps

    def terminal_status(self) -> dict[str, Any]:
        solved = self.problem.is_goal(self.state)
        max_steps_reached = self.step_index >= self.max_steps
        if solved:
            reason = "goal"
        elif max_steps_reached:
            reason = "max_steps"
        else:
            reason = "running"
        return {
            "is_terminal": solved or max_steps_reached,
            "reason": reason,
            "solved": solved,
            "max_steps_reached": max_steps_reached,
            "step_index": self.step_index,
        }

    def run_scripted(self, actions: Iterable[str]) -> dict[str, Any]:
        self.reset()
        for action in actions:
            if self.is_terminal:
                break
            self.step(action)
        return build_run_payload(loop=self, mode="scripted", selected_actions=list(actions))

    def run_oracle(self) -> dict[str, Any]:
        self.reset()
        selected_actions: list[str] = []
        while not self.is_terminal:
            plan = shortest_action_plan(self.problem, self.state, max_depth=max(64, self.max_steps + 8))
            if not plan:
                break
            next_action = plan[0]
            selected_actions.append(next_action.serialize())
            self.step(next_action.serialize())
        return build_run_payload(loop=self, mode="oracle", selected_actions=selected_actions)


def build_observation_payload(
    *,
    problem: BlocksworldProblem,
    state: Iterable[str],
    instance_id: str,
    fixture_path: Path,
    step_index: int,
    max_steps: int,
) -> dict[str, Any]:
    atom_set = frozenset(state)
    return {
        "schema_version": "planning_benchmark_observation_v1",
        "domain": "blocksworld",
        "instance_id": instance_id,
        "fixture": str(fixture_path),
        "step_index": step_index,
        "max_steps": max_steps,
        "state_id": problem.state_id(atom_set),
        "state_atoms": sorted(atom_set),
        "goal_atoms": sorted(problem.goal_atoms),
        "legal_actions": list(problem.legal_action_strings(atom_set)),
        "is_goal": problem.is_goal(atom_set),
    }


def parse_action_text(action_text: str) -> BlocksworldAction:
    match = ACTION_PATTERN.match(action_text)
    if match is None:
        raise BenchmarkLoopError(
            "illegal_action",
            f"action must use canonical form name(arg1,arg2): {action_text!r}",
            details={"action": action_text},
        )
    name = match.group(1).strip().lower()
    args = tuple(arg.strip().lower() for arg in match.group(2).split(",") if arg.strip())
    try:
        return BlocksworldAction(name, args)
    except ValueError as error:
        raise BenchmarkLoopError("illegal_action", str(error), details={"action": action_text}) from error


def shortest_action_plan(problem: BlocksworldProblem, start_state: Iterable[str], *, max_depth: int) -> tuple[BlocksworldAction, ...] | None:
    start = frozenset(start_state)
    if problem.is_goal(start):
        return tuple()

    frontier: deque[tuple[AtomSet, tuple[BlocksworldAction, ...]]] = deque([(start, tuple())])
    visited = {problem.state_id(start)}
    while frontier:
        state, plan = frontier.popleft()
        if len(plan) >= max_depth:
            continue
        for action in problem.legal_actions(state):
            next_state = problem.transition(state, action)
            next_id = problem.state_id(next_state)
            if next_id in visited:
                continue
            next_plan = (*plan, action)
            if problem.is_goal(next_state):
                return next_plan
            visited.add(next_id)
            frontier.append((next_state, next_plan))
    return None


def load_validated_loop(fixture_path: Path, *, max_steps: int) -> BlocksworldBenchmarkLoop:
    validate_fixture(fixture_path, require_non_empty_goal=True)
    fixture = load_fixture(fixture_path)
    problem = parse_blocksworld(fixture.domain_pddl, fixture.problem_pddl)
    instance_id = str(fixture.payload.get("instance_id") or problem.problem_name)
    return BlocksworldBenchmarkLoop(
        problem=problem,
        instance_id=instance_id,
        fixture_path=fixture_path,
        max_steps=max_steps,
    )


def load_scripted_actions(path: Path) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise BenchmarkLoopError("malformed_actions", f"actions JSON is malformed: {error}") from error
    if isinstance(payload, list):
        actions = payload
    elif isinstance(payload, dict) and isinstance(payload.get("actions"), list):
        actions = payload["actions"]
    else:
        raise BenchmarkLoopError("malformed_actions", "actions file must be a JSON list or an object with an actions list")
    if not all(isinstance(action, str) and action.strip() for action in actions):
        raise BenchmarkLoopError("malformed_actions", "every scripted action must be a non-empty string")
    return [str(action) for action in actions]


def build_run_payload(*, loop: BlocksworldBenchmarkLoop, mode: str, selected_actions: Sequence[str]) -> dict[str, Any]:
    terminal_status = loop.terminal_status()
    return {
        "valid": True,
        "schema_version": "planning_benchmark_loop_run_v1",
        "mode": mode,
        "domain": "blocksworld",
        "fixture": str(loop.fixture_path),
        "instance_id": loop.instance_id,
        "max_steps": loop.max_steps,
        "steps": len(loop.step_logs),
        "selected_actions": list(selected_actions),
        "solved": terminal_status["solved"],
        "illegal_action_count": 0,
        "initial_observation": build_observation_payload(
            problem=loop.problem,
            state=loop.problem.initial_state(),
            instance_id=loop.instance_id,
            fixture_path=loop.fixture_path,
            step_index=0,
            max_steps=loop.max_steps,
        ),
        "final_observation": loop.observe(),
        "terminal_status": terminal_status,
        "step_logs": loop.step_logs,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the direct Python Blocksworld benchmark loop.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    oracle = subparsers.add_parser("run-oracle", help="Run deterministic local BFS oracle actions.")
    _add_common_run_args(oracle)

    scripted = subparsers.add_parser("run-scripted", help="Run a scripted action sequence from JSON.")
    _add_common_run_args(scripted)
    scripted.add_argument("--actions", required=True, type=Path, help="JSON list or object containing an actions list.")
    return parser


def _add_common_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--fixture", required=True, type=Path, help="Validated planning fixture JSON.")
    parser.add_argument("--max-steps", type=int, default=64, help="Maximum in-process environment steps.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")


def _error_payload(error: BenchmarkLoopError | InstanceValidationError) -> dict[str, Any]:
    if isinstance(error, InstanceValidationError):
        return {"valid": False, "error": {"code": error.code, "message": str(error), "details": error.details}}
    return {"valid": False, "error": {"code": error.code, "message": str(error), "details": error.details}}


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.max_steps <= 0:
        parser.exit(status=2, message="--max-steps must be positive\n")

    try:
        loop = load_validated_loop(args.fixture, max_steps=args.max_steps)
        if args.command == "run-oracle":
            payload = loop.run_oracle()
        elif args.command == "run-scripted":
            payload = loop.run_scripted(load_scripted_actions(args.actions))
        else:  # pragma: no cover - argparse prevents this branch.
            raise BenchmarkLoopError("unknown_command", f"unsupported command: {args.command}")
    except (BenchmarkLoopError, InstanceValidationError) as error:
        if args.json:
            print(json.dumps(_error_payload(error), indent=2, sort_keys=True))
        else:
            print(f"invalid: {error}")
        code = error.code if isinstance(error, (BenchmarkLoopError, InstanceValidationError)) else "benchmark_loop_error"
        print(f"{code}: {error}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"solved={payload['solved']} steps={payload['steps']} mode={payload['mode']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BenchmarkLoopError",
    "BlocksworldBenchmarkLoop",
    "build_observation_payload",
    "build_parser",
    "load_scripted_actions",
    "load_validated_loop",
    "main",
    "parse_action_text",
    "shortest_action_plan",
]
