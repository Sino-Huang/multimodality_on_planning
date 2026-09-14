#!/usr/bin/env python
"""Independently replay expanded-baseline episodes and report complete coverage or missingness."""

import argparse
from collections import Counter, defaultdict
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.planning_benchmark_slice.expanded_baseline import (  # noqa: E402
    assigned_bindings,
    binding_paths,
    bindings,
    independently_replay,
    validate_protocol,
)
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, write  # noqa: E402
from examples.planning_benchmark_slice.scene_assets import read_json  # noqa: E402


def load_context(config):
    protocol = read(config)
    protocol["root"] = str(ROOT)
    panel, _, readiness = validate_protocol(ROOT, protocol)
    protocol["verified_checkpoints"] = {
        f"{row['modality']}:{row['algorithm']}": row["checkpoint"] for row in readiness["checkpoints"]
    }
    tasks = {task["row"]["task_id"]: task for task in read(ROOT / panel["view_report"])["tasks"]}
    return protocol, panel, tasks


def verify_report(protocol, task, binding, report, endpoint):
    expected_checkpoint = (
        protocol["verified_checkpoints"][f"{binding['modality']}:{binding['algorithm']}"]
        if binding["condition"] == "process_sft"
        else None
    )
    if (
        report["protocol_id"] != protocol["protocol_id"]
        or report["binding_index"] != binding["index"]
        or report["task_id"] != binding["task_id"]
        or report["modality"] != binding["modality"]
        or report["algorithm"] != binding["algorithm"]
        or report["arm"] != binding["condition"]
        or report["seed"] != protocol["evaluation_seed"]
        or report["checkpoint"] != expected_checkpoint
        or report["model_id"] != protocol["model_id"]
        or report["model_revision"] != protocol["model_revision"]
        or report["outcome"] != "RECORDED"
        or len(report["events"]) != len(report["call_measurements"])
        or report["result"]["decision_count"] != len(report["events"])
    ):
        raise ValueError(f"episode report binding/result differs: {binding['index']}")
    model = binding["condition"] in {"pretrained_base", "process_sft"}
    if any(measurement["model_call"] != model for measurement in report["call_measurements"]):
        raise ValueError("episode model-call provenance differs from its condition")
    if report["oracle_assisted_valid_operation_control"] != (binding["condition"] == "random_valid"):
        raise ValueError("random-valid oracle assistance label differs")
    independently_replay(ROOT, task, report, endpoint)


def audit_subset(protocol, panel, tasks, selected, endpoint):
    verified = []
    missing = []
    for binding in selected:
        episode, _, _ = binding_paths(ROOT, protocol, binding)
        if not episode.exists():
            missing.append(binding)
            continue
        report = read_json(episode)
        verify_report(protocol, tasks[binding["task_id"]], binding, report, endpoint)
        verified.append(report)
    return verified, missing


