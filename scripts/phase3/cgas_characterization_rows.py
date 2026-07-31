from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Final, Mapping, Sequence

from .cgas_partition_contracts import (
    CHARACTERIZATION_FILE,
    DEFAULT_LIMITS,
    MANIFEST_FILE,
    SCHEMA_VERSION,
    CharacterizationContractError,
    CharacterizationInput,
)
from .cgas_serialization import canonical, digest, digest_text, write_json, write_jsonl
from .local_planner_types import JSONValue, RecoveryPolicy
from .pddl import GroundAction, PDDLTask, replay_plan


CHARACTERIZATION_LIMITS: Final = {
    **DEFAULT_LIMITS,
    "local_iw_recovery": RecoveryPolicy.DISABLED,
    "max_trace_steps": 1,
}

__all__ = (
    "CHARACTERIZATION_LIMITS",
    "_base_row",
    "_object_count",
    "_path_digest",
    "_planner_record",
    "_retained_trace_count",
    "_source_record_digest",
    "_stack_height",
    "_state_descriptor",
    "canonical_composition_signature",
    "failure_row",
    "success_row",
    "write_characterization",
)


def write_characterization(
    rows: Sequence[dict[str, object]], output_root: Path, *, implementation_module: Path
) -> Path:
    """Write canonical rows and their digest-bound manifest without publication semantics."""
    output_root.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows, key=lambda row: str(row["instance_id"]))
    artifact = output_root / CHARACTERIZATION_FILE
    write_jsonl(artifact, ordered)
    manifest: dict[str, object] = {
        "artifact_sha256": digest(artifact),
        "counts_by_object": dict(sorted(Counter(_object_count(row) for row in ordered).items())),
        "counts_by_split": dict(sorted(Counter(str(row["split"]) for row in ordered).items())),
        "implementation": {
            "bfs_sha256": digest(implementation_module.with_name("cgas_bfs.py")),
            "iw_sha256": digest(implementation_module.with_name("local_iw.py")),
            "module_sha256": digest(implementation_module),
        },
        "limits": CHARACTERIZATION_LIMITS,
        "row_count": len(ordered),
        "schema_version": SCHEMA_VERSION,
        "source_records_sha256": digest_text("|".join(sorted(_source_record_digest(row) for row in ordered))),
    }
    write_json(output_root / MANIFEST_FILE, manifest)
    return artifact


def canonical_composition_signature(task: PDDLTask) -> str:
    """Return a name-invariant Blocksworld init/goal composition signature."""
    return canonical(
        {
            "goal": _state_descriptor(task.goal),
            "init": _state_descriptor(task.init),
            "object_count": len(task.objects_by_type.get("object", ())),
        }
    )


def success_row(
    instance: CharacterizationInput,
    task: PDDLTask,
    grounded: list[GroundAction],
    bfs_plan: tuple[str, ...],
    bfs_trace: Mapping[str, JSONValue],
    bfs_status: str,
    iw_plan: list[str],
    iw_trace: Mapping[str, JSONValue],
    iw_status: str,
) -> dict[str, object]:
    bfs_replay = replay_plan(task, list(bfs_plan), grounded_actions=grounded)
    iw_replay = replay_plan(task, iw_plan, grounded_actions=grounded)
    return {
        **_base_row(instance, task),
        "bfs": _planner_record(
            "scripts.phase3.cgas_bfs.run_fifo_bfs",
            bfs_plan,
            bfs_trace,
            bfs_status,
            bfs_replay,
            True,
        ),
        "failure_reason": None,
        "iw_width_1": _planner_record(
            "scripts.phase3.local_iw.run_iterated_width",
            iw_plan,
            iw_trace,
            iw_status,
            iw_replay,
            "plan_recovery" not in iw_trace,
        ),
        "partition": None,
        "status": "characterized",
    }


def failure_row(instance: CharacterizationInput, reason: str, *, task: PDDLTask | None = None) -> dict[str, object]:
    return {
        **_base_row(instance, task),
        "bfs": None,
        "failure_reason": reason,
        "iw_width_1": None,
        "partition": None,
        "status": "failed",
    }


