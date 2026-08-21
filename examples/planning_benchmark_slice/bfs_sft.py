"""Convert governed BFS corpus views into explicit ms-swift messages datasets."""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .bfs_phase import BFSPhaseGate
from .qwen_text_policy import QWEN_TEXT_POLICY_SYSTEM_PROMPT

_RELEASE_SCHEMA = "bfs_text_corpus_release_v1"
_CONVERSION_SCHEMA = "bfs_ms_swift_conversion_v1"
_RELEASE_SCHEMA_V3 = "bfs_process_corpus_release_v3"
_CONVERSION_SCHEMA_V3 = "bfs_process_ms_swift_conversion_v3"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROCESS_INPUT_FIELDS = {"goal_atoms", "observation", "search_memory"}
_PROCESS_TARGET_FIELDS = {"canonical_rationale", "runtime_result", "typed_operation"}
_OPERATIONAL_INPUT_FIELDS = {"goal_atoms", "source_state"}
_OPERATIONAL_TARGET_FIELDS = {"action", "target_state", "validity"}
_OPERATIONAL_SYSTEM_PROMPT = """You are the operational-only planning control.
Given only a goal and source state, return exactly one JSON object with action, target_state, and validity.
Do not emit frontier, visited, search-memory, rationale, heuristic, or other search-process fields.
Do not use Markdown fences or add text outside the JSON object."""


def build_ms_swift_sft_command(
    *,
    dataset_root: str | Path,
    output_root: str | Path,
    phase_gate: BFSPhaseGate,
    seed: int,
    world_size: int,
    smoke: bool = False,
) -> list[str]:
    """Translate the frozen optimizer contract into explicit ms-swift flags."""

    if seed not in phase_gate.freeze["seeds"]:
        raise ValueError(f"BFS SFT seed is not frozen: {seed}")
    if isinstance(world_size, bool) or not isinstance(world_size, int) or world_size <= 0:
        raise ValueError("world_size must be a positive integer")
    data_root = Path(dataset_root).resolve()
    train_dataset = data_root / "data" / "train.jsonl"
    dev_dataset = data_root / "data" / "dev.jsonl"
    if not train_dataset.is_file() or not dev_dataset.is_file():
        raise ValueError("ms-swift conversion must contain train and dev datasets")
    optimization = phase_gate.freeze["training"]["optimization"]
    lora = phase_gate.freeze["training"]["lora"]
    global_batch_size = optimization["global_batch_size"]
    if global_batch_size % world_size:
        raise ValueError("frozen global batch size must be divisible by world_size")
    gradient_accumulation_steps = global_batch_size // world_size
    model = phase_gate.freeze["models"]["primary"]
    command = [
        "swift",
        "sft",
        "--tuner_backend",
        "peft",
        "--tuner_type",
        "lora",
        "--model",
        model["model_id"],
        "--model_revision",
        model["revision"],
        "--use_hf",
        "true",
        "--dataset",
        str(train_dataset),
        "--val_dataset",
        str(dev_dataset),
        "--split_dataset_ratio",
        "0",
        "--target_modules",
        lora["target_modules"],
        "--lora_rank",
        str(lora["rank"]),
        "--lora_alpha",
        str(lora["alpha"]),
        "--lora_dropout",
        str(lora["dropout"]),
        "--lora_bias",
        lora["bias"],
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
        str(gradient_accumulation_steps),
        "--learning_rate",
        str(optimization["learning_rate"]),
        "--lr_scheduler_type",
        optimization["lr_scheduler"],
        "--warmup_ratio",
        str(optimization["warmup_ratio"]),
        "--max_grad_norm",
        str(optimization["max_gradient_norm"]),
        "--weight_decay",
        str(optimization["weight_decay"]),
        "--optim",
        optimization["optimizer"],
        "--bf16",
        str(optimization["bf16"]).lower(),
        "--gradient_checkpointing",
        str(optimization["gradient_checkpointing"]).lower(),
        "--max_length",
        str(phase_gate.freeze["budgets"]["max_context_tokens"]),
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
        command.extend(
            [
                "--max_steps",
                "1",
                "--eval_strategy",
                "no",
                "--save_strategy",
                "steps",
                "--save_steps",
                "1",
                "--logging_steps",
                "1",
            ]
        )
    return command


def convert_bfs_corpus_to_ms_swift(
    *,
    corpus_root: str | Path,
    output_root: str | Path,
    phase_gate: BFSPhaseGate,
    view: str,
) -> Path:
    """Create train/dev messages files and a source-bound sidecar manifest."""

    if view not in {"operational", "process"}:
        raise ValueError("BFS SFT view must be 'operational' or 'process'")
    is_v3 = phase_gate.freeze["schema_version"] == "bfs_phase_freeze_v3"
    if is_v3 and view != "process":
        raise ValueError("BFS v3 authorizes only the process corpus projection")
    stage = "operational_sft" if view == "operational" else "process_sft_and_sanity_gate"
    phase_gate.require_run(stage=stage, contract_id=phase_gate.phase_id)
    source_root = Path(corpus_root).resolve()
    destination = Path(output_root).resolve()
    if destination.exists():
        raise FileExistsError(f"ms-swift conversion output already exists: {destination}")

    release_manifest_path = source_root / "manifests" / "bfs-text-corpus-release.json"
    if is_v3:
        release_manifest_path = source_root / "manifests" / "bfs-text-corpus.json"
    release_manifest_bytes = release_manifest_path.read_bytes()
    release_manifest = _json_object(release_manifest_bytes, "BFS corpus release manifest")
    if (
        release_manifest.get("schema_version") != (_RELEASE_SCHEMA_V3 if is_v3 else _RELEASE_SCHEMA)
        or release_manifest.get("phase_receipt") != phase_gate.receipt(stage="corpus_release")
        or release_manifest.get("views") != (["process"] if is_v3 else ["operational", "process"])
    ):
        raise ValueError("BFS corpus release does not match the frozen phase")
    artifacts = _verified_artifacts(source_root, release_manifest)
    source_path = f"corpus/{view}.jsonl"
    source_bytes = artifacts.get(source_path)
    if source_bytes is None:
        raise ValueError(f"BFS corpus release is missing {source_path}")

    rows = _jsonl_objects(source_bytes, f"BFS {view} corpus")
    converted: dict[str, list[dict[str, Any]]] = {"dev": [], "train": []}
    metadata: list[dict[str, Any]] = []
    system_prompt = _OPERATIONAL_SYSTEM_PROMPT if view == "operational" else QWEN_TEXT_POLICY_SYSTEM_PROMPT
    for row in rows:
        _validate_source_row(row, view=view, is_v3=is_v3)
        split = row["split"]
        converted[split].append(
            {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": _canonical_text(row["input"])},
                    {"role": "assistant", "content": _canonical_text(row["target"])},
                ]
            }
        )
        metadata.append(
            {
                "difficulty": row["difficulty"],
                "domain_id": row["domain_id"],
                "instance_id": row["instance_id"],
                "record_id": row["record_id"],
                "split": split,
                "split_assignment_id": row["split_assignment_id"],
                "whole_instance_id": row["whole_instance_id"],
            }
        )
    if not converted["train"] or not converted["dev"]:
        raise ValueError("BFS SFT conversion requires non-empty frozen train and dev splits")

    payloads = {
        "data/dev.jsonl": _jsonl_bytes(converted["dev"]),
        "data/train.jsonl": _jsonl_bytes(converted["train"]),
        "metadata/source-records.jsonl": _jsonl_bytes(metadata),
    }
    conversion_manifest = {
        "artifacts": [
            {"path": path, "size_bytes": len(payload)}
            for path, payload in sorted(payloads.items())
        ],
        "counts": {split: len(converted[split]) for split in ("train", "dev")},
        "framework": {"name": "ms-swift", "version": "4.2.2"},
        "phase_receipt": phase_gate.receipt(stage=stage),
        "schema_version": _CONVERSION_SCHEMA_V3 if is_v3 else _CONVERSION_SCHEMA,
        "source": {
            "manifest_path": _stable_path(release_manifest_path) if is_v3 else str(release_manifest_path),
        },
        "view": view,
    }
    payloads["manifest.json"] = _canonical_bytes(conversion_manifest)

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        for relative_path, payload in payloads.items():
            path = staging / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        staging.replace(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination / "manifest.json"


def _verified_artifacts(root: Path, manifest: Mapping[str, Any]) -> dict[str, bytes]:
    entries = manifest.get("artifacts")
    if not isinstance(entries, list):
        raise ValueError("BFS corpus release artifacts must be a list")
    artifacts: dict[str, bytes] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "size_bytes"}:
            raise ValueError("BFS corpus artifact entry is malformed")
        relative_path = Path(entry["path"])
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("BFS corpus artifact path escapes its release")
        payload = (root / relative_path).read_bytes()
        if len(payload) != entry["size_bytes"]:
            raise ValueError(f"BFS corpus artifact differs from its release manifest: {relative_path}")
        artifacts[relative_path.as_posix()] = payload
    return artifacts