def main(argv=None):
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("stage", choices=("worker", "final", "hook"))
    parser.add_argument("--config", type=Path, default=ROOT / "configs/experiments/expanded-study/baseline-protocol.json")
    parser.add_argument("--worker", type=int)
    parser.add_argument("--kind", choices=("controls", "models"))
    args = parser.parse_args(argv)
    protocol, panel, tasks = load_context(args.config)
    if args.stage == "hook":
        terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
        report = read(ROOT / "docs/experiments/expanded-study/baseline-evaluation.json")
        replay = read(ROOT / "docs/experiments/expanded-study/baseline-independent-replay.json")
        if terminal["status"] != "succeeded" or report["outcome"] != "PASS" or replay["outcome"] != "PASS":
            raise RuntimeError("expanded baseline final audit did not prove complete coverage")
        print("PASS: expanded baseline final completion hook")
        return 0
    if args.stage == "worker":
        if args.worker is None or args.kind is None:
            parser.error("worker audit requires --worker and --kind")
        selected = assigned_bindings(panel, protocol, args.worker, args.kind)
        verified, missing = audit_subset(protocol, panel, tasks, selected, protocol["endpoints"][args.worker])
        terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
        if terminal["status"] == "succeeded" and missing:
            raise ValueError("successful worker omitted frozen bindings")
        report = {
            "outcome": "PASS" if not missing else "PARTIAL",
            "terminal_status": terminal["status"],
            "worker": args.worker,
            "kind": args.kind,
            "verified_episodes": len(verified),
            "missing_bindings": missing,
            "independent_replay": True,
        }
        write(Path(terminal["directory"]) / "independent-audit.json", report)
        print(f"{report['outcome']}: replayed {len(verified)}; missing {len(missing)}")
        return 0
    all_bindings = bindings(panel, protocol)
    verified, missing = audit_subset(protocol, panel, tasks, all_bindings, protocol["endpoints"][0])
    ledger = read(ROOT / "outputs/expanded-study/v1/budget.json")
    job_ids = [f"baseline-{kind}-{worker}" for kind in ("controls", "models") for worker in range(2)]
    attempts = {job_id: [a for a in ledger["attempts"] if a["job_id"] == job_id][-1] for job_id in job_ids}
    if any(a["status"] != "succeeded" for a in attempts.values()) or missing:
        raise ValueError("final audit requires all four baseline workers and all frozen bindings")
    coverage = Counter((r["modality"], r["algorithm"], r["arm"]) for r in verified)
    expected_coverage = {
        (m, a, c): 24 for m in protocol["modalities"] for a in protocol["algorithms"] for c in protocol["conditions"]
    }
    if dict(coverage) != expected_coverage:
        raise ValueError("expanded baseline cell coverage differs")
    def empty_metrics():
        return {"episodes": 0, "successes": 0, "decisions": 0, "invalid_operations": 0}

    by_condition = defaultdict(empty_metrics)
    by_cell = defaultdict(empty_metrics)
    for report in verified:
        for row in (
            by_condition[report["arm"]],
            by_cell[(report["modality"], report["algorithm"], report["arm"])],
        ):
            row["episodes"] += 1
            row["successes"] += int(report["result"]["invariant_valid_success"])
            row["decisions"] += report["result"]["decision_count"]
            row["invalid_operations"] += report["result"]["invalid_operation_count"]
    spent = sum(a["gpu_hours"] for a in ledger["attempts"] if a["branch"] == "expanded_baseline")
    evaluation = {
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "panel_id": protocol["panel_id"],
        "logical_bindings": len(verified),
        "model_episodes": sum(r["arm"] in {"pretrained_base", "process_sft"} for r in verified),
        "complete_coverage": True,
        "missing_bindings": [],
        "coverage": [
            {"modality": m, "algorithm": a, "condition": c, "episodes": n}
            for (m, a, c), n in sorted(coverage.items())
        ],
        "by_condition": dict(by_condition),
        "by_cell": [
            {
                "modality": modality,
                "algorithm": algorithm,
                "condition": condition,
                **metrics,
            }
            for (modality, algorithm, condition), metrics in sorted(by_cell.items())
        ],
        "random_valid_is_oracle_assisted": True,
        "new_training": False,
        "raw_invalid_outputs_preserved": sum(r["raw_invalid_outputs_preserved"] for r in verified),
        "expanded_baseline_gpu_hours_cumulative": spent,
        "branch_cap_gpu_hours": ledger["allocations_gpu_hours"]["expanded_baseline"],
        "worker_attempts": attempts,
        "finished": time.time(),
    }
    replay = {
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "episodes_replayed": len(verified),
        "expected_episodes": protocol["logical_bindings"],
        "every_episode_replayed": True,
        "replay_used_read_only_persisted_views": True,
        "missing_bindings": [],
    }
    write(ROOT / "docs/experiments/expanded-study/baseline-evaluation.json", evaluation)
    write(ROOT / "docs/experiments/expanded-study/baseline-independent-replay.json", replay)
    write(os.environ["EXPANDED_PROGRESS_PATH"], {"completed": len(verified), "total": len(all_bindings)})
    print(f"PASS: independently replayed all {len(verified)} expanded baseline bindings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
