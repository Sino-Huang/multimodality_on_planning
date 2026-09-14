"""Prior final candidates must not bypass expanded-panel whole-task exclusion."""

from examples.planning_benchmark_slice.expanded_panel import matched_candidate_sources
from examples.planning_benchmark_slice.expanded_scheduler import write


def test_previous_final_and_rejected_candidates_are_inventory_sources(tmp_path):
    for index, eligible in enumerate((True, False)):
        folder = tmp_path / f"outputs/matched_modalities/v5/preparation/candidates/ferry-{index}"
        task = folder / "task.json"
        write(task, {"domain_pddl": "retained", "problem_pddl": "retained"})
        write(
            folder / "candidate.json",
            {"domain": "ferry", "eligible": eligible, "row": {"task_path": str(task.relative_to(tmp_path))}},
        )
    sources = matched_candidate_sources(tmp_path, {"ferry"})
    assert len(sources) == 2
    assert all(s["domain"] == "ferry" for s in sources)
    assert matched_candidate_sources(tmp_path, {"storage"}) == []
