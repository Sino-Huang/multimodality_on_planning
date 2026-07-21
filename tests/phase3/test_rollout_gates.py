from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.phase3.io_utils import read_jsonl
from scripts.phase3.rollout_gates import assess_promotion, prepare_selection


def test_promotion_binds_manifest_pair_identity_prior_receipt_and_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("scripts.phase3.rollout_gates.verify_output", lambda _root, _mode: {"counts": {"pair_records": 1, "state_render_records": 1}})
    fixture_root = _rollout_root(tmp_path / "fixture", plan_length=1)
    prepare_selection(fixture_root, "fixture")
    fixture_decision = assess_promotion(fixture_root, "fixture", fixture_root / "diagnostics" / "rollout_selection.json")

    stale_root = tmp_path / "stale"
    shutil.copytree(fixture_root, stale_root)
    stale_pairing = stale_root / "diagnostics" / "pairing_manifest.jsonl"
    stale_pair = json.loads(stale_pairing.read_text(encoding="utf-8"))
    stale_pair["source_record_sha256"] = "0" * 64
    stale_pairing.write_text(json.dumps(stale_pair) + "\n", encoding="utf-8")
    stale_decision = assess_promotion(stale_root, "fixture", stale_root / "diagnostics" / "rollout_selection.json")

    forged_prior = tmp_path / "forged-prior.json"
    forged_receipt = json.loads((fixture_root / "diagnostics" / "rollout_promotion_receipt.json").read_text(encoding="utf-8"))
    forged_receipt["approved"] = False
    forged_prior.write_text(json.dumps(forged_receipt), encoding="utf-8")
    changed_root = _rollout_root(tmp_path / "changed", plan_length=5)
    prepare_selection(changed_root, "changed-canary")
    forged_decision = assess_promotion(changed_root, "changed-canary", changed_root / "diagnostics" / "rollout_selection.json", forged_prior)

    missing_root = tmp_path / "missing"
    shutil.copytree(fixture_root, missing_root)
    (missing_root / "diagnostics" / "state_render_manifest.jsonl").unlink()
    missing_decision = assess_promotion(missing_root, "fixture", missing_root / "diagnostics" / "rollout_selection.json")
    missing_receipt = json.loads((missing_root / "diagnostics" / "rollout_promotion_receipt.json").read_text(encoding="utf-8"))

    assert fixture_decision.approved is True
    assert "frozen_pairing_manifest_hash_mismatch" in stale_decision.reasons
    assert "output_pairing_manifest_pair_identity_mismatch" in stale_decision.reasons
    assert "prior_promotion_receipt_integrity_failure" in forged_decision.reasons
    assert "missing_artifact:diagnostics/state_render_manifest.jsonl" in missing_decision.reasons
    assert missing_receipt["approved"] is False
    assert missing_receipt["frozen_output_receipts"]["state_render_manifest_sha256"] == ""


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("plan_length", True, "pair plan_length must be an integer"),
        ("planner", "bfs", "pair planner is unsupported"),
    ],
)
def test_prepare_selection_rejects_invalid_persisted_pairs_without_receipt(
    tmp_path: Path, field: str, value: object, reason: str
) -> None:
    # Given: a persisted manifest row that violates the strict pairing contract.
    root = _rollout_root(tmp_path / "invalid", plan_length=1)
    manifest_path = root / "diagnostics" / "pairing_manifest.jsonl"
    pair = json.loads(manifest_path.read_text(encoding="utf-8"))
    pair[field] = value
    manifest_path.write_text(json.dumps(pair) + "\n", encoding="utf-8")

    # When: selection preparation reads the untrusted persisted manifest.
    with pytest.raises(RuntimeError, match=reason):
        prepare_selection(root, "fixture")

    # Then: no apparently valid selection receipt is persisted.
    assert not (root / "diagnostics" / "rollout_selection.json").exists()


def test_prepare_selection_rejects_non_object_jsonl_rows_without_receipt(tmp_path: Path) -> None:
    # Given: a JSONL manifest containing a syntactically valid but non-object row.
    root = _rollout_root(tmp_path / "non-object", plan_length=1)
    manifest_path = root / "diagnostics" / "pairing_manifest.jsonl"
    manifest_path.write_text("[]\n", encoding="utf-8")

    # When: the active JSONL reader reaches the persisted row.
    with pytest.raises(RuntimeError, match="JSONL row must be an object"):
        prepare_selection(root, "fixture")

    # Then: the generic JSONL boundary also rejects the non-object row and no selection exists.
    with pytest.raises(RuntimeError, match="JSONL row must be an object"):
        read_jsonl(manifest_path)
    assert not (root / "diagnostics" / "rollout_selection.json").exists()


def _rollout_root(root: Path, *, plan_length: int) -> Path:
    diagnostics = root / "diagnostics"
    diagnostics.mkdir(parents=True)
    pair = {
        "pair_id": "pair-0000",
        "source_root": "tmp/fixture-source",
        "source_root_id": "fixture-source",
        "source_root_sha256": "a" * 64,
        "source_jsonl": "train.jsonl",
        "source_split_sha256": "a" * 64,
        "source_line_index": 0,
        "source_record_sha256": "b" * 64,
        "example_id": "example-0000",
        "domain": "grid",
        "instance_id": "grid-train-easy-0000",
        "schema_version": "phase3_planimation_vlm_v1",
        "planner": "gbfs",
        "active_planner_id": "gbfs",
        "split": "train",
        "bucket": "easy",
        "plan_hash": "plan-hash",
        "trace_hash": "trace-hash",
        "trace_fidelity": "success_full_trace",
        "planner_approximation": "exact",
        "domain_path": "tmp/domain.pddl",
        "problem_path": "tmp/problem.pddl",
        "render_trace_path": "tmp/trace.vfg.json",
        "render_action_hash": "action-hash",
        "frame_paths": [],
        "frame_count": 0,
        "plan_length": plan_length,
        "trace_size_chars": 1,
        "vfg_action_count": 0,
        "frame_alignment_status": "existing_exact_complete",
        "vfg_error": None,
        "training_eligible": True,
        "exclusion_reasons": [],
    }
    (diagnostics / "pairing_manifest.jsonl").write_text(json.dumps(pair) + "\n", encoding="utf-8")
    (diagnostics / "hybrid_output_manifest.json").write_text("{}\n", encoding="utf-8")
    (diagnostics / "state_render_manifest.jsonl").write_text("{}\n", encoding="utf-8")
    return root
