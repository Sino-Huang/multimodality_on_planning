from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import re
import shlex
import tempfile
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from .cgas_candidate_accounting import PlannerInput, planner_input_record
from .cgas_candidate_space import build_candidate
from .cgas_pilot_expansion_index import PilotExpansionIndexError, state_sha256
from .cgas_pilot_representative_mapping import POLICY_ID
from .cgas_pilot_representative_mapping import SCHEMA_VERSION as MAPPING_SCHEMA_VERSION
from .io_utils import file_sha256, stable_hash, write_json
from .pddl import PDDLError, PDDLTask, canonical_atom, parse_task
from .planimation_pairing_contracts import RenderConfig, RendererResult, StateRenderer
from .planimation_pairing_rendering import _render_one_state, render_state_with_planimation
from .render_semantics import validate_render_artifacts
from .traversal_state_types import JSONValue

SCHEMA_VERSION = "cgas_phase3_pilot_planimation_adapter_v1"
DEFAULT_DOMAIN_PATH = Path("modules/pddl-generators/blocksworld/4ops/domain.pddl")
DEFAULT_OUTPUT_ROOT = Path("outputs/image_frames/cgas-phase3-pilot-planimation-adapter-v1")
DEFAULT_MANIFEST_PATH = Path(".claude/evidence/cgas-phase3-pilot-manifest/pilot-source-manifest.json")
DEFAULT_CHECKPOINT_PATH = Path("tmp/cgas-p0-characterized-v3/checkpoints/reservoir_checkpoint_000001.json")
PRODUCTION_REQUEST_SHA256 = "13db7cba5fb1cf885bd203ff657e5c7714bda6f832c5970dbfe5a9dee36d0585"
PRODUCTION_REQUEST_COUNT = 16_822
PRODUCTION_INDEX_SHA256 = "46d1e7c1c0a6a133372782e691888840a74f3d3732dd625b5e2d8611fdf5d390"
PRODUCTION_INDEX_COUNT = 31_171
PRODUCTION_MAPPING_SHA256 = "3d6ff222e3662319d9429e18e3bd0d33a7ea1aee67a07e6d9b1a25c506ad7de3"
PRODUCTION_MAPPING_COUNT = 16_822


def _pilot_render_config() -> RenderConfig:
    return RenderConfig(request_delay_seconds=0, max_attempts=1)


@dataclass(frozen=True, slots=True)
class PilotRenderError(RuntimeError):
    rule: str

    def __str__(self) -> str:
        return self.rule


@dataclass(frozen=True, slots=True)
class PilotRenderRequest:
    repository_root: Path
    request_path: Path
    expansion_index_path: Path
    output_root: Path
    domain_path: Path | None = None
    profile_path: Path | None = None
    config: RenderConfig = field(default_factory=_pilot_render_config)
    pilot_manifest_path: Path | None = None
    checkpoint_path: Path | None = None
    expected_request_sha256: str | None = None
    expected_request_count: int | None = None
    expected_index_sha256: str | None = None
    expected_index_count: int | None = None
    representative_mapping_path: Path | None = None
    expected_mapping_sha256: str | None = None
    expected_mapping_count: int | None = None


@dataclass(frozen=True, slots=True)
class PilotRenderResult:
    manifest_path: Path
    report_path: Path
    counts: dict[str, int]


_ZERO_PADDED_BLOCK_OBJECT = re.compile(r"^b\d{2,}$")
PLANIMATION_COMPAT_PROBLEM_NAME = "problem.planimation-compat.pddl"
# Optional per-row field carrying a supplied action sequence for the Planimation
# render of that state. Absent rows render through the backend solver (historical
# behavior); present rows must be a valid non-empty parenthesised plan.
SUPPLIED_PLAN_FIELD = "supplied_plan"


def _supplied_plan(index_row: dict[str, object]) -> str | None:
    """Return the optional supplied plan bound to an index row, or None.

    Only rows that explicitly carry ``supplied_plan`` get a supplied plan. The
    value must be a non-empty string whose text contains at least one
    parenthesised action (mirroring the pinned backend's acceptance test for its
    multipart ``plan`` field); any present-but-invalid value fails closed so a
    malformed row can never silently fall back to the hosted planner.
    """
    if SUPPLIED_PLAN_FIELD not in index_row:
        return None
    value = index_row.get(SUPPLIED_PLAN_FIELD)
    if not isinstance(value, str) or not value.strip() or "(" not in value or ")" not in value:
        raise PilotRenderError("supplied_plan_invalid")
    return value


