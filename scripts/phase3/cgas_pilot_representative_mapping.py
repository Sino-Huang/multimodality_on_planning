from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from .cgas_candidate_accounting import PlannerInput, planner_input_record
from .cgas_candidate_space import build_candidate
from .cgas_pilot_expansion_index import publish_once, state_sha256

POLICY_ID = "replay_then_held_out_then_stable_source_v1"
SCHEMA_VERSION = "cgas_phase3_pilot_representative_mapping_v1"
REPORT_SCHEMA_VERSION = "cgas_phase3_pilot_representative_mapping_report_v1"
MAPPING_NAME = "representative-source-mapping.jsonl"
REPORT_NAME = "representative-source-mapping-report.json"
PRODUCTION_REQUEST_SHA256 = "13db7cba5fb1cf885bd203ff657e5c7714bda6f832c5970dbfe5a9dee36d0585"
PRODUCTION_REQUEST_COUNT = 16_822
PRODUCTION_INDEX_SHA256 = "46d1e7c1c0a6a133372782e691888840a74f3d3732dd625b5e2d8611fdf5d390"
PRODUCTION_INDEX_COUNT = 31_171

JsonObject: TypeAlias = dict[str, object]


@dataclass(frozen=True, slots=True)
class RepresentativeMappingError(RuntimeError):
    rule: str
    path: Path | None = None

    def __str__(self) -> str:
        return self.rule if self.path is None else f"{self.rule}: {self.path}"


@dataclass(frozen=True, slots=True)
class RepresentativeMappingResult:
    mapping_path: Path
    report_path: Path
    mapping_sha256: str
    report_sha256: str
    count: int


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise RepresentativeMappingError("representative_input_read_failed", path) from error
    return digest.hexdigest()


def _jsonl_snapshot(path: Path) -> tuple[list[JsonObject], str]:
    try:
        payload = path.read_bytes()
        text = payload.decode("utf-8")
        rows: list[JsonObject] = []
        for line in text.splitlines():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise RepresentativeMappingError("representative_jsonl_record_invalid", path)
            rows.append(dict(value))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RepresentativeMappingError("representative_jsonl_read_failed", path) from error
    return rows, hashlib.sha256(payload).hexdigest()


