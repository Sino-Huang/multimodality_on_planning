from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, NoReturn

import pytest

from scripts.phase3.cgas_qwenvl_contracts import (
    JsonRecord,
    QwenContractError,
    build_manifest,
    canonical_json,
    convert_steps,
    validate_manifest,
    validate_records,
)


Mutation = Literal[
    "extra_top_level",
    "second_image",
    "extra_token",
    "assistant_media",
    "denied_human",
    "denied_planner_trace",
    "denied_replay",
    "extra_target",
    "wrong_target",
]


def assert_never(value: NoReturn) -> NoReturn:
    raise AssertionError(value)


def test_convert_steps_projects_identity_and_destination_only_media_path(tmp_path: Path) -> None:
    # Given: one accepted Todo4 step with an absolute source image and copied output PNG.
    image_root = _image_root(tmp_path)
    steps = [_step(split="train")]

    # When: the strict converter projects the accepted step to a Qwen record.
    records = convert_steps(steps, image_root, "train")

    # Then: it exposes exactly the native media and human/GPT conversation keys.
    assert records == [
        {
            "id": "step-train",
            "image": "train/step-train.png",
            "conversations": [
                {
                    "from": "human",
                    "value": '<image>\n{"domain":"blocksworld","planner":"breadth_first_search","task_text":"Execute the next action."}',
                },
                {
                    "from": "gpt",
                    "value": '{"action":"(move a b)","certificate":{"expanded_state":"state-a","frontier_head":"state-a","frontier_order_summary":["state-b"],"kind":"bfs","visited_delta":["state-b"]}}',
                },
            ],
        }
    ]
    assert canonical_json(records[0]) == canonical_json(records[0])


def test_convert_steps_does_not_leak_or_resolve_the_todo4_source_image_path(tmp_path: Path) -> None:
    # Given: an accepted Todo4 step whose source path is absolute and absent from output.
    image_root = _image_root(tmp_path)
    step = _step(split="train", image_path="/accepted/todo4-source.png")

    # When: conversion projects native Qwen media paths under the output root.
    records = convert_steps([step], image_root, "train")

    # Then: only the deterministic destination path is emitted and checked.
    assert records[0]["image"] == "train/step-train.png"
    assert "/accepted/todo4-source.png" not in canonical_json(records[0])


def test_convert_steps_rejects_symlinked_image_path(tmp_path: Path) -> None:
    # Given: a relative image path implemented by a symlink inside the image root.
    image_root = _image_root(tmp_path)
    target = image_root / "train" / "target.png"
    target.write_bytes(b"png")
    link = image_root / "train" / "step-train.png"
    link.unlink()
    link.symlink_to(target)

    # When: conversion validates the media path.
    with pytest.raises(QwenContractError) as error:
        convert_steps([_step(split="train")], image_root, "train")

    # Then: symlinked media is rejected before native loader resolution.
    assert error.value.reason == "symlink_image_path"