def format_planimation_compat_problem(task: PDDLTask, *, problem_name: str | None = None) -> str | None:
    """Format a parsed Blocksworld task in the July-compatible Planimation layout.

    A zero-padded bNN object namespace is renamed bijectively to b1..bN by parsed
    symbol order (never naive substring replacement), and init/goal atoms are emitted
    in sorted canonical order. Returns None for problems without a zero-padded bNN
    namespace so callers can pass the original problem through unchanged.
    """
    objects = tuple(sorted(task.objects_by_type.get("object", ())))
    if not objects or not all(_ZERO_PADDED_BLOCK_OBJECT.fullmatch(obj) for obj in objects):
        return None
    renamed = {obj: f"b{index + 1}" for index, obj in enumerate(objects)}
    name = task.problem_name if problem_name is None else problem_name
    lines: list[str] = ["", ""]
    lines.append(f"(define (problem {name})")
    lines.append(f"(:domain {task.domain_name})")
    lines.append("(:objects " + " ".join(renamed[obj] for obj in objects) + " )")
    lines.append("(:init")
    lines.extend(f"  {canonical_atom(tuple(renamed.get(part, part) for part in atom))}" for atom in sorted(task.init))
    lines.append(")")
    if task.goal:
        goal_atoms = sorted(canonical_atom(tuple(renamed.get(part, part) for part in atom)) for atom in task.goal)
        lines.append("(:goal")
        lines.append("(and")
        lines.extend(goal_atoms[:-1])
        lines.append(f"{goal_atoms[-1]})")
        lines.append(")")
    else:
        lines.append("(:goal (and))")
    lines.append(")")
    lines.append("")
    lines.append("")
    return "\n".join(lines) + "\n"


def _planimation_compat_problem_path(domain_path: Path, problem_path: Path, cache_dir: Path) -> Path:
    try:
        task = parse_task(domain_path, problem_path)
    except (PDDLError, OSError):
        return problem_path
    formatted = format_planimation_compat_problem(task)
    if formatted is None:
        return problem_path
    compat_path = cache_dir / PLANIMATION_COMPAT_PROBLEM_NAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    compat_path.write_text(formatted, encoding="utf-8")
    return compat_path


def render_state_with_planimation_compat(
    domain_path: Path, problem_path: Path, profile_path: Path, cache_dir: Path, config: RenderConfig
) -> RendererResult:
    """Render a derived state with Planimation using a July-compatible problem layout.

    Only cache_dir/problem.planimation-compat.pddl is written; the b00-bound cache
    problem.pddl is never modified. Problems without a zero-padded bNN object
    namespace are passed through unchanged via the original problem path.
    """
    compat_path = _planimation_compat_problem_path(domain_path, problem_path, cache_dir)
    return render_state_with_planimation(domain_path, compat_path, profile_path, cache_dir, config)


