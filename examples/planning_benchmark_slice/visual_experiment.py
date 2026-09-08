"""Frozen #75 scope, clock, permissions and outcome-blind coverage selection."""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path

from src.data_collect.governance import (
    AuthorizationReceipt,
    GateReceipt,
    ReceiptBinding,
    StopOutcome,
    evaluate_execution_permission,
)

from .modality_corpus import ModalityCorpus
from .modality_view_preparation import write_json
from .scene_assets import read_json

ROOT = Path(__file__).resolve().parents[2]
ALGORITHMS = ("bfs", "best_first_width", "best_first_add_w3", "best_first_add_greedy")
ARMS = ("exact_reference", "random_valid", "pretrained_base", "process_sft")


class VisualExperiment:
    def __init__(self, config_path=ROOT / "configs/experiments/issue75/experiment.json"):
        self.config = read_json(config_path)
        c = self.config
        self.output = ROOT / c["output_root"]
        auth = read_json(ROOT / c["authorization"])
        gate = GateReceipt(
            ReceiptBinding(**auth["gate"]["binding"]),
            StopOutcome(auth["gate"]["outcome"]),
            auth["gate"].get("ancestor_receipt_id"),
        )
        authorization = AuthorizationReceipt(ReceiptBinding(**auth["binding"]), auth["gate_receipt_id"])
        binding = ReceiptBinding(c["contract_id"], self.output.name, self.output.resolve())
        self.permission = evaluate_execution_permission(
            binding=binding,
            gate_receipt=gate,
            authorization_receipt=authorization,
            ancestor_receipt_id=gate.ancestor_receipt_id,
        )
        if not self.permission.start_permitted:
            raise RuntimeError(f"{self.permission.outcome.value}: {self.permission.reason}")
        if auth["experiment"] != c:
            raise ValueError("experiment authorization settings differ")
        self.corpus = ModalityCorpus(ROOT, ROOT / c["corpus_report"])
        source = self.corpus.contract
        if (
            c["model_id"] != source["model_id"]
            or c["model_revision"] != source["model_revision"]
            or c["context_tokens"] != source["context_tokens"]
            or c["output_tokens"] != source["output_tokens"]
            or c["training_seed"] != 17
            or c["modality"] != "visual-state"
            or c["algorithms"] != list(ALGORITHMS)
            or c["parent_freeze"] != source["parent_freeze"]
            or c["training"]["dtype"] != "bfloat16"
            or not c["training"]["freeze_vision"]
            or c["inference_dtype"] != "float32"
        ):
            raise ValueError("model, corpus or visual training scope differs")
        if (
            not 0 < c["qualification_seconds"] < c["stop_new_calls_seconds"] < c["gate_seconds"]
            or c["rollout_certification_seconds"] > c["stop_new_calls_seconds"]
            or len(set(c["devices"])) != len(c["devices"])
            or len(set(c["master_ports"])) != len(c["devices"])
        ):
            raise ValueError("invalid clock or GPU/port mapping")
        from .planimation_render import _require_local_base_url

        for endpoint in c["backend_endpoints"]:
            _require_local_base_url(endpoint)
        self.panel = read_json(ROOT / source["panel_manifest"])["selected"]
        self.dev = [r for r in self.panel if r["split"] == "dev"]
        self.train_counts = Counter()
        self.dev_counts = Counter()
        for row in self.panel:
            if row["split"] == "train":
                for algorithm, cost in row["reference_costs"].items():
                    self.train_counts[algorithm] += cost["decisions"]
            else:
                for algorithm, cost in row["reference_costs"].items():
                    self.dev_counts[algorithm] += cost["decisions"]

    def start(self, resume=False):
        path = self.output / "attempt.json"
        if (self.output / "result.json").exists():
            raise ValueError("completed matrix attempt is immutable")
        if path.exists():
            if not resume:
                raise ValueError("interrupted matrix requires --resume; the clock is not reset")
            old = read_json(path)
            if old["experiment"] != self.config:
                raise ValueError("interrupted experiment differs")
            return old
        if resume and self.output.exists():
            raise ValueError("cannot resume an output without its original attempt clock")
        attempt = {
            "experiment": self.config,
            "permission": self.permission.to_dict(),
            "started_unix": time.time(),
            "started_monotonic": time.monotonic(),
        }
        write_json(path, attempt)
        return attempt

    def deadline(self, stage="calls"):
        attempt = read_json(self.output / "attempt.json")
        seconds = self.config["stop_new_calls_seconds"] if stage == "calls" else self.config["gate_seconds"]
        if time.monotonic() < attempt["started_monotonic"]:
            raise RuntimeError("VALID_STOP: original monotonic clock is unavailable")
        return attempt["started_monotonic"] + seconds

    def require(self, stage):
        if time.monotonic() >= self.deadline("gate" if stage == "adjudicate" else "calls"):
            raise RuntimeError("VALID_STOP: original matrix cutoff has elapsed")
        predecessors = {
            "train": ("qualification",),
            "references": ("qualification",),
            "evaluate": ("qualification", "training"),
            "adjudicate": ("references", "evaluation"),
        }.get(stage, ())
        for predecessor in predecessors:
            path = self.output / f"{predecessor}.json"
            if not path.is_file():
                raise RuntimeError(f"VALID_STOP: missing {predecessor} stage")
            report = read_json(path)
            if report.get("contract_id") != self.config["contract_id"]:
                raise ValueError("stage predecessor contract differs")
            if report.get("outcome") in ("VALID_STOP", "ANCESTOR_STOP"):
                raise RuntimeError(f"ANCESTOR_STOP: {predecessor} did not pass")
            if report.get("outcome") != "PASS":
                raise ValueError(f"invalid {predecessor} predecessor")
            if predecessor == "qualification":
                selection = report.get("selection", {})
                expected = self.dev if selection.get("mode") == "full" else cheapest_panel(self.dev)
                devices = report.get("device_qualifications", [])
                if (
                    selection.get("mode") not in ("full", "cost_fallback")
                    or selection.get("task_ids") != [r["task_id"] for r in expected]
                    or len(devices) != len(self.config["devices"])
                    or {d.get("worker") for d in devices} != set(range(len(self.config["devices"])))
                    or any(
                        d.get("outcome") != "PASS" or d.get("contract_id") != self.config["contract_id"] for d in devices
                    )
                    or report.get("model_outcomes_used_for_selection") is not False
                ):
                    raise ValueError("qualification coverage or device scope is incomplete")
            if predecessor == "training":
                runs = report.get("training_runs", [])
                if len(runs) != len(ALGORITHMS) or {r.get("algorithm") for r in runs} != set(ALGORITHMS):
                    raise ValueError("training cell coverage is incomplete")
                for run in runs:
                    algorithm = run["algorithm"]
                    expected_checkpoint = self.output / "training" / algorithm / "final"
                    if (
                        run.get("outcome") != "PASS"
                        or run.get("seed") != 17
                        or run.get("contract_id") != self.config["contract_id"]
                        or run.get("steps") != training_steps(self.train_counts[algorithm], self.config["training"])
                        or run.get("train_records") != self.train_counts[algorithm]
                        or (ROOT / run.get("final_checkpoint", "")).resolve() != expected_checkpoint.resolve()
                        or not (expected_checkpoint / "adapter_config.json").is_file()
                    ):
                        raise ValueError("training checkpoint/seed/coverage differs")

    def plan(self):
        rows = self.dev
        episodes = sum(len(r["reference_costs"]) for r in rows)
        return {
            "outcome": "PASS",
            "dry_run": True,
            "writes": 0,
            "contract_id": self.config["contract_id"],
            "modality": "visual-state",
            "train_records": dict(self.train_counts),
            "training_runs": 4,
            "training_seed": 17,
            "optimizer_steps": {a: training_steps(n, self.config["training"]) for a, n in self.train_counts.items()},
            "full_dev_task_groups": len(rows),
            "full_dev_algorithm_episodes": episodes,
            "planned_condition_episodes": episodes * (1 + 3 * len(self.config["evaluation_seeds"])),
            "fallback_task_groups": len(cheapest_panel(rows)),
            "devices": self.config["devices"],
            "master_ports": self.config["master_ports"],
            "backend_endpoints": self.config["backend_endpoints"],
            "stages": ["qualification", "references", "training", "evaluation", "adjudication"],
            "model_calls_started": False,
            "scientific_completion": False,
            "clock_seconds": self.config["gate_seconds"],
            "actual_hardware_qualification_required": True,
        }


