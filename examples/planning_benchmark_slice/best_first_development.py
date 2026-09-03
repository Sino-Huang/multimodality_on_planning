"""Issue-65 additive best-first development experiment."""

from __future__ import annotations

import gzip
import json
import math
import random
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.data_collect.governance import StopOutcome

from .best_first_controller import BEST_FIRST_SETTINGS, BestFirstController
from .best_first_model_input import build_compact_best_first_live_model_input
from .model_search_episode import SearchPolicyRequest
from .pddl_state import PDDLStateAuthority

_DESIGN = Path("configs/experiments/best-first-issue65-development-v1.json")
_AUTHORIZATION = Path("configs/experiments/best-first-issue65-authorization-v1.json")


@dataclass(frozen=True, slots=True)
class BestFirstDevelopmentTask:
    pair_id: str
    instance_id: str
    domain_id: str
    difficulty: str
    task_path: Path
    exact_decisions: int
    exact_expansions: int

    @property
    def model_call_limit(self) -> int:
        return 2 * self.exact_decisions


@dataclass(frozen=True, slots=True)
class BestFirstIssue65Experiment:
    repo_root: Path
    design: Mapping[str, Any]
    authorization: Mapping[str, Any]
    tasks: tuple[BestFirstDevelopmentTask, ...]
    training_manifest: Mapping[str, Any]
    train_datasets: tuple[Path, ...]
    dev_datasets: tuple[Path, ...]

    @property
    def contract_id(self) -> str:
        return str(self.design["contract_id"])

    @property
    def evaluation_seeds(self) -> tuple[int, ...]:
        return tuple(int(seed) for seed in self.design["evaluation"]["seeds"])

    def require_stage(self, stage: str) -> None:
        if (
            self.authorization.get("contract_id") != self.contract_id
            or self.authorization.get("outcome") != StopOutcome.PASS.value
            or self.authorization.get("start_permitted") is not True
            or stage not in self.authorization.get("authorized_stages", [])
        ):
            raise ValueError(f"issue #65 stage is not authorized: {stage}")

    def preflight(self) -> dict[str, Any]:
        return {
            "algorithm": self.design["algorithm"],
            "contract_id": self.contract_id,
            "development_exact_decisions": sum(task.exact_decisions for task in self.tasks),
            "development_tasks": len(self.tasks),
            "evaluation_seeds": list(self.evaluation_seeds),
            "fresh_test_accessed": False,
            "max_reference_decisions": max(task.exact_decisions for task in self.tasks),
            "maximum_calls_per_episode": max(task.model_call_limit for task in self.tasks),
            "physical_model_conditions": 2,
            "training_w3_counts": {
                "dev": self.design["expected"]["training_w3_validation_records"],
                "train": self.design["expected"]["training_w3_records"],
            },
            "training_epochs": self.design["training"]["epochs"],
            "training_seed": self.design["training"]["seed"],
            "training_runs": 1,
        }