def render_missing_states(
    request: PilotRenderRequest,
    *,
    renderer: StateRenderer = render_state_with_planimation_compat,
) -> PilotRenderResult:
    """Render requested canonical states with fail-closed, digest-bound resume."""
    _assert_output_root(request.repository_root, request.output_root)
    rows, duplicate_count = _requested_states(request.request_path)
    index_rows, index_count = _index_requested_rows(request.expansion_index_path, set(rows))
    index = _selected_index_rows(request, rows, index_rows)
    _validate_expected_bindings(request, rows, index_count)
    domain_path = (request.domain_path or request.repository_root / DEFAULT_DOMAIN_PATH).resolve()
    profile_path = (request.profile_path or _default_profile_path(request.repository_root)).resolve()
    mapping_sha256 = (
        file_sha256(request.representative_mapping_path) if request.representative_mapping_path is not None else None
    )
    contract_record = _run_contract(request, domain_path, profile_path, renderer)
    contract = stable_hash(contract_record)
    diagnostics = request.output_root / "diagnostics"
    manifest_path = diagnostics / "state_render_manifest.jsonl"
    checkpoint_path = diagnostics / "render-checkpoint.jsonl"
    report_path = request.output_root / "reports" / "render-report.json"
    _persist_run_contract(diagnostics / "run-contract.json", contract_record, contract)
    records = _validated_prior_records(manifest_path, checkpoint_path, contract)
    requested_digests = set(rows)
    if not set(records).issubset(requested_digests):
        raise PilotRenderError("manifest_state_outside_request")
    counts: Counter[str] = Counter(
        requested=len(rows), duplicate=duplicate_count, collision=0, processed=0, succeeded=0, failed=0
    )

    for digest, state in sorted(rows.items()):
        indexed = index.get(digest)
        if indexed is None:
            raise PilotRenderError("request_state_missing_from_expansion_index")
        if indexed["state_atoms"] != state["state_atoms"]:
            raise PilotRenderError("request_state_collision")
        _validate_source_row(indexed)
        existing = records.get(digest)
        if existing is not None and existing.get("status") == "success":
            _validate_manifest_record(existing, state, contract, request.output_root)
            counts["succeeded"] += 1
            continue
        record = _render_state(
            request=request,
            state=state,
            index_row=indexed,
            domain_path=domain_path,
            profile_path=profile_path,
            renderer=renderer,
            contract=contract,
            mapping_sha256=mapping_sha256,
        )
        records[digest] = record
        _append_checkpoint(checkpoint_path, record)
        counts["processed"] += 1
        counts["succeeded"] += int(record.get("status") == "success")
        counts["failed"] += int(record.get("status") != "success")

    counts["remaining"] = counts["requested"] - counts["succeeded"]
    _atomic_write_jsonl(manifest_path, [records[digest] for digest in sorted(records)])
    _atomic_write_json(
        report_path,
        {
            "schema_version": SCHEMA_VERSION,
            "status": "complete" if counts["remaining"] == 0 else "incomplete",
            "request_path": str(request.request_path),
            "expansion_index_path": str(request.expansion_index_path),
            "run_contract_sha256": contract,
            "checkpoint_path": str(checkpoint_path),
            "resume_command": _resume_command(request, domain_path, profile_path),
            "counts": dict(counts),
        },
    )
    return PilotRenderResult(manifest_path, report_path, dict(counts))


def _requested_states(path: Path) -> tuple[dict[str, dict[str, object]], int]:
    requested: dict[str, dict[str, object]] = {}
    duplicate_count = 0
    for raw in _jsonl(path):
        atoms = _strings(raw, "state_atoms", "request_state_atoms_invalid")
        digest = _digest(raw, "state_sha256", "request_state_hash_invalid")
        try:
            computed = state_sha256(atoms)
        except PilotExpansionIndexError as error:
            raise PilotRenderError("request_state_atoms_noncanonical") from error
        if computed != digest:
            raise PilotRenderError("request_state_hash_mismatch")
        candidate = {"state_sha256": digest, "state_atoms": sorted(atoms)}
        previous = requested.get(digest)
        if previous is None:
            requested[digest] = candidate
        elif previous == candidate:
            duplicate_count += 1
        else:
            raise PilotRenderError("request_state_collision")
    return requested, duplicate_count


def _index_requested_rows(path: Path, requested: set[str]) -> tuple[dict[str, list[dict[str, object]]], int]:
    result: dict[str, list[dict[str, object]]] = {}
    row_count = 0
    for raw in _jsonl_records(path):
        row_count += 1
        atoms = _strings(raw, "state_atoms", "index_state_atoms_invalid")
        digest = _digest(raw, "state_sha256", "index_state_hash_invalid")
        if state_sha256(atoms) != digest:
            raise PilotRenderError("index_state_hash_mismatch")
        if digest not in requested:
            continue
        normalized = dict(raw)
        normalized["state_atoms"] = sorted(atoms)
        rows = result.setdefault(digest, [])
        if rows and rows[0]["state_atoms"] != normalized["state_atoms"]:
            raise PilotRenderError("index_state_collision")
        rows.append(normalized)
    return result, row_count


