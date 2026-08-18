from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.phase3.cgas_partition_selection import (
    SelectionFeasibilityError,
    build_draft,
    select_rows,
)
from scripts.phase3.cgas_partition_approval import approve_draft


def _row(
    instance_id: str,
    *,
    object_count: int = 4,
    signature: str = "sig-a",
    bfs_length: int = 1,
    iw_length: int = 1,
    bfs_expansions: int = 2,
    iw_expansions: int = 2,
    exact: bool = True,
) -> dict[str, object]:
    eligibility = "eligible_complete_trace" if exact else "ineligible_bounded_trace"
    return {
        "instance_id": instance_id,
        "object_count": object_count,
        "composition_signature": signature,
        "source_identity": {"source_record_sha256": hashlib.sha256(instance_id.encode()).hexdigest()},
        "split": "train",
        "status": "characterized",
        "bfs": {
            "source_eligibility": eligibility,
            "exact_search": {"plan_length": bfs_length, "expansion_count": bfs_expansions, "status": "exact_solution_replayed"},
            "replay": {"replay_ok": True, "goal_satisfied": True},
        },
        "iw_width_1": {
            "source_eligibility": eligibility,
            "exact_search": {"plan_length": iw_length, "expansion_count": iw_expansions, "status": "exact_solution_replayed"},
            "replay": {"replay_ok": True, "goal_satisfied": True},
        },
    }


def _feasible_rows() -> tuple[dict[str, object], ...]:
    group_sizes = (2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 19, 20, 20, 20, 20, 21)
    rows: list[dict[str, object]] = []
    for group_index, group_size in enumerate(group_sizes):
        for _ in range(group_size):
            index = len(rows)
            high = group_index < 10
            rows.append(
                _row(
                    f"row-{index:03}",
                    object_count=12 if high else 4,
                    signature=f"sig-{group_index:02}",
                    bfs_length=10 if high else 0,
                    iw_length=10 if high else 0,
                    bfs_expansions=40 if high else 0,
                    iw_expansions=40 if high else 0,
                )
            )
    return tuple(rows)


def test_select_rows_fails_closed_when_all_12_block_rows_are_not_paired_exact() -> None:
    # Given: a required structural-OOD member whose IW trace is incomplete.
    rows = (_row("four"), _row("twelve", object_count=12, exact=False))

    # When: selection evaluates eligibility before assigning any roles.
    with pytest.raises(SelectionFeasibilityError, match="structural_ood_ineligible"):
        select_rows(rows)

    # Then: the selection cannot weaken the exactness requirement.


def test_select_rows_keeps_complete_horizon_and_branching_ties() -> None:
    # Given: 12-block rows and equal boundary metrics that must stay together.
    rows = _feasible_rows()

    # When: the structural OOD union is selected.
    result = select_rows(rows)

    # Then: both members tied at a selected 90th-percentile boundary are OOD.
    roles = {record.instance_id: record.role for record in result.records}
    assert roles["row-018"] == "structural_ood"
    assert roles["row-019"] == "structural_ood"


def test_select_rows_never_splits_a_composition_signature_across_roles() -> None:
    # Given: enough whole composition groups to satisfy all role minima.
    rows = _feasible_rows()

    # When: roles are selected.
    result = select_rows(rows)

    # Then: every signature belongs to exactly one role.
    by_signature: dict[str, set[str]] = {}
    for record in result.records:
        by_signature.setdefault(record.composition_signature, set()).add(record.role)
    assert all(len(roles) == 1 for roles in by_signature.values())


def test_build_draft_is_reverse_input_deterministic_and_unapproved() -> None:
    # Given: a feasible fixture and immutable input bindings.
    rows = _feasible_rows()

    # When: the same rows arrive in opposite orders.
    first = build_draft(rows, "a" * 64, "b" * 64, "c" * 64)
    second = build_draft(tuple(reversed(rows)), "a" * 64, "b" * 64, "c" * 64)

    # Then: the review artifact is identical and contains no approval digest.
    assert first == second
    assert first["owner_approved"] is False
    assert "owner_approval_digest" not in first


def test_approve_draft_rejects_empty_fail_closed_current_receipt(tmp_path: Path) -> None:
    # Given: the current owner-review receipt has no role records and names the hard blocker.
    draft = build_draft_for_failure("structural_ood_ineligible")
    draft_path = tmp_path / "empty-draft.json"
    approval_path = tmp_path / "approval.json"
    output_path = tmp_path / "approved.json"
    _write_json(draft_path, draft)
    _write_json(
        approval_path,
        {
            "draft_sha256": hashlib.sha256(draft_path.read_bytes()).hexdigest(),
            "owner_approved": True,
            "policy_sha256": draft["policy_sha256"],
            "record_count": 0,
            "schema_version": "cgas_partition_owner_approval_v1",
        },
    )

    # When: an approval artifact is presented for the empty draft.
    with pytest.raises(SelectionFeasibilityError, match="partition_records_empty"):
        approve_draft(draft_path, approval_path, output_path)

    # Then: no approved partition can be emitted from the fail-closed receipt.
    assert not output_path.exists()


