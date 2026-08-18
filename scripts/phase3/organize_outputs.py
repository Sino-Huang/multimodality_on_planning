from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import stat
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from .output_layout_contracts import DEFAULT_OUTPUT_LAYOUT, serialize_catalog
from .output_layout_inventory_types import OutputLayoutInventoryError
from .output_layout_journal import OutputLayoutJournalError, digest, journal_path, read_record, write_record
from .output_layout_lock import exclusive_output_layout_lock
from .output_layout_receipt_io import close_descriptor as _close_descriptor
from .output_layout_receipt_io import open_parent_directory as _open_parent_directory
from .output_layout_rename import OutputLayoutRenameError, prepare_destination_parent, rename_noreplace
from .output_layout_snapshot import snapshot_tree
from .output_layout_writer_detection import find_overlapping_writer


CheckpointName = Literal["prepared_persisted", "rename_published", "move_verified", "records_verified"]
Checkpoint = Callable[[CheckpointName], None]
_SIDE_CAR_RECEIPT = Path("outputs/deprecated/phase3/output_reorganization_20260726.json")
_SIDE_CAR_NAMES = (".output_reorganization_20260726.json.txn", ".output_reorganization_20260726.json.swap")
_RECORD_OPEN_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
_open_descriptor = os.open


class OrganizerError(RuntimeError):
    def __init__(self, *, rule: str, path: Path) -> None:
        self.rule = rule
        self.path = path
        super().__init__(f"{rule}: {path}")


class OrganizerCheckpoint(RuntimeError):
    pass


def catalog(repository: Path) -> str:
    _ = repository
    return serialize_catalog(DEFAULT_OUTPUT_LAYOUT)


def apply(repository: Path, *, checkpoint: Checkpoint | CheckpointName | None = None) -> None:
    repository = repository.resolve(strict=True)
    with exclusive_output_layout_lock(repository):
        _validate_inventory(repository)
        if (journal_path(repository) / "complete.json").exists():
            _verify_completed_apply_state(repository)
            return
        _quarantine_sidecars(repository)
        journal = journal_path(repository)
        prepared = _prepared(repository, journal)
        _checkpoint(checkpoint, "prepared_persisted")
        for index, relocation in enumerate(DEFAULT_OUTPUT_LAYOUT.relocations):
            _move(repository, journal, prepared, index, checkpoint)
        _copy_records(repository, journal, checkpoint)
        _validate_completed_inventory(repository)
        _write_once(journal, "complete.json", {"schema_version": 1, "state": "complete"})


def verify(repository: Path) -> None:
    repository = repository.resolve(strict=True)
    with exclusive_output_layout_lock(repository):
        _verify_locked(repository)


def _verify_locked(repository: Path) -> None:
    journal = journal_path(repository)
    complete = _read(journal / "complete.json")
    if complete.get("state") != "complete":
        raise OrganizerError(rule="migration journal is not complete", path=journal)
    prepared = _read(journal / "prepared.json")
    entries = prepared.get("relocations")
    if not isinstance(entries, list) or len(entries) != len(DEFAULT_OUTPUT_LAYOUT.relocations):
        raise OrganizerError(rule="prepared journal has invalid relocations", path=journal)
    for relocation, entry in zip(DEFAULT_OUTPUT_LAYOUT.relocations, entries, strict=True):
        if not isinstance(entry, dict):
            raise OrganizerError(rule="prepared journal has invalid relocation", path=journal)
        source = repository / relocation.source.value
        destination = repository / relocation.destination.value
        if _exists(source):
            raise OrganizerError(rule="source remains after migration", path=source)
        _verify_snapshot(destination, entry.get("snapshot"))
    _verify_records(repository, journal)
    _validate_completed_inventory(repository)


def _verify_completed_apply_state(repository: Path) -> None:
    journal = journal_path(repository)
    complete = _read(journal / "complete.json")
    if complete.get("state") != "complete":
        raise OrganizerError(rule="migration journal is not complete", path=journal)
    entries = _read(journal / "prepared.json").get("relocations")
    if not isinstance(entries, list) or len(entries) != len(DEFAULT_OUTPUT_LAYOUT.relocations):
        raise OrganizerError(rule="prepared journal has invalid relocations", path=journal)
    for relocation, entry in zip(DEFAULT_OUTPUT_LAYOUT.relocations, entries, strict=True):
        if not isinstance(entry, dict):
            raise OrganizerError(rule="prepared journal has invalid relocation", path=journal)
        source = repository / relocation.source.value
        destination = repository / relocation.destination.value
        if _exists(source):
            raise OrganizerError(rule="source remains after migration", path=source)
        try:
            destination_status = destination.lstat()
        except OSError as error:
            raise OrganizerError(rule="completed destination is unavailable", path=destination) from error
        if not stat.S_ISDIR(destination_status.st_mode):
            raise OrganizerError(rule="completed destination is not a real directory", path=destination)
    _verify_records(repository, journal)
    _validate_completed_inventory(repository)


