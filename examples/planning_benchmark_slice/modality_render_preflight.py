"""Cheap initial-observation feasibility before any issue72 render production."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding

from .modality_observation import ModalityInputLimits, measure_relation_layout, state_goal_relations
from .modality_phase import ROOT, ModalityPhase
from .pddl_state import PDDLStateAuthority


def initial_layout(domain: str, problem: str, limits: ModalityInputLimits) -> dict[str, Any]:
    """A necessary condition for full coverage, never a claim about later states."""
    authority = PDDLStateAuthority.from_pddl(domain, problem)
    state, goal = state_goal_relations(authority, authority.initial_state)
    measured_state = measure_relation_layout(state, has_scene=True, limits=limits)
    measured_goal = measure_relation_layout(goal, has_scene=False, limits=limits)
    return {"state": measured_state, "goal": measured_goal, "fits": measured_state["fits"] and measured_goal["fits"]}


def run_initial_layout_preflight(
    phase: ModalityPhase,
    *,
    binding: ReceiptBinding,
    gate: GateReceipt,
    authorization: AuthorizationReceipt | None,
    progress: Callable[[dict[str, Any]], None],
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    """Check the whole selected panel without HTTP, pixel allocation or model work."""
    permission = phase.permission(
        stage="render_preflight", binding=binding, gate=gate, authorization=authorization, predecessors={}, split="dev"
    )
    report: dict[str, Any] = {
        "schema_version": "issue72_initial_layout_preflight_v1",
        "phase_id": phase.freeze["phase_id"],
        "stage": "render_preflight",
        "binding": binding.to_dict(),
        "permission": permission.to_dict(),
        "scientific_completion": False,
        "complete_selected_coverage": False,
        "rendered_frames": 0,
        "http_requests": 0,
        "checks": {},
        "records": [],
    }
    if not permission.start_permitted:
        report.update(outcome=permission.outcome.value, reason=permission.reason)
        if permission.run_state == "gated-not-run":
            report["gated_not_run_receipt"] = permission.to_dict()
        return report
    render, budget = phase.components["render"], phase.components["budget"]
    limits = ModalityInputLimits(
        phase.components["checkpoint"]["model_id"],
        phase.components["checkpoint"]["model_revision"],
        budget["max_input_tokens"],
        render["image_width"],
        render["image_height"],
        render["font_size"],
        phase.components["corpus"]["search_memory"]["max_bytes"],
        phase.components["corpus"]["search_memory"]["accepted_delta_limit"],
        tuple(budget["input_size_bins"]),
        render["font_name"],
    )
    panel = json.loads((repo_root / phase.components["corpus"]["panel_manifest"]).read_text())["selected"]
    sources = {}
    for family, path in (
        ("bfs", "data/bfs_pilot_v6/selected-manifest.jsonl"),
        ("best_first_width", "data/bfws_phase_v1/development-manifest.jsonl"),
    ):
        sources[family] = {
            row["instance_id"]: row for row in map(json.loads, (repo_root / path).read_text().splitlines())
        }
    for index, task in enumerate(panel):
        progress({"stage": "layout_task_started", "completed": index, "total": len(panel), "task_id": task["task_id"]})
        try:
            if task["task_id"].startswith("astar-pair-"):
                trace = repo_root / next(iter(task["trace_paths"].values()))
                source = json.loads((trace.parent / "task.json").read_text())
                domain, problem = source["domain_pddl"], source["problem_pddl"]
            else:
                family, instance = task["task_id"].split("/", 1)
                source = sources[family][instance]
                domain = (repo_root / source["domain_path"]).read_text()
                problem = (repo_root / source["problem_path"]).read_text()
            measured = initial_layout(domain, problem, limits)
            record = {
                "task_id": task["task_id"],
                "domain": task["domain"],
                "split": task["split"],
                "reference_costs": task["reference_costs"],
                **measured,
                "outcome": "PASS" if measured["fits"] else "VALID_STOP",
            }
        except (ValueError, OSError, KeyError) as error:
            record = {"task_id": task["task_id"], "domain": task["domain"], "outcome": "INVALID", "reason": str(error)}
        report["records"].append(record)
        progress(
            {
                "stage": "layout_task_complete",
                "completed": index + 1,
                "total": len(panel),
                "task_id": task["task_id"],
                "outcome": record["outcome"],
            }
        )
    counts = Counter(record["outcome"] for record in report["records"])
    report.update(
        initial_layout_complete=True,
        counts=dict(counts),
        outcome="INVALID" if counts["INVALID"] else "VALID_STOP",
        reason=(
            "invalid_source"
            if counts["INVALID"]
            else (
                "frozen_image_capacity_exceeded"
                if counts["VALID_STOP"]
                else "full_trace_and_profile_qualification_pending"
            )
        ),
    )
    report["receipt_id"] = f"issue72-layout:{binding.attempt_id}:{report['outcome']}"
    if report["outcome"] == "VALID_STOP":
        report["gated_not_run_receipt"] = {
            "receipt_type": "gated_not_run",
            "receipt_id": f"{report['receipt_id']}:render-not-run",
            "binding": binding.to_dict(),
            "outcome": "VALID_STOP",
            "reason": report["reason"],
            "start_permitted": False,
            "scientific_completion": False,
        }
    return report
