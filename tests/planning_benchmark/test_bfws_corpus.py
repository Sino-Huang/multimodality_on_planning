from __future__ import annotations

import json
from pathlib import Path

from examples.planning_benchmark_slice.bfws_corpus import (
    materialize_frozen_bfws_corpus_trace,
    run_frozen_bfws_corpus_release,
)
from examples.planning_benchmark_slice.bfws_generation import preflight_frozen_bfws_trace_generation
from examples.planning_benchmark_slice.bfws_model_input import bfws_text_policy_training_messages
from examples.planning_benchmark_slice.bfws_phase import load_bfws_phase_gate
from src.data_collect.generate import GenerationRequest
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome

REPO_ROOT = Path(__file__).resolve().parents[2]
FREEZE = REPO_ROOT / "configs" / "experiments" / "bfws_phase_freeze_v1.json"
AUTHORIZATION = REPO_ROOT / "configs" / "experiments" / "bfws_phase_authorization_v1.json"
TRACE_ROOT = REPO_ROOT / "data" / "bfws_phase_v1" / "exact-traces"
TRACE_MANIFEST = TRACE_ROOT / "manifests" / "bfws-expert-traces.json"
CORPUS_ROOT = REPO_ROOT / "data" / "bfws_phase_v1" / "corpus-release"


def _request(tmp_path: Path, outcome: StopOutcome = StopOutcome.PASS) -> GenerationRequest:
    binding = ReceiptBinding(
        contract_id="issue-56-bfws-development-v1",
        attempt_id=f"issue-58-corpus-{outcome.value.lower()}-test",
        output_root=(tmp_path / "corpus-release").resolve(),
    )
    gate = GateReceipt(binding, outcome)
    return GenerationRequest(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=(
            AuthorizationReceipt(binding, gate.receipt_id) if outcome is StopOutcome.PASS else None
        ),
        receipt_root=(tmp_path / "receipts").resolve(),
    )


def test_single_replay_verified_trace_materializes_both_views_and_training_projection() -> None:
    gate = load_bfws_phase_gate(FREEZE, AUTHORIZATION)
    rows = preflight_frozen_bfws_trace_generation(gate)
    row = next(item for item in rows if item["instance_id"] == "storage-train-easy-0004")
    manifest = json.loads(TRACE_MANIFEST.read_bytes())
    item = next(item for item in manifest["traces"] if item["instance_id"] == row["instance_id"])

    shard = materialize_frozen_bfws_corpus_trace(
        row=row,
        trace_item=item,
        trace_root=TRACE_ROOT,
        phase_gate=gate,
    )

    assert len(shard.process_rows) == row["exact_reference_decision_count"] == 3
    assert len(shard.operational_rows) == 3
    assert len(shard.training_rows) == 3
    assert shard.audit["future_step_leakage_count"] == 0
    assert shard.audit["live_training_input_mismatch_count"] == 0
    assert shard.audit["teacher_decision_rejection_count"] == 0
    assert shard.audit["max_input_tokens"] <= 7_808
    assert shard.audit["max_target_tokens"] <= 384

    first = shard.process_rows[0]
    assert first["algorithm"] == "best_first_width"
    assert first["view"] == "process"
    assert first["input"]["search_memory"]["context_type"] == "bounded_bfws_search_memory"
    assert first["target"]["runtime_result"] is None
    assert first["target"]["typed_operation"].get("source_state_id") == "$"
    assert first["expert_evidence"] == {
        "episode_path": item["evidence"]["path"],
        "trace_record_index": 0,
    }
    assert shard.training_rows[0] == {
        "messages": bfws_text_policy_training_messages(first["input"], first["target"])
    }

    operational = shard.operational_rows[0]
    assert operational["view"] == "operational"
    assert set(operational["input"]) == {"action", "source_state", "task_context"}
    assert operational["target"]["validity"] == "accepted"


def test_corpus_release_retains_a_gated_not_run_receipt(tmp_path: Path) -> None:
    gate = load_bfws_phase_gate(FREEZE, AUTHORIZATION)
    request = _request(tmp_path, StopOutcome.VALID_STOP)

    receipt = run_frozen_bfws_corpus_release(
        trace_manifest_path=TRACE_MANIFEST,
        request=request,
        phase_gate=gate,
        resume=False,
    )

    assert receipt.outcome is StopOutcome.VALID_STOP
    assert receipt.status == "gated_not_run"
    assert receipt.scientific_completion is False
    assert receipt.execution_result is None
    assert not Path(request.binding.output_root).exists()


def test_released_bfws_corpus_covers_the_frozen_panel_without_heldout_access() -> None:
    manifest = json.loads((CORPUS_ROOT / "manifests" / "bfws-text-corpus.json").read_bytes())
    audit = json.loads((CORPUS_ROOT / "audits" / "corpus.json").read_bytes())
    training = json.loads((CORPUS_ROOT / "training" / "manifest.json").read_bytes())

    assert manifest["counts"] == {
        "operational_records": 67_215,
        "process_records": 69_019,
        "split_assignments": 105,
        "strata": 35,
        "training_projection_records": 69_019,
    }
    assert manifest["segment_alignment"] == "atomic_search_event"
    assert manifest["views"] == ["operational", "process"]
    assert "fresh-test" not in json.dumps(manifest)
    assert training["counts"] == {"dev": 21_239, "train": 47_780}
    assert audit["max_input_tokens"] == 7_360
    assert audit["max_target_tokens"] == 96
    for name in (
        "canonical_input_overlap_count",
        "future_step_leakage_count",
        "held_out_instance_count",
        "identical_input_conflicting_target_count",
        "input_over_budget_count",
        "input_target_overlap_count",
        "live_training_input_mismatch_count",
        "semantic_task_overlap_count",
        "target_over_budget_count",
        "target_parse_rejection_count",
        "teacher_decision_rejection_count",
    ):
        assert audit[name] == 0
    for artifact in manifest["artifacts"]:
        relative = Path(artifact["path"])
        assert not relative.is_absolute() and ".." not in relative.parts
        assert (CORPUS_ROOT / relative).stat().st_size == artifact["size_bytes"]
