from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from .zero_shot import ALGORITHMS, normalize_algorithm


SCHEMA_VERSION = "planning_expert_trajectory_v1"
SUPPORTED_SUFFIXES = (".json", ".jsonl")

SHARED_REQUIRED_FIELDS: tuple[str, ...] = (
    "trajectory_id",
    "algorithm",
    "domain",
    "instance_id",
    "step_index",
    "state_id",
    "state_atoms",
    "goal_atoms",
    "legal_actions",
    "selected_action",
    "is_terminal",
    "metadata",
)

ALGORITHM_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "bfs": (
        "frontier_before",
        "frontier_after",
        "visited_before",
        "visited_after",
        "dequeued_state_id",
        "successors",
    ),
    "fast_forward": (
        "heuristic_value",
        "successor_heuristics",
        "selected_successor_id",
        "tie_break_rule",
        "relaxed_plan_metadata",
    ),
    "iterated_width": (
        "width",
        "novelty_table_before",
        "novelty_table_after",
        "novel_item",
        "decision",
    ),
    "graphplan": (
        "proposition_layers",
        "action_layers",
        "mutex_pairs",
        "extraction",
    ),
}


@dataclass(frozen=True, order=True)
class TrajectoryValidationError:
    source: str
    path: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "path": self.path,
            "source": self.source,
        }


class TrajectorySchemaError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


def canonical_string_list(values: Iterable[Any]) -> list[str]:
    return sorted(str(value) for value in values)


def canonical_novelty_table(value: Any) -> list[Any]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return []
    entries = [_canonical_novelty_entry(entry) for entry in value]
    return sorted(entries, key=_json_sort_key)


def canonical_mutex_pairs(value: Any) -> list[list[str]]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return []
    pairs: list[list[str]] = []
    for pair in value:
        if not isinstance(pair, (list, tuple, set, frozenset)):
            pairs.append([str(pair)])
            continue
        pairs.append(sorted(str(item) for item in pair))
    return sorted(pairs, key=_json_sort_key)


def canonicalize_trajectory_step(step: dict[str, Any]) -> dict[str, Any]:
    canonical = {str(key): _canonicalize_json_value(value) for key, value in step.items()}
    for field in ("state_atoms", "goal_atoms", "legal_actions"):
        if isinstance(step.get(field), (list, tuple, set, frozenset)):
            canonical[field] = canonical_string_list(step[field])

    algorithm = normalize_algorithm(str(step.get("algorithm", "")))
    if algorithm in ALGORITHMS:
        canonical["algorithm"] = algorithm
    if algorithm == "bfs" and isinstance(step.get("bfs"), dict):
        canonical["bfs"] = _canonicalize_bfs(step["bfs"])
    elif algorithm == "fast_forward" and isinstance(step.get("fast_forward"), dict):
        canonical["fast_forward"] = _canonicalize_fast_forward(step["fast_forward"])
    elif algorithm == "iterated_width" and isinstance(step.get("iterated_width"), dict):
        canonical["iterated_width"] = _canonicalize_iterated_width(step["iterated_width"])
    elif algorithm == "graphplan" and isinstance(step.get("graphplan"), dict):
        canonical["graphplan"] = _canonicalize_graphplan(step["graphplan"])
    return dict(sorted(canonical.items()))


