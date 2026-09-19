"""Scientific phase permissions, not artifact-integrity tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import TypedDict

import pytest

from examples.planning_benchmark_slice.modality_phase import (
    ROOT,
    ModalityPhase,
    inspect_modality_sources,
    load_modality_phase,
)
from scripts.prepare_modality_issue71 import main
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome


class RequestArguments(TypedDict):
    binding: ReceiptBinding
    gate: GateReceipt
    authorization: AuthorizationReceipt | None
    split: str


def request(tmp_path: Path) -> RequestArguments:
    binding = ReceiptBinding("issue-71-modality-development-v1", "test-attempt", tmp_path / "output")
    gate = GateReceipt(binding, StopOutcome.PASS)
    return RequestArguments(
        binding=binding, gate=gate, authorization=AuthorizationReceipt(binding, gate.receipt_id), split="dev"
    )


def future_phase() -> ModalityPhase:
    """An authorized in-memory successor fixture, not a production receipt."""
    phase = load_modality_phase(ROOT / "configs/experiments/issue71/freeze.json")
    authorization = dict(phase.authorization)
    authorization.update(outcome="PASS", authorized_stages=list(phase.components["matrix"]["stages"]))
    return replace(phase, authorization=authorization)


def predecessor(stage: str, **updates):
    return (
        dict(
            phase_id="issue-71-modality-development-v1",
            stage=stage,
            receipt_id=f"test:{stage}",
            outcome="PASS",
            scientific_completion=True,
            complete_selected_coverage=True,
        )
        | updates
    )


def test_candidate_is_inspectable_but_cannot_start_any_production_stage(tmp_path):
    phase = load_modality_phase(ROOT / "configs/experiments/issue71/freeze.json")
    assert len(phase.cells) == 12
    assert inspect_modality_sources(phase)["paired_additive"]["process_records"] == 31531
    for stage in phase.components["matrix"]["stages"]:
        result = phase.permission(stage=stage, predecessors={}, **request(tmp_path))
        assert result.outcome is StopOutcome.ANCESTOR_STOP
        assert result.run_state == "gated-not-run"
        assert not result.start_permitted and not result.scientific_completion
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("defect", ["authorization", "binding", "split", "stage"])
def test_scope_and_attempt_permissions_remain_required(tmp_path, defect):
    args = request(tmp_path)
    stage = "render"
    if defect == "authorization":
        args["authorization"] = None
    elif defect == "binding":
        args["binding"] = replace(args["binding"], output_root=tmp_path / "other")
    elif defect == "split":
        args["split"] = "test"
    else:
        stage = "dagger"
    result = future_phase().permission(stage=stage, predecessors={}, **args)
    assert result.outcome is StopOutcome.INVALID
    assert not result.start_permitted and not result.scientific_completion


@pytest.mark.parametrize("stage", ["corpus", "training", "qualification", "evaluation", "synthesis"])
def test_missing_stage_evidence_cannot_be_replaced_by_a_pass_attempt_gate(tmp_path, stage):
    result = future_phase().permission(stage=stage, predecessors={}, **request(tmp_path))
    assert result.outcome is StopOutcome.VALID_STOP
    assert result.run_state == "gated-not-run"


@pytest.mark.parametrize(
    "updates,expected",
    [
        ({"outcome": "VALID_STOP"}, StopOutcome.ANCESTOR_STOP),
        ({"outcome": "ANCESTOR_STOP"}, StopOutcome.ANCESTOR_STOP),
        ({"outcome": "INVALID"}, StopOutcome.INVALID),
        ({"outcome": "unknown"}, StopOutcome.INVALID),
        ({"phase_id": "old-phase"}, StopOutcome.INVALID),
        ({"stage": "render"}, StopOutcome.INVALID),
        ({"scientific_completion": False}, StopOutcome.VALID_STOP),
        ({"complete_selected_coverage": False}, StopOutcome.VALID_STOP),
    ],
)
def test_model_evaluation_requires_complete_scoped_predecessors(tmp_path, updates, expected):
    reports = {name: predecessor(name) for name in ("corpus", "training", "qualification")}
    reports["qualification"].update(updates)
    result = future_phase().permission(stage="evaluation", predecessors=reports, **request(tmp_path))
    assert result.outcome is expected
    assert not result.start_permitted


def test_matching_future_permissions_authorize_start_not_completion(tmp_path):
    reports = {name: predecessor(name) for name in ("corpus", "training", "qualification")}
    result = future_phase().permission(stage="evaluation", predecessors=reports, **request(tmp_path))
    assert result.start_permitted
    assert not result.scientific_completion


def test_source_coverage_is_scientific_metadata_not_a_regeneration_check():
    phase = load_modality_phase()
    components = deepcopy(phase.components)
    components["corpus"]["sources"]["bfs"]["tasks"] = 1
    with pytest.raises(ValueError, match="source corpus coverage"):
        inspect_modality_sources(replace(phase, components=components))


def test_cli_progress_distinguishes_valid_dry_run_from_production_authorization(capsys):
    assert main(["--dry-run"]) == 0
    output = capsys.readouterr().out
    assert '"stage": "preflight_complete"' in output
    assert '"dry_run_valid": true' in output
    assert '"outcome": "PASS"' in output
    assert '"phase_authorized": true' in output
    assert '"start_permitted": false' in output
    assert '"writes": 0' in output


def v2_request(stage):
    phase = load_modality_phase()
    binding = ReceiptBinding(
        phase.freeze["phase_id"], "test-attempt", ROOT / phase.freeze["output_root"] / stage / "test-attempt"
    )
    gate = GateReceipt(binding, StopOutcome.PASS)
    return RequestArguments(
        binding=binding, gate=gate, authorization=AuthorizationReceipt(binding, gate.receipt_id), split="dev"
    )


def test_v2_freezes_profiles_panel_and_observation_mapping_without_claiming_render_completion():
    phase = load_modality_phase()
    counts = inspect_modality_sources(phase)["selected_panel"]
    assert counts["selected_task_groups"] == 241
    assert counts["excluded_task_groups"] == 18
    assert sum(counts["episodes_by_algorithm_split"].values()) == 305
    assert len(phase.components["render"]["domain_profiles"]) == 15
    assert "off-solution" in phase.components["render"]["trace_mapping"]["coverage"]
    preflight = phase.permission(stage="render_preflight", predecessors={}, **v2_request("render_preflight"))
    assert preflight.start_permitted and not preflight.scientific_completion
    render = phase.permission(stage="render", predecessors={}, **v2_request("render"))
    assert render.outcome is StopOutcome.VALID_STOP


def test_v2_cannot_reuse_another_stages_attempt_authorization():
    result = load_modality_phase().permission(stage="evaluation", predecessors={}, **v2_request("render_preflight"))
    assert result.outcome is StopOutcome.INVALID
    assert result.reason is not None and "output" in result.reason


def test_v2_complete_flag_without_matched_cell_coverage_cannot_authorize_training():
    phase = load_modality_phase()
    report = predecessor("corpus", phase_id=phase.freeze["phase_id"])
    report["checks"] = {name: True for name in phase.components["matrix"]["stages"]["corpus"]["required_checks"]}
    result = phase.permission(stage="training", predecessors={"corpus": report}, **v2_request("training"))
    assert result.outcome is StopOutcome.INVALID


def test_v2_render_requires_successful_profile_and_path_checks_not_just_pass_label():
    phase = load_modality_phase()
    report = predecessor("render_preflight", phase_id=phase.freeze["phase_id"])
    result = phase.permission(stage="render", predecessors={"render_preflight": report}, **v2_request("render"))
    assert result.outcome is StopOutcome.INVALID
    report["checks"] = {
        name: True for name in phase.components["matrix"]["stages"]["render_preflight"]["required_checks"]
    }
    result = phase.permission(stage="render", predecessors={"render_preflight": report}, **v2_request("render"))
    assert result.start_permitted and not result.scientific_completion
