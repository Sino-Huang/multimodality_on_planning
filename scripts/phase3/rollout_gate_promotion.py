"""Promotion assessment for semantic Planimation rollout gates."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .io_utils import JSONInputError, JSONRecord, read_json_object, read_jsonl, write_json
from .rollout_gate_contracts import RECEIPT_ARTIFACT_PATHS, STAGES, PromotionDecision, Stage
from .rollout_gate_selection import (
    append_pair_validation_errors,
    has_valid_selection_pair_contract,
    stage_coverage_errors,
    validate_frozen_pairs,
)
from .verify_planimation_vlm import VerificationFailure, verify_output


def assess_promotion(
    output_root: Path,
    stage: Stage,
    selection_file: Path,
    prior_receipt: Path | None = None,
    *,
    verifier: Callable[[Path, str], JSONRecord] = verify_output,
) -> PromotionDecision:
    reasons: list[str] = []
    selection = _load_selection(selection_file, stage, reasons)
    _require_artifacts(output_root, reasons)
    _require_prior_receipt(prior_receipt, stage, reasons)
    manifest = output_root / "diagnostics" / "pairing_manifest.jsonl"
    pairs = read_jsonl(manifest) if manifest.is_file() else []
    append_pair_validation_errors(pairs, reasons)
    if selection:
        validate_frozen_pairs(selection, pairs, reasons)
    counts = _release_and_coverage(stage, output_root, pairs, reasons, verifier)
    decision = PromotionDecision(stage, not reasons, tuple(sorted(set(reasons))), counts)
    receipt: JSONRecord = {
        **decision.to_record(),
        "selection_file": str(selection_file),
        "prior_receipt": str(prior_receipt) if prior_receipt is not None else None,
        "output_root": str(output_root),
        "semantic_image_qa": "verified_by_release" if decision.approved else "not_promotable",
        "output_artifacts": list(RECEIPT_ARTIFACT_PATHS),
    }
    write_json(output_root / "diagnostics" / "rollout_promotion_receipt.json", receipt)
    return decision


def _require_artifacts(output_root: Path, reasons: list[str]) -> None:
    for relative_path in RECEIPT_ARTIFACT_PATHS:
        if not (output_root / relative_path).is_file():
            reasons.append(f"missing_artifact:{relative_path}")


def _load_selection(path: Path, stage: Stage, reasons: list[str]) -> JSONRecord:
    try:
        selection = read_json_object(path)
    except JSONInputError:
        reasons.append("invalid_frozen_selection")
        return {}
    if selection.get("stage") != stage or selection.get("artifact_kind") != "planimation_rollout_selection_v1":
        reasons.append("invalid_frozen_selection")
    if selection.get("input_pairing_manifest_path") != "diagnostics/pairing_manifest.jsonl":
        reasons.append("invalid_frozen_selection")
    if not has_valid_selection_pair_contract(selection.get("selected_pair_ids"), selection.get("selected_pairs")):
        reasons.append("invalid_frozen_selection")
    if selection.get("preparation_reasons"):
        reasons.append("selection_preparation_blocked")
    return selection


def _require_prior_receipt(path: Path | None, stage: Stage, reasons: list[str]) -> None:
    if stage == "fixture":
        return
    if path is None:
        reasons.append("missing_prior_promotion_receipt")
        return
    try:
        receipt = read_json_object(path)
    except JSONInputError:
        reasons.append("invalid_prior_promotion_receipt")
        return
    expected = STAGES[STAGES.index(stage) - 1]
    if receipt.get("stage") != expected or receipt.get("approved") is not True:
        reasons.append("prior_stage_not_approved")


def _release_and_coverage(
    stage: Stage,
    output_root: Path,
    pairs: list[JSONRecord],
    reasons: list[str],
    verifier: Callable[[Path, str], JSONRecord],
) -> dict[str, int]:
    if reasons:
        return {}
    try:
        verification = verifier(output_root, "release")
    except VerificationFailure as error:
        reasons.extend(error.reasons)
        return {}
    reasons.extend(stage_coverage_errors(stage, pairs))
    counts = verification.get("counts")
    if not isinstance(counts, dict):
        raise RuntimeError("release verification returned invalid counts")
    pair_records = counts.get("pair_records")
    state_render_records = counts.get("state_render_records")
    if type(pair_records) is not int or type(state_render_records) is not int:
        raise RuntimeError("release verification returned invalid counts")
    return {"pair_records": pair_records, "state_render_records": state_render_records}
