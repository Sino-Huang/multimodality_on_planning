from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Sequence

from .cgas_characterization_bundle import parse_bundle
from .cgas_serialization import digest, write_json

CALIBRATION_SIZE: Final = 39
MIN_EVALUATION_ROWS: Final = 20
MIN_OOD_SIGNATURES: Final = 10
POLICY: Final = "paired_exact_v1:ood12+p90_horizon+p90_branching+hashed_groups:fps_gower39:grouped_80_10_10"


@dataclass(frozen=True, slots=True)
class SelectionFeasibilityError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class RoleRecord:
    instance_id: str; source_record_sha256: str; source_split: str; composition_signature: str; role: str


@dataclass(frozen=True, slots=True)
class Selection:
    records: tuple[RoleRecord, ...]
    exclusions: tuple[str, ...]


def select_rows(rows: Sequence[dict[str, object]]) -> Selection:
    """Select disjoint draft roles from complete paired-exact characterization rows."""
    ordered = tuple(sorted(rows, key=_instance_id))
    if len({_instance_id(row) for row in ordered}) != len(ordered):
        raise SelectionFeasibilityError("duplicate_instance_id")
    if len({_text(_mapping(row["source_identity"], "source_identity")["source_record_sha256"], "source_record_sha256") for row in ordered}) != len(ordered):
        raise SelectionFeasibilityError("duplicate_source_identity")
    eligible, exclusions = _paired_exact(ordered)
    ood = _structural_ood(eligible)
    groups = _groups(tuple(row for row in eligible if _instance_id(row) not in ood))
    calibration = _exact_group_subset(groups, CALIBRATION_SIZE)
    remaining = {signature: members for signature, members in groups.items() if signature not in calibration}
    development, test = _evaluation_groups(remaining)
    roles = {instance_id: "structural_ood" for instance_id in ood}
    roles.update({instance_id: "calibration" for instance_id in _group_ids(groups, calibration)})
    roles.update({instance_id: "dev" for instance_id in _group_ids(remaining, development)})
    roles.update({instance_id: "test" for instance_id in _group_ids(remaining, test)})
    roles.update({instance_id: "train" for instance_id in _group_ids(remaining, set(remaining) - development - test)})
    if len(roles) != len(eligible):
        raise SelectionFeasibilityError("role_coverage")
    return Selection(tuple(_record(row, roles[_instance_id(row)]) for row in eligible), tuple(sorted(exclusions)))


def build_draft(rows: Sequence[dict[str, object]], source_digest: str, characterization_digest: str, implementation_digest: str) -> dict[str, object]:
    """Build one deterministic unapproved owner-review manifest in memory."""
    _digest(source_digest, "source_digest")
    _digest(characterization_digest, "characterization_digest")
    _digest(implementation_digest, "implementation_digest")
    selection = select_rows(rows)
    records = [
        {
            "composition_signature": record.composition_signature,
            "instance_id": record.instance_id,
            "role": record.role,
            "source_record_sha256": record.source_record_sha256,
            "source_split": record.source_split,
        }
        for record in sorted(selection.records, key=lambda item: item.instance_id)
    ]
    _audit(records)
    return {
        "characterization_artifact_sha256": characterization_digest,
        "exclusions": list(selection.exclusions),
        "implementation_sha256": implementation_digest,
        "owner_approved": False,
        "policy": POLICY,
        "policy_sha256": hashlib.sha256(POLICY.encode()).hexdigest(),
        "records": records,
        "source_manifest_sha256": source_digest,
        "status": "draft_for_owner_review",
    }


def derive_bundle_draft(bundle_path: Path, output_path: Path) -> dict[str, object]:
    """Parse a final characterization bundle and persist one local draft manifest."""
    contents = bundle_path.read_bytes()
    parsed = parse_bundle(contents)
    members = {member.name: member.contents for member in parsed.members}
    contract = _mapping(json.loads(members["run-contract.json"]), "run_contract")
    manifest = _mapping(json.loads(members["characterization_manifest.json"]), "manifest")
    rows = tuple(_mapping(json.loads(line), "row") for line in members["characterization.jsonl"].splitlines())
    source = _mapping(contract["source"], "contract_source")
    source_digest = _text(source["manifest_sha256"], "source_manifest_sha256")
    artifact_digest = _text(manifest["artifact_sha256"], "artifact_sha256")
    implementation_digest = digest(Path(__file__))
    try:
        draft = build_draft(rows, source_digest, artifact_digest, implementation_digest)
    except SelectionFeasibilityError as error:
        draft = _failed_draft(rows, source_digest, artifact_digest, implementation_digest, str(error))
    write_json(output_path, draft)
    return draft


