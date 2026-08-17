from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from scripts.phase3.cgas_candidate_characterization_contracts import canonical_bytes, parse_canonical_model
from scripts.phase3.cgas_candidate_characterization_models import CheckpointModel, JsonObject
from scripts.phase3.cgas_pilot_manifest import (
    PilotManifestError,
    PilotManifestReport,
    PilotManifestRequest,
    PilotSelection,
    build_row_budget,
    publish_once,
    run,
    select_pilot_rows,
    validate_pilot_approval,
)
from scripts.phase3.cgas_pilot_scope_evidence import _rows

ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT = ROOT / "tmp/cgas-p0-characterized-v3/checkpoints/reservoir_checkpoint_000001.json"
SCOPE_REPORT = ROOT / ".claude/evidence/cgas-phase3-pilot-scope/report.json"
OWNER_APPROVAL = ROOT / ".claude/evidence/cgas-phase3-pilot-manifest/pilot-owner-approval.json"


def test_owner_approval_binds_exact_scope_report_and_v3_inputs(tmp_path: Path) -> None:
    # Given: the owner's canonical ruling and the exact signed-v3 scope report it approves.
    expected_digest = hashlib.sha256(OWNER_APPROVAL.read_bytes()).hexdigest()

    # When: the approval boundary validates the pair.
    actual_digest = validate_pilot_approval(SCOPE_REPORT, OWNER_APPROVAL)

    # Then: the approval identity is exact and a stale report binding is refused.
    assert actual_digest == expected_digest
    stale = TypeAdapter(JsonObject).validate_json(OWNER_APPROVAL.read_bytes())
    stale["scope_report_sha256"] = "0" * 64
    stale_path = tmp_path / "stale-approval.json"
    stale_path.write_bytes(canonical_bytes(stale) + b"\n")
    with pytest.raises(PilotManifestError, match="pilot_scope_report_mismatch"):
        validate_pilot_approval(SCOPE_REPORT, stale_path)


def test_selection_is_deterministic_and_proves_every_approved_clause() -> None:
    # Given: all 281 real characterization rows from the signed v3 checkpoint.
    rows = _real_rows()

    # When: selection receives either checkpoint order.
    first = select_pilot_rows(rows)
    second = select_pilot_rows(tuple(reversed(rows)))

    # Then: the same 90 source identities and balanced, isolated roles are selected.
    assert first == second
    assert len(first.records) == len({record.instance_id for record in first.records}) == 90
    assert Counter(record.object_count for record in first.records) == Counter({4: 30, 8: 30, 12: 30})
    assert Counter(record.role for record in first.records) == Counter({"train": 75, "held_out_calibration": 15})
    assert Counter((record.object_count, record.role) for record in first.records) == Counter(
        {
            (4, "train"): 25,
            (4, "held_out_calibration"): 5,
            (8, "train"): 25,
            (8, "held_out_calibration"): 5,
            (12, "train"): 25,
            (12, "held_out_calibration"): 5,
        }
    )
    roles_by_signature: defaultdict[str, set[str]] = defaultdict(set)
    for record in first.records:
        roles_by_signature[record.composition_signature].add(record.role)
        assert len(record.candidate_id) == len(record.source_record_sha256) == 64
    assert all(len(roles) == 1 for roles in roles_by_signature.values())
    assert _diversity(rows, first) == {4: (7, 5, 3), 8: (8, 10, 6), 12: (6, 8, 7)}


def test_selection_refuses_a_pool_below_the_approved_diversity_floor() -> None:
    # Given: the real checkpoint with all but four 12-object composition signatures removed.
    rows = _real_rows()
    signatures = sorted({str(row["composition_signature"]) for row in rows if row["object_count"] == 12})[:4]
    reduced = tuple(
        row
        for row in rows
        if row["object_count"] != 12 or str(row["composition_signature"]) in signatures
    )

    # When/Then: the approved five-repeated-signature floor is not relaxed.
    with pytest.raises(PilotManifestError, match="pilot_object_count_capacity_unavailable"):
        select_pilot_rows(reduced)


def test_row_budget_pins_fraction_harvest_stability_and_sampling_order() -> None:
    # Given: the deterministic real-checkpoint selection and its future manifest identity.
    selection = select_pilot_rows(_real_rows())

    # When: the row-budget contract is derived.
    budget = build_row_budget(selection, "a" * 64)

    # Then: no unapproved failure-rate assumption or production quota enters the pilot contract.
    assert budget["manifest_sha256"] == "a" * 64
    assert budget["harvest"] == "off_plan"
    assert budget["stability_bar"] == 10
    assert budget["held_out_fraction"] == {"denominator": 481, "numerator": 79}
    assert budget["matrix"] == {
        "certificate_family_count": 7,
        "minimum_failure_observations": 210,
        "object_count_count": 3,
        "total_cells": 21,
    }
    assert budget["source_instances"] == {"held_out_calibration": 15, "total": 90, "train": 75}
    assert budget["sampling_order"] == "object_count_then_role_then_raw_rank_then_candidate_id_then_trace_order"
    assert "failure_rate" not in budget


