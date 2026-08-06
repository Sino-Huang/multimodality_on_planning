from __future__ import annotations

import json
from collections import Counter
from typing import Sequence

from .cgas_candidate_characterization_models import JsonObject
from .cgas_partition_selection import RoleRecord, SelectionFeasibilityError


def accepted_manifest(rows: tuple[JsonObject, ...], records: Sequence[RoleRecord]) -> bytes:
    if len(records) != 481:
        raise SelectionFeasibilityError("exact_population_481_unavailable")
    if sum(record.role == "calibration" for record in records) != 39:
        raise SelectionFeasibilityError("calibration_exact_39_unavailable")
    by_id = {str(row.get("instance_id")): row for row in rows}
    if len(by_id) != len(rows) or len({record.instance_id for record in records}) != len(records):
        raise SelectionFeasibilityError("selector_manifest_identity_overlap")
    selected: list[JsonObject] = []
    for record in records:
        row = by_id.get(record.instance_id)
        if row is None:
            raise SelectionFeasibilityError("selector_manifest_row_missing")
        if not _paired_exact(row):
            raise SelectionFeasibilityError("accepted_manifest_authoritative_parity_unavailable")
        identity = row.get("source_identity")
        source_digest = identity.get("source_record_sha256") if isinstance(identity, dict) else None
        if (
            source_digest != record.source_record_sha256
            or row.get("composition_signature") != record.composition_signature
            or row.get("split") != record.source_split
        ):
            raise SelectionFeasibilityError("selector_manifest_parity_invalid")
        role = {"calibration": "dev", "structural_ood": "test"}.get(record.role, record.role)
        if role not in {"train", "dev", "test"}:
            raise SelectionFeasibilityError("selector_role_invalid")
        selected.append({**row, "split": role})
    split_counts = Counter(str(row["split"]) for row in selected)
    object_counts = Counter(_required_integer(row, "object_count") for row in selected)
    matrix = Counter((str(row["split"]), _required_integer(row, "object_count")) for row in selected)
    if split_counts != Counter({"train": 402, "dev": 39, "test": 40}):
        raise SelectionFeasibilityError("production_split_quota_invalid")
    if object_counts != Counter({4: 190, 8: 198, 12: 93}):
        raise SelectionFeasibilityError("production_object_quota_invalid")
    expected_matrix = Counter(
        {("train", 4): 190, ("train", 8): 198, ("train", 12): 14, ("dev", 12): 39, ("test", 12): 40}
    )
    if matrix != expected_matrix:
        raise SelectionFeasibilityError("production_quota_matrix_invalid")
    signatures: dict[str, str] = {}
    for row in selected:
        signature = str(row["composition_signature"])
        split = str(row["split"])
        if signature in signatures and signatures[signature] != split:
            raise SelectionFeasibilityError("production_signature_split_overlap")
        signatures[signature] = split
    if len({signature for signature, split in signatures.items() if split == "test"}) < 10:
        raise SelectionFeasibilityError("production_ood_signature_coverage")
    rows_jsonl = "".join(
        json.dumps(row, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
        for row in sorted(selected, key=lambda item: str(item["instance_id"]))
    )
    return rows_jsonl.encode()


def _required_integer(row: JsonObject, key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SelectionFeasibilityError(f"invalid_{key}")
    return value


def _paired_exact(row: JsonObject) -> bool:
    if row.get("status") != "characterized":
        return False
    for key in ("bfs", "iw_width_1"):
        planner = row.get(key)
        if not isinstance(planner, dict):
            return False
        exact = planner.get("exact_search")
        replay = planner.get("replay")
        if (
            not isinstance(exact, dict)
            or not isinstance(replay, dict)
            or planner.get("source_eligibility") != "eligible_complete_trace"
            or exact.get("status") != "exact_solution_replayed"
            or replay.get("replay_ok") is not True
            or replay.get("goal_satisfied") is not True
        ):
            return False
    return True
