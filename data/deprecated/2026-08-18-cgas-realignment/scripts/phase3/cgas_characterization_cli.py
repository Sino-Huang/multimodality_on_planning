from __future__ import annotations

import argparse
import os
import sys
import unicodedata
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Sequence

from .cgas_characterization_assembly import CharacterizationAssemblyError, assemble_characterization_candidate
from .cgas_characterization_command_lock import CommandLockError, command_lock
from .cgas_characterization_final_publication import FinalPublicationError, publish_final_bundle
from .cgas_characterization_runner import RunMode, RunnerError, RunRequest, run
from .cgas_characterization_state_directory import StateDirectoryError, TrustedStateDirectory, open_trusted_state_directory
from .cgas_characterization_verifier import VerificationRequest, verify_characterization
from .cgas_partition_contracts import EXPECTED_ROW_COUNT
from .cgas_serialization import canonical_json_object


class Command(str, Enum):
    FRESH = "fresh"
    SHARD = "shard"
    RESUME = "resume"
    FINALIZE = "finalize"
    VERIFY = "verify"


@dataclass(frozen=True, slots=True)
class CharacterizationCLIError(RuntimeError):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class _Paths:
    repository_root: Path
    source_manifest: Path
    bundle_name: str
    final_path: Path
    private_root: Path

    @property
    def work_root(self) -> Path:
        return self.final_path.with_name(f"{self.bundle_name}.work")


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CharacterizationCLIError(f"invalid_arguments:{message}")


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(description="Run CGAS characterization checkpoints and publish one verified bundle.")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in Command:
        child = commands.add_parser(command.value)
        _common_arguments(child)
        if command in (Command.FRESH, Command.SHARD, Command.RESUME):
            child.add_argument("--shard-count", required=True, type=int)
            child.add_argument("--shard-index", default=0 if command is not Command.SHARD else None, required=command is Command.SHARD, type=int)
        if command is Command.VERIFY:
            child.add_argument("--target", choices=("work", "final"), required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(arguments)
        command = Command(args.command)
        _bundle_name(args.bundle_name)
        with open_trusted_state_directory(args.repository_root.resolve(), create=command is Command.FRESH) as state:
            report = _dispatch(command, args, state)
    except (CharacterizationCLIError, StateDirectoryError, RunnerError, CharacterizationAssemblyError, FinalPublicationError, CommandLockError) as error:
        _terminal({"error": _reason(error), "status": "indeterminate" if _reason(error) == "link_durability_indeterminate" else "error"})
        return 75 if isinstance(error, CommandLockError) else 1
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else 0
    _terminal(report)
    return 1 if report["status"] == "invalid" else 0


def _common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--bundle-name", required=True)
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--module-root", action="append", default=[])
    parser.add_argument("--no-wait", action="store_true")


def _dispatch(command: Command, args: argparse.Namespace, state: TrustedStateDirectory) -> dict[str, object]:
    paths = _paths(command, args, state)
    module_roots = tuple(args.module_root)
    match command:
        case Command.FRESH | Command.SHARD | Command.RESUME:
            mode = RunMode(command.value)
            return _locked_run(paths, module_roots, mode, args.shard_count, args.shard_index, args.no_wait)
        case Command.FINALIZE:
            with command_lock(paths.final_path, exclusive=True, wait=not args.no_wait):
                return _finalize(paths, module_roots, state)
        case Command.VERIFY:
            return _verify(paths, module_roots, args.target)


def _paths(command: Command, args: argparse.Namespace, state: TrustedStateDirectory) -> _Paths:
    repository = args.repository_root.resolve()
    if not repository.is_dir():
        raise CharacterizationCLIError("repository_root_not_directory")
    _bundle_name(args.bundle_name)
    source = _repository_file(args.source_manifest, repository, "source_manifest_not_regular")
    _reject_legacy_roots(repository, args.bundle_name)
    private = state.private_path(_repository_private_path(args.private_root, repository), create=command is Command.FRESH)
    return _Paths(repository, source, args.bundle_name, state.final_path(args.bundle_name), private)


def _repository_file(path: Path, repository: Path, reason: str) -> Path:
    if path.is_symlink():
        raise CharacterizationCLIError(reason)
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(repository)
    except (OSError, ValueError) as error:
        raise CharacterizationCLIError(reason) from error
    if not resolved.is_file():
        raise CharacterizationCLIError(reason)
    return resolved


def _repository_private_path(path: Path, repository: Path) -> Path:
    if any(part == ".." or unicodedata.normalize("NFC", part) != part for part in path.parts):
        raise CharacterizationCLIError("private_root_not_directory")
    candidate = path if path.is_absolute() else repository / path
    try:
        relative = candidate.relative_to(repository)
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(repository)
    except (OSError, ValueError) as error:
        raise CharacterizationCLIError("private_root_outside_state") from error
    current = repository
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise CharacterizationCLIError("private_root_not_directory")
    return resolved


def _bundle_name(value: str) -> None:
    if not value or value in {".", ".."} or "\x00" in value or "/" in value or "\\" in value or Path(value).is_absolute() or Path(value).name != value or unicodedata.normalize("NFC", value) != value:
        raise CharacterizationCLIError("unsafe_bundle_name")


def _reject_legacy_roots(repository: Path, name: str) -> None:
    for legacy in (repository / "tmp" / name, repository / "tmp" / f"{name}.work"):
        try:
            os.lstat(legacy)
        except FileNotFoundError:
            continue
        except OSError as error:
            raise CharacterizationCLIError("legacy_state_root_indeterminate") from error
        raise CharacterizationCLIError("legacy_state_root_present")


def _locked_run(paths: _Paths, roots: tuple[str, ...], mode: RunMode, count: int, index: int, no_wait: bool) -> dict[str, object]:
    with command_lock(paths.final_path, exclusive=True, wait=not no_wait):
        report = run(RunRequest(paths.repository_root, paths.source_manifest, paths.final_path, paths.private_root, count, index, roots), mode)
    return {"bundle_name": paths.bundle_name, "characterized_count": report.characterized_count, "command": mode.value, "status": "ok"}


def _finalize(paths: _Paths, roots: tuple[str, ...], state: TrustedStateDirectory) -> dict[str, object]:
    _require_absent_final(paths.final_path)
    request = VerificationRequest(paths.repository_root, paths.source_manifest, paths.work_root, None, roots)
    work = verify_characterization(request)
    if not work.valid or work.checkpoint_count != EXPECTED_ROW_COUNT:
        raise CharacterizationCLIError("work_not_complete_verified")
    candidate = assemble_characterization_candidate(request, paths.private_root)
    publish_final_bundle(request, candidate.candidate_root, paths.final_path, paths.private_root, state)
    return {"bundle_name": paths.bundle_name, "checkpoint_count": work.checkpoint_count, "command": Command.FINALIZE.value, "status": "ok"}


def _require_absent_final(path: Path) -> None:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return
    except OSError as error:
        raise CharacterizationCLIError("final_entry_indeterminate") from error
    raise CharacterizationCLIError("final_entry_exists")


def _verify(paths: _Paths, roots: tuple[str, ...], target: str) -> dict[str, object]:
    final = paths.final_path if target == "final" else None
    report = verify_characterization(VerificationRequest(paths.repository_root, paths.source_manifest, paths.work_root, final, roots))
    return {"bundle_name": paths.bundle_name, "checkpoint_count": report.checkpoint_count, "command": Command.VERIFY.value, "complete": report.complete, "errors": {str(index): error for index, error in enumerate(report.errors)}, "publishable": report.publishable, "status": "ok" if report.valid else "invalid", "target": target, "valid": report.valid}


def _reason(
    error: CharacterizationCLIError | StateDirectoryError | RunnerError | CharacterizationAssemblyError | FinalPublicationError | CommandLockError,
) -> str:
    match error:
        case CharacterizationAssemblyError(rule=reason) | FinalPublicationError(rule=reason):
            return reason
        case CharacterizationCLIError(reason=reason) | StateDirectoryError(reason=reason) | RunnerError(reason=reason) | CommandLockError(reason=reason):
            return reason


def _terminal(payload: dict[str, object]) -> None:
    print(canonical_json_object(payload).decode(), file=sys.stdout, flush=True)