def test_convert_steps_rejects_split_mismatch_and_duplicate_step_ids(tmp_path: Path) -> None:
    # Given: records that violate the requested split or repeat an accepted Todo4 ID.
    image_root = _image_root(tmp_path)

    # When: conversion binds records to one output split.
    with pytest.raises(QwenContractError) as mismatch:
        convert_steps([_step(split="dev")], image_root, "train")
    with pytest.raises(QwenContractError) as duplicate:
        convert_steps([_step(split="train"), _step(split="train")], image_root, "train")

    # Then: each collection-level invariant has an independent stable reason.
    assert mismatch.value.reason == "split_mismatch"
    assert duplicate.value.reason == "duplicate_step_id"


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("extra_top_level", "invalid_record_keys"),
        ("second_image", "invalid_image_cardinality"),
        ("extra_token", "invalid_image_token_count"),
        ("assistant_media", "assistant_media_token"),
        ("denied_human", "denied_human_field:route_label"),
        ("denied_planner_trace", "denied_human_field:planner_trace"),
        ("denied_replay", "denied_human_field:replay_transitions"),
        ("extra_target", "invalid_assistant_target_keys"),
        ("wrong_target", "assistant_target_mismatch"),
    ],
)
def test_validate_records_rejects_qwen_schema_policy_and_target_mutations(
    tmp_path: Path, mutation: Mutation, reason: str
) -> None:
    # Given: a converted Qwen record with exactly one deliberate contract mutation.
    image_root = _image_root(tmp_path)
    steps = [_step(split="train")]
    records = convert_steps(steps, image_root, "train")
    record = records[0]
    human = _turn(record, 0)
    assistant = _turn(record, 1)
    match mutation:
        case "extra_top_level":
            record["step_id"] = "leaked"
        case "second_image":
            record["image"] = ["train/step-train.png", "train/step-train.png"]
        case "extra_token":
            human_value = human["value"]
            assert isinstance(human_value, str)
            human["value"] = f"<image>\n<image>\n{human_value.split(chr(10), 1)[1]}"
        case "assistant_media":
            assistant["value"] = f"<image>{assistant['value']}"
        case "denied_human":
            human["value"] = '<image>\n{"domain":"blocksworld","planner":"breadth_first_search","route_label":"x","task_text":"Execute the next action."}'
        case "denied_planner_trace":
            human["value"] = '<image>\n{"domain":"blocksworld","planner":"breadth_first_search","planner_trace":{},"task_text":"Execute the next action."}'
        case "denied_replay":
            human["value"] = '<image>\n{"domain":"blocksworld","planner":"breadth_first_search","replay_transitions":[],"task_text":"Execute the next action."}'
        case "extra_target":
            assistant["value"] = '{"action":"(move a b)","certificate":{},"planner_trace":{}}'
        case "wrong_target":
            assistant["value"] = '{"action":"(move b a)","certificate":{"kind":"bfs"}}'
        case unexpected:
            assert_never(unexpected)

    # When: Qwen output is verified against its corresponding accepted steps.
    with pytest.raises(QwenContractError) as error:
        validate_records(steps, records, image_root, "train")

    # Then: schema, policy, and target drift do not collapse into generic errors.
    assert error.value.reason == reason


def test_validate_records_rejects_non_string_paths_and_malformed_human_json(tmp_path: Path) -> None:
    # Given: native-shaped records with a non-string media field or malformed human payload.
    image_root = _image_root(tmp_path)
    steps = [_step(split="train")]
    records = convert_steps(steps, image_root, "train")
    records[0]["image"] = 1

    # When: contract validation reads the row before the native loader's coercions.
    with pytest.raises(QwenContractError) as path_error:
        validate_records(steps, records, image_root, "train")
    records = convert_steps(steps, image_root, "train")
    _turn(records[0], 0)["value"] = "<image>\n{not-json}"
    with pytest.raises(QwenContractError) as payload_error:
        validate_records(steps, records, image_root, "train")

    # Then: type and syntax boundaries retain deterministic reasons.
    assert path_error.value.reason == "invalid_image_path_type"
    assert payload_error.value.reason == "malformed_human_payload"


@pytest.mark.parametrize(
    ("image_path", "reason"),
    [
        ("/absolute.png", "absolute_image_path"),
        ("../escape.png", "traversal_image_path"),
        ("train/missing.png", "missing_image_path"),
    ],
)
def test_validate_records_rejects_invalid_destination_media_paths(
    tmp_path: Path, image_path: str, reason: str
) -> None:
    # Given: a native Qwen row whose emitted output-media path is unsafe or absent.
    image_root = _image_root(tmp_path)
    steps = [_step(split="train")]
    records = convert_steps(steps, image_root, "train")
    records[0]["image"] = image_path

    # When: destination media paths are validated under the registry data root.
    with pytest.raises(QwenContractError) as error:
        validate_records(steps, records, image_root, "train")

    # Then: the output path boundary reports a stable reason.
    assert error.value.reason == reason


