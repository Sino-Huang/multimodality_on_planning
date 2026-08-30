"""Governed BFWS process-SFT and development structural-gate workflow."""

from __future__ import annotations

import gzip
import json
import math
import os
import random
import statistics
from collections import defaultdict, deque
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from src.data_collect.governance import StopOutcome

from .bfws_episode import (
    BFWS_NOVELTY_PRECISION,
    PriorityKey,
    build_bfws_evaluator,
    build_bfws_observation,
)
from .bfws_model_input import (
    bfws_text_policy_training_messages,
    build_bounded_bfws_model_input,
    resolve_bfws_model_operation,
)
from .bfws_phase import BFWSPhaseGate, load_bfws_phase_gate
from .iw_episode import NoveltyItem, first_novel_item, iw_novelty_items
from .pddl_state import PDDLStateAuthority
from .search_context import AcceptedSearchDelta
from .search_memory import (
    AcceptedRetirement,
    AcceptedTransition,
    SearchMemory,
    SearchRetireRequest,
    SearchTransitionRequest,
    apply_search_retirement,
    apply_search_transition,
)
from .search_trace import _decode_operation, _serialize_operation

_FREEZE = Path("configs/experiments/bfws_phase_freeze_v1.json")
_AUTHORIZATION = Path("configs/experiments/bfws_phase_authorization_v1.json")
_TRAINING_MANIFEST = Path("data/bfws_phase_v1/corpus-release/training/manifest.json")
_TRACE_MANIFEST = Path("data/bfws_phase_v1/exact-traces/manifests/bfws-expert-traces.json")
_TRACE_AUDIT = Path("data/bfws_phase_v1/exact-traces/manifests/bfws-trace-audit.json")
_CORPUS_RECEIPT = Path(
    "data/bfws_phase_v1/execution-receipts/"
    "generation-run-issue-56-bfws-development-v1-issue-58-bfws-text-corpus-v1-resume-004.json"
)
_BUDGET_OVERRIDE = Path("configs/experiments/bfws_issue59_budget_override_v1.json")