def load_best_first_issue65(repo_root: str | Path) -> BestFirstIssue65Experiment:
    """Load the active issue-65 development contract."""

    root = Path(repo_root).resolve()
    design = _json_object(root / _DESIGN)
    authorization = _json_object(root / _AUTHORIZATION)
    if design.get("schema_version") != "best_first_issue65_development_v1":
        raise ValueError("issue #65 development design has the wrong schema")
    if (
        design.get("contract_id") != "issue-65-best-first-add-w3-development-v1"
        or design.get("source_issue") != 65
        or design.get("parent_issue") != 38
        or design.get("algorithm") != "best_first_add_w3"
        or design.get("priority") != "g + 3*h_add"
        or design.get("reopen_closed") is not True
        or design.get("training", {}).get("seed") != 17
        or design.get("training", {}).get("replicate_count") != 1
        or design.get("evaluation", {}).get("decision_call_multiplier") != 2
        or design.get("evaluation", {}).get("reference_decision_ceiling") != 1_024
    ):
        raise ValueError("issue #65 development design differs from the ticket")
    if (
        authorization.get("schema_version") != "best_first_issue65_authorization_v1"
        or authorization.get("authorization_id") != "issue-65-best-first-add-w3-authorization-v1"
        or authorization.get("contract_id") != design["contract_id"]
        or authorization.get("outcome") != StopOutcome.PASS.value
        or authorization.get("start_permitted") is not True
        or authorization.get("scientific_completion") is not False
        or authorization.get("gate_receipt")
        != {
            "contract_id": design["contract_id"],
            "outcome": StopOutcome.PASS.value,
            "receipt_id": "gate:issue-65-best-first-add-w3-development-v1:PASS",
            "source_issue": 65,
        }
    ):
        raise ValueError("issue #65 authorization differs from the active contract")

    paths = design["data"]
    corpus_receipt = _json_object(root / paths["corpus_receipt"])
    if (
        corpus_receipt.get("contract_id") != "issue-64-best-first-paired-corpus-v3"
        or corpus_receipt.get("outcome") != StopOutcome.PASS.value
        or corpus_receipt.get("scientific_completion") is not True
        or corpus_receipt.get("source_issue") != 64
    ):
        raise ValueError("issue #64 did not provide a completed corpus ancestor")
    training_manifest = _json_object(root / paths["training_manifest"])
    if (
        training_manifest.get("schema_version") != "best_first_process_training_projection_v1"
        or training_manifest.get("source_view") != "process"
        or training_manifest.get("counts") != {"dev": 13_791, "train": 17_740}
    ):
        raise ValueError("issue #64 training projection is not the released process corpus")
    train_datasets, dev_datasets = _training_paths(
        root / paths["corpus_root"],
        training_manifest,
        algorithm=str(design["algorithm"]),
    )

    assignments = {str(row["pair_id"]): str(row["split"]) for row in _gzip_jsonl(root / paths["split_ledger"])}
    task_rows = {str(row["pair_id"]): row for row in _json_object(root / paths["task_manifest"])["pairs"]}
    trace_rows = {str(row["pair_id"]): row for row in _json_object(root / paths["trace_manifest"])["pairs"]}
    selected_pair_ids = sorted(pair_id for pair_id, split in assignments.items() if split == "dev")
    tasks = []
    for pair_id in selected_pair_ids:
        task_row = task_rows[pair_id]
        trace_row = trace_rows[pair_id]
        trace = trace_row["traces"][design["algorithm"]]
        tasks.append(
            BestFirstDevelopmentTask(
                pair_id=pair_id,
                instance_id=str(task_row["instance_id"]),
                domain_id=str(task_row["domain_id"]),
                difficulty=str(task_row["difficulty"]),
                task_path=(root / paths["trace_root"] / "pairs" / pair_id / str(trace_row["task_path"])),
                exact_decisions=int(trace["decision_count"]),
                exact_expansions=int(trace["expansion_count"]),
            )
        )
    tasks.sort(key=lambda task: task.instance_id)
    expected = design["expected"]
    if (
        len(tasks) != expected["development_tasks"]
        or sum(task.exact_decisions for task in tasks) != expected["development_exact_decisions"]
        or max(task.exact_decisions for task in tasks) > design["evaluation"]["reference_decision_ceiling"]
        or any(not task.task_path.is_file() for task in tasks)
    ):
        raise ValueError("issue #65 development tasks differ from the issue #64 v3 panel")
    experiment = BestFirstIssue65Experiment(
        root,
        design,
        authorization,
        tuple(tasks),
        training_manifest,
        train_datasets,
        dev_datasets,
    )
    for stage in authorization["authorized_stages"]:
        experiment.require_stage(str(stage))
    return experiment


