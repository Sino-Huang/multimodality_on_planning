"""CPU-only replay diagnostics and observed-prefix accounting for matched v5."""

import itertools
from collections import Counter

import numpy as np

from .matched_execution import adapter_paths
from .matched_views import final_view_store
from .model_search_episode import _parse_model_output
from .scene_assets import read_json
from .visual_episode import VisualSession


def observed_prefix(snapshots, cap):
    """Use only completed operations up to the common cap; never extend a trace."""
    selected = snapshots[:cap]
    last = selected[-1] if selected else {}
    return {
        "observed_decisions": len(selected),
        "invalid_operations": sum(not s["accepted"] for s in selected),
        "expansions": last.get("expansions", 0),
        "success_observed": last.get("success", False),
        "terminal_observed": last.get("terminal", False),
        "censored_at_common_cap": len(snapshots) > cap,
    }


def paired_interval(differences):
    """Each entry is one whole-problem contrast, not a decision or rollout."""
    values = np.asarray(differences, dtype=float)
    samples = np.random.default_rng(1729).integers(0, len(values), size=(10000, len(values)))
    means = values[samples].mean(axis=1)
    return {
        "difference": float(values.mean()),
        "lower": float(np.quantile(means, 0.025)),
        "upper": float(np.quantile(means, 0.975)),
        "whole_problems": len(values),
    }


def rejection(session, event):
    if event["accepted"]:
        return None
    if session.algorithm.startswith("best_first_add"):
        return str(session.session.events[-1]["trusted_runtime_result"].get("reason", "unspecified rejection"))
    if session.algorithm == "best_first_width":
        return str(session.session.events[-1].get("error", "unspecified rejection"))
    _, error = _parse_model_output(event["raw_output"])
    return error or "BFS operation rejected; detailed validity rule not retained"


def failure_category(reason):
    if reason is None:
        return None
    value = reason.lower()
    if any(x in value for x in ("expecting value", "unterminated string", "json", "delimiter", "extra data")):
        return "json_syntax"
    if any(
        x in value for x in ("schema", "parse", "required", "unexpected", "must contain", "must be", "invalid fields")
    ):
        return "schema_or_shape"
    if "applicable" in value or "precondition" in value:
        return "applicability"
    if "candidate" in value:
        return "candidate_membership_or_duplicate"
    if "effect" in value:
        return "effect_or_successor"
    return "search_rule_or_unresolved"


def expansion_count(session):
    if session.algorithm == "bfs":
        return len(session.session.expansions)
    if session.algorithm == "best_first_width":
        return session.session.expansion_count
    return session.session.controller.expansion_count


def solution_length(session):
    """Recover unit-action cost from the trusted replay, only on success."""
    if not session.result()["goal_reached"]:
        return None
    if session.algorithm.startswith("best_first_add"):
        controller = session.session.controller
        return controller.best_g[controller.frontier_head_state_id()]
    memory = session.session.context.memory if session.algorithm == "bfs" else session.session.memory
    distances = {session.authority.initial_state.state_id: 0}
    for edge in memory.provenance:
        distances.setdefault(edge.target_state_id, distances[edge.source_state_id] + 1)
    goals = [distances[s] for s in memory.visited if session.authority.is_goal(memory.state(s))]
    return min(goals)


