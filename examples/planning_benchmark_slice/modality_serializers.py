from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from .trajectory_schema import load_trajectory_records, validate_trajectory_records
from .zero_shot import ALGORITHMS, normalize_algorithm, validate_modalities


MODALITY_DATASET_SCHEMA_VERSION = "planning_modality_dataset_v1"
MODALITY_RECORD_SCHEMA_VERSION = "planning_modality_record_v1"
VISION_MODALITIES = frozenset({"vision", "vision_language", "vision_language_tool"})
ALGORITHM_ORDER = {algorithm: index for index, algorithm in enumerate(ALGORITHMS)}


class ModalitySerializationError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass(frozen=True, order=True)
class LeakageError:
    record_id: str
    modality: str
    path: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "modality": self.modality,
            "path": self.path,
            "record_id": self.record_id,
        }


def build_modality_records(*, input_path: Path, modalities: Sequence[str]) -> list[dict[str, Any]]:
    selected_modalities = validate_modalities(modalities)
    records_with_source, _files = load_trajectory_records(input_path)
    validation = validate_trajectory_records(records_with_source)
    if not validation["valid"]:
        raise ModalitySerializationError(
            "invalid_trajectory_input",
            "trajectory input failed schema validation",
            details={"validation": validation},
        )

    sorted_steps = sorted(records_with_source, key=lambda item: _record_sort_key(item[0], item[1]))
    modality_records: list[dict[str, Any]] = []
    for step, source in sorted_steps:
        normalized_step = _normalize_step(step)
        for modality in selected_modalities:
            modality_records.append(_build_modality_record(normalized_step, source=source, modality=modality))
    return modality_records


def serialize_modalities(*, input_path: Path, output_dir: Path, modalities: Sequence[str]) -> dict[str, Any]:
    selected_modalities = validate_modalities(modalities)
    records = build_modality_records(input_path=input_path, modalities=selected_modalities)
    leakage_errors = leakage_errors_for_records(records)

    output_dir.mkdir(parents=True, exist_ok=True)
    by_modality = {modality: [record for record in records if record["modality"] == modality] for modality in selected_modalities}
    output_paths: dict[str, str] = {}
    counts_by_modality: dict[str, int] = {}
    counts_by_algorithm = {algorithm: {modality: 0 for modality in selected_modalities} for algorithm in ALGORITHMS}

    for modality in selected_modalities:
        path = output_dir / f"{modality}.jsonl"
        modality_records = by_modality[modality]
        _write_jsonl(path, modality_records)
        output_paths[modality] = str(path)
        counts_by_modality[modality] = len(modality_records)
        for record in modality_records:
            algorithm = str(record["algorithm"])
            if algorithm in counts_by_algorithm:
                counts_by_algorithm[algorithm][modality] += 1

    active_counts_by_algorithm = {
        algorithm: counts
        for algorithm, counts in counts_by_algorithm.items()
        if any(counts.values())
    }
    vision_skip_reasons = _vision_skip_reasons(records)
    return {
        "counts_by_algorithm": active_counts_by_algorithm,
        "counts_by_modality": counts_by_modality,
        "input": str(input_path),
        "leakage_errors": [error.to_dict() for error in leakage_errors],
        "modalities": list(selected_modalities),
        "output": str(output_dir),
        "output_paths": output_paths,
        "record_count": len(records),
        "schema_version": MODALITY_DATASET_SCHEMA_VERSION,
        "valid": not leakage_errors,
        "vision_skip_reasons": vision_skip_reasons,
    }


def leakage_errors_for_records(records: Iterable[dict[str, Any]]) -> list[LeakageError]:
    errors: list[LeakageError] = []
    for record in records:
        errors.extend(leakage_errors_for_record(record))
    return sorted(errors)