def test_validate_records_rejects_output_identity_path_and_duplicate_mutations(tmp_path: Path) -> None:
    # Given: output records whose id/path do not bind uniquely to Todo4 step IDs.
    image_root = _image_root(tmp_path)
    first = _step(split="train")
    second = _step(split="train", step_id="step-second")
    _destination(image_root, "train", "step-second")
    records = convert_steps([first, second], image_root, "train")

    # When: one projected ID, path, or uniqueness property is corrupted.
    records[0]["id"] = "forged"
    with pytest.raises(QwenContractError) as id_error:
        validate_records([first, second], records, image_root, "train")
    records = convert_steps([first, second], image_root, "train")
    _destination(image_root, "train", "alternate")
    records[0]["image"] = "train/alternate.png"
    with pytest.raises(QwenContractError) as path_error:
        validate_records([first, second], records, image_root, "train")
    records = convert_steps([first, second], image_root, "train")
    records[1]["id"] = "step-train"
    with pytest.raises(QwenContractError) as duplicate_id:
        validate_records([first, second], records, image_root, "train")
    records = convert_steps([first, second], image_root, "train")
    records[1]["image"] = "train/step-train.png"
    with pytest.raises(QwenContractError) as duplicate_path:
        validate_records([first, second], records, image_root, "train")

    # Then: identity, path binding, and output uniqueness do not share a reason.
    assert id_error.value.reason == "record_id_mismatch"
    assert path_error.value.reason == "image_path_mismatch"
    assert duplicate_id.value.reason == "duplicate_record_id"
    assert duplicate_path.value.reason == "duplicate_image_path"


def test_manifest_binds_exact_split_records_and_rejects_tampering(tmp_path: Path) -> None:
    # Given: independently converted train and dev Qwen record sets.
    image_root = _image_root(tmp_path)
    train = convert_steps([_step(split="train")], image_root, "train")
    _destination(image_root, "dev", "step-dev")
    dev = convert_steps([_step(split="dev", step_id="step-dev")], image_root, "dev")

    # When: the canonical manifest is built and checked against those split records.
    manifest = build_manifest({"train": train, "dev": dev})
    validate_manifest(manifest, {"train": train, "dev": dev})

    # Then: manifest bytes are canonical and a changed record fails closed.
    assert list(manifest) == ["schema_version", "splits"]
    splits = manifest["splits"]
    assert isinstance(splits, dict)
    train_manifest = splits["train"]
    assert isinstance(train_manifest, dict)
    assert train_manifest["records"] == 1
    _turn(dev[0], 1)["value"] = json.dumps({"action": "(move b a)", "certificate": {}})
    with pytest.raises(QwenContractError) as error:
        validate_manifest(manifest, {"train": train, "dev": dev})
    assert error.value.reason == "manifest_mismatch"


def _image_root(root: Path) -> Path:
    image_root = root / "assets"
    _destination(image_root, "train", "step-train")
    return image_root


def _destination(image_root: Path, split: str, step_id: str) -> Path:
    image = image_root / split / f"{step_id}.png"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"png")
    return image


def _step(split: str, step_id: str = "step-train", image_path: str = "/accepted/todo4-source.png") -> JsonRecord:
    return {
        "schema_version": "planning_cgas_v1",
        "step_id": step_id,
        "source_transition_id": "source-transition",
        "source_hash": "source-hash",
        "planner": {"algorithm": "breadth_first_search", "version": "v1"},
        "split": split,
        "structural_ood": False,
        "model_input": {
            "domain": "blocksworld",
            "image_path": image_path,
            "planner": "breadth_first_search",
            "task_text": "Execute the next action.",
        },
        "action_target": "(move a b)",
        "certificate": {
            "kind": "bfs",
            "frontier_head": "state-a",
            "frontier_order_summary": ["state-b"],
            "visited_delta": ["state-b"],
            "expanded_state": "state-a",
        },
        "replay_evidence": {"replay_ok": True, "replay_validation_id": "replay-1"},
        "alignment": {
            "png_sha256": "image-hash",
            "state_before_hash": "state-hash",
            "vision_status": "vision_available_step_aligned",
        },
        "counterfactual_targets": [],
    }


def _turn(record: JsonRecord, index: int) -> JsonRecord:
    conversations = record["conversations"]
    assert isinstance(conversations, list)
    turn = conversations[index]
    assert isinstance(turn, dict)
    return turn