def _base_row(instance: CharacterizationInput, task: PDDLTask | None) -> dict[str, object]:
    return {
        "composition_signature": canonical_composition_signature(task) if task else None,
        "domain_sha256": _path_digest(instance.domain_path),
        "goal_descriptor": _state_descriptor(task.goal) if task else None,
        "init_descriptor": _state_descriptor(task.init) if task else None,
        "instance_id": instance.instance_id,
        "object_count": len(task.objects_by_type.get("object", ())) if task else None,
        "problem_sha256": _path_digest(instance.problem_path),
        "schema_version": SCHEMA_VERSION,
        "source_identity": {"source_record_sha256": instance.source_record_sha256},
        "split": instance.split,
    }


def _planner_record(
    implementation: str, plan: Sequence[str], trace: Mapping[str, JSONValue], status: str, replay: dict[str, object], exact: bool
) -> dict[str, object]:
    replay_ok = replay.get("replay_ok") is True and replay.get("goal_satisfied") is True
    search_exact = exact and status in {"success_full_trace", "success_truncated_trace"} and replay_ok
    trace_complete = trace.get("trace_complete") is True
    retained_count = _retained_trace_count(trace)
    snapshot_budget = CHARACTERIZATION_LIMITS["max_trace_steps"]
    outcome = (
        "exact_search_complete_trace"
        if search_exact and trace_complete
        else "exact_search_bounded_trace"
        if search_exact
        else "search_not_exact"
    )
    source_eligibility = (
        "eligible_complete_trace"
        if outcome == "exact_search_complete_trace"
        else "ineligible_bounded_trace"
        if outcome == "exact_search_bounded_trace"
        else "ineligible_search_failure"
    )
    return {
        "characterization_outcome": outcome,
        "exact_search": {
            "expansion_count": _expansion_count(trace),
            "plan_length": len(plan),
            "status": "exact_solution_replayed" if search_exact else "not_exact_solution",
        },
        "implementation": implementation,
        "limits": CHARACTERIZATION_LIMITS,
        "plan": list(plan),
        "replay": replay,
        "retained_trace": {
            "retained_expansion_count": retained_count,
            "snapshot_budget": snapshot_budget,
            "status": "complete_transition_trace" if trace_complete else "bounded_snapshot",
            "trace_sha256": digest_text(canonical(trace)),
        },
        "source_eligibility": source_eligibility,
    }


def _expansion_count(trace: Mapping[str, JSONValue]) -> int:
    value = trace.get("expansion_count")
    if isinstance(value, int):
        return value
    events = trace.get("events")
    return sum(isinstance(event, dict) and event.get("decision") == "expand" for event in events) if isinstance(events, list) else 0


def _retained_trace_count(trace: Mapping[str, JSONValue]) -> int:
    expansions = trace.get("expansions")
    if isinstance(expansions, list):
        return len(expansions)
    events = trace.get("events")
    return len(events) if isinstance(events, list) else 0


def _state_descriptor(atoms: frozenset[tuple[str, ...]]) -> dict[str, object]:
    on_edges = sorted((atom[1], atom[2]) for atom in atoms if len(atom) == 3 and atom[0] == "on")
    ontable = {atom[1] for atom in atoms if len(atom) == 2 and atom[0] in {"ontable", "on-table"}}
    supports = {support: child for child, support in on_edges}
    stack_heights = sorted(_stack_height(root, supports) for root in ontable)
    return {
        "clear_count": sum(atom[0] == "clear" for atom in atoms),
        "handempty": ("handempty",) in atoms or ("arm-empty",) in atoms,
        "on_edges": len(on_edges),
        "ontable_count": len(ontable),
        "stack_heights": stack_heights,
    }


def _stack_height(root: str, supports: dict[str, str]) -> int:
    height = 1
    current = root
    while current in supports:
        current = supports[current]
        height += 1
    return height


def _path_digest(path: Path) -> str | None:
    return digest(path) if path.is_file() else None


def _object_count(row: dict[str, object]) -> int:
    value = row["object_count"]
    if not isinstance(value, int):
        raise CharacterizationContractError("missing_object_count")
    return value


def _source_record_digest(row: dict[str, object]) -> str:
    identity = row["source_identity"]
    if not isinstance(identity, dict):
        raise CharacterizationContractError("missing_source_identity")
    value = identity.get("source_record_sha256")
    if not isinstance(value, str):
        raise CharacterizationContractError("missing_source_record_sha256")
    return value
