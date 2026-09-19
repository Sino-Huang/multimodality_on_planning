"""Reproducible #75 scope, run clock and outcome-blind coverage selection."""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path

from .modality_corpus import ModalityCorpus
from .modality_view_preparation import write_json
from .scene_assets import read_json
from .visual_panel import load_cost_panel

ROOT = Path(__file__).resolve().parents[2]
ALGORITHMS = ("bfs", "best_first_width", "best_first_add_w3", "best_first_add_greedy")
ARMS = ("exact_reference", "random_valid", "pretrained_base", "process_sft")


class VisualExperiment:
    def __init__(self, config_path=ROOT / "configs/experiments/issue75/experiment.json", output=None):
        self.config = read_json(config_path)
        c = self.config
        self.output = (ROOT / (output or c["output_root"])).resolve()
        c["output_root"] = str(self.output)
        self.corpus = ModalityCorpus(ROOT, ROOT / c["corpus_report"])
        source = self.corpus.contract
        if (
            c["model_id"] != source["model_id"]
            or c["model_revision"] != source["model_revision"]
            or c["context_tokens"] != source["context_tokens"]
            or c["output_tokens"] != source["output_tokens"]
            or c["training_seed"] != 17
            or c["modality"] not in ("visual-state", "multimodal-state")
            or c["modality"] not in source["released_modalities"]
            or c["algorithms"] != list(ALGORITHMS)
            or c["parent_freeze"] != source["parent_freeze"]
            or c["training"]["dtype"] != "bfloat16"
            or not c["training"]["freeze_vision"]
            or c["inference_dtype"] != "float32"
        ):
            raise ValueError("model, corpus or visual training scope differs")
        if c.get("budget_mode", "hard") not in ("hard", "advisory", "timeboxed"):
            raise ValueError("budget_mode must be hard, advisory or timeboxed")
        if (
            not 0 < c["stop_new_calls_seconds"] < c["gate_seconds"]
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
        self.cost_panel = load_cost_panel(ROOT / c["cost_panel"], c, self.dev) if c.get("cost_panel") else None
        self.pilot = read_json(ROOT / c["pilot_manifest"]) if c.get("pilot_manifest") else None
        if self.pilot:
            if (
                self.pilot["schema"] != "deadline_pilot_v1"
                or c.get("study_scope") != "deadline_pilot"
                or self.pilot["corpus_report"] != c["corpus_report"]
                or c["evaluation_seeds"] != [17]
                or not set(self.pilot["selected_task_ids"]) <= {r["task_id"] for r in self.dev}
            ):
                raise ValueError("pilot source, scope or seed differs")
            for key in ("training_record_ids", "diagnostic_record_ids"):
                if set(self.pilot[key]) != set(ALGORITHMS) or any(
                    not ids or len(ids) != len(set(ids)) for ids in self.pilot[key].values()
                ):
                    raise ValueError("pilot record membership is incomplete or duplicated")
            self.train_counts = Counter({a: len(ids) for a, ids in self.pilot["training_record_ids"].items()})
            self.dev_counts = Counter({a: len(ids) for a, ids in self.pilot["diagnostic_record_ids"].items()})

    def start(self, resume=False):
        path = self.output / "attempt.json"
        if (self.output / "result.json").exists():
            raise ValueError("completed run already exists; use --output with a new directory")
        if path.exists():
            if not resume:
                raise ValueError("interrupted matrix requires --resume; the clock is not reset")
            old = read_json(path)
            if (
                old["experiment"] != self.config
                or old.get("cost_panel") != self.cost_panel
                or old.get("pilot_manifest") != self.pilot
            ):
                raise ValueError("interrupted experiment differs")
            return old
        if resume and self.output.exists():
            raise ValueError("cannot resume an output without its original attempt clock")
        attempt = {
            "experiment": self.config,
            "cost_panel": self.cost_panel,
            "pilot_manifest": self.pilot,
            "started_unix": time.time(),
            "started_monotonic": time.monotonic(),
        }
        write_json(path, attempt)
        return attempt

    def deadline(self, stage="calls"):
        attempt = read_json(self.output / "attempt.json")
        if self.config.get("budget_mode", "hard") == "advisory":
            return float("inf")
        seconds = self.config["stop_new_calls_seconds"] if stage == "calls" else self.config["gate_seconds"]
        if time.monotonic() < attempt["started_monotonic"]:
            raise RuntimeError("VALID_STOP: original monotonic clock is unavailable")
        return attempt["started_monotonic"] + seconds

    def reused_qualification(self):
        """Reuse passed hardware probes when only bookkeeping/budget settings changed."""
        source = ROOT / self.config["qualification_source"]
        report = read_json(source)
        previous = read_json(source.parent / "attempt.json")["experiment"]
        bookkeeping = {
            "contract_id",
            "output_root",
            "budget_mode",
            "gate_seconds",
            "stop_new_calls_seconds",
            "rollout_certification_seconds",
            "qualification_source",
            "cost_panel",
            "pilot_manifest",
            "study_scope",
            "evaluation_seeds",
            "coverage",
            "qualification",
        }

        def hardware_settings(config):
            settings = {k: v for k, v in config.items() if k not in bookkeeping}
            settings["training"] = {k: v for k, v in config["training"].items() if k != "epochs"}
            return settings

        if hardware_settings(previous) != hardware_settings(self.config):
            raise ValueError("qualification reuse requires unchanged model, data, training and device settings")
        if report.get("outcome") not in ("PASS", "VALID_STOP") or report.get("contract_id") != previous["contract_id"]:
            raise ValueError("qualification source is invalid")
        qualifications = []
        for worker in range(len(self.config["devices"])):
            device = read_json(source.parent / "qualification" / f"{worker}.json")
            probes = [
                read_json(p)
                for p in sorted((source.parent / "qualification" / f"worker-{worker}-probes").glob("*.json"))
            ]
            if (
                device.get("outcome") != "PASS"
                or device.get("worker") != worker
                or device.get("contract_id") != previous["contract_id"]
                or device.get("probe_records", 0) != len(probes)
                or not probes
                or len({p["record_id"] for p in probes}) != len(probes)
                or any(p.get("outcome") != "PASS" or p.get("modality") != self.config["modality"] for p in probes)
                or device.get("dtype") != self.config["inference_dtype"]
                or device.get("attention_implementation") != self.config["inference_attention"]
                or device.get("timing_output_tokens") != self.config["output_tokens"]
                or device.get("model_outcomes_used_for_selection") is not False
            ):
                raise ValueError("qualification source has incomplete or mismatched hardware coverage")
            qualifications.append(device)
        return qualifications, previous["contract_id"]

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
                mode = selection.get("mode")
                if self.pilot and mode != "deadline_pilot":
                    raise ValueError("qualification must use the configured pilot")
                if self.cost_panel and mode != "cost_ranked":
                    raise ValueError("qualification must use the configured cost-ranked panel")
                if mode == "deadline_pilot" and self.pilot:
                    expected = [r for r in self.dev if r["task_id"] in self.pilot["selected_task_ids"]]
                elif mode == "cost_ranked" and self.cost_panel:
                    expected = [r for r in self.dev if r["task_id"] in self.cost_panel["selected_task_ids"]]
                else:
                    expected = self.dev if mode == "full" else cheapest_panel(self.dev)
                devices = report.get("device_qualifications", [])
                if (
                    mode not in ("full", "cost_fallback", "cost_ranked", "deadline_pilot")
                    or (mode == "deadline_pilot" and not self.pilot)
                    or (mode == "cost_ranked" and not self.cost_panel)
                    or selection.get("task_ids") != [r["task_id"] for r in expected]
                    or len(devices) != len(self.config["devices"])
                    or {d.get("worker") for d in devices} != set(range(len(self.config["devices"])))
                    or any(
                        d.get("outcome") != "PASS"
                        or d.get("contract_id") != report.get("qualification_contract_id", self.config["contract_id"])
                        for d in devices
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
        selected = [r for r in rows if not self.cost_panel or r["task_id"] in self.cost_panel["selected_task_ids"]]
        if self.pilot:
            selected = [r for r in rows if r["task_id"] in self.pilot["selected_task_ids"]]
        selected_episodes = sum(len(r["reference_costs"]) for r in selected)
        return {
            "outcome": "PASS",
            "dry_run": True,
            "writes": 0,
            "contract_id": self.config["contract_id"],
            "modality": self.config["modality"],
            "train_records": dict(self.train_counts),
            "training_runs": 4,
            "training_seed": 17,
            "evaluation_seeds": self.config["evaluation_seeds"],
            "study_scope": self.config.get("study_scope", "development_matrix"),
            "comparison_scope": self.config.get("comparison_scope", "within_modality"),
            "optimizer_steps": {a: training_steps(n, self.config["training"]) for a, n in self.train_counts.items()},
            "full_dev_task_groups": len(rows),
            "full_dev_algorithm_episodes": episodes,
            "selected_dev_task_groups": len(selected),
            "selected_dev_algorithm_episodes": selected_episodes,
            "planned_condition_episodes": selected_episodes * (1 + 3 * len(self.config["evaluation_seeds"])),
            "cost_panel": self.config.get("cost_panel"),
            "evaluation_cost": self.cost_panel["evaluation"] if self.cost_panel else None,
            "training_cost": self.cost_panel["training"] if self.cost_panel else None,
            "fallback_task_groups": len(cheapest_panel(rows)),
            "devices": self.config["devices"],
            "master_ports": self.config["master_ports"],
            "backend_endpoints": self.config["backend_endpoints"],
            "stages": ["qualification", "references", "training", "evaluation", "adjudication"],
            "model_calls_started": False,
            "scientific_completion": False,
            "clock_seconds": (
                self.config["gate_seconds"] if self.config.get("budget_mode", "hard") != "advisory" else None
            ),
            "budget_mode": self.config.get("budget_mode", "hard"),
            "reference_budget_seconds": self.config["gate_seconds"],
            "qualification_source": self.config.get("qualification_source"),
            "output_root": str(self.output),
            "qualification_modalities": [self.config["modality"]],
            "approval_required": False,
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
    if (
        len(qualifications) != len(c["devices"])
        or {q.get("worker") for q in qualifications} != set(range(len(c["devices"])))
        or any(q.get("outcome") != "PASS" for q in qualifications)
    ):
        raise ValueError("complete passed hardware qualification is required before panel selection")
    seconds_per_call = max(q["seconds_per_call"] for q in qualifications)
    training_seconds = (
        max(q["training_microstep_seconds"] for q in qualifications)
        * (sum(experiment.train_counts.values()) * c["training"]["epochs"] + 2 * sum(experiment.dev_counts.values()))
        / len(qualifications)
    )
    elapsed = time.monotonic() - read_json(experiment.output / "attempt.json")["started_monotonic"]
    margin = experiment.cost_panel["policy"]["margin"] if experiment.cost_panel else 1.2
    estimates = []
    if experiment.cost_panel:
        panel = experiment.cost_panel
        candidates = [
            ("full", experiment.dev),
            ("cost_ranked", [r for r in experiment.dev if r["task_id"] in panel["selected_task_ids"]]),
        ]
        training_seconds = panel["training"]["combined_proxy_wall_seconds"]
    else:
        candidates = [("full", experiment.dev), ("cost_fallback", cheapest_panel(experiment.dev))]
    if experiment.pilot:
        candidates = [
            ("deadline_pilot", [r for r in experiment.dev if r["task_id"] in experiment.pilot["selected_task_ids"]])
        ]
    for name, rows in candidates:
        calls = (
            2
            * 2
            * len(c["evaluation_seeds"])
            * sum(cost["decisions"] for r in rows for cost in r["reference_costs"].values())
        )
        rollout = calls * seconds_per_call / len(qualifications)
        if experiment.cost_panel:
            key = "full_proxy_wall_seconds" if name == "full" else "selected_proxy_wall_seconds"
            rollout = experiment.cost_panel["evaluation"][key] / experiment.cost_panel["policy"]["margin"]
        if experiment.pilot and c["modality"] == "visual-state":
            rollout = experiment.pilot["evaluation_proxy_seconds"] / margin
        projected = elapsed + margin * (training_seconds + rollout)
        estimates.append(
            {
                "mode": name,
                "task_ids": [r["task_id"] for r in rows],
                "maximum_model_calls": calls,
                "projected_rollout_seconds": rollout,
                "projected_training_seconds": training_seconds,
                "projected_total_seconds": projected,
            }
        )
        estimates[-1]["fits_reference_budget"] = (
            projected <= c["stop_new_calls_seconds"] and margin * rollout <= c["rollout_certification_seconds"]
        )
    advisory = c.get("budget_mode", "hard") != "hard"
    eligible = estimates[-1:] if experiment.cost_panel else estimates
    selection = eligible[0] if advisory else next((e for e in eligible if e["fits_reference_budget"]), None)
    report = {
        "contract_id": c["contract_id"],
        "outcome": "PASS" if selection else "VALID_STOP",
        "hardware_qualification": "PASS",
        "budget_mode": c.get("budget_mode", "hard"),
        "estimate_kind": "stress_projection_not_eta",
        "estimate_assumptions": [
            "Every episode exhausts its maximum decision-call allowance.",
            "Every call costs the slowest measured forced-384-token generation.",
            "Every training example and diagnostic uses the slowest training microstep cost.",
            "Ideal device balance, 1.2 margin; references, adapter checks and I/O excluded.",
        ],
        "estimates": estimates,
        "device_qualifications": qualifications,
        "model_outcomes_used_for_selection": False,
    }
    if selection:
        report["selection"] = selection
    else:
        report["reason"] = "stress projection exceeds hard time budget for both panels"
    if experiment.cost_panel:
        report.update(
            cost_panel=c.get("cost_panel"),
            estimate_kind=experiment.cost_panel["evaluation"]["estimate_kind"],
            evaluation_cost=experiment.cost_panel["evaluation"],
            training_cost=experiment.cost_panel["training"],
            estimate_assumptions=experiment.cost_panel["limitations"],
        )
        if not selection:
            report["reason"] = "configured cost-ranked panel exceeds hard time budget"
    if experiment.pilot:
        report.update(
            study_scope="deadline_pilot",
            estimate_kind="input_weighted_evaluation_and_training_stress_not_eta",
            estimate_assumptions=[
                "Evaluation uses input-weighted forced-384-token costs and maximum episode calls.",
                "Subset training and diagnostics use the slowest measured training microstep.",
                "Ideal device balance, 1.2 margin; references, adapter checks and I/O excluded.",
                "Estimates are advisory; the live wall-clock limit stops owned workers.",
            ],
        )
    if experiment.pilot and c["modality"] == "multimodal-state":
        report["estimate_kind"] = "measured_multimodal_maximum_call_stress_not_eta"
        report["estimate_assumptions"][
            0
        ] = "Evaluation uses the slowest measured multimodal full-output call and maximum episode calls."
    return report


def training_steps(records, training):
    import math

    return math.ceil(records / training["global_batch_size"]) * training["epochs"]