def _selected_index_rows(
    request: PilotRenderRequest,
    requested: dict[str, dict[str, object]],
    index_rows: dict[str, list[dict[str, object]]],
) -> dict[str, dict[str, object]]:
    if request.representative_mapping_path is not None:
        return _mapped_index_rows(request, requested, index_rows)
    result: dict[str, dict[str, object]] = {}
    for digest, rows in index_rows.items():
        selected = rows[0]
        for other in rows[1:]:
            if _source_identity(selected) != _source_identity(other):
                raise PilotRenderError("request_state_source_ambiguous")
        result[digest] = selected
    return result


def _mapped_index_rows(
    request: PilotRenderRequest,
    requested: dict[str, dict[str, object]],
    index_rows: dict[str, list[dict[str, object]]],
) -> dict[str, dict[str, object]]:
    path = request.representative_mapping_path
    if path is None:
        raise PilotRenderError("representative_mapping_required")
    if request.expected_mapping_sha256 is not None and file_sha256(path) != request.expected_mapping_sha256:
        raise PilotRenderError("representative_mapping_binding_mismatch")
    mapping_rows = _jsonl(path)
    if request.expected_mapping_count is not None and len(mapping_rows) != request.expected_mapping_count:
        raise PilotRenderError("representative_mapping_count_mismatch")
    request_digest = file_sha256(request.request_path)
    index_digest = file_sha256(request.expansion_index_path)
    result: dict[str, dict[str, object]] = {}
    for mapping_row in mapping_rows:
        if mapping_row.get("schema_version") != MAPPING_SCHEMA_VERSION:
            raise PilotRenderError("representative_mapping_schema_mismatch")
        digest = _digest(mapping_row, "state_sha256", "representative_mapping_state_invalid")
        if digest not in requested or digest in result:
            raise PilotRenderError("representative_mapping_state_set_mismatch")
        if mapping_row.get("state_atoms") != requested[digest]["state_atoms"]:
            raise PilotRenderError("representative_mapping_state_mismatch")
        selection = _mapping(mapping_row, "selection", "representative_mapping_selection_invalid")
        if selection.get("policy_id") != POLICY_ID:
            raise PilotRenderError("representative_mapping_policy_mismatch")
        bindings = _mapping(mapping_row, "bindings", "representative_mapping_bindings_invalid")
        if (
            bindings.get("request_sha256") != request_digest
            or bindings.get("expansion_index_sha256") != index_digest
            or bindings.get("request_count") != len(requested)
        ):
            raise PilotRenderError("representative_mapping_bindings_mismatch")
        representative = _mapping(mapping_row, "representative", "representative_mapping_source_invalid")
        matches = [
            row
            for row in index_rows.get(digest, [])
            if _mapping_source_identity(row) == _mapping_source_identity(representative)
        ]
        if len(matches) != 1:
            raise PilotRenderError("representative_mapping_source_mismatch")
        result[digest] = matches[0]
    if set(result) != set(requested):
        raise PilotRenderError("representative_mapping_state_set_mismatch")
    return result


def _mapping_source_identity(row: dict[str, object]) -> tuple[object, ...]:
    return (
        row.get("row_id"),
        row.get("candidate_id"),
        row.get("instance_id"),
        row.get("object_count"),
        row.get("raw_rank"),
        row.get("role"),
        row.get("planner"),
        row.get("source_record_sha256"),
        row.get("event_sequence"),
        row.get("event_sha256"),
        row.get("trace_path"),
        row.get("trace_stream_sha256"),
        row.get("trace_contract_id"),
        row.get("trace_contract_sha256"),
        row.get("replay_plan_member"),
        row.get("replay_step_index"),
    )


def _source_identity(row: dict[str, object]) -> tuple[object, object, object, object]:
    return (
        row.get("candidate_id"),
        row.get("object_count"),
        row.get("raw_rank"),
        row.get("source_record_sha256"),
    )


def _validate_expected_bindings(
    request: PilotRenderRequest,
    rows: dict[str, dict[str, object]],
    index_count: int,
) -> None:
    request_digest = file_sha256(request.request_path)
    index_digest = file_sha256(request.expansion_index_path)
    if request.expected_request_sha256 is not None and request_digest != request.expected_request_sha256:
        raise PilotRenderError("request_binding_mismatch")
    if request.expected_request_count is not None and len(rows) != request.expected_request_count:
        raise PilotRenderError("request_count_mismatch")
    if request.expected_index_sha256 is not None and index_digest != request.expected_index_sha256:
        raise PilotRenderError("index_binding_mismatch")
    if request.expected_index_count is not None and index_count != request.expected_index_count:
        raise PilotRenderError("index_count_mismatch")


