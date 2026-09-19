"""Independently replay a terminal visual/multimodal experiment without model calls."""

# ruff: noqa: E402
from __future__ import annotations

import argparse
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.modality_view_preparation import write_json
from examples.planning_benchmark_slice.scene_assets import read_json
from examples.planning_benchmark_slice.visual_episode import VisualTaskViews, replay_visual_episode
from examples.planning_benchmark_slice.visual_experiment import ALGORITHMS, ARMS, VisualExperiment, training_steps
from scripts.run_visual_issue75 import heartbeat, log


def identity(episode):
    return tuple(episode[k] for k in ("task_id", "algorithm", "arm", "seed"))


def expected_episodes(rows, seeds):
    return {
        (row["task_id"], algorithm, arm, seed)
        for row in rows
        for algorithm in row["reference_costs"]
        for arm in ARMS
        for seed in ([17] if arm == "exact_reference" else seeds)
    }


def coverage(episodes, expected):
    observed = [identity(e) for e in episodes]
    if len(observed) != len(set(observed)):
        raise ValueError("duplicate episode identity")
    if set(observed) - expected:
        raise ValueError("episode outside declared task/algorithm/condition/seed scope")
    missing = sorted(expected - set(observed))
    return {"complete": not missing, "completed": len(observed), "total": len(expected), "missing": missing}


def point_metrics(episodes):
    result = {}
    for algorithm in ALGORITHMS:
        result[algorithm] = {}
        for arm in ARMS:
            rows = [e["result"] for e in episodes if e["algorithm"] == algorithm and e["arm"] == arm]
            if rows:
                result[algorithm][arm] = {
                    "episodes": len(rows),
                    "invariant_valid_success": statistics.mean(float(r["invariant_valid_success"]) for r in rows),
                    "invalid_operation_rate": (
                        sum(r["invalid_operation_count"] for r in rows) / max(1, sum(r["decision_count"] for r in rows))
                    ),
                    "budget_usage": sum(r["decision_count"] for r in rows) / sum(r["model_call_limit"] for r in rows),
                }
    return result


