from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from multiprocessing.connection import Connection
from multiprocessing.context import SpawnContext
from multiprocessing.process import BaseProcess
from pathlib import Path
from types import ModuleType
from typing import Final, Literal, TypeAlias

from typing_extensions import assert_never

import pytest

from scripts.phase3 import generate_planimation_vlm, pipeline
from scripts.phase3.organize_outputs import apply
from scripts.phase3.output_layout_contracts import DEFAULT_OUTPUT_LAYOUT
from scripts.phase3.output_layout_lock import exclusive_output_layout_lock, shared_output_layout_lock


WriterName: TypeAlias = Literal["planimation", "pipeline"]
EVENT_TIMEOUT_SECONDS: Final = 5.0
BLOCKED_POLL_SECONDS: Final = 0.2


class WriterMutationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class WriterProcess:
    process: BaseProcess
    entered: Connection
    release: Connection


class RecordingLock(AbstractContextManager[None]):
    def __init__(self, repository: Path, events: list[str], repositories: list[Path]) -> None:
        self._repository = repository
        self._events = events
        self._repositories = repositories

    def __enter__(self) -> None:
        self._repositories.append(self._repository)
        self._events.append("acquired")

    def __exit__(self, exception_type, exception, traceback) -> Literal[False]:
        self._events.append("released")
        return False


def writer_module(writer: WriterName) -> ModuleType:
    match writer:
        case "planimation":
            return generate_planimation_vlm
        case "pipeline":
            return pipeline
        case unreachable:
            assert_never(unreachable)


def writer_repository(module: ModuleType) -> Path:
    writer_file = module.__file__
    assert writer_file is not None
    return Path(writer_file).resolve().parents[2]


def patch_pipeline_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    raises_after_reports: bool,
    output_root: Path,
) -> Callable[[], None]:
    def clear_root(_output_root: Path, *, input_root: Path) -> None:
        _ = input_root
        events.append("clear")

    def record_mutation(*_arguments) -> None:
        events.append("write")

    def write_reports(*_arguments) -> dict[str, dict[str, int]]:
        events.append("reports")
        if raises_after_reports:
            raise WriterMutationError()
        return {"summary": {}}

    monkeypatch.setattr(pipeline, "clear_output_root", clear_root)
    monkeypatch.setattr(pipeline, "write_schema_documents", record_mutation)
    monkeypatch.setattr(pipeline, "build_instance_accounting", _empty_rows)
    monkeypatch.setattr(pipeline, "preflight_pddl_features", _empty_rows)
    monkeypatch.setattr(pipeline, "validate_vision_assets", _empty_rows)
    monkeypatch.setattr(pipeline, "run_planner_jobs", _empty_planner_jobs)
    monkeypatch.setattr(pipeline, "write_jsonl", record_mutation)
    monkeypatch.setattr(pipeline, "_write_reports", write_reports)
    return lambda: _generate_pipeline(output_root)


def _empty_rows(*_arguments) -> list[dict[str, str]]:
    return []


def _empty_planner_jobs(*_arguments) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    return [], [], []


def _generate_pipeline(output_root: Path) -> None:
    _ = pipeline.generate_supervised_data(Path("input"), output_root, planners=("gbfs",))


def prepare_organizer_repository(repository: Path) -> Path:
    repository.mkdir(parents=True)
    for index, root in enumerate(DEFAULT_OUTPUT_LAYOUT.protected_roots):
        protected = repository / root.path.value
        protected.mkdir(parents=True)
        _ = (protected / f"protected-{index}.txt").write_text("protected\n", encoding="utf-8")
    for index, relocation in enumerate(DEFAULT_OUTPUT_LAYOUT.relocations):
        source = repository / relocation.source.value
        source.mkdir(parents=True)
        _ = (source / f"payload-{index}.txt").write_text("payload\n", encoding="utf-8")
    for link in DEFAULT_OUTPUT_LAYOUT.view_links:
        target = repository / link.target.value
        target.parent.mkdir(parents=True, exist_ok=True)
        if link.target_kind == "directory":
            target.mkdir(exist_ok=True)
        else:
            _ = target.write_text("approved\n", encoding="utf-8")
    return repository


def run_writer_until_released(
    writer: WriterName,
    repository: Path,
    entered_sender: Connection,
    release_receiver: Connection,
) -> None:
    module = writer_module(writer)
    synthetic_file = repository / "scripts" / "phase3" / f"{module.__name__.rsplit('.', maxsplit=1)[1]}.py"
    original_file = module.__file__
    module.__file__ = str(synthetic_file)
    setattr(module, "shared_output_layout_lock", shared_output_layout_lock)

    def mutation() -> None:
        entered_sender.send(writer)
        if not release_receiver.poll(EVENT_TIMEOUT_SECONDS):
            raise WriterMutationError()
        _ = release_receiver.recv()

    try:
        match writer:
            case "planimation":
                def build_manifest(_roots: list[Path], _output_root: Path, *, config) -> dict[str, dict[str, str]]:
                    _ = config
                    mutation()
                    return {"summary": {}}

                generate_planimation_vlm.build_pairing_manifest = build_manifest
                sys.argv = ["generate_planimation_vlm.py", "--output-root", "unused", "--manifest-only"]
                _ = generate_planimation_vlm.main()
            case "pipeline":
                def clear_root(_output_root: Path, *, input_root: Path) -> None:
                    _ = input_root
                    mutation()

                pipeline.clear_output_root = clear_root
                pipeline.write_schema_documents = _raise_writer_mutation
                with pytest.raises(WriterMutationError):
                    _ = _generate_pipeline(Path("unused"))
            case unreachable:
                assert_never(unreachable)
    finally:
        module.__file__ = original_file
        entered_sender.close()
        release_receiver.close()


def _raise_writer_mutation(_output_root: Path) -> None:
    raise WriterMutationError()


def apply_organizer(repository: Path, completed_sender: Connection, lock_sender: Connection) -> None:
    from scripts.phase3 import organize_outputs

    @contextmanager
    def signaling_exclusive_lock(lock_repository: Path) -> Iterator[None]:
        lock_sender.send("attempting")
        with exclusive_output_layout_lock(lock_repository):
            lock_sender.send("acquired")
            yield

    original_lock = organize_outputs.exclusive_output_layout_lock
    organize_outputs.exclusive_output_layout_lock = signaling_exclusive_lock
    try:
        apply(repository, repository / "outputs/deprecated/phase3/output_reorganization_20260726.json")
        completed_sender.send("complete")
    finally:
        organize_outputs.exclusive_output_layout_lock = original_lock
        completed_sender.close()
        lock_sender.close()


def start_writer(context: SpawnContext, writer: WriterName, repository: Path) -> WriterProcess:
    entered_receiver, entered_sender = context.Pipe(duplex=False)
    release_receiver, release_sender = context.Pipe(duplex=False)
    process = context.Process(target=run_writer_until_released, args=(writer, repository, entered_sender, release_receiver))
    try:
        process.start()
    finally:
        entered_sender.close()
        release_receiver.close()
    return WriterProcess(process, entered_receiver, release_sender)


def cleanup_writer(writer: WriterProcess) -> None:
    try:
        if writer.process.is_alive():
            writer.process.terminate()
        writer.process.join(EVENT_TIMEOUT_SECONDS)
    finally:
        writer.entered.close()
        writer.release.close()
