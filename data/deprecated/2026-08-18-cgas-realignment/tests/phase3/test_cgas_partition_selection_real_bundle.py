from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.phase3.cgas_characterization_bundle import parse_bundle
from scripts.phase3.cgas_partition_selection import derive_bundle_draft


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_PATH = REPOSITORY_ROOT / "tmp/.cgas-characterization/planning_cgas_v1-characterization-481.cgas"
SOURCE_PATH = REPOSITORY_ROOT / "data/curriculum_pddl/accepted_manifest.jsonl"
SUCCESSOR_BUNDLE_PATH = REPOSITORY_ROOT / "tmp/.cgas-characterization/cgas-state-gate-158105.cgas"
BUNDLE_SHA256 = "942d7be93ad0eb0ec6580bfe380fb8f09141662140ffc3d3c98e7f09a10ddaf4"
RUN_FINGERPRINT = "0856e76571643362abb70551ff9d4e02e2d585f7384fc3ac0adb64df240d893a"
ELIGIBLE_IDS = (
    "blocksworld-dev-easy-0000",
    "blocksworld-dev-easy-0007",
    "blocksworld-train-easy-0000",
    "blocksworld-train-easy-0001",
    "blocksworld-train-easy-0002",
    "blocksworld-train-easy-0003",
    "blocksworld-train-easy-0004",
    "blocksworld-train-easy-0005",
    "blocksworld-train-easy-0006",
    "blocksworld-train-easy-0007",
    "blocksworld-train-easy-0008",
    "blocksworld-train-easy-0009",
    "blocksworld-train-easy-0010",
    "blocksworld-train-easy-0011",
    "blocksworld-train-easy-0012",
    "blocksworld-train-easy-0070",
    "blocksworld-train-easy-0071",
    "blocksworld-train-easy-0072",
    "blocksworld-train-easy-0073",
    "blocksworld-train-easy-0099",
    "blocksworld-train-easy-0131",
    "blocksworld-train-easy-0139",
    "blocksworld-train-easy-0140",
    "blocksworld-train-easy-0145",
)


def test_real_bundle_fails_closed_with_all_ineligible_12_object_rows(tmp_path: Path) -> None:
    # Given: the immutable final characterization, source manifest, and prior owner-review draft.
    parsed = parse_bundle(BUNDLE_PATH.read_bytes())
    members = {member.name: member.contents for member in parsed.members}
    rows = [json.loads(line) for line in members["characterization.jsonl"].splitlines()]
    source_rows = [json.loads(line) for line in SOURCE_PATH.read_text(encoding="utf-8").splitlines() if line]

    # When: the selector produces an independent draft in a fresh test root.
    generated_path = tmp_path / "planning_cgas_v1-draft.json"
    generated = derive_bundle_draft(BUNDLE_PATH, generated_path)

    # Then: all identities are accounted for, the authoritative failure is deterministic, and no approval exists.
    eligible_ids = tuple(row["instance_id"] for row in rows if _paired_exact(row))
    row_ids = {row["instance_id"] for row in rows}
    source_ids = {row["instance_id"] for row in source_rows if row["domain_id"] == "blocksworld"}
    exclusions = _string_set(generated["exclusions"])
    assert hashlib.sha256(BUNDLE_PATH.read_bytes()).hexdigest() == BUNDLE_SHA256
    assert parsed.run_fingerprint == RUN_FINGERPRINT
    assert len(rows) == len(source_ids) == 481
    assert row_ids == source_ids
    assert eligible_ids == ELIGIBLE_IDS
    assert all(row["object_count"] == 4 for row in rows if row["instance_id"] in eligible_ids)
    assert all(not _paired_exact(row) for row in rows if row["object_count"] == 12)
    assert exclusions == row_ids - set(ELIGIBLE_IDS)
    assert len(exclusions) == 457
    assert generated["failure"] == "structural_ood_ineligible"
    assert generated["records"] == []
    assert generated["owner_approved"] is False
    assert "owner_approval_digest" not in generated
    assert json.loads(generated_path.read_text(encoding="utf-8")) == generated


def test_successor_bundle_is_still_blocked_by_signature_coverage(tmp_path: Path) -> None:
    # Given: the successor characterization candidate where all source rows are paired-exact but only three signatures exist.
    parsed = parse_bundle(SUCCESSOR_BUNDLE_PATH.read_bytes())
    members = {member.name: member.contents for member in parsed.members}
    rows = [json.loads(line) for line in members["characterization.jsonl"].splitlines()]

    # When: the selector derives a fresh owner-review draft from that characterization.
    output_path = tmp_path / "planning_cgas_v1-successor-draft.json"
    generated = derive_bundle_draft(SUCCESSOR_BUNDLE_PATH, output_path)

    # Then: the candidate remains blocked until the source population adds enough signature coverage.
    assert len(rows) == 481
    assert all(_paired_exact(row) for row in rows)
    assert len({row["composition_signature"] for row in rows}) == 3
    assert generated == json.loads(output_path.read_text(encoding="utf-8"))
    assert generated["failure"] == "structural_ood_coverage"
    assert generated["records"] == []
    assert generated["owner_approved"] is False
    assert "owner_approval_digest" not in generated


def _paired_exact(row: dict[str, object]) -> bool:
    return row["status"] == "characterized" and all(
        _planner_exact(row[key]) for key in ("bfs", "iw_width_1")
    )


def _planner_exact(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        value["source_eligibility"] == "eligible_complete_trace"
        and isinstance(value["exact_search"], dict)
        and value["exact_search"]["status"] == "exact_solution_replayed"
        and isinstance(value["replay"], dict)
        and value["replay"]["replay_ok"] is True
        and value["replay"]["goal_satisfied"] is True
    )


def _string_set(value: object) -> set[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise AssertionError("expected a list of string identities")
    return {item for item in value if isinstance(item, str)}
