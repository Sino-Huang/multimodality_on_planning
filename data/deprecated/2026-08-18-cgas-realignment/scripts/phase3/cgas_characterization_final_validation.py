from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

from .cgas_characterization_rows import CHARACTERIZATION_LIMITS
from .cgas_partition_characterization import _characterize
from .cgas_partition_contracts import CharacterizationInput, EXPECTED_ROW_COUNT, SCHEMA_VERSION
from .cgas_serialization import canonical, digest_text
from .pddl import GroundAction, PDDLTask, ground_actions, parse_task, replay_plan


def expected_characterization_rows(payload: dict[str, object], repository: Path) -> tuple[dict[str, object], ...]:
    """Recompute the authoritative characterization rows through the unchanged kernel."""
    records = _mapping(_mapping(payload["source"], "contract_source")["records"], "contract_records")
    return tuple(
        _characterize(CharacterizationInput(instance_id, _text(record.get("split"), "source_split"), repository / _text(record.get("domain_path"), "domain_path"), repository / _text(record.get("problem_path"), "problem_path"), _text(record.get("source_record_sha256"), "source_digest")))
        for instance_id, raw_record in sorted(records.items())
        for record in (_mapping(raw_record, "source_record"),)
    )


def verify_final(rows: tuple[dict[str, object], ...], rows_bytes: bytes, manifest: dict[str, object], payload: dict[str, object], repository: Path, expected_rows: tuple[dict[str, object], ...]) -> None:
    """Validate canonical final rows against current source, planners, and manifest inputs."""
    records = _mapping(_mapping(payload["source"], "contract_source")["records"], "contract_records")
    if len(rows) != EXPECTED_ROW_COUNT or tuple(_text(row.get("instance_id"), "row_instance") for row in rows) != tuple(sorted(records)):
        raise ValueError("final_instance_coverage")
    if tuple(canonical(row).encode() for row in rows) != tuple(canonical(row).encode() for row in expected_rows):
        raise ValueError("final_row_recomputation_mismatch")
    for row in rows:
        _verify_row(row, records, repository)
    _verify_manifest(manifest, rows_bytes, rows, repository)


def _verify_row(row: dict[str, object], records: dict[str, object], repository: Path) -> None:
    instance_id = _text(row.get("instance_id"), "row_instance")
    source = _mapping(records[instance_id], "source_record")
    if row.get("partition") is not None or row.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("row_terminal_contract")
    for key in ("split", "domain_sha256", "problem_sha256"):
        if row.get(key) != source.get(key):
            raise ValueError(f"row_{key}_mismatch")
    if _mapping(row.get("source_identity"), "source_identity").get("source_record_sha256") != source.get("source_record_sha256"):
        raise ValueError("row_source_digest_mismatch")
    match row.get("status"):
        case "failed":
            if not isinstance(row.get("failure_reason"), str) or row.get("bfs") is not None or row.get("iw_width_1") is not None:
                raise ValueError("row_failure_contract")
            return
        case "characterized":
            if row.get("failure_reason") is not None:
                raise ValueError("row_terminal_contract")
        case _:
            raise ValueError("row_terminal_contract")
    task = parse_task(repository / _text(source.get("domain_path"), "domain_path"), repository / _text(source.get("problem_path"), "problem_path"))
    grounded, status = ground_actions(task, max_grounded_actions=CHARACTERIZATION_LIMITS["max_grounded_actions"], max_grounded_atoms=CHARACTERIZATION_LIMITS["max_grounded_atoms"])
    if status is not None or task.unsupported_features:
        raise ValueError("row_pddl_not_replayable")
    _planner(_mapping(row.get("bfs"), "bfs"), "scripts.phase3.cgas_bfs.run_fifo_bfs", task, grounded)
    _planner(_mapping(row.get("iw_width_1"), "iw"), "scripts.phase3.local_iw.run_iterated_width", task, grounded)


def _planner(record: dict[str, object], implementation: str, task: PDDLTask, grounded: list[GroundAction]) -> None:
    if set(record) != {"characterization_outcome", "exact_search", "implementation", "limits", "plan", "replay", "retained_trace", "source_eligibility"}:
        raise ValueError("planner_oracle_or_recovery_field")
    plan = record.get("plan")
    if not isinstance(plan, list) or not all(isinstance(action, str) for action in plan) or record.get("implementation") != implementation or record.get("limits") != CHARACTERIZATION_LIMITS:
        raise ValueError("planner_policy")
    exact = _mapping(record.get("exact_search"), "exact_search")
    retained = _mapping(record.get("retained_trace"), "retained_trace")
    if exact.get("plan_length") != len(plan) or retained.get("snapshot_budget") != CHARACTERIZATION_LIMITS["max_trace_steps"]:
        raise ValueError("planner_exact_metadata")
    match exact.get("status"):
        case "exact_solution_replayed":
            replay = replay_plan(task, plan, grounded_actions=grounded)
            complete = retained.get("status") == "complete_transition_trace"
            outcome = "exact_search_complete_trace" if complete else "exact_search_bounded_trace"
            eligibility = "eligible_complete_trace" if complete else "ineligible_bounded_trace"
            if replay != record.get("replay") or replay.get("replay_ok") is not True or replay.get("goal_satisfied") is not True or record.get("characterization_outcome") != outcome or record.get("source_eligibility") != eligibility:
                raise ValueError("planner_success_contract")
        case "not_exact_solution":
            replay = _mapping(record.get("replay"), "planner_replay")
            if plan or replay.get("replay_ok") is True or replay.get("goal_satisfied") is True or record.get("characterization_outcome") != "search_not_exact" or record.get("source_eligibility") != "ineligible_search_failure":
                raise ValueError("planner_nonexact_contract")
        case _:
            raise ValueError("planner_exact_status")


def _verify_manifest(manifest: dict[str, object], rows_bytes: bytes, rows: tuple[dict[str, object], ...], repository: Path) -> None:
    files = {"bfs_sha256": "scripts/phase3/cgas_bfs.py", "iw_sha256": "scripts/phase3/local_iw.py", "module_sha256": "scripts/phase3/cgas_partition_characterization.py"}
    expected = {"artifact_sha256": hashlib.sha256(rows_bytes).hexdigest(), "counts_by_object": {str(key): value for key, value in sorted(Counter(row["object_count"] for row in rows).items())}, "counts_by_split": dict(sorted(Counter(_text(row["split"], "row_split") for row in rows).items())), "implementation": {key: hashlib.sha256((repository / path).read_bytes()).hexdigest() for key, path in files.items()}, "limits": CHARACTERIZATION_LIMITS, "owner_approved": False, "row_count": len(rows), "schema_version": SCHEMA_VERSION, "source_records_sha256": digest_text("|".join(sorted(_source_digest(row) for row in rows)))}
    if set(manifest) != set(expected) or manifest.get("owner_approved") is not False:
        raise ValueError("manifest_owner_approved")
    if manifest != expected:
        raise ValueError("manifest_recomputation")


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"invalid_{label}")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"invalid_{label}")
    return value


def _source_digest(row: dict[str, object]) -> str:
    return _text(_mapping(row["source_identity"], "source_identity").get("source_record_sha256"), "source_record_digest")