def _validate_source_row(row: Mapping[str, Any], *, view: str, is_v3: bool = False) -> None:
    required_metadata = {
        "algorithm",
        "difficulty",
        "domain_id",
        "input",
        "instance_id",
        "record_id",
        "schema_version",
        "split",
        "split_assignment_id",
        "target",
        "trace_record_index",
        "view",
        "whole_instance_id",
    }
    if set(row) != required_metadata or row.get("algorithm") != "bfs" or row.get("view") != view:
        raise ValueError(f"BFS {view} source row is malformed")
    if row.get("split") not in {"train", "dev"}:
        raise ValueError("BFS SFT conversion cannot read held-out or unknown splits")
    input_fields = _OPERATIONAL_INPUT_FIELDS if view == "operational" else _PROCESS_INPUT_FIELDS
    target_fields = _OPERATIONAL_TARGET_FIELDS if view == "operational" else _PROCESS_TARGET_FIELDS
    if not isinstance(row.get("input"), dict) or set(row["input"]) != input_fields:
        raise ValueError(f"BFS {view} input fields are invalid")
    if not isinstance(row.get("target"), dict) or set(row["target"]) != target_fields:
        raise ValueError(f"BFS {view} target fields are invalid")
    if is_v3 and (
        row.get("schema_version") != "bfs_process_corpus_record_v3" or row["target"]["runtime_result"] is not None
    ):
        raise ValueError("BFS v3 process target must keep runtime_result null")


def _stable_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def _jsonl_objects(payload: bytes, name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(payload.decode("utf-8").splitlines(), start=1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{name} has invalid JSON at line {line_number}") from error
        if not isinstance(value, dict):
            raise ValueError(f"{name} row must be an object at line {line_number}")
        rows.append(value)
    return rows


def _json_object(payload: bytes, name: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{name} is invalid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _canonical_text(value: object) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _canonical_bytes(value: object) -> bytes:
    return (_canonical_text(value) + "\n").encode("utf-8")


def _jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(_canonical_bytes(row) for row in rows)


__all__ = ["build_ms_swift_sft_command", "convert_bfs_corpus_to_ms_swift"]