def _text(row: Mapping[str, object], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise RepresentativeMappingError(f"representative_invalid_text:{field}")
    return value


def _integer(row: Mapping[str, object], field: str) -> int:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RepresentativeMappingError(f"representative_invalid_integer:{field}")
    return value


def _strings(row: Mapping[str, object], field: str) -> list[str]:
    value = row.get(field)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RepresentativeMappingError(f"representative_invalid_string_array:{field}")
    return list(value)


def _digest(row: Mapping[str, object], field: str) -> str:
    value = _text(row, field)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise RepresentativeMappingError(f"representative_invalid_digest:{field}")
    return value


def _validate_binding(
    path: Path,
    rows: Sequence[JsonObject],
    digest: str,
    expected_sha256: str | None,
    expected_count: int | None,
    kind: str,
) -> str:
    if expected_sha256 is not None and digest != expected_sha256:
        raise RepresentativeMappingError(f"representative_{kind}_sha256_mismatch", path)
    if expected_count is not None and len(rows) != expected_count:
        raise RepresentativeMappingError(f"representative_{kind}_count_mismatch", path)
    return digest


def _validate_request(rows: Sequence[JsonObject]) -> list[JsonObject]:
    result: list[JsonObject] = []
    seen: dict[str, list[str]] = {}
    for row in rows:
        atoms = _strings(row, "state_atoms")
        digest = _digest(row, "state_sha256")
        if len(set(atoms)) != len(atoms):
            raise RepresentativeMappingError("representative_request_state_atoms_noncanonical")
        if atoms != sorted(atoms) or state_sha256(atoms) != digest:
            raise RepresentativeMappingError("representative_request_state_mismatch")
        partitions = _strings(row, "partitions")
        if partitions != sorted(set(partitions)):
            raise RepresentativeMappingError("representative_request_partitions_noncanonical")
        prior = seen.get(digest)
        if prior is not None:
            if prior != atoms:
                raise RepresentativeMappingError("representative_request_state_collision")
            raise RepresentativeMappingError("representative_request_state_duplicate")
        seen[digest] = atoms
        result.append({"state_atoms": atoms, "state_sha256": digest, "partitions": partitions})
    return result


def _validate_source(row: Mapping[str, object]) -> JsonObject:
    if row.get("schema_version") != "cgas_phase3_pilot_expansion_index_v1":
        raise RepresentativeMappingError("representative_source_schema_unsupported")
    atoms = _strings(row, "state_atoms")
    digest = _digest(row, "state_sha256")
    if atoms != sorted(atoms) or state_sha256(atoms) != digest:
        raise RepresentativeMappingError("representative_source_state_mismatch")
    object_count = _integer(row, "object_count")
    raw_rank = _integer(row, "raw_rank")
    candidate_id = _text(row, "candidate_id")
    if _text(row, "instance_id") != candidate_id:
        raise RepresentativeMappingError("representative_source_instance_mismatch")
    candidate = build_candidate(object_count, raw_rank)
    if candidate.candidate_id != candidate_id:
        raise RepresentativeMappingError("representative_source_candidate_mismatch")
    planner_input = PlannerInput(
        object_count,
        raw_rank,
        "emitted",
        candidate.candidate_id,
        raw_rank,
        candidate,
    )
    expected_source_digest = hashlib.sha256(_canonical_bytes(planner_input_record(planner_input))).hexdigest()
    if _digest(row, "source_record_sha256") != expected_source_digest:
        raise RepresentativeMappingError("representative_source_record_mismatch")
    role = _text(row, "role")
    planner = _text(row, "planner")
    if role not in {"train", "held_out_calibration"}:
        raise RepresentativeMappingError("representative_source_role_unsupported")
    if planner not in {"bfs", "iw"}:
        raise RepresentativeMappingError("representative_source_planner_unsupported")
    row_id = _text(row, "row_id")
    event_sequence = _integer(row, "event_sequence")
    _digest(row, "event_sha256")
    _text(row, "trace_path")
    _digest(row, "trace_stream_sha256")
    _text(row, "trace_contract_id")
    _digest(row, "trace_contract_sha256")
    replay = row.get("replay_plan_member")
    if not isinstance(replay, bool):
        raise RepresentativeMappingError("representative_source_replay_flag_invalid")
    replay_step = row.get("replay_step_index")
    if replay and (isinstance(replay_step, bool) or not isinstance(replay_step, int) or replay_step < 0):
        raise RepresentativeMappingError("representative_source_replay_step_invalid")
    if not replay and replay_step is not None:
        raise RepresentativeMappingError("representative_source_replay_step_invalid")
    return {
        "candidate_id": candidate_id,
        "event_sequence": event_sequence,
        "event_sha256": row["event_sha256"],
        "instance_id": candidate_id,
        "object_count": object_count,
        "planner": planner,
        "raw_rank": raw_rank,
        "replay_plan_member": replay,
        "replay_step_index": replay_step,
        "role": role,
        "row_id": row_id,
        "source_record_sha256": expected_source_digest,
        "state_atoms": atoms,
        "state_sha256": digest,
        "trace_contract_id": row["trace_contract_id"],
        "trace_contract_sha256": row["trace_contract_sha256"],
        "trace_path": row["trace_path"],
        "trace_stream_sha256": row["trace_stream_sha256"],
    }


def _selection_key(row: Mapping[str, object]) -> tuple[object, ...]:
    role_order = {"held_out_calibration": 0, "train": 1}
    planner_order = {"bfs": 0, "iw": 1}
    return (
        0 if row["replay_plan_member"] is True else 1,
        role_order[str(row["role"])],
        _integer(row, "raw_rank"),
        str(row["candidate_id"]),
        planner_order[str(row["planner"])],
        _integer(row, "event_sequence"),
        str(row["row_id"]),
    )


def _implementation_sha256() -> str:
    return _file_sha256(Path(__file__).resolve())


def _preflight_publication(path: Path, payload: bytes) -> None:
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != payload:
            from .cgas_pilot_expansion_index import PilotExpansionIndexError

            raise PilotExpansionIndexError("pilot_expansion_publication_collision", path)


def build_representative_mapping(
    request_path: Path,
    expansion_index_path: Path,
    output_root: Path,
    *,
    expected_request_sha256: str | None = None,
    expected_request_count: int | None = None,
    expected_index_sha256: str | None = None,
    expected_index_count: int | None = None,
) -> RepresentativeMappingResult:
    raw_request_rows, request_snapshot_digest = _jsonl_snapshot(request_path)
    index_rows, index_snapshot_digest = _jsonl_snapshot(expansion_index_path)
    request_rows = _validate_request(raw_request_rows)
    request_digest = _validate_binding(
        request_path,
        request_rows,
        request_snapshot_digest,
        expected_request_sha256,
        expected_request_count,
        "request",
    )
    index_digest = _validate_binding(
        expansion_index_path,
        index_rows,
        index_snapshot_digest,
        expected_index_sha256,
        expected_index_count,
        "index",
    )
    requested = {str(row["state_sha256"]): row for row in request_rows}
    groups: dict[str, list[JsonObject]] = defaultdict(list)
    first_row_ids: dict[str, str] = {}
    for source_row in index_rows:
        source = _validate_source(source_row)
        digest = str(source["state_sha256"])
        if digest not in requested:
            continue
        if source["state_atoms"] != requested[digest]["state_atoms"]:
            raise RepresentativeMappingError("representative_source_state_collision")
        groups[digest].append(source)
        first_row_ids.setdefault(digest, str(source["row_id"]))

    implementation_digest = _implementation_sha256()
    bindings = {
        "expansion_index_count": len(index_rows),
        "expansion_index_sha256": index_digest,
        "request_count": len(request_rows),
        "request_sha256": request_digest,
    }
    mapping_rows: list[JsonObject] = []
    selected_rows: list[JsonObject] = []
    selections_differing_from_first = 0
    for request_row in request_rows:
        digest = str(request_row["state_sha256"])
        candidates = groups.get(digest, [])
        if not candidates:
            raise RepresentativeMappingError("representative_source_missing")
        selected = min(candidates, key=_selection_key)
        tied = [candidate for candidate in candidates if _selection_key(candidate) == _selection_key(selected)]
        if any(candidate != selected for candidate in tied[1:]):
            raise RepresentativeMappingError("representative_selection_key_collision")
        selected_rows.append(selected)
        if selected["row_id"] != first_row_ids[digest]:
            selections_differing_from_first += 1
        mapping_rows.append(
            {
                "bindings": bindings,
                "generator_implementation_sha256": implementation_digest,
                "partitions": request_row["partitions"],
                "representative": selected,
                "schema_version": SCHEMA_VERSION,
                "selection": {
                    "candidate_count": len(candidates),
                    "policy_id": POLICY_ID,
                    "selection_key": list(_selection_key(selected)),
                },
                "state_atoms": request_row["state_atoms"],
                "state_sha256": digest,
            }
        )

    mapping_payload = b"".join(_canonical_bytes(row) for row in mapping_rows)
    mapping_digest = hashlib.sha256(mapping_payload).hexdigest()
    mapping_path = output_root / MAPPING_NAME
    report_path = output_root / REPORT_NAME

    duplicate_groups = [rows for rows in groups.values() if len(rows) > 1]
    report: JsonObject = {
        "bindings": bindings,
        "distinct_goal_ambiguity_count": sum(
            len({build_candidate(_integer(row, "object_count"), _integer(row, "raw_rank")).goal_atoms for row in rows})
            > 1
            for rows in duplicate_groups
        ),
        "generator_implementation_sha256": implementation_digest,
        "group_statistics": {
            "cross_role_count": sum(len({row["role"] for row in rows}) > 1 for rows in duplicate_groups),
            "duplicate_count": len(duplicate_groups),
            "maximum_group_size": max((len(rows) for rows in groups.values()), default=0),
            "multi_candidate_count": sum(
                len({row["candidate_id"] for row in rows}) > 1 for rows in duplicate_groups
            ),
            "replay_containing_count": sum(
                any(row["replay_plan_member"] is True for row in rows) for rows in duplicate_groups
            ),
            "selections_differing_from_first_index_row": selections_differing_from_first,
        },
        "mapping": {"count": len(mapping_rows), "path": mapping_path.name, "sha256": mapping_digest},
        "policy_id": POLICY_ID,
        "representative_distribution": {
            "planner": dict(sorted(Counter(str(row["planner"]) for row in selected_rows).items())),
            "role": dict(sorted(Counter(str(row["role"]) for row in selected_rows).items())),
        },
        "schema_version": REPORT_SCHEMA_VERSION,
    }
    report_payload = _canonical_bytes(report)
    _preflight_publication(mapping_path, mapping_payload)
    _preflight_publication(report_path, report_payload)
    publish_once(mapping_path, mapping_payload)
    publish_once(report_path, report_payload)
    return RepresentativeMappingResult(
        mapping_path=mapping_path,
        report_path=report_path,
        mapping_sha256=mapping_digest,
        report_sha256=hashlib.sha256(report_payload).hexdigest(),
        count=len(mapping_rows),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the Phase 3 representative source mapping.")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--production-contract", action="store_true")
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    production = arguments.production_contract
    result = build_representative_mapping(
        arguments.request,
        arguments.index,
        arguments.output,
        expected_request_sha256=PRODUCTION_REQUEST_SHA256 if production else None,
        expected_request_count=PRODUCTION_REQUEST_COUNT if production else None,
        expected_index_sha256=PRODUCTION_INDEX_SHA256 if production else None,
        expected_index_count=PRODUCTION_INDEX_COUNT if production else None,
    )
    print(json.dumps({"count": result.count, "mapping_sha256": result.mapping_sha256}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