def test_publication_is_write_once_idempotent_and_collision_safe(tmp_path: Path) -> None:
    # Given: one absent canonical artifact path.
    destination = tmp_path / "manifest.json"

    # When: exact bytes are published and replayed.
    first_read_only = publish_once(destination, b"{\"version\":1}\n")
    identity = (destination.stat().st_ino, destination.stat().st_mtime_ns)
    second_read_only = publish_once(destination, b"{\"version\":1}\n")

    # Then: replay preserves identity and conflicting bytes fail closed.
    assert first_read_only is False
    assert second_read_only is True
    assert (destination.stat().st_ino, destination.stat().st_mtime_ns) == identity
    with pytest.raises(PilotManifestError, match="pilot_publication_collision"):
        publish_once(destination, b"{\"version\":2}\n")


def test_run_real_v3_publishes_only_digest_bound_pilot_contracts(tmp_path: Path) -> None:
    # Given: the real signed v3 round, exact owner approval, and a fresh evidence root.
    request = PilotManifestRequest(
        ROOT,
        ROOT / "tmp/cgas-p0-characterized-v3",
        ROOT / ".claude/evidence/cgas-trace-contract-v3/approved-trace-v3.json",
        ROOT / "configs/cgas/production_p0_candidates.json",
        SCOPE_REPORT,
        OWNER_APPROVAL,
        tmp_path / "pilot",
    )
    checkpoint_before = CHECKPOINT.read_bytes()

    # When: the complete boundary runs twice over the same inputs.
    first = run(request)
    identities = tuple((path.stat().st_ino, path.stat().st_mtime_ns) for path in _report_paths(first))
    second = run(request)

    # Then: only the three approved contract artifacts exist and replay is byte-identical/read-only.
    manifest = TypeAdapter(JsonObject).validate_json(first.manifest_path.read_bytes())
    bindings = TypeAdapter(JsonObject).validate_python(manifest["bindings"])
    budget = TypeAdapter(JsonObject).validate_json(first.row_budget_path.read_bytes())
    report = TypeAdapter(JsonObject).validate_json(first.report_path.read_bytes())
    assert first.read_only is False
    assert second.read_only is True
    assert sorted(path.name for path in request.output_root.iterdir()) == [
        "pilot-manifest-report.json",
        "pilot-row-budget.json",
        "pilot-source-manifest.json",
    ]
    assert tuple((path.stat().st_ino, path.stat().st_mtime_ns) for path in _report_paths(second)) == identities
    assert manifest["schema_version"] == "cgas_phase3_pilot_source_manifest_v1"
    assert bindings["pilot_approval_implementation_sha256"] == hashlib.sha256(
        (ROOT / "scripts/phase3/cgas_pilot_manifest_approval.py").read_bytes()
    ).hexdigest()
    assert len(TypeAdapter(list[JsonObject]).validate_python(manifest["records"])) == 90
    assert budget["manifest_sha256"] == hashlib.sha256(first.manifest_path.read_bytes()).hexdigest()
    assert report["owner_approval_sha256"] == hashlib.sha256(OWNER_APPROVAL.read_bytes()).hexdigest()
    assert CHECKPOINT.read_bytes() == checkpoint_before


def _report_paths(report: PilotManifestReport) -> tuple[Path, Path, Path]:
    return report.manifest_path, report.row_budget_path, report.report_path


def _real_rows() -> tuple[JsonObject, ...]:
    checkpoint, _ = parse_canonical_model(CHECKPOINT, CheckpointModel, "pilot_test_checkpoint_invalid")
    return _rows(checkpoint, CHECKPOINT)


def _diversity(rows: tuple[JsonObject, ...], selection: PilotSelection) -> dict[int, tuple[int, int, int]]:
    by_id = {str(row["instance_id"]): row for row in rows}
    result: dict[int, tuple[int, int, int]] = {}
    for object_count in (4, 8, 12):
        chosen = [by_id[record.instance_id] for record in selection.records if record.object_count == object_count]
        signatures = Counter(str(row["composition_signature"]) for row in chosen)
        profiles = {
            tuple(TypeAdapter(list[int]).validate_python(TypeAdapter(JsonObject).validate_python(row["init_descriptor"])["stack_heights"]))
            for row in chosen
        }
        goals = {
            TypeAdapter(int).validate_python(TypeAdapter(JsonObject).validate_python(row["goal_descriptor"])["on_edges"])
            for row in chosen
        }
        result[object_count] = (sum(count >= 2 for count in signatures.values()), len(profiles), len(goals))
    return result
