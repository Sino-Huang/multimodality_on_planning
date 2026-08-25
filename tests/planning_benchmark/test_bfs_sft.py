from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from examples.planning_benchmark_slice.bfs_phase import load_bfs_phase_gate
from examples.planning_benchmark_slice.bfs_sft import (
    build_ms_swift_sft_command,
    convert_bfs_corpus_to_ms_swift,
)
from scripts import run_bfs_sft

REPO_ROOT = Path(__file__).resolve().parents[2]
FREEZE = REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v1.json"
AUTHORIZATION = REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v1.json"
V3_FREEZE = REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v3.json"
V3_AUTHORIZATION = REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v3.json"
V6_FREEZE = REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v6.json"
V6_AUTHORIZATION = REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v6.json"


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


def _v3_release(tmp_path: Path) -> tuple[Path, object]:
    phase_gate = load_bfs_phase_gate(V3_FREEZE, V3_AUTHORIZATION)
    root = tmp_path / "v3-release"
    rows = []
    for index, split in enumerate(("train", "dev")):
        rows.append(
            {
                "algorithm": "bfs",
                "difficulty": "easy",
                "domain_id": "blocksworld",
                "input": {
                    "goal_atoms": ["on(a,b)"],
                    "observation": {"state_id": f"state-{index}"},
                    "search_memory": {"accepted_deltas": []},
                },
                "instance_id": f"blocksworld-{split}-{index}",
                "record_id": f"record-{split}-{index}",
                "schema_version": "bfs_process_corpus_record_v3",
                "split": split,
                "split_assignment_id": f"assignment-{split}-{index}",
                "target": {
                    "canonical_rationale": {"rule": "fifo_frontier_head"},
                    "runtime_result": None,
                    "typed_operation": {"kind": "expand", "state_id": f"state-{index}"},
                },
                "trace_record_index": index,
                "view": "process",
                "whole_instance_id": f"instance-{split}-{index}",
            }
        )
    process = b"".join(_canonical_bytes(row) for row in rows)
    process_path = root / "corpus" / "process.jsonl"
    process_path.parent.mkdir(parents=True)
    process_path.write_bytes(process)
    manifest = {
        "artifacts": [
            {
                "path": "corpus/process.jsonl",
                "size_bytes": len(process),
            }
        ],
        "phase_receipt": phase_gate.receipt(stage="corpus_release"),
        "schema_version": "bfs_process_corpus_release_v3",
        "views": ["process"],
    }
    manifest_path = root / "manifests" / "bfs-text-corpus.json"
    manifest_path.parent.mkdir(parents=True)
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
    assert arguments["--logging_strategy"] == "steps"
    assert arguments["--logging_steps"] == "1"
    assert arguments["--disable_tqdm"] == "false"


def test_single_gpu_parallel_seed_command_preserves_the_frozen_global_batch(tmp_path: Path) -> None:
    dataset_root = tmp_path / "converted"
    for split in ("train", "dev"):
        path = dataset_root / "data" / f"{split}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
    phase_gate = load_bfs_phase_gate(V3_FREEZE, V3_AUTHORIZATION)

    command = build_ms_swift_sft_command(
        dataset_root=dataset_root,
        output_root=tmp_path / "checkpoint",
        phase_gate=phase_gate,
        seed=17,
        world_size=1,
    )
    arguments = dict(zip(command[2::2], command[3::2], strict=True))

    assert arguments["--per_device_train_batch_size"] == "1"
    assert arguments["--gradient_accumulation_steps"] == "32"