def leakage_errors_for_record(record: dict[str, Any]) -> list[LeakageError]:
    modality = str(record.get("modality", "<unknown>"))
    record_id = str(record.get("record_id", "<unknown>"))
    model_facing = record.get("model_facing")
    if not isinstance(model_facing, dict):
        return [
            LeakageError(
                record_id=record_id,
                modality=modality,
                path="model_facing",
                code="model_facing_not_object",
                message="model_facing must be a JSON object",
            )
        ]

    errors: list[LeakageError] = []
    field_paths = sorted(_field_paths(model_facing))
    flattened = json.dumps(model_facing, sort_keys=True, ensure_ascii=True).lower()

    if modality == "vision":
        forbidden_fragments = (
            "canonical_atom",
            "goal_atom",
            "gold",
            "legal_action",
            "pddl",
            "selected_action",
            "state_atom",
            "state_id",
            "symbolic_goal",
            "target",
        )
        for path in field_paths:
            lowered = path.lower()
            if any(fragment in lowered for fragment in forbidden_fragments):
                errors.append(
                    LeakageError(
                        record_id=record_id,
                        modality=modality,
                        path=path,
                        code="vision_symbolic_field_leak",
                        message=f"vision model_facing leaks forbidden symbolic/gold field {path}",
                    )
                )
        forbidden_patterns = (
            r"\b[0-9a-f]{64}\b",
            r"\barm-empty\b",
            r"\bon-table\s*\(",
            r"\b(clear|holding|on)\s*\(",
            r"\b(pickup|putdown|stack|unstack)\s*\(",
        )
        for pattern in forbidden_patterns:
            if re.search(pattern, flattened):
                errors.append(
                    LeakageError(
                        record_id=record_id,
                        modality=modality,
                        path="model_facing",
                        code="vision_symbolic_text_leak",
                        message=f"vision model_facing leaks forbidden text matching {pattern}",
                    )
                )

    if modality == "language":
        forbidden_fragments = ("frame", "image", "render", "visual", "vision")
        for path in field_paths:
            lowered = path.lower()
            if any(fragment in lowered for fragment in forbidden_fragments):
                errors.append(
                    LeakageError(
                        record_id=record_id,
                        modality=modality,
                        path=path,
                        code="language_visual_field_leak",
                        message=f"language model_facing leaks visual field {path}",
                    )
                )
        forbidden_patterns = (r"\.(png|jpg|jpeg|webp|vfg\.json)\b", r"render[_/-]", r"frame[_/-]")
        for pattern in forbidden_patterns:
            if re.search(pattern, flattened):
                errors.append(
                    LeakageError(
                        record_id=record_id,
                        modality=modality,
                        path="model_facing",
                        code="language_visual_text_leak",
                        message=f"language model_facing leaks visual text matching {pattern}",
                    )
                )
    return errors


def _build_modality_record(step: dict[str, Any], *, source: str, modality: str) -> dict[str, Any]:
    algorithm = normalize_algorithm(str(step["algorithm"]))
    record_id = _record_id(step, modality)
    model_facing = _build_model_facing(step, algorithm=algorithm, modality=modality)
    return {
        "algorithm": algorithm,
        "domain": str(step["domain"]),
        "evaluation_metadata": _evaluation_metadata(step, source=source),
        "instance_id": str(step["instance_id"]),
        "modality": modality,
        "modality_boundary_note": "Only model_facing is intended for prompts; supervised_target and evaluation_metadata are not prompt input.",
        "model_facing": model_facing,
        "record_id": record_id,
        "schema_version": MODALITY_RECORD_SCHEMA_VERSION,
        "step_index": int(step["step_index"]),
        "supervised_target": _supervised_target(step, algorithm=algorithm),
        "trajectory_id": str(step["trajectory_id"]),
    }