def _paired_exact(rows: Sequence[dict[str, object]]) -> tuple[tuple[dict[str, object], ...], list[str]]:
    eligible: list[dict[str, object]] = []
    exclusions: list[str] = []
    for row in rows:
        if _is_paired_exact(row):
            eligible.append(row)
        else:
            exclusions.append(_instance_id(row))
    ineligible_12 = [row for row in rows if _integer(row["object_count"], "object_count") == 12 and row not in eligible]
    if ineligible_12:
        raise SelectionFeasibilityError("structural_ood_ineligible")
    return tuple(eligible), exclusions


def _structural_ood(rows: Sequence[dict[str, object]]) -> set[str]:
    if not rows:
        raise SelectionFeasibilityError("no_paired_exact_rows")
    horizon = _percentile([max(_metric(row, "bfs", "plan_length"), _metric(row, "iw_width_1", "plan_length")) for row in rows])
    branching = _percentile([max(_metric(row, "bfs", "expansion_count"), _metric(row, "iw_width_1", "expansion_count")) for row in rows])
    selected = {
        _instance_id(row)
        for row in rows
        if _integer(row["object_count"], "object_count") == 12
        or max(_metric(row, "bfs", "plan_length"), _metric(row, "iw_width_1", "plan_length")) >= horizon
        or max(_metric(row, "bfs", "expansion_count"), _metric(row, "iw_width_1", "expansion_count")) >= branching
    }
    by_signature = _groups(rows)
    selected_signatures = {_signature(row) for row in rows if _instance_id(row) in selected}
    selected.update(_group_ids(by_signature, selected_signatures))
    for signature in sorted(by_signature, key=lambda value: hashlib.sha256(value.encode()).hexdigest()):
        if len(selected) >= MIN_EVALUATION_ROWS and len(selected_signatures) >= MIN_OOD_SIGNATURES:
            break
        selected.update(_instance_id(row) for row in by_signature[signature])
        selected_signatures.add(signature)
    if len(selected) < MIN_EVALUATION_ROWS or len(selected_signatures) < MIN_OOD_SIGNATURES:
        raise SelectionFeasibilityError("structural_ood_coverage")
    return selected


def _exact_group_subset(groups: dict[str, tuple[dict[str, object], ...]], target: int) -> set[str]:
    choices: dict[int, tuple[str, ...]] = {0: ()}
    for signature in _gower_group_order(groups):
        size = len(groups[signature])
        for count, selected in tuple(sorted(choices.items(), reverse=True)):
            if count + size <= target and count + size not in choices:
                choices[count + size] = (*selected, signature)
    if target not in choices:
        raise SelectionFeasibilityError("calibration_exact_39_unavailable")
    return set(choices[target])


def _evaluation_groups(groups: dict[str, tuple[dict[str, object], ...]]) -> tuple[set[str], set[str]]:
    target = max(MIN_EVALUATION_ROWS, round(sum(len(group) for group in groups.values()) / 10))
    development = _nearest_group_subset(groups, target, set())
    test = _nearest_group_subset(groups, target, development)
    if len(_group_ids(groups, development)) < MIN_EVALUATION_ROWS or len(_group_ids(groups, test)) < MIN_EVALUATION_ROWS:
        raise SelectionFeasibilityError("dev_test_minimum_unavailable")
    return development, test


def _nearest_group_subset(groups: dict[str, tuple[dict[str, object], ...]], target: int, forbidden: set[str]) -> set[str]:
    selected: set[str] = set()
    count = 0
    for signature in sorted((key for key in groups if key not in forbidden), key=lambda value: hashlib.sha256(value.encode()).hexdigest()):
        size = len(groups[signature])
        if count < target or abs(count + size - target) < abs(count - target):
            selected.add(signature)
            count += size
    return selected


def _gower_group_order(groups: dict[str, tuple[dict[str, object], ...]]) -> tuple[str, ...]:
    available = set(groups)
    first = min(available, key=lambda signature: _instance_id(groups[signature][0]))
    ordered = [first]
    available.remove(first)
    while available:
        selected = tuple(ordered)
        distances = {signature: min(_gower(groups[signature][0], groups[chosen][0], groups) for chosen in selected) for signature in available}
        best_distance = max(distances.values())
        next_signature = min(signature for signature, value in distances.items() if value == best_distance)
        ordered.append(next_signature)
        available.remove(next_signature)
    return tuple(ordered)


