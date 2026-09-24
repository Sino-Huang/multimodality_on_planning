#!/usr/bin/env python
"""Choice-frontier v4 seeds (#138): 3-seed replication of the #136 adapter.

Derived from ``scripts/run_choice_frontier_v3.py`` (#136, frozen and imported
read-only, never edited). Protocol: ``configs/experiments/choice-frontier-v4/
seeds-protocol.json`` / ``docs/experiments/choice-frontier/issue-138-protocol.md``.
Unchanged #136 machinery (augmentation, episode runner, independent replay,
policy loading, panel loading, smoke tasks, train audit) is imported from the
v3 module and always called with the v4 protocol, so every path resolves under
``outputs/choice-frontier/v4/seeds``. Stages changed for #138:

- ``train --algorithm A --seed S`` / ``audit-train`` — seeds 29/71 on the frozen
  #136 corpus and store (read-only from v3); the sample order is pinned to the
  #136 ``order:17`` so the seed changes only LoRA init and dropout.
- ``smoke`` / ``audit-smoke`` — the #132 smoke gate on the seed-29 adapters.
- ``evaluate-inputs`` / ``evaluate-worker --algorithm A --seed S`` /
  ``audit-evaluate-worker`` — the new cells on the frozen #135 panel; the hook
  derives the attempt dir from ``EXPANDED_TERMINAL_PATH`` (the #136 fix).
- ``finalize`` — independent replay of every v4 model episode.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.choice_frontier import (  # noqa: E402
    CHOICE_ARM,
    CHOICE_LEGEND,
    CHOICE_RECIPE_ID,
    CHOICE_SCHEMA,
    CHOICE_SYSTEM_MESSAGE,
)
from examples.planning_benchmark_slice.scene_assets import read_json  # noqa: E402
from scripts import run_choice_frontier_v3 as v3  # noqa: E402

PROTOCOL_PATH = ROOT / "configs/experiments/choice-frontier-v4/seeds-protocol.json"
SCHEDULE_PATH = Path("docs/experiments/choice-frontier/schedule-v4.json")
LEDGER_PATH = ROOT / "outputs/choice-frontier/v4/budget.json"
V3_MEMBERSHIP = v3.MEMBERSHIP
V3_STORE = ROOT / "outputs/choice-frontier/v3/preparation/store.json"
V3_MEMBERSHIP_SHA256 = "f5cc9b2ac3b2fe8e94b7a8039e6b9cd828c701a8c5b707ddd7a3b01b2ca8c077"
SAMPLE_ORDER_SEED = 17
RECIPE_KEYS = (
    "study", "study_sha256", "epochs", "global_batch_size", "microbatch_size", "learning_rate", "lr_scheduler",
    "warmup_ratio", "lora", "dtype", "samples_per_cell", "optimizer_updates", "max_seconds_per_cell",
)
ALGORITHMS = v3.ALGORITHMS
ENDPOINT = v3.ENDPOINT
write = v3.write


def load_protocol() -> dict:
    protocol = read_json(PROTOCOL_PATH)
    protocol["root"] = str(ROOT)
    return protocol


def output_root(protocol: dict) -> Path:
    return ROOT / protocol["output_root"]


def frozen_membership() -> dict:
    membership = read_json(V3_MEMBERSHIP)
    if membership["membership_sha256"] != V3_MEMBERSHIP_SHA256 or v3.membership_sha(membership) != V3_MEMBERSHIP_SHA256:
        raise ValueError("#136 corpus membership_sha256 differs from f5cc9b2a...c077")
    return membership


# --------------------------------------------------------------------------- #
# train / audit-train (frozen #136 corpus; only the training seed changes)
# --------------------------------------------------------------------------- #


class PinnedOrderDataset(v3.AugmentedChoiceDataset):
    """#136 dataset whose sample order is pinned to ``order:17`` for every training seed.

    The #136 class seeds its shuffle with ``order:{training_seed}`` (``order:17`` in #136);
    passing 17 reproduces the #136 sample sequence byte-for-byte for seeds 29/71.
    """

    def __init__(self, store: dict, membership: dict, algorithm: str, seed: int, split: str):
        super().__init__(store, membership, algorithm, SAMPLE_ORDER_SEED, split)


def train_stage(algorithm: str, seed: int) -> dict:
    if os.environ.get("CUDA_VISIBLE_DEVICES") is None:
        raise ValueError("choice-frontier training requires CUDA_VISIBLE_DEVICES isolation")
    if not os.environ.get("MASTER_PORT"):
        raise ValueError("choice-frontier training requires an explicit scheduler MASTER_PORT")
    protocol = load_protocol()
    if algorithm not in protocol["learned_algorithms"] or seed not in protocol["training_seeds"]:
        raise ValueError("choice-frontier v4 cell is not in the frozen protocol")
    training = protocol["training"]
    membership = frozen_membership()
    store = read_json(V3_STORE)
    progress = v3.progress_writer()

    def factory(root, config, algo, split):
        return PinnedOrderDataset(store, membership, algo, seed, split)

    from examples.planning_benchmark_slice.visual_model import train_visual

    study = read_json(ROOT / training["study"])
    if v3.sha256_file(ROOT / training["study"]) != training["study_sha256"]:
        raise ValueError("study-v5 sha differs")
    if (study["model_id"], study["model_revision"]) != (protocol["model_id"], protocol["model_revision"]):
        raise ValueError("study-v5 backbone differs from the frozen protocol")
    config = {**study, "modality": CHOICE_ARM, "training_seed": int(seed)}
    output = v3.cell_dir(protocol, algorithm, seed)
    deadline = time.monotonic() + float(training["max_seconds_per_cell"])
    started = time.monotonic()
    result = train_visual(config, ROOT, algorithm, output, deadline=deadline, progress=progress, dataset_factory=factory)
    result["arm"] = CHOICE_ARM
    result["train_samples"] = result.pop("train_records")
    result["train_records"] = len(membership["training_record_ids"][algorithm])
    result["training_record_ids"] = [*result["training_record_ids"][:8], "..."]
    summary = {
        "schema_version": "choice_frontier_v4_seeds_training_v1",
        "protocol_id": protocol["protocol_id"],
        "arm": CHOICE_ARM,
        "algorithm": algorithm,
        "seed": seed,
        "sample_order_seed": f"order:{SAMPLE_ORDER_SEED}",
        "corpus_membership_sha256": membership["membership_sha256"],
        "cell": result,
        "wall_seconds": time.monotonic() - started,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "master_port": os.environ.get("MASTER_PORT"),
        "outcome": "PASS",
    }
    write(output / "report.json", summary)
    return summary


def audit_train_stage(algorithm: str | None = None, seed: int | None = None) -> dict:
    protocol = load_protocol()
    membership = frozen_membership()
    cells = []
    for a in protocol["learned_algorithms"]:
        for s in protocol["training_seeds"]:
            if (algorithm is None or a == algorithm) and (seed is None or s == seed):
                cell = v3.audit_cell(protocol, membership, a, s)
                report_path = v3.cell_dir(protocol, a, s) / "report.json"
                report = read_json(report_path) if report_path.is_file() else {}
                cell.setdefault("checks", {})
                cell["checks"]["sample_order_order_17"] = report.get("sample_order_seed") == f"order:{SAMPLE_ORDER_SEED}"
                cell["checks"]["corpus_membership_sha"] = report.get("corpus_membership_sha256") == V3_MEMBERSHIP_SHA256
                cell["ok"] = cell.get("ok", False) and all(cell["checks"].values())
                cells.append(cell)
    audit = {
        "schema_version": "choice_frontier_v4_seeds_train_audit_v1",
        "protocol_id": protocol["protocol_id"],
        "cells": cells,
        "ok": bool(cells) and all(c["ok"] for c in cells),
    }
    name = "audit.json" if algorithm is None else f"audit-{algorithm}-s{seed}.json"
    write(output_root(protocol) / "training" / name, audit)
    return audit


# --------------------------------------------------------------------------- #
# smoke gate (the #132 definition on the seed-29 adapters)
# --------------------------------------------------------------------------- #


def smoke_gate(protocol: dict) -> str | None:
    path = output_root(protocol) / "smoke" / "smoke.json"
    return read_json(path)["gate"] if path.is_file() else None


def smoke_bindings(protocol: dict, tasks: list[dict]) -> list[dict]:
    rows = v3.smoke_bindings(protocol, tasks)
    return [{**row, "training_seed": int(protocol["smoke_gate"]["training_seed"])} for row in rows]


def smoke_stage(endpoint: str) -> dict:
    if os.environ.get("CUDA_VISIBLE_DEVICES") is None:
        raise ValueError("choice-frontier smoke requires CUDA_VISIBLE_DEVICES isolation")
    if not os.environ.get("MASTER_PORT"):
        raise ValueError("choice-frontier smoke requires an explicit scheduler MASTER_PORT")
    protocol = load_protocol()
    if smoke_gate(protocol) is not None:
        raise ValueError("choice-frontier smoke gate already exists; refusing an outcome-selected rerun")
    tasks = v3.smoke_tasks(protocol)
    rows = smoke_bindings(protocol, tasks)
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    training_seed = int(protocol["smoke_gate"]["training_seed"])
    adapters = {a: v3.adapter_path(protocol, a, training_seed) for a in protocol["learned_algorithms"]}
    policy = v3.load_policy(protocol, adapters)
    model_calls = 0
    accepted_calls = 0
    episodes = []
    progress = v3.progress_writer()
    for position, binding in enumerate(rows):

        def generate(example, algorithm=binding["algorithm"]):
            nonlocal model_calls
            output = policy.generate([example], algorithm)[0]
            model_calls += 1
            return output, policy.last_generation_usage["generated_sequence_tokens"]

        report, _retained = v3.run_binding(
            ROOT, protocol, task_by_id[binding["task_id"]], binding, adapters[binding["algorithm"]], endpoint,
            generate, smoke=True,
        )
        calls = len(report["events"])
        invalid = report["result"]["invalid_operation_count"]
        accepted_calls += calls - invalid
        episodes.append(
            {
                "task_id": binding["task_id"],
                "algorithm": binding["algorithm"],
                "training_seed": training_seed,
                "calls": calls,
                "accepted": calls - invalid,
                "goal_reached": report["result"]["goal_reached"],
                "termination_reason": report["result"]["termination_reason"],
            }
        )
        progress("choice_smoke", completed=position + 1, total=len(rows))
    rate = accepted_calls / model_calls if model_calls else 0.0
    threshold = float(protocol["smoke_gate"]["threshold"])
    result = {
        "schema_version": "choice_frontier_smoke_v1",
        "protocol_id": protocol["protocol_id"],
        "training_seed": training_seed,
        "episodes": episodes,
        "model_calls": model_calls,
        "accepted_calls": accepted_calls,
        "schema_valid_grounded_rate": rate,
        "threshold": threshold,
        "gate": "PASS" if rate >= threshold else "FAIL",
    }
    write(output_root(protocol) / "smoke" / "smoke.json", result)
    return result


def audit_smoke_stage(endpoint: str) -> dict:
    protocol = load_protocol()
    report = read_json(output_root(protocol) / "smoke" / "smoke.json")
    tasks = v3.smoke_tasks(protocol)
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    replayed = accepted_calls = model_calls = 0
    for binding in smoke_bindings(protocol, tasks):
        episode, _partial, _views = v3.episode_paths(protocol, binding, smoke=True)
        stored = read_json(episode)
        v3.independently_replay(ROOT, protocol, task_by_id[binding["task_id"]], stored, endpoint, smoke=True)
        replayed += 1
        model_calls += len(stored["events"])
        accepted_calls += len(stored["events"]) - stored["result"]["invalid_operation_count"]
    rate = accepted_calls / model_calls if model_calls else 0.0
    threshold = float(protocol["smoke_gate"]["threshold"])
    gate = "PASS" if rate >= threshold else "FAIL"
    audit = {
        "schema_version": "choice_frontier_smoke_audit_v1",
        "protocol_id": protocol["protocol_id"],
        "episodes_replayed": replayed,
        "recomputed_rate": rate,
        "stored_rate": report["schema_valid_grounded_rate"],
        "gate": gate,
        "matches_stored": report["gate"] == gate and abs(rate - report["schema_valid_grounded_rate"]) < 1e-9,
    }
    audit["ok"] = audit["matches_stored"] and replayed == int(protocol["smoke_gate"]["episodes"])
    write(output_root(protocol) / "smoke" / "audit.json", audit)
    return audit


# --------------------------------------------------------------------------- #
# evaluation on the frozen #135 panel
# --------------------------------------------------------------------------- #


def evaluate_inputs_stage() -> dict:
    protocol = load_protocol()
    tasks = v3.load_tasks(protocol)
    rows = v3.bindings(protocol, tasks)
    if len(rows) != protocol["evaluation"]["gpu_episodes"]:
        raise ValueError("choice-frontier v4 evaluation matrix differs from the frozen protocol")
    manifest = {
        "schema_version": "choice_frontier_evaluation_inputs_v1",
        "protocol_id": protocol["protocol_id"],
        "membership_sha256": protocol["evaluation"]["membership_sha256"],
        "bindings": rows,
        "counts": {"models": len(rows)},
    }
    write(output_root(protocol) / "evaluation" / "bindings.json", manifest)
    return manifest


def evaluate_worker(algorithm: str, seed: int, endpoint: str) -> dict:
    if os.environ.get("CUDA_VISIBLE_DEVICES") is None:
        raise ValueError("choice-frontier model worker requires CUDA_VISIBLE_DEVICES isolation")
    if not os.environ.get("MASTER_PORT"):
        raise ValueError("choice-frontier model worker requires an explicit scheduler MASTER_PORT")
    protocol = load_protocol()
    tasks = v3.load_tasks(protocol)
    manifest = read_json(output_root(protocol) / "evaluation" / "bindings.json")
    rows = [r for r in manifest["bindings"] if r["algorithm"] == algorithm and r["training_seed"] == seed]
    if len(rows) != len(tasks):
        raise ValueError("choice-frontier v4 worker partition differs from frozen coverage")
    attempt_dir = Path(os.environ["EXPANDED_ATTEMPT_DIR"])
    gate = smoke_gate(protocol)
    if gate is None:
        raise ValueError("choice-frontier evaluation requires the frozen smoke gate")
    if gate == "FAIL":
        result = {"schema_version": "choice_frontier_evaluate_worker_v1", "gated_out_by_smoke": True,
                  "episodes_completed": 0}
        write(attempt_dir / "worker-result.json", result)
        return result
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"])
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    checkpoint = v3.adapter_path(protocol, algorithm, seed)
    policy = None
    if any(not v3.episode_paths(protocol, row)[0].exists() for row in rows):
        policy = v3.load_policy(protocol, {algorithm: checkpoint})
    completed = retained = model_calls = 0
    started = time.monotonic()
    reports = []
    for binding in rows:

        def generate(example):
            nonlocal model_calls
            output = policy.generate([example], algorithm)[0]
            model_calls += 1
            return output, policy.last_generation_usage["generated_sequence_tokens"]

        report, was_retained = v3.run_binding(
            ROOT, protocol, task_by_id[binding["task_id"]], binding, checkpoint, endpoint, generate
        )
        retained += int(was_retained)
        reports.append(report["output"])
        completed += 1
        write(
            progress_path,
            {"completed": completed, "total": len(rows), "retained": retained, "model_calls": model_calls,
             "algorithm": algorithm, "training_seed": seed},
        )
    result = {
        "schema_version": "choice_frontier_evaluate_worker_v1",
        "protocol_id": protocol["protocol_id"],
        "algorithm": algorithm,
        "training_seed": seed,
        "episodes_completed": completed,
        "episodes_retained": retained,
        "model_calls": model_calls,
        "elapsed_seconds": time.monotonic() - started,
        "outputs": reports,
    }
    write(attempt_dir / "worker-result.json", result)
    return result


def audit_evaluate_worker() -> dict:
    terminal_path = Path(os.environ["EXPANDED_TERMINAL_PATH"])
    terminal = read_json(terminal_path)
    # The completion hook only receives EXPANDED_TERMINAL_PATH; the attempt dir is its parent (#136 fix).
    path = terminal_path.parent / "worker-result.json"
    result = read_json(path) if path.is_file() else {}
    ok = terminal["status"] == "succeeded" and (
        result.get("episodes_completed", 0) > 0 or result.get("gated_out_by_smoke") is True
    )
    return {
        "schema_version": "choice_frontier_evaluate_audit_v1",
        "algorithm": result.get("algorithm"),
        "training_seed": result.get("training_seed"),
        "ok": ok,
    }


def finalize_stage(endpoint: str) -> dict:
    """Independent replay of every v4 model episode; complete coverage or explicit missingness."""

    protocol = load_protocol()
    tasks = v3.load_tasks(protocol)
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    manifest = read_json(output_root(protocol) / "evaluation" / "bindings.json")
    gate = smoke_gate(protocol)
    if gate is None:
        raise ValueError("choice-frontier finalize requires the frozen smoke gate")
    replayed = 0
    missing, mismatches, gated = [], [], []
    cells = {}
    for binding in manifest["bindings"]:
        episode, partial, _views = v3.episode_paths(protocol, binding)
        if not episode.exists():
            (gated if gate == "FAIL" else missing).append(binding["index"])
            continue
        if partial.exists():
            mismatches.append({"index": binding["index"], "error": "partial journal beside completed episode"})
            continue
        report = read_json(episode)
        try:
            v3.independently_replay(ROOT, protocol, task_by_id[binding["task_id"]], report, endpoint)
        except ValueError as error:
            mismatches.append({"index": binding["index"], "error": str(error)})
            continue
        replayed += 1
        key = f"{binding['task_id']}|{binding['algorithm']}|s{binding['training_seed']}"
        cells[key] = report["result"]
    evaluation = {
        "schema_version": "choice_frontier_evaluation_v1",
        "protocol_id": protocol["protocol_id"],
        "episodes_replayed": replayed,
        "bindings_total": len(manifest["bindings"]),
        "missing_bindings": missing,
        "replay_mismatches": mismatches,
        "gated_out_by_smoke": gated,
        "smoke_gate": gate,
        "complete": not missing and not mismatches,
    }
    write(output_root(protocol) / "evaluation" / "evaluation.json", evaluation)
    write(
        output_root(protocol) / "evaluation" / "cells.json",
        {"schema_version": "choice_frontier_cells_v1", "cells": dict(sorted(cells.items()))},
    )
    return evaluation


def validate_stage() -> dict:
    protocol = load_protocol()
    arm = protocol["arms"][CHOICE_ARM]
    membership = frozen_membership()
    frozen_training = read_json(ROOT / v3.PROTOCOL_PATH)["training"]
    checks = {
        "recipe_id": arm["recipe_id"] == CHOICE_RECIPE_ID,
        "schema": arm["schema"] == CHOICE_SCHEMA,
        "legend": arm["legend"] == CHOICE_LEGEND,
        "system_message": arm["system_message"] == CHOICE_SYSTEM_MESSAGE,
        "v1_model_pin": read_json(v3.V1_PROTOCOL)["model_revision"] == protocol["model_revision"],
        "panel_membership_sha": read_json(v3.PANEL_MEMBERSHIP)["membership_sha256"]
        == protocol["evaluation"]["membership_sha256"],
        "corpus_membership_sha": membership["membership_sha256"] == V3_MEMBERSHIP_SHA256,
        "store_present": V3_STORE.is_file(),
        "recipe_matches_136": all(
            protocol["training"][key] == frozen_training[key] for key in RECIPE_KEYS
        ),
        "seed_17_adapters_present": all(
            (ROOT / f"outputs/choice-frontier/v3/training/{a}/seed-17/final/adapter_model.safetensors").is_file()
            for a in ALGORITHMS
        ),
    }
    return {"checks": checks, "ok": all(checks.values())}


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=[
            "validate",
            "train",
            "audit-train",
            "smoke",
            "audit-smoke",
            "evaluate-inputs",
            "evaluate-worker",
            "audit-evaluate-worker",
            "finalize",
        ],
    )
    parser.add_argument("--algorithm", choices=list(ALGORITHMS), default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--endpoint", default=ENDPOINT)
    args = parser.parse_args(argv)

    if args.stage == "validate":
        result = validate_stage()
    elif args.stage == "train":
        if args.algorithm is None or args.seed is None:
            raise ValueError("train requires --algorithm and --seed")
        result = train_stage(args.algorithm, args.seed)
    elif args.stage == "audit-train":
        result = audit_train_stage(args.algorithm, args.seed)
    elif args.stage == "smoke":
        result = smoke_stage(args.endpoint)
    elif args.stage == "audit-smoke":
        result = audit_smoke_stage(args.endpoint)
    elif args.stage == "evaluate-inputs":
        result = evaluate_inputs_stage()
    elif args.stage == "evaluate-worker":
        if args.algorithm is None or args.seed is None:
            raise ValueError("evaluate-worker requires --algorithm and --seed")
        result = evaluate_worker(args.algorithm, args.seed, args.endpoint)
    elif args.stage == "audit-evaluate-worker":
        result = audit_evaluate_worker()
    elif args.stage == "finalize":
        result = finalize_stage(args.endpoint)
    else:  # pragma: no cover
        raise ValueError(args.stage)
    print(json.dumps(result, indent=2, sort_keys=True, default=str)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