def _build_model_facing(step: dict[str, Any], *, algorithm: str, modality: str) -> dict[str, Any]:
    model_facing: dict[str, Any] = {
        "planner": {
            "algorithm": algorithm,
            "task": f"Predict the next one-step planner output for {algorithm}.",
        },
        "response_format": {
            "internal_state_update": "brief text describing the algorithm state update",
            "next_action": "one canonical Blocksworld action string",
        },
    }
    if modality == "vision":
        model_facing["task_framing"] = {
            "domain": "blocksworld",
            "instruction": "Use the supplied scene observation to choose the next planning action.",
        }
        model_facing["visual_observation"] = _visual_observation(step)
        return model_facing

    if modality in {"language", "vision_language", "vision_language_tool"}:
        model_facing["language_context"] = _language_context(step)
    if modality in {"vision_language", "vision_language_tool"}:
        model_facing["visual_observation"] = _visual_observation(step)
    if modality == "vision_language_tool":
        model_facing["tool_state"] = _tool_state(step, algorithm=algorithm)
    return model_facing


def _visual_observation(step: dict[str, Any]) -> dict[str, Any]:
    render_paths = _render_paths(step)
    payload: dict[str, Any] = {
        "kind": "blocksworld_render_artifacts",
        "render_paths": render_paths,
    }
    if not render_paths:
        payload["unavailable"] = {
            "code": "no_render_artifacts",
            "message": "The source trajectory did not reference render artifacts for this step.",
        }
    return payload


def _language_context(step: dict[str, Any]) -> dict[str, Any]:
    state_atoms = [str(atom) for atom in step.get("state_atoms", [])]
    goal_atoms = [str(atom) for atom in step.get("goal_atoms", [])]
    return {
        "action_vocabulary": ["pickup(X)", "putdown(X)", "stack(X,Y)", "unstack(X,Y)"],
        "current_state_atoms": state_atoms,
        "current_state_text": _atoms_sentence("Current state", state_atoms),
        "goal_atoms": goal_atoms,
        "goal_text": _atoms_sentence("Goal", goal_atoms),
        "legal_action_count": len(step.get("legal_actions", [])) if isinstance(step.get("legal_actions"), list) else 0,
    }


def _tool_state(step: dict[str, Any], *, algorithm: str) -> dict[str, Any]:
    algorithm_payload = step.get(algorithm)
    if not isinstance(algorithm_payload, dict):
        algorithm_payload = {}
    return {
        "algorithm": algorithm,
        "scratchpad": _strip_prompt_hidden_labels(algorithm_payload),
        "update_target_field": "internal_state_update",
    }


def _strip_prompt_hidden_labels(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _strip_prompt_hidden_labels(nested)
            for key, nested in value.items()
            if str(key) != "selected_action"
        }
    if isinstance(value, list):
        return [_strip_prompt_hidden_labels(item) for item in value]
    return value


def _supervised_target(step: dict[str, Any], *, algorithm: str) -> dict[str, Any]:
    return {
        "internal_state_update": _internal_state_update_target(step, algorithm=algorithm),
        "next_action": step.get("selected_action"),
    }


def _evaluation_metadata(step: dict[str, Any], *, source: str) -> dict[str, Any]:
    return {
        "goal_atoms": list(step.get("goal_atoms", [])),
        "is_terminal": bool(step.get("is_terminal", False)),
        "legal_actions": list(step.get("legal_actions", [])),
        "selected_action": step.get("selected_action"),
        "source": source,
        "state_atoms": list(step.get("state_atoms", [])),
        "state_id": str(step.get("state_id", "")),
    }


