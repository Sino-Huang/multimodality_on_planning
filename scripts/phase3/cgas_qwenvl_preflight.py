from __future__ import annotations

import argparse
import importlib
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Protocol, Sequence

import torch


class QwenProcessor(Protocol):
    @property
    def tokenizer(self) -> object: ...

    @property
    def image_processor(self) -> object: ...

    def apply_chat_template(self, messages: object, tokenize: bool, return_dict: bool, return_tensors: str) -> dict[str, object]: ...


def strict_preflight(qwenvl_root: Path, image_root: Path, processor: QwenProcessor) -> dict[str, object]:
    loader = _loader_module()
    records_by_split = _read_records(qwenvl_root)
    manifest_ids = _manifest_ids(qwenvl_root / "manifest.json")
    rejections: list[dict[str, str]] = []
    checked_step_ids: list[str] = []
    counters = {
        "row_identity_mismatches": 0,
        "message_build_failures": 0,
        "tokenization_failures": 0,
        "empty_assistant_label_rows": 0,
        "null_image_tensor_rows": 0,
        "null_image_grid_rows": 0,
    }
    emitted = sum(len(rows) for rows in records_by_split.values())
    for split, rows in records_by_split.items():
        expected_ids = manifest_ids.get(split, [])
        for index, record in enumerate(rows):
            step_id = _record_id(record, split, index)
            checked_step_ids.append(step_id)
            if index >= len(expected_ids) or expected_ids[index] != step_id:
                counters["row_identity_mismatches"] += 1
                rejections.append(_rejection(step_id, "row_identity_mismatch"))
            source = dict(record)
            source["data_path"] = str(image_root)
            try:
                loader._build_messages(source, image_root)
            except (OSError, ValueError, KeyError, TypeError) as error:
                counters["message_build_failures"] += 1
                rejections.append(_rejection(step_id, f"message_build_failed:{type(error).__name__}"))
                continue
            try:
                _parse_assistant_json(source)
                tokenized = loader.preprocess_qwen_visual([source], processor)
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
                counters["tokenization_failures"] += 1
                rejections.append(_rejection(step_id, f"tokenization_failed:{type(error).__name__}"))
                continue
            _record_tensor_failures(step_id, tokenized, counters, rejections)
    accepted = not rejections and emitted == sum(len(ids) for ids in manifest_ids.values())
    return {
        "accepted": accepted,
        "records_checked": len(checked_step_ids),
        "records_emitted": emitted,
        "checked_step_ids": checked_step_ids,
        "rejections": rejections,
        **counters,
    }


