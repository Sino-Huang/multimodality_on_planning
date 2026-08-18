from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import stat
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import BinaryIO

from . import cgas_trace_contract_v3
from .cgas_candidate_characterization_contracts import canonical_bytes, parse_canonical_model
from .cgas_candidate_characterization_models import CheckpointModel, JsonObject
from .cgas_gate0b_verifier import Gate0bReport, verify_gate0b_round
from .cgas_pilot_expansion_index import (
    BfsCertificateFold,
    PilotExpansionIndexError,
    iter_verified_events,
    project_expansion,
    state_sha256,
)
from .cgas_pilot_manifest_approval import read_json, sha256, validate_pilot_approval
from .cgas_pilot_scope_evidence import _rows
from .cgas_trace_stream_v2 import verify_trace_stream

EXPECTED_MANIFEST_SHA256 = "14e6ff873b0c86f2fcbbe9e342ef387880ae3815f30ca73c32767718915137f9"
EXPECTED_ROW_BUDGET_SHA256 = "504e49aeb47c097b979a9e56a8d5a94fd4be8cde303657e346742751b8eb34f1"
EXPECTED_PILOT_APPROVAL_SHA256 = "7b4dedb1b59a2ec338c64a3f671156581a66db027ecf03569a2f6271fd8fed85"
EXPECTED_ROWS = 31_171
EXPECTED_REPLAY_ROWS = 790
ROLE_ORDER = {"train": 0, "held_out_calibration": 1}
PLANNER_ORDER = {"bfs": 0, "iw": 1}


@dataclass(frozen=True, slots=True)
class MaterializationRequest:
    repository_root: Path
    characterization_root: Path
    approved_trace_path: Path
    candidate_config_path: Path
    scope_report_path: Path
    pilot_approval_path: Path
    manifest_path: Path
    row_budget_path: Path
    output_root: Path
    checkpoint_path: Path


@dataclass(frozen=True, slots=True)
class MaterializationResult:
    index_path: Path
    report_path: Path
    index_sha256: str
    row_count: int
    replay_plan_row_count: int
    off_plan_only_row_count: int
    read_only: bool


