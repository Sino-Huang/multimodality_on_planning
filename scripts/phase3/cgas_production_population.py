from __future__ import annotations

import argparse
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Sequence

from pydantic import TypeAdapter

from .cgas_candidate_characterization_contracts import (
    CandidateCharacterizationError,
    canonical_bytes,
    sha256,
)
from .cgas_candidate_characterization_models import JsonObject, JsonValue
from .cgas_partition_selection import (
    Selection,
    SelectionFeasibilityError,
    select_rows,
)
from .cgas_production_population_contracts import diagnostics, load_population_input
from .cgas_production_population_manifest import accepted_manifest as _accepted_manifest

_MANIFEST_NAME: Final = "accepted_manifest.jsonl"


@dataclass(frozen=True, slots=True)
class PopulationRequest:
    repository_root: Path
    checkpoint: Path | None
    checkpoint_index: Path | None
    output: Path


@dataclass(frozen=True, slots=True)
class PopulationReport:
    result: Path
    record: JsonObject
    read_only: bool


def run(request: PopulationRequest) -> PopulationReport:
    repository = request.repository_root.resolve()
    population = load_population_input(repository, request.checkpoint, request.checkpoint_index)
    checkpoint = population.checkpoint
    rows = population.rows
    selector_diagnostics = diagnostics(population)
    non_exhausted: list[JsonValue] = [
        int(stream.object_count) for stream in checkpoint.streams if not stream.exhausted
    ]
    manifest_contents: bytes | None = None
    try:
        selection = _select_rows(rows)
        manifest_contents = _accepted_manifest(rows, selection.records)
        manifest_digest = sha256(manifest_contents)
        raw_record: JsonObject = {
            "accepted_manifest_sha256": manifest_digest,
            "checkpoint_sha256": population.digest,
            "diagnostics": selector_diagnostics,
            "non_exhausted_streams": non_exhausted,
            "reservoir_sha256": checkpoint.reservoir.sha256,
            "round": checkpoint.round,
            "schema_version": "cgas_production_selector_attempt_v1",
            "selector_config_sha256": checkpoint.selector.config_sha256,
            "selector_implementation_sha256": checkpoint.selector.implementation_sha256,
            "status": "selector_feasible",
        }
        record = _json_object(raw_record)
    except SelectionFeasibilityError as error:
        raw_record = {
            "checkpoint_sha256": population.digest,
            "diagnostics": selector_diagnostics,
            "non_exhausted_streams": non_exhausted,
            "reason": error.reason,
            "reservoir_sha256": checkpoint.reservoir.sha256,
            "round": checkpoint.round,
            "schema_version": "cgas_production_selector_attempt_v1",
            "selector_config_sha256": checkpoint.selector.config_sha256,
            "selector_implementation_sha256": checkpoint.selector.implementation_sha256,
            "status": "selector_infeasible",
        }
        record = _json_object(raw_record)
    result = request.output / f"selector_attempt_{checkpoint.round:06d}.json"
    return _publish(request.output, result, record, manifest_contents)


def _select_rows(rows: tuple[JsonObject, ...]) -> Selection:
    selector_rows = TypeAdapter(Sequence[dict[str, object]]).validate_python(rows)  # noqa: RUF100  # noqa: OBJECT_OK
    return select_rows(selector_rows)


def _publish(
    output: Path,
    result: Path,
    record: JsonObject,
    manifest_contents: bytes | None,
) -> PopulationReport:
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    if output.is_symlink() or not stat.S_ISDIR(output.lstat().st_mode):
        raise CandidateCharacterizationError("output_directory_invalid", output)
    expected_names = {result.name}
    if manifest_contents is not None:
        expected_names.add(_MANIFEST_NAME)
    for path in output.iterdir():
        if path.name.startswith("selector_attempt_") and path.name not in expected_names:
            raise CandidateCharacterizationError("selector_result_path_invalid", path)
    result_contents = canonical_bytes(record) + b"\n"
    manifest = output / _MANIFEST_NAME
    if result.exists():
        if result.is_symlink() or result.read_bytes() != result_contents:
            raise CandidateCharacterizationError("selector_result_collision", result)
        if manifest_contents is None:
            if manifest.exists():
                raise CandidateCharacterizationError("accepted_manifest_unexpected", manifest)
        elif manifest.is_symlink() or not manifest.is_file() or manifest.read_bytes() != manifest_contents:
            raise CandidateCharacterizationError("accepted_manifest_binding_invalid", manifest)
        return PopulationReport(result, record, True)
    if manifest.exists():
        raise CandidateCharacterizationError("accepted_manifest_unexpected", manifest)
    if manifest_contents is not None:
        _publish_once(manifest, manifest_contents)
    try:
        _publish_once(result, result_contents)
    except CandidateCharacterizationError:
        if manifest_contents is not None:
            manifest.unlink(missing_ok=True)
        raise
    return PopulationReport(result, record, False)


def _publish_once(path: Path, contents: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path, follow_symlinks=False)
    except (FileExistsError, OSError) as error:
        raise CandidateCharacterizationError("immutable_publication_failed", path) from error
    finally:
        temporary.unlink(missing_ok=True)


def _json_object(value: JsonObject) -> JsonObject:
    return TypeAdapter(JsonObject).validate_python(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--checkpoint", type=Path)
    source.add_argument("--checkpoint-index", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json", action="store_true", required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    try:
        report = run(PopulationRequest(Path.cwd(), args.checkpoint, args.checkpoint_index, args.output))
    except CandidateCharacterizationError as error:
        print(json.dumps({"error": error.code}, sort_keys=True))
        return 2
    payload = {**report.record, "read_only": report.read_only, "result_path": report.result.as_posix()}
    print(json.dumps(payload, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