def loader_batch_smoke(processor: QwenProcessor, data_args: SimpleNamespace) -> dict[str, object]:
    loader = _loader_module()
    dataset = loader.LazySupervisedDataset(processor, data_args)
    sample = dataset[0]
    collator = loader.DataCollatorForSupervisedDataset(processor.tokenizer)
    batch = collator([sample])
    labels = batch["labels"]
    label_count = int((labels != loader.IGNORE_INDEX).sum().item()) if isinstance(labels, torch.Tensor) else 0
    return {
        "dataset_name": str(data_args.dataset_use),
        "batch_size": 1,
        "assistant_label_token_count": label_count,
        "pixel_values_non_null": batch.get("pixel_values") is not None,
        "image_grid_thw_non_null": batch.get("image_grid_thw") is not None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Strictly preflight CGAS Qwen-VL rows through the native loader path.")
    parser.add_argument("--qwenvl-root", type=Path, default=Path("data/planning_cgas_v1/qwenvl"))
    parser.add_argument("--image-root", type=Path, default=Path("data/planning_cgas_v1/qwenvl/images"))
    parser.add_argument("--processor", required=True)
    parser.add_argument("--loader-smoke", action="store_true")
    parser.add_argument("--model-type", default="qwen2.5vl")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    try:
        import transformers

        processor = transformers.AutoProcessor.from_pretrained(args.processor)
        processor.tokenizer.model_max_length = 4096
        processor.tokenizer.padding_side = "left"
        report = strict_preflight(args.qwenvl_root, args.image_root, processor)
        if args.loader_smoke and report["accepted"]:
            report["loader_batch"] = loader_batch_smoke(processor, _data_args(args.model_type))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(_json(report))
    return 0 if report["accepted"] else 1


def _data_args(model_type: str) -> SimpleNamespace:
    return SimpleNamespace(
        dataset_use="planning_cgas_v1_train",
        model_type=model_type,
        data_packing=False,
        data_flatten=False,
        min_pixels=1,
        max_pixels=1024,
        video_min_pixels=1,
        video_max_pixels=1024,
        video_min_frames=1,
        video_max_frames=1,
        video_fps=1,
    )


def _read_records(root: Path) -> dict[str, list[dict[str, object]]]:
    return {split: [json.loads(line) for line in (root / f"{split}.jsonl").read_text(encoding="utf-8").splitlines() if line] for split in ("train", "dev", "test")}


def _manifest_ids(path: Path) -> dict[str, list[str]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    splits = manifest.get("splits") if isinstance(manifest, dict) else None
    if not isinstance(splits, dict):
        return {}
    result: dict[str, list[str]] = {}
    for split, value in splits.items():
        if isinstance(split, str) and isinstance(value, dict) and isinstance(value.get("ids"), list):
            result[split] = [item for item in value["ids"] if isinstance(item, str)]
    return result


def _record_id(record: dict[str, object], split: str, index: int) -> str:
    value = record.get("id")
    return value if isinstance(value, str) and value else f"{split}:{index}"


def _parse_assistant_json(record: dict[str, object]) -> None:
    conversations = record["conversations"]
    if not isinstance(conversations, list) or len(conversations) < 2:
        raise ValueError("invalid_conversations")
    assistant = conversations[1]
    if not isinstance(assistant, dict) or not isinstance(assistant.get("value"), str):
        raise ValueError("invalid_assistant")
    json.loads(assistant["value"])


def _record_tensor_failures(step_id: str, tokenized: dict[str, object], counters: dict[str, int], rejections: list[dict[str, str]]) -> None:
    loader = _loader_module()
    labels = tokenized.get("labels")
    if not isinstance(labels, torch.Tensor) or int((labels != loader.IGNORE_INDEX).sum().item()) == 0:
        counters["empty_assistant_label_rows"] += 1
        rejections.append(_rejection(step_id, "empty_assistant_labels"))
    if tokenized.get("pixel_values") is None:
        counters["null_image_tensor_rows"] += 1
        rejections.append(_rejection(step_id, "null_image_tensor"))
    if tokenized.get("image_grid_thw") is None:
        counters["null_image_grid_rows"] += 1
        rejections.append(_rejection(step_id, "null_image_grid_thw"))


def _rejection(step_id: str, reason: str) -> dict[str, str]:
    return {"step_id": step_id, "reason": reason}


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _loader_module():
    try:
        return importlib.import_module("starVLA.dataloader.vlm_datasets")
    except ImportError as error:
        if not _is_transformers_import_boundary(error):
            raise
    image_utils = types.ModuleType("transformers.image_utils")
    setattr(image_utils, "load_image", _load_image)
    transformers_module = types.ModuleType("transformers")
    setattr(transformers_module, "PreTrainedTokenizer", object)
    setattr(transformers_module, "image_utils", image_utils)
    previous_transformers = sys.modules.get("transformers")
    previous_image_utils = sys.modules.get("transformers.image_utils")
    sys.modules["transformers"] = transformers_module
    sys.modules["transformers.image_utils"] = image_utils
    try:
        return importlib.import_module("starVLA.dataloader.vlm_datasets")
    finally:
        if previous_transformers is not None:
            sys.modules["transformers"] = previous_transformers
        else:
            sys.modules.pop("transformers", None)
        if previous_image_utils is not None:
            sys.modules["transformers.image_utils"] = previous_image_utils
        else:
            sys.modules.pop("transformers.image_utils", None)


def _is_transformers_import_boundary(error: ImportError) -> bool:
    return error.name in {"transformers", "transformers.image_utils", "huggingface_hub"} and "huggingface-hub" in str(error)


def _load_image(path: str):
    from PIL import Image

    return Image.open(path).convert("RGB")


if __name__ == "__main__":
    raise SystemExit(main())