def materialize(request: MaterializationRequest) -> MaterializationResult:
    repository = request.repository_root.resolve()
    gate = verify_gate0b_round(
        repository,
        request.characterization_root,
        request.approved_trace_path,
        request.candidate_config_path,
        request.checkpoint_path,
    )
    manifest, manifest_contents = read_json(request.manifest_path, "pilot_expansion_manifest_invalid")
    budget, budget_contents = read_json(request.row_budget_path, "pilot_expansion_budget_invalid")
    _verify_approval_and_inputs(request, manifest, manifest_contents, budget, budget_contents, gate)
    checkpoint, _ = parse_canonical_model(
        gate.checkpoint_path,
        CheckpointModel,
        "pilot_expansion_checkpoint_invalid",
    )
    checkpoint_rows = {_text(row, "candidate_id"): row for row in _rows(checkpoint, gate.checkpoint_path)}
    manifest_records = _manifest_records(manifest)
    output = request.output_root / "pilot-expansion-index.jsonl"
    report_path = request.output_root / "materialization-report.json"
    implementation_sha256 = _file_sha256(Path(__file__))
    projection_sha256 = _file_sha256(Path(__file__).with_name("cgas_pilot_expansion_index.py"))
    temporary, handle = _temporary_output(output)
    counts: Counter[str] = Counter()
    partitions: Counter[str] = Counter()
    seen_rows: set[str] = set()
    stream_bindings: list[JsonObject] = []
    try:
        with handle:
            for manifest_record in manifest_records:
                candidate_id = _text(manifest_record, "candidate_id")
                checkpoint_row = checkpoint_rows.get(candidate_id)
                if checkpoint_row is None:
                    raise PilotExpansionIndexError("pilot_expansion_candidate_missing", gate.checkpoint_path)
                _verify_candidate_binding(manifest_record, checkpoint_row, gate.checkpoint_path)
                for planner in ("bfs", "iw"):
                    planner_row = _mapping(
                        checkpoint_row,
                        "bfs" if planner == "bfs" else "iw_width_1",
                    )
                    trace = _mapping(planner_row, "trace_v3")
                    trace_path = _confined(repository, _text(trace, "path"))
                    expected_stream_digest = _text(manifest_record, f"{planner}_trace_sha256")
                    verification = verify_trace_stream(trace_path)
                    if verification.stream_sha256 != expected_stream_digest:
                        raise PilotExpansionIndexError("pilot_expansion_stream_digest_mismatch", trace_path)
                    replay_steps = _replay_step_membership(planner_row)
                    matched_steps: Counter[int] = Counter()
                    fold = BfsCertificateFold() if planner == "bfs" else None
                    iw_width = _final_iw_width(trace_path) if planner == "iw" else None
                    projected_count = 0
                    for framed in iter_verified_events(trace_path):
                        event = _mapping(framed, "event")
                        if iw_width is not None and event.get("width_decision") != f"width_{iw_width}_novel":
                            continue
                        projection = project_expansion(planner, event, fold)
                        if projection is None:
                            continue
                        sequence = _integer(framed, "sequence")
                        event_hash = _digest(framed, "event_sha256")
                        state_digest = _text(projection, "state_sha256")
                        replay_step = replay_steps.get(state_digest)
                        if replay_step is not None:
                            matched_steps[replay_step] += 1
                        row = {
                            "schema_version": "cgas_phase3_pilot_expansion_index_v1",
                            "row_id": _row_id(candidate_id, planner, sequence, event_hash),
                            "candidate_id": candidate_id,
                            "instance_id": _text(manifest_record, "instance_id"),
                            "raw_rank": _integer(manifest_record, "raw_rank"),
                            "role": _text(manifest_record, "role"),
                            "object_count": _integer(manifest_record, "object_count"),
                            "composition_signature": _text(manifest_record, "composition_signature"),
                            "source_record_sha256": _digest(manifest_record, "source_record_sha256"),
                            "domain_sha256": _digest(manifest_record, "domain_sha256"),
                            "planner": planner,
                            "trace_path": trace_path.relative_to(repository).as_posix(),
                            "trace_stream_sha256": verification.stream_sha256,
                            "trace_contract_id": verification.contract_id,
                            "trace_contract_sha256": verification.contract_sha256,
                            "trace_final_event_sha256": verification.final_event_sha256,
                            "event_sequence": sequence,
                            "event_sha256": event_hash,
                            **projection,
                            "replay_plan_member": replay_step is not None,
                            "replay_step_index": replay_step,
                            "bindings": {
                                "checkpoint_sha256": gate.checkpoint_sha256,
                                "manifest_sha256": EXPECTED_MANIFEST_SHA256,
                                "row_budget_sha256": EXPECTED_ROW_BUDGET_SHA256,
                                "materializer_sha256": implementation_sha256,
                                "projection_sha256": projection_sha256,
                            },
                        }
                        row_id = _text(row, "row_id")
                        if row_id in seen_rows:
                            raise PilotExpansionIndexError("pilot_expansion_row_duplicate", output)
                        seen_rows.add(row_id)
                        handle.write(canonical_bytes(row) + b"\n")
                        projected_count += 1
                        counts["rows"] += 1
                        counts["replay"] += int(replay_step is not None)
                        partition = f"{row['role']}|{row['object_count']}|{planner}"
                        partitions[partition] += 1
                    if projected_count != _integer(_mapping(planner_row, "exact_search"), "expansion_count"):
                        raise PilotExpansionIndexError("pilot_expansion_planner_budget_mismatch", trace_path)
                    if matched_steps != Counter({step: 1 for step in replay_steps.values()}):
                        raise PilotExpansionIndexError("pilot_expansion_replay_membership_mismatch", trace_path)
                    stream_bindings.append(
                        {
                            "candidate_id": candidate_id,
                            "planner": planner,
                            "path": trace_path.relative_to(repository).as_posix(),
                            "record_count": verification.record_count,
                            "stream_sha256": verification.stream_sha256,
                        }
                    )
            handle.flush()
            os.fsync(handle.fileno())
        _verify_totals(counts, budget, output)
        index_digest = _file_sha256(temporary)
        report: JsonObject = {
            "schema_version": "cgas_phase3_pilot_expansion_materialization_v1",
            "status": "verified_certificate_source_index",
            "action_target_policy_status": "owner_decision_required",
            "index_path": output.relative_to(repository).as_posix(),
            "index_sha256": index_digest,
            "row_count": counts["rows"],
            "replay_plan_row_count": counts["replay"],
            "off_plan_only_row_count": counts["rows"] - counts["replay"],
            "partitions": dict(sorted(partitions.items())),
            "gate0b": _gate_record(gate),
            "bindings": {
                "checkpoint_sha256": gate.checkpoint_sha256,
                "manifest_sha256": sha256(manifest_contents),
                "row_budget_sha256": sha256(budget_contents),
                "pilot_approval_sha256": EXPECTED_PILOT_APPROVAL_SHA256,
                "materializer_sha256": implementation_sha256,
                "projection_sha256": projection_sha256,
            },
            "streams": [dict(binding) for binding in stream_bindings],
        }
        report_contents = canonical_bytes(report) + b"\n"
        request.output_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        read_only = _install_once(temporary, output)
        report_read_only = _publish_bytes(report_path, report_contents)
        return MaterializationResult(
            output,
            report_path,
            index_digest,
            counts["rows"],
            counts["replay"],
            counts["rows"] - counts["replay"],
            read_only and report_read_only,
        )
    finally:
        temporary.unlink(missing_ok=True)


