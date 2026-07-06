from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Sequence

from .blocksworld import BlocksworldAction, BlocksworldProblem, parse_blocksworld
from .validate_instance import load_fixture, validate_fixture


ALGORITHMS: tuple[str, ...] = ("bfs", "fast_forward", "iterated_width", "graphplan")
MODALITIES: tuple[str, ...] = ("vision", "language", "vision_language", "vision_language_tool")
OUTPUT_REQUIRED_FIELDS: tuple[str, ...] = ("algorithm", "next_action", "internal_state_update", "confidence")
SCORE_LABEL_PASS = "Pass"
SCORE_LABEL_ALGORITHMIC_ERROR = "Algorithmic Error"
SCORE_LABEL_ACTION_ERROR = "Action Error"
SCORE_LABEL_PARSE_ERROR = "Parse Error"


ALGORITHM_DEFINITIONS: dict[str, str] = {
    "bfs": (
        "Breadth First Search: maintain a FIFO queue of states. Dequeue the front state; "
        "if it satisfies the goal, return. Otherwise enqueue all valid successor states and repeat."
    ),
    "fast_forward": (
        "Fast Forward: compute a delete-relaxation heuristic by ignoring negative effects, "
        "estimate distance to the goal, and greedily expand the most promising state."
    ),
    "iterated_width": (
        "Iterated Width: maintain a novelty table. For width k, expand a state only if it "
        "introduces a new k-atom conjunction not seen before; increase k when needed."
    ),
    "graphplan": (
        "Graphplan: build proposition layers from the initial layer, add action/proposition layers, "
        "track mutex relations for incompatible propositions, and stop when non-mutex goals appear."
    ),
}


ALGORITHM_CONTRACTS: dict[str, dict[str, Any]] = {
    "bfs": {
        "contract_id": "bfs_fifo_frontier_step",
        "description": "The update must describe FIFO dequeue/enqueue behavior for the frontier queue.",
        "required_terms": ["fifo", "queue", "dequeue", "enqueue"],
    },
    "fast_forward": {
        "contract_id": "ff_delete_relaxation_heuristic_step",
        "description": "The update must describe delete-relaxation heuristic estimation and greedy selection.",
        "required_terms": ["delete-relaxation", "heuristic", "greedy"],
    },
    "iterated_width": {
        "contract_id": "iw_novelty_width_step",
        "description": "The update must describe width-based novelty checking before expansion.",
        "required_terms": ["novelty", "width", "new"],
    },
    "graphplan": {
        "contract_id": "graphplan_layer_mutex_step",
        "description": "The update must describe proposition layers and mutex tracking.",
        "required_terms": ["proposition", "layer", "mutex"],
    },
}


class ZeroShotError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


