from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Final

from .cgas_candidate_accounting import (
    accounting_record,
    iter_accounting_slice,
    planner_input_record,
)
from .cgas_candidate_contracts import (
    CandidateConfig,
    CandidateContractError,
    RangeReceipt,
    canonical_json_bytes,
    canonical_json_line,
    load_config,
    sha256,
    validate_range,
)
from .cgas_candidate_publication_fs import PublicationSpec, publish_files
from .cgas_candidate_space import stream_capacity

_RANGE_NAME: Final = re.compile(r"raw-(\d{12})-count-(\d{12})")
_FILES: Final = ("raw-accounting.jsonl", "planner-inputs.jsonl", "receipt.json")


def range_root(output: Path, object_count: int, start_rank: int, count: int) -> Path:
    return (
        output
        / "streams"
        / f"objects-{object_count:02d}"
        / f"raw-{start_rank:012d}-count-{count:012d}"
    )


def _existing_ranges(stream_root: Path) -> tuple[tuple[int, int, Path], ...]:
    if not stream_root.exists():
        return ()
    if not stream_root.is_dir() or stream_root.is_symlink():
        raise CandidateContractError("stale_immutable_artifact", stream_root)
    ranges: list[tuple[int, int, Path]] = []
    for child in stream_root.iterdir():
        if child.name.startswith(".range-stage-"):
            continue
        match = _RANGE_NAME.fullmatch(child.name)
        if match is None or not child.is_dir() or child.is_symlink():
            raise CandidateContractError("stale_immutable_artifact", child)
        start, count = (int(value) for value in match.groups())
        ranges.append((start, count, child))
    return tuple(sorted(ranges))


def _preflight(output: Path, object_count: int, start_rank: int, count: int) -> Path | None:
    stream_root = output / "streams" / f"objects-{object_count:02d}"
    exact: Path | None = None
    end_rank = start_rank + count
    for existing_start, existing_count, path in _existing_ranges(stream_root):
        existing_end = existing_start + existing_count
        if (existing_start, existing_count) == (start_rank, count):
            if (path / _FILES[2]).is_file():
                exact = path
            continue
        if max(existing_start, start_rank) < min(existing_end, end_rank):
            raise CandidateContractError("range_overlap", path)
    return exact


def _expected_lines(
    object_count: int,
    start_rank: int,
    count: int,
) -> Iterator[tuple[bytes, bytes | None, str]]:
    for row, planner in iter_accounting_slice(object_count, start_rank, count):
        yield (
            canonical_json_line(accounting_record(row)),
            canonical_json_line(planner_input_record(planner)) if planner is not None else None,
            row.status,
        )


def _write_lines(path: Path, lines: Iterable[bytes]) -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        for line in lines:
            handle.write(line)
            digest.update(line)
            count += 1
        handle.flush()
        os.fsync(handle.fileno())
    return digest.hexdigest(), count


def _receipt_bytes(receipt: RangeReceipt) -> bytes:
    payload = receipt.record()
    payload["receipt_sha256"] = sha256(canonical_json_bytes(payload))
    return canonical_json_bytes(payload) + b"\n"


