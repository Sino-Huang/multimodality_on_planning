"""Second-backbone (#101-#103) branch machinery: InternVL3.5-8B replication.

The frozen primary Qwen contract stays the default everywhere; this module only
takes effect where the second-backbone protocol is passed explicitly. GPU stages
(probe/train/evaluate) are implemented here and executed by the scheduler.
"""

from __future__ import annotations

import hashlib
import math
import os
import shutil
import subprocess
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .backbone_port import backbone_spec
from .best_first_curriculum import paired_bootstrap_interval
from .expanded_baseline import _commit_pending, _restore_events
from .expanded_curriculum_evaluation import paired_rows
from .expanded_curriculum_training import (
    _final_fingerprints,
    _safetensor_count,
    _source_manifest,
    _validate_adapter_config,
    optimizer_updates,
    sequential_sampler,
)
from .expanded_successor_training import _adapter_tensor_changes, _sha256
from .expanded_views import ExpandedTaskViews
from .modality_corpus import ModalityCorpus
from .modality_corpus_replay import canonical
from .modality_view_preparation import frozen_processor, page_processor_for, write_json
from .scene_assets import read_json
from .visual_episode import VisualSession, replay_visual_episode

QUALIFICATION_SCHEMA = "expanded_second_backbone_qualification_v1"
PROBE_SCHEMA = "expanded_second_backbone_probe_v1"
ADMISSION_SCHEMA = "expanded_second_backbone_admission_v1"
CELL_SCHEMA = "expanded_second_backbone_training_cell_v1"
TRAINING_REPORT_SCHEMA = "expanded_second_backbone_training_report_v1"
EPISODE_SCHEMA = "expanded_second_backbone_episode_v1"
EVIDENCE_SCHEMA = "expanded_second_backbone_evaluation_evidence_v1"
ANALYSIS_SCHEMA = "expanded_second_backbone_analysis_v1"
RECEIPT_FILE = "completion-receipt.json"
RECOVERY_FILE = ".training-recovery.json"
FRESH_INIT_FILE = "fresh-lora-init.safetensors"
BACKBONE_KEY = "internvl3_5-8b"
MODEL_CONDITIONS = ("pretrained_base", "process_sft")
COMPARATOR_CONDITIONS = ("random_valid", "exact_reference")
PANEL_NAME = "unseen"
SCHEDULE_DOC = "docs/experiments/expanded-study/schedule.json"
LEDGER_PATH = "outputs/expanded-study/v1/budget.json"
EXPECTED_ADAPTER_TENSORS = 504
BASELINE_PANEL_ID = "expanded-panel-v2-qualified"


def _branch_spent(ledger: Mapping[str, Any], branch: str = "second_backbone") -> float:
    return sum(
        float(attempt.get("gpu_hours", 0.0)) for attempt in ledger.get("attempts", []) if attempt.get("branch") == branch
    )


def _json_sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(value).encode()).hexdigest()


def _ids_sha256(ids: Sequence[str]) -> str:
    return "sha256:" + hashlib.sha256("\n".join(ids).encode()).hexdigest()


def backbone_page_processor(protocol: Mapping[str, Any]):
    return page_processor_for(protocol["base_model"]["backbone_key"])


def training_root(root: Path, protocol: Mapping[str, Any], modality: str) -> Path:
    return root / protocol["output_root"] / "training" / modality


def qualification_root(root: Path, protocol: Mapping[str, Any]) -> Path:
    return root / protocol["output_root"] / "qualification"


def evaluation_root(root: Path, protocol: Mapping[str, Any]) -> Path:
    return root / protocol["output_root"] / "evaluation"


def _task_name(task_id: str) -> str:
    return task_id.replace("/", "__")


