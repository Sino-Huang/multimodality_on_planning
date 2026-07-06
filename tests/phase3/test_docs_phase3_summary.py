from __future__ import annotations

from pathlib import Path


DOC = Path("doc/detailed_implementation_summary/phase3_complete_supervised_planning_data_summary.md")
CURRICULUM_EXTENSION_DOC = Path(
    "doc/detailed_implementation_summary/phase3_curriculum_extension_and_fd_plan_saving_summary.md"
)


def test_docs_summary_contains_required_commands_and_root() -> None:
    text = DOC.read_text(encoding="utf-8")
    required = [
        "data/phase3_supervised_planning",
        "generate_supervised_data",
        "verify_manifest_coverage",
        "verify_planner_attempts",
        "validate_jsonl_schema",
        "verify_replay_validated_examples",
        "verify_fidelity_labels",
        "verify_splits",
        "verify_domain_coverage",
        "verify_vision_assets",
        "verify_no_smoke_sources",
        "verify_determinism",
    ]
    for phrase in required:
        assert phrase in text


def test_docs_summary_no_overclaim() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    assert "outputs/planning_artifacts" in text
    assert "smoke/prototype" in text
    assert "phase 4 training is not done" in text
    assert "not all planner attempts succeed" in text


def test_curriculum_extension_summary_contains_safe_runbook() -> None:
    text = CURRICULUM_EXTENSION_DOC.read_text(encoding="utf-8")
    required = [
        "visible root",
        "data/curriculum_pddl_shards",
        "--candidate-multiplier",
        "5,153 accepted",
        "accepted_total=4492",
        "7995` target should be treated as aspirational only",
        "duplicate_accepted_problem_hashes=0",
        "save_fast_downward_plans",
        "extend_curriculum_workflow",
        "--update-root",
        "--verbose",
        "plan_available_total=5",
        "--max-generate-commands 0",
        "Only replace `data/curriculum_pddl` once the staged root",
    ]
    for phrase in required:
        assert phrase in text