def _build_stage(
    stage: Path,
    config: CandidateConfig,
    object_count: int,
    start_rank: int,
    count: int,
) -> RangeReceipt:
    statuses: Counter[str] = Counter()

    def accounting_lines() -> Iterator[bytes]:
        for accounting, _, status in _expected_lines(object_count, start_rank, count):
            statuses[status] += 1
            yield accounting

    accounting_digest, accounting_rows = _write_lines(stage / _FILES[0], accounting_lines())
    planner_digest, planner_rows = _write_lines(
        stage / _FILES[1],
        (
            planner
            for _, planner, _ in _expected_lines(object_count, start_rank, count)
            if planner is not None
        ),
    )
    receipt = RangeReceipt(
        object_count,
        start_rank,
        count,
        start_rank + count,
        stream_capacity(object_count),
        config.sha256,
        accounting_digest,
        planner_digest,
        accounting_rows,
        planner_rows,
        statuses["emitted"],
        statuses["duplicate"],
        statuses["solved"],
    )
    _write_lines(stage / _FILES[2], (_receipt_bytes(receipt),))
    directory = os.open(stage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return receipt


def _parse_receipt(path: Path) -> RangeReceipt:
    try:
        payload = json.loads(path.read_bytes())
        files = payload["files"]
        statuses = payload["status_counts"]
        receipt_digest = payload.pop("receipt_sha256")
        if receipt_digest != sha256(canonical_json_bytes(payload)):
            raise CandidateContractError("artifact_mismatch", path)
        return RangeReceipt(
            payload["object_count"],
            payload["start_rank"],
            payload["count"],
            payload["end_rank"],
            payload["capacity"],
            payload["config_sha256"],
            files["raw-accounting.jsonl"]["sha256"],
            files["planner-inputs.jsonl"]["sha256"],
            files["raw-accounting.jsonl"]["rows"],
            files["planner-inputs.jsonl"]["rows"],
            statuses["emitted"],
            statuses["duplicate"],
            statuses["solved"],
        )
    except (KeyError, OSError, TypeError, json.JSONDecodeError) as error:
        raise CandidateContractError("artifact_mismatch", path) from error


def _verify_existing(
    root: Path,
    config: CandidateConfig,
    object_count: int,
    start_rank: int,
    count: int,
) -> RangeReceipt:
    if set(path.name for path in root.iterdir()) != set(_FILES):
        raise CandidateContractError("artifact_mismatch", root)
    receipt = _parse_receipt(root / _FILES[2])
    accounting_digest = hashlib.sha256()
    planner_digest = hashlib.sha256()
    accounting_rows = 0
    planner_rows = 0
    statuses: Counter[str] = Counter()
    with (root / _FILES[0]).open("rb") as accounting_handle, (root / _FILES[1]).open("rb") as planner_handle:
        for accounting, planner, status in _expected_lines(object_count, start_rank, count):
            if accounting_handle.readline() != accounting:
                raise CandidateContractError("artifact_mismatch", root / _FILES[0])
            accounting_digest.update(accounting)
            accounting_rows += 1
            statuses[status] += 1
            if planner is not None:
                if planner_handle.readline() != planner:
                    raise CandidateContractError("artifact_mismatch", root / _FILES[1])
                planner_digest.update(planner)
                planner_rows += 1
        if accounting_handle.read(1) or planner_handle.read(1):
            raise CandidateContractError("artifact_mismatch", root)
    expected = RangeReceipt(
        object_count,
        start_rank,
        count,
        start_rank + count,
        receipt.capacity,
        config.sha256,
        accounting_digest.hexdigest(),
        planner_digest.hexdigest(),
        accounting_rows,
        planner_rows,
        statuses["emitted"],
        statuses["duplicate"],
        statuses["solved"],
    )
    if receipt != expected:
        raise CandidateContractError("artifact_mismatch", root)
    if (root / _FILES[2]).read_bytes() != _receipt_bytes(expected):
        raise CandidateContractError("artifact_mismatch", root / _FILES[2])
    return receipt


def materialize_slice(
    config_path: Path,
    output: Path,
    object_count: int,
    start_rank: int,
    count: int,
) -> RangeReceipt:
    config = load_config(config_path)
    validate_range(config, object_count, start_rank, count)
    exact = _preflight(output, object_count, start_rank, count)
    if exact is not None:
        return _verify_existing(exact, config, object_count, start_rank, count)
    stream_root = output / "streams" / f"objects-{object_count:02d}"
    stream_root.mkdir(parents=True, mode=0o700, exist_ok=True)
    destination = range_root(output, object_count, start_rank, count)
    with tempfile.TemporaryDirectory(prefix=".range-stage-", dir=stream_root) as temporary:
        stage = Path(temporary)
        receipt = _build_stage(stage, config, object_count, start_rank, count)
        try:
            publish_files(PublicationSpec(stage, destination, _FILES, _FILES[2]))
        except FileExistsError:
            return _verify_existing(destination, config, object_count, start_rank, count)
        return receipt
