from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.phase3.io_utils import read_jsonl
from scripts.phase3.rollout_gates import assess_promotion, prepare_selection
from scripts.phase3.rollout_gate_selection import validate_frozen_pairs


def test_fixture_promotion_uses_semantic_selection_and_required_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.phase3.rollout_gates.verify_output",
        lambda _root, _mode: {"counts": {"pair_records": 1, "state_render_records": 1}},
    )
    root = _rollout_root(tmp_path / "fixture", plan_length=1)
    selection = prepare_selection(root, "fixture")

    decision = assess_promotion(root, "fixture", root / "diagnostics" / "rollout_selection.json")

    assert decision.approved is True
    assert selection["selected_pair_ids"] == ["pair-0000"]
    receipt = json.loads((root / "diagnostics" / "rollout_promotion_receipt.json").read_text())
    assert receipt["output_artifacts"] == [
        "diagnostics/pairing_manifest.jsonl",
        "diagnostics/hybrid_output_manifest.json",
        "diagnostics/state_render_manifest.jsonl",
    ]


def test_promotion_rejects_changed_frozen_pair_by_direct_record_comparison(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.phase3.rollout_gates.verify_output",
        lambda _root, _mode: {"counts": {"pair_records": 1, "state_render_records": 1}},
    )
    root = _rollout_root(tmp_path / "changed", plan_length=1)
    prepare_selection(root, "fixture")
    manifest = root / "diagnostics" / "pairing_manifest.jsonl"
    pair = json.loads(manifest.read_text())
    pair["instance_id"] = "changed-instance"
    manifest.write_text(json.dumps(pair) + "\n")

    decision = assess_promotion(root, "fixture", root / "diagnostics" / "rollout_selection.json")

    assert decision.approved is False
    assert "output_pairing_manifest_pair_identity_mismatch" in decision.reasons


def test_nonfixture_requires_approved_previous_stage(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.phase3.rollout_gates.verify_output",
        lambda _root, _mode: {"counts": {"pair_records": 1, "state_render_records": 1}},
    )
    root = _rollout_root(tmp_path / "changed", plan_length=5)
    prepare_selection(root, "changed-canary")
    prior = tmp_path / "prior.json"
    prior.write_text(json.dumps({"stage": "fixture", "approved": False}))

    decision = assess_promotion(root, "changed-canary", root / "diagnostics" / "rollout_selection.json", prior)

    assert decision.approved is False
    assert "prior_stage_not_approved" in decision.reasons


def test_missing_required_artifact_blocks_promotion(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.phase3.rollout_gates.verify_output",
        lambda _root, _mode: {"counts": {"pair_records": 1, "state_render_records": 1}},
    )
    root = _rollout_root(tmp_path / "missing", plan_length=1)
    prepare_selection(root, "fixture")
    (root / "diagnostics" / "state_render_manifest.jsonl").unlink()

    decision = assess_promotion(root, "fixture", root / "diagnostics" / "rollout_selection.json")

    assert "missing_artifact:diagnostics/state_render_manifest.jsonl" in decision.reasons


def test_validate_frozen_pairs_preserves_record_multiplicity() -> None:
    pair = {"pair_id": "pair-0000", "source_record_id": "train.jsonl:0:example-0000"}
    reasons: list[str] = []

    validate_frozen_pairs({"selected_pairs": [pair, pair]}, [pair], reasons)

    assert reasons == ["output_pairing_manifest_pair_identity_mismatch"]


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [("plan_length", True, "pair plan_length must be an integer"), ("planner", "bfs", "pair planner is unsupported")],
)
def test_prepare_selection_rejects_invalid_persisted_pairs(
    tmp_path: Path, field: str, value: object, reason: str
) -> None:
    root = _rollout_root(tmp_path / "invalid", plan_length=1)
    manifest = root / "diagnostics" / "pairing_manifest.jsonl"
    pair = json.loads(manifest.read_text())
    pair[field] = value
    manifest.write_text(json.dumps(pair) + "\n")

    with pytest.raises(RuntimeError, match=reason):
        prepare_selection(root, "fixture")


def test_jsonl_reader_rejects_non_object_rows(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl"
    path.write_text("[]\n")
    with pytest.raises(RuntimeError, match="JSONL row must be an object"):
        read_jsonl(path)


def _rollout_root(root: Path, *, plan_length: int) -> Path:
    diagnostics = root / "diagnostics"
    diagnostics.mkdir(parents=True)
    pair = {
        "pair_id": "pair-0000",
        "source_root": "tmp/fixture-source",
        "source_root_id": "fixture-source",
        "source_jsonl": "train.jsonl",
        "source_line_index": 0,
        "source_record_id": "train.jsonl:0:example-0000",
        "example_id": "example-0000",
        "domain": "grid",
        "instance_id": "grid-train-easy-0000",
        "schema_version": "phase3_planimation_vlm_v1",
        "planner": "gbfs",
        "active_planner_id": "gbfs",
        "split": "train",
        "bucket": "easy",
        "trace_fidelity": "success_full_trace",
        "planner_approximation": "exact",
        "domain_path": "tmp/domain.pddl",
        "problem_path": "tmp/problem.pddl",
        "render_trace_path": "tmp/trace.vfg.json",
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
    (diagnostics / "pairing_manifest.jsonl").write_text(json.dumps(pair) + "\n")
    (diagnostics / "hybrid_output_manifest.json").write_text("{}\n")
    (diagnostics / "state_render_manifest.jsonl").write_text("{}\n")
    return root