def _verify_approval_and_inputs(
    request: MaterializationRequest,
    manifest: JsonObject,
    manifest_contents: bytes,
    budget: JsonObject,
    budget_contents: bytes,
    gate: Gate0bReport,
) -> None:
    approval_digest = validate_pilot_approval(request.scope_report_path, request.pilot_approval_path)
    if approval_digest != EXPECTED_PILOT_APPROVAL_SHA256:
        raise PilotExpansionIndexError("pilot_expansion_approval_drift", request.pilot_approval_path)
    if sha256(manifest_contents) != EXPECTED_MANIFEST_SHA256:
        raise PilotExpansionIndexError("pilot_expansion_manifest_drift", request.manifest_path)
    if sha256(budget_contents) != EXPECTED_ROW_BUDGET_SHA256:
        raise PilotExpansionIndexError("pilot_expansion_budget_drift", request.row_budget_path)
    bindings = _mapping(manifest, "bindings")
    if (
        manifest.get("owner_approved") is not True
        or manifest.get("status") != "approved_pilot_source_manifest"
        or bindings.get("pilot_owner_approval_sha256") != approval_digest
        or bindings.get("checkpoint_sha256") != gate.checkpoint_sha256
        or budget.get("manifest_sha256") != EXPECTED_MANIFEST_SHA256
    ):
        raise PilotExpansionIndexError("pilot_expansion_approval_binding_invalid", request.manifest_path)


def _manifest_records(manifest: JsonObject) -> tuple[JsonObject, ...]:
    records = _mappings(manifest, "records")
    ordered = tuple(
        sorted(
            records,
            key=lambda row: (
                _integer(row, "object_count"),
                ROLE_ORDER.get(_text(row, "role"), 99),
                _integer(row, "raw_rank"),
                _text(row, "candidate_id"),
            ),
        )
    )
    if len(ordered) != 90 or len({_text(row, "candidate_id") for row in ordered}) != 90:
        raise PilotExpansionIndexError("pilot_expansion_manifest_count_invalid")
    if list(ordered) != records:
        raise PilotExpansionIndexError("pilot_expansion_manifest_order_invalid")
    return ordered