def cheapest_panel(rows):
    selected = {}
    for row in rows:
        family = "additive" if row["task_id"].startswith("astar-pair-") else next(iter(row["reference_costs"]))
        key = (family, row["domain"])
        cost = (sum(c["decisions"] for c in row["reference_costs"].values()), row["task_id"])
        if key not in selected or cost < selected[key][0]:
            selected[key] = (cost, row)
    return sorted((value[1] for value in selected.values()), key=lambda r: r["task_id"])


def select_coverage(experiment, qualifications):
    """Conservative full/fallback estimates use timings only, never model success."""
    c = experiment.config
    seconds_per_call = max(q["seconds_per_call"] for q in qualifications)
    training_seconds = (
        max(q["training_microstep_seconds"] for q in qualifications)
        * (sum(experiment.train_counts.values()) * c["training"]["epochs"] + 2 * sum(experiment.dev_counts.values()))
        / len(qualifications)
    )
    elapsed = time.monotonic() - read_json(experiment.output / "attempt.json")["started_monotonic"]
    estimates = []
    for name, rows in [("full", experiment.dev), ("cost_fallback", cheapest_panel(experiment.dev))]:
        calls = (
            2
            * 2
            * len(c["evaluation_seeds"])
            * sum(cost["decisions"] for r in rows for cost in r["reference_costs"].values())
        )
        rollout = calls * seconds_per_call / len(qualifications)
        projected = elapsed + 1.2 * (training_seconds + rollout)
        estimates.append(
            {
                "mode": name,
                "task_ids": [r["task_id"] for r in rows],
                "scheduled_model_calls": calls,
                "projected_rollout_seconds": rollout,
                "projected_training_seconds": training_seconds,
                "projected_total_seconds": projected,
            }
        )
        if projected <= c["stop_new_calls_seconds"] and 1.2 * rollout <= c["rollout_certification_seconds"]:
            return {
                "contract_id": c["contract_id"],
                "outcome": "PASS",
                "selection": estimates[-1],
                "estimates": estimates,
                "device_qualifications": qualifications,
                "model_outcomes_used_for_selection": False,
            }
    return {
        "contract_id": c["contract_id"],
        "outcome": "VALID_STOP",
        "reason": "neither frozen panel fits the clock",
        "estimates": estimates,
        "device_qualifications": qualifications,
        "model_outcomes_used_for_selection": False,
    }


def training_steps(records, training):
    import math

    return math.ceil(records / training["global_batch_size"]) * training["epochs"]