def bfws_text_policy_messages(model_input: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build Qwen processor messages without changing the frozen #58 builder."""

    return [
        {
            "role": message["role"],
            "content": [{"type": "text", "text": message["content"]}],
        }
        for message in bfws_text_policy_training_messages(model_input)
    ]


@dataclass(frozen=True, slots=True)
class BFWSDevelopmentTask:
    domain_id: str
    difficulty: str
    instance_id: str
    domain_path: Path
    problem_path: Path
    exact_decisions: int
    exact_expansions: int

    @property
    def model_call_limit(self) -> int:
        return 2 * self.exact_decisions


@dataclass(frozen=True, slots=True)
class BFWSIssue59Experiment:
    repo_root: Path
    phase_gate: BFWSPhaseGate
    training_manifest: Mapping[str, Any]
    trace_manifest: Mapping[str, Any]
    tasks: tuple[BFWSDevelopmentTask, ...]
    train_datasets: tuple[Path, ...]
    dev_datasets: tuple[Path, ...]
    budget_override: Mapping[str, Any]

    @property
    def contract_id(self) -> str:
        return str(self.budget_override["contract_id"])

    @property
    def training_seeds(self) -> tuple[int, ...]:
        return (int(self.budget_override["training"]["seed"]),)

    @property
    def evaluation_seeds(self) -> tuple[int, ...]:
        return tuple(int(seed) for seed in self.budget_override["evaluation"]["process_sft_seeds"])

    def preflight(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "development_exact_decisions": sum(task.exact_decisions for task in self.tasks),
            "development_tasks": len(self.tasks),
            "fresh_test_accessed": False,
            "maximum_model_calls": sum(task.model_call_limit for task in self.tasks),
            "phase_id": self.phase_gate.phase_id,
            "training_examples": dict(self.training_manifest["counts"]),
            "training_task_files": {"dev": len(self.dev_datasets), "train": len(self.train_datasets)},
            "training_runs": int(self.budget_override["training"]["replicate_count"]),
            "training_seeds": list(self.training_seeds),
        }


def load_bfws_issue59(repo_root: str | Path) -> BFWSIssue59Experiment:
    """Load only the authorized development products released by issues #56-#58."""

    root = Path(repo_root).resolve()
    gate = load_bfws_phase_gate(root / _FREEZE, root / _AUTHORIZATION, repo_root=root)
    for stage in ("process_sft_training", "development_references", "development_structural_gate"):
        gate.require_run(stage=stage, contract_id=gate.phase_id)

    training = _json_object(root / _TRAINING_MANIFEST)
    if (
        training.get("schema_version") != "bfws_process_training_projection_v1"
        or training.get("framework") != {"name": "ms-swift", "version": "4.2.2"}
        or training.get("phase_receipt") != gate.receipt(stage="process_sft_training")
        or training.get("source_view") != "process"
        or training.get("counts") != {"dev": 21_239, "train": 47_780}
    ):
        raise ValueError("issue #59 training projection differs from the issue #58 release")
    train_datasets, dev_datasets = _training_paths(root, training)

    trace_manifest = _json_object(root / _TRACE_MANIFEST)
    trace_rows = trace_manifest.get("traces")
    if (
        trace_manifest.get("schema_version") != "bfws_expert_trace_generation_v1"
        or trace_manifest.get("phase_receipt") != gate.receipt(stage="trace_generation")
        or not isinstance(trace_rows, list)
        or len(trace_rows) != 105
    ):
        raise ValueError("issue #59 exact references differ from the issue #57 release")
    audit = _json_object(root / _TRACE_AUDIT)
    if (
        audit.get("schema_version") != "bfws_trace_release_audit_v1"
        or audit.get("decision_count") != 69_019
        or any(int(value) != 0 for value in audit.get("audit_results", {}).values())
    ):
        raise ValueError("issue #59 exact-reference audit is incomplete")
    corpus_receipt = _json_object(root / _CORPUS_RECEIPT)
    if (
        corpus_receipt.get("outcome") != StopOutcome.PASS.value
        or corpus_receipt.get("status") != "completed"
        or corpus_receipt.get("scientific_completion") is not True
        or corpus_receipt.get("execution_result", {}).get("byte_identical_regeneration") is not True
    ):
        raise ValueError("issue #58 corpus receipt does not authorize process SFT")
    budget_override = _json_object(root / _BUDGET_OVERRIDE)
    if budget_override != {
        "contract_id": "issue-59-bfws-single-training-v1",
        "evaluation": {
            "base_seeds": [17],
            "model_sessions_per_task": 2,
            "process_sft_seeds": [17],
            "random_valid_seeds": [17],
        },
        "parent_phase_id": gate.phase_id,
        "reason": "Supervisor limited issue 59 to one model training run for time and compute budget.",
        "schema_version": "bfws_issue59_budget_override_v1",
        "scientific_scope": (
            "Single-checkpoint development comparison with whole-instance bootstrap uncertainty; "
            "training-seed variance is not estimated."
        ),
        "source_issue": 59,
        "training": {"device": "cuda:1", "replicate_count": 1, "seed": 17, "world_size": 1},
    }:
        raise ValueError("issue #59 budget override differs from the supervisor decision")

    tasks = []
    for row in trace_rows:
        if not isinstance(row, dict) or row.get("split") != "dev":
            continue
        source = row.get("source")
        result = row.get("result")
        if (
            not isinstance(source, dict)
            or not isinstance(result, dict)
            or result.get("goal_reached") is not True
            or result.get("outcome") != StopOutcome.PASS.value
        ):
            raise ValueError("issue #59 dev reference is not a solved replay-verified trace")
        tasks.append(
            BFWSDevelopmentTask(
                domain_id=str(row["domain_id"]),
                difficulty=str(row["difficulty"]),
                instance_id=str(row["instance_id"]),
                domain_path=_repository_path(root, source["domain_path"]),
                problem_path=_repository_path(root, source["problem_path"]),
                exact_decisions=int(row["exact_reference_decision_count"]),
                exact_expansions=int(row["max_expansions"]),
            )
        )
    tasks.sort(key=lambda item: item.instance_id)
    if len(tasks) != 35 or sum(task.exact_decisions for task in tasks) != 21_239:
        raise ValueError("issue #59 dev references do not cover the frozen 35-task panel")
    return BFWSIssue59Experiment(
        repo_root=root,
        phase_gate=gate,
        training_manifest=training,
        trace_manifest=trace_manifest,
        tasks=tuple(tasks),
        train_datasets=train_datasets,
        dev_datasets=dev_datasets,
        budget_override=budget_override,
    )


def build_bfws_sft_command(
    experiment: BFWSIssue59Experiment,
    *,
    seed: int,
    output_root: str | Path,
    world_size: int,
    smoke: bool = False,
) -> tuple[str, ...]:
    """Translate the immutable issue #56 optimizer into one ms-swift command."""

    training = experiment.phase_gate.components["training"]
    if seed not in training["seeds"]:
        raise ValueError(f"BFWS SFT seed is not frozen: {seed}")
    if isinstance(world_size, bool) or not isinstance(world_size, int) or world_size <= 0:
        raise ValueError("world_size must be a positive integer")
    optimization = training["optimization"]
    global_batch = int(optimization["global_batch_size"])
    if global_batch % world_size:
        raise ValueError("frozen global batch size must be divisible by world_size")
    lora = training["lora"]
    model = training["model"]
    command = [
        "swift",
        "sft",
        "--tuner_backend",
        "peft",
        "--tuner_type",
        "lora",
        "--model",
        str(model["model_id"]),
        "--model_revision",
        str(model["revision"]),
        "--use_hf",
        "true",
        "--dataset",
        *(str(path) for path in experiment.train_datasets),
        "--val_dataset",
        *(str(path) for path in experiment.dev_datasets),
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
        str(optimization["epochs"]),
        "--per_device_train_batch_size",
        "1",
        "--per_device_eval_batch_size",
        "1",
        "--gradient_accumulation_steps",
        str(global_batch // world_size),
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
        str(optimization["bf16"]).lower(),
        "--gradient_checkpointing",
        str(optimization["gradient_checkpointing"]).lower(),
        "--max_length",
        str(training["training_max_length"]),
        "--seed",
        str(seed),
        "--data_seed",
        str(seed),
        "--full_determinism",
        str(optimization["deterministic_algorithms"]).lower(),
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
        "epoch",
    ]
    if smoke:
        command.extend(("--max_steps", "1", "--eval_strategy", "no", "--save_strategy", "steps", "--save_steps", "1"))
    return tuple(command)


@dataclass(frozen=True, slots=True)
class BFWSModelRequest:
    session_id: str
    adapter_id: str | None
    seed: int
    instance_id: str
    decision_index: int
    model_input: Mapping[str, Any]
    observation: Mapping[str, Any]

    @property
    def canonical_input(self) -> bytes:
        return (_canonical_text(dict(self.model_input)) + "\n").encode("utf-8")


@dataclass(frozen=True, slots=True)
class _Snapshot:
    frontier: tuple[str, ...]
    visited: frozenset[str]
    known_states: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _Checkpoint:
    authority_id: str
    snapshot: _Snapshot


class BFWSModelSession:
    """Incremental model-owned BFWS episode using the released bounded input."""

    def __init__(
        self,
        *,
        authority: PDDLStateAuthority,
        instance_id: str,
        arm: str,
        seed: int,
        max_model_calls: int,
        accepted_delta_limit: int,
        max_input_bytes: int,
        max_input_tokens: int,
        input_token_counter: Callable[[Mapping[str, Any]], int],
        max_expansions: int | None = None,
        adapter_id: str | None = None,
    ) -> None:
        if not instance_id or arm not in {"pretrained_base", "process_sft", "random_valid", "exact_bfws"}:
            raise ValueError("BFWS model session has an invalid identity")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in (max_model_calls, accepted_delta_limit, max_input_bytes, max_input_tokens)
        ):
            raise ValueError("BFWS model session limits must be positive integers")
        self.authority = authority
        self.instance_id = instance_id
        self.arm = arm
        self.seed = seed
        self.max_model_calls = max_model_calls
        self.max_expansions = max_expansions or max_model_calls
        self.accepted_delta_limit = accepted_delta_limit
        self.max_input_bytes = max_input_bytes
        self.max_input_tokens = max_input_tokens
        self.input_token_counter = input_token_counter
        self.adapter_id = adapter_id
        self.memory = SearchMemory.initial(authority)
        initial = authority.initial_state
        initial_goals = _unachieved_goal_count(authority, initial)
        initial_items = iw_novelty_items(initial, BFWS_NOVELTY_PRECISION)
        initial_novel = first_novel_item(initial_items, set())
        initial_bucket = len(initial_novel) if initial_novel is not None else BFWS_NOVELTY_PRECISION + 1
        self.partition_tables: dict[int, set[NoveltyItem]] = {initial_goals: set(initial_items)}
        self.priority_by_state: dict[str, PriorityKey] = {initial.state_id: (initial_bucket, initial_goals, 0, 0)}
        self.accepted_deltas: deque[AcceptedSearchDelta] = deque(maxlen=accepted_delta_limit)
        self.events: list[dict[str, Any]] = []
        self.expansion_count = 0
        self.invalid_operation_count = 0
        self._expanded_state_id: str | None = None
        self._pending: BFWSModelRequest | None = None
        self.termination_reason: str | None = "goal_reached" if authority.is_goal(initial) else None
        self.session_id = f"{arm}:{adapter_id or 'reference'}:{seed}:{instance_id}"

    @property
    def complete(self) -> bool:
        return self.termination_reason is not None

    def next_request(self) -> BFWSModelRequest | None:
        if self._pending is not None:
            return self._pending
        while not self.complete:
            if len(self.events) >= self.max_model_calls:
                self.termination_reason = "decision_budget_exhausted"
                break
            if self.expansion_count >= self.max_expansions:
                self.termination_reason = "expansion_budget_exhausted"
                break
            if self._expanded_state_id is None:
                if not self.memory.frontier:
                    self.termination_reason = "frontier_exhausted"
                    break
                self._expanded_state_id = self.memory.frontier[0]
                if self.authority.is_goal(self.memory.state(self._expanded_state_id)):
                    self.termination_reason = "goal_reached"
                    break
            state = self.memory.state(self._expanded_state_id)
            observation = build_bfws_observation(
                authority=self.authority,
                state=state,
                memory=self.memory,
                partition_tables={key: frozenset(value) for key, value in self.partition_tables.items()},
                priority_by_state=self.priority_by_state,
            )
            nonduplicates = [item for item in observation["successor_candidates"] if not item["duplicate"]]
            source_is_head = bool(self.memory.frontier and self.memory.frontier[0] == self._expanded_state_id)
            if not nonduplicates and not source_is_head:
                self.expansion_count += 1
                self._expanded_state_id = None
                continue
            checkpoint = _Checkpoint(
                self.memory.authority.authority_id,
                _Snapshot(
                    frontier=self.memory.frontier,
                    visited=self.memory.visited,
                    known_states={state_id: self.memory.state(state_id) for state_id in self.memory.visited},
                ),
            )
            model_input, _dropped = build_bounded_bfws_model_input(
                observation=observation,
                checkpoint=checkpoint,
                accepted_deltas=tuple(self.accepted_deltas),
                max_bytes=self.max_input_bytes,
                max_input_tokens=self.max_input_tokens,
                token_counter=self.input_token_counter,
            )
            self._pending = BFWSModelRequest(
                session_id=self.session_id,
                adapter_id=self.adapter_id,
                seed=self.seed,
                instance_id=self.instance_id,
                decision_index=len(self.events),
                model_input=model_input,
                observation=observation,
            )
            return self._pending
        return None

    def submit_output(self, raw_output: str) -> None:
        request = self._pending
        if request is None:
            raise ValueError("BFWS submit_output requires an outstanding request")
        if not isinstance(raw_output, str):
            raise TypeError("BFWS model output must be text")
        self._pending = None
        parsed, parse_error = _parse_model_output(raw_output)
        resolved = None
        result = None
        error = parse_error
        if parsed is not None:
            try:
                resolved = resolve_bfws_model_operation(parsed, request.observation)
                result = self._apply_validated_operation(resolved, request.observation)
            except (KeyError, TypeError, ValueError) as caught:
                error = str(caught)
        event: dict[str, Any] = {
            "decision_index": request.decision_index,
            "input": dict(request.model_input),
            "raw_output": raw_output,
            "status": "rejected" if error is not None else "accepted",
        }
        if error is not None or not isinstance(result, (AcceptedTransition, AcceptedRetirement)):
            self.invalid_operation_count += 1
            event["error"] = error or "trusted BFWS runtime rejected the operation"
            self.events.append(event)
            self.termination_reason = "deterministic_invalid_operation"
            return

        assert resolved is not None
        event["operation"] = _serialize_operation(resolved)
        self.events.append(event)
        if isinstance(result, AcceptedTransition):
            assert isinstance(resolved, SearchTransitionRequest)
            self.accepted_deltas.append(
                AcceptedSearchDelta(
                    record_index=request.decision_index,
                    operation=resolved,
                    transition=result.transition,
                    evaluation=result.evaluation,
                )
            )
            target = result.transition.target_state
            evaluation = _candidate_evaluation(request.observation, resolved)
            partition = int(evaluation["partition"])
            self.partition_tables.setdefault(partition, set()).update(iw_novelty_items(target, BFWS_NOVELTY_PRECISION))
            self.priority_by_state[target.state_id] = tuple(evaluation["priority"])
            self.memory = result.memory
            if self.authority.is_goal(target):
                self.expansion_count += 1
                self.termination_reason = "goal_reached"
        else:
            self.memory = result.memory
            self.expansion_count += 1
            self._expanded_state_id = None

    def _apply_validated_operation(
        self,
        operation: SearchTransitionRequest | SearchRetireRequest,
        observation: Mapping[str, Any],
    ) -> AcceptedTransition | AcceptedRetirement:
        assert self._expanded_state_id is not None
        candidates = observation["successor_candidates"]
        if isinstance(operation, SearchRetireRequest):
            if any(not item["duplicate"] for item in candidates):
                raise ValueError("BFWS retirement omitted an unvisited successor")
            if operation.state_id != self._expanded_state_id:
                raise ValueError("BFWS retirement must target the current expansion")
            result = apply_search_retirement(self.memory, operation)
            if not isinstance(result, AcceptedRetirement):
                raise ValueError("trusted BFWS runtime rejected retirement")
            return result

        evaluation = _candidate_evaluation(observation, operation)
        expected_intent = evaluation["frontier_intent"]
        if (
            operation.source_state_id != self._expanded_state_id
            or operation.frontier_intent.retire_source is not expected_intent["retire_source"]
            or operation.frontier_intent.target_position != expected_intent["target_position"]
            or operation.visit_target is not True
            or operation.evaluate_target is not True
        ):
            raise ValueError("BFWS transition differs from its observable candidate evaluation")
        result = apply_search_transition(
            self.memory,
            operation,
            evaluator=build_bfws_evaluator(int(evaluation["novelty_bucket"]), int(evaluation["partition"])),
        )
        if not isinstance(result, AcceptedTransition):
            raise ValueError("trusted BFWS runtime rejected transition")
        return result

    def result(self) -> dict[str, Any]:
        if not self.complete:
            raise ValueError("BFWS episode is not complete")
        goal_reached = self.termination_reason == "goal_reached"
        return {
            "algorithm_invariants_hold": True,
            "decision_count": len(self.events),
            "expansion_count": self.expansion_count,
            "goal_reached": goal_reached,
            "invariant_valid_success": goal_reached,
            "invalid_operation_count": self.invalid_operation_count,
            "invalid_operation_rate": self.invalid_operation_count / len(self.events) if self.events else 0.0,
            "termination_reason": self.termination_reason,
        }


class BFWSBatchedPolicy:
    """Float32 greedy Qwen inference with one backbone and isolated LoRA adapters."""

    def __init__(
        self,
        *,
        model_id: str,
        revision: str,
        adapter_paths: Mapping[str, str | Path],
        device: str,
        max_new_tokens: int = 384,
        max_context_tokens: int = 8_192,
        max_batch_size: int = 8,
        max_batch_input_tokens: int = 48_000,
    ) -> None:
        if max_context_tokens != 8_192 or max_new_tokens != 384:
            raise ValueError("BFWS inference token limits are frozen to 8192/384")
        if max_batch_size != 8 or max_batch_input_tokens != 48_000:
            raise ValueError("BFWS batching is frozen to 8 requests and 48,000 padded input tokens")
        import torch
        from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

        os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
        torch.use_deterministic_algorithms(True)
        torch.manual_seed(17)
        torch.cuda.manual_seed_all(17)
        self._torch = torch
        self.device = device
        self.max_new_tokens = max_new_tokens
        self.max_context_tokens = max_context_tokens
        self.max_batch_size = max_batch_size
        self.max_batch_input_tokens = max_batch_input_tokens
        self.processor = AutoProcessor.from_pretrained(model_id, revision=revision)
        self.processor.tokenizer.padding_side = "left"
        if self.processor.tokenizer.pad_token_id is None:
            self.processor.tokenizer.pad_token_id = self.processor.tokenizer.eos_token_id
        loaded_model: Any = Qwen3VLForConditionalGeneration.from_pretrained(
            model_id,
            revision=revision,
            dtype=torch.float32,
            low_cpu_mem_usage=True,
        )
        self.model: Any = loaded_model.to(device)
        self.model.eval()
        self.adapter_paths = {name: str(Path(path).resolve()) for name, path in adapter_paths.items()}
        if any(not name or not Path(path).is_dir() for name, path in self.adapter_paths.items()):
            raise ValueError("BFWS adapter paths must be named existing directories")
        self._loaded_adapters: set[str] = set()
        self._peft_wrapped = False
        self._output_cache: dict[tuple[str | None, bytes], str] = {}
        self._token_cache: dict[bytes, int] = {}
        self.identity = {
            "adapter_isolated_cache": True,
            "decoding": "greedy",
            "dtype": "float32",
            "max_batch_input_tokens": max_batch_input_tokens,
            "max_batch_size": max_batch_size,
            "max_context_tokens": max_context_tokens,
            "max_new_tokens": max_new_tokens,
            "model_id": model_id,
            "revision": revision,
        }

    def input_token_count(self, model_input: Mapping[str, Any]) -> int:
        key = (_canonical_text(dict(model_input)) + "\n").encode("utf-8")
        cached = self._token_cache.get(key)
        if cached is not None:
            return cached
        length = len(
            self.processor.tokenizer.apply_chat_template(
                bfws_text_policy_training_messages(model_input),
                tokenize=True,
                add_generation_prompt=True,
            )
        )
        self._token_cache[key] = length
        return length

    def input_token_length(self, request: BFWSModelRequest) -> int:
        return self.input_token_count(request.model_input)

    def generate_many(self, requests: Sequence[BFWSModelRequest]) -> list[str]:
        request_list = list(requests)
        outputs: list[str | None] = [None] * len(request_list)
        by_adapter: dict[str | None, list[tuple[int, BFWSModelRequest]]] = defaultdict(list)
        for index, request in enumerate(request_list):
            by_adapter[request.adapter_id].append((index, request))
        for adapter_id in sorted(by_adapter, key=lambda value: value or ""):
            indexed = by_adapter[adapter_id]
            missing: dict[tuple[str | None, bytes], BFWSModelRequest] = {}
            for index, request in indexed:
                key = (adapter_id, request.canonical_input)
                if key in self._output_cache:
                    outputs[index] = self._output_cache[key]
                else:
                    missing.setdefault(key, request)
            if missing:
                generated = self._generate_uncached(adapter_id, tuple(missing.values()))
                for key, output in zip(missing, generated, strict=True):
                    self._output_cache[key] = output
            for index, request in indexed:
                if outputs[index] is None:
                    outputs[index] = self._output_cache[(adapter_id, request.canonical_input)]
        if any(output is None for output in outputs):
            raise RuntimeError("BFWS batched policy did not produce every requested output")
        return [str(output) for output in outputs]

    def verify_scalar_batch_parity(self, requests: Sequence[BFWSModelRequest]) -> bool:
        probes = tuple(requests)
        if not probes or len({request.adapter_id for request in probes}) != 1:
            raise ValueError("BFWS parity probes must use one adapter")
        adapter_id = probes[0].adapter_id
        scalar = [self._generate_uncached(adapter_id, (request,))[0] for request in probes]
        return scalar == self._generate_uncached(adapter_id, probes)

    def verify_repeated_batch(self, requests: Sequence[BFWSModelRequest]) -> bool:
        probes = tuple(requests)
        if not probes or len({request.adapter_id for request in probes}) != 1:
            raise ValueError("BFWS repeated-batch probes must use one adapter")
        adapter_id = probes[0].adapter_id
        return self._generate_uncached(adapter_id, probes) == self._generate_uncached(adapter_id, probes)

    def _generate_uncached(
        self,
        adapter_id: str | None,
        requests: Sequence[BFWSModelRequest],
    ) -> list[str]:
        if not requests:
            return []
        lengths = [self.input_token_length(request) for request in requests]
        if len(requests) > self.max_batch_size or max(lengths) * len(lengths) > self.max_batch_input_tokens:
            raise ValueError("BFWS inference batch exceeds its frozen capacity")
        if any(length + self.max_new_tokens > self.max_context_tokens for length in lengths):
            raise ValueError("BFWS inference request exceeds the frozen model context")
        conversations = [bfws_text_policy_messages(request.model_input) for request in requests]
        inputs = self.processor.apply_chat_template(
            conversations,
            tokenize=True,
            add_generation_prompt=True,
            padding=True,
            return_dict=True,
            return_tensors="pt",
        ).to(self.device)
        input_width = inputs["input_ids"].shape[1]
        with self._adapter_context(adapter_id), self._torch.inference_mode():
            output_ids = self.model.generate(
                **inputs,
                do_sample=False,
                max_new_tokens=self.max_new_tokens,
            )
        return [
            output.strip()
            for output in self.processor.batch_decode(
                output_ids[:, input_width:],
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )
        ]

    @contextmanager
    def _adapter_context(self, adapter_id: str | None):
        if adapter_id is None:
            with self.model.disable_adapter() if self._peft_wrapped else nullcontext():
                yield
            return
        try:
            path = self.adapter_paths[adapter_id]
        except KeyError as error:
            raise ValueError(f"unknown BFWS adapter: {adapter_id}") from error
        if not self._peft_wrapped:
            from peft import PeftModel

            self.model = PeftModel.from_pretrained(self.model, path, adapter_name=adapter_id).to(self.device)
            self.model.eval()
            self._peft_wrapped = True
            self._loaded_adapters.add(adapter_id)
        elif adapter_id not in self._loaded_adapters:
            self.model.load_adapter(path, adapter_name=adapter_id)
            self._loaded_adapters.add(adapter_id)
        self.model.set_adapter(adapter_id)
        yield


@dataclass(frozen=True, slots=True)
class BFWSQualification:
    calls_per_second_lower_95: float
    model_load_seconds: float
    runtime_seconds_per_call: float
    task_ids: tuple[str, ...]
    coverage_mode: str | None
    maximum_scheduled_calls: int
    projected_rollout_seconds: float
    outcome: StopOutcome

    def to_dict(self) -> dict[str, Any]:
        return {
            "calls_per_second_lower_95": self.calls_per_second_lower_95,
            "coverage": {
                "maximum_scheduled_calls": self.maximum_scheduled_calls,
                "mode": self.coverage_mode,
                "outcome": self.outcome.value,
                "projected_rollout_seconds": self.projected_rollout_seconds,
                "task_ids": list(self.task_ids),
            },
            "model_load_seconds": self.model_load_seconds,
            "outcomes_observed": False,
            "runtime_seconds_per_call": self.runtime_seconds_per_call,
            "schema_version": "bfws_issue59_hardware_qualification_v1",
        }


def select_bfws_coverage(
    tasks: Sequence[BFWSDevelopmentTask],
    *,
    model_load_seconds: float,
    throughput_samples: Sequence[float],
    runtime_seconds_per_call: float,
    model_sessions_per_task: int,
) -> BFWSQualification:
    """Select full coverage first, then the preregistered cheapest-per-domain panel."""

    task_list = tuple(tasks)
    if len(task_list) != 35:
        raise ValueError("BFWS qualification requires the complete 35-task development panel")
    if model_sessions_per_task <= 0:
        raise ValueError("BFWS qualification requires a positive model-session count")
    throughput = _lower_95_bound(throughput_samples)
    by_domain: dict[str, list[BFWSDevelopmentTask]] = defaultdict(list)
    for task in task_list:
        by_domain[task.domain_id].append(task)
    panel = tuple(
        min(by_domain[domain], key=lambda task: (task.exact_decisions, task.difficulty, task.instance_id))
        for domain in sorted(by_domain)
    )
    if len(panel) != 15:
        raise ValueError("BFWS exact-cost panel must contain one task per domain")
    for mode, candidates in (("full_development", task_list), ("preregistered_exact_cost_panel", panel)):
        calls = model_sessions_per_task * sum(task.model_call_limit for task in candidates)
        projected = 1.2 * (model_load_seconds + calls / throughput + calls * runtime_seconds_per_call)
        if projected <= 15 * 60 * 60:
            return BFWSQualification(
                throughput,
                model_load_seconds,
                runtime_seconds_per_call,
                tuple(task.instance_id for task in candidates),
                mode,
                calls,
                projected,
                StopOutcome.PASS,
            )
    calls = model_sessions_per_task * sum(task.model_call_limit for task in panel)
    projected = 1.2 * (model_load_seconds + calls / throughput + calls * runtime_seconds_per_call)
    return BFWSQualification(
        throughput,
        model_load_seconds,
        runtime_seconds_per_call,
        (),
        None,
        calls,
        projected,
        StopOutcome.VALID_STOP,
    )


def run_bfws_sessions(
    sessions: Sequence[BFWSModelSession],
    policy: BFWSBatchedPolicy,
    *,
    should_stop: Callable[[], bool],
    on_complete: Callable[[BFWSModelSession], None],
    on_progress: Callable[[int, int, int], None],
) -> tuple[BFWSModelSession, ...]:
    """Drive deterministic rounds with at most one request per active episode."""

    active = {session.session_id: session for session in sessions}
    if len(active) != len(sessions):
        raise ValueError("BFWS scheduler session IDs must be unique")
    completed: list[BFWSModelSession] = []
    launched_calls = 0
    while active and not should_stop():
        requests = []
        for session_id in sorted(active):
            session = active[session_id]
            request = session.next_request()
            if request is None:
                completed.append(session)
                on_complete(session)
            else:
                requests.append(request)
        for session in completed:
            active.pop(session.session_id, None)
        if not requests:
            continue
        for batch in _deterministic_batches(requests, policy):
            if should_stop():
                break
            outputs = policy.generate_many(batch)
            launched_calls += len(batch)
            for request, output in zip(batch, outputs, strict=True):
                session = active[request.session_id]
                session.submit_output(output)
                if session.complete:
                    completed.append(session)
                    on_complete(session)
                    active.pop(request.session_id)
        on_progress(len(completed), len(sessions), launched_calls)
    return tuple(completed)


def _deterministic_batches(
    requests: Sequence[BFWSModelRequest],
    policy: BFWSBatchedPolicy,
) -> tuple[tuple[BFWSModelRequest, ...], ...]:
    measured = sorted(
        ((request, policy.input_token_length(request)) for request in requests),
        key=lambda item: (
            item[0].adapter_id or "",
            item[0].seed,
            item[0].instance_id,
            item[0].decision_index,
            item[1],
        ),
    )
    batches: list[tuple[BFWSModelRequest, ...]] = []
    current: list[tuple[BFWSModelRequest, int]] = []
    for item in measured:
        candidate = [*current, item]
        same_adapter = not current or item[0].adapter_id == current[0][0].adapter_id
        padded = max(length for _request, length in candidate) * len(candidate)
        if current and (
            not same_adapter or len(candidate) > policy.max_batch_size or padded > policy.max_batch_input_tokens
        ):
            batches.append(tuple(request for request, _length in current))
            current = [item]
        else:
            current = candidate
    if current:
        batches.append(tuple(request for request, _length in current))
    return tuple(batches)


def _lower_95_bound(samples: Sequence[float]) -> float:
    values = tuple(float(value) for value in samples)
    if not values or any(value <= 0 for value in values):
        raise ValueError("BFWS throughput samples must be positive")
    if len(values) == 1:
        return values[0]
    lower_bound = statistics.mean(values) - 1.96 * statistics.stdev(values) / math.sqrt(len(values))
    return max(math.nextafter(0.0, 1.0), lower_bound)


def exact_bfws_model_output(observation: Mapping[str, Any]) -> str:
    """Return the canonical expert decision visible in one BFWS observation."""

    source = observation["expanded_state"]["state_id"]
    candidate = next((item for item in observation["successor_candidates"] if not item["duplicate"]), None)
    if candidate is None:
        operation: dict[str, Any] = {"operation_type": "retire_frontier", "state_id": "$"}
    else:
        operation = {
            "action": candidate["grounded_action"],
            "evaluate_target": True,
            "frontier_intent": candidate["evaluation"]["frontier_intent"],
            "source_state_id": "$",
            "visit_target": True,
        }
    assert source
    return _canonical_text(
        {
            "canonical_rationale": "exact_bfws_goal_count_priority_successor",
            "runtime_result": None,
            "typed_operation": operation,
        }
    )


def random_valid_bfws_model_output(observation: Mapping[str, Any], generator: random.Random) -> str:
    """Choose one runtime-valid observable successor without using outcomes."""

    frontier_size = int(observation["search_memory"]["frontier_size"])
    candidates = []
    for item in observation["successor_candidates"]:
        evaluation = item.get("evaluation")
        if item["duplicate"] or not isinstance(evaluation, Mapping):
            continue
        intent = evaluation["frontier_intent"]
        available = frontier_size - int(intent["retire_source"])
        if int(intent["target_position"]) <= available:
            candidates.append(item)
    if not candidates:
        operation: dict[str, Any] = {"operation_type": "retire_frontier", "state_id": "$"}
    else:
        candidate = generator.choice(candidates)
        operation = {
            "action": candidate["grounded_action"],
            "evaluate_target": True,
            "frontier_intent": candidate["evaluation"]["frontier_intent"],
            "source_state_id": "$",
            "visit_target": True,
        }
    return _canonical_text(
        {
            "canonical_rationale": "seeded_random_valid_bfws_operation",
            "runtime_result": None,
            "typed_operation": operation,
        }
    )


def materialize_random_valid_bfws_reference(
    *,
    task: BFWSDevelopmentTask,
    seed: int,
    evidence_path: str | Path,
    input_token_counter: Callable[[Mapping[str, Any]], int],
) -> tuple[dict[str, Any], str]:
    """Generate one random-valid episode, or replay an existing atomic episode."""

    path = Path(evidence_path).resolve()
    authority = PDDLStateAuthority.from_pddl(
        task.domain_path.read_text(encoding="utf-8"),
        task.problem_path.read_text(encoding="utf-8"),
    )
    if path.is_file():
        payload = _gzip_json_object(path)
        status = "reused"
    else:
        session = BFWSModelSession(
            authority=authority,
            instance_id=task.instance_id,
            arm="random_valid",
            seed=seed,
            max_model_calls=task.model_call_limit,
            max_expansions=task.exact_expansions,
            accepted_delta_limit=16,
            max_input_bytes=10_000_000,
            max_input_tokens=7_808,
            input_token_counter=input_token_counter,
        )
        generator = random.Random(seed * 1_000_003 + _stable_text_seed(task.instance_id))
        while (request := session.next_request()) is not None:
            session.submit_output(random_valid_bfws_model_output(request.observation, generator))
        payload = bfws_episode_payload(session)
        _write_gzip_json(path, payload)
        status = "generated"
    replay_bfws_episode(payload, authority=authority, input_token_counter=input_token_counter)
    if payload["result"]["invalid_operation_count"] != 0:
        raise ValueError(f"random-valid BFWS policy emitted an invalid operation: {task.instance_id}")
    return payload, status


def bfws_episode_payload(session: BFWSModelSession) -> dict[str, Any]:
    """Return compact, gzip-ready full decision evidence for one session."""

    return {
        "accepted_delta_limit": session.accepted_delta_limit,
        "adapter_id": session.adapter_id,
        "arm": session.arm,
        "events": session.events,
        "instance_id": session.instance_id,
        "max_expansions": session.max_expansions,
        "max_input_bytes": session.max_input_bytes,
        "max_input_tokens": session.max_input_tokens,
        "max_model_calls": session.max_model_calls,
        "result": session.result(),
        "schema_version": "bfws_model_episode_v1",
        "seed": session.seed,
    }


def replay_bfws_episode(
    payload: Mapping[str, Any],
    *,
    authority: PDDLStateAuthority,
    input_token_counter: Callable[[Mapping[str, Any]], int],
) -> dict[str, Any]:
    """Rebuild every bounded input and trusted transition without model inference."""

    if payload.get("schema_version") != "bfws_model_episode_v1" or not isinstance(payload.get("events"), list):
        raise ValueError("BFWS model episode evidence has the wrong schema")
    session = BFWSModelSession(
        authority=authority,
        instance_id=str(payload["instance_id"]),
        arm=str(payload["arm"]),
        seed=int(payload["seed"]),
        max_model_calls=int(payload["max_model_calls"]),
        max_expansions=int(payload["max_expansions"]),
        accepted_delta_limit=int(payload["accepted_delta_limit"]),
        max_input_bytes=int(payload["max_input_bytes"]),
        max_input_tokens=int(payload["max_input_tokens"]),
        input_token_counter=input_token_counter,
        adapter_id=str(payload["adapter_id"]) if payload.get("adapter_id") is not None else None,
    )
    for expected_index, event in enumerate(payload["events"]):
        if not isinstance(event, Mapping) or event.get("decision_index") != expected_index:
            raise ValueError("BFWS model episode event sequence is malformed")
        request = session.next_request()
        if request is None or request.model_input != event.get("input"):
            raise ValueError("BFWS replay model input differs from retained evidence")
        session.submit_output(str(event["raw_output"]))
        if session.events[-1] != event:
            raise ValueError("BFWS replay runtime result differs from retained evidence")
    if session.next_request() is not None or session.result() != payload.get("result"):
        raise ValueError("BFWS replay result differs from retained evidence")
    return session.result()


def adjudicate_bfws_structural_gate(
    *,
    expected_ids: set[str],
    seeds: Sequence[int],
    exact_rows: Sequence[Mapping[str, Any]],
    random_rows: Sequence[Mapping[str, Any]],
    base_rows: Sequence[Mapping[str, Any]],
    process_rows: Sequence[Mapping[str, Any]],
    thresholds: Mapping[str, Any],
    bootstrap_resamples: int,
    bootstrap_seed: int,
) -> dict[str, Any]:
    """Adjudicate complete whole-instance products against the frozen thresholds."""

    frozen_seeds = tuple(seeds)
    _require_product(exact_rows, expected_ids, (None,), "exact BFWS")
    _require_product(random_rows, expected_ids, frozen_seeds, "random-valid")
    _require_product(base_rows, expected_ids, frozen_seeds, "pretrained base")
    _require_product(process_rows, expected_ids, frozen_seeds, "process SFT")
    exact_success = _mean([_success(row) for row in exact_rows])
    if exact_success < float(thresholds["exact_reference_invariant_valid_success"]):
        return {
            "exact_reference_invariant_valid_success": exact_success,
            "outcome": StopOutcome.ANCESTOR_STOP.value,
            "scientific_completion": False,
        }
    base_success = _mean([_success(row) for row in base_rows])
    random_success = _mean([_success(row) for row in random_rows])
    process_success = _mean([_success(row) for row in process_rows])
    controls = {"pretrained_base": base_success, "random_valid": random_success}
    best_control = max(controls, key=lambda name: controls[name])
    gain = process_success - controls[best_control]
    control_rows = base_rows if best_control == "pretrained_base" else random_rows
    lower_bound = _paired_bootstrap_lower_bound(
        _task_success(process_rows, expected_ids),
        _task_success(control_rows, expected_ids),
        resamples=bootstrap_resamples,
        seed=bootstrap_seed,
    )
    invalid_rate = _invalid_rate(process_rows)
    checks = {
        "absolute_gain": gain >= float(thresholds["process_sft_absolute_gain_over_best_control"]),
        "bootstrap_lower_bound": lower_bound >= float(thresholds["process_sft_gain_bootstrap_lower_bound"]),
        "invariant_valid_success": process_success >= float(thresholds["process_sft_invariant_valid_success"]),
        "invalid_operation_rate": invalid_rate <= float(thresholds["maximum_invalid_operation_rate"]),
    }
    outcome = StopOutcome.PASS if all(checks.values()) else StopOutcome.VALID_STOP
    return {
        "absolute_gain_over_best_control": gain,
        "base_invariant_valid_success": base_success,
        "best_control": best_control,
        "checks": checks,
        "exact_reference_invariant_valid_success": exact_success,
        "outcome": outcome.value,
        "paired_bootstrap_gain_lower_bound": lower_bound,
        "process_sft_invariant_valid_success": process_success,
        "process_sft_invalid_operation_rate": invalid_rate,
        "random_valid_invariant_valid_success": random_success,
        "scientific_completion": outcome is StopOutcome.PASS,
    }


def _training_paths(root: Path, manifest: Mapping[str, Any]) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    release_root = (root / _TRAINING_MANIFEST).parent.parent
    by_split: dict[str, list[Path]] = {"train": [], "dev": []}
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("issue #58 training projection artifact list is malformed")
    for item in artifacts:
        if not isinstance(item, dict) or set(item) != {"path", "size_bytes"}:
            raise ValueError("issue #58 training projection artifact is malformed")
        relative = Path(str(item["path"]))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("issue #58 training projection path escapes its release")
        split = relative.parts[2] if len(relative.parts) > 3 else ""
        if split not in by_split:
            raise ValueError("issue #58 training projection contains a non-development split")
        path = release_root / relative
        if not path.is_file() or path.stat().st_size != item["size_bytes"]:
            raise ValueError(f"issue #58 training projection artifact differs: {relative}")
        by_split[split].append(path.resolve())
    if len(by_split["train"]) != 70 or len(by_split["dev"]) != 35:
        raise ValueError("issue #58 training projection does not contain 70 train and 35 dev task shards")
    return tuple(sorted(by_split["train"])), tuple(sorted(by_split["dev"]))


def _candidate_evaluation(
    observation: Mapping[str, Any],
    operation: SearchTransitionRequest,
) -> Mapping[str, Any]:
    for candidate in observation["successor_candidates"]:
        action = candidate["grounded_action"]
        if action["name"] == operation.action.name and tuple(action["args"]) == operation.action.args:
            if candidate["duplicate"] or not isinstance(candidate.get("evaluation"), Mapping):
                raise ValueError("BFWS model selected a duplicate successor")
            return candidate["evaluation"]
    raise ValueError("BFWS model selected an action outside the observable candidates")


def _parse_model_output(raw_output: str) -> tuple[SearchTransitionRequest | SearchRetireRequest | None, str | None]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate model output field: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> NoReturn:
        raise ValueError(f"invalid model output number: {value}")

    try:
        payload = json.loads(raw_output, object_pairs_hook=reject_duplicates, parse_constant=reject_constant)
        if not isinstance(payload, dict) or set(payload) != {
            "canonical_rationale",
            "runtime_result",
            "typed_operation",
        }:
            raise ValueError("BFWS model output has the wrong fields")
        if not isinstance(payload["canonical_rationale"], str) or payload["runtime_result"] is not None:
            raise ValueError("BFWS rationale must be text and runtime_result must be null")
        return _decode_operation(payload["typed_operation"]), None
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        return None, str(error)


def _unachieved_goal_count(authority: PDDLStateAuthority, state: Any) -> int:
    if authority.goal_atoms is None:
        return 1
    return len(set(authority.goal_atoms) - set(state.atoms))


def _require_product(
    rows: Sequence[Mapping[str, Any]],
    expected_ids: set[str],
    seeds: Sequence[int | None],
    label: str,
) -> None:
    actual = {(str(row.get("instance_id")), row.get("seed")) for row in rows}
    expected = {(instance_id, seed) for instance_id in expected_ids for seed in seeds}
    if actual != expected or len(rows) != len(expected):
        raise ValueError(f"{label} is not the complete frozen task-by-seed product")


def _success(row: Mapping[str, Any]) -> float:
    result = row.get("result")
    if not isinstance(result, Mapping):
        raise ValueError("BFWS result record is malformed")
    return float(result.get("invariant_valid_success") is True)


def _invalid_rate(rows: Sequence[Mapping[str, Any]]) -> float:
    invalid = 0
    decisions = 0
    for row in rows:
        result = row["result"]
        invalid += int(result.get("invalid_operation_count", 0))
        decisions += int(result.get("decision_count", 0))
    return invalid / decisions if decisions else 0.0


def _task_success(rows: Sequence[Mapping[str, Any]], expected_ids: set[str]) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[str(row["instance_id"])].append(_success(row))
    if set(grouped) != expected_ids:
        raise ValueError("BFWS metric rows do not cover the frozen whole-instance panel")
    return {instance_id: _mean(grouped[instance_id]) for instance_id in sorted(expected_ids)}


def _paired_bootstrap_lower_bound(
    treatment: Mapping[str, float],
    control: Mapping[str, float],
    *,
    resamples: int,
    seed: int,
) -> float:
    if treatment.keys() != control.keys() or resamples <= 0:
        raise ValueError("BFWS paired bootstrap inputs are malformed")
    differences = [treatment[key] - control[key] for key in sorted(treatment)]
    generator = random.Random(seed)
    draws = sorted(_mean([generator.choice(differences) for _ in differences]) for _ in range(resamples))
    return draws[int(0.025 * (resamples - 1))]


def _mean(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("cannot average an empty BFWS metric")
    return sum(values) / len(values)


def _repository_path(root: Path, value: object) -> Path:
    path = Path(str(value))
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("BFWS release path escapes the repository")
    resolved = (root / path).resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return resolved


def _stable_text_seed(value: str) -> int:
    return sum((index + 1) * ord(character) for index, character in enumerate(value))


def _gzip_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(gzip.decompress(path.read_bytes()))
    if not isinstance(value, dict):
        raise ValueError(f"expected gzip JSON object: {path}")
    return value


def _write_gzip_json(path: Path, value: object) -> None:
    payload = gzip.compress((_canonical_text(value) + "\n").encode("utf-8"), compresslevel=6, mtime=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _canonical_text(value: object) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


__all__ = [
    "BFWSBatchedPolicy",
    "BFWSDevelopmentTask",
    "BFWSIssue59Experiment",
    "BFWSModelRequest",
    "BFWSModelSession",
    "BFWSQualification",
    "adjudicate_bfws_structural_gate",
    "bfws_episode_payload",
    "bfws_text_policy_messages",
    "build_bfws_sft_command",
    "exact_bfws_model_output",
    "load_bfws_issue59",
    "materialize_random_valid_bfws_reference",
    "random_valid_bfws_model_output",
    "replay_bfws_episode",
    "run_bfws_sessions",
    "select_bfws_coverage",
]