def _gower(left: dict[str, object], right: dict[str, object], groups: dict[str, tuple[dict[str, object], ...]]) -> float:
    population = tuple(row for members in groups.values() for row in members)
    features = (
        (lambda row: _integer(row["object_count"], "object_count")),
        (lambda row: _metric(row, "bfs", "plan_length")),
        (lambda row: _metric(row, "iw_width_1", "plan_length")),
        (lambda row: _metric(row, "bfs", "expansion_count")),
        (lambda row: _metric(row, "iw_width_1", "expansion_count")),
    )
    distance = 0.0
    for feature in features:
        values = [feature(row) for row in population]
        span = max(values) - min(values)
        distance += 0.0 if span == 0 else abs(feature(left) - feature(right)) / span
    return distance / len(features)


def _is_paired_exact(row: dict[str, object]) -> bool:
    return row.get("status") == "characterized" and all(
        _planner_exact(_mapping(row[key], key)) for key in ("bfs", "iw_width_1")
    )


def _planner_exact(planner: dict[str, object]) -> bool:
    exact = _mapping(planner["exact_search"], "exact_search")
    replay = _mapping(planner["replay"], "replay")
    return planner.get("source_eligibility") == "eligible_complete_trace" and exact.get("status") == "exact_solution_replayed" and replay.get("replay_ok") is True and replay.get("goal_satisfied") is True


def _groups(rows: Sequence[dict[str, object]]) -> dict[str, tuple[dict[str, object], ...]]:
    grouped: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[_signature(row)].append(row)
    return {signature: tuple(sorted(members, key=_instance_id)) for signature, members in grouped.items()}


def _record(row: dict[str, object], role: str) -> RoleRecord:
    identity = _mapping(row["source_identity"], "source_identity")
    return RoleRecord(_instance_id(row), _text(identity["source_record_sha256"], "source_record_sha256"), _text(row["split"], "source_split"), _signature(row), role)


def _audit(records: list[dict[str, str]]) -> None:
    if len({str(record["instance_id"]) for record in records}) != len(records):
        raise SelectionFeasibilityError("audit_instance_overlap")
    roles_by_signature: defaultdict[str, set[str]] = defaultdict(set)
    for record in records:
        roles_by_signature[_text(record["composition_signature"], "composition_signature")].add(_text(record["role"], "role"))
    if any(len(roles) != 1 for roles in roles_by_signature.values()):
        raise SelectionFeasibilityError("audit_composition_leakage")


def _failed_draft(rows: Sequence[dict[str, object]], source_digest: str, artifact_digest: str, implementation_digest: str, reason: str) -> dict[str, object]:
    return {"characterization_artifact_sha256": artifact_digest, "exclusions": sorted(_instance_id(row) for row in rows if not _is_paired_exact(row)), "failure": reason, "implementation_sha256": implementation_digest, "owner_approved": False, "policy": POLICY, "policy_sha256": hashlib.sha256(POLICY.encode()).hexdigest(), "records": [], "source_manifest_sha256": source_digest, "status": "draft_for_owner_review"}


def _percentile(values: list[int]) -> int:
    return sorted(values)[(9 * len(values) - 1) // 10]


def _metric(row: dict[str, object], planner_key: str, metric: str) -> int:
    return _integer(_mapping(_mapping(row[planner_key], planner_key)["exact_search"], "exact_search")[metric], metric)


def _instance_id(row: dict[str, object]) -> str:
    return _text(row.get("instance_id"), "instance_id")


def _signature(row: dict[str, object]) -> str:
    return _text(row["composition_signature"], "composition_signature")


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise SelectionFeasibilityError(f"invalid_{label}")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise SelectionFeasibilityError(f"invalid_{label}")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SelectionFeasibilityError(f"invalid_{label}")
    return value


def _digest(value: str, label: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise SelectionFeasibilityError(f"invalid_{label}")


def _group_ids(groups: dict[str, tuple[dict[str, object], ...]], signatures: set[str]) -> set[str]:
    return {_instance_id(row) for signature in signatures for row in groups[signature]}


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(arguments)
    derive_bundle_draft(args.bundle, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