def verify(experiment):
    started = time.monotonic()
    e, root = experiment, experiment.output
    terminal = root / "result.json"
    if not terminal.exists():
        raise ValueError("experiment has no terminal result; inspect the live process instead")
    receipt = read_json(terminal)
    attempt = read_json(root / "attempt.json")
    if (
        attempt["experiment"] != e.config
        or attempt.get("cost_panel") != e.cost_panel
        or attempt.get("pilot_manifest") != e.pilot
        or receipt["contract_id"] != e.config["contract_id"]
    ):
        raise ValueError("terminal experiment differs from its declared configuration")
    selected = (
        e.pilot["selected_task_ids"]
        if e.pilot
        else e.cost_panel["selected_task_ids"] if e.cost_panel else [r["task_id"] for r in e.dev]
    )
    rows = {r["task_id"]: r for r in e.dev if r["task_id"] in selected}
    expected = expected_episodes(rows.values(), e.config["evaluation_seeds"])
    episodes = []
    paths = sorted(
        p for stage in ("references", "evaluation") for p in (root / stage).glob("worker-*/episode-*.json.gz")
    )
    for path in paths:
        report = read_json(path)
        if (
            report["contract_id"] != e.config["contract_id"]
            or report.get("modality", "visual-state") != e.config["modality"]
            or (ROOT / report["output"]).resolve() != path.resolve()
            or identity(report) not in expected
        ):
            raise ValueError("retained episode binding differs")
        row = rows[report["task_id"]]
        views = VisualTaskViews(
            ROOT,
            row,
            e.corpus.results[row["task_id"]]["view_manifest"],
            ROOT / report["view_root"],
            e.config["backend_endpoints"][0],
            read_only=True,
        )
        replay_visual_episode(ROOT, row, report, views)
        episodes.append({k: report[k] for k in ("task_id", "algorithm", "arm", "seed", "result")})
        log("verification:episode", completed=len(episodes), total=len(paths))
    scope = coverage(episodes, expected)
    indexed = {identity(e): e["result"] for e in episodes}
    for stage, arms in (("references", ARMS[:2]), ("evaluation", ARMS[2:])):
        manifest = root / f"{stage}.json"
        if manifest.exists():
            saved = read_json(manifest)
            declared = saved["episodes"]
            actual = {k: v for k, v in indexed.items() if k[2] in arms}
            if (
                saved["contract_id"] != e.config["contract_id"]
                or saved["outcome"] != "PASS"
                or len(declared) != len(actual)
                or {identity(r): r["result"] for r in declared} != actual
            ):
                raise ValueError("aggregate episode manifest differs from replayed files")
    checkpoints = {}
    for algorithm in ALGORITHMS:
        path = root / "training" / f"{algorithm}.json"
        if not path.exists() or read_json(path).get("outcome") != "PASS":
            continue
        run = read_json(path)
        checkpoint = ROOT / run["final_checkpoint"]
        if (
            run["contract_id"] != e.config["contract_id"]
            or run["seed"] != 17
            or run["steps"] != training_steps(e.train_counts[algorithm], e.config["training"])
            or run["train_records"] != e.train_counts[algorithm]
            or checkpoint.resolve() != (root / "training" / algorithm / "final").resolve()
            or not (checkpoint / "adapter_config.json").is_file()
            or not (checkpoint / "adapter_model.safetensors").is_file()
        ):
            raise ValueError("final training checkpoint binding differs")
        checkpoints[algorithm] = run
    metrics = point_metrics(episodes)
    adjudication = root / "adjudicate.json"
    stage_files = ("qualification", "references", "training", "evaluation", "adjudicate")
    execution_complete = (
        scope["complete"] and len(checkpoints) == 4 and all((root / f"{stage}.json").exists() for stage in stage_files)
    )
    if not execution_complete and any(
        receipt.get(key) for key in ("scientific_completion", "pilot_complete", "full_matrix_complete")
    ):
        raise ValueError("terminal receipt claims completion without complete evidence")
    gate_passed = False
    if execution_complete:
        qualification = read_json(root / "qualification.json")
        devices = qualification["device_qualifications"]
        if (
            qualification["outcome"] != "PASS"
            or qualification["contract_id"] != e.config["contract_id"]
            or qualification["selection"]["task_ids"] != list(rows)
            or len(devices) != len(e.config["devices"])
            or {d["worker"] for d in devices} != set(range(len(devices)))
            or any(d["outcome"] != "PASS" or d["dtype"] != e.config["inference_dtype"] for d in devices)
        ):
            raise ValueError("hardware qualification coverage differs")
        training = read_json(root / "training.json")
        if (
            training["outcome"] != "PASS"
            or training["contract_id"] != e.config["contract_id"]
            or len(training["training_runs"]) != 4
            or {r["algorithm"]: r for r in training["training_runs"]} != checkpoints
        ):
            raise ValueError("aggregate training report differs")
        saved = read_json(adjudication)
        if (
            saved["contract_id"] != e.config["contract_id"]
            or not saved["complete_selected_coverage"]
            or saved["episodes"] != len(expected)
        ):
            raise ValueError("adjudication coverage differs")
        for algorithm, arms in metrics.items():
            for arm, values in arms.items():
                for key in ("invariant_valid_success", "invalid_operation_rate", "budget_usage"):
                    if values[key] != saved["metrics"][algorithm][key][arm]:
                        raise ValueError("saved adjudication point metrics differ from replay")
        thresholds = e.config["thresholds"]
        gate_passed = all(
            arms["exact_reference"]["invariant_valid_success"] >= thresholds["exact_success"]
            and arms["process_sft"]["invariant_valid_success"] >= thresholds["learned_success"]
            and arms["process_sft"]["invalid_operation_rate"] <= thresholds["maximum_invalid_rate"]
            for arms in metrics.values()
        )
        if saved["outcome"] != ("PASS" if gate_passed else "VALID_STOP") or receipt["outcome"] != saved["outcome"]:
            raise ValueError("terminal performance gate differs from replayed results")
    return {
        "contract_id": e.config["contract_id"],
        "modality": e.config["modality"],
        "verification_outcome": "PASS" if execution_complete else "PARTIAL",
        "execution_complete": execution_complete,
        "scientific_gate_passed": gate_passed,
        "retained_outcome": receipt["outcome"],
        "retained_scientific_completion": receipt["scientific_completion"],
        "comparison_scope": e.config.get("comparison_scope", "within_modality"),
        "coverage": scope,
        "independently_replayed_episodes": len(episodes),
        "condition_counts": dict(Counter(r["arm"] for r in episodes)),
        "metrics": metrics,
        "training": checkpoints,
        "new_model_calls": 0,
        "elapsed_seconds": round(time.monotonic() - started, 2),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="Separate audit JSON; never the experiment directory")
    args = parser.parse_args()
    experiment = VisualExperiment(args.config)
    if args.output.resolve().is_relative_to(experiment.output):
        raise ValueError("verification output must be separate from the retained experiment")
    report = heartbeat(lambda: verify(experiment), "verification")
    write_json(args.output, report)
    log(
        "verification:complete",
        outcome=report["verification_outcome"],
        completed=report["coverage"]["completed"],
        total=report["coverage"]["total"],
    )
    return 0 if report["execution_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
