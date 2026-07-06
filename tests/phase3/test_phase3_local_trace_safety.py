from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.phase3.generate_curriculum_trace_dataset import _extract_traces
from scripts.phase3.local_planner_types import LocalPlannerRequest
from scripts.phase3.local_planners import run_local_planner
from scripts.phase3.pddl import ground_actions, parse_task


def test_iw_rejects_width_above_configured_max(tmp_path: Path) -> None:
    domain, problem = _write_empty_init_goal_pddl(tmp_path)
    task = parse_task(domain, problem)
    grounded, _status = ground_actions(task, max_grounded_actions=100, max_grounded_atoms=100)

    result = run_local_planner(
        LocalPlannerRequest(
            planner="iw",
            task=task,
            grounded=tuple(grounded),
            limits={"bfs_max_expansions": 50, "max_plan_length": 5, "max_trace_steps": 10, "local_iw_width": 4, "local_iw_max_width": 3},
        )
    )

    assert result.status == "skipped_resource_limit"
    assert result.trace["width"] == 4


@pytest.mark.parametrize("field", ["domain", "split", "instance_id", "planner"])
def test_trace_extraction_rejects_path_traversal_components(tmp_path: Path, field: str) -> None:
    output_root = tmp_path / "phase3"
    row = {
        "domain": "safe-domain",
        "split": "train",
        "instance_id": "safe-instance",
        "planner": "bfs",
        "supervised_target": {"planner_trace": {"algorithm": "bfs"}},
    }
    row[field] = "../escape"
    output_root.mkdir()
    (output_root / "train.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="unsafe trace path component"):
        _extract_traces(output_root)

    assert not (output_root / "escape").exists()


def _write_empty_init_goal_pddl(root: Path) -> tuple[Path, Path]:
    domain = root / "domain.pddl"
    problem = root / "problem.pddl"
    domain.write_text(
        """
(define (domain empty-start)
  (:requirements :strips)
  (:predicates (done))
  (:action make-done
    :parameters ()
    :precondition (and)
    :effect (and (done)))
)
""",
        encoding="utf-8",
    )
    problem.write_text(
        """
(define (problem empty-start-p1)
  (:domain empty-start)
  (:init)
  (:goal (and (done)))
)
""",
        encoding="utf-8",
    )
    return domain, problem
