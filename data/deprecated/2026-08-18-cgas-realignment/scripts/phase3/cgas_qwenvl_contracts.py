from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Final, Mapping, Sequence, TypeAlias


STEP_SCHEMA_VERSION: Final = "planning_cgas_v1"
MANIFEST_SCHEMA_VERSION: Final = "planning_cgas_qwenvl_v1"
SPLITS: Final = frozenset({"train", "dev", "test"})
HUMAN_FIELDS: Final = frozenset({"domain", "planner", "task_text"})
DENIED_HUMAN_FIELDS: Final = frozenset(
    {"route_label", "planner_trace", "replay_transitions"}
)
DENIED_MODEL_INPUT_FIELDS: Final = DENIED_HUMAN_FIELDS
STEP_FIELDS: Final = frozenset(
    {
        "schema_version",
        "step_id",
        "source_transition_id",
        "source_hash",
        "planner",
        "split",
        "structural_ood",
        "model_input",
        "action_target",
        "certificate",
        "replay_evidence",
        "alignment",
        "counterfactual_targets",
    }
)
JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonRecord: TypeAlias = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class QwenContractError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


def canonical_json(value: JsonValue) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def convert_steps(
    steps: Sequence[JsonRecord], image_root: Path, split: str
) -> list[JsonRecord]:
    _validate_split(split)
    _validate_step_collection(steps, split)
    records: list[JsonRecord] = []
    for step in steps:
        source = _source(step, split)
        image_path = _output_image_path(source.step_id, split)
        _validate_image_path(image_path, image_root)
        human = canonical_json(
            {
                "domain": source.domain,
                "planner": source.planner,
                "task_text": source.task_text,
            }
        )
        assistant = canonical_json(
            {"action": source.action, "certificate": source.certificate}
        )
        records.append(
            {
                "id": source.step_id,
                "image": image_path,
                "conversations": [
                    {"from": "human", "value": f"<image>\n{human}"},
                    {"from": "gpt", "value": assistant},
                ],
            }
        )
    return records


def validate_records(
    steps: Sequence[JsonRecord],
    records: Sequence[JsonRecord],
    image_root: Path,
    split: str,
) -> None:
    _validate_split(split)
    _validate_step_collection(steps, split)
    if len(steps) != len(records):
        raise QwenContractError("record_count_mismatch")
    _validate_output_uniqueness(records)
    for step, record in zip(steps, records, strict=True):
        source = _source(step, split)
        _validate_record(record, source, image_root)


def build_manifest(
    records_by_split: Mapping[str, Sequence[JsonRecord]],
) -> JsonRecord:
    splits: JsonRecord = {}
    for split in sorted(records_by_split):
        _validate_split(split)
        records = records_by_split[split]
        splits[split] = {
            "records": len(records),
            "sha256": _digest(canonical_json(list(records))),
        }
    return {"schema_version": MANIFEST_SCHEMA_VERSION, "splits": splits}


def validate_manifest(
    manifest: JsonRecord, records_by_split: Mapping[str, Sequence[JsonRecord]]
) -> None:
    if set(manifest) != {"schema_version", "splits"}:
        raise QwenContractError("invalid_manifest_keys")
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise QwenContractError("invalid_manifest_schema")
    if manifest != build_manifest(records_by_split):
        raise QwenContractError("manifest_mismatch")


@dataclass(frozen=True, slots=True)
class _StepSource:
    step_id: str
    split: str
    domain: str
    planner: str
    task_text: str
    action: str
    certificate: JsonRecord


def _validate_step_collection(steps: Sequence[JsonRecord], split: str) -> None:
    step_ids: list[str] = []
    for step in steps:
        source = _source(step, split)
        step_ids.append(source.step_id)
    if len(step_ids) != len(set(step_ids)):
        raise QwenContractError("duplicate_step_id")


def _source(step: JsonRecord, expected_split: str) -> _StepSource:
    if set(step) != STEP_FIELDS:
        raise QwenContractError("invalid_step_keys")
    if step.get("schema_version") != STEP_SCHEMA_VERSION:
        raise QwenContractError("invalid_step_schema")
    if step.get("split") != expected_split:
        raise QwenContractError("split_mismatch")
    step_id = _string(step, "step_id", "invalid_step_id")
    model_input = _mapping(step, "model_input", "invalid_model_input")
    denied = sorted(set(model_input) & DENIED_MODEL_INPUT_FIELDS)
    if denied:
        raise QwenContractError(f"denied_model_input_field:{denied[0]}")
    if set(model_input) != {"domain", "image_path", "planner", "task_text"}:
        raise QwenContractError("invalid_model_input_keys")
    _string(model_input, "image_path", "invalid_source_image_path")
    certificate = _mapping(step, "certificate", "invalid_certificate")
    return _StepSource(
        step_id=step_id,
        split=expected_split,
        domain=_string(model_input, "domain", "invalid_model_input"),
        planner=_string(model_input, "planner", "invalid_model_input"),
        task_text=_string(model_input, "task_text", "invalid_model_input"),
        action=_string(step, "action_target", "invalid_action_target"),
        certificate=certificate,
    )


