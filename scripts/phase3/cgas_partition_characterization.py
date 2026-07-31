from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Final, Sequence

from src.data_collect.metadata import AcceptedInstanceMetadata

from .cgas_bfs import run_fifo_bfs
from .cgas_characterization_rows import (
    CHARACTERIZATION_LIMITS,
    _base_row,
    _planner_record,
    canonical_composition_signature,
    failure_row as _failure_row,
    success_row as _success_row,
    write_characterization as _write_characterization,
)
from .cgas_partition_contracts import (
    CharacterizationContractError,
    CharacterizationInput,
    assert_expected_population,
)
from .local_iw import run_iterated_width
from .local_planner_types import LocalPlannerRequest
from .pddl import PDDLError, ground_actions, parse_task


DEFAULT_SOURCE_MANIFEST: Final = Path("data/curriculum_pddl/accepted_manifest.jsonl")

__all__ = (
    "CHARACTERIZATION_LIMITS",
    "CharacterizationInput",
    "_base_row",
    "_failure_row",
    "_planner_record",
    "_success_row",
    "build_characterization",
    "build_parser",
    "canonical_composition_signature",
    "characterize_instances",
    "load_accepted_blocksworld",
    "main",
    "write_characterization",
)


def build_parser() -> argparse.ArgumentParser:
    from .cgas_characterization_cli import build_parser as build_lifecycle_parser

    return build_lifecycle_parser()


def load_accepted_blocksworld(source_manifest: Path) -> tuple[CharacterizationInput, ...]:
    """Parse the repository accepted-row schema and retain only Blocksworld identities."""
    source_bytes = source_manifest.read_bytes()
    records: list[CharacterizationInput] = []
    for raw_line in source_bytes.splitlines():
        if not raw_line:
            continue
        payload = json.loads(raw_line)
        if not isinstance(payload, dict):
            raise CharacterizationContractError("source_row_not_object")
        metadata = AcceptedInstanceMetadata.from_dict(payload)
        if metadata.domain_id == "blocksworld":
            records.append(
                CharacterizationInput(
                    metadata.instance_id,
                    metadata.split,
                    Path(metadata.domain_path),
                    Path(metadata.problem_path),
                    hashlib.sha256(raw_line).hexdigest(),
                )
            )
    return tuple(sorted(records, key=lambda row: row.instance_id))


def characterize_instances(inputs: Sequence[CharacterizationInput]) -> list[dict[str, object]]:
    """Characterize supplied local PDDL instances in canonical identity order."""
    rows = [_characterize(instance) for instance in sorted(inputs, key=lambda row: row.instance_id)]
    if len({str(row["instance_id"]) for row in rows}) != len(rows):
        raise CharacterizationContractError("duplicate_instance_id")
    return rows


def build_characterization(source_manifest: Path, output_root: Path) -> Path:
    """Build the complete accepted-row characterization artifact at an explicit local root."""
    inputs = load_accepted_blocksworld(source_manifest)
    rows = characterize_instances(inputs)
    assert_expected_population(rows)
    return write_characterization(rows, output_root)


def write_characterization(rows: Sequence[dict[str, object]], output_root: Path) -> Path:
    return _write_characterization(rows, output_root, implementation_module=Path(__file__))


def _characterize(instance: CharacterizationInput) -> dict[str, object]:
    try:
        task = parse_task(instance.domain_path, instance.problem_path)
        if task.unsupported_features:
            return _failure_row(instance, "unsupported_pddl", task=task)
        grounded, grounding_status = ground_actions(
            task,
            max_grounded_actions=CHARACTERIZATION_LIMITS["max_grounded_actions"],
            max_grounded_atoms=CHARACTERIZATION_LIMITS["max_grounded_atoms"],
        )
        if grounding_status is not None:
            return _failure_row(instance, grounding_status, task=task)
        bfs = run_fifo_bfs(task, tuple(grounded), CHARACTERIZATION_LIMITS)
        iw = run_iterated_width(
            LocalPlannerRequest("iw", task, tuple(grounded), CHARACTERIZATION_LIMITS)
        )
        return _success_row(
            instance,
            task,
            grounded,
            bfs.plan,
            bfs.trace,
            bfs.status,
            iw.plan,
            iw.trace,
            iw.status,
        )
    except (OSError, PDDLError, json.JSONDecodeError) as error:
        return _failure_row(instance, f"pddl_error:{type(error).__name__}")


def main(arguments: Sequence[str] | None = None) -> int:
    from .cgas_characterization_cli import main as lifecycle_main

    return lifecycle_main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