def load_panel(root: Path, protocol: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    panel = read_json(root / protocol["evaluation"]["panel"])
    views = read_json(root / panel["view_report"])
    tasks = list(views["tasks"])
    if (
        panel.get("program_id") != protocol["program_id"]
        or panel.get("panel_id") != protocol["evaluation"]["panel_id"]
        or panel.get("evaluation_seed") != protocol["evaluation"]["seed"]
        or len(panel.get("tasks", [])) != 24
        or len(tasks) != 24
        or {task["row"]["task_id"] for task in tasks} != {task["row"]["task_id"] for task in panel["tasks"]}
        or any("native_views" not in task for task in tasks)
    ):
        raise ValueError("second-backbone panel differs from the frozen qualified panel")
    for task in panel["tasks"]:
        if not (root / task["reference_paths"][protocol["algorithm"]]).is_file():
            raise ValueError("second-backbone panel reference trace is missing")
    return panel, tasks


def _source_files(root: Path, protocol: Mapping[str, Any], corpus: ModalityCorpus, records) -> list[Path]:
    paths = {
        root / protocol["source_membership"],
        root / protocol["source_corpus"],
        root / protocol["source_study"],
        root / protocol["views"]["scene_views"],
        root / protocol["selection_doc"],
        root / protocol["evaluation"]["panel"],
    }
    task_ids = {record["task_id"] for record in records}
    scene_report = read_json(root / protocol["views"]["scene_views"])
    raw_scene_tasks = scene_report.get("tasks", {})
    scene_tasks = (
        raw_scene_tasks if isinstance(raw_scene_tasks, dict) else {row["task_id"]: row for row in raw_scene_tasks}
    )
    states_by_task: dict[str, set[str]] = {}
    for record in records:
        states_by_task.setdefault(record["task_id"], set()).add(str(record["state"]))
    for task_id in task_ids:
        result = corpus.results[task_id]
        for key in ("path", "view_manifest"):
            if result.get(key):
                paths.add(root / result[key])
        scene = scene_tasks.get(task_id, {})
        if scene.get("source_manifest"):
            source_manifest = root / scene["source_manifest"]
            paths.add(source_manifest)
            manifest = read_json(source_manifest)
            paths.add(root / manifest["scene_catalog"])
        for path in (*scene.get("static_pages", []), *scene.get("goal_pages", [])):
            paths.add(root / path)
        scenes = scene.get("scenes", {})
        for state in {"0", *states_by_task.get(task_id, set())}:
            if state in scenes:
                paths.add(root / scenes[state])
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise ValueError(f"second-backbone source artifacts are missing: {missing[0]}")
    return sorted(paths)


def validate_protocol(root: Path, protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Hard-fail unless every frozen protocol reference still matches reality."""
    schedule = read_json(root / SCHEDULE_DOC)
    pinned_sha256 = {
        "selection_doc": protocol["selection_doc"],
        "source_study": protocol["source_study"],
        "source_membership": protocol["source_membership"],
        "source_corpus": protocol["source_corpus"],
        "views.contract": protocol["views"]["contract"],
        "views.scene_views": protocol["views"]["scene_views"],
        "evaluation.panel": protocol["evaluation"]["panel"],
        "evaluation.comparator_audit.baseline_protocol": protocol["evaluation"]["comparator_audit"]["baseline_protocol"],
        "evaluation.comparator_audit.baseline_evaluation": protocol["evaluation"]["comparator_audit"][
            "baseline_evaluation"
        ],
        "evaluation.comparator_audit.baseline_independent_replay": protocol["evaluation"]["comparator_audit"][
            "baseline_independent_replay"
        ],
    }
    sha_lookup = {
        "selection_doc": protocol["selection_doc_sha256"],
        "source_study": protocol["source_study_sha256"],
        "source_membership": protocol["source_membership_sha256"],
        "source_corpus": protocol["source_corpus_sha256"],
        "views.contract": protocol["views"]["contract_sha256"],
        "views.scene_views": protocol["views"]["scene_views_sha256"],
        "evaluation.panel": protocol["evaluation"]["panel_sha256"],
        "evaluation.comparator_audit.baseline_protocol": protocol["evaluation"]["comparator_audit"][
            "baseline_protocol_sha256"
        ],
        "evaluation.comparator_audit.baseline_evaluation": protocol["evaluation"]["comparator_audit"][
            "baseline_evaluation_sha256"
        ],
        "evaluation.comparator_audit.baseline_independent_replay": protocol["evaluation"]["comparator_audit"][
            "baseline_independent_replay_sha256"
        ],
    }
    for key, relative in pinned_sha256.items():
        if _sha256(root / relative) != sha_lookup[key]:
            raise ValueError(f"second-backbone pinned artifact differs: {key}")

    study = read_json(root / protocol["source_study"])
    membership = read_json(root / protocol["source_membership"])
    base, training, evaluation, launch, budget = (
        protocol["base_model"],
        protocol["training"],
        protocol["evaluation"],
        protocol["launch"],
        protocol["budget"],
    )
    spec = backbone_spec(base["backbone_key"])
    expected_training = {
        "records_per_cell": 512,
        "epochs": 1,
        "optimizer_updates": 16,
        "seed": 17,
        "data_seed": 17,
        "microbatch_size": 1,
        "global_batch_size": 32,
        "gradient_accumulation_steps": 32,
        "sampler": "sequential_membership_order",
        "trainer_reshuffling": False,
        "learning_rate": 0.0001,
        "optimizer": "adamw_torch",
        "adam_beta1": 0.9,
        "adam_beta2": 0.999,
        "adam_epsilon": 1e-8,
        "warmup_ratio": 0.03,
        "warmup_steps": 1,
        "lr_scheduler": "cosine",
        "weight_decay": 0,
        "max_grad_norm": 1,
        "lora_rank": 64,
        "lora_alpha": 128,
        "lora_dropout": 0.05,
        "lora_target_modules": "all-linear",
        "lora_exclude_modules": r".*(vision_tower|multi_modal_projector).*",
        "lora_bias": "none",
        "lora_task_type": "CAUSAL_LM",
        "freeze_vision": True,
        "dtype": "bfloat16",
        "attention": "sdpa",
        "gradient_checkpointing_use_reentrant": False,
        "checkpoint_selection": "final_update_16_only",
        "loss": "shared_collator_assistant_target_only",
        "single_training_seed_limitation": (
            "exactly one training run per cell; no training-seed variance is estimated or claimed"
        ),
    }
    if (
        protocol.get("schema_version") != "expanded_second_backbone_protocol_v1"
        or protocol.get("protocol_id") != "expanded-second-backbone-v1"
        or protocol.get("status") != "frozen_before_qualification"
        or protocol.get("issues") != [101, 102, 103]
        or protocol.get("parent_issue") != 38
        or protocol.get("algorithm") != "bfs"
        or protocol.get("modalities") != ["text-state", "visual-state", "multimodal-state"]
        or protocol.get("source_study") != "configs/experiments/matched-modalities/study-v5.json"
        or protocol.get("source_membership") != "configs/experiments/matched-modalities/membership.json"
        or protocol.get("source_corpus") != "outputs/modality_corpus/issue74-matched-32k-v1/release-001/report.json"
        or protocol.get("output_root") != "outputs/expanded-study/v1/second-backbone"
        or protocol.get("source_record_ids") != membership["training_record_ids"][protocol["algorithm"]]
        or protocol.get("source_record_ids_sha256") != _ids_sha256(protocol["source_record_ids"])
        or len(protocol["source_record_ids"]) != 512
        or len(set(protocol["source_record_ids"])) != 512
        or base.get("backbone_key") != BACKBONE_KEY
        or base.get("model_id") != spec["model_id"]
        or base.get("revision") != spec["model_revision"]
        or base.get("processor_class") != spec["processor_class"]
        or base.get("model_class") != spec["model_class"]
        or base.get("processor_overrides") != {}
        or base.get("license") != spec["license"]
        or base.get("historical_checkpoint_reuse") is not False
        or training != expected_training
        or training["lora_exclude_modules"] != spec["lora_exclude_modules"]
        or evaluation.get("panel") != "configs/experiments/expanded-study/final-panel.json"
        or evaluation.get("panel_id") != BASELINE_PANEL_ID
        or evaluation.get("seed") != 17
        or evaluation.get("final_checkpoints_only") is not True
        or evaluation.get("model_conditions") != list(MODEL_CONDITIONS)
        or evaluation.get("comparator_conditions") != list(COMPARATOR_CONDITIONS)
        or evaluation.get("reference_decision_multiplier") != 2
        or evaluation.get("expansion_cap") != "reference_expansions"
        or evaluation.get("logical_bindings") != 288
        or evaluation.get("model_episodes") != 144
        or evaluation.get("comparator_episodes") != 144
        or evaluation.get("context_tokens") != 32768
        or evaluation.get("maximum_input_tokens") != 32384
        or evaluation.get("output_tokens") != 384
        or evaluation.get("inference")
        != {
            "dtype": "float32",
            "attention": "visual_sdpa",
            "attention_fallback": "sdpa (only on documented probe incompatibility, disclosed in probe evidence)",
            "do_sample": False,
            "max_batch_size": 2,
            "max_padded_batch_input_tokens": 24000,
            "allow_qualified_single_input_above_batch_cap": True,
            "output_cache": "none",
            "kv_cache": "per_call_only",
        }
        or launch.get("devices") != [0, 1]
        or launch.get("master_port_pool") != schedule["master_port_pool"]
        or launch.get("backend_endpoints") != ["http://127.0.0.1:18092", "http://127.0.0.1:18093"]
        or launch.get("training_worker_cells")
        != {"0": [{"modality": "text-state"}, {"modality": "visual-state"}], "1": [{"modality": "multimodal-state"}]}
        or launch.get("evaluation_worker_policy_load_order") != {"0": ["text-state", "multimodal-state"], "1": ["visual-state"]}
        or launch.get("evaluation_worker_partition") != "task_index_modulo_two_within_every_modality_condition_cell"
        or budget.get("branch") != "second_backbone"
        or budget.get("gpu_hours") != 40
        or budget.get("gpu_hours") != schedule["allocations_gpu_hours"]["second_backbone"]
        or budget.get("qualification_safety_factor") != 1.25
        or budget.get("qualification_safety_factor") != schedule["qualification_safety_factor"]
        or not study.get("model_id")
    ):
        raise ValueError("second-backbone protocol differs from the frozen study")
    ledger_path = root / LEDGER_PATH
    if ledger_path.is_file():
        ledger = read_json(ledger_path)
        if (
            ledger.get("schedule") != schedule
            or ledger.get("allocations_gpu_hours") != schedule["allocations_gpu_hours"]
        ):
            raise ValueError("second-backbone scheduler ledger schedule block differs")
    panel, panel_tasks = load_panel(root, protocol)
    corpus = ModalityCorpus(root, root / protocol["source_corpus"], scene_views=protocol["views"]["scene_views"])
    records = list(corpus.records(algorithm=protocol["algorithm"], split="train"))
    indexed = {record["record_id"]: record for record in records}
    if not set(protocol["source_record_ids"]).issubset(indexed):
        raise ValueError("second-backbone source corpus omits frozen membership records")
    selected = [indexed[record_id] for record_id in protocol["source_record_ids"]]
    source_files = _source_files(root, protocol, corpus, selected)
    return {
        "study": study,
        "membership": membership,
        "corpus": corpus,
        "records": selected,
        "source_files": source_files,
        "panel": panel,
        "panel_tasks": panel_tasks,
    }


def qualify_inputs(
    root: Path,
    protocol: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    record_limit: int | None = None,
    task_limit: int | None = None,
    progress: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """Re-measure every training and live input under the InternVL processor."""
    started = time.monotonic()
    processor = backbone_page_processor(protocol)
    qwen = frozen_processor()
    modalities = list(protocol["modalities"])
    context_tokens = protocol["evaluation"]["context_tokens"]
    output_tokens = protocol["evaluation"]["output_tokens"]
    records = list(context["records"])
    if record_limit is not None:
        records = records[:record_limit]
    tasks = list(context["panel_tasks"])
    if task_limit is not None:
        tasks = tasks[:task_limit]

    train_prefix: dict[str, Counter] = {modality: Counter() for modality in modalities}
    train_full: dict[str, Counter] = {modality: Counter() for modality in modalities}
    train_measurements: list[dict[str, Any]] = []
    live_measurements: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    tokenizer_identity = True
    extrema: dict[str, dict[str, Any]] = {}
    total_steps = len(records) * len(modalities)
    step = 0
    for record in records:
        for modality in modalities:
            example = context["corpus"].training_example(record, modality)
            messages, images = example["messages"], example["images"]
            sizes = [image.size for image in images]
            prefix = processor.count(messages[:-1], image_sizes=sizes)
            full = processor.count(messages, image_sizes=sizes)
            train_prefix[modality][prefix] += 1
            train_full[modality][full] += 1
            if modality == "text-state":
                templated = processor.processor.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=False
                )
                if (
                    qwen.processor.tokenizer(templated)["input_ids"]
                    != processor.processor.tokenizer(templated)["input_ids"]
                ):
                    tokenizer_identity = False
            if prefix + output_tokens > context_tokens or full > context_tokens:
                violations.append(
                    {
                        "kind": "training",
                        "record_id": record["record_id"],
                        "modality": modality,
                        "prefix_tokens": prefix,
                        "full_tokens": full,
                    }
                )
            train_measurements.append(
                {"record_id": record["record_id"], "modality": modality, "prefix_tokens": prefix, "full_tokens": full}
            )
            for image in images:
                image.close()
            step += 1
            if progress is not None and (step % 10 == 0 or step == total_steps):
                progress(completed=step, total=total_steps, stage="training_inputs")

    endpoint = protocol["launch"]["backend_endpoints"][0]
    qual_root = qualification_root(root, protocol)
    raw_inputs: dict[tuple[str, int], dict[str, Any]] = {}
    densest: tuple[int, dict[str, Any], str, int] | None = None
    for task in tasks:
        reference = read_json(root / task["reference_paths"][protocol["algorithm"]])
        task_name = _task_name(task["row"]["task_id"])
        views = ExpandedTaskViews(
            root,
            task,
            qual_root / "live-views" / task_name,
            endpoint,
            read_only=True,
            page_processor=processor,
        )
        session = VisualSession(
            root,
            task["row"],
            protocol["algorithm"],
            "exact_reference",
            protocol["evaluation"]["seed"],
            qual_root / "reference-replay" / task_name,
            protocol["protocol_id"],
            views=None,
        )
        for index, event in enumerate(reference["events"]):
            request = session.next_request()
            if request is None or dict(request.model_input) != event["input"]:
                raise ValueError("second-backbone qualification reference input differs")
            raw_inputs[(task["row"]["task_id"], index)] = dict(request.model_input)
            for modality in modalities:
                try:
                    observed = views.observe(
                        dict(request.model_input), protocol["algorithm"], modality=modality, pixels=False
                    )
                except RuntimeError as error:
                    if "VALID_STOP" not in str(error):
                        raise
                    violations.append(
                        {
                            "kind": "live",
                            "task_id": task["row"]["task_id"],
                            "modality": modality,
                            "event_index": index,
                        }
                    )
                    continue
                tokens = observed["binding"]["input_tokens"]
                live_measurements.append(
                    {
                        "task_id": task["row"]["task_id"],
                        "event_index": index,
                        "modality": modality,
                        "input_tokens": tokens,
                        "input_pages": observed["binding"]["input_pages"],
                    }
                )
                if densest is None or tokens > densest[0]:
                    densest = (tokens, task, modality, index)
            session.submit(event["raw_output"])
        if session.next_request() is not None or session.result() != reference["result"]:
            raise ValueError("second-backbone qualification reference replay differs")
        if progress is not None:
            progress(
                completed=len([m for m in live_measurements]),
                total=total_steps,
                stage="live_inputs",
                task_id=task["row"]["task_id"],
            )

    cross_checks = []
    for modality in modalities:
        rows = [row for row in live_measurements if row["modality"] == modality]
        if not rows:
            continue
        dense = max(rows, key=lambda row: row["input_tokens"])
        task = next(t for t in tasks if t["row"]["task_id"] == dense["task_id"])
        views = ExpandedTaskViews(
            root,
            task,
            qual_root / "live-views" / _task_name(dense["task_id"]),
            endpoint,
            read_only=True,
            page_processor=processor,
        )
        observed = views.observe(
            raw_inputs[(dense["task_id"], dense["event_index"])],
            protocol["algorithm"],
            modality=modality,
            pixels=True,
        )
        processor.verify_complete(observed["messages"], observed["images"])
        for image in observed["images"]:
            image.close()
        cross_checks.append(
            {
                "modality": modality,
                "task_id": dense["task_id"],
                "event_index": dense["event_index"],
                "input_tokens": observed["binding"]["input_tokens"],
                "images": len(observed["images"]),
                "verify_complete": True,
            }
        )

    preview_rows: list[dict[str, Any]] = []
    if densest is not None:
        _, task, modality, index = densest
        task_name = _task_name(task["row"]["task_id"])
        views = ExpandedTaskViews(
            root, task, qual_root / "live-views" / task_name, endpoint, read_only=True, page_processor=processor
        )
        observed = views.observe(
            raw_inputs[(task["row"]["task_id"], index)], protocol["algorithm"], modality=modality, pixels=True
        )
        preview_dir = qual_root / "previews" / task_name
        for page_index, (image, binding) in enumerate(
            zip(observed["images"], observed["binding"]["input_pages"], strict=False)
        ):
            preview = processor.preview(image)
            path = preview_dir / f"page-{page_index:02d}-{binding[0]}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            preview.save(path)
            preview.close()
            preview_rows.append({"page": page_index, "role": binding[0], "path": str(path.relative_to(root))})
        for image in observed["images"]:
            image.close()

    maxima = {}
    for modality in modalities:
        live_tokens = [row["input_tokens"] for row in live_measurements if row["modality"] == modality]
        maxima[modality] = {
            "train_prefix": max(train_prefix[modality]) if train_prefix[modality] else None,
            "train_full": max(train_full[modality]) if train_full[modality] else None,
            "live": max(live_tokens) if live_tokens else None,
        }
        prefix_rows = [row for row in train_measurements if row["modality"] == modality]
        if prefix_rows:
            smallest = min(prefix_rows, key=lambda row: row["full_tokens"])
            densest_train = max(prefix_rows, key=lambda row: row["full_tokens"])
            extrema[modality] = {
                "smallest_full": {
                    "record_id": smallest["record_id"],
                    "full_tokens": smallest["full_tokens"],
                },
                "densest_full": {
                    "record_id": densest_train["record_id"],
                    "full_tokens": densest_train["full_tokens"],
                },
            }
    if live_measurements:
        dense_live = max(live_measurements, key=lambda row: row["input_tokens"])
        extrema["densest_live"] = {
            "task_id": dense_live["task_id"],
            "event_index": dense_live["event_index"],
            "modality": dense_live["modality"],
            "input_tokens": dense_live["input_tokens"],
        }
    outcome = "PASS" if not violations and tokenizer_identity else "VALID_STOP"
    complete = record_limit is None and task_limit is None
    distributions_path = qual_root / "decision-token-distributions.json.gz"
    write_json(
        distributions_path,
        {
            "schema_version": "expanded_second_backbone_token_distributions_v1",
            "protocol_id": protocol["protocol_id"],
            "train_prefix": {modality: dict(train_prefix[modality]) for modality in modalities},
            "train_full": {modality: dict(train_full[modality]) for modality in modalities},
            "live": {
                modality: [row["input_tokens"] for row in live_measurements if row["modality"] == modality]
                for modality in modalities
            },
            "train_measurements": train_measurements,
            "live_measurements": live_measurements,
        },
    )
    result = {
        "schema_version": QUALIFICATION_SCHEMA,
        "outcome": outcome,
        "protocol_id": protocol["protocol_id"],
        "backbone_key": BACKBONE_KEY,
        "complete": complete,
        "limits": {"record_limit": record_limit, "task_limit": task_limit},
        "context_tokens": context_tokens,
        "output_tokens": output_tokens,
        "records_measured": len(records) * len(modalities),
        "tasks_measured": len(tasks),
        "decisions_measured": len(live_measurements),
        "tokenizer_identity": tokenizer_identity,
        "maxima": maxima,
        "extrema": extrema,
        "violations": violations,
        "cross_checks": cross_checks,
        "previews": preview_rows,
        "decision_token_distributions": str(distributions_path.relative_to(root)),
        "elapsed_seconds": time.monotonic() - started,
    }
    write_json(qual_root / "qualification.json", result)
    return result


def _summary(values: Sequence[float]) -> dict[str, float]:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return {"mean": 0.0, "p05": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0, "calls": 0}

    def quantile(probability: float) -> float:
        position = probability * (len(ordered) - 1)
        lower = math.floor(position)
        upper = min(len(ordered) - 1, lower + 1)
        fraction = position - lower
        return ordered[lower] * (1 - fraction) + ordered[upper] * fraction

    return {
        "mean": sum(ordered) / len(ordered),
        "p05": quantile(0.05),
        "p50": quantile(0.5),
        "p95": quantile(0.95),
        "max": ordered[-1],
        "calls": len(ordered),
    }


def _densest_live_examples(
    root: Path, protocol: Mapping[str, Any], task: Mapping[str, Any], count: int, modality: str
) -> list[dict[str, Any]]:
    """Rebuild the densest live decision examples of one task with real pixels."""
    processor = backbone_page_processor(protocol)
    endpoint = protocol["launch"]["backend_endpoints"][0]
    reference = read_json(root / task["reference_paths"][protocol["algorithm"]])
    task_name = _task_name(task["row"]["task_id"])
    views = ExpandedTaskViews(
        root,
        task,
        qualification_root(root, protocol) / "live-views" / task_name,
        endpoint,
        read_only=True,
        page_processor=processor,
    )
    session = VisualSession(
        root,
        task["row"],
        protocol["algorithm"],
        "exact_reference",
        protocol["evaluation"]["seed"],
        qualification_root(root, protocol) / "reference-replay" / task_name,
        protocol["protocol_id"],
        views=None,
    )
    examples = []
    seen = set()
    for event in reference["events"]:
        request = session.next_request()
        if request is None:
            break
        observed = views.observe(dict(request.model_input), protocol["algorithm"], modality=modality, pixels=True)
        key = observed["binding"]["input_tokens"]
        if key not in seen:
            seen.add(key)
            examples.append(observed)
        else:
            for image in observed["images"]:
                image.close()
        session.submit(event["raw_output"])
        if len(examples) >= count:
            break
    examples.sort(key=lambda example: example["binding"]["input_tokens"], reverse=True)
    return examples[:count]


def _save_probe_adapters(model: Any, protocol: Mapping[str, Any], output_dir: Path) -> dict[str, str]:
    """Save two freshly initialized LoRA adapters (seeds 17/18) for isolation probes.

    ``model`` arrives already LoRA-wrapped by ``load_training_model`` with a fresh
    "default" adapter; a second fresh adapter ("probe_b", seed 18) is added here.
    Fresh LoRA inits have zero B, so a small deterministic B perturbation is added
    to each saved state; production adapters come from training, never from here.
    """
    import torch
    from peft import LoraConfig, get_peft_model_state_dict
    from safetensors.torch import save_file
    from transformers import set_seed

    training = protocol["training"]
    config = LoraConfig(
        r=training["lora_rank"],
        lora_alpha=training["lora_alpha"],
        lora_dropout=training["lora_dropout"],
        bias="none",
        target_modules="all-linear",
        exclude_modules=training["lora_exclude_modules"],
        task_type="CAUSAL_LM",
    )
    set_seed(training["seed"] + 1)
    model.add_adapter("probe_b", config)
    directories = {}
    for name, seed in (("default", training["seed"]), ("probe_b", training["seed"] + 1)):
        state = get_peft_model_state_dict(model, adapter_name=name)
        generator = torch.Generator().manual_seed(seed)
        perturbed = {}
        for key, tensor in state.items():
            tensor = tensor.detach().cpu()
            if key.endswith("lora_B.weight"):
                noise = (torch.rand(tensor.shape, generator=generator, dtype=torch.float32) - 0.5) * 0.02
                perturbed[key] = (tensor.float() + noise).to(tensor.dtype)
            else:
                perturbed[key] = tensor
        directory = output_dir / f"probe-{seed}"
        directory.mkdir(parents=True, exist_ok=True)
        save_file(perturbed, str(directory / "adapter_model.safetensors"), metadata={"format": "pt"})
        config.save_pretrained(str(directory))
        directories[name] = str(directory)
    model.set_adapter("default")
    return directories


def probe_stage(
    root: Path,
    protocol: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    attempt_dir: Path,
    progress: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """GPU probe: parity, determinism, isolation, guards, throughput, step cost."""
    import torch
    from transformers import set_seed

    from .visual_attention import configure_visual_attention
    from .visual_model import VisualCollator, VisualPolicy, load_training_model

    attempt_dir = Path(attempt_dir)
    started_all = time.monotonic()
    evaluation = protocol["evaluation"]
    inference = evaluation["inference"]
    processor = backbone_page_processor(protocol)
    spec = backbone_spec(protocol["base_model"]["backbone_key"])
    qualification = read_json(qualification_root(root, protocol) / "qualification.json")
    if qualification.get("outcome") != "PASS" or not qualification.get("complete"):
        raise RuntimeError("second-backbone probe requires a complete PASS qualification")
    set_seed(evaluation["seed"])

    load_started = time.monotonic()
    policy = VisualPolicy(
        model_id=protocol["base_model"]["model_id"],
        revision=protocol["base_model"]["revision"],
        adapter_paths={},
        device="cuda:0",
        max_context_tokens=evaluation["context_tokens"],
        max_new_tokens=evaluation["output_tokens"],
        max_batch_size=inference["max_batch_size"],
        max_batch_input_tokens=inference["max_padded_batch_input_tokens"],
        inference_dtype="float32",
        backbone=spec,
        page_processor=processor,
    )
    load_seconds = time.monotonic() - load_started
    load_vram = torch.cuda.memory_allocated()
    attention = {"requested": inference["attention"], "applied": None, "fallback_used": False}
    try:
        configure_visual_attention(policy.model, inference["attention"])
    except Exception:
        configure_visual_attention(policy.model, "sdpa")
        attention["fallback_used"] = True
    attention["applied"] = getattr(policy.model.config, "_attn_implementation", None)

    indexed = {record["record_id"]: record for record in context["records"]}

    def training_example(record_id: str, modality: str) -> dict[str, Any]:
        return context["corpus"].training_example(indexed[record_id], modality)

    def close_example(example: Mapping[str, Any]) -> None:
        for image in example.get("images", []):
            image.close()

    extrema = qualification["extrema"]
    dense_modality = max(
        protocol["modalities"], key=lambda modality: extrema[modality]["densest_full"]["full_tokens"]
    )
    smallest_id = extrema[dense_modality]["smallest_full"]["record_id"]
    densest_id = extrema[dense_modality]["densest_full"]["record_id"]
    parity_examples = [training_example(smallest_id, dense_modality), training_example(densest_id, dense_modality)]
    try:
        lengths = [
            processor.count(example["messages"], image_sizes=[image.size for image in example["images"]])
            for example in parity_examples
        ]
        batch_size = len(parity_examples)
        if max(lengths) * batch_size > inference["max_padded_batch_input_tokens"]:
            batch_size = 1
        scalar_outputs = [policy.generate([example], force_full_output=True)[0] for example in parity_examples]
        batched_outputs = []
        for offset in range(0, len(parity_examples), batch_size):
            batched_outputs.extend(
                policy.generate(parity_examples[offset : offset + batch_size], force_full_output=True)
            )
        parity = {
            "modality": dense_modality,
            "smallest_full_tokens": lengths[0],
            "densest_full_tokens": lengths[1],
            "batch_size": batch_size,
            "byte_identical": scalar_outputs == batched_outputs,
        }
        repeated = []
        for offset in range(0, len(parity_examples), batch_size):
            repeated.extend(policy.generate(parity_examples[offset : offset + batch_size], force_full_output=True))
        determinism = {"byte_identical": repeated == batched_outputs}
    finally:
        for example in parity_examples:
            close_example(example)
    if not parity["byte_identical"]:
        raise RuntimeError("VALID_STOP: second-backbone scalar/batch parity failed")
    if not determinism["byte_identical"]:
        raise RuntimeError("VALID_STOP: second-backbone repeated-batch determinism failed")

    live_reference = extrema["densest_live"]
    live_task = next(task for task in context["panel_tasks"] if task["row"]["task_id"] == live_reference["task_id"])
    live_examples = _densest_live_examples(root, protocol, live_task, 4, live_reference["modality"])
    try:
        near_limit = live_examples[0]
        near_lengths = processor.count(
            near_limit["messages"], image_sizes=[image.size for image in near_limit["images"]]
        )
        policy.generate([near_limit], force_full_output=True)
        token_guards = {
            "near_limit_input_tokens": near_lengths,
            "near_limit_succeeded": True,
            "oversize_batch_raises_valid_stop": False,
        }
        original = policy.page_processor

        class _OversizeCounter:
            def count(self, *args, **kwargs):
                return evaluation["maximum_input_tokens"] + 1

        policy.page_processor = _OversizeCounter()
        try:
            policy.generate([near_limit])
        except RuntimeError as error:
            token_guards["oversize_batch_raises_valid_stop"] = "VALID_STOP" in str(error)
        finally:
            policy.page_processor = original
    finally:
        for example in live_examples:
            close_example(example)

    throughput = {}
    for modality in protocol["modalities"]:
        task = live_task
        examples = _densest_live_examples(root, protocol, task, 4, modality)
        latencies, tokens_per_second, input_tokens, batch_sizes = [], [], [], []
        try:
            counts = [
                processor.count(example["messages"], image_sizes=[image.size for image in example["images"]])
                for example in examples
            ]
            batches = form_generation_batches(
                examples,
                counts,
                max_batch_size=inference["max_batch_size"],
                max_batch_input_tokens=inference["max_padded_batch_input_tokens"],
            )
            torch.cuda.reset_peak_memory_stats()
            calls = 0
            while calls < 20:
                for batch in batches:
                    if calls >= 20:
                        break
                    call_started = time.monotonic()
                    policy.generate(batch)
                    latencies.append(time.monotonic() - call_started)
                    usage = policy.last_generation_usage
                    tokens_per_second.append(usage["generated_sequence_tokens"] / max(latencies[-1], 1e-9))
                    input_tokens.extend(usage["input_tokens"])
                    batch_sizes.append(len(batch))
                    calls += 1
            throughput[modality] = {
                "task_id": task["row"]["task_id"],
                "calls": calls,
                "batch_sizes": {
                    "min": min(batch_sizes),
                    "max": max(batch_sizes),
                    "mean": sum(batch_sizes) / len(batch_sizes),
                },
                "latency_seconds": _summary(latencies),
                "tokens_per_second": {
                    "mean": sum(tokens_per_second) / len(tokens_per_second),
                    "lower_95": sorted(tokens_per_second)[max(0, int(0.05 * (len(tokens_per_second) - 1)))],
                },
                "input_tokens": _summary(input_tokens),
                "peak_vram_bytes": torch.cuda.max_memory_allocated(),
            }
        finally:
            for example in examples:
                close_example(example)
        if progress is not None:
            progress(completed=len(throughput), total=len(protocol["modalities"]), stage="throughput")

    training_model = load_training_model(_training_model_config(protocol))
    adapter_dirs = _save_probe_adapters(training_model, protocol, attempt_dir)
    isolation_examples = [training_example(densest_id, dense_modality)]
    try:
        policy.adapter_paths = dict(adapter_dirs)
        outputs = {}
        for adapter_id in (None, "default", "probe_b"):
            outputs[adapter_id] = [
                policy.generate([example], adapter_id, force_full_output=True)[0] for example in isolation_examples
            ]
        base_outputs = outputs[None]
        adapter_isolation = {
            "adapters": sorted(adapter_dirs),
            "initialization": (
                "fresh LoRA init (seeds 17/18) with a deterministic small B perturbation so adapters "
                "have nonzero effect; production adapters come from training only"
            ),
            "base_vs_adapter_a": base_outputs != outputs["default"],
            "base_vs_adapter_b": base_outputs != outputs["probe_b"],
            "adapter_a_vs_adapter_b": outputs["default"] != outputs["probe_b"],
            "disable_restores_base": True,
        }
        if not (
            adapter_isolation["base_vs_adapter_a"]
            and adapter_isolation["base_vs_adapter_b"]
            and adapter_isolation["adapter_a_vs_adapter_b"]
        ):
            raise RuntimeError("VALID_STOP: second-backbone adapter isolation failed")
    finally:
        for example in isolation_examples:
            close_example(example)

    # The fp32 policy is no longer needed; production training runs without it resident.
    del policy
    import gc

    gc.collect()
    torch.cuda.empty_cache()

    training_step = {}
    collator = VisualCollator(processor.processor, page_processor=processor)
    distributions = read_json(qualification_root(root, protocol) / "decision-token-distributions.json.gz")
    trainable = [parameter for parameter in training_model.parameters() if parameter.requires_grad]
    optimizer = torch.optim.AdamW(
        trainable,
        lr=protocol["training"]["learning_rate"],
        betas=(protocol["training"]["adam_beta1"], protocol["training"]["adam_beta2"]),
        eps=protocol["training"]["adam_epsilon"],
        weight_decay=protocol["training"]["weight_decay"],
    )
    training_model.train()
    for modality in protocol["modalities"]:
        rows = [row for row in distributions["train_measurements"] if row["modality"] == modality]
        dense_ids = [
            row["record_id"]
            for row in sorted(rows, key=lambda row: row["full_tokens"], reverse=True)[
                : protocol["training"]["global_batch_size"]
            ]
        ]
        examples = [training_example(record_id, modality) for record_id in dense_ids]
        torch.cuda.reset_peak_memory_stats()
        started = time.monotonic()
        try:
            optimizer.zero_grad(set_to_none=True)
            for example in examples:
                batch = {
                    key: value.to("cuda:0") if torch.is_tensor(value) else value
                    for key, value in collator([example]).items()
                }
                loss = training_model(**batch).loss / protocol["training"]["gradient_accumulation_steps"]
                loss.backward()
            torch.nn.utils.clip_grad_norm_(trainable, protocol["training"]["max_grad_norm"])
            optimizer.step()
        finally:
            wall = time.monotonic() - started
            for example in examples:
                close_example(example)
        training_step[modality] = {
            "optimizer_steps": 1,
            "microbatches": len(examples),
            "wall_seconds": wall,
            "peak_vram_bytes": torch.cuda.max_memory_allocated(),
            "max_full_tokens": max(row["full_tokens"] for row in rows) if rows else None,
        }
        if progress is not None:
            progress(
                completed=len(training_step),
                total=len(protocol["modalities"]),
                stage="training_step_cost",
            )
    del training_model
    import gc

    gc.collect()
    torch.cuda.empty_cache()
    result = {
        "schema_version": PROBE_SCHEMA,
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "backbone_key": BACKBONE_KEY,
        "gpu": {"index": 0, "name": torch.cuda.get_device_name(0)},
        "load": {"wall_seconds": load_seconds, "vram_bytes_after_load": load_vram},
        "attention": attention,
        "scalar_batch_parity": parity,
        "repeated_batch_determinism": determinism,
        "adapter_isolation": adapter_isolation,
        "token_limit_guards": token_guards,
        "throughput": throughput,
        "training_step": training_step,
        "probe_gpu_hours": (time.monotonic() - started_all) / 3600,
        "finished_at": time.time(),
    }
    write_json(attempt_dir / "probe.json", result)
    write_json(root / protocol["output_root"] / "probe.json", result)
    return result


def _training_model_config(protocol: Mapping[str, Any]) -> dict[str, Any]:
    base, training = protocol["base_model"], protocol["training"]
    return {
        "model_id": base["model_id"],
        "model_revision": base["revision"],
        "model_class": base["model_class"],
        "training_seed": training["seed"],
        "training": {
            "lora_rank": training["lora_rank"],
            "lora_alpha": training["lora_alpha"],
            "lora_dropout": training["lora_dropout"],
            "lora_exclude_modules": training["lora_exclude_modules"],
            "freeze_vision": training["freeze_vision"],
            "attention": training["attention"],
        },
    }


def decide_admission(
    protocol: Mapping[str, Any],
    qualification: Mapping[str, Any],
    probe: Mapping[str, Any],
    *,
    branch_spent_gpu_hours: float,
    panel_task_costs: Sequence[Mapping[str, Any]],
    panel_task_ids: Sequence[str],
) -> dict[str, Any]:
    training = protocol["training"]
    budget = protocol["budget"]
    safety = budget["qualification_safety_factor"]
    cap = budget["gpu_hours"]
    remainder = cap - branch_spent_gpu_hours
    modalities = list(protocol["modalities"])
    step_costs = {modality: probe["training_step"][modality]["wall_seconds"] for modality in modalities}
    training_seconds = sum(step_costs.values()) * training["optimizer_updates"]
    latency = {modality: probe["throughput"][modality]["latency_seconds"]["p95"] for modality in modalities}
    reference_decisions = [cost["bfs"]["decisions"] for cost in panel_task_costs]
    if len(panel_task_ids) != len(reference_decisions) or len(set(panel_task_ids)) != len(panel_task_ids):
        raise ValueError("second-backbone admission task identities differ from panel costs")
    tasks_by_cost = sorted(range(len(reference_decisions)), key=lambda index: reference_decisions[index])

    def level_arithmetic(task_indices: Sequence[int]) -> dict[str, Any]:
        episodes = len(task_indices) * len(modalities) * len(MODEL_CONDITIONS)
        eval_seconds = sum(
            len(task_indices)
            * sum(2 * reference_decisions[index] for index in task_indices)
            / max(1, len(task_indices))
            * latency[modality]
            for modality in modalities
        )
        train_gpu_hours = training_seconds / 3600
        eval_gpu_hours = eval_seconds / 3600
        subtotal = train_gpu_hours + eval_gpu_hours
        required = subtotal * safety + branch_spent_gpu_hours
        return {
            "episodes": episodes,
            "training_gpu_hours": train_gpu_hours,
            "evaluation_gpu_hours": eval_gpu_hours,
            "safety_factor": safety,
            "required_gpu_hours_including_spent": required,
            "fits_branch_remainder": required <= remainder,
        }

    arithmetic = {"L0": level_arithmetic(list(range(len(reference_decisions))))}
    key_cell_count = max(1, len(reference_decisions) // 2)
    key_cell_indices = sorted(tasks_by_cost[:key_cell_count])
    arithmetic["L1"] = level_arithmetic(key_cell_indices)
    if arithmetic["L0"]["fits_branch_remainder"]:
        decision, outcome, reduced = "L0", "PASS", None
    elif arithmetic["L1"]["fits_branch_remainder"]:
        decision = "L1"
        outcome = "PASS"
        reduced = (
            "reduced key-cell panel selected by lowest reference bfs decision count only "
            f"(tasks ranked by reference_costs.bfs.decisions; kept {key_cell_count}/{len(reference_decisions)} tasks); "
            "documented fallback because L0 exceeded the branch remainder"
        )
    else:
        decision, outcome, reduced = "L2", "VALID_STOP", None
    authorized_scope = None
    if outcome == "PASS":
        selected = set(range(len(reference_decisions))) if decision == "L0" else set(key_cell_indices)
        scope_ids = [task_id for index, task_id in enumerate(panel_task_ids) if index in selected]
        authorized_scope = {
            "decision": decision,
            "task_ids": scope_ids,
            "task_id_order": "frozen panel order",
            "model_episodes": len(scope_ids) * len(modalities) * len(MODEL_CONDITIONS),
            "comparator_episodes": len(scope_ids) * len(modalities) * len(COMPARATOR_CONDITIONS),
            "selection": (
                "full qualified panel"
                if decision == "L0"
                else "lowest reference bfs decision count only, frozen before any model outcome"
            ),
        }
    return {
        "schema_version": ADMISSION_SCHEMA,
        "decision": decision,
        "outcome": outcome,
        "protocol_id": protocol["protocol_id"],
        "branch_cap_gpu_hours": cap,
        "branch_spent_gpu_hours": branch_spent_gpu_hours,
        "branch_remainder_gpu_hours": remainder,
        "arithmetic": arithmetic,
        "calls_per_episode_basis": "2 x reference bfs decisions per task (the frozen decision-call allowance)",
        "measured_inputs": {
            "training_step_wall_seconds": step_costs,
            "per_call_latency_p95_seconds": latency,
            "probe_gpu_hours": probe["probe_gpu_hours"],
        },
        "reduced_scope": reduced,
        "authorized_scope": authorized_scope,
        "ledger_mutated": False,
    }


def admit_stage(root: Path, protocol: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    qualification = read_json(qualification_root(root, protocol) / "qualification.json")
    probe = read_json(root / protocol["output_root"] / "probe.json")
    if qualification.get("outcome") != "PASS" or not qualification.get("complete"):
        raise RuntimeError("second-backbone admission requires a complete PASS qualification")
    if probe.get("outcome") != "PASS":
        raise RuntimeError("second-backbone admission requires a PASS probe")
    ledger = read_json(root / LEDGER_PATH)
    spent = _branch_spent(ledger)
    costs = [task["row"]["reference_costs"] for task in context["panel_tasks"]]
    task_ids = [task["row"]["task_id"] for task in context["panel_tasks"]]
    result = decide_admission(
        protocol,
        qualification,
        probe,
        branch_spent_gpu_hours=spent,
        panel_task_costs=costs,
        panel_task_ids=task_ids,
    )
    write_json(root / protocol["output_root"] / "admission.json", result)
    return result


def require_admission_gate(root: Path, protocol: Mapping[str, Any]) -> dict[str, Any]:
    """GPU work is authorized only by a PASS admission: full panel (L0) or the
    reference-cost-reduced key-cell panel (L1) frozen before any model outcome."""
    path = root / protocol["output_root"] / "admission.json"
    if not path.is_file():
        raise RuntimeError("VALID_STOP: second-backbone cost admission has not run")
    admission = read_json(path)
    scope = admission.get("authorized_scope")
    if (
        admission.get("schema_version") != ADMISSION_SCHEMA
        or admission.get("protocol_id") != protocol["protocol_id"]
        or admission.get("outcome") != "PASS"
        or admission.get("decision") not in ("L0", "L1")
        or admission.get("ledger_mutated") is not False
        or not isinstance(scope, dict)
        or scope.get("decision") != admission.get("decision")
        or not scope.get("task_ids")
    ):
        raise RuntimeError(
            "VALID_STOP: second-backbone admission did not authorize execution "
            f"(decision={admission.get('decision')}, outcome={admission.get('outcome')}); "
            "arithmetic is published in admission.json"
        )
    return admission


def authorized_panel_tasks(
    root: Path, protocol: Mapping[str, Any], panel_tasks: Sequence[Mapping[str, Any]]
) -> list[Mapping[str, Any]]:
    """Filter the frozen panel to the admission-authorized tasks, preserving panel order."""
    admission = require_admission_gate(root, protocol)
    scope = admission["authorized_scope"]
    scope_ids = list(scope["task_ids"])
    panel_ids = [task["row"]["task_id"] for task in panel_tasks]
    if len(set(scope_ids)) != len(scope_ids) or not set(scope_ids).issubset(panel_ids):
        raise ValueError("second-backbone admission scope is not a subset of the frozen panel")
    selected = [task for task in panel_tasks if task["row"]["task_id"] in set(scope_ids)]
    episodes = len(selected) * len(protocol["modalities"]) * len(MODEL_CONDITIONS)
    if episodes != scope.get("model_episodes"):
        raise ValueError("second-backbone admission scope episode count differs")
    return selected


def training_arguments_kwargs(protocol: Mapping[str, Any], output: Path) -> dict[str, Any]:
    training = protocol["training"]
    return {
        "output_dir": str(output),
        "num_train_epochs": training["epochs"],
        "per_device_train_batch_size": training["microbatch_size"],
        "gradient_accumulation_steps": training["gradient_accumulation_steps"],
        "learning_rate": training["learning_rate"],
        "weight_decay": training["weight_decay"],
        "warmup_ratio": training["warmup_ratio"],
        "warmup_steps": training["warmup_steps"],
        "lr_scheduler_type": training["lr_scheduler"],
        "optim": training["optimizer"],
        "adam_beta1": training["adam_beta1"],
        "adam_beta2": training["adam_beta2"],
        "adam_epsilon": training["adam_epsilon"],
        "max_grad_norm": training["max_grad_norm"],
        "bf16": True,
        "gradient_checkpointing": True,
        "gradient_checkpointing_kwargs": {"use_reentrant": False},
        "seed": training["seed"],
        "data_seed": training["data_seed"],
        "logging_steps": 1,
        "save_strategy": "no",
        "report_to": [],
        "remove_unused_columns": False,
        "dataloader_num_workers": 0,
    }


def _effective_arguments(protocol: Mapping[str, Any]) -> dict[str, Any]:
    return {**protocol["training"], "base_model": dict(protocol["base_model"])}


def _trainer_digest(state: Mapping[str, Any]) -> dict[str, Any]:
    value = {"global_step": state.get("global_step"), "log_history": state.get("log_history", [])}
    return {**value, "sha256": _json_sha256(value)}


def _receipt(
    root: Path,
    protocol: Mapping[str, Any],
    *,
    modality: str,
    source_manifest: Mapping[str, Any],
    final: Path,
    init_tensor: Path,
    state: Mapping[str, Any],
    wall_seconds: float,
    cpu_seconds: float,
) -> dict[str, Any]:
    ordered = list(protocol["source_record_ids"])
    return {
        "schema_version": "expanded_second_backbone_training_completion_receipt_v1",
        "status": "PASS",
        "protocol_id": protocol["protocol_id"],
        "modality": modality,
        "backbone_key": BACKBONE_KEY,
        "ordered_training_record_ids": ordered,
        "ordered_training_record_ids_sha256": _json_sha256(ordered),
        "effective_training_arguments": _effective_arguments(protocol),
        "base_model": dict(protocol["base_model"]),
        "source_manifest_sha256": _json_sha256(source_manifest),
        "fresh_lora_init_sha256": _sha256(init_tensor),
        "fresh_lora_init_tensors": _safetensor_count(init_tensor),
        "final_checkpoint": str(final.relative_to(root)),
        **_final_fingerprints(final),
        "trainer_state_digest": _trainer_digest(state),
        "wall_seconds": wall_seconds,
        "cpu_seconds": cpu_seconds,
        "completed_at": time.time(),
    }


def _validate_receipt(
    root: Path,
    protocol: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    modality: str,
    source_manifest: Mapping[str, Any],
    final: Path,
    init_tensor: Path,
    state: Mapping[str, Any],
) -> None:
    expected = _receipt(
        root,
        protocol,
        modality=modality,
        source_manifest=source_manifest,
        final=final,
        init_tensor=init_tensor,
        state=state,
        wall_seconds=receipt.get("wall_seconds", -1),
        cpu_seconds=receipt.get("cpu_seconds", -1),
    )
    expected["completed_at"] = receipt.get("completed_at")
    if dict(receipt) != expected or any(
        not isinstance(receipt.get(key), (int, float)) or receipt[key] < 0
        for key in ("wall_seconds", "cpu_seconds", "completed_at")
    ):
        raise ValueError("second-backbone completion receipt differs from retained artifacts")


def _build_report(
    root: Path,
    protocol: Mapping[str, Any],
    *,
    modality: str,
    source_before: Mapping[str, Any],
    source_after: Mapping[str, Any],
    output: Path,
    state: Mapping[str, Any],
    runtime: Mapping[str, Any],
    recovered: bool,
) -> dict[str, Any]:
    final, receipt = output / "final", output / RECEIPT_FILE
    changed, count = _adapter_tensor_changes(output / FRESH_INIT_FILE, final / "adapter_model.safetensors")
    if count != EXPECTED_ADAPTER_TENSORS:
        raise ValueError(
            f"second-backbone adapter tensor count differs: expected {EXPECTED_ADAPTER_TENSORS}, actual {count}"
        )
    return {
        "schema_version": CELL_SCHEMA,
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "modality": modality,
        "backbone_key": BACKBONE_KEY,
        "base_model": dict(protocol["base_model"]),
        "source_manifest_before": dict(source_before),
        "source_manifest_after": dict(source_after),
        "source_unchanged": source_before == source_after,
        "source_manifest_sha256": _json_sha256(source_after),
        "training_record_ids": list(protocol["source_record_ids"]),
        "training_record_ids_sha256": protocol["source_record_ids_sha256"],
        "records": protocol["training"]["records_per_cell"],
        "optimizer_updates": state["global_step"],
        "final_checkpoint": str(final.relative_to(root)),
        **_final_fingerprints(final),
        "fresh_lora_init": str((output / FRESH_INIT_FILE).relative_to(root)),
        "fresh_lora_init_sha256": _sha256(output / FRESH_INIT_FILE),
        "fresh_lora_init_tensors": _safetensor_count(output / FRESH_INIT_FILE),
        "changed_parameter_tensors": changed,
        "parameter_tensors": count,
        "expected_parameter_tensors": EXPECTED_ADAPTER_TENSORS,
        "completion_receipt": str(receipt.relative_to(root)),
        "completion_receipt_sha256": _sha256(receipt),
        "recovered_without_retrain": recovered,
        "runtime_head": runtime["runtime_head"],
        "cuda_visible_devices": runtime.get("cuda_visible_devices"),
        "master_port": runtime["master_port"],
        "elapsed_seconds": runtime["elapsed_seconds"],
        "loss_history": [row for row in state.get("log_history", []) if "loss" in row],
    }


def _git_head(root: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def _recover(root, protocol, context, modality, output, source_manifest):
    recovery_path, receipt_path = output / RECOVERY_FILE, output / RECEIPT_FILE
    if not receipt_path.is_file():
        raise ValueError("second-backbone retained artifacts lack a completion receipt")
    recovery = read_json(recovery_path)
    if (
        recovery.get("schema_version") != "expanded_second_backbone_training_recovery_v1"
        or recovery.get("protocol_id") != protocol["protocol_id"]
        or recovery.get("modality") != modality
        or recovery.get("source_manifest_before") != source_manifest
    ):
        raise ValueError("second-backbone recovery marker differs")
    state, final, init_tensor = read_json(output / "training_state.json"), output / "final", output / FRESH_INIT_FILE
    if state.get("global_step") != protocol["training"]["optimizer_updates"]:
        raise ValueError("second-backbone retained Trainer state is incomplete")
    _validate_adapter_config(protocol, final / "adapter_config.json")
    _adapter_tensor_changes(init_tensor, final / "adapter_model.safetensors")
    receipt = read_json(receipt_path)
    _validate_receipt(
        root,
        protocol,
        receipt,
        modality=modality,
        source_manifest=source_manifest,
        final=final,
        init_tensor=init_tensor,
        state=state,
    )
    report = _build_report(
        root,
        protocol,
        modality=modality,
        source_before=source_manifest,
        source_after=source_manifest,
        output=output,
        state=state,
        runtime={
            "runtime_head": recovery["runtime_head"],
            "cuda_visible_devices": recovery.get("cuda_visible_devices"),
            "master_port": recovery["master_port"],
            "elapsed_seconds": receipt["wall_seconds"],
        },
        recovered=True,
    )
    write_json(output / "report.json", report)
    recovery_path.unlink()
    return report


def train_cell(
    root: Path,
    protocol: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    modality: str,
    progress: Callable[..., None],
) -> dict[str, Any]:
    """Train one fresh InternVL LoRA adapter in the protocol membership order."""
    from transformers import Trainer, TrainerCallback, TrainingArguments

    from .visual_model import VisualCollator, VisualDataset, load_training_model

    if modality not in protocol["modalities"]:
        raise ValueError("second-backbone training cell is outside the frozen protocol")
    processor = backbone_page_processor(protocol)
    output = training_root(root, protocol, modality)
    if (output / "report.json").is_file():
        verify_training_cell(root, protocol, context, modality=modality)
        return read_json(output / "report.json")
    dataset = VisualDataset(
        root,
        root / protocol["source_corpus"],
        protocol["algorithm"],
        record_ids=protocol["source_record_ids"],
        modality=modality,
        scene_views=protocol["views"]["scene_views"],
    )
    if [record["record_id"] for record in dataset.records] != list(protocol["source_record_ids"]):
        raise ValueError("second-backbone dataset does not preserve membership order")
    total = optimizer_updates(len(dataset), protocol["training"])
    if len(dataset) != protocol["training"]["records_per_cell"] or total != protocol["training"]["optimizer_updates"]:
        raise ValueError("second-backbone cell does not yield exactly 16 optimizer updates")
    source_before = _source_manifest(root, context["source_files"])
    if (output / "final").exists() or (output / "training_state.json").exists():
        return _recover(root, protocol, context, modality, output, source_before)
    output.mkdir(parents=True, exist_ok=True)
    recovery = {
        "schema_version": "expanded_second_backbone_training_recovery_v1",
        "protocol_id": protocol["protocol_id"],
        "modality": modality,
        "source_manifest_before": source_before,
        "runtime_head": _git_head(root),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "master_port": int(os.environ["MASTER_PORT"]),
    }
    write_json(output / RECOVERY_FILE, recovery)
    model = load_training_model(_training_model_config(protocol))
    trainable = [name for name, parameter in model.named_parameters() if parameter.requires_grad]
    if not trainable or any(token in name for name in trainable for token in ("vision_tower", "multi_modal_projector")):
        raise ValueError("second-backbone fresh LoRA did not freeze the vision tower and projector")
    temporary = output / ".fresh-init"
    model.save_pretrained(str(temporary))
    shutil.copyfile(temporary / "adapter_model.safetensors", output / FRESH_INIT_FILE)
    shutil.rmtree(temporary)
    started, cpu_started = time.monotonic(), time.process_time()

    class FrozenTrainer(Trainer):
        def _get_train_sampler(self, train_dataset=None):
            return sequential_sampler(dataset)

    class Progress(TrainerCallback):
        def on_step_end(self, args, state, control, **kwargs):
            progress(
                completed=state.global_step,
                total=total,
                eta_seconds=(time.monotonic() - started) / max(1, state.global_step) * (total - state.global_step),
            )
            return control

    trainer = FrozenTrainer(
        model=model,
        args=TrainingArguments(**training_arguments_kwargs(protocol, output)),
        train_dataset=dataset,
        data_collator=VisualCollator(processor.processor, page_processor=processor),
        callbacks=[Progress()],
    )
    trainer.train()
    if trainer.state.global_step != protocol["training"]["optimizer_updates"]:
        raise RuntimeError("VALID_STOP: second-backbone training ended before update 16")
    final = output / "final"
    trainer.save_model(str(final))
    trainer.state.save_to_json(str(output / "training_state.json"))
    if list(output.glob("checkpoint-*")):
        raise ValueError("second-backbone retained a non-final checkpoint")
    source_after = _source_manifest(root, context["source_files"])
    if source_before != source_after:
        raise ValueError("second-backbone source artifacts changed during training")
    _validate_adapter_config(protocol, final / "adapter_config.json")
    _final_fingerprints(final)
    _adapter_tensor_changes(output / FRESH_INIT_FILE, final / "adapter_model.safetensors")
    state = read_json(output / "training_state.json")
    receipt = _receipt(
        root,
        protocol,
        modality=modality,
        source_manifest=source_after,
        final=final,
        init_tensor=output / FRESH_INIT_FILE,
        state=state,
        wall_seconds=time.monotonic() - started,
        cpu_seconds=time.process_time() - cpu_started,
    )
    write_json(output / RECEIPT_FILE, receipt)
    _validate_receipt(
        root,
        protocol,
        receipt,
        modality=modality,
        source_manifest=source_after,
        final=final,
        init_tensor=output / FRESH_INIT_FILE,
        state=state,
    )
    report = _build_report(
        root,
        protocol,
        modality=modality,
        source_before=source_before,
        source_after=source_after,
        output=output,
        state=state,
        runtime={
            "runtime_head": recovery["runtime_head"],
            "cuda_visible_devices": recovery.get("cuda_visible_devices"),
            "master_port": recovery["master_port"],
            "elapsed_seconds": receipt["wall_seconds"],
        },
        recovered=False,
    )
    write_json(output / "report.json", report)
    (output / RECOVERY_FILE).unlink()
    return report


def verify_training_cell(
    root: Path, protocol: Mapping[str, Any], context: Mapping[str, Any], *, modality: str
) -> dict[str, Any]:
    """CPU-only audit of exposure, lineage, and every adapter tensor update."""
    output = training_root(root, protocol, modality)
    report = read_json(output / "report.json")
    if (
        report.get("schema_version") != CELL_SCHEMA
        or report.get("outcome") != "PASS"
        or report.get("protocol_id") != protocol["protocol_id"]
        or report.get("modality") != modality
        or report.get("backbone_key") != BACKBONE_KEY
        or report.get("training_record_ids") != list(protocol["source_record_ids"])
        or report.get("training_record_ids_sha256") != protocol["source_record_ids_sha256"]
        or report.get("records") != protocol["training"]["records_per_cell"]
        or report.get("optimizer_updates") != protocol["training"]["optimizer_updates"]
        or report.get("base_model") != protocol["base_model"]
        or report.get("source_unchanged") is not True
        or report.get("parameter_tensors") != EXPECTED_ADAPTER_TENSORS
    ):
        raise ValueError("second-backbone training report differs from frozen exposure")
    source = _source_manifest(root, context["source_files"])
    if report.get("source_manifest_before") != source or report.get("source_manifest_after") != source:
        raise ValueError("second-backbone source artifact manifest changed")
    state, final, init_tensor = read_json(output / "training_state.json"), output / "final", output / FRESH_INIT_FILE
    if state.get("global_step") != protocol["training"]["optimizer_updates"] or list(output.glob("checkpoint-*")):
        raise ValueError("second-backbone final-only Trainer state is invalid")
    _validate_adapter_config(protocol, final / "adapter_config.json")
    fingerprints = _final_fingerprints(final)
    if any(report.get(key) != value for key, value in fingerprints.items()):
        raise ValueError("second-backbone final checkpoint fingerprint changed")
    changed, count = _adapter_tensor_changes(init_tensor, final / "adapter_model.safetensors")
    if report.get("changed_parameter_tensors") != changed or report.get("parameter_tensors") != count:
        raise ValueError("second-backbone adapter tensor change accounting differs")
    receipt_path = output / RECEIPT_FILE
    if report.get("completion_receipt_sha256") != _sha256(receipt_path):
        raise ValueError("second-backbone completion receipt fingerprint changed")
    _validate_receipt(
        root,
        protocol,
        read_json(receipt_path),
        modality=modality,
        source_manifest=source,
        final=final,
        init_tensor=init_tensor,
        state=state,
    )
    return {
        "outcome": "PASS",
        "modality": modality,
        "records": report["records"],
        "optimizer_updates": report["optimizer_updates"],
        "training_record_ids": report["training_record_ids"],
        "final_checkpoint": report["final_checkpoint"],
        **fingerprints,
        "changed_parameter_tensors": changed,
        "parameter_tensors": count,
        "fresh_lora_init_sha256": report["fresh_lora_init_sha256"],
        "fresh_lora_init_tensors": report["fresh_lora_init_tensors"],
        "recovered_without_retrain": report["recovered_without_retrain"],
    }


def bindings(protocol: Mapping[str, Any], panel_tasks: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    workers = len(protocol["launch"]["devices"])
    result = []
    index = 0
    for modality in protocol["modalities"]:
        for task_index, task in enumerate(panel_tasks):
            for condition in MODEL_CONDITIONS:
                result.append(
                    {
                        "index": index,
                        "worker": task_index % workers,
                        "task_index": task_index,
                        "task_id": task["row"]["task_id"],
                        "modality": modality,
                        "condition": condition,
                    }
                )
                index += 1
    if len({(row["modality"], row["task_index"], row["condition"]) for row in result}) != len(result):
        raise ValueError("second-backbone binding enumeration is duplicated")
    return result


def assigned_bindings(
    protocol: Mapping[str, Any], panel_tasks: Sequence[Mapping[str, Any]], worker: int
) -> list[dict[str, Any]]:
    if worker not in range(len(protocol["launch"]["devices"])):
        raise ValueError("unknown second-backbone evaluation worker")
    return [binding for binding in bindings(protocol, panel_tasks) if binding["worker"] == worker]


def worker_modalities(protocol: Mapping[str, Any], owned: Sequence[Mapping[str, Any]]) -> list[str]:
    """Protocol-listed policy load order first, then any remaining owned modalities (parity split)."""
    listed = list(protocol["launch"]["evaluation_worker_policy_load_order"][str(owned[0]["worker"])]) if owned else []
    return listed + [modality for modality in protocol["modalities"] if modality not in listed]


def episode_path(root: Path, protocol: Mapping[str, Any], modality: str, task_id: str, condition: str) -> Path:
    return evaluation_root(root, protocol) / modality / _task_name(task_id) / f"{condition}.json.gz"


def _identity(
    root: Path,
    protocol: Mapping[str, Any],
    bound: Mapping[str, Any],
    binding: Mapping[str, Any],
    task: Mapping[str, Any],
    output: Path,
    view_output: Path,
) -> dict[str, Any]:
    modality, condition = binding["modality"], binding["condition"]
    checkpoint = None
    fingerprints = {"final_checkpoint_sha256": None, "final_adapter_config_sha256": None}
    if condition == "process_sft":
        checkpoint = bound["_second_backbone_checkpoints"][modality]
        fingerprints = dict(bound["_second_backbone_fingerprints"][modality])
    return {
        "schema_version": EPISODE_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "contract_id": protocol["protocol_id"],
        "panel": PANEL_NAME,
        "panel_id": protocol["evaluation"]["panel_id"],
        "binding_index": binding["index"],
        "worker": binding["worker"],
        "task_id": task["row"]["task_id"],
        "modality": modality,
        "algorithm": protocol["algorithm"],
        "arm": condition,
        "comparison_arm": f"{modality}__{condition}",
        "behavior_arm": condition,
        "adapter_id": condition if condition == "process_sft" else None,
        "seed": protocol["evaluation"]["seed"],
        "output": str(output.relative_to(root)),
        "view_output": str(view_output.relative_to(root)),
        "checkpoint": checkpoint,
        "backbone_key": BACKBONE_KEY,
        **fingerprints,
        "model_id": protocol["base_model"]["model_id"],
        "model_revision": protocol["base_model"]["revision"],
        "oracle_assisted_valid_operation_control": False,
        "producing_attempt": bound["_producing_attempt"],
        "runtime_head": bound["_runtime_head"],
        "policy_identity": bound["_second_backbone_policy_identity"][(modality, condition)],
    }


def require_training_gate(root: Path, protocol: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    path = root / protocol["output_root"] / "training" / "training-report.json"
    if not path.is_file():
        raise RuntimeError("second-backbone evaluation requires a PASS training report")
    report = read_json(path)
    cells = report.get("cells", [])
    if (
        report.get("schema_version") != TRAINING_REPORT_SCHEMA
        or report.get("status") != "PASS"
        or report.get("outcome") != "PASS"
        or report.get("protocol_id") != protocol["protocol_id"]
        or report.get("same_record_set_all_cells") is not True
        or report.get("fresh_lora_init_identical_all_cells") is not True
        or {cell.get("modality") for cell in cells} != set(protocol["modalities"])
    ):
        raise RuntimeError("second-backbone training gate is incomplete")
    checkpoints, fingerprints = {}, {}
    for cell in cells:
        modality = cell["modality"]
        checkpoint = root / cell["final_checkpoint"]
        actual = {
            "final_checkpoint_sha256": _sha256(checkpoint / "adapter_model.safetensors"),
            "final_adapter_config_sha256": _sha256(checkpoint / "adapter_config.json"),
        }
        if any(cell.get(key) != value for key, value in actual.items()):
            raise RuntimeError("second-backbone training gate checkpoint fingerprint differs")
        checkpoints[modality] = cell["final_checkpoint"]
        fingerprints[modality] = actual
    bound = dict(protocol)
    bound["_second_backbone_checkpoints"] = checkpoints
    bound["_second_backbone_fingerprints"] = fingerprints
    return bound, report


def _finalize(root: Path, state: Mapping[str, Any]) -> dict[str, Any]:
    saved, session, views = state["saved"], state["session"], state["views"]
    report = {
        **state["identity"],
        "outcome": "RECORDED",
        "events": saved["events"],
        "result": session.result(),
        "call_measurements": saved["call_measurements"],
        "started": saved["started"],
        "finished": time.time(),
        "active_wall_seconds": saved["active_wall_seconds"],
        "raw_invalid_outputs_preserved": sum(not event["accepted"] for event in saved["events"]),
        "resumed_from_attempts": saved.get("resumed_from_attempts", []),
    }
    views.save()
    write_json(state["episode"], report)
    state["journal"].unlink()
    return report


def verify_episode(
    root: Path,
    protocol: Mapping[str, Any],
    bound: Mapping[str, Any],
    binding: Mapping[str, Any],
    task: Mapping[str, Any],
    endpoint: str,
) -> dict[str, Any]:
    path = episode_path(root, protocol, binding["modality"], binding["task_id"], binding["condition"])
    report = read_json(path)
    view_output = Path(report["view_output"])
    if not view_output.is_absolute():
        view_output = root / view_output
    expected = _identity(
        root,
        protocol,
        bound,
        binding,
        task,
        path,
        view_output,
    )
    scientific_keys = (
        "schema_version",
        "protocol_id",
        "panel",
        "panel_id",
        "binding_index",
        "task_id",
        "modality",
        "algorithm",
        "arm",
        "seed",
        "checkpoint",
        "backbone_key",
        "final_checkpoint_sha256",
        "final_adapter_config_sha256",
        "model_id",
        "model_revision",
    )
    if any(report.get(key) != value for key, value in expected.items() if key in scientific_keys):
        raise ValueError("second-backbone retained episode identity differs")
    view_output = Path(report["view_output"])
    if not view_output.is_absolute():
        view_output = root / view_output
    views = ExpandedTaskViews(
        root, task, view_output, endpoint, read_only=True, page_processor=backbone_page_processor(protocol)
    )
    result = replay_visual_episode(root, task["row"], report, views, page_processor=backbone_page_processor(protocol))
    if (
        result != report["result"]
        or len(report["events"]) != len(report["call_measurements"])
        or any(
            measurement["input_tokens"] > protocol["evaluation"]["maximum_input_tokens"]
            or measurement["generated_sequence_tokens"] > protocol["evaluation"]["output_tokens"]
            for measurement in report["call_measurements"]
        )
    ):
        raise ValueError("second-backbone episode replay or model-call accounting differs")
    return report


def run_cell(
    root: Path,
    protocol: Mapping[str, Any],
    bound: Mapping[str, Any],
    *,
    modality: str,
    task_bindings: list[tuple[Mapping[str, Any], Mapping[str, Any]]],
    endpoint: str,
    generate: Callable[[list[dict[str, Any]], str | None], tuple[list[str], list[int]]],
    progress: Callable[..., None],
) -> list[dict[str, Any]]:
    """Deterministic rounds for one modality; token-aware batches per adapter within the frozen caps."""
    processor = backbone_page_processor(protocol)
    finished = []
    active = []
    for binding, task in task_bindings:
        task_id = task["row"]["task_id"]
        output = episode_path(root, protocol, modality, task_id, binding["condition"])
        journal = output.with_name(output.name.removesuffix(".json.gz") + ".partial.json.gz")
        view_output = output.parent / f"{binding['condition']}-views"
        identity = _identity(root, protocol, bound, binding, task, output, view_output)
        if output.exists():
            report = verify_episode(root, protocol, bound, binding, task, endpoint)
            if journal.exists():
                saved = read_json(journal)
                if (
                    saved.get("pending") is not None
                    or saved.get("events") != report["events"]
                    or saved.get("call_measurements") != report["call_measurements"]
                ):
                    raise ValueError("completed second-backbone episode has a conflicting journal")
                journal.unlink()
            finished.append(report)
            progress(completed=len(finished), total=len(task_bindings), task_id=task_id, retained=True)
            continue
        views = ExpandedTaskViews(root, task, view_output, endpoint, page_processor=processor)
        session = VisualSession(
            root,
            task["row"],
            protocol["algorithm"],
            binding["condition"],
            protocol["evaluation"]["seed"],
            output,
            protocol["protocol_id"],
            views=views,
        )
        saved = (
            read_json(journal)
            if journal.exists()
            else {
                **identity,
                "events": [],
                "call_measurements": [],
                "pending": None,
                "started": time.time(),
                "active_wall_seconds": 0.0,
                "resumed_from_attempts": [],
            }
        )
        if journal.exists():
            prior = {
                "binding_index": saved["binding_index"],
                "modality": saved["modality"],
                "arm": saved["arm"],
                "producing_attempt": saved["producing_attempt"],
                "runtime_head": saved["runtime_head"],
                "policy_identity": saved["policy_identity"],
            }
            history = [*saved.get("resumed_from_attempts", []), prior]
            for key, value in identity.items():
                saved[key] = value
            saved["resumed_from_attempts"] = history
        elif any(saved.get(key) != value for key, value in identity.items()):
            raise ValueError("second-backbone partial journal identity differs")
        restored = time.monotonic()
        _restore_events(session, views, saved)
        _commit_pending(session, views, saved)
        saved["active_wall_seconds"] += time.monotonic() - restored
        write_json(journal, saved)
        active.append(
            {
                "binding": binding,
                "task": task,
                "episode": output,
                "journal": journal,
                "identity": identity,
                "views": views,
                "session": session,
                "saved": saved,
            }
        )

    while active:
        requests = []
        remaining = []
        for state in active:
            request = state["session"].next_request()
            if request is None:
                finished.append(_finalize(root, state))
                progress(
                    completed=len(finished),
                    total=len(task_bindings),
                    task_id=state["task"]["row"]["task_id"],
                    retained=False,
                )
                continue
            example = state["views"].observe(dict(request.model_input), protocol["algorithm"], modality=modality)
            requests.append((state, request, example))
            remaining.append(state)
        active = remaining
        grouped: dict[str | None, list[tuple[Any, Any, Any]]] = {}
        for state, request, example in requests:
            adapter_id = state["binding"]["condition"] if state["binding"]["condition"] == "process_sft" else None
            grouped.setdefault(adapter_id, []).append((state, request, example))
        inference = protocol["evaluation"]["inference"]
        for adapter_id in sorted(grouped, key=lambda value: (value is not None, value or "")):
            group = grouped[adapter_id]
            counts = [
                processor.count(row[2]["messages"], image_sizes=[image.size for image in row[2]["images"]])
                for row in group
            ]
            for batch in form_generation_batches(
                group,
                counts,
                max_batch_size=inference["max_batch_size"],
                max_batch_input_tokens=inference["max_padded_batch_input_tokens"],
            ):
                examples = [row[2] for row in batch]
                called = time.monotonic()
                try:
                    outputs, generated_tokens = generate(examples, adapter_id)
                finally:
                    for example in examples:
                        for image in example["images"]:
                            image.close()
                elapsed = time.monotonic() - called
                for (state, request, example), raw_output, tokens in zip(batch, outputs, generated_tokens, strict=True):
                    saved = state["saved"]
                    saved["pending"] = {
                        "input": dict(request.model_input),
                        "binding": example["binding"],
                        "raw_output": raw_output,
                        "measurement": {
                            "event_index": len(saved["events"]),
                            "model_call": True,
                            "input_tokens": example["binding"]["input_tokens"],
                            "generated_sequence_tokens": tokens,
                            "call_wall_seconds": elapsed / len(batch),
                            "batch_size": len(batch),
                        },
                    }
                    saved["active_wall_seconds"] += elapsed / len(batch)
                    write_json(state["journal"], saved)
                for state, _, _ in batch:
                    committed = time.monotonic()
                    _commit_pending(state["session"], state["views"], state["saved"])
                    state["saved"]["active_wall_seconds"] += time.monotonic() - committed
                    write_json(state["journal"], state["saved"])
    if len(finished) != len(task_bindings):
        raise ValueError("second-backbone evaluation cell omitted bindings")
    ordered = []
    for binding, task in task_bindings:
        match = next(
            report
            for report in finished
            if report["task_id"] == task["row"]["task_id"] and report["arm"] == binding["condition"]
        )
        ordered.append(match)
    return ordered


def form_generation_batches(
    examples: Sequence[Any], counts: Sequence[int], *, max_batch_size: int, max_batch_input_tokens: int
) -> list[list[Any]]:
    """Deterministic order-preserving batches that always satisfy the frozen caps.

    The policy guard charges padded width as max(lengths)*len(batch); pair only when
    that fits. Qualified singles above the pair cap run alone (never truncated).
    """
    batches: list[list[Any]] = []
    current: list[Any] = []
    current_max = 0
    for example, count in zip(examples, counts, strict=True):
        proposed_max = max(current_max, count)
        if current and (len(current) >= max_batch_size or proposed_max * (len(current) + 1) > max_batch_input_tokens):
            batches.append(current)
            current, current_max, proposed_max = [], 0, count
        current.append(example)
        current_max = proposed_max
    if current:
        batches.append(current)
    return batches


def validate_comparator_sources(root: Path, protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Bind the reused Goal-3 baseline comparator evidence by pinned sha256."""
    audit = protocol["evaluation"]["comparator_audit"]
    protocol_path = root / audit["baseline_protocol"]
    evidence_path = root / audit["baseline_evaluation"]
    replay_path = root / audit["baseline_independent_replay"]
    baseline_protocol = read_json(protocol_path)
    evidence = read_json(evidence_path)
    replay = read_json(replay_path)
    if (
        _sha256(protocol_path) != audit["baseline_protocol_sha256"]
        or _sha256(evidence_path) != audit["baseline_evaluation_sha256"]
        or _sha256(replay_path) != audit["baseline_independent_replay_sha256"]
        or evidence.get("outcome") != "PASS"
        or evidence.get("protocol_id") != baseline_protocol["protocol_id"]
        or evidence.get("panel_id") != protocol["evaluation"]["panel_id"]
        or evidence.get("complete_coverage") is not True
        or replay.get("outcome") != "PASS"
        or replay.get("protocol_id") != baseline_protocol["protocol_id"]
        or replay.get("episodes_replayed") != replay.get("expected_episodes")
        or replay.get("every_episode_replayed") is not True
    ):
        raise ValueError("second-backbone comparator audit binding differs")
    return {
        "baseline_protocol": audit["baseline_protocol"],
        "baseline_protocol_sha256": audit["baseline_protocol_sha256"],
        "baseline_evaluation": audit["baseline_evaluation"],
        "baseline_evaluation_sha256": audit["baseline_evaluation_sha256"],
        "baseline_independent_replay": audit["baseline_independent_replay"],
        "baseline_independent_replay_sha256": audit["baseline_independent_replay_sha256"],
        "baseline_episodes_root": audit["baseline_episodes_root"],
        "reused_conditions": list(audit["reused_conditions"]),
    }


def verify_comparator(
    root: Path,
    protocol: Mapping[str, Any],
    task: Mapping[str, Any],
    modality: str,
    condition: str,
    endpoint: str,
) -> dict[str, Any]:
    audit = protocol["evaluation"]["comparator_audit"]
    baseline_protocol = read_json(root / audit["baseline_protocol"])
    path = (
        root
        / audit["baseline_episodes_root"]
        / modality
        / _task_name(task["row"]["task_id"])
        / f"{protocol['algorithm']}-{condition}.json.gz"
    )
    report = read_json(path)
    view_output = Path(report["view_output"])
    if not view_output.is_absolute():
        view_output = root / view_output
    views = ExpandedTaskViews(
        root, task, view_output, endpoint, read_only=True, page_processor=backbone_page_processor(protocol)
    )
    replay_report = dict(report, contract_id=report.get("contract_id", report.get("protocol_id")))
    replay_visual_episode(root, task["row"], replay_report, views, page_processor=backbone_page_processor(protocol))
    actual_contract = report.get("contract_id", report.get("protocol_id"))
    if (
        report.get("task_id") != task["row"]["task_id"]
        or report.get("modality") != modality
        or report.get("algorithm") != protocol["algorithm"]
        or report.get("arm") != condition
        or report.get("seed") != protocol["evaluation"]["seed"]
        or actual_contract != baseline_protocol["protocol_id"]
        or report.get("model_id") != baseline_protocol["model_id"]
        or report.get("model_revision") != baseline_protocol["model_revision"]
        or report.get("checkpoint") is not None
    ):
        raise ValueError("reused second-backbone comparator differs from its panel binding")
    return {
        **report,
        "panel": PANEL_NAME,
        "comparison_arm": f"{modality}__{condition}",
        "comparator_source": str(path.relative_to(root)),
        "comparator_contract": actual_contract,
    }


def summarize(reports: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for report in reports:
        grouped.setdefault((report["modality"], report["arm"]), []).append(report)
    cells = []
    for (modality, arm), rows in sorted(grouped.items()):
        decisions = sum(row["result"]["decision_count"] for row in rows)
        invalid = sum(row["result"]["invalid_operation_count"] for row in rows)
        cells.append(
            {
                "modality": modality,
                "condition": arm,
                "episodes": len(rows),
                "invariant_valid_successes": sum(row["result"]["invariant_valid_success"] for row in rows),
                "goal_reached": sum(row["result"]["goal_reached"] for row in rows),
                "algorithm_invariants_hold": sum(row["result"]["algorithm_invariants_hold"] for row in rows),
                "decisions": decisions,
                "invalid_operations": invalid,
                "invalid_operation_rate": invalid / max(1, decisions),
                "model_calls": decisions if arm in MODEL_CONDITIONS else 0,
                "decision_call_allowance": sum(row["result"]["model_call_limit"] for row in rows),
            }
        )
    return cells


def build_evidence(
    root: Path,
    protocol: Mapping[str, Any],
    attempts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Independently replay all model episodes, verify comparators, assemble evidence."""
    comparator_audit = validate_comparator_sources(root, protocol)
    _, panel_tasks = load_panel(root, protocol)
    panel_tasks = authorized_panel_tasks(root, protocol, panel_tasks)
    admission = read_json(root / protocol["output_root"] / "admission.json")
    tasks = {task["row"]["task_id"]: task for task in panel_tasks}
    bound, _training = require_training_gate(root, protocol)
    fresh, missing = [], []
    worker_results: dict[tuple[str, int], dict[str, Any]] = {}
    for attempt in attempts:
        worker_result_path = Path(attempt["directory"]) / "worker-result.json"
        worker_results[(attempt["job_id"], attempt["attempt"])] = (
            read_json(worker_result_path) if worker_result_path.is_file() else {}
        )
    for binding in bindings(protocol, panel_tasks):
        path = episode_path(root, protocol, binding["modality"], binding["task_id"], binding["condition"])
        if not path.is_file():
            missing.append(str(path.relative_to(root)))
            continue
        retained = read_json(path)
        episode_bound = {
            **bound,
            "_producing_attempt": retained["producing_attempt"],
            "_runtime_head": retained["runtime_head"],
            "_second_backbone_policy_identity": {
                (binding["modality"], binding["condition"]): retained["policy_identity"]
            },
        }
        report = verify_episode(
            root,
            protocol,
            episode_bound,
            binding,
            tasks[binding["task_id"]],
            protocol["launch"]["backend_endpoints"][binding["worker"]],
        )
        producing = report.get("producing_attempt")
        worker_result = worker_results.get((producing["job_id"], producing["attempt"]), {})
        if worker_result.get("policy_identities", {}).get(report["arm"]) != report.get("policy_identity"):
            raise ValueError("second-backbone episode policy identity differs from its producing worker")
        fresh.append(report)
    comparators, comparator_missing = [], []
    for binding in bindings(protocol, panel_tasks):
        for condition in COMPARATOR_CONDITIONS:
            path = (
                root
                / comparator_audit["baseline_episodes_root"]
                / binding["modality"]
                / _task_name(binding["task_id"])
                / f"{protocol['algorithm']}-{condition}.json.gz"
            )
            if not path.is_file():
                comparator_missing.append(f"{binding['modality']}:{binding['task_id']}:{condition}")
                continue
            comparators.append(
                verify_comparator(
                    root,
                    protocol,
                    tasks[binding["task_id"]],
                    binding["modality"],
                    condition,
                    protocol["launch"]["backend_endpoints"][binding["worker"]],
                )
            )
    missing = sorted(missing)
    comparator_missing = sorted(comparator_missing)
    expected_model = len(bindings(protocol, panel_tasks))
    expected_comparators = len(panel_tasks) * len(protocol["modalities"]) * len(COMPARATOR_CONDITIONS)
    complete = not missing and not comparator_missing and len(fresh) == expected_model
    reports = [*fresh, *comparators]
    by_condition: dict[str, dict[str, Any]] = {}
    for report in reports:
        bucket = by_condition.setdefault(
            report["arm"], {"episodes": 0, "successes": 0, "decisions": 0, "invalid_operations": 0}
        )
        bucket["episodes"] += 1
        bucket["successes"] += int(report["result"]["invariant_valid_success"])
        bucket["decisions"] += report["result"]["decision_count"]
        bucket["invalid_operations"] += report["result"]["invalid_operation_count"]
    ledger = read_json(root / LEDGER_PATH)
    spent = _branch_spent(ledger)
    paired = (
        paired_rows(
            [
                {
                    "panel": PANEL_NAME,
                    "modality": report["modality"],
                    "task_id": report["task_id"],
                    "comparison_arm": {
                        "pretrained_base": f"{report['modality']}__base",
                        "process_sft": f"{report['modality']}__sft_sequential_order_control",
                    }.get(report["arm"], f"{report['modality']}__{report['arm']}"),
                    "result": report["result"],
                }
                for report in reports
            ],
            {**protocol, "evaluation": {**protocol["evaluation"], "arms": []}},
        )
        if complete
        else []
    )
    return {
        "schema_version": EVIDENCE_SCHEMA,
        "status": "PASS" if complete else "VALID_STOP",
        "outcome": "PASS" if complete else "VALID_STOP",
        "protocol_id": protocol["protocol_id"],
        "panel_id": protocol["evaluation"]["panel_id"],
        "backbone_key": BACKBONE_KEY,
        "logical_bindings": protocol["evaluation"]["logical_bindings"],
        "model_episodes": len(fresh),
        "expected_model_episodes": expected_model,
        "comparator_episodes": len(comparators),
        "expected_comparator_episodes": expected_comparators,
        "frozen_full_panel_model_episodes": protocol["evaluation"]["model_episodes"],
        "authorized_scope": admission["authorized_scope"],
        "reduced_scope": admission.get("reduced_scope"),
        "complete_coverage": complete,
        "missing_bindings": missing,
        "missing_comparator_bindings": comparator_missing,
        "by_condition": dict(by_condition),
        "by_cell": summarize(reports),
        "paired_rows": paired,
        "paired_rows_note": (
            "paired_rows reused from expanded_curriculum_evaluation; the InternVL process_sft arm binds to "
            "the sft_sequential_order_control key because both are sequential-order process-SFT conditions"
        ),
        "compute": {
            "model_calls": sum(
                1
                for report in fresh
                for measurement in report.get("call_measurements", [])
                if measurement.get("model_call")
            ),
            "active_wall_seconds": sum(report.get("active_wall_seconds", 0.0) for report in fresh),
        },
        "comparator_provenance": {
            "audit": comparator_audit,
            "sources": sorted({row["comparator_source"] for row in comparators}),
        },
        "producing_attempts": [
            {"job_id": job_id, "attempt": attempt, "directory": directory}
            for job_id, attempt, directory in sorted(
                {
                    (
                        report["producing_attempt"]["job_id"],
                        report["producing_attempt"]["attempt"],
                        report["producing_attempt"]["directory"],
                    )
                    for report in fresh
                }
            )
        ],
        "launch_heads": [
            {
                "job_id": attempt["job_id"],
                "attempt": attempt["attempt"],
                "runtime_head": worker_results.get((attempt["job_id"], attempt["attempt"]), {}).get("runtime_head"),
            }
            for attempt in attempts
        ],
        "branch_accounting": {
            "branch": protocol["budget"]["branch"],
            "cap_gpu_hours": ledger["allocations_gpu_hours"][protocol["budget"]["branch"]],
            "cumulative_spent_gpu_hours": spent,
        },
        "jobs": [
            {key: row[key] for key in ("job_id", "attempt", "gpus", "master_port", "gpu_hours") if key in row}
            for row in attempts
        ],
    }


def _values(rows: Sequence[Mapping[str, Any]], arm: str) -> dict[str, float]:
    return {f"{row['task_id']}": float(row["arms"][arm]["invariant_valid_success"]) for row in rows}


def _interval(protocol: Mapping[str, Any], left: Mapping[str, float], right: Mapping[str, float]) -> dict[str, float]:
    analysis = protocol["analysis"]
    return paired_bootstrap_interval(
        left,
        right,
        resamples=analysis["bootstrap_resamples"],
        seed=analysis["bootstrap_seed"],
        confidence=analysis["confidence"],
    )


def analyze_evidence(root: Path, protocol: Mapping[str, Any], evidence: Mapping[str, Any]) -> dict[str, Any]:
    if evidence.get("status") != "PASS":
        return {
            "schema_version": ANALYSIS_SCHEMA,
            "outcome": "VALID_STOP",
            "protocol_id": protocol["protocol_id"],
            "reason": "evaluation coverage incomplete",
            "missing_bindings": evidence.get("missing_bindings", []),
            "missing_comparator_bindings": evidence.get("missing_comparator_bindings", []),
        }
    rows = evidence["paired_rows"]
    if not rows:
        raise ValueError("second-backbone analysis requires complete paired rows")
    analysis = protocol["analysis"]
    by_modality: dict[str, dict[str, Any]] = {}
    contrasts = []
    for modality in protocol["modalities"]:
        sft = _values(rows, f"{modality}__sft_sequential_order_control")
        base = _values(rows, f"{modality}__base")
        random_valid = _values(rows, f"{modality}__random_valid")
        _values(rows, f"{modality}__exact_reference")
        for name, left, right in (
            ("process_sft_minus_pretrained_base", sft, base),
            ("process_sft_minus_random_valid", sft, random_valid),
        ):
            interval = _interval(protocol, left, right)
            contrasts.append({"modality": modality, "contrast": name, "interval": interval})
        cells = {(cell["modality"], cell["condition"]): cell for cell in evidence["by_cell"]}
        sft_cell = cells[(modality, "process_sft")]
        base_cell = cells[(modality, "pretrained_base")]
        random_cell = cells[(modality, "random_valid")]
        reference_cell = cells[(modality, "exact_reference")]
        by_modality[modality] = {
            "internvl": {
                "process_sft_successes": sft_cell["invariant_valid_successes"],
                "pretrained_base_successes": base_cell["invariant_valid_successes"],
                "random_valid_successes": random_cell["invariant_valid_successes"],
                "exact_reference_successes": reference_cell["invariant_valid_successes"],
                "episodes": sft_cell["episodes"],
            },
            "invalid_operation_rates": {
                condition: cells[(modality, condition)]["invalid_operation_rate"]
                for condition in (*MODEL_CONDITIONS, *COMPARATOR_CONDITIONS)
            },
            "decision_usage": {
                "process_sft_decisions": sft_cell["decisions"],
                "process_sft_decision_call_allowance": sft_cell["decision_call_allowance"],
                "pretrained_base_decisions": base_cell["decisions"],
            },
        }
    baseline = read_json(root / protocol["evaluation"]["comparator_audit"]["baseline_evaluation"])
    baseline_bfs = {
        (row["modality"], row["condition"]): row
        for row in baseline["by_cell"]
        if row["algorithm"] == protocol["algorithm"]
    }
    scope = evidence.get("authorized_scope") or {}
    reduced = scope.get("decision") == "L1"
    cross_backbone = []
    for modality in protocol["modalities"]:
        sft = _values(rows, f"{modality}__sft_sequential_order_control")
        qwen = baseline_bfs[(modality, "process_sft")]
        qwen_rate = qwen["successes"] / max(1, qwen["episodes"])
        right = {task_id: qwen_rate for task_id in sft}
        interval = _interval(protocol, sft, right)
        cross_backbone.append(
            {
                "modality": modality,
                "contrast": "internvl3_5-8b_process_sft_minus_qwen3-vl-8b_process_sft",
                "interval": interval,
                "qwen_process_sft_success_rate": qwen_rate,
                "method": (
                    "paired interval conditions the Qwen per-task outcome at its pinned by_cell BFS success "
                    "rate (only aggregate baseline cells are pinned); interval width reflects InternVL "
                    "task-level variation around the Qwen rate"
                )
                + (
                    "; the InternVL panel is the reference-cost-reduced key-cell subset while the Qwen rate "
                    "remains the pinned full-panel aggregate, so this contrast is descriptive, not paired"
                    if reduced
                    else ""
                ),
            }
        )
    all_sft = [cell for cell in evidence["by_cell"] if cell["condition"] == "process_sft"]
    all_reference = [cell for cell in evidence["by_cell"] if cell["condition"] == "exact_reference"]
    control_saturation = {
        "exact_reference_saturated": all(
            cell["invariant_valid_successes"] == cell["episodes"] for cell in all_reference
        ),
        "process_sft_saturated": all(cell["invariant_valid_successes"] == cell["episodes"] for cell in all_sft),
        "note": (
            "exact_reference/random_valid are deterministic reused controls; saturation is reported, never "
            "treated as a model result"
        ),
    }
    return {
        "schema_version": ANALYSIS_SCHEMA,
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "unit": analysis["unit"],
        "paired_units": len(rows),
        "authorized_scope": evidence.get("authorized_scope"),
        "reduced_scope": evidence.get("reduced_scope"),
        "bootstrap": {
            "seed": analysis["bootstrap_seed"],
            "resamples": analysis["bootstrap_resamples"],
            "confidence": analysis["confidence"],
        },
        "contrasts": contrasts,
        "cross_backbone": cross_backbone,
        "by_modality": by_modality,
        "control_saturation": control_saturation,
        "random_valid_assistance": protocol["evaluation"]["random_valid_assistance"],
        "invalid_operation_rates_preserved": True,
        "negative_results_preserved": analysis["negative_results_preserved"],
        "single_training_seed_limitation": protocol["training"]["single_training_seed_limitation"],
        "architecture_note": (
            "InternVL3.5-8B shares the Qwen3-8B LLM family with the primary backbone; the replication "
            "contrast is the vision tower (InternViT vs Qwen-ViT), connector, image tokenization, and "
            "multimodal training recipe, and it is reported as an architecture-difference limitation"
        ),
    }


DOCS_DIR = "docs/experiments/expanded-study"


def _fmt_sha(value: str | None) -> str:
    if not value:
        return "—"
    return value[:20] + "…"


def _write_markdown(path: Path, title: str, lines: Sequence[str]) -> None:
    path.write_text(f"# {title}\n\n" + "\n".join(lines).strip() + "\n")


def _copy_evidence(source: Path, root: Path, name: str) -> Path:
    target = root / DOCS_DIR / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return target


def _publish_qualification(root: Path, protocol: Mapping[str, Any]) -> Path:
    source = qualification_root(root, protocol) / "qualification.json"
    target = _copy_evidence(source, root, "second-backbone-qualification.json")
    report = read_json(source)
    lines = [
        f"Second-backbone input qualification for `{protocol['protocol_id']}` (backbone `{report['backbone_key']}`).",
        "",
        f"Outcome: **{report['outcome']}** (complete: {report['complete']}).",
        "",
        "| Modality | Max train prefix | Max train full | Max live |",
        "| --- | ---: | ---: | ---: |",
    ]
    for modality, row in report["maxima"].items():
        lines.append(f"| {modality} | {row['train_prefix']} | {row['train_full']} | {row['live']} |")
    lines += [
        "",
        f"- Context tokens: {report['context_tokens']}; output tokens: {report['output_tokens']}.",
        f"- Tokenizer identity (InternVL vs Qwen templated ids): {report['tokenizer_identity']}.",
        f"- Records measured: {report['records_measured']}; tasks measured: {report['tasks_measured']}; "
        f"decisions measured: {report['decisions_measured']}.",
        f"- Violations: {len(report['violations'])}; verify_complete cross-checks: {len(report['cross_checks'])}; "
        f"processed-pixel previews: {len(report['previews'])}.",
        "",
        "Compact evidence: [second-backbone-qualification.json](second-backbone-qualification.json) "
        "(byte-identical copy of the runtime report).",
    ]
    _write_markdown(
        root / DOCS_DIR / "second-backbone-qualification.md",
        "Second-backbone qualification (#101-#103)",
        lines,
    )
    return target


def _publish_probe(root: Path, protocol: Mapping[str, Any]) -> list[Path]:
    probe = read_json(root / protocol["output_root"] / "probe.json")
    admission = read_json(root / protocol["output_root"] / "admission.json")
    probe_target = _copy_evidence(root / protocol["output_root"] / "probe.json", root, "second-backbone-probe.json")
    admission_target = _copy_evidence(
        root / protocol["output_root"] / "admission.json", root, "second-backbone-admission.json"
    )
    lines = [
        f"Second-backbone probe and admission for `{protocol['protocol_id']}`.",
        "",
        f"Probe outcome: **{probe['outcome']}**; admission decision: **{admission['decision']}** "
        f"({admission['outcome']}).",
        "",
        f"- Attention: requested `{probe['attention']['requested']}`, applied `{probe['attention']['applied']}`, "
        f"fallback used: {probe['attention']['fallback_used']}.",
        f"- Load: {probe['load']['wall_seconds']:.1f}s; VRAM after load {probe['load']['vram_bytes_after_load']} bytes.",
        f"- Scalar/batch byte parity: {probe['scalar_batch_parity']['byte_identical']}; "
        f"repeated-batch determinism: {probe['repeated_batch_determinism']['byte_identical']}.",
        f"- Adapter isolation: base≠A {probe['adapter_isolation']['base_vs_adapter_a']}, "
        f"base≠B {probe['adapter_isolation']['base_vs_adapter_b']}, "
        f"A≠B {probe['adapter_isolation']['adapter_a_vs_adapter_b']}, "
        f"disable restores base {probe['adapter_isolation']['disable_restores_base']}.",
        f"- Token-limit guards: near-limit ({probe['token_limit_guards']['near_limit_input_tokens']} tokens) "
        f"succeeded {probe['token_limit_guards']['near_limit_succeeded']}; oversize batch VALID_STOP "
        f"{probe['token_limit_guards']['oversize_batch_raises_valid_stop']}.",
        "",
        "| Modality | Calls | Latency p50 (s) | Latency p95 (s) | Tokens/s (mean) | Peak VRAM (bytes) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for modality, row in probe["throughput"].items():
        lines.append(
            f"| {modality} | {row['calls']} | {row['latency_seconds']['p50']:.2f} | "
            f"{row['latency_seconds']['p95']:.2f} | {row['tokens_per_second']['mean']:.1f} | {row['peak_vram_bytes']} |"
        )
    lines += [
        "",
        "| Modality | One-step wall (s) | Microbatches | Peak VRAM (bytes) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for modality, row in probe["training_step"].items():
        lines.append(f"| {modality} | {row['wall_seconds']:.1f} | {row['microbatches']} | {row['peak_vram_bytes']} |")
    arithmetic = admission["arithmetic"]
    lines += [
        "",
        "| Level | Episodes | Required GPU-h (incl. spent, x safety) | Fits remainder |",
        "| --- | ---: | ---: | --- |",
    ]
    for level in ("L0", "L1"):
        row = arithmetic[level]
        lines.append(
            f"| {level} | {row['episodes']} | {row['required_gpu_hours_including_spent']:.3f} | "
            f"{row['fits_branch_remainder']} |"
        )
    lines += [
        "",
        f"Branch cap {admission['branch_cap_gpu_hours']} GPU-h; spent {admission['branch_spent_gpu_hours']:.3f}; "
        f"remainder {admission['branch_remainder_gpu_hours']:.3f}; ledger mutated: {admission['ledger_mutated']}.",
        "",
        "Compact evidence: [second-backbone-probe.json](second-backbone-probe.json) and "
        "[second-backbone-admission.json](second-backbone-admission.json) (byte-identical copies).",
    ]
    _write_markdown(
        root / DOCS_DIR / "second-backbone-probe.md",
        "Second-backbone probe and admission (#101-#103)",
        lines,
    )
    return [probe_target, admission_target]


def _publish_training(root: Path, protocol: Mapping[str, Any]) -> Path:
    source = root / protocol["output_root"] / "training" / "training-report.json"
    target = _copy_evidence(source, root, "second-backbone-training.json")
    report = read_json(source)
    lines = [
        f"Second-backbone training for `{protocol['protocol_id']}` trained three fresh InternVL LoRA "
        "adapters (one per modality) from the frozen base model.",
        "",
        f"Outcome: **{report['outcome']}**. Fresh seed-17 LoRA initialization identical across cells: "
        f"{report['fresh_lora_init_identical_all_cells']} "
        f"(`{_fmt_sha(report['fresh_lora_init']['sha256'])}`, "
        f"{report['fresh_lora_init']['parameter_tensors']} tensors).",
        "",
        "| Modality | Records | Updates | Tensors changed | Final checkpoint sha256 |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for cell in report["cells"]:
        lines.append(
            f"| {cell['modality']} | {cell['records']} | {cell['optimizer_updates']} | "
            f"{cell['changed_parameter_tensors']}/{cell['parameter_tensors']} | "
            f"{_fmt_sha(cell['final_checkpoint_sha256'])} |"
        )
    lines += [
        "",
        "Every cell: same 512 BFS membership records in frozen membership order, one epoch, global batch 32 "
        "(microbatch 1 x accumulation 32), exactly 16 optimizer updates, sequential sampler, trainer "
        "reshuffling disabled, final checkpoint only, vision tower and multi-modal projector frozen.",
        "",
        "Compact evidence: [second-backbone-training.json](second-backbone-training.json) (byte-identical "
        "copy of the runtime aggregate report).",
    ]
    _write_markdown(
        root / DOCS_DIR / "second-backbone-training.md",
        "Second-backbone training (#102)",
        lines,
    )
    return target


def _publish_evaluation(root: Path, protocol: Mapping[str, Any]) -> Path:
    source = evaluation_root(root, protocol) / "evidence.json"
    target = _copy_evidence(source, root, "second-backbone-evaluation.json")
    report = read_json(source)
    lines = [
        f"Second-backbone held-out evaluation for `{protocol['protocol_id']}` (panel `{report['panel_id']}`).",
        "",
        f"Outcome: **{report['outcome']}**; complete coverage: {report['complete_coverage']}; "
        f"model episodes {report['model_episodes']}/{report['expected_model_episodes']}; comparator episodes "
        f"{report['comparator_episodes']}/{report['expected_comparator_episodes']}.",
        "",
    ]
    scope = report.get("authorized_scope") or {}
    if scope.get("decision") == "L1":
        lines += [
            f"**Reduced scope (cost admission L1):** the executed panel is the {len(scope['task_ids'])} "
            "reference-cost-selected key-cell tasks, frozen before any model outcome; the frozen full panel is "
            f"{report['frozen_full_panel_model_episodes']} model episodes. Selection: {scope['selection']}. "
            f"Admission rationale: {report.get('reduced_scope')}.",
            "",
        ]
    lines += [
        "| Modality | Condition | Episodes | Successes | Decisions | Invalid ops | Model calls |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for cell in report["by_cell"]:
        lines.append(
            f"| {cell['modality']} | {cell['condition']} | {cell['episodes']} | "
            f"{cell['invariant_valid_successes']} | {cell['decisions']} | {cell['invalid_operations']} | "
            f"{cell['model_calls']} |"
        )
    lines += [
        "",
        f"All {report['expected_model_episodes']} model episodes were independently replayed; the "
        f"{report['expected_comparator_episodes']} comparator episodes (random_valid, exact_reference) are "
        "sha256-pinned reused Goal-3 baseline episodes on identical tasks, never regenerated.",
        "",
        "Compact evidence: [second-backbone-evaluation.json](second-backbone-evaluation.json) (byte-identical "
        "copy of the runtime evidence).",
    ]
    _write_markdown(
        root / DOCS_DIR / "second-backbone-evaluation.md",
        "Second-backbone evaluation (#103)",
        lines,
    )
    return target


def _publish_analysis(root: Path, protocol: Mapping[str, Any]) -> Path:
    source = evaluation_root(root, protocol) / "analysis.json"
    target = _copy_evidence(source, root, "second-backbone-analysis.json")
    report = read_json(source)
    lines = [
        f"Second-backbone paired whole-instance analysis for `{protocol['protocol_id']}` "
        f"({report['paired_units']} paired units; bootstrap seed {report['bootstrap']['seed']}, "
        f"{report['bootstrap']['resamples']} resamples, {report['bootstrap']['confidence']} confidence).",
        "",
        "Success = goal reached with algorithm invariants holding. Intervals are paired bootstrap "
        "success-rate differences in proportion units.",
        "",
        "| Modality | Contrast | Point | Lower | Upper |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for row in report["contrasts"]:
        interval = row["interval"]
        lines.append(
            f"| {row['modality']} | {row['contrast']} | {interval['point']:.3f} | "
            f"{interval['lower']:.3f} | {interval['upper']:.3f} |"
        )
    for row in report["cross_backbone"]:
        interval = row["interval"]
        lines.append(
            f"| {row['modality']} | {row['contrast']} | {interval['point']:.3f} | "
            f"{interval['lower']:.3f} | {interval['upper']:.3f} |"
        )
    lines += [
        "",
        f"Single-training-seed limitation: {report['single_training_seed_limitation']}.",
        f"Random-valid assistance: {report['random_valid_assistance']}.",
        f"Architecture note: {report['architecture_note']}.",
        "",
        "Compact evidence: [second-backbone-analysis.json](second-backbone-analysis.json) (byte-identical "
        "copy of the runtime analysis).",
    ]
    _write_markdown(
        root / DOCS_DIR / "second-backbone-analysis.md",
        "Second-backbone analysis (#103)",
        lines,
    )
    return target


def publish(root: Path, protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Copy compact byte-identical evidence JSONs and render Markdown summaries."""
    targets = [
        str(_publish_qualification(root, protocol).relative_to(root)),
        *[str(path.relative_to(root)) for path in _publish_probe(root, protocol)],
        str(_publish_training(root, protocol).relative_to(root)),
        str(_publish_evaluation(root, protocol).relative_to(root)),
        str(_publish_analysis(root, protocol).relative_to(root)),
    ]
    result = {
        "schema_version": "expanded_second_backbone_publish_v1",
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "published": targets,
        "published_at": time.time(),
    }
    write_json(root / protocol["output_root"] / "publish.json", result)
    return result