def _verify_candidate_binding(manifest: JsonObject, checkpoint: JsonObject, path: Path) -> None:
    fields = ("candidate_id", "instance_id", "raw_rank", "object_count", "composition_signature", "domain_sha256")
    if any(manifest.get(field) != checkpoint.get(field) for field in fields):
        raise PilotExpansionIndexError("pilot_expansion_candidate_binding_invalid", path)
    identity = _mapping(checkpoint, "source_identity")
    if manifest.get("source_record_sha256") != identity.get("source_record_sha256"):
        raise PilotExpansionIndexError("pilot_expansion_candidate_binding_invalid", path)


def _replay_step_membership(planner: JsonObject) -> dict[str, int]:
    replay = _mapping(planner, "replay")
    transitions = _mappings(replay, "transitions")
    membership: dict[str, int] = {}
    for transition in transitions:
        digest = state_sha256(_strings(transition, "state_before"))
        step = _integer(transition, "step_index")
        if digest in membership:
            raise PilotExpansionIndexError("pilot_expansion_replay_state_duplicate")
        membership[digest] = step
    if len(transitions) != _integer(replay, "transition_count"):
        raise PilotExpansionIndexError("pilot_expansion_replay_count_invalid")
    return membership


def _final_iw_width(trace_path: Path) -> int:
    widths: list[int] = []
    for framed in iter_verified_events(trace_path):
        event = _mapping(framed, "event")
        decision = event.get("width_decision")
        if event.get("decision") != "expand" or not isinstance(decision, str):
            continue
        parts = decision.split("_")
        if len(parts) != 3 or parts[0] != "width" or parts[2] != "novel" or not parts[1].isdigit():
            raise PilotExpansionIndexError("pilot_expansion_iw_width_invalid", trace_path)
        widths.append(int(parts[1]))
    if not widths:
        raise PilotExpansionIndexError("pilot_expansion_iw_width_missing", trace_path)
    minimum_width = cgas_trace_contract_v3.POLICY_LIMITS["local_iw_width"]
    maximum_width = cgas_trace_contract_v3.POLICY_LIMITS["local_iw_max_width"]
    if (
        not isinstance(minimum_width, int)
        or not isinstance(maximum_width, int)
        or widths[0] != minimum_width
        or widths[-1] > maximum_width
        or any(next_width not in {width, width + 1} for width, next_width in pairwise(widths))
    ):
        raise PilotExpansionIndexError("pilot_expansion_iw_width_sequence_invalid", trace_path)
    return widths[-1]


def _verify_totals(counts: Counter[str], budget: JsonObject, path: Path) -> None:
    available = _mapping(budget, "available_rows")
    expected = (
        _integer(available, "off_plan_total"),
        _integer(available, "on_plan_total"),
        _integer(available, "off_plan_only"),
    )
    actual = (counts["rows"], counts["replay"], counts["rows"] - counts["replay"])
    if expected != (EXPECTED_ROWS, EXPECTED_REPLAY_ROWS, EXPECTED_ROWS - EXPECTED_REPLAY_ROWS) or actual != expected:
        raise PilotExpansionIndexError("pilot_expansion_total_budget_mismatch", path)


def _gate_record(gate: Gate0bReport) -> JsonObject:
    return {
        "round": gate.round,
        "checkpoint_sha256": gate.checkpoint_sha256,
        "candidate_count": gate.candidate_count,
        "stream_count": gate.stream_count,
        "total_stream_bytes": gate.total_stream_bytes,
    }


