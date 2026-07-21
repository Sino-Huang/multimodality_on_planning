"""Promotion assessment and frozen-receipt validation for rollout gates."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .io_utils import JSONInputError, JSONRecord, file_sha256, read_json_object, read_jsonl, write_json
from .rollout_gate_contracts import RECEIPT_ARTIFACT_PATHS, STAGES, PromotionDecision, Stage
from .rollout_gate_selection import (
    _stable_sha256,
    append_pair_validation_errors,
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
    """Fail closed unless a frozen selection, release, and coverage all pass."""
    reasons: list[str] = []
    selection = _load_selection(selection_file, stage, reasons)
    selection_file_sha256 = _safe_file_sha256(selection_file, "rollout_selection.json", reasons)
    artifact_hashes = _output_artifact_hashes(output_root, reasons)
    prior_receipt_sha256 = _prior_receipt_sha256(prior_receipt, stage, reasons)
    pairs = read_jsonl(output_root / "diagnostics" / "pairing_manifest.jsonl") if artifact_hashes["pairing_manifest_sha256"] else []
    if pairs:
        append_pair_validation_errors(pairs, reasons)
    if selection and artifact_hashes["pairing_manifest_sha256"]:
        validate_frozen_pairs(selection, pairs, artifact_hashes["pairing_manifest_sha256"], reasons)
    verification_counts = _release_and_coverage(stage, output_root, pairs, reasons, verifier)
    decision = PromotionDecision(stage, not reasons, tuple(sorted(set(reasons))), verification_counts)
    receipt = _receipt(
        decision,
        selection_file,
        selection,
        selection_file_sha256,
        prior_receipt_sha256,
        output_root,
        artifact_hashes,
    )
    write_json(output_root / "diagnostics" / "rollout_promotion_receipt.json", receipt)
    return decision


def _prior_receipt_sha256(prior_receipt: Path | None, stage: Stage, reasons: list[str]) -> str:
    if stage != "fixture" and prior_receipt is None:
        reasons.append("missing_prior_promotion_receipt")
        return ""
    return _require_prior_receipt(prior_receipt, stage, reasons) if prior_receipt is not None else ""


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
    return _verification_counts(verification)


def _receipt(
    decision: PromotionDecision,
    selection_file: Path,
    selection: JSONRecord,
    selection_file_sha256: str,
    prior_receipt_sha256: str,
    output_root: Path,
    artifact_hashes: dict[str, str],
) -> JSONRecord:
    receipt = decision.to_record()
    receipt["selection_file"] = str(selection_file)
    receipt["selection_file_sha256"] = selection_file_sha256
    receipt["selection_sha256"] = selection.get("selection_sha256", "")
    receipt["prior_receipt_sha256"] = prior_receipt_sha256
    receipt["output_root"] = str(output_root)
    receipt["semantic_image_qa"] = "verified_by_release" if decision.approved else "not_promotable"
    receipt["frozen_output_receipts"] = artifact_hashes
    receipt["receipt_sha256"] = _stable_sha256(receipt)
    return receipt


def _safe_file_sha256(path: Path, relative_path: str, reasons: list[str], *, prefix: str = "") -> str:
    try:
        return file_sha256(path)
    except OSError:
        reasons.append(f"{prefix}missing_artifact:{relative_path}")
        return ""


def _output_artifact_hashes(output_root: Path, reasons: list[str]) -> dict[str, str]:
    return {
        artifact_name: _safe_file_sha256(output_root / relative_path, relative_path, reasons)
        for artifact_name, relative_path in RECEIPT_ARTIFACT_PATHS.items()
    }


def _load_selection(path: Path, stage: Stage, reasons: list[str]) -> JSONRecord:
    try:
        selection = read_json_object(path)
    except JSONInputError:
        reasons.append("invalid_frozen_selection")
        return {}
    unsigned = dict(selection)
    supplied_hash = str(unsigned.pop("selection_sha256", ""))
    if selection.get("stage") != stage or supplied_hash != _stable_sha256(unsigned):
        reasons.append("frozen_selection_integrity_failure")
    if selection.get("artifact_kind") != "planimation_rollout_selection_v1":
        reasons.append("invalid_frozen_selection")
    if not isinstance(selection.get("selected_pair_ids"), list) or not selection["selected_pair_ids"] or not isinstance(selection.get("selected_pairs"), list):
        reasons.append("frozen_selection_missing_pairs")
    if selection.get("preparation_reasons"):
        reasons.append("selection_preparation_blocked")
    return selection


def _require_prior_receipt(path: Path, stage: Stage, reasons: list[str]) -> str:
    try:
        receipt = read_json_object(path)
    except JSONInputError:
        reasons.append("invalid_prior_promotion_receipt")
        return ""
    unsigned = dict(receipt)
    supplied_hash = str(unsigned.pop("receipt_sha256", ""))
    if supplied_hash != _stable_sha256(unsigned):
        reasons.append("prior_promotion_receipt_integrity_failure")
    expected = STAGES[STAGES.index(stage) - 1]
    if receipt.get("stage") != expected or receipt.get("approved") is not True:
        reasons.append("prior_stage_not_approved")
    output_root = receipt.get("output_root")
    artifact_hashes = receipt.get("frozen_output_receipts")
    if not isinstance(output_root, str) or not isinstance(artifact_hashes, dict):
        reasons.append("prior_receipt_artifact_binding_failure")
        return supplied_hash
    for artifact_name, relative_path in RECEIPT_ARTIFACT_PATHS.items():
        expected_hash = artifact_hashes.get(artifact_name)
        current_hash = _safe_file_sha256(Path(output_root) / relative_path, relative_path, reasons, prefix="prior_receipt_")
        if not isinstance(expected_hash, str) or not expected_hash or current_hash != expected_hash:
            reasons.append(f"prior_receipt_artifact_hash_mismatch:{artifact_name}")
    return supplied_hash


def _verification_counts(verification: JSONRecord) -> dict[str, int]:
    counts = verification.get("counts")
    if not isinstance(counts, dict):
        raise RuntimeError("release verification returned invalid counts")
    pair_records = counts.get("pair_records")
    state_render_records = counts.get("state_render_records")
    if type(pair_records) is not int or type(state_render_records) is not int:
        raise RuntimeError("release verification returned invalid counts")
    return {"pair_records": pair_records, "state_render_records": state_render_records}