def _prepared(repository: Path, journal: Path) -> dict[str, object]:
    path = journal / "prepared.json"
    if path.exists():
        return _read(path)
    records: list[dict[str, object]] = []
    for relocation in DEFAULT_OUTPUT_LAYOUT.relocations:
        source = repository / relocation.source.value
        _reject_writer(source)
        records.append({"source": relocation.source.value, "destination": relocation.destination.value, "snapshot": snapshot_tree(source).to_record()})
    record: dict[str, object] = {"schema_version": 1, "state": "prepared", "relocations": records}
    _write_once(journal, "prepared.json", record)
    return record


def _move(repository: Path, journal: Path, prepared: dict[str, object], index: int, checkpoint: Checkpoint | CheckpointName | None) -> None:
    relocation = DEFAULT_OUTPUT_LAYOUT.relocations[index]
    entries = prepared["relocations"]
    if not isinstance(entries, list) or not isinstance(entries[index], dict):
        raise OrganizerError(rule="prepared journal has invalid relocation", path=journal)
    expected = entries[index].get("snapshot")
    source = repository / relocation.source.value
    destination = repository / relocation.destination.value
    marker = journal / f"move-{index:02d}.json"
    if marker.exists():
        if _exists(source):
            raise OrganizerError(rule="moved journal entry still has source", path=source)
        _verify_snapshot(destination, expected)
        return
    if _exists(source):
        _verify_snapshot(source, expected)
        _reject_writer(source)
        try:
            prepare_destination_parent(source, destination)
            rename_noreplace(source, destination)
        except OutputLayoutRenameError as error:
            raise OrganizerError(rule=error.rule, path=destination) from error
        _checkpoint(checkpoint, "rename_published")
    _verify_snapshot(destination, expected)
    _write_once(journal, marker.name, {"schema_version": 1, "index": index, "state": "moved", "snapshot": expected})
    _checkpoint(checkpoint, "move_verified")


def _copy_records(repository: Path, journal: Path, checkpoint: Checkpoint | CheckpointName | None) -> None:
    marker = journal / "records.json"
    if marker.exists():
        _verify_records(repository, journal)
        return
    entries: list[dict[str, object]] = []
    for copy in DEFAULT_OUTPUT_LAYOUT.physical_record_copies:
        source = repository / copy.source.value
        destination = repository / copy.destination.value
        source_meta = _record_metadata(source)
        if _exists(destination):
            if _record_metadata(destination) != source_meta:
                raise OrganizerError(rule="record copy differs from canonical source", path=destination)
        else:
            _copy_file(source, destination, source_meta)
            if _record_metadata(destination) != source_meta:
                raise OrganizerError(rule="record copy verification failed", path=destination)
        entries.append({"source": copy.source.value, "destination": copy.destination.value, "metadata": source_meta})
    _write_once(journal, "records.json", {"schema_version": 1, "records": entries})
    _checkpoint(checkpoint, "records_verified")


def _verify_records(repository: Path, journal: Path) -> None:
    record = _read(journal / "records.json")
    entries = record.get("records")
    if not isinstance(entries, list) or len(entries) != len(DEFAULT_OUTPUT_LAYOUT.physical_record_copies):
        raise OrganizerError(rule="record journal has invalid entries", path=journal)
    for copy, entry in zip(DEFAULT_OUTPUT_LAYOUT.physical_record_copies, entries, strict=True):
        if not isinstance(entry, dict):
            raise OrganizerError(rule="record journal entry is invalid", path=journal)
        source = repository / copy.source.value
        destination = repository / copy.destination.value
        metadata = entry.get("metadata")
        if _record_metadata(source) != metadata or _record_metadata(destination) != metadata:
            raise OrganizerError(rule="record copy verification failed", path=destination)