def _temporary_output(output: Path) -> tuple[Path, BinaryIO]:
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if output.parent.is_symlink() or not stat.S_ISDIR(output.parent.lstat().st_mode):
        raise PilotExpansionIndexError("pilot_expansion_output_directory_invalid", output.parent)
    descriptor, name = tempfile.mkstemp(prefix=f".{output.name}-", dir=output.parent)
    os.fchmod(descriptor, 0o600)
    return Path(name), os.fdopen(descriptor, "wb")


def _install_once(temporary: Path, output: Path) -> bool:
    directory = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        fcntl.flock(directory, fcntl.LOCK_EX)
        if output.exists() or output.is_symlink():
            if output.is_symlink() or not output.is_file() or _file_sha256(output) != _file_sha256(temporary):
                raise PilotExpansionIndexError("pilot_expansion_publication_collision", output)
            return True
        try:
            os.link(temporary, output, follow_symlinks=False)
            os.fsync(directory)
        except OSError as error:
            raise PilotExpansionIndexError("pilot_expansion_publication_failed", output) from error
        return False
    finally:
        os.close(directory)


def _publish_bytes(output: Path, contents: bytes) -> bool:
    temporary, handle = _temporary_output(output)
    try:
        with handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        return _install_once(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def _row_id(candidate_id: str, planner: str, sequence: int, event_hash: str) -> str:
    preimage = f"{candidate_id}:{PLANNER_ORDER[planner]}:{sequence}:{event_hash}"
    return "cgas-pilot-expansion-" + hashlib.sha256(preimage.encode()).hexdigest()[:24]


def _confined(repository: Path, relative: str) -> Path:
    path = (repository / relative).resolve()
    if not path.is_relative_to(repository) or not path.is_file() or path.is_symlink():
        raise PilotExpansionIndexError("pilot_expansion_trace_path_invalid", path)
    return path


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(value: Mapping[str, object], field: str) -> JsonObject:
    item = value.get(field)
    if not isinstance(item, dict):
        raise PilotExpansionIndexError(f"pilot_expansion_invalid_mapping:{field}")
    return dict(item)


def _mappings(value: Mapping[str, object], field: str) -> list[JsonObject]:
    items = value.get(field)
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise PilotExpansionIndexError(f"pilot_expansion_invalid_mapping_array:{field}")
    return [dict(item) for item in items]


def _strings(value: Mapping[str, object], field: str) -> list[str]:
    items = value.get(field)
    if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
        raise PilotExpansionIndexError(f"pilot_expansion_invalid_string_array:{field}")
    return list(items)


def _text(value: Mapping[str, object], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item:
        raise PilotExpansionIndexError(f"pilot_expansion_invalid_text:{field}")
    return item


def _digest(value: Mapping[str, object], field: str) -> str:
    digest = _text(value, field)
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise PilotExpansionIndexError(f"pilot_expansion_invalid_digest:{field}")
    return digest


def _integer(value: Mapping[str, object], field: str) -> int:
    item = value.get(field)
    if isinstance(item, bool) or not isinstance(item, int) or item < 0:
        raise PilotExpansionIndexError(f"pilot_expansion_invalid_integer:{field}")
    return item


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize the approved Phase 3 pilot expansion index.")
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    repository = args.repository.resolve()
    evidence = repository / ".claude/evidence/cgas-phase3-pilot-manifest"
    result = materialize(
        MaterializationRequest(
            repository,
            repository / "tmp/cgas-p0-characterized-v3",
            repository / ".claude/evidence/cgas-trace-contract-v3/approved-trace-v3.json",
            repository / "configs/cgas/production_p0_candidates.json",
            repository / ".claude/evidence/cgas-phase3-pilot-scope/report.json",
            evidence / "pilot-owner-approval.json",
            evidence / "pilot-source-manifest.json",
            evidence / "pilot-row-budget.json",
            args.output.resolve(),
            repository / "tmp/cgas-p0-characterized-v3/checkpoints/reservoir_checkpoint_000001.json",
        )
    )
    print(json.dumps({"index_sha256": result.index_sha256, "row_count": result.row_count}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