def build_best_first_sft_command(
    experiment: BestFirstIssue65Experiment,
    *,
    dataset_root: str | Path,
    output_root: str | Path,
    smoke: bool = False,
    resume_from_checkpoint: str | Path | None = None,
) -> tuple[str, ...]:
    """Translate the one-seed training contract into explicit ms-swift flags."""

    training = experiment.design["training"]
    optimization = training["optimization"]
    lora = training["lora"]
    dataset = Path(dataset_root).resolve()
    train_path = dataset / "data" / "train.jsonl"
    dev_path = dataset / "data" / "dev.jsonl"
    command = [
        "swift",
        "sft",
        "--tuner_backend",
        "peft",
        "--tuner_type",
        "lora",
        "--model",
        str(experiment.design["model"]["model_id"]),
        "--model_revision",
        str(experiment.design["model"]["revision"]),
        "--use_hf",
        "true",
        "--dataset",
        str(train_path),
        "--val_dataset",
        str(dev_path),
        "--split_dataset_ratio",
        "0",
        "--target_modules",
        str(lora["target_modules"]),
        "--lora_rank",
        str(lora["rank"]),
        "--lora_alpha",
        str(lora["alpha"]),
        "--lora_dropout",
        str(lora["dropout"]),
        "--lora_bias",
        str(lora["bias"]),
        "--freeze_vit",
        "true",
        "--freeze_aligner",
        "true",
        "--torch_dtype",
        "bfloat16",
        "--attn_impl",
        "sdpa",
        "--num_train_epochs",
        str(training["epochs"]),
        "--per_device_train_batch_size",
        "1",
        "--per_device_eval_batch_size",
        "1",
        "--gradient_accumulation_steps",
        str(optimization["global_batch_size"]),
        "--learning_rate",
        str(optimization["learning_rate"]),
        "--lr_scheduler_type",
        str(optimization["lr_scheduler"]),
        "--warmup_ratio",
        str(optimization["warmup_ratio"]),
        "--max_grad_norm",
        str(optimization["max_gradient_norm"]),
        "--weight_decay",
        str(optimization["weight_decay"]),
        "--optim",
        str(optimization["optimizer"]),
        "--bf16",
        "true",
        "--gradient_checkpointing",
        "true",
        "--max_length",
        str(experiment.design["model"]["context_tokens"]),
        "--seed",
        str(training["seed"]),
        "--data_seed",
        str(training["seed"]),
        "--full_determinism",
        "true",
        "--train_dataloader_shuffle",
        "false",
        "--dataloader_num_workers",
        "0",
        "--logging_strategy",
        "steps",
        "--logging_steps",
        "1",
        "--logging_first_step",
        "true",
        "--disable_tqdm",
        "false",
        "--output_dir",
        str(Path(output_root).resolve()),
        "--add_version",
        "false",
        "--report_to",
        "none",
        "--eval_strategy",
        "epoch",
        "--save_strategy",
        "steps",
        "--save_steps",
        str(expected_training_steps(experiment) // 4),
    ]
    if smoke:
        command.extend(("--max_steps", "1", "--eval_strategy", "no", "--save_steps", "1"))
    elif resume_from_checkpoint is not None:
        command.extend(("--resume_from_checkpoint", str(Path(resume_from_checkpoint).resolve())))
    return tuple(command)


def expected_training_steps(experiment: BestFirstIssue65Experiment) -> int:
    train_count = int(experiment.design["expected"]["training_w3_records"])
    batch = int(experiment.design["training"]["optimization"]["global_batch_size"])
    return math.ceil(train_count / batch) * int(experiment.design["training"]["epochs"])


class BestFirstModelSession:
    """Incremental best-first episode with independent call and expansion limits."""

    def __init__(
        self,
        *,
        authority: PDDLStateAuthority,
        task: BestFirstDevelopmentTask,
        arm: str,
        seed: int,
        adapter_id: str | None = None,
        accepted_delta_limit: int = 16,
    ) -> None:
        if arm not in {"pretrained_base", "process_sft", "random_valid", "exact_reference"}:
            raise ValueError("issue #65 episode arm is invalid")
        self.authority = authority
        self.task = task
        self.arm = arm
        self.seed = seed
        self.adapter_id = adapter_id
        self.accepted_delta_limit = accepted_delta_limit
        self.controller = BestFirstController(
            authority,
            BEST_FIRST_SETTINGS["best_first_add_w3"],
            accepted_delta_limit=accepted_delta_limit,
            retain_decision_evidence=False,
        )
        self.events: list[dict[str, Any]] = []
        self.termination_reason: str | None = "goal_reached" if authority.is_goal(authority.initial_state) else None
        self._pending: SearchPolicyRequest | None = None
        self.session_id = f"{arm}:{adapter_id or 'reference'}:{seed}:{task.instance_id}"

    @property
    def complete(self) -> bool:
        return self.termination_reason is not None

    def next_request(self) -> SearchPolicyRequest | None:
        if self._pending is not None:
            return self._pending
        while not self.complete:
            if len(self.events) >= self.task.model_call_limit:
                self.termination_reason = "decision_budget_exhausted"
                break
            if self.controller.active_state_id is None:
                state_id = self.controller.frontier_head_state_id()
                if state_id is None:
                    self.termination_reason = "frontier_exhausted"
                    break
                if self.authority.is_goal(self.controller.node_state(state_id)):
                    self.termination_reason = "goal_reached"
                    break
                if self.controller.expansion_count >= self.task.exact_expansions:
                    self.termination_reason = "expansion_budget_exhausted"
                    break
                self.controller.start_expansion()
            if not self.controller.current_candidates():
                self.controller.finish_expansion()
                continue
            model_input = build_compact_best_first_live_model_input(self.authority, self.controller)
            self._pending = SearchPolicyRequest(
                session_id=self.session_id,
                adapter_id=self.adapter_id,
                seed=self.seed,
                instance_id=self.task.instance_id,
                decision_index=len(self.events),
                model_input=model_input,
            )
            return self._pending
        return self._pending

    def submit_output(self, output: str) -> None:
        if self._pending is None or self.complete:
            raise ValueError("issue #65 episode has no pending model request")
        request = self._pending
        result = self.controller.apply_raw_output(output)
        self.events.append(
            {
                "decision_index": request.decision_index,
                "input": dict(request.model_input),
                "raw_output": output,
                "trusted_runtime_result": dict(result.runtime_result),
            }
        )
        self._pending = None
        if not result.accepted:
            self.termination_reason = "deterministic_invalid_operation"
        elif not self.controller.current_candidates():
            self.controller.finish_expansion()

    def result(self) -> dict[str, Any]:
        if not self.complete:
            raise ValueError("issue #65 episode is not complete")
        goal_reached = self.termination_reason == "goal_reached"
        return {
            "algorithm_invariants_hold": self.controller.invalid_operation_count == 0,
            "decision_count": len(self.events),
            "expansion_count": self.controller.expansion_count,
            "goal_reached": goal_reached,
            "invariant_valid_success": goal_reached and self.controller.invalid_operation_count == 0,
            "invalid_operation_count": self.controller.invalid_operation_count,
            "invalid_operation_rate": self.controller.invalid_operation_count / len(self.events) if self.events else 0.0,
            "model_call_limit": self.task.model_call_limit,
            "termination_reason": self.termination_reason,
        }

    def episode(self) -> dict[str, Any]:
        if not self.complete or self._pending is not None:
            raise ValueError("issue #65 episode is not complete")
        return {
            "accepted_delta_limit": self.accepted_delta_limit,
            "adapter_id": self.adapter_id,
            "algorithm": "best_first_add_w3",
            "arm": self.arm,
            "events": self.events,
            "exact_reference_decisions": self.task.exact_decisions,
            "exact_reference_expansions": self.task.exact_expansions,
            "instance_id": self.task.instance_id,
            "pair_id": self.task.pair_id,
            "result": self.result(),
            "schema_version": "best_first_issue65_model_episode_v1",
            "seed": self.seed,
        }


def exact_best_first_output(model_input: Mapping[str, Any]) -> str:
    return _candidate_output(model_input, 0)


def random_valid_best_first_output(model_input: Mapping[str, Any], generator: random.Random) -> str:
    rows = model_input["successor_candidates"]["rows"]
    return _candidate_output(model_input, generator.randrange(len(rows)))


def _candidate_output(model_input: Mapping[str, Any], index: int) -> str:
    table = model_input["successor_candidates"]
    columns = table["columns"]
    row = table["rows"][index]
    action = row[columns.index("action")]
    return _canonical_text(
        {
            "action": {"args": list(action[1:]), "name": action[0]},
            "source_state_id": model_input["current"]["state_id"],
        }
    )


def run_reference_episode(task: BestFirstDevelopmentTask, *, arm: str, seed: int) -> dict[str, Any]:
    payload = _json_object(task.task_path)
    authority = PDDLStateAuthority.from_pddl(payload["domain_pddl"], payload["problem_pddl"])
    session = BestFirstModelSession(authority=authority, task=task, arm=arm, seed=seed)
    generator = random.Random(seed * 1_000_003 + sum(ord(char) for char in task.instance_id))
    while (request := session.next_request()) is not None:
        output = (
            exact_best_first_output(request.model_input)
            if arm == "exact_reference"
            else random_valid_best_first_output(request.model_input, generator)
        )
        session.submit_output(output)
    episode = session.episode()
    if episode["result"]["invariant_valid_success"] is not True:
        raise ValueError(f"{arm} did not solve the declared best-first reference: {task.instance_id}")
    return episode


def replay_best_first_model_episode(
    episode: Mapping[str, Any],
    *,
    task: BestFirstDevelopmentTask,
) -> dict[str, Any]:
    """Reconstruct every model input and trusted runtime transition semantically."""

    if (
        episode.get("schema_version") != "best_first_issue65_model_episode_v1"
        or episode.get("pair_id") != task.pair_id
        or episode.get("instance_id") != task.instance_id
        or episode.get("algorithm") != "best_first_add_w3"
        or not isinstance(episode.get("events"), list)
    ):
        raise ValueError("issue #65 episode identity is invalid")
    task_payload = _json_object(task.task_path)
    authority = PDDLStateAuthority.from_pddl(task_payload["domain_pddl"], task_payload["problem_pddl"])
    session = BestFirstModelSession(
        authority=authority,
        task=task,
        arm=str(episode["arm"]),
        seed=int(episode["seed"]),
        adapter_id=str(episode["adapter_id"]) if episode.get("adapter_id") is not None else None,
        accepted_delta_limit=int(episode["accepted_delta_limit"]),
    )
    for index, event in enumerate(episode["events"]):
        if not isinstance(event, Mapping) or event.get("decision_index") != index:
            raise ValueError("issue #65 episode decision sequence is invalid")
        request = session.next_request()
        if request is None or request.model_input != event.get("input"):
            raise ValueError("issue #65 replay reconstructed a different scientific model input")
        session.submit_output(str(event["raw_output"]))
        if session.events[-1]["trusted_runtime_result"] != event.get("trusted_runtime_result"):
            raise ValueError("issue #65 replay reconstructed a different trusted runtime result")
    if session.next_request() is not None or session.result() != episode.get("result"):
        raise ValueError("issue #65 replay reconstructed a different episode result")
    return session.result()


@dataclass(frozen=True, slots=True)
class BestFirstQualification:
    calls_per_second_lower_95: float
    model_load_seconds: float
    runtime_seconds_per_call: float
    maximum_scheduled_calls: int
    maximum_shard_scheduled_calls: int
    projected_rollout_seconds: float
    task_ids: tuple[str, ...]
    outcome: StopOutcome

    def to_dict(self) -> dict[str, Any]:
        return {
            "calls_per_second_lower_95": self.calls_per_second_lower_95,
            "coverage": {
                "maximum_scheduled_calls": self.maximum_scheduled_calls,
                "maximum_shard_scheduled_calls": self.maximum_shard_scheduled_calls,
                "mode": "complete_issue64_v3_development_panel" if self.task_ids else None,
                "outcome": self.outcome.value,
                "projected_rollout_seconds": self.projected_rollout_seconds,
                "task_ids": list(self.task_ids),
            },
            "model_load_seconds": self.model_load_seconds,
            "outcomes_observed": False,
            "runtime_seconds_per_call": self.runtime_seconds_per_call,
            "schema_version": "best_first_issue65_hardware_qualification_v1",
        }


def select_issue65_coverage(
    tasks: Sequence[BestFirstDevelopmentTask],
    *,
    model_load_seconds: float,
    throughput_samples: Sequence[float],
    runtime_seconds_per_call: float,
    rollout_shard_count: int,
) -> BestFirstQualification:
    """Certify the complete issue-64 v3 development panel or stop."""

    task_list = tuple(tasks)
    if len(task_list) != 23 or rollout_shard_count <= 0:
        raise ValueError("issue #65 qualification requires 23 tasks and positive shard count")
    throughput = lower_95_bound(throughput_samples)
    conditions = 2
    calls = conditions * sum(task.model_call_limit for task in task_list)
    shards = cost_balanced_task_shards(task_list, shard_count=rollout_shard_count)
    maximum_shard_calls = conditions * max(sum(task.model_call_limit for task in shard) for shard in shards)
    projected = 1.2 * (
        model_load_seconds + maximum_shard_calls / throughput + maximum_shard_calls * runtime_seconds_per_call
    )
    passed = projected <= 15 * 60 * 60
    return BestFirstQualification(
        throughput,
        model_load_seconds,
        runtime_seconds_per_call,
        calls,
        maximum_shard_calls,
        projected,
        tuple(task.instance_id for task in task_list) if passed else (),
        StopOutcome.PASS if passed else StopOutcome.VALID_STOP,
    )


def cost_balanced_task_shards(
    tasks: Sequence[BestFirstDevelopmentTask], *, shard_count: int
) -> tuple[tuple[BestFirstDevelopmentTask, ...], ...]:
    if shard_count <= 0:
        raise ValueError("issue #65 shard count must be positive")
    shards: list[list[BestFirstDevelopmentTask]] = [[] for _ in range(shard_count)]
    loads = [0] * shard_count
    for task in sorted(tasks, key=lambda item: (-item.model_call_limit, item.instance_id)):
        index = min(range(shard_count), key=lambda value: (loads[value], value))
        shards[index].append(task)
        loads[index] += task.model_call_limit
    return tuple(tuple(sorted(shard, key=lambda item: item.instance_id)) for shard in shards)


def lower_95_bound(samples: Sequence[float]) -> float:
    values = tuple(float(value) for value in samples)
    if not values or any(value <= 0 for value in values):
        raise ValueError("issue #65 throughput samples must be positive")
    if len(values) == 1:
        return values[0]
    return max(
        math.nextafter(0.0, 1.0),
        statistics.mean(values) - 1.96 * statistics.stdev(values) / math.sqrt(len(values)),
    )


def adjudicate_issue65(
    *,
    expected_tasks: Sequence[BestFirstDevelopmentTask],
    seeds: Sequence[int],
    exact_rows: Sequence[Mapping[str, Any]],
    random_rows: Sequence[Mapping[str, Any]],
    base_rows: Sequence[Mapping[str, Any]],
    process_rows: Sequence[Mapping[str, Any]],
    bootstrap_resamples: int,
    bootstrap_seed: int,
) -> dict[str, Any]:
    """Report complete development performance without treating a negative result as invalid."""

    ids = {task.instance_id for task in expected_tasks}
    frozen_seeds = tuple(int(seed) for seed in seeds)
    _require_product(exact_rows, ids, (None,), "exact reference")
    _require_product(random_rows, ids, frozen_seeds, "random valid")
    _require_product(base_rows, ids, frozen_seeds, "pretrained base")
    _require_product(process_rows, ids, frozen_seeds, "process SFT")
    exact_success = _mean([_success(row) for row in exact_rows])
    if exact_success != 1.0:
        return {
            "exact_reference_invariant_valid_success": exact_success,
            "outcome": StopOutcome.INVALID.value,
            "scientific_completion": False,
        }
    base_success = _mean([_success(row) for row in base_rows])
    random_success = _mean([_success(row) for row in random_rows])
    process_success = _mean([_success(row) for row in process_rows])
    controls = {"pretrained_base": base_success, "random_valid": random_success}
    best_control = max(controls, key=controls.__getitem__)
    control_rows = base_rows if best_control == "pretrained_base" else random_rows
    gain = process_success - controls[best_control]
    return {
        "absolute_gain_over_best_control": gain,
        "base_invariant_valid_success": base_success,
        "best_control": best_control,
        "exact_reference_invariant_valid_success": exact_success,
        "outcome": StopOutcome.PASS.value,
        "paired_bootstrap_gain_lower_bound": _paired_bootstrap_lower_bound(
            _task_success(process_rows, ids),
            _task_success(control_rows, ids),
            resamples=bootstrap_resamples,
            seed=bootstrap_seed,
        ),
        "process_sft_budget_usage": _budget_usage(process_rows),
        "process_sft_invariant_valid_success": process_success,
        "process_sft_invalid_operation_rate": _invalid_rate(process_rows),
        "random_valid_invariant_valid_success": random_success,
        "scientific_completion": True,
    }


def _training_paths(
    release_root: Path,
    manifest: Mapping[str, Any],
    *,
    algorithm: str,
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    by_split: dict[str, list[Path]] = {"train": [], "dev": []}
    for item in manifest.get("artifacts", []):
        if not isinstance(item, Mapping) or set(item) != {"path"}:
            raise ValueError("issue #64 training artifact entry is malformed")
        relative = Path(str(item["path"]))
        if relative.name != f"{algorithm}.jsonl.gz":
            continue
        split = relative.parts[2]
        if split in by_split:
            path = release_root / relative
            if not path.is_file():
                raise ValueError(f"issue #64 training shard is missing: {relative}")
            by_split[split].append(path)
    return tuple(sorted(by_split["train"])), tuple(sorted(by_split["dev"]))


def _require_product(
    rows: Sequence[Mapping[str, Any]],
    expected_ids: set[str],
    expected_seeds: Sequence[int | None],
    label: str,
) -> None:
    product = {(str(row["instance_id"]), row.get("seed")) for row in rows}
    expected = {(instance_id, seed) for instance_id in expected_ids for seed in expected_seeds}
    if product != expected or len(rows) != len(expected):
        raise ValueError(f"issue #65 {label} coverage is incomplete")


def _success(row: Mapping[str, Any]) -> float:
    return float(bool(row["result"]["invariant_valid_success"]))


def _invalid_rate(rows: Sequence[Mapping[str, Any]]) -> float:
    decisions = sum(int(row["result"]["decision_count"]) for row in rows)
    invalid = sum(int(row["result"]["invalid_operation_count"]) for row in rows)
    return invalid / decisions if decisions else 0.0


def _budget_usage(rows: Sequence[Mapping[str, Any]]) -> float:
    used = sum(int(row["result"]["decision_count"]) for row in rows)
    available = sum(int(row["result"]["model_call_limit"]) for row in rows)
    return used / available if available else 0.0


def _task_success(rows: Sequence[Mapping[str, Any]], ids: set[str]) -> dict[str, float]:
    return {
        instance_id: _mean([_success(row) for row in rows if row["instance_id"] == instance_id]) for instance_id in ids
    }


def _paired_bootstrap_lower_bound(
    learned: Mapping[str, float],
    control: Mapping[str, float],
    *,
    resamples: int,
    seed: int,
) -> float:
    ids = sorted(learned)
    generator = random.Random(seed)
    samples = sorted(
        _mean([learned[item] - control[item] for item in (generator.choice(ids) for _ in ids)]) for _ in range(resamples)
    )
    return samples[int(0.025 * (len(samples) - 1))]


def _mean(values: Sequence[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _gzip_jsonl(path: Path) -> list[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _canonical_text(value: object) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


__all__ = [
    "BestFirstDevelopmentTask",
    "BestFirstIssue65Experiment",
    "BestFirstModelSession",
    "BestFirstQualification",
    "adjudicate_issue65",
    "build_best_first_sft_command",
    "cost_balanced_task_shards",
    "exact_best_first_output",
    "expected_training_steps",
    "load_best_first_issue65",
    "lower_95_bound",
    "random_valid_best_first_output",
    "replay_best_first_model_episode",
    "run_reference_episode",
    "select_issue65_coverage",
]