def normalize_algorithm(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    aliases = {"ff": "fast_forward", "fastforward": "fast_forward", "iw": "iterated_width"}
    return aliases.get(normalized, normalized)


def validate_algorithms(values: Sequence[str]) -> tuple[str, ...]:
    algorithms = tuple(normalize_algorithm(value) for value in values)
    unknown = sorted(set(algorithms) - set(ALGORITHMS))
    if unknown:
        raise ZeroShotError("unknown_algorithm", f"unsupported algorithms: {', '.join(unknown)}")
    return algorithms


def validate_modalities(values: Sequence[str]) -> tuple[str, ...]:
    modalities = tuple(value.strip().lower() for value in values)
    unknown = sorted(set(modalities) - set(MODALITIES))
    if unknown:
        raise ZeroShotError("unknown_modality", f"unsupported modalities: {', '.join(unknown)}")
    return modalities


def load_validated_problem(fixture_path: Path) -> tuple[dict[str, Any], BlocksworldProblem]:
    validation = validate_fixture(fixture_path, min_plan_length=2, require_non_empty_goal=True)
    fixture = load_fixture(fixture_path)
    problem = parse_blocksworld(fixture.domain_pddl, fixture.problem_pddl)
    if isinstance(fixture.payload.get("instance_id"), str):
        validation = {**validation, "instance_id": fixture.payload["instance_id"]}
    return validation, problem


def build_prompt_package(
    *,
    fixture_path: Path,
    fixture_summary: dict[str, Any],
    problem: BlocksworldProblem,
    algorithm: str,
    modality: str,
) -> dict[str, Any]:
    algorithm = normalize_algorithm(algorithm)
    if algorithm not in ALGORITHMS:
        raise ZeroShotError("unknown_algorithm", f"unsupported algorithm: {algorithm}")
    if modality not in MODALITIES:
        raise ZeroShotError("unknown_modality", f"unsupported modality: {modality}")

    instance_id = str(fixture_summary.get("instance_id") or problem.problem_name)
    package_id = f"{instance_id}__{algorithm}__{modality}"
    legal_actions = list(problem.legal_action_strings(problem.initial_atoms))
    model_facing = _build_model_facing(problem=problem, algorithm=algorithm, modality=modality)
    gold_metadata = _build_gold_metadata(
        fixture_path=fixture_path,
        fixture_summary=fixture_summary,
        problem=problem,
        algorithm=algorithm,
        modality=modality,
        legal_actions=legal_actions,
    )
    return {
        "algorithm": algorithm,
        "domain": "blocksworld",
        "gold_scoring_metadata": gold_metadata,
        "instance_id": instance_id,
        "modality_boundary_note": "Only model_facing is intended for model prompts; gold_scoring_metadata is evaluator-only.",
        "modality": modality,
        "model_facing": model_facing,
        "package_id": package_id,
        "schema_version": "zero_shot_prompt_package_v1",
    }


def build_prompt_packages(
    *,
    fixture_path: Path,
    algorithms: Sequence[str] = ALGORITHMS,
    modalities: Sequence[str] = MODALITIES,
) -> list[dict[str, Any]]:
    selected_algorithms = validate_algorithms(algorithms)
    selected_modalities = validate_modalities(modalities)
    fixture_summary, problem = load_validated_problem(fixture_path)
    return [
        build_prompt_package(
            fixture_path=fixture_path,
            fixture_summary=fixture_summary,
            problem=problem,
            algorithm=algorithm,
            modality=modality,
        )
        for algorithm in selected_algorithms
        for modality in selected_modalities
    ]


def write_prompt_packages(packages: Sequence[dict[str, Any]], output_dir: Path) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[dict[str, Any]] = []
    for package in packages:
        package_id = str(package["package_id"])
        path = output_dir / f"{package_id}.json"
        path.write_text(json.dumps(package, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(
            {
                "algorithm": package["algorithm"],
                "modality": package["modality"],
                "package_id": package_id,
                "path": str(path),
            }
        )
    return written


def leakage_errors_for_package(package: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    modality = package.get("modality")
    model_facing = package.get("model_facing")
    if not isinstance(model_facing, dict):
        return [f"{package.get('package_id', '<unknown>')}: model_facing must be an object"]

    flattened = json.dumps(model_facing, sort_keys=True).lower()
    field_paths = set(_field_paths(model_facing))
    package_id = str(package.get("package_id", "<unknown>"))

    if modality == "vision":
        forbidden_field_fragments = (
            "pddl",
            "state_atoms",
            "goal_atoms",
            "state_id",
            "symbolic_goal",
            "objects",
            "legal_actions",
            "natural_language_goal",
        )
        for path in sorted(field_paths):
            if any(fragment in path.lower() for fragment in forbidden_field_fragments):
                errors.append(f"{package_id}: vision model_facing leaks symbolic field {path}")
        forbidden_text_patterns = (
            r"\b(clear|holding|on-table|on|arm-empty)\s*\(",
            r"\b[0-9a-f]{64}\b",
        )
        for pattern in forbidden_text_patterns:
            if re.search(pattern, flattened):
                errors.append(f"{package_id}: vision model_facing leaks symbolic text matching {pattern}")

    if modality == "language":
        forbidden_field_fragments = ("render", "image", "frame")
        for path in sorted(field_paths):
            if any(fragment in path.lower() for fragment in forbidden_field_fragments):
                errors.append(f"{package_id}: language model_facing leaks visual field {path}")
    return errors


def leakage_errors_for_packages(packages: Iterable[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for package in packages:
        errors.extend(leakage_errors_for_package(package))
    return errors


def validate_model_output_payload(payload: Any) -> dict[str, Any]:
    try:
        model_output = extract_model_output(payload)
    except ZeroShotError as error:
        return _schema_result(False, error.code, str(error), error.details)

    missing = [field for field in OUTPUT_REQUIRED_FIELDS if field not in model_output]
    if missing:
        return _schema_result(False, "missing_required_fields", "model output is missing required fields", {"missing": missing})

    field_errors: list[str] = []
    algorithm = model_output.get("algorithm")
    if not isinstance(algorithm, str) or normalize_algorithm(algorithm) not in ALGORITHMS:
        field_errors.append("algorithm must be one of the locked zero-shot algorithms")
    if not isinstance(model_output.get("next_action"), str) or not model_output.get("next_action", "").strip():
        field_errors.append("next_action must be a non-empty string")
    if not isinstance(model_output.get("internal_state_update"), str) or not model_output.get(
        "internal_state_update", ""
    ).strip():
        field_errors.append("internal_state_update must be a non-empty string")
    confidence = model_output.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or confidence < 0 or confidence > 1:
        field_errors.append("confidence must be a number in [0.0, 1.0]")
    if field_errors:
        return _schema_result(False, "schema_error", "model output failed schema checks", {"field_errors": field_errors})
    return {
        "valid": True,
        "syntactic_validity": True,
        "required_fields": list(OUTPUT_REQUIRED_FIELDS),
        "model_output": {
            "algorithm": normalize_algorithm(str(model_output["algorithm"])),
            "confidence": float(model_output["confidence"]),
            "internal_state_update": str(model_output["internal_state_update"]),
            "next_action": str(model_output["next_action"]),
        },
    }


def extract_model_output(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and "model_output_text" in payload:
        text = payload["model_output_text"]
        if not isinstance(text, str):
            raise ZeroShotError("model_output_text_not_string", "model_output_text must be a string")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as error:
            raise ZeroShotError("json_parse_error", f"model output is not parseable JSON: {error}") from error
        if not isinstance(parsed, dict):
            raise ZeroShotError("model_output_not_object", "parsed model output must be a JSON object")
        return parsed
    if isinstance(payload, dict) and "model_output" in payload:
        model_output = payload["model_output"]
        if not isinstance(model_output, dict):
            raise ZeroShotError("model_output_not_object", "model_output must be a JSON object")
        return model_output
    if isinstance(payload, dict):
        return payload
    raise ZeroShotError("model_output_not_object", "model output must be a JSON object")


def score_model_output_payload(payload: dict[str, Any]) -> dict[str, Any]:
    schema = validate_model_output_payload(payload)
    if not schema["valid"]:
        return {
            "action_validity": False,
            "algorithm": _expected_algorithm(payload),
            "algorithmic_fidelity": False,
            "details": schema.get("error", {}),
            "score_label": SCORE_LABEL_PARSE_ERROR,
            "syntactic_validity": False,
        }

    model_output = schema["model_output"]
    metadata = extract_gold_metadata(payload)
    expected_algorithm = normalize_algorithm(str(metadata["algorithm"]))
    action_validity, action_details = _action_validity(model_output["next_action"], metadata.get("legal_actions", []))
    algorithmic_fidelity, algorithmic_details = _algorithmic_fidelity(
        model_output=model_output,
        expected_algorithm=expected_algorithm,
        contract=metadata.get("algorithm_contract", {}),
    )

    if not action_validity:
        score_label = SCORE_LABEL_ACTION_ERROR
    elif not algorithmic_fidelity:
        score_label = SCORE_LABEL_ALGORITHMIC_ERROR
    else:
        score_label = SCORE_LABEL_PASS

    return {
        "action_validity": action_validity,
        "action_validity_details": action_details,
        "algorithm": expected_algorithm,
        "algorithmic_fidelity": algorithmic_fidelity,
        "algorithmic_fidelity_details": algorithmic_details,
        "model_output": model_output,
        "score_label": score_label,
        "syntactic_validity": True,
    }


def extract_gold_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("gold_scoring_metadata")
    if metadata is None and isinstance(payload.get("package"), dict):
        metadata = payload["package"].get("gold_scoring_metadata")
    if not isinstance(metadata, dict):
        raise ZeroShotError("missing_gold_metadata", "score input is missing gold_scoring_metadata")
    algorithm = metadata.get("algorithm")
    if not isinstance(algorithm, str) or normalize_algorithm(algorithm) not in ALGORITHMS:
        raise ZeroShotError("invalid_gold_algorithm", "gold_scoring_metadata.algorithm is invalid")
    if not isinstance(metadata.get("legal_actions"), list):
        raise ZeroShotError("invalid_gold_legal_actions", "gold_scoring_metadata.legal_actions must be a list")
    if not isinstance(metadata.get("algorithm_contract"), dict):
        raise ZeroShotError("invalid_gold_contract", "gold_scoring_metadata.algorithm_contract must be an object")
    return metadata


def _build_model_facing(*, problem: BlocksworldProblem, algorithm: str, modality: str) -> dict[str, Any]:
    base: dict[str, Any] = {
        "algorithm_definition": ALGORITHM_DEFINITIONS[algorithm],
        "output_format": {
            "algorithm": algorithm,
            "confidence": "number from 0.0 to 1.0",
            "internal_state_update": "one-step planner-state update for the requested algorithm",
            "next_action": "pickup(X), putdown(X), stack(X,Y), or unstack(X,Y)",
        },
        "system": f"You are executing {algorithm} on one Blocksworld task.",
        "task_instruction": f"Execute the next step of {algorithm} and respond only with JSON.",
    }
    if modality == "vision":
        base["visual_input"] = {
            "kind": "rendered_blocksworld_observation",
            "render_paths": [],
            "text": "Use only the visual observation supplied by the evaluator.",
        }
        return base

    language_input = {
        "action_vocabulary": list(problem.action_vocabulary),
        "current_state_atoms": sorted(problem.initial_atoms),
        "goal_atoms": sorted(problem.goal_atoms),
        "natural_language_goal": _natural_language_goal(problem.goal_atoms),
        "objects": list(problem.objects),
    }
    if modality == "language":
        base["language_input"] = language_input
        return base
    if modality in {"vision_language", "vision_language_tool"}:
        base["visual_input"] = {
            "kind": "rendered_blocksworld_observation",
            "render_paths": [],
            "text": "Use this visual observation together with the symbolic task text.",
        }
        base["language_input"] = language_input
    if modality == "vision_language_tool":
        base["tool_input"] = _scratchpad_state(problem, algorithm)
    return base


def _build_gold_metadata(
    *,
    fixture_path: Path,
    fixture_summary: dict[str, Any],
    problem: BlocksworldProblem,
    algorithm: str,
    modality: str,
    legal_actions: list[str],
) -> dict[str, Any]:
    return {
        "algorithm": algorithm,
        "algorithm_contract": ALGORITHM_CONTRACTS[algorithm],
        "current_state_atoms": sorted(problem.initial_atoms),
        "current_state_id": problem.state_id(problem.initial_atoms),
        "fixture": str(fixture_path),
        "goal_atoms": sorted(problem.goal_atoms),
        "initial_legal_action_count": len(legal_actions),
        "legal_actions": legal_actions,
        "modality": modality,
        "problem_name": problem.problem_name,
        "shortest_plan_length": fixture_summary.get("shortest_plan_length"),
    }


def _field_paths(value: Any, prefix: str = "") -> Iterable[str]:
    if isinstance(value, dict):
        for key, nested in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield path
            yield from _field_paths(nested, path)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            yield from _field_paths(nested, f"{prefix}[{index}]")


def _natural_language_goal(goal_atoms: Iterable[str]) -> str:
    atoms = sorted(goal_atoms)
    if not atoms:
        return "No goal atoms are specified."
    return "Achieve these Blocksworld goal atoms: " + ", ".join(atoms) + "."


def _scratchpad_state(problem: BlocksworldProblem, algorithm: str) -> dict[str, Any]:
    current_id = problem.state_id(problem.initial_atoms)
    if algorithm == "bfs":
        return {"queue": [current_id], "visited": [current_id]}
    if algorithm == "fast_forward":
        return {"heuristic_values": {current_id: len(problem.goal_atoms)}, "selected_state_id": current_id}
    if algorithm == "iterated_width":
        return {"novelty_table": sorted(problem.initial_atoms), "width": 1}
    return {"mutexes": [], "proposition_layers": [{"atoms": sorted(problem.initial_atoms), "layer": 0}]}


def _schema_result(valid: bool, code: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "error": {"code": code, "details": details, "message": message},
        "required_fields": list(OUTPUT_REQUIRED_FIELDS),
        "syntactic_validity": False,
        "valid": valid,
    }


def _expected_algorithm(payload: Any) -> str | None:
    if isinstance(payload, dict):
        metadata = payload.get("gold_scoring_metadata")
        if metadata is None and isinstance(payload.get("package"), dict):
            metadata = payload["package"].get("gold_scoring_metadata")
        if isinstance(metadata, dict) and isinstance(metadata.get("algorithm"), str):
            return normalize_algorithm(metadata["algorithm"])
    return None


def _action_validity(action_text: str, legal_actions: Any) -> tuple[bool, dict[str, Any]]:
    legal_action_strings = sorted(str(action) for action in legal_actions)
    parsed = _parse_action(action_text)
    if parsed is None:
        return False, {"legal_actions": legal_action_strings, "reason": "next_action is not a supported action string"}
    serialized = parsed.serialize()
    return serialized in legal_action_strings, {"legal_actions": legal_action_strings, "next_action": serialized}


def _parse_action(action_text: str) -> BlocksworldAction | None:
    match = re.fullmatch(r"\s*([A-Za-z_-]+)\(([^()]*)\)\s*", action_text)
    if match is None:
        return None
    name = match.group(1).strip().lower().replace("-", "_")
    args = tuple(part.strip().lower() for part in match.group(2).split(",") if part.strip())
    try:
        return BlocksworldAction(name, args)
    except ValueError:
        return None


def _algorithmic_fidelity(
    *, model_output: dict[str, Any], expected_algorithm: str, contract: dict[str, Any]
) -> tuple[bool, dict[str, Any]]:
    output_algorithm = normalize_algorithm(str(model_output.get("algorithm", "")))
    if output_algorithm != expected_algorithm:
        return False, {"expected_algorithm": expected_algorithm, "model_algorithm": output_algorithm, "reason": "algorithm mismatch"}
    update = str(model_output.get("internal_state_update", "")).lower()
    required_terms = [str(term).lower() for term in contract.get("required_terms", [])]
    missing_terms = [term for term in required_terms if term not in update]
    return not missing_terms, {"contract_id": contract.get("contract_id"), "missing_terms": missing_terms}


__all__ = [
    "ALGORITHM_CONTRACTS",
    "ALGORITHM_DEFINITIONS",
    "ALGORITHMS",
    "MODALITIES",
    "OUTPUT_REQUIRED_FIELDS",
    "SCORE_LABEL_ACTION_ERROR",
    "SCORE_LABEL_ALGORITHMIC_ERROR",
    "SCORE_LABEL_PARSE_ERROR",
    "SCORE_LABEL_PASS",
    "ZeroShotError",
    "build_prompt_package",
    "build_prompt_packages",
    "extract_gold_metadata",
    "extract_model_output",
    "leakage_errors_for_package",
    "leakage_errors_for_packages",
    "load_validated_problem",
    "normalize_algorithm",
    "score_model_output_payload",
    "validate_algorithms",
    "validate_modalities",
    "validate_model_output_payload",
    "write_prompt_packages",
]