def _quarantine_sidecars(repository: Path) -> None:
    source_directory = repository / "outputs/deprecated/phase3"
    sources = tuple(source_directory / name for name in _SIDE_CAR_NAMES)
    destination_directory = repository / "outputs/deprecated/receipts/failed-output-reorganization-20260726"
    destinations = tuple(destination_directory / name for name in _SIDE_CAR_NAMES)
    if not any(source.exists() for source in sources) and not any(destination.exists() for destination in destinations):
        return
    if all(destination.exists() for destination in destinations) and not any(source.exists() for source in sources):
        return
    if not all(source.exists() for source in sources) or any(destination.exists() for destination in destinations):
        raise OrganizerError(rule="sidecar recovery state is ambiguous", path=source_directory)
    transaction = _sidecar_json(sources[0])
    swap_digest, swap_size = digest(sources[1])
    if transaction.get("canonical_sha256") != swap_digest or transaction.get("canonical_size") != swap_size or transaction.get("swap_name") != _SIDE_CAR_NAMES[1] or (repository / _SIDE_CAR_RECEIPT).exists():
        raise OrganizerError(rule="failed receipt sidecars are invalid", path=source_directory)
    for source, destination in zip(sources, destinations, strict=True):
        try:
            prepare_destination_parent(source, destination)
            _rename_regular_file(source, destination)
        except OSError as error:
            raise OrganizerError(rule="sidecar quarantine rename failed", path=destination) from error
    _write_once(destination_directory, "recovery.json", {"schema_version": 1, "state": "quarantined", "transaction_sha256": digest(destinations[0])[0], "swap_sha256": swap_digest})