def _validate_source_row(row: dict[str, object]) -> None:
    object_count = _integer(row, "object_count", "index_object_count_invalid")
    raw_rank = _integer(row, "raw_rank", "index_raw_rank_invalid")
    candidate = build_candidate(object_count, raw_rank)
    if row.get("candidate_id") != candidate.candidate_id:
        raise PilotRenderError("candidate_identity_mismatch")
    instance_id = row.get("instance_id")
    if not isinstance(instance_id, str) or instance_id != candidate.candidate_id:
        raise PilotRenderError("instance_identity_mismatch")
    planner = PlannerInput(
        object_count,
        raw_rank,
        "emitted",
        candidate.candidate_id,
        raw_rank,
        candidate,
    )
    source = planner_input_record(planner)
    payload = (
        json.dumps(source, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode() + b"\n"
    )
    if row.get("source_record_sha256") != hashlib.sha256(payload).hexdigest():
        raise PilotRenderError("source_record_hash_mismatch")


def _render_state(
    *,
    request: PilotRenderRequest,
    state: dict[str, object],
    index_row: dict[str, object],
    domain_path: Path,
    profile_path: Path,
    renderer: StateRenderer,
    contract: str,
    mapping_sha256: str | None,
) -> dict[str, object]:
    problem = _candidate_problem(index_row)
    problem_path = request.output_root / "candidate_problems" / f"{state['state_sha256']}.pddl"
    problem_path.parent.mkdir(parents=True, exist_ok=True)
    problem_path.write_text(problem, encoding="utf-8")
    pair: dict[str, JSONValue] = {
        "pair_id": f"pilot-{state['state_sha256']}",
        "domain": "blocksworld",
        "instance_id": str(index_row.get("instance_id", index_row.get("candidate_id", "unknown"))),
        "split": str(index_row.get("role", "pilot")),
        "planner": str(index_row.get("planner", "unknown")),
        "domain_path": str(domain_path),
        "problem_path": str(problem_path),
        "profile_path": str(profile_path),
    }
    state_atoms = _strings(state, "state_atoms", "request_state_atoms_invalid")
    state_payload: list[JSONValue] = list(state_atoms)
    transition: dict[str, JSONValue] = {"step_index": 0, "state_before": state_payload}
    plan = _supplied_plan(index_row)
    # The shared request config never carries a per-state plan; only this state's
    # render uses a plan-bearing config, so absent-plan states stay byte-identical.
    state_config = replace(request.config, plan=plan) if plan is not None else request.config
    record: dict[str, object] = {
        key: value
        for key, value in _render_one_state(pair, transition, request.output_root, renderer, state_config).items()
    }
    if record.get("status") == "success":
        record.update(
            {
                "png_sha256": file_sha256(Path(str(record["frame_path"]))),
                "vfg_sha256": file_sha256(Path(str(record["trace_path"]))),
            }
        )
    record.update(
        {
            "schema_version": SCHEMA_VERSION,
            "state_sha256": state["state_sha256"],
            "transition": transition,
            "run_contract_sha256": contract,
            "source_row_id": index_row.get("row_id"),
            "representative_mapping_sha256": mapping_sha256,
            "source_record_sha256": index_row.get("source_record_sha256"),
            "candidate_id": index_row.get("candidate_id"),
            "object_count": index_row.get("object_count"),
            "raw_rank": index_row.get("raw_rank"),
        }
    )
    if plan is not None:
        # Direct per-state provenance receipt: the exact supplied plan digest.
        # The plan itself is bound transitively via the expansion-index SHA256 in
        # the run contract plus the cache identity, which includes the plan text.
        record["supplied_plan_sha256"] = stable_hash(plan)
    return record


def _candidate_problem(row: dict[str, object]) -> str:
    object_count = _integer(row, "object_count", "index_object_count_invalid")
    raw_rank = _integer(row, "raw_rank", "index_raw_rank_invalid")
    candidate = build_candidate(object_count, raw_rank)
    if row.get("candidate_id") != candidate.candidate_id:
        raise PilotRenderError("candidate_identity_mismatch")
    return candidate.problem


def _run_contract(
    request: PilotRenderRequest,
    domain_path: Path,
    profile_path: Path,
    renderer: StateRenderer,
) -> dict[str, JSONValue]:
    manifest = (request.pilot_manifest_path or request.repository_root / DEFAULT_MANIFEST_PATH).resolve()
    checkpoint = (request.checkpoint_path or request.repository_root / DEFAULT_CHECKPOINT_PATH).resolve()
    rendering_source = inspect.getsourcefile(_render_one_state)
    renderer_source = inspect.getsourcefile(renderer)
    semantics_source = inspect.getsourcefile(validate_render_artifacts)
    if rendering_source is None or renderer_source is None or semantics_source is None:
        raise PilotRenderError("run_contract_implementation_unavailable")
    scripts_root = Path(__file__).resolve().parents[1]
    planimation_sources = {
        "planimation_facade_implementation_sha256": scripts_root / "planimation_phase1.py",
        "planimation_client_implementation_sha256": scripts_root / "planimation_phase1_client.py",
        "planimation_frames_implementation_sha256": scripts_root / "planimation_phase1_frames.py",
    }
    optional: dict[str, JSONValue] = {}
    for name, path in (("pilot_manifest", manifest), ("checkpoint", checkpoint)):
        if path.exists():
            optional[f"{name}_path"] = str(path)
            optional[f"{name}_sha256"] = file_sha256(path)
        elif request.pilot_manifest_path is not None or request.checkpoint_path is not None:
            raise PilotRenderError("run_contract_input_unavailable")
    try:
        return {
            "schema_version": SCHEMA_VERSION,
            "request_path": str(request.request_path.resolve()),
            "request_sha256": file_sha256(request.request_path),
            "expansion_index_path": str(request.expansion_index_path.resolve()),
            "expansion_index_sha256": file_sha256(request.expansion_index_path),
            **(
                {
                    "representative_mapping_path": str(request.representative_mapping_path.resolve()),
                    "representative_mapping_sha256": file_sha256(request.representative_mapping_path),
                    "representative_mapping_policy_id": POLICY_ID,
                }
                if request.representative_mapping_path is not None
                else {}
            ),
            "domain_path": str(domain_path),
            "domain_sha256": file_sha256(domain_path),
            "profile_path": str(profile_path),
            "profile_sha256": file_sha256(profile_path),
            "adapter_implementation_sha256": file_sha256(Path(__file__)),
            "rendering_implementation_sha256": file_sha256(Path(rendering_source)),
            "renderer_implementation_sha256": file_sha256(Path(renderer_source)),
            "render_semantics_implementation_sha256": file_sha256(Path(semantics_source)),
            **{name: file_sha256(path) for name, path in planimation_sources.items()},
            "render_config": {
                "base_url": request.config.base_url,
                "timeout_seconds": request.config.timeout_seconds,
                "request_delay_seconds": request.config.request_delay_seconds,
                "max_attempts": request.config.max_attempts,
            },
            **optional,
        }
    except OSError as error:
        raise PilotRenderError("run_contract_input_unavailable") from error


def _persist_run_contract(path: Path, record: dict[str, JSONValue], digest: str) -> None:
    contents = {**record, "run_contract_sha256": digest}
    if path.exists():
        try:
            prior = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise PilotRenderError("run_contract_read_failed") from error
        if prior != contents:
            raise PilotRenderError("run_contract_mismatch")
        return
    write_json(path, contents)


def _validated_prior_records(manifest: Path, checkpoint: Path, contract: str) -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    for path in (manifest, checkpoint):
        if not path.exists():
            continue
        for record in _jsonl(path):
            if record.get("run_contract_sha256") != contract:
                raise PilotRenderError("run_contract_mismatch")
            digest = _digest(record, "state_sha256", "manifest_state_hash_invalid")
            atoms = _strings(
                _mapping(record, "transition", "manifest_transition_invalid"),
                "state_before",
                "manifest_state_atoms_invalid",
            )
            if state_sha256(atoms) != digest:
                raise PilotRenderError("manifest_state_hash_mismatch")
            previous = records.get(digest)
            if previous is not None:
                previous_success = previous.get("status") == "success"
                record_success = record.get("status") == "success"
                if previous_success and record_success and previous != record:
                    raise PilotRenderError("manifest_success_collision")
                if previous_success:
                    continue
            records[digest] = record
    return records


def _validate_manifest_record(
    record: dict[str, object], state: dict[str, object], contract: str, output_root: Path
) -> None:
    if record.get("run_contract_sha256") != contract:
        raise PilotRenderError("run_contract_mismatch")
    transition = _mapping(record, "transition", "manifest_transition_invalid")
    if transition.get("state_before") != state["state_atoms"]:
        raise PilotRenderError("manifest_state_collision")
    frame_path = Path(str(record.get("frame_path", "")))
    trace_path = Path(str(record.get("trace_path", "")))
    output_root = output_root.resolve()
    for artifact_path in (frame_path, trace_path):
        try:
            resolved = artifact_path.resolve(strict=True)
        except OSError as error:
            raise PilotRenderError("manifest_artifact_unavailable") from error
        if artifact_path.is_symlink() or not resolved.is_relative_to(output_root):
            raise PilotRenderError("manifest_artifact_path_invalid")
    try:
        if file_sha256(frame_path) != record.get("png_sha256"):
            raise PilotRenderError("manifest_png_hash_mismatch")
        if file_sha256(trace_path) != record.get("vfg_sha256"):
            raise PilotRenderError("manifest_vfg_hash_mismatch")
        if validate_render_artifacts(trace_path, frame_path).status != "success":
            raise PilotRenderError("manifest_semantic_receipt_invalid")
    except OSError as error:
        raise PilotRenderError("manifest_artifact_unavailable") from error


def _append_checkpoint(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(record, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())


def _atomic_write_jsonl(path: Path, rows: Sequence[dict[str, object]]) -> None:
    contents = "".join(
        json.dumps(row, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n" for row in rows
    ).encode("utf-8")
    _atomic_publish(path, contents)


def _atomic_write_json(path: Path, value: object) -> None:
    contents = (
        json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")
    _atomic_publish(path, contents)


def _atomic_publish(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError as error:
        raise PilotRenderError("publication_failed") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _resume_command(request: PilotRenderRequest, domain_path: Path, profile_path: Path) -> str:
    command = [
        "python",
        "-m",
        "scripts.phase3.cgas_pilot_planimation_adapter",
        str(request.request_path),
        str(request.expansion_index_path),
        "--repository-root",
        str(request.repository_root),
        "--output-root",
        str(request.output_root),
        "--domain-path",
        str(domain_path),
        "--profile-path",
        str(profile_path),
        "--base-url",
        request.config.base_url,
        "--timeout-seconds",
        str(request.config.timeout_seconds),
        "--request-delay-seconds",
        str(request.config.request_delay_seconds),
        "--max-attempts",
        str(request.config.max_attempts),
    ]
    if request.representative_mapping_path is not None:
        command.extend(["--representative-mapping-path", str(request.representative_mapping_path)])
    if request.expected_mapping_sha256 is not None:
        command.extend(["--expected-mapping-sha256", request.expected_mapping_sha256])
    if request.expected_mapping_count is not None:
        command.extend(["--expected-mapping-count", str(request.expected_mapping_count)])
    if (
        request.representative_mapping_path is not None
        and request.expected_mapping_sha256 in {None, PRODUCTION_MAPPING_SHA256}
        and request.expected_mapping_count in {None, PRODUCTION_MAPPING_COUNT}
        and request.expected_request_sha256 == PRODUCTION_REQUEST_SHA256
        and request.expected_request_count == PRODUCTION_REQUEST_COUNT
        and request.expected_index_sha256 == PRODUCTION_INDEX_SHA256
        and request.expected_index_count == PRODUCTION_INDEX_COUNT
    ):
        command.append("--production-contract")
    return "source ~/cd_vlaplan && " + shlex.join(command)


def _default_profile_path(root: Path) -> Path:
    candidates = sorted(root.glob("**/*blocksworld*profile*.pddl"))
    if not candidates:
        raise PilotRenderError("planimation_profile_not_found")
    return candidates[0]


def _assert_output_root(repository_root: Path, output_root: Path) -> None:
    repository = repository_root.resolve()
    output = output_root.resolve()
    if output_root.is_symlink() or not any(
        output.is_relative_to(parent) for parent in (repository / "outputs", repository / "tmp")
    ):
        raise PilotRenderError("output_root_invalid")


def _jsonl(path: Path) -> Sequence[dict[str, object]]:
    return list(_jsonl_records(path))


def _jsonl_records(path: Path) -> Iterator[dict[str, object]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise PilotRenderError("jsonl_record_invalid")
                yield row
    except (OSError, json.JSONDecodeError) as error:
        raise PilotRenderError("jsonl_read_failed") from error


def _mapping(row: dict[str, object], field: str, rule: str) -> dict[str, object]:
    value = row.get(field)
    if not isinstance(value, dict):
        raise PilotRenderError(rule)
    return value


def _strings(row: dict[str, object], field: str, rule: str) -> list[str]:
    value = row.get(field)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise PilotRenderError(rule)
    return value


def _integer(row: dict[str, object], field: str, rule: str) -> int:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise PilotRenderError(rule)
    return value


def _digest(row: dict[str, object], field: str, rule: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise PilotRenderError(rule)
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render canonical CGAS pilot states with Planimation.")
    render_defaults = _pilot_render_config()
    parser.add_argument("request_path", type=Path)
    parser.add_argument("expansion_index_path", type=Path)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--domain-path", type=Path, default=DEFAULT_DOMAIN_PATH)
    parser.add_argument("--profile-path", type=Path, required=True)
    parser.add_argument("--base-url", default=render_defaults.base_url)
    parser.add_argument("--timeout-seconds", type=int, default=render_defaults.timeout_seconds)
    parser.add_argument("--request-delay-seconds", type=float, default=render_defaults.request_delay_seconds)
    parser.add_argument("--max-attempts", type=int, default=render_defaults.max_attempts)
    parser.add_argument("--representative-mapping-path", type=Path)
    parser.add_argument("--expected-mapping-sha256")
    parser.add_argument("--expected-mapping-count", type=int)
    parser.add_argument("--production-contract", action="store_true")
    args = parser.parse_args(argv)
    if args.timeout_seconds < 1 or args.request_delay_seconds < 0 or args.max_attempts < 1:
        parser.error("render timing values must be positive, except request delay may be zero")
    if args.production_contract and args.representative_mapping_path is None:
        parser.error("--production-contract requires --representative-mapping-path")
    if args.representative_mapping_path is None and (
        args.expected_mapping_sha256 is not None or args.expected_mapping_count is not None
    ):
        parser.error("--expected-mapping-sha256/--expected-mapping-count require --representative-mapping-path")
    if args.production_contract and (
        args.expected_mapping_sha256 not in {None, PRODUCTION_MAPPING_SHA256}
        or args.expected_mapping_count not in {None, PRODUCTION_MAPPING_COUNT}
    ):
        parser.error("--production-contract mapping binding does not match the frozen mapping")
    expected = (
        {
            "expected_request_sha256": PRODUCTION_REQUEST_SHA256,
            "expected_request_count": PRODUCTION_REQUEST_COUNT,
            "expected_index_sha256": PRODUCTION_INDEX_SHA256,
            "expected_index_count": PRODUCTION_INDEX_COUNT,
        }
        if args.production_contract
        else {}
    )
    result = render_missing_states(
        PilotRenderRequest(
            args.repository_root,
            args.request_path,
            args.expansion_index_path,
            args.output_root,
            args.domain_path,
            args.profile_path,
            RenderConfig(
                args.base_url,
                args.timeout_seconds,
                args.request_delay_seconds,
                args.max_attempts,
            ),
            **expected,
            representative_mapping_path=args.representative_mapping_path,
            expected_mapping_sha256=(
                PRODUCTION_MAPPING_SHA256 if args.production_contract else args.expected_mapping_sha256
            ),
            expected_mapping_count=(
                PRODUCTION_MAPPING_COUNT if args.production_contract else args.expected_mapping_count
            ),
        )
    )
    print(
        json.dumps(
            {
                "manifest_path": str(result.manifest_path),
                "report_path": str(result.report_path),
                "counts": result.counts,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
