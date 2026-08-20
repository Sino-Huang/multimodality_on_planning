from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from examples.planning_benchmark_slice.bfs_phase import load_bfs_phase_gate
from examples.planning_benchmark_slice.bfs_sft import (
    build_ms_swift_sft_command,
    convert_bfs_corpus_to_ms_swift,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FREEZE = REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v1.json"
AUTHORIZATION = REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v1.json"


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _row(split: str, index: int) -> dict[str, object]:
    return {
        "algorithm": "bfs",
        "difficulty": "easy",
        "domain_id": "blocksworld",
        "input": {
            "goal_atoms": ["on(a,b)"],
            "source_state": {"atoms": ["clear(a)"], "authority_id": "authority", "fluents": [], "state_id": "s"},
        },
        "instance_id": f"blocksworld-{split}-{index}",
        "record_id": f"record-{split}-{index}",
        "schema_version": "bfs_text_corpus_record_v1",
        "source_record_hash": "a" * 64,
        "split": split,
        "split_assignment_id": f"assignment-{split}-{index}",
        "target": {
            "action": {"args": ["a"], "name": "pickup"},
            "target_state": {"atoms": ["holding(a)"], "authority_id": "authority", "fluents": [], "state_id": "t"},
            "validity": "accepted",
        },
        "trace_record_index": index,
        "view": "operational",
        "whole_instance_id": f"instance-{split}-{index}",
    }


def _release(tmp_path: Path, splits: tuple[str, ...]) -> tuple[Path, object]:
    phase_gate = load_bfs_phase_gate(FREEZE, AUTHORIZATION)
    root = tmp_path / "release"
    operational = b"".join(_canonical_bytes(_row(split, index)) for index, split in enumerate(splits))
    process = b""
    payloads = {
        "corpus/operational.jsonl": operational,
        "corpus/process.jsonl": process,
    }
    for relative_path, payload in payloads.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    manifest = {
        "artifacts": [
            {
                "path": path,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
            }
            for path, payload in sorted(payloads.items())
        ],
        "phase_receipt": phase_gate.receipt(stage="corpus_release"),
        "schema_version": "bfs_text_corpus_release_v1",
        "views": ["operational", "process"],
    }
    manifest_path = root / "manifests" / "bfs-text-corpus-release.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(_canonical_bytes(manifest))
    return root, phase_gate


def test_converts_only_operational_fields_to_source_bound_ms_swift_messages(tmp_path: Path) -> None:
    corpus_root, phase_gate = _release(tmp_path, ("train", "dev"))
    output_root = tmp_path / "converted"

    manifest_path = convert_bfs_corpus_to_ms_swift(
        corpus_root=corpus_root,
        output_root=output_root,
        phase_gate=phase_gate,
        view="operational",
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["counts"] == {"dev": 1, "train": 1}
    assert manifest["framework"] == {"name": "ms-swift", "version": "4.2.2"}
    train = json.loads((output_root / "data" / "train.jsonl").read_text(encoding="utf-8"))
    assert [message["role"] for message in train["messages"]] == ["system", "user", "assistant"]
    assert set(json.loads(train["messages"][1]["content"])) == {"goal_atoms", "source_state"}
    assert set(json.loads(train["messages"][2]["content"])) == {"action", "target_state", "validity"}
    assert "search-memory" in train["messages"][0]["content"]


def test_refuses_a_release_without_both_frozen_training_and_development_splits(tmp_path: Path) -> None:
    corpus_root, phase_gate = _release(tmp_path, ("dev",))
    output_root = tmp_path / "converted"

    with pytest.raises(ValueError, match="non-empty frozen train and dev"):
        convert_bfs_corpus_to_ms_swift(
            corpus_root=corpus_root,
            output_root=output_root,
            phase_gate=phase_gate,
            view="operational",
        )

    assert not output_root.exists()


def test_builds_explicit_frozen_two_gpu_ms_swift_lora_command(tmp_path: Path) -> None:
    dataset_root = tmp_path / "converted"
    for split in ("train", "dev"):
        path = dataset_root / "data" / f"{split}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
    phase_gate = load_bfs_phase_gate(FREEZE, AUTHORIZATION)

    command = build_ms_swift_sft_command(
        dataset_root=dataset_root,
        output_root=tmp_path / "checkpoint",
        phase_gate=phase_gate,
        seed=17,
        world_size=2,
    )
    arguments = dict(zip(command[2::2], command[3::2], strict=True))

    assert command[:2] == ["swift", "sft"]
    assert arguments["--model"] == "Qwen/Qwen3-VL-8B-Instruct"
    assert arguments["--model_revision"] == "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"
    assert arguments["--lora_rank"] == "64"
    assert arguments["--lora_alpha"] == "128"
    assert arguments["--target_modules"] == "all-linear"
    assert arguments["--gradient_accumulation_steps"] == "16"
    assert arguments["--learning_rate"] == "0.0001"
    assert arguments["--max_length"] == "4096"
    assert arguments["--seed"] == arguments["--data_seed"] == "17"
    assert arguments["--full_determinism"] == "true"
    assert arguments["--train_dataloader_shuffle"] == "false"