def canonical_json_text(payload: Any) -> str:
    return json.dumps(_canonicalize_json_value(payload), indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def validate_trajectory_step(step: Any, *, source: str = "<memory>") -> list[TrajectoryValidationError]:
    errors: list[TrajectoryValidationError] = []
    if not isinstance(step, dict):
        return [
            TrajectoryValidationError(
                source=source,
                path="<root>",
                code="not_object",
                message="trajectory step must be a JSON object",
            )
        ]

    for field in SHARED_REQUIRED_FIELDS:
        if field not in step:
            errors.append(_missing(source, field))

    algorithm = step.get("algorithm")
    normalized_algorithm = normalize_algorithm(algorithm) if isinstance(algorithm, str) else ""
    if normalized_algorithm not in ALGORITHMS:
        errors.append(
            TrajectoryValidationError(
                source=source,
                path="algorithm",
                code="invalid_algorithm",
                message="algorithm must be one of: " + ", ".join(ALGORITHMS),
            )
        )
    elif algorithm != normalized_algorithm:
        errors.append(
            TrajectoryValidationError(
                source=source,
                path="algorithm",
                code="noncanonical_algorithm",
                message=f"algorithm must use canonical name {normalized_algorithm!r}",
            )
        )

    errors.extend(_validate_shared_types(step, source=source))
    if normalized_algorithm in ALGORITHM_REQUIRED_FIELDS:
        errors.extend(_validate_algorithm_fields(step, algorithm=normalized_algorithm, source=source))
    return sorted(errors)


def validate_trajectory_records(records: Sequence[tuple[dict[str, Any], str]]) -> dict[str, Any]:
    errors: list[TrajectoryValidationError] = []
    valid_algorithm_counts = {algorithm: 0 for algorithm in ALGORITHMS}
    for step, source in records:
        step_errors = validate_trajectory_step(step, source=source)
        errors.extend(step_errors)
        algorithm = step.get("algorithm") if isinstance(step, dict) else None
        if not step_errors and isinstance(algorithm, str):
            normalized = normalize_algorithm(algorithm)
            if normalized in valid_algorithm_counts:
                valid_algorithm_counts[normalized] += 1

    algorithms_validated = [algorithm for algorithm in ALGORITHMS if valid_algorithm_counts[algorithm] > 0]
    payload: dict[str, Any] = {
        "algorithms_validated": algorithms_validated,
        "by_algorithm": {algorithm: valid_algorithm_counts[algorithm] for algorithm in algorithms_validated},
        "error_count": len(errors),
        "errors": [error.to_dict() for error in sorted(errors)],
        "schema_version": SCHEMA_VERSION,
        "trajectory_count": len(records),
        "valid": not errors,
    }
    return payload


def validate_path(input_path: Path) -> dict[str, Any]:
    records, files = load_trajectory_records(input_path)
    payload = validate_trajectory_records(records)
    payload.update(
        {
            "file_count": len(files),
            "files": [str(path) for path in files],
            "input": str(input_path),
        }
    )
    return dict(sorted(payload.items()))


def load_trajectory_records(input_path: Path) -> tuple[list[tuple[dict[str, Any], str]], list[Path]]:
    if input_path.is_dir():
        files = sorted(path for path in input_path.rglob("*") if path.is_file() and path.suffix in SUPPORTED_SUFFIXES)
    elif input_path.is_file():
        files = [input_path]
    else:
        raise TrajectorySchemaError("missing_input", f"trajectory input path does not exist: {input_path}")
    if not files:
        raise TrajectorySchemaError(
            "no_trajectory_files",
            f"no JSON/JSONL trajectory files found under {input_path}",
            details={"supported_suffixes": list(SUPPORTED_SUFFIXES)},
        )

    records: list[tuple[dict[str, Any], str]] = []
    for path in files:
        records.extend(_load_records_from_file(path))
    return records, files


def _load_records_from_file(path: Path) -> list[tuple[dict[str, Any], str]]:
    if path.suffix == ".jsonl":
        return _load_jsonl_records(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise TrajectorySchemaError("json_parse_error", f"{path} is not valid JSON: {error}") from error
    return _extract_records(payload, source=str(path))


def _load_jsonl_records(path: Path) -> list[tuple[dict[str, Any], str]]:
    records: list[tuple[dict[str, Any], str]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError as error:
            raise TrajectorySchemaError(
                "json_parse_error", f"{path}:{line_number} is not valid JSON: {error}"
            ) from error
        records.extend(_extract_records(payload, source=f"{path}:{line_number}"))
    return records


def _extract_records(payload: Any, *, source: str) -> list[tuple[dict[str, Any], str]]:
    if isinstance(payload, dict) and isinstance(payload.get("steps"), list):
        return [(step, f"{source}#steps[{index}]") for index, step in enumerate(payload["steps"])]
    if isinstance(payload, list):
        return [(step, f"{source}[{index}]") for index, step in enumerate(payload)]
    if isinstance(payload, dict):
        return [(payload, source)]
    return [(payload, source)]


def _validate_shared_types(step: dict[str, Any], *, source: str) -> list[TrajectoryValidationError]:
    errors: list[TrajectoryValidationError] = []
    _require_string(step, "trajectory_id", source, errors)
    _require_string(step, "domain", source, errors)
    _require_string(step, "instance_id", source, errors)
    _require_string(step, "state_id", source, errors)
    _require_string_or_null(step, "selected_action", source, errors)
    _require_nonnegative_int(step, "step_index", source, errors)
    _require_bool(step, "is_terminal", source, errors)
    _require_object(step, "metadata", source, errors)
    for path in ("state_atoms", "goal_atoms", "legal_actions"):
        _require_string_list(step, path, source, errors)
    return errors


def _validate_algorithm_fields(step: dict[str, Any], *, algorithm: str, source: str) -> list[TrajectoryValidationError]:
    errors: list[TrajectoryValidationError] = []
    algorithm_payload = step.get(algorithm)
    if not isinstance(algorithm_payload, dict):
        errors.append(_missing(source, algorithm))
        return errors
    for field in ALGORITHM_REQUIRED_FIELDS[algorithm]:
        if field not in algorithm_payload:
            errors.append(_missing(source, f"{algorithm}.{field}"))
    if algorithm == "bfs":
        _validate_bfs_types(algorithm_payload, source, errors)
    elif algorithm == "fast_forward":
        _validate_fast_forward_types(algorithm_payload, source, errors)
    elif algorithm == "iterated_width":
        _validate_iterated_width_types(algorithm_payload, source, errors)
    elif algorithm == "graphplan":
        _validate_graphplan_types(algorithm_payload, source, errors)
    return errors


def _validate_bfs_types(payload: dict[str, Any], source: str, errors: list[TrajectoryValidationError]) -> None:
    for path in ("frontier_before", "frontier_after", "visited_before", "visited_after"):
        _require_list(payload, path, source, errors, prefix="bfs")
    _require_string(payload, "dequeued_state_id", source, errors, prefix="bfs")
    _require_list(payload, "successors", source, errors, prefix="bfs")


def _validate_fast_forward_types(payload: dict[str, Any], source: str, errors: list[TrajectoryValidationError]) -> None:
    _require_number(payload, "heuristic_value", source, errors, prefix="fast_forward")
    _require_list(payload, "successor_heuristics", source, errors, prefix="fast_forward")
    _require_string(payload, "selected_successor_id", source, errors, prefix="fast_forward")
    _require_string(payload, "tie_break_rule", source, errors, prefix="fast_forward")
    _require_object(payload, "relaxed_plan_metadata", source, errors, prefix="fast_forward")


def _validate_iterated_width_types(payload: dict[str, Any], source: str, errors: list[TrajectoryValidationError]) -> None:
    _require_positive_int(payload, "width", source, errors, prefix="iterated_width")
    _require_list(payload, "novelty_table_before", source, errors, prefix="iterated_width")
    _require_list(payload, "novelty_table_after", source, errors, prefix="iterated_width")
    _require_string(payload, "decision", source, errors, prefix="iterated_width")


def _validate_graphplan_types(payload: dict[str, Any], source: str, errors: list[TrajectoryValidationError]) -> None:
    _require_list(payload, "proposition_layers", source, errors, prefix="graphplan")
    _require_list(payload, "action_layers", source, errors, prefix="graphplan")
    _require_list(payload, "mutex_pairs", source, errors, prefix="graphplan")
    _require_object(payload, "extraction", source, errors, prefix="graphplan")


def _require_string(
    payload: dict[str, Any], path: str, source: str, errors: list[TrajectoryValidationError], *, prefix: str | None = None
) -> None:
    if path in payload and (not isinstance(payload[path], str) or not payload[path].strip()):
        _type_error(source, _path(prefix, path), "must be a non-empty string", errors)


def _require_string_or_null(
    payload: dict[str, Any], path: str, source: str, errors: list[TrajectoryValidationError], *, prefix: str | None = None
) -> None:
    if path in payload and payload[path] is not None and (not isinstance(payload[path], str) or not payload[path].strip()):
        _type_error(source, _path(prefix, path), "must be a non-empty string or null", errors)


def _require_string_list(
    payload: dict[str, Any], path: str, source: str, errors: list[TrajectoryValidationError], *, prefix: str | None = None
) -> None:
    if path not in payload:
        return
    value = payload[path]
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        _type_error(source, _path(prefix, path), "must be a list of non-empty strings", errors)


def _require_list(
    payload: dict[str, Any], path: str, source: str, errors: list[TrajectoryValidationError], *, prefix: str | None = None
) -> None:
    if path in payload and not isinstance(payload[path], list):
        _type_error(source, _path(prefix, path), "must be a list", errors)


def _require_object(
    payload: dict[str, Any], path: str, source: str, errors: list[TrajectoryValidationError], *, prefix: str | None = None
) -> None:
    if path in payload and not isinstance(payload[path], dict):
        _type_error(source, _path(prefix, path), "must be an object", errors)


def _require_bool(
    payload: dict[str, Any], path: str, source: str, errors: list[TrajectoryValidationError], *, prefix: str | None = None
) -> None:
    if path in payload and not isinstance(payload[path], bool):
        _type_error(source, _path(prefix, path), "must be a boolean", errors)


def _require_number(
    payload: dict[str, Any], path: str, source: str, errors: list[TrajectoryValidationError], *, prefix: str | None = None
) -> None:
    if path in payload and (not isinstance(payload[path], (int, float)) or isinstance(payload[path], bool)):
        _type_error(source, _path(prefix, path), "must be a number", errors)


def _require_nonnegative_int(
    payload: dict[str, Any], path: str, source: str, errors: list[TrajectoryValidationError], *, prefix: str | None = None
) -> None:
    if path in payload and (not isinstance(payload[path], int) or isinstance(payload[path], bool) or payload[path] < 0):
        _type_error(source, _path(prefix, path), "must be a non-negative integer", errors)


def _require_positive_int(
    payload: dict[str, Any], path: str, source: str, errors: list[TrajectoryValidationError], *, prefix: str | None = None
) -> None:
    if path in payload and (not isinstance(payload[path], int) or isinstance(payload[path], bool) or payload[path] <= 0):
        _type_error(source, _path(prefix, path), "must be a positive integer", errors)


def _missing(source: str, path: str) -> TrajectoryValidationError:
    return TrajectoryValidationError(
        source=source,
        path=path,
        code="missing_required_field",
        message=f"missing required field: {path}",
    )


def _type_error(source: str, path: str, message: str, errors: list[TrajectoryValidationError]) -> None:
    errors.append(TrajectoryValidationError(source=source, path=path, code="invalid_type", message=f"{path} {message}"))


def _path(prefix: str | None, path: str) -> str:
    return f"{prefix}.{path}" if prefix else path


def _canonicalize_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _canonicalize_json_value(value[key]) for key in sorted(value)}
    if isinstance(value, (set, frozenset)):
        return sorted((_canonicalize_json_value(item) for item in value), key=_json_sort_key)
    if isinstance(value, tuple):
        return [_canonicalize_json_value(item) for item in value]
    if isinstance(value, list):
        return [_canonicalize_json_value(item) for item in value]
    return value


def _canonicalize_bfs(payload: dict[str, Any]) -> dict[str, Any]:
    canonical = _canonicalize_json_value(payload)
    for field in ("visited_before", "visited_after"):
        if isinstance(canonical.get(field), list):
            canonical[field] = sorted(canonical[field], key=_json_sort_key)
    if isinstance(canonical.get("successors"), list):
        successors = []
        for successor in canonical["successors"]:
            if isinstance(successor, dict) and isinstance(successor.get("state_atoms"), list):
                successor = {**successor, "state_atoms": canonical_string_list(successor["state_atoms"])}
            successors.append(successor)
        canonical["successors"] = sorted(successors, key=_successor_sort_key)
    return canonical


def _canonicalize_fast_forward(payload: dict[str, Any]) -> dict[str, Any]:
    canonical = _canonicalize_json_value(payload)
    if isinstance(canonical.get("successor_heuristics"), list):
        canonical["successor_heuristics"] = sorted(canonical["successor_heuristics"], key=_heuristic_sort_key)
    return canonical


def _canonicalize_iterated_width(payload: dict[str, Any]) -> dict[str, Any]:
    canonical = _canonicalize_json_value(payload)
    for field in ("novelty_table_before", "novelty_table_after"):
        if field in canonical:
            canonical[field] = canonical_novelty_table(canonical[field])
    if isinstance(canonical.get("novel_item"), (list, tuple, set, frozenset)):
        canonical["novel_item"] = _canonical_novelty_entry(canonical["novel_item"])
    return canonical


def _canonicalize_graphplan(payload: dict[str, Any]) -> dict[str, Any]:
    canonical = _canonicalize_json_value(payload)
    if isinstance(canonical.get("mutex_pairs"), list):
        canonical["mutex_pairs"] = canonical_mutex_pairs(canonical["mutex_pairs"])
    for layer_field in ("proposition_layers", "action_layers"):
        if not isinstance(canonical.get(layer_field), list):
            continue
        layers = []
        for layer in canonical[layer_field]:
            if not isinstance(layer, dict):
                layers.append(layer)
                continue
            layer = dict(layer)
            for list_field in ("atoms", "actions", "propositions"):
                if isinstance(layer.get(list_field), list):
                    layer[list_field] = canonical_string_list(layer[list_field])
            if isinstance(layer.get("mutex_pairs"), list):
                layer["mutex_pairs"] = canonical_mutex_pairs(layer["mutex_pairs"])
            layers.append(dict(sorted(layer.items())))
        canonical[layer_field] = sorted(layers, key=_layer_sort_key)
    return canonical


def _canonical_novelty_entry(entry: Any) -> Any:
    if isinstance(entry, (list, tuple, set, frozenset)):
        return sorted(str(item) for item in entry)
    return str(entry)


def _json_sort_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _successor_sort_key(value: Any) -> tuple[str, str, str]:
    if not isinstance(value, dict):
        return ("", "", _json_sort_key(value))
    return (str(value.get("action", "")), str(value.get("state_id", "")), _json_sort_key(value))


def _heuristic_sort_key(value: Any) -> tuple[float, str, str, str]:
    if not isinstance(value, dict):
        return (float("inf"), "", "", _json_sort_key(value))
    heuristic = value.get("heuristic_value")
    numeric = float(heuristic) if isinstance(heuristic, (int, float)) and not isinstance(heuristic, bool) else float("inf")
    return (numeric, str(value.get("action", "")), str(value.get("state_id", "")), _json_sort_key(value))


def _layer_sort_key(value: Any) -> tuple[int, str]:
    if not isinstance(value, dict):
        return (10**9, _json_sort_key(value))
    index = value.get("layer_index", value.get("layer", 10**9))
    numeric = index if isinstance(index, int) and not isinstance(index, bool) else 10**9
    return (numeric, _json_sort_key(value))


__all__ = [
    "ALGORITHM_REQUIRED_FIELDS",
    "SCHEMA_VERSION",
    "SHARED_REQUIRED_FIELDS",
    "TrajectorySchemaError",
    "TrajectoryValidationError",
    "canonical_json_text",
    "canonical_mutex_pairs",
    "canonical_novelty_table",
    "canonical_string_list",
    "canonicalize_trajectory_step",
    "load_trajectory_records",
    "validate_path",
    "validate_trajectory_records",
    "validate_trajectory_step",
]