def replay_row(root, study, task, modality, algorithm, arm, report):
    views = final_view_store(root, study, task)
    views.read_only = True
    session = VisualSession(
        root, task["row"], algorithm, arm, 17, root / report["output"], study["study_id"], views=views
    )
    snapshots, failures = [], []
    request = session.next_request()
    for event, measurement in zip(report["events"], report["call_measurements"], strict=True):
        if request is None or dict(request.model_input) != event["input"]:
            raise ValueError("analysis replay input mismatch")
        binding = views.observe(dict(request.model_input), algorithm, modality=modality, pixels=False)["binding"]
        if binding != event["view"] or measurement["input_tokens"] != binding["input_tokens"]:
            raise ValueError("analysis input/view/token binding mismatch")
        session.submit(event["raw_output"], binding)
        if session.events[-1] != event:
            raise ValueError("analysis operation replay mismatch")
        reason = rejection(session, event)
        if reason:
            failures.append({"index": event["index"], "reason": reason, "category": failure_category(reason)})
        request = session.next_request()
        snapshots.append(
            {
                "accepted": event["accepted"],
                "terminal": request is None,
                "success": session.result()["invariant_valid_success"] if request is None else False,
                "expansions": expansion_count(session),
            }
        )
    if request is not None or session.result() != report["result"]:
        raise ValueError("analysis terminal result mismatch")
    cost = task["row"]["reference_costs"][algorithm]
    cap = min(2 * c["decisions"] for c in task["row"]["reference_costs"].values())
    result = report["result"]
    if len(failures) != result["invalid_operation_count"] or len(snapshots) != result["decision_count"]:
        raise ValueError("replayed decision/rejection accounting differs")
    if result["model_call_limit"] != 2 * cost["decisions"]:
        raise ValueError("episode decision allowance differs from matching reference")
    if result["decision_count"] > 2 * cost["decisions"] or result["expansion_count"] > cost["expansions"]:
        raise ValueError("observed episode exceeds its declared resource allowance")
    model = arm in ("pretrained_base", "process_sft")
    return {
        "task_id": task["row"]["task_id"],
        "domain": task["row"]["domain"],
        "modality": modality,
        "algorithm": algorithm,
        "arm": arm,
        "episode": report["output"],
        "success": result["invariant_valid_success"],
        "goal_reached": result["goal_reached"],
        "runtime_reported_invariants_hold": result["algorithm_invariants_hold"],
        "all_operations_valid": result["invalid_operation_count"] == 0,
        "invalid_operations": result["invalid_operation_count"],
        "decisions": result["decision_count"],
        "expansions": result["expansion_count"],
        "termination": result["termination_reason"],
        "decision_cap": 2 * cost["decisions"],
        "expansion_cap": cost["expansions"],
        "decision_budget_fraction": result["decision_count"] / (2 * cost["decisions"]),
        "expansion_budget_fraction": result["expansion_count"] / cost["expansions"],
        "solution_unit_action_cost": solution_length(session),
        "failures": failures,
        "common_cap": cap,
        "common_prefix": observed_prefix(snapshots, cap),
        "model_input_tokens": sum(c["input_tokens"] for c in report["call_measurements"]) if model else 0,
        "model_output_tokens": sum(c["generated_sequence_tokens"] for c in report["call_measurements"]) if model else 0,
        "call_wall_seconds": sum(c["call_wall_seconds"] for c in report["call_measurements"]),
        "episode_wall_seconds": report["episode_wall_seconds"],
    }


