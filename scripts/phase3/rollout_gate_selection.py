"""Strict pairing-manifest selection for Planimation rollout stages."""

from __future__ import annotations

import json
from collections import Counter
from hashlib import sha256
from pathlib import Path

from .io_utils import JSONRecord, file_sha256, read_jsonl, write_json
from .planimation_persisted_contracts import validate_pair_record
from .rollout_gate_contracts import Stage


def prepare_selection(output_root: Path, stage: Stage, domain: str | None = None) -> JSONRecord:
    """Freeze a deterministic eligible-pair selection from a fresh manifest root."""
    pairs = read_jsonl(output_root / "diagnostics" / "pairing_manifest.jsonl")
    _require_valid_pairs(pairs)
    eligible = [pair for pair in pairs if pair["training_eligible"] is True]
    if domain is not None:
        eligible = [pair for pair in eligible if pair.get("domain") == domain]
    eligible.sort(
        key=lambda pair: (
            _pair_text(pair, "domain"),
            _pair_text(pair, "planner"),
            _pair_text(pair, "split"),
            _pair_text(pair, "instance_id"),
            _pair_text(pair, "pair_id"),
        )
    )
    selected, reasons = _select(stage, eligible, domain)
    selection: JSONRecord = {
        "artifact_kind": "planimation_rollout_selection_v1",
        "config": {
            "selection_order": "domain,planner,split,instance_id,pair_id",
            "stage": stage,
            "stage_transition_limits": {"changed-canary": [5, 10], "stratified-pilot": [250, 500]},
        },
        "domain": domain,
        "input_pairing_manifest_sha256": file_sha256(output_root / "diagnostics" / "pairing_manifest.jsonl"),
        "selected_pair_ids": [_pair_text(pair, "pair_id") for pair in selected],
        "selected_pairs": [_frozen_pair(pair) for pair in selected],
        "stage": stage,
        "transition_count": sum(_pair_integer(pair, "plan_length") for pair in selected),
        "preparation_reasons": reasons,
    }
    selection["selection_sha256"] = _stable_sha256(selection)
    write_json(output_root / "diagnostics" / "rollout_selection.json", selection)
    return selection


def validate_frozen_pairs(selection: JSONRecord, pairs: list[JSONRecord], manifest_hash: str, reasons: list[str]) -> None:
    if selection.get("input_pairing_manifest_sha256") != manifest_hash:
        reasons.append("frozen_pairing_manifest_hash_mismatch")
    selected_pairs = selection.get("selected_pairs")
    if not isinstance(selected_pairs, list):
        return
    if not all(isinstance(pair, dict) for pair in selected_pairs):
        reasons.append("invalid_frozen_selection")
        return
    expected = Counter(_stable_sha256(pair) for pair in selected_pairs)
    actual = Counter(_stable_sha256(_frozen_pair(pair)) for pair in pairs)
    if expected != actual:
        reasons.append("output_pairing_manifest_pair_identity_mismatch")


def append_pair_validation_errors(pairs: list[JSONRecord], reasons: list[str]) -> None:
    for index, pair in enumerate(pairs):
        reasons.extend(f"pair[{index}]: {error}" for error in validate_pair_record(pair))


def stage_coverage_errors(stage: Stage, pairs: list[JSONRecord]) -> list[str]:
    transitions = Counter[str]()
    for pair in pairs:
        transitions[_pair_text(pair, "domain")] += _pair_integer(pair, "plan_length")
    if stage == "changed-canary" and any(count < 5 or count > 10 for count in transitions.values()):
        return ["changed_canary_transition_coverage_failure"]
    if stage == "stratified-pilot":
        total = sum(transitions.values())
        cells = {(_pair_text(pair, "domain"), _pair_text(pair, "planner"), _pair_text(pair, "split")) for pair in pairs}
        return [] if 250 <= total <= 500 and cells else ["stratified_pilot_coverage_failure"]
    return []


def _select(stage: Stage, eligible: list[JSONRecord], domain: str | None) -> tuple[list[JSONRecord], list[str]]:
    if not eligible:
        return [], ["no_strict_v1_eligible_pairs"]
    match stage:
        case "fixture":
            return [eligible[0]], []
        case "changed-canary":
            return _changed_canary_selection(eligible)
        case "stratified-pilot":
            return _stratified_pilot_selection(eligible)
        case "complete-domain":
            return (eligible, []) if domain is not None else ([], ["complete_domain_requires_domain"])
        case "frozen-full":
            return eligible, []


def _changed_canary_selection(eligible: list[JSONRecord]) -> tuple[list[JSONRecord], list[str]]:
    selected: list[JSONRecord] = []
    for domain in sorted({_pair_text(pair, "domain") for pair in eligible}):
        transitions = 0
        for pair in (candidate for candidate in eligible if _pair_text(candidate, "domain") == domain):
            next_count = transitions + _pair_integer(pair, "plan_length")
            if next_count > 10:
                break
            selected.append(pair)
            transitions = next_count
            if transitions >= 5:
                break
        if transitions < 5:
            return [], [f"insufficient_changed_transitions:{domain}"]
    return selected, []


def _stratified_pilot_selection(eligible: list[JSONRecord]) -> tuple[list[JSONRecord], list[str]]:
    cells = {(_pair_text(pair, "domain"), _pair_text(pair, "planner"), _pair_text(pair, "split")) for pair in eligible}
    selected = [_first_in_cell(eligible, cell) for cell in sorted(cells)]
    transitions = sum(_pair_integer(pair, "plan_length") for pair in selected)
    for pair in eligible:
        if pair in selected:
            continue
        plan_length = _pair_integer(pair, "plan_length")
        if transitions + plan_length > 500:
            break
        selected.append(pair)
        transitions += plan_length
        if transitions >= 250:
            break
    return (selected, []) if 250 <= transitions <= 500 else ([], ["stratified_pilot_transition_count_out_of_range"])


def _first_in_cell(pairs: list[JSONRecord], cell: tuple[str, str, str]) -> JSONRecord:
    return next(pair for pair in pairs if (_pair_text(pair, "domain"), _pair_text(pair, "planner"), _pair_text(pair, "split")) == cell)


def _frozen_pair(pair: JSONRecord) -> JSONRecord:
    return dict(pair)


def _require_valid_pairs(pairs: list[JSONRecord]) -> None:
    errors: list[str] = []
    append_pair_validation_errors(pairs, errors)
    if errors:
        raise RuntimeError(f"invalid_pairing_manifest: {'; '.join(errors)}")


def _pair_text(pair: JSONRecord, field: str) -> str:
    value = pair[field]
    if not isinstance(value, str):
        raise RuntimeError(f"invalid_pairing_manifest: pair {field} must be a nonempty string")
    return value


def _pair_integer(pair: JSONRecord, field: str) -> int:
    value = pair[field]
    if type(value) is not int:
        raise RuntimeError(f"invalid_pairing_manifest: pair {field} must be an integer")
    return value


def _stable_sha256(value: JSONRecord) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