def _internal_state_update_target(step: dict[str, Any], *, algorithm: str) -> str:
    payload = step.get(algorithm)
    if not isinstance(payload, dict):
        return f"{algorithm} has no algorithm-specific update payload for this step."
    if algorithm == "bfs":
        return (
            "BFS dequeues the recorded state, expands its successors, and updates the FIFO frontier "
            f"from {len(payload.get('frontier_before', []))} to {len(payload.get('frontier_after', []))} entries."
        )
    if algorithm == "fast_forward":
        return (
            "Fast Forward records the current relaxed heuristic and chooses the successor with the "
            f"best {payload.get('tie_break_rule', 'tie-break rule')} score."
        )
    if algorithm == "iterated_width":
        return (
            "Iterated Width applies the recorded novelty decision "
            f"{payload.get('decision', '<missing>')} at width {payload.get('width', '<missing>')}."
        )
    if algorithm == "graphplan":
        proposition_layers = payload.get("proposition_layers", [])
        action_layers = payload.get("action_layers", [])
        mutex_pairs = payload.get("mutex_pairs", [])
        return (
            "Graphplan updates its layer graph with "
            f"{len(proposition_layers)} proposition layers, {len(action_layers)} action layers, "
            f"and {len(mutex_pairs)} action mutex pairs."
        )
    return f"Update the {algorithm} planner state according to the recorded scratchpad."


def _render_paths(step: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for container in (step, step.get("metadata") if isinstance(step.get("metadata"), dict) else {}):
        if not isinstance(container, dict):
            continue
        for key in ("render_paths", "render_frames", "frame_paths", "image_paths", "images"):
            value = container.get(key)
            if isinstance(value, list):
                paths.extend(str(item) for item in value if str(item).strip())
            elif isinstance(value, str) and value.strip():
                paths.append(value)
        for key in ("render_trace", "trace_path", "render_result_path"):
            value = container.get(key)
            if isinstance(value, str) and value.strip():
                paths.append(value)
    return sorted(dict.fromkeys(paths))


def _vision_skip_reasons(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    for record in records:
        if record.get("modality") not in VISION_MODALITIES:
            continue
        visual = record.get("model_facing", {}).get("visual_observation") if isinstance(record.get("model_facing"), dict) else None
        if not isinstance(visual, dict):
            continue
        unavailable = visual.get("unavailable")
        if not isinstance(unavailable, dict):
            continue
        reasons.append(
            {
                "code": str(unavailable.get("code", "unknown")),
                "message": str(unavailable.get("message", "")),
                "modality": str(record.get("modality")),
                "record_id": str(record.get("record_id")),
            }
        )
    return sorted(reasons, key=lambda item: (item["modality"], item["record_id"], item["code"]))


def _normalize_step(step: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(step)
    normalized["algorithm"] = normalize_algorithm(str(step["algorithm"]))
    return normalized


def _record_sort_key(step: dict[str, Any], source: str) -> tuple[int, str, str, int, str]:
    algorithm = normalize_algorithm(str(step.get("algorithm", "")))
    step_index = step.get("step_index", 0)
    numeric_step = step_index if isinstance(step_index, int) and not isinstance(step_index, bool) else 0
    return (
        ALGORITHM_ORDER.get(algorithm, len(ALGORITHM_ORDER)),
        str(step.get("instance_id", "")),
        str(step.get("trajectory_id", "")),
        numeric_step,
        source,
    )


def _record_id(step: dict[str, Any], modality: str) -> str:
    return f"{step['trajectory_id']}__step_{int(step['step_index']):04d}__{modality}"


def _atoms_sentence(label: str, atoms: Sequence[str]) -> str:
    if not atoms:
        return f"{label}: none."
    return f"{label}: " + ", ".join(atoms) + "."


def _field_paths(value: Any, prefix: str = "") -> Iterable[str]:
    if isinstance(value, dict):
        for key, nested in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield path
            yield from _field_paths(nested, path)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            yield from _field_paths(nested, f"{prefix}[{index}]")


def _write_jsonl(path: Path, records: Sequence[dict[str, Any]]) -> None:
    text = "".join(json.dumps(record, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n" for record in records)
    path.write_text(text, encoding="utf-8")


__all__ = [
    "MODALITY_DATASET_SCHEMA_VERSION",
    "MODALITY_RECORD_SCHEMA_VERSION",
    "LeakageError",
    "ModalitySerializationError",
    "build_modality_records",
    "leakage_errors_for_record",
    "leakage_errors_for_records",
    "serialize_modalities",
]