def analyze(root, study, progress):
    panel = read_json(root / study["output_root"] / "preparation/final-panel.json")
    if panel["study"] != study:
        raise ValueError("analysis panel differs from study")
    rows, coverage = [], []
    expected = itertools.product(study["modalities"], panel["tasks"], study["algorithms"], study["final"]["conditions"])
    for modality, task, algorithm, arm in expected:
        path = (
            root
            / study["output_root"]
            / "evaluation"
            / modality
            / task["row"]["task_id"].replace("/", "__")
            / f"{algorithm}-{arm}.json.gz"
        )
        identity = {"task_id": task["row"]["task_id"], "modality": modality, "algorithm": algorithm, "arm": arm}
        coverage.append(
            {**identity, "status": "complete" if path.exists() else "missing", "episode": str(path.relative_to(root))}
        )
        if not path.exists():
            continue
        report = read_json(path)
        checkpoint = (
            str((root / adapter_paths(root, study, modality)[algorithm]).relative_to(root))
            if arm == "process_sft"
            else None
        )
        if (
            any(report[k] != v for k, v in identity.items())
            or report["seed"] != 17
            or report["checkpoint"] != checkpoint
        ):
            raise ValueError("episode identity/checkpoint mismatch")
        if report["contract_id"] != study["study_id"] or report["model_revision"] != study["model_revision"]:
            raise ValueError("episode protocol/model mismatch")
        rows.append(replay_row(root, study, task, modality, algorithm, arm, report))
        progress("analysis:replay", completed=len(rows), total=144)
    summaries = []
    for m, a in itertools.product(study["modalities"], study["final"]["conditions"]):
        subset = [r for r in rows if r["modality"] == m and r["arm"] == a]
        summaries.append(
            {
                "modality": m,
                "arm": a,
                "observed": len(subset),
                "expected": 12,
                "successes": sum(r["success"] for r in subset),
                "valid_operation_episodes": sum(r["all_operations_valid"] for r in subset),
                "decisions": sum(r["decisions"] for r in subset),
                "invalid_operations": sum(r["invalid_operations"] for r in subset),
                "expansions": sum(r["expansions"] for r in subset),
                "model_input_tokens": sum(r["model_input_tokens"] for r in subset),
                "model_output_tokens": sum(r["model_output_tokens"] for r in subset),
                "call_wall_seconds": sum(r["call_wall_seconds"] for r in subset),
                "terminations": dict(Counter(r["termination"] for r in subset)),
            }
        )
    contrasts = []
    tasks = [t["row"]["task_id"] for t in panel["tasks"]]
    index = {(r["task_id"], r["algorithm"], r["modality"], r["arm"]): r for r in rows}
    for algorithm, arm, (left, right) in itertools.product(
        study["algorithms"], study["final"]["conditions"], itertools.combinations(study["modalities"], 2)
    ):
        for metric in ("success", "all_operations_valid", "decisions", "expansions"):
            pairs = [(index.get((t, algorithm, left, arm)), index.get((t, algorithm, right, arm))) for t in tasks]
            values = [float(a[metric]) - float(b[metric]) for a, b in pairs if a is not None and b is not None]
            contrasts.append(
                {
                    "algorithm": algorithm,
                    "arm": arm,
                    "left_minus_right": [left, right],
                    "metric": metric,
                    "complete_paired_coverage": len(values) == 3,
                    "estimate": paired_interval(values) if len(values) == 3 else None,
                }
            )
    curriculum = read_json(root / "data/best_first_paired_phase_v3/issue67-terminal/result.json")
    if curriculum["outcome"] != "PASS" or curriculum["semantic_replay"]["episodes"] != 312:
        raise ValueError("curriculum terminal evidence incomplete")
    if curriculum["coverage"]["selected_tasks"] != 12 or any(
        curriculum["training"][cell]["completed_steps"] != 522 or curriculum["training"][cell]["seed"] != 17
        for cell in ("staged", "shuffled", "mixed_order")
    ):
        raise ValueError("curriculum scope/training evidence differs")
    ledger = read_json(root / "outputs/matched_modalities/v2/budget.json")
    if any(s.get("ended") is None for s in ledger["segments"]):
        raise ValueError("cannot analyze a live stage as final")
    return {
        "study_id": study["study_id"],
        "complete_coverage": len(rows) == 144,
        "coverage": coverage,
        "episodes": rows,
        "summaries": summaries,
        "paired_contrasts": contrasts,
        "curriculum_source": "data/best_first_paired_phase_v3/issue67-terminal/result.json",
        "curriculum": curriculum,
        "cumulative_stage_seconds": {
            stage: sum(s["ended"] - s["started"] for s in ledger["segments"] if s["stage"] == stage)
            for stage in ("qualify", "train", "evaluate")
        },
        "infrastructure_stops": [
            s
            for s in ledger["segments"]
            if s["stage"] == "evaluate"
            and any(read_json(root / c["status"])["outcome"] != "PASS" for c in s["children"])
        ],
    }