def _sidecar_json(path: Path) -> dict[str, object]:
    try:
        status = path.lstat()
        if not stat.S_ISREG(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o600:
            raise OrganizerError(rule="sidecar must be a mode-0600 regular file", path=path)
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise OrganizerError(rule="sidecar is not valid JSON", path=path) from error
    if not isinstance(value, dict):
        raise OrganizerError(rule="sidecar transaction is invalid", path=path)
    return value


def _record_metadata(path: Path) -> dict[str, object]:
    hasher = hashlib.sha256()
    size = 0
    lines = 0
    try:
        with _open_regular_record(path) as descriptor, os.fdopen(descriptor, "rb", closefd=False) as handle:
            for line in handle:
                hasher.update(line)
                size += len(line)
                json.loads(line.decode("utf-8"))
                lines += 1
    except OrganizerError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OrganizerError(rule="record JSONL is invalid", path=path) from error
    return {"sha256": hasher.hexdigest(), "bytes": size, "lines": lines}


def _copy_file(source: Path, destination: Path, expected_metadata: dict[str, object]) -> None:
    try:
        prepare_destination_parent(source, destination)
    except OutputLayoutRenameError as error:
        raise OrganizerError(rule=error.rule, path=destination) from error
    temporary = destination.parent / f".{destination.name}.copy-{secrets.token_hex(16)}"
    try:
        with _open_regular_record(source) as descriptor, os.fdopen(descriptor, "rb", closefd=False) as input_handle, temporary.open("xb") as output_handle:
            os.chmod(temporary, 0o600)
            while chunk := input_handle.read(1024 * 1024):
                output_handle.write(chunk)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        if _record_metadata(temporary) != expected_metadata:
            raise OrganizerError(rule="record source changed during copy", path=source)
        if _exists(destination):
            raise OrganizerError(rule="record copy destination collision", path=destination)
        parent_descriptor = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            try:
                os.link(
                    temporary.name,
                    destination.name,
                    src_dir_fd=parent_descriptor,
                    dst_dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
            except FileExistsError as error:
                raise OrganizerError(rule="record copy destination collision", path=destination) from error
            os.fsync(parent_descriptor)
            os.unlink(temporary.name, dir_fd=parent_descriptor)
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
    except (OSError, OrganizerError) as error:
        if temporary.exists():
            temporary.unlink()
        if isinstance(error, OrganizerError):
            raise
        raise OrganizerError(rule="unable to copy record", path=destination) from error


@contextmanager
def _open_regular_record(path: Path) -> Iterator[int]:
    parent_descriptor: int | None = None
    descriptor: int | None = None
    try:
        try:
            parent_descriptor = _open_parent_directory(path.parent)
            descriptor = _open_descriptor(path.name, _RECORD_OPEN_FLAGS, dir_fd=parent_descriptor)
            opened = os.fstat(descriptor)
        except (OSError, OutputLayoutInventoryError) as error:
            raise OrganizerError(rule="record must be a regular file", path=path) from error
        if not stat.S_ISREG(opened.st_mode):
            raise OrganizerError(rule="record must be a regular file", path=path)
        yield descriptor
    finally:
        close_error: OutputLayoutInventoryError | None = None
        if descriptor is not None:
            try:
                _close_descriptor(descriptor, f"unable to close record descriptor: {path}")
            except OutputLayoutInventoryError as error:
                close_error = error
        if parent_descriptor is not None:
            try:
                _close_descriptor(parent_descriptor, f"unable to close record parent: {path.parent}")
            except OutputLayoutInventoryError as error:
                if close_error is None:
                    close_error = error
        if close_error is not None:
            raise OrganizerError(rule="unable to close record", path=path) from close_error


def _rename_regular_file(source: Path, destination: Path) -> None:
    source_status = source.lstat()
    if not stat.S_ISREG(source_status.st_mode) or stat.S_IMODE(source_status.st_mode) != 0o600:
        raise OrganizerError(rule="sidecar must be a mode-0600 regular file", path=source)
    if _exists(destination):
        raise OrganizerError(rule="sidecar quarantine destination collision", path=destination)
    source_parent = os.open(source.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    destination_parent = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        if os.fstat(source_parent).st_dev != os.fstat(destination_parent).st_dev:
            raise OrganizerError(rule="sidecar quarantine crosses filesystems", path=destination)
        if _exists(destination):
            raise OrganizerError(rule="sidecar quarantine destination collision", path=destination)
        os.rename(source.name, destination.name, src_dir_fd=source_parent, dst_dir_fd=destination_parent)
        os.fsync(source_parent)
        if source_parent != destination_parent:
            os.fsync(destination_parent)
    finally:
        os.close(destination_parent)
        os.close(source_parent)


def _validate_inventory(repository: Path) -> None:
    outputs = repository / "outputs"
    allowed = {Path(relocation.source.value).name for relocation in DEFAULT_OUTPUT_LAYOUT.relocations} | {"reasoning_traces", "image_frames", "deprecated"}
    try:
        names = {entry.name for entry in outputs.iterdir()}
    except OSError as error:
        raise OrganizerError(rule="outputs root cannot be listed", path=outputs) from error
    if "deprecated" not in names or names - allowed:
        unexpected = sorted((names - allowed) or {"deprecated"})
        raise OrganizerError(rule="outputs root does not match migration state", path=outputs / unexpected[0])


def _validate_completed_inventory(repository: Path) -> None:
    _validate_names(repository / "outputs", {"reasoning_traces", "image_frames", "deprecated"})


def _validate_names(outputs: Path, expected: set[str]) -> None:
    try:
        names = {entry.name for entry in outputs.iterdir()}
    except OSError as error:
        raise OrganizerError(rule="outputs root cannot be listed", path=outputs) from error
    if names != expected:
        unexpected = sorted(names ^ expected)
        raise OrganizerError(rule="outputs root does not match migration state", path=outputs / unexpected[0])


def _verify_snapshot(path: Path, expected: object) -> None:
    if not isinstance(expected, dict) or snapshot_tree(path).to_record() != expected:
        raise OrganizerError(rule="tree differs from prepared snapshot", path=path)


def _reject_writer(path: Path) -> None:
    overlap = find_overlapping_writer(path)
    if overlap is not None:
        raise OrganizerError(rule=f"active writer {overlap.pid} overlaps source", path=path)


def _write_once(directory: Path, name: str, record: dict[str, object]) -> None:
    try:
        write_record(directory, name, record)
    except OutputLayoutJournalError as error:
        raise OrganizerError(rule=error.rule, path=error.path) from error


def _read(path: Path) -> dict[str, object]:
    try:
        return read_record(path)
    except OutputLayoutJournalError as error:
        raise OrganizerError(rule=error.rule, path=error.path) from error


def _exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _checkpoint(checkpoint: Checkpoint | CheckpointName | None, name: CheckpointName) -> None:
    if checkpoint == name:
        raise OrganizerCheckpoint(name)
    if callable(checkpoint):
        checkpoint(name)


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely organize VLM outputs.")
    parser.add_argument("command", choices=("catalog", "apply", "verify"))
    parser.add_argument("--repo-root", required=True, type=Path)
    namespace = parser.parse_args(arguments)
    try:
        repository = namespace.repo_root.resolve(strict=True)
        if namespace.command == "catalog":
            print(catalog(repository), end="")
        elif namespace.command == "apply":
            apply(repository)
            print(json.dumps({"command": "apply", "ok": True}, sort_keys=True))
        else:
            verify(repository)
            print(json.dumps({"command": "verify", "ok": True}, sort_keys=True))
    except OrganizerError as error:
        print(json.dumps({"error": error.rule, "ok": False}, sort_keys=True), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