def test_v3_projects_only_null_result_process_targets_byte_identically(tmp_path: Path) -> None:
    corpus_root, phase_gate = _v3_release(tmp_path)
    first_root = tmp_path / "first-projection"
    second_root = tmp_path / "second-projection"

    first_manifest = convert_bfs_corpus_to_ms_swift(
        corpus_root=corpus_root,
        output_root=first_root,
        phase_gate=phase_gate,
        view="process",
    )
    convert_bfs_corpus_to_ms_swift(
        corpus_root=corpus_root,
        output_root=second_root,
        phase_gate=phase_gate,
        view="process",
    )

    assert {
        path.relative_to(first_root).as_posix(): path.read_bytes() for path in first_root.rglob("*") if path.is_file()
    } == {
        path.relative_to(second_root).as_posix(): path.read_bytes() for path in second_root.rglob("*") if path.is_file()
    }
    manifest = json.loads(first_manifest.read_bytes())
    assert manifest["schema_version"] == "bfs_process_ms_swift_conversion_v3"
    assert manifest["view"] == "process"
    for split in ("train", "dev"):
        row = json.loads((first_root / "data" / f"{split}.jsonl").read_text(encoding="utf-8"))
        target = json.loads(row["messages"][2]["content"])
        assert set(target) == {"canonical_rationale", "runtime_result", "typed_operation"}
        assert target["runtime_result"] is None

    with pytest.raises(ValueError, match="only the process corpus"):
        convert_bfs_corpus_to_ms_swift(
            corpus_root=corpus_root,
            output_root=tmp_path / "forbidden-operational",
            phase_gate=phase_gate,
            view="operational",
        )


def test_v3_training_dry_run_validates_and_prints_without_starting_training(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus_root, phase_gate = _v3_release(tmp_path)
    dataset_root = tmp_path / "projection"
    convert_bfs_corpus_to_ms_swift(
        corpus_root=corpus_root,
        output_root=dataset_root,
        phase_gate=phase_gate,
        view="process",
    )
    output_root = tmp_path / "training"
    monkeypatch.setattr(run_bfs_sft, "_validate_v3_reference_gate", lambda *_args: None)

    assert (
        run_bfs_sft.main(
            [
                "--phase",
                "v3",
                "--dataset-root",
                str(dataset_root),
                "--output-root",
                str(output_root),
                "--view",
                "process",
                "--seed",
                "17",
                "--world-size",
                "2",
                "--devices",
                "0,1",
                "--attempt-id",
                "issue-54-test-dry-run",
                "--dry-run",
            ]
        )
        == 0
    )

    plan = json.loads(capsys.readouterr().out)
    assert plan["dry_run"] is True
    assert plan["estimated_optimizer_steps"] == 3
    assert plan["environment"]["MASTER_PORT"] == "29500"
    assert plan["phase_receipt"]["phase_id"] == "issue-111-bfs-expansion-qualified-pilot-v3"
    assert not output_root.exists()


def test_v6_training_accepts_the_observable_ms_swift_projection(tmp_path: Path) -> None:
    phase_gate = load_bfs_phase_gate(V6_FREEZE, V6_AUTHORIZATION)
    dataset_root = tmp_path / "projection"
    dataset_root.mkdir()
    manifest = {
        "counts": {"dev": 12115, "train": 12994},
        "framework": {"name": "ms-swift", "version": "4.2.2"},
        "phase_receipt": phase_gate.receipt(stage="process_sft_and_sanity_gate"),
        "schema_version": "bfs_process_ms_swift_conversion_v5",
        "view": "process",
    }
    (dataset_root / "manifest.json").write_bytes(_canonical_bytes(manifest))

    assert run_bfs_sft._validate_conversion(
        dataset_root,
        phase_gate.receipt(stage="process_sft_and_sanity_gate"),
        "process",
    ) == manifest


def test_training_progress_parser_reads_the_latest_expected_tqdm_step(tmp_path: Path) -> None:
    log = tmp_path / "training.log"
    log.write_text("noise 1/2\r 25%|step| 3/12\r 50%|step| 6/12\n", encoding="utf-8")

    assert run_bfs_sft._latest_completed_step(log, 12) == 6


def test_training_output_is_teed_byte_for_byte_to_log_and_terminal() -> None:
    source = io.BytesIO(b"loading model\n1/1260 [00:02<41:58]\n")
    log = io.BytesIO()
    terminal = io.BytesIO()

    run_bfs_sft._tee_output(source, log, terminal)

    assert log.getvalue() == source.getvalue()
    assert terminal.getvalue() == source.getvalue()