def _validate_record(record: JsonRecord, source: _StepSource, image_root: Path) -> None:
    if set(record) != {"id", "image", "conversations"}:
        raise QwenContractError("invalid_record_keys")
    if _string(record, "id", "invalid_record_id") != source.step_id:
        raise QwenContractError("record_id_mismatch")
    if isinstance(record.get("image"), list):
        raise QwenContractError("invalid_image_cardinality")
    image_path = _string(record, "image", "invalid_image_path_type")
    _validate_image_path(image_path, image_root)
    if image_path != _output_image_path(source.step_id, source.split):
        raise QwenContractError("image_path_mismatch")
    conversations = record.get("conversations")
    if not isinstance(conversations, list) or len(conversations) != 2:
        raise QwenContractError("invalid_conversations")
    human = _turn(conversations[0], "human")
    assistant = _turn(conversations[1], "gpt")
    _validate_human(human, source)
    _validate_assistant(assistant, source)


def _turn(value: JsonValue, expected_role: str) -> str:
    if not isinstance(value, dict) or set(value) != {"from", "value"}:
        raise QwenContractError("invalid_conversation_turn")
    if value.get("from") != expected_role:
        raise QwenContractError("invalid_conversation_roles")
    return _string(value, "value", "invalid_conversation_value")


def _validate_human(value: str, source: _StepSource) -> None:
    if value.count("<image>") != 1:
        raise QwenContractError("invalid_image_token_count")
    if "<video>" in value or not value.startswith("<image>\n"):
        raise QwenContractError("invalid_human_media")
    payload = _json_mapping(value.removeprefix("<image>\n"), "malformed_human_payload")
    denied = sorted(set(payload) & DENIED_HUMAN_FIELDS)
    if denied:
        raise QwenContractError(f"denied_human_field:{denied[0]}")
    if set(payload) != HUMAN_FIELDS:
        raise QwenContractError("invalid_human_payload_keys")
    expected = {"domain": source.domain, "planner": source.planner, "task_text": source.task_text}
    if payload != expected:
        raise QwenContractError("human_payload_mismatch")


def _validate_assistant(value: str, source: _StepSource) -> None:
    if "<image>" in value or "<video>" in value:
        raise QwenContractError("assistant_media_token")
    target = _json_mapping(value, "malformed_assistant_target")
    if set(target) != {"action", "certificate"}:
        raise QwenContractError("invalid_assistant_target_keys")
    if target != {"action": source.action, "certificate": source.certificate}:
        raise QwenContractError("assistant_target_mismatch")


def _validate_image_path(image_path: str, image_root: Path) -> None:
    posix_path = PurePosixPath(image_path)
    windows_path = PureWindowsPath(image_path)
    if posix_path.is_absolute() or windows_path.is_absolute():
        raise QwenContractError("absolute_image_path")
    if not image_path or "\\" in image_path or any(part in {"", ".", ".."} for part in posix_path.parts):
        raise QwenContractError("traversal_image_path")
    candidate = image_root.joinpath(*posix_path.parts)
    current = image_root
    for part in posix_path.parts:
        current = current / part
        if current.is_symlink():
            raise QwenContractError("symlink_image_path")
    if not candidate.is_file():
        raise QwenContractError("missing_image_path")


def _validate_output_uniqueness(records: Sequence[JsonRecord]) -> None:
    record_ids = [record["id"] for record in records if isinstance(record.get("id"), str)]
    image_paths = [record["image"] for record in records if isinstance(record.get("image"), str)]
    if len(record_ids) != len(set(record_ids)):
        raise QwenContractError("duplicate_record_id")
    if len(image_paths) != len(set(image_paths)):
        raise QwenContractError("duplicate_image_path")


def _output_image_path(step_id: str, split: str) -> str:
    path = PurePosixPath(step_id)
    if path.name != step_id or step_id in {"", ".", ".."}:
        raise QwenContractError("invalid_step_id")
    return f"{split}/{step_id}.png"


def _validate_split(split: str) -> None:
    if split not in SPLITS:
        raise QwenContractError("invalid_split")


def _string(value: Mapping[str, JsonValue], field: str, reason: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result:
        raise QwenContractError(reason)
    return result


def _mapping(value: Mapping[str, JsonValue], field: str, reason: str) -> JsonRecord:
    result = value.get(field)
    if not isinstance(result, dict):
        raise QwenContractError(reason)
    return result


def _json_mapping(value: str, reason: str) -> JsonRecord:
    try:
        result: JsonValue = json.loads(value)
    except json.JSONDecodeError as error:
        raise QwenContractError(reason) from error
    if not isinstance(result, dict):
        raise QwenContractError(reason)
    return result


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
