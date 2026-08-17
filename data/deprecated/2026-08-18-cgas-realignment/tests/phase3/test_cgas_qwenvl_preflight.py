from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch

from scripts.phase3 import cgas_qwenvl_preflight
from scripts.phase3.cgas_qwenvl import build_corpus
from scripts.phase3.cgas_qwenvl_preflight import loader_batch_smoke, strict_preflight
from starVLA.dataloader.qwenvl_llavajson import qwen_data_config
from test_cgas_qwenvl_conversion import _inputs


def test_strict_preflight_checks_every_native_qwen_row_before_lazy_dataset_retry(tmp_path: Path) -> None:
    # Given: a fixture-derived Qwen corpus and a processor exposing the native Qwen contract.
    source, alignment, steps = _inputs(tmp_path)
    output = tmp_path / "qwenvl"
    assert build_corpus(source, alignment, steps, output)["rejections"] == []
    processor = FakeQwenProcessor()

    # When: the strict preflight runs row by row before LazySupervisedDataset exists.
    report = strict_preflight(output, output / "images", processor)

    # Then: every emitted row is checked once with preserved step identity and visual tensors.
    assert report["records_checked"] == 12
    assert report["records_emitted"] == 12
    assert report["row_identity_mismatches"] == 0
    assert report["message_build_failures"] == 0
    assert report["tokenization_failures"] == 0
    assert report["empty_assistant_label_rows"] == 0
    assert report["null_image_tensor_rows"] == 0
    assert report["null_image_grid_rows"] == 0
    assert len(processor.calls) == _int(report, "records_checked")


def test_strict_preflight_fails_on_corrupt_row_exact_step_id_without_fallback(tmp_path: Path) -> None:
    # Given: a valid corpus whose first row is independently corrupted in two ways.
    source, alignment, steps = _inputs(tmp_path)
    output = tmp_path / "qwenvl"
    assert build_corpus(source, alignment, steps, output)["rejections"] == []
    first_id = _first_row_id(output / "train.jsonl")
    image_corrupt = tmp_path / "bad-image"
    shutil.copytree(output, image_corrupt)
    _mutate_first_row(image_corrupt / "train.jsonl", "image", "train/missing.png")
    json_corrupt = tmp_path / "bad-json"
    shutil.copytree(output, json_corrupt)
    _mutate_first_turn(json_corrupt / "train.jsonl", 1, "{not-json}")

    # When: each copied corpus is preflighted.
    image_report = strict_preflight(image_corrupt, image_corrupt / "images", FakeQwenProcessor())
    json_report = strict_preflight(json_corrupt, json_corrupt / "images", FakeQwenProcessor())

    # Then: both failures name the originating row rather than substituting another sample.
    assert image_report["accepted"] is False
    assert image_report["message_build_failures"] == 1
    assert _first_rejection_step_id(image_report) == first_id
    assert json_report["accepted"] is False
    assert json_report["tokenization_failures"] == 1
    assert _first_rejection_step_id(json_report) == first_id


def test_loader_batch_smoke_uses_registered_train_dataset_and_collator(tmp_path: Path, monkeypatch) -> None:
    # Given: the actual registered train alias rebound to a fixture corpus.
    source, alignment, steps = _inputs(tmp_path)
    output = tmp_path / "qwenvl"
    assert build_corpus(source, alignment, steps, output)["rejections"] == []
    monkeypatch.setitem(
        qwen_data_config.data_dict,
        "planning_cgas_v1_train",
        {"annotation_path": str(output / "train.jsonl"), "data_path": str(output / "images")},
    )

    # When: the native LazySupervisedDataset and DataCollator surface builds one batch.
    report = loader_batch_smoke(FakeQwenProcessor(), _data_args())

    # Then: the collated batch retains non-null image tensors and assistant labels.
    assert report["dataset_name"] == "planning_cgas_v1_train"
    assert report["batch_size"] == 1
    assert report["pixel_values_non_null"] is True
    assert report["image_grid_thw_non_null"] is True
    assert _int(report, "assistant_label_token_count") > 0


def test_loader_module_preserves_internal_import_error_when_message_mentions_huggingface_hub(monkeypatch) -> None:
    # Given: the native loader import raises from inside its own module, not from the transformers boundary.
    attempts: list[str] = []

    def import_module(name: str) -> object:
        attempts.append(name)
        raise ImportError("internal loader error mentions huggingface-hub diagnostics")

    monkeypatch.setattr(cgas_qwenvl_preflight.importlib, "import_module", import_module)

    # When / Then: the internal error is propagated without retrying with fake transformers modules.
    with pytest.raises(ImportError, match="internal loader error"):
        cgas_qwenvl_preflight._loader_module()
    assert attempts == ["starVLA.dataloader.vlm_datasets"]


class FakeTokenizer:
    pad_token_id = 0
    model_max_length = 128
    padding_side = "left"

    def decode(self, tokens: object, skip_special_tokens: bool = False) -> str:
        _ = skip_special_tokens
        return str(tokens)


class FakeImageProcessor:
    min_pixels = 1
    max_pixels = 1024
    merge_size = 2
    size = {"shortest_edge": 1, "longest_edge": 1024}


class FakeQwenProcessor:
    def __init__(self) -> None:
        self.tokenizer = FakeTokenizer()
        self.image_processor = FakeImageProcessor()
        self.video_processor = None
        self.calls: list[dict[str, str]] = []

    def apply_chat_template(self, messages: object, tokenize: bool, return_dict: bool, return_tensors: str) -> dict[str, object]:
        _ = (tokenize, return_dict, return_tensors)
        assert isinstance(messages, list)
        assert isinstance(messages[1], dict)
        content = messages[1]["content"]
        assert isinstance(content, list)
        assert isinstance(content[0], dict)
        assistant_text = str(content[0]["text"])
        json.loads(assistant_text)
        self.calls.append({"assistant_text": assistant_text})
        return {
            "input_ids": torch.tensor([[151652, 151655, 77091, 42, 151645, 11]], dtype=torch.long),
            "pixel_values": torch.ones((1, 3), dtype=torch.float32),
            "image_grid_thw": torch.tensor([[1, 2, 2]], dtype=torch.long),
        }


def _data_args() -> SimpleNamespace:
    return SimpleNamespace(
        dataset_use="planning_cgas_v1_train",
        model_type="qwen2.5vl",
        data_packing=False,
        data_flatten=False,
        min_pixels=1,
        max_pixels=1024,
    )


def _first_row_id(path: Path) -> str:
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert isinstance(row["id"], str)
    return row["id"]


def _int(report: dict[str, object], field: str) -> int:
    value = report[field]
    assert isinstance(value, int)
    return value


def _first_rejection_step_id(report: dict[str, object]) -> str:
    rejections = report["rejections"]
    assert isinstance(rejections, list)
    rejection = rejections[0]
    assert isinstance(rejection, dict)
    step_id = rejection["step_id"]
    assert isinstance(step_id, str)
    return step_id


def _mutate_first_row(path: Path, field: str, value: str) -> None:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0][field] = value
    path.write_text("".join(json.dumps(item) + "\n" for item in rows), encoding="utf-8")


def _mutate_first_turn(path: Path, index: int, value: str) -> None:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    conversations = rows[0]["conversations"]
    assert isinstance(conversations, list)
    turn = conversations[index]
    assert isinstance(turn, dict)
    turn["value"] = value
    path.write_text("".join(json.dumps(item) + "\n" for item in rows), encoding="utf-8")
