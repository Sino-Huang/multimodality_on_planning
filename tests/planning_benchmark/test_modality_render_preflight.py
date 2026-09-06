from dataclasses import replace

import pytest

from examples.planning_benchmark_slice.modality_observation import (
    ModalityInputLimits,
    measure_relation_layout,
)
from examples.planning_benchmark_slice.modality_phase import ROOT, load_modality_phase
from examples.planning_benchmark_slice.modality_render_preflight import initial_layout, run_initial_layout_preflight
from src.data_collect.governance import GateReceipt, ReceiptBinding, StopOutcome


def limits():
    return ModalityInputLimits("model", "revision", 7808, 1024, 1536, 18, 32768, 16, (2048, 4096, 6144, 7808))


def test_known_production_initial_state_cannot_fit_frozen_layout():
    root = ROOT / "data/curriculum_pddl/15puzzle/train/easy/15puzzle-train-easy-0091"
    measured = initial_layout((root / "domain.pddl").read_text(), (root / "problem.pddl").read_text(), limits())
    assert measured["state"]["rows"] == 93
    assert measured["state"]["required_height"] == 3628
    assert measured["fits"] is False


def test_layout_measurement_uses_both_text_width_and_complete_row_height():
    assert measure_relation_layout((("state", "at", ("a",)),), has_scene=True, limits=limits())["fits"]
    assert not measure_relation_layout((("state", "x" * 200, ()),), has_scene=True, limits=limits())["fits"]
    assert not measure_relation_layout(
        tuple(("state", "at", (str(i),)) for i in range(93)), has_scene=True, limits=limits()
    )["fits"]


@pytest.mark.parametrize("outcome", list(StopOutcome))
def test_missing_authorization_or_stopped_gate_cannot_read_tasks_or_render(tmp_path, outcome):
    phase = load_modality_phase()
    binding = ReceiptBinding(
        phase.freeze["phase_id"], "test-layout", ROOT / phase.freeze["output_root"] / "render_preflight/test-layout"
    )
    gate = GateReceipt(binding, outcome, "ancestor" if outcome is StopOutcome.ANCESTOR_STOP else None)
    report = run_initial_layout_preflight(
        phase,
        binding=binding,
        gate=gate,
        authorization=None,
        progress=lambda event: pytest.fail("work started without permission"),
        repo_root=tmp_path,
    )
    assert report["outcome"] != "PASS"
    assert not report["scientific_completion"]
    assert ("gated_not_run_receipt" in report) == (report["outcome"] in {"VALID_STOP", "ANCESTOR_STOP"})
    assert report["rendered_frames"] == report["http_requests"] == 0
    assert not list(tmp_path.iterdir())


def test_smaller_images_do_not_hide_overflow_by_dropping_rows():
    relations = tuple(("state", "at", (str(i),)) for i in range(30))
    measured = measure_relation_layout(relations, has_scene=True, limits=replace(limits(), image_height=768))
    assert measured["rows"] == 30
    assert not measured["fits"]
