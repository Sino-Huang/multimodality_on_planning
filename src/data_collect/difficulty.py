"""Measured difficulty assignment helpers for curriculum data collection."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .hashing import strip_pddl_comments
from .metadata import AcceptedInstanceMetadata


DIFFICULTY_BUCKETS = ("easy", "medium", "hard")
_PLAN_LENGTH_KEYS = (
    "plan_length",
    "planlength",
    "trace_length",
    "solution_length",
    "solutionlength",
)
_FRAME_COUNT_KEYS = ("frame_count", "framecount", "png_count", "pngcount")
_OBJECT_COUNT_KEYS = ("object_count", "objectcount", "num_objects", "numobjects")
_GROUNDED_ACTION_COUNT_KEYS = (
    "grounded_action_count",
    "groundedactioncount",
    "grounded_actions",
    "groundedactions",
)
_PDDL_OBJECT_COUNT_KEYS = ("pddl_object_count", "pddlobjectcount")
_PDDL_PREDICATE_COUNT_KEYS = ("pddl_predicate_count", "pddlpredicatecount")


@dataclass(frozen=True)
class DifficultyMetrics:
    """Measured and fallback metrics used for curriculum bucketing."""

    plan_length: int | None = None
    frame_count: int | None = None
    object_count: int | None = None
    grounded_action_count: int | None = None
    pddl_object_count: int | None = None
    pddl_predicate_count: int | None = None

    def as_dict(self) -> dict[str, int | None]:
        return {
            "plan_length": self.plan_length,
            "frame_count": self.frame_count,
            "object_count": self.object_count,
            "grounded_action_count": self.grounded_action_count,
            "pddl_object_count": self.pddl_object_count,
            "pddl_predicate_count": self.pddl_predicate_count,
        }


@dataclass(frozen=True)
class DifficultyAssessment:
    """Resolved difficulty evidence for one accepted candidate."""

    candidate_id: str
    domain_id: str
    difficulty_target: str
    primary_metric_name: str
    primary_metric_value: int | None
    metrics: DifficultyMetrics
    sort_key: tuple[int, int, int, int, int, int, str]


def _normalize_key(value: str) -> str:
    return value.replace("-", "").replace("_", "").lower()


def _coerce_count(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    if isinstance(value, (list, tuple, set)):
        return len(value)
    return None


def _find_first_count(payload: Any, candidate_keys: Iterable[str]) -> int | None:
    normalized_keys = {_normalize_key(key) for key in candidate_keys}

    def visit(node: Any) -> int | None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if _normalize_key(str(key)) in normalized_keys:
                    resolved = _coerce_count(value)
                    if resolved is not None:
                        return resolved
                resolved = visit(value)
                if resolved is not None:
                    return resolved
        elif isinstance(node, list):
            for item in node:
                resolved = visit(item)
                if resolved is not None:
                    return resolved
        return None

    return visit(payload)


def _load_json_file(path: Path | None) -> Mapping[str, Any] | None:
    if path is None or not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, Mapping):
        return payload
    return None


def _extract_render_payload(instance: AcceptedInstanceMetadata) -> Mapping[str, Any]:
    render_payload = instance.extra.get("render", {})
    if isinstance(render_payload, Mapping):
        return render_payload
    return {}


def _resolve_trace_path(instance: AcceptedInstanceMetadata, render_payload: Mapping[str, Any]) -> Path | None:
    trace_path = render_payload.get("trace_path")
    if trace_path:
        return Path(str(trace_path))
    for artifact_path in instance.render_artifact_paths:
        if artifact_path.endswith("trace.vfg.json"):
            return Path(artifact_path)
    return None


def _resolve_frame_count(instance: AcceptedInstanceMetadata, render_payload: Mapping[str, Any]) -> int | None:
    explicit_count = _find_first_count(render_payload, _FRAME_COUNT_KEYS)
    if explicit_count is not None:
        return explicit_count
    png_paths = [path for path in instance.render_artifact_paths if path.lower().endswith(".png")]
    return len(png_paths) if png_paths else None


def _extract_visual_object_count(trace_payload: Mapping[str, Any] | None) -> int | None:
    if trace_payload is None:
        return None
    explicit_count = _find_first_count(trace_payload, _OBJECT_COUNT_KEYS)
    if explicit_count is not None:
        return explicit_count

    stages = trace_payload.get("visualStages")
    if not isinstance(stages, list):
        return None

    named_objects: set[str] = set()
    max_sprite_count = 0
    for stage in stages:
        if not isinstance(stage, Mapping):
            continue
        sprites = stage.get("visualSprites")
        if not isinstance(sprites, list):
            continue
        max_sprite_count = max(max_sprite_count, len(sprites))
        for sprite in sprites:
            if not isinstance(sprite, Mapping):
                continue
            label = sprite.get("name") or sprite.get("label")
            if label:
                named_objects.add(str(label))

    if named_objects:
        return len(named_objects)
    return max_sprite_count if max_sprite_count > 0 else None


def _extract_plan_length(trace_payload: Mapping[str, Any] | None, render_payload: Mapping[str, Any]) -> int | None:
    for payload in (render_payload, trace_payload):
        if payload is None:
            continue
        explicit_count = _find_first_count(payload, _PLAN_LENGTH_KEYS)
        if explicit_count is not None:
            return explicit_count

    if trace_payload is None:
        return None
    stages = trace_payload.get("visualStages")
    if isinstance(stages, list) and stages:
        return len(stages)
    return None


def _extract_grounded_action_count(trace_payload: Mapping[str, Any] | None, render_payload: Mapping[str, Any]) -> int | None:
    for payload in (render_payload, trace_payload):
        if payload is None:
            continue
        explicit_count = _find_first_count(payload, _GROUNDED_ACTION_COUNT_KEYS)
        if explicit_count is not None:
            return explicit_count
    return None


def _tokenize_pddl(text: str) -> list[str]:
    stripped = strip_pddl_comments(text)
    return stripped.replace("(", " ( ").replace(")", " ) ").split()


def _parse_sexpression(tokens: Sequence[str]) -> list[Any]:
    root: list[Any] = []
    stack: list[list[Any]] = [root]
    for token in tokens:
        if token == "(":
            node: list[Any] = []
            stack[-1].append(node)
            stack.append(node)
        elif token == ")":
            if len(stack) == 1:
                raise ValueError("Unbalanced PDDL: unexpected closing parenthesis")
            stack.pop()
        else:
            stack[-1].append(token)
    if len(stack) != 1:
        raise ValueError("Unbalanced PDDL: missing closing parenthesis")
    return root


def _walk_lists(node: Any) -> Iterable[list[Any]]:
    if isinstance(node, list):
        yield node
        for child in node:
            yield from _walk_lists(child)


def _read_text_if_exists(path_text: str) -> str | None:
    if not path_text:
        return None
    path = Path(path_text)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _count_problem_objects(problem_text: str | None) -> int | None:
    if not problem_text:
        return None
    try:
        parsed = _parse_sexpression(_tokenize_pddl(problem_text))
    except ValueError:
        return None

    for node in _walk_lists(parsed):
        if node and node[0] == ":objects":
            object_count = 0
            skip_next = False
            for token in node[1:]:
                if isinstance(token, list):
                    continue
                if skip_next:
                    skip_next = False
                    continue
                if token == "-":
                    skip_next = True
                    continue
                object_count += 1
            return object_count
    return None


def _count_domain_predicates(domain_text: str | None) -> int | None:
    if not domain_text:
        return None
    try:
        parsed = _parse_sexpression(_tokenize_pddl(domain_text))
    except ValueError:
        return None

    for node in _walk_lists(parsed):
        if node and node[0] == ":predicates":
            return sum(1 for predicate in node[1:] if isinstance(predicate, list) and predicate)
    return None


def extract_difficulty_metrics(instance: AcceptedInstanceMetadata) -> DifficultyMetrics:
    """Extract render- and PDDL-derived metrics for one accepted instance."""

    render_payload = _extract_render_payload(instance)
    trace_payload = _load_json_file(_resolve_trace_path(instance, render_payload))
    problem_text = _read_text_if_exists(instance.problem_path)
    domain_text = _read_text_if_exists(instance.domain_path)

    pddl_object_count = _find_first_count(render_payload, _PDDL_OBJECT_COUNT_KEYS)
    if pddl_object_count is None:
        pddl_object_count = _count_problem_objects(problem_text)

    pddl_predicate_count = _find_first_count(render_payload, _PDDL_PREDICATE_COUNT_KEYS)
    if pddl_predicate_count is None:
        pddl_predicate_count = _count_domain_predicates(domain_text)

    return DifficultyMetrics(
        plan_length=_extract_plan_length(trace_payload, render_payload),
        frame_count=_resolve_frame_count(instance, render_payload),
        object_count=_extract_visual_object_count(trace_payload),
        grounded_action_count=_extract_grounded_action_count(trace_payload, render_payload),
        pddl_object_count=pddl_object_count,
        pddl_predicate_count=pddl_predicate_count,
    )


def assess_instance_difficulty(instance: AcceptedInstanceMetadata) -> DifficultyAssessment:
    """Build the deterministic comparison key for one instance."""

    metrics = extract_difficulty_metrics(instance)
    metric_pairs = (
        ("plan_length", metrics.plan_length),
        ("frame_count", metrics.frame_count),
        ("object_count", metrics.object_count),
        ("grounded_action_count", metrics.grounded_action_count),
        ("pddl_object_count", metrics.pddl_object_count),
        ("pddl_predicate_count", metrics.pddl_predicate_count),
    )
    primary_metric_name = "unknown"
    primary_metric_value: int | None = None
    for name, value in metric_pairs:
        if value is not None:
            primary_metric_name = name
            primary_metric_value = value
            break

    sort_key = (
        metrics.plan_length if metrics.plan_length is not None else -1,
        metrics.frame_count if metrics.frame_count is not None else -1,
        metrics.object_count if metrics.object_count is not None else -1,
        metrics.grounded_action_count if metrics.grounded_action_count is not None else -1,
        metrics.pddl_object_count if metrics.pddl_object_count is not None else -1,
        metrics.pddl_predicate_count if metrics.pddl_predicate_count is not None else -1,
        instance.candidate_id,
    )
    return DifficultyAssessment(
        candidate_id=instance.candidate_id,
        domain_id=instance.domain_id,
        difficulty_target=instance.difficulty_target or instance.bucket,
        primary_metric_name=primary_metric_name,
        primary_metric_value=primary_metric_value,
        metrics=metrics,
        sort_key=sort_key,
    )


def _bucket_for_rank(rank: int, population_size: int) -> str:
    if population_size <= 0:
        raise ValueError("population_size must be positive")
    bucket_index = min(len(DIFFICULTY_BUCKETS) - 1, (rank * len(DIFFICULTY_BUCKETS)) // population_size)
    return DIFFICULTY_BUCKETS[bucket_index]


def _percentile_for_rank(rank: int, population_size: int) -> float:
    if population_size <= 0:
        raise ValueError("population_size must be positive")
    return round((rank + 0.5) / population_size, 6)


def hybrid_measured_percentile(instances: Sequence[AcceptedInstanceMetadata]) -> tuple[AcceptedInstanceMetadata, ...]:
    """Assign measured easy/medium/hard buckets per domain from render/PDDL metrics.

    The policy sorts accepted instances lexicographically by the available metrics
    in priority order:
    plan length, frame count, object count, grounded action count, then PDDL
    object count and predicate count. Instances are bucketed by per-domain
    percentile thirds, while `difficulty_target` preserves the generator preset
    used to create the candidate.
    """

    assessments_by_domain: dict[str, list[tuple[AcceptedInstanceMetadata, DifficultyAssessment]]] = defaultdict(list)
    for instance in instances:
        assessments_by_domain[instance.domain_id].append((instance, assess_instance_difficulty(instance)))

    annotated_by_candidate_id: dict[str, AcceptedInstanceMetadata] = {}
    for domain_id in sorted(assessments_by_domain):
        assessed_group = sorted(
            assessments_by_domain[domain_id],
            key=lambda pair: pair[1].sort_key,
        )
        group_size = len(assessed_group)
        for rank, (instance, assessment) in enumerate(assessed_group):
            measured_bucket = _bucket_for_rank(rank, group_size)
            percentile = _percentile_for_rank(rank, group_size)
            difficulty_payload = {
                "policy": "hybrid_measured_percentile",
                "domain_pool_size": group_size,
                "domain_rank": rank,
                "percentile": percentile,
                "primary_metric_name": assessment.primary_metric_name,
                "primary_metric_value": assessment.primary_metric_value,
                "metrics": assessment.metrics.as_dict(),
            }
            updated_extra = dict(instance.extra)
            updated_extra["difficulty"] = difficulty_payload
            annotated_by_candidate_id[instance.candidate_id] = replace(
                instance,
                difficulty_target=assessment.difficulty_target,
                difficulty_measured=measured_bucket,
                measured_bucket=measured_bucket,
                measured_difficulty=percentile,
                extra=updated_extra,
            )

    return tuple(annotated_by_candidate_id[instance.candidate_id] for instance in instances)


__all__ = [
    "DIFFICULTY_BUCKETS",
    "DifficultyAssessment",
    "DifficultyMetrics",
    "assess_instance_difficulty",
    "extract_difficulty_metrics",
    "hybrid_measured_percentile",
]
