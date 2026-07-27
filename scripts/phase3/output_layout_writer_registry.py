from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from typing_extensions import assert_never


class WriterDetectionError(RuntimeError):
    def __init__(self, rule: str, pid: int | None = None) -> None:
        self.rule = rule
        self.pid = pid
        suffix = f" for pid {pid}" if pid is not None else ""
        super().__init__(f"{rule}{suffix}")


@dataclass(frozen=True, slots=True)
class WriterTarget:
    command: str
    value: str


_DIRECT_COMMANDS: Final = {
    ("scripts", "phase3", "generate_planimation_vlm.py"): "planimation",
    ("scripts", "phase3", "generate_curriculum_trace_dataset.py"): "curriculum-traces",
    ("scripts", "phase3", "generate_supervised_data.py"): "supervised-data",
    ("scripts", "phase3", "rollout_gates.py"): "rollout-gates",
    ("scripts", "phase3", "save_fast_downward_plans.py"): "fast-downward-plans",
    ("scripts", "phase3", "extend_curriculum_workflow.py"): "extend-curriculum",
    ("src", "data_collect", "__main__.py"): "data-collect",
}
_MODULE_COMMANDS: Final = {
    "scripts.phase3.generate_planimation_vlm": "planimation",
    "scripts.phase3.generate_curriculum_trace_dataset": "curriculum-traces",
    "scripts.phase3.generate_supervised_data": "supervised-data",
    "scripts.phase3.rollout_gates": "rollout-gates",
    "scripts.phase3.save_fast_downward_plans": "fast-downward-plans",
    "scripts.phase3.extend_curriculum_workflow": "extend-curriculum",
    "src.data_collect": "data-collect",
}
_PYTHON_SWITCHES: Final = frozenset(("-B", "-E", "-I", "-O", "-OO", "-q", "-s", "-S", "-u", "-v", "--bytes-warning", "--dont-write-bytecode", "--ignore-environment", "--isolated", "--no-site", "--no-user-site", "--quiet", "--utf8", "--verbose"))
_PYTHON_OPTIONS_WITH_VALUE: Final = frozenset(("-W", "-X", "--check-hash-based-pycs"))


def writer_targets(arguments: Sequence[str]) -> tuple[WriterTarget, ...]:
    command, start = _command_identity(arguments)
    if command is None:
        return ()
    options = tuple(arguments[start:])
    match command:
        case "planimation":
            return (_target(command, _required_option(options, "--output-root")),)
        case "curriculum-traces":
            return (_target(command, _option_or_default(options, "--output-root", "outputs/reasoning_traces/curriculum")),)
        case "supervised-data":
            return (_target(command, _option_or_default(options, "--output-root", "data/phase3_supervised_planning")),)
        case "rollout-gates":
            return _rollout_targets(command, options)
        case "fast-downward-plans":
            return (_target(command, _option_or_default(options, "--input-root", "data/curriculum_pddl")),)
        case "extend-curriculum":
            return _extend_targets(command, options)
        case "data-collect":
            return _data_collect_targets(command, options)
        case unreachable:
            assert_never(unreachable)


def _command_identity(arguments: Sequence[str]) -> tuple[str | None, int]:
    index = 1
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            index += 1
            if index >= len(arguments):
                return None, len(arguments)
            return _DIRECT_COMMANDS.get(Path(arguments[index]).parts[-3:]), index + 1
        if argument == "-m":
            if index + 1 >= len(arguments):
                return None, len(arguments)
            return _MODULE_COMMANDS.get(arguments[index + 1]), index + 2
        if argument in _PYTHON_SWITCHES:
            index += 1
            continue
        if argument in _PYTHON_OPTIONS_WITH_VALUE:
            index += 2
            continue
        if argument.startswith("-X") or argument.startswith("-W"):
            index += 1
            continue
        return _DIRECT_COMMANDS.get(Path(argument).parts[-3:]), index + 1
    return None, len(arguments)


def _rollout_targets(command: str, options: tuple[str, ...]) -> tuple[WriterTarget, ...]:
    if not options or options[0] not in {"prepare", "assess"}:
        return ()
    return (_target(command, _required_option(options[1:], "--output-root")),)


def _extend_targets(command: str, options: tuple[str, ...]) -> tuple[WriterTarget, ...]:
    shards = _option_or_default(options, "--shards-root", "data/curriculum_pddl_shards")
    candidate = _option_or_default(options, "--candidate-root", "/tmp/opencode/curriculum_pddl_candidate_auto")
    targets = [_target(command, shards), _target(command, candidate)]
    if "--update-root" in options:
        targets.append(_target(command, _option_or_default(options, "--final-root", "data/curriculum_pddl")))
    return tuple(targets)


def _data_collect_targets(command: str, options: tuple[str, ...]) -> tuple[WriterTarget, ...]:
    if not options:
        return ()
    subcommand = options[0]
    if subcommand == "generate":
        if "--dry-run" in options:
            return ()
        return (_target(command, _required_option(options[1:], "--output")),)
    if subcommand == "merge-shards":
        return (_target(command, _required_option(options[1:], "--output")),)
    return ()


def _target(command: str, value: str) -> WriterTarget:
    return WriterTarget(command=command, value=value)


def _option_or_default(options: tuple[str, ...], flag: str, default: str) -> str:
    value = _option_value(options, flag)
    return default if value is None else value


def _required_option(options: tuple[str, ...], flag: str) -> str:
    value = _option_value(options, flag)
    if value is None:
        raise WriterDetectionError(f"malformed recognized invocation: missing required {flag}")
    return value


def _option_value(options: tuple[str, ...], flag: str) -> str | None:
    value: str | None = None
    equals_prefix = f"{flag}="
    for index, option in enumerate(options):
        if option.startswith(equals_prefix):
            value = option.removeprefix(equals_prefix)
        elif option == flag:
            if index + 1 >= len(options):
                raise WriterDetectionError(f"malformed recognized invocation: missing value for {flag}")
            value = options[index + 1]
    return value