def test_approve_draft_requires_exact_owner_artifact_for_non_empty_partition(tmp_path: Path) -> None:
    # Given: a feasible future draft and a mismatched owner approval artifact.
    draft_path = tmp_path / "draft.json"
    approval_path = tmp_path / "approval.json"
    output_path = tmp_path / "approved.json"
    draft = build_draft(_feasible_rows(), "a" * 64, "b" * 64, "c" * 64)
    _write_json(draft_path, draft)
    _write_json(
        approval_path,
        {
            "draft_sha256": "0" * 64,
            "owner_approved": True,
            "policy_sha256": draft["policy_sha256"],
            "record_count": len(_records(draft["records"])),
            "schema_version": "cgas_partition_owner_approval_v1",
        },
    )

    # When: the approval digest does not bind to the exact draft bytes.
    with pytest.raises(SelectionFeasibilityError, match="owner_approval_draft_mismatch"):
        approve_draft(draft_path, approval_path, output_path)

    # Then: the future partition remains a draft until the owner signs this artifact exactly.
    assert not output_path.exists()


def test_approve_draft_emits_owner_bound_non_empty_partition(tmp_path: Path) -> None:
    # Given: a feasible future draft and an exact owner approval artifact.
    draft_path = tmp_path / "draft.json"
    approval_path = tmp_path / "approval.json"
    output_path = tmp_path / "approved.json"
    draft = build_draft(_feasible_rows(), "a" * 64, "b" * 64, "c" * 64)
    _write_json(draft_path, draft)
    approval = {
        "draft_sha256": hashlib.sha256(draft_path.read_bytes()).hexdigest(),
        "owner_approved": True,
        "policy_sha256": draft["policy_sha256"],
        "record_count": len(_records(draft["records"])),
        "schema_version": "cgas_partition_owner_approval_v1",
    }
    _write_json(approval_path, approval)

    # When: the approval gate consumes both artifacts.
    approved = approve_draft(draft_path, approval_path, output_path)

    # Then: the persisted partition is non-empty, explicitly approved, and bound to the approval bytes.
    assert approved == json.loads(output_path.read_text(encoding="utf-8"))
    assert approved["owner_approved"] is True
    assert approved["owner_approval_digest"] == hashlib.sha256(approval_path.read_bytes()).hexdigest()
    assert approved["status"] == "approved_p0_partition"
    assert len(_records(approved["records"])) == len(_records(draft["records"]))


def test_build_draft_reports_missing_ids_and_calibration_coverage_failure() -> None:
    # Given: a duplicate immutable source identity and too few remaining rows for calibration.
    duplicate = _row("duplicate", object_count=12)
    rows = (duplicate, duplicate)

    # When: the draft boundary validates the complete population.
    with pytest.raises(SelectionFeasibilityError, match="duplicate_instance_id"):
        build_draft(rows, "a" * 64, "b" * 64, "c" * 64)

    # Then: no ambiguous or under-covered draft is emitted.


def build_draft_for_failure(reason: str) -> dict[str, object]:
    return {
        "characterization_artifact_sha256": "b" * 64,
        "exclusions": ["blocksworld-train-hard-0000"],
        "failure": reason,
        "implementation_sha256": "c" * 64,
        "owner_approved": False,
        "policy": "paired_exact_v1:ood12+p90_horizon+p90_branching+hashed_groups:fps_gower39:grouped_80_10_10",
        "policy_sha256": hashlib.sha256("paired_exact_v1:ood12+p90_horizon+p90_branching+hashed_groups:fps_gower39:grouped_80_10_10".encode()).hexdigest(),
        "records": [],
        "source_manifest_sha256": "a" * 64,
        "status": "draft_for_owner_review",
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _records(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise AssertionError("expected record list")
    return tuple(item for item in value)


def test_select_rows_rejects_missing_or_overlapping_immutable_identities() -> None:
    # Given: rows with a missing instance identity and duplicated source identity.
    missing = _row("missing")
    missing.pop("instance_id")
    first = _row("first")
    second = _row("second")
    second["source_identity"] = first["source_identity"]

    # When: the identity boundary consumes each invalid input.
    with pytest.raises(SelectionFeasibilityError, match="invalid_instance_id"):
        select_rows((missing,))
    with pytest.raises(SelectionFeasibilityError, match="duplicate_source_identity"):
        select_rows((first, second))

    # Then: neither missing nor overlapping immutable identities are accepted.


def test_select_rows_rejects_unsplittable_exact_calibration_coverage() -> None:
    # Given: complete structural OOD coverage but only a 40-row remaining composition group.
    ood = tuple(
        _row(f"ood-{index:02}", object_count=12, signature=f"ood-signature-{index // 2}", bfs_length=10, iw_length=10, bfs_expansions=10, iw_expansions=10)
        for index in range(20)
    )
    rows = ood + tuple(_row(f"remaining-{index:02}", signature="remaining") for index in range(40))

    # When: calibration requires exactly 39 rows without splitting a composition group.
    with pytest.raises(SelectionFeasibilityError, match="calibration_exact_39_unavailable"):
        select_rows(rows)

    # Then: the minimum remains strict rather than splitting or weakening the group.
