"""Replay-bound Modality Observations with a shared semantic information boundary."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal, TypeAlias

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .best_first_controller import BestFirstController
from .best_first_model_input import build_best_first_live_model_input
from .pddl_state import CanonicalState, GroundedAction, PDDLStateAuthority
from .planimation_render import PlanimationRenderRequest, canonical_supplied_actions, produce_planimation_render


class ModalityParityError(ValueError):
    """An observation omits or contradicts authoritative task/search semantics."""


Relation: TypeAlias = tuple[str, str, tuple[str, ...]]
Modality: TypeAlias = Literal["text-state", "visual-state", "multimodal-state"]
MODALITIES: tuple[Modality, ...] = ("text-state", "visual-state", "multimodal-state")
TokenCounter: TypeAlias = Callable[[str, tuple[Path, ...]], int]
RELATION_LEGEND = (
    "Rows: section | predicate | ordered arguments. State and initial rows list all true dynamic facts; "
    "omitted dynamic facts are false. Static rows are always true. Goal rows are required together; "
    "unlisted goal facts are unconstrained. object_type rows declare objects. "
    "The relation panels are authoritative; scene geometry is illustrative."
)


@dataclass(frozen=True)
class ModalityInputLimits:
    """Caller-frozen processor and capacity contract; no throughput defaults."""

    tokenizer_id: str
    tokenizer_revision: str
    max_input_tokens: int
    image_width: int
    image_height: int
    font_size: int
    max_memory_bytes: int
    accepted_delta_limit: int
    input_size_bins: tuple[int, ...]
    font_name: str = "DejaVuSans.ttf"

    def __post_init__(self) -> None:
        if not self.tokenizer_id or not self.tokenizer_revision:
            raise ValueError("a frozen tokenizer identity and revision are required")
        if (
            min(
                self.max_input_tokens,
                self.image_width,
                self.image_height,
                self.font_size,
                self.max_memory_bytes,
                self.accepted_delta_limit,
            )
            <= 0
        ):
            raise ValueError("modality capacities must be positive")
        if (
            not self.input_size_bins
            or tuple(sorted(set(self.input_size_bins))) != self.input_size_bins
            or self.input_size_bins[0] <= 0
            or self.input_size_bins[-1] != self.max_input_tokens
        ):
            raise ValueError("input-size bins must increase and end at the frozen token limit")


@dataclass(frozen=True)
class SemanticModelInput:
    """One authoritative snapshot before one Typed Search Operation."""

    common_json: str
    state_relations: tuple[Relation, ...]
    goal_relations: tuple[Relation, ...]


@dataclass(frozen=True)
class RelationImage:
    """Drawing commands and their PNG, retained for semantic replay (not pixel comparison)."""

    path: Path
    relations: tuple[Relation, ...]
    source_frame: Path | None


@dataclass(frozen=True)
class ModalityObservation:
    modality: Modality
    prompt: str
    images: tuple[RelationImage, ...]
    input_tokens: int
    input_size_bin: int
    limits: ModalityInputLimits

    def messages(self) -> list[dict[str, Any]]:
        """Model-facing input only: no replay metadata, teacher labels, or future frames."""
        content: list[dict[str, Any]] = [{"type": "text", "text": self.prompt}]
        content.extend({"type": "image", "image": str(image.path)} for image in self.images)
        return [{"role": "user", "content": content}]


@dataclass(frozen=True)
class ReplayedFrames:
    """One supplied Action Sequence; repeated states use their first occurrence."""

    authority: PDDLStateAuthority
    states: tuple[CanonicalState, ...]
    frame_paths: tuple[Path, ...]

    def frame_for(self, state: CanonicalState) -> Path:
        try:
            return self.frame_paths[self.states.index(state)]
        except ValueError as error:
            raise ModalityParityError("state has no replay-bound frame") from error


def render_replayed_plan(request: PlanimationRenderRequest) -> ReplayedFrames:
    """Replay supplied actions before HTTP and bind each interpreted stage to its state.

    This validates Plan Interpretation and state/frame ordering, not the meaning
    of arbitrary animation-profile geometry. The complete relation layer below
    supplies explicit authoritative facts independently of that geometry.
    """

    authority = PDDLStateAuthority.from_pddl(request.domain_path.read_text(), request.problem_path.read_text())
    actions = canonical_supplied_actions(request.supplied_plan)
    state = authority.initial_state
    states = [state]
    for text in actions:
        parts = text[1:-1].split()
        action = GroundedAction(parts[0], tuple(parts[1:]))
        state = authority.apply(state, action).target_state
        states.append(state)
    result = produce_planimation_render(request)
    stages = json.loads(result.trace_path.read_text())["visualStages"]
    if (
        stages[0]["stageName"].strip().lower() != "initial stage"
        or canonical_supplied_actions(tuple(stage["stageName"] for stage in stages[1:])) != actions
    ):
        raise ModalityParityError("Plan Interpretation differs from supplied Action Sequence")
    if len(result.frame_paths) != len(states):
        raise ModalityParityError("rendered stages do not cover the replayed states")
    return ReplayedFrames(authority, tuple(states), result.frame_paths)


def render_replayed_paths(
    request: PlanimationRenderRequest,
    supplied_paths: Sequence[tuple[str, ...]],
) -> ReplayedFrames:
    """Cover branching search with supplied paths, each replayed from the initial state.

    Paths are ordered by length and canonical Action Sequence; the first occurrence
    wins, independently of caller ordering. Output subdirectories isolate each path.
    """
    paths = sorted(
        {canonical_supplied_actions(path) for path in supplied_paths},
        key=lambda path: (len(path), path),
    )
    if not paths:
        raise ModalityParityError("at least one supplied path is required")
    rendered = [
        render_replayed_plan(replace(request, supplied_plan=path, output_dir=request.output_dir / f"path-{index:06d}"))
        for index, path in enumerate(paths)
    ]
    return ReplayedFrames(
        rendered[0].authority,
        tuple(state for item in rendered for state in item.states),
        tuple(frame for item in rendered for frame in item.frame_paths),
    )


def best_first_semantic_input(controller: BestFirstController) -> SemanticModelInput:
    """Factor the current live input into modality content and identical Search Memory."""
    authority = controller.authority
    if authority.goal_atoms is None:
        raise ModalityParityError("partial-goal images currently require conjunctive positive STRIPS goals")
    raw = build_best_first_live_model_input(authority, controller)
    current = dict(raw["current"])
    state_relations = _relations("state", current.pop("state_atoms"))
    state = controller.node_state(controller.active_state_id or "")
    state_relations += _relations("state_fluent", state.fluents)
    state_relations += _relations("static", authority.static_initial_facts)
    state_relations += _relations("initial", authority.initial_state.atoms)
    state_relations += _relations("initial_fluent", authority.initial_state.fluents)
    state_relations += tuple(
        ("object_type", type_name, (obj,)) for type_name, objects in authority.objects_by_type for obj in objects
    )
    common = {
        "algorithm": raw["algorithm"],
        "current": current,
        "search_memory": {
            **raw["search_memory"],
            "accepted_deltas": raw["accepted_deltas"],
            "successor_candidates": raw["successor_candidates"],
        },
    }
    return SemanticModelInput(_json(common), tuple(sorted(state_relations)), _relations("goal", authority.goal_atoms))


def build_matched_best_first_observations(
    *,
    frames: ReplayedFrames,
    controller: BestFirstController,
    limits: ModalityInputLimits,
    token_counter: TokenCounter,
    output_dir: Path,
) -> tuple[ModalityObservation, ...]:
    """Produce the three inputs for one decision; never truncate required semantics.

    The counter must use the caller's frozen processor including image tokens.
    #70 supplies the governed episode runner; this boundary performs no search.
    """
    semantic = best_first_semantic_input(controller)
    memory = json.loads(semantic.common_json)["search_memory"]
    _validate_memory_capacity(memory, controller, limits)
    state = controller.node_state(controller.active_state_id or "")
    if frames.authority.task_context() != controller.authority.task_context():
        raise ModalityParityError("frames belong to a different authoritative task")
    source_frame = frames.frame_for(state)
    state_index = frames.states.index(state)
    images = (
        _draw_relations(semantic.state_relations, source_frame, output_dir / f"state-{state_index:06d}.png", limits),
        _draw_relations(semantic.goal_relations, None, output_dir / "goal.png", limits),
    )
    observations: list[ModalityObservation] = []
    for modality in MODALITIES:
        payload = json.loads(semantic.common_json)
        payload["representation"] = modality
        payload["relation_legend"] = RELATION_LEGEND
        if modality != "visual-state":
            payload["state"] = semantic.state_relations
            payload["goal"] = semantic.goal_relations
        selected_images = () if modality == "text-state" else images
        prompt = _json(payload)
        count = token_counter(prompt, tuple(image.path for image in selected_images))
        if count > limits.max_input_tokens:
            raise ModalityParityError(f"{modality} requires {count} tokens; limit is {limits.max_input_tokens}")
        observations.append(
            ModalityObservation(
                modality,
                prompt,
                selected_images,
                count,
                next(bound for bound in limits.input_size_bins if count <= bound),
                limits,
            )
        )
    result = tuple(observations)
    validate_modality_parity(result, controller=controller)
    return result


def validate_modality_parity(
    observations: Sequence[ModalityObservation],
    *,
    controller: BestFirstController,
) -> int:
    """Compare the exposed semantic drawing/text content against current trusted replay.

    This checks the meaning of exposed facts, goals, and Search Memory.
    It does not infer the semantics of arbitrary Planimation sprite geometry.
    """
    expected = best_first_semantic_input(controller)
    if tuple(item.modality for item in observations) != MODALITIES:
        raise ModalityParityError("parity requires one observation for each modality in canonical order")
    for item in observations:
        if item.limits != observations[0].limits:
            raise ModalityParityError("modalities must use identical fixed capacities")
        payload = json.loads(item.prompt)
        if payload.pop("representation") != item.modality:
            raise ModalityParityError("observation representation differs from its modality")
        if payload.pop("relation_legend") != RELATION_LEGEND:
            raise ModalityParityError("state or partial-goal interpretation differs across modalities")
        if item.modality != "visual-state":
            state_rows = _row_tuples(payload.pop("state"))
            goal_rows = _row_tuples(payload.pop("goal"))
            if state_rows != expected.state_relations or goal_rows != expected.goal_relations:
                raise ModalityParityError("text state or partial goal differs from authoritative replay")
        if item.modality != "text-state":
            if (
                len(item.images) != 2
                or item.images[0].relations != expected.state_relations
                or item.images[1].relations != expected.goal_relations
            ):
                raise ModalityParityError("visual state or partial goal differs from authoritative replay")
        elif item.images:
            raise ModalityParityError("text-state cannot include images")
        if _json(payload) != expected.common_json:
            raise ModalityParityError("visible Search Memory differs from authoritative replay")
        _validate_memory_capacity(payload["search_memory"], controller, item.limits)
    return len(observations)


def _validate_memory_capacity(
    memory: dict[str, Any],
    controller: BestFirstController,
    limits: ModalityInputLimits,
) -> None:
    if controller.accepted_delta_limit != limits.accepted_delta_limit:
        raise ModalityParityError("Search Memory accepted-delta capacity differs from the frozen contract")
    if len(_json(memory).encode()) > limits.max_memory_bytes:
        raise ModalityParityError("Search Memory exceeds the frozen byte capacity")


def _relations(section: str, facts: Sequence[str]) -> tuple[Relation, ...]:
    rows: list[Relation] = []
    for fact in sorted(facts):
        predicate, separator, tail = fact.partition("(")
        if not separator:
            rows.append((section, predicate, ()))
        elif tail.endswith(")"):
            rows.append((section, predicate, tuple(tail[:-1].split(","))))
        else:
            # Numeric fluents retain their full equation as the row label.
            rows.append((section, fact, ()))
    return tuple(rows)


def _row_tuples(rows: Any) -> tuple[Relation, ...]:
    return tuple((section, predicate, tuple(arguments)) for section, predicate, arguments in rows)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _draw_relations(
    relations: tuple[Relation, ...],
    source_frame: Path | None,
    path: Path,
    limits: ModalityInputLimits,
) -> RelationImage:
    font = ImageFont.truetype(limits.font_name, limits.font_size)
    canvas = Image.new("RGB", (limits.image_width, limits.image_height), "white")
    draw = ImageDraw.Draw(canvas)
    y = 16
    title = "STATE / TASK FACTS" if source_frame else "PARTIAL GOAL: all rows required; other facts unconstrained"
    if draw.textlength(title, font=font) > limits.image_width - 32:
        raise ModalityParityError("image width cannot fit the relation legend at the frozen font size")
    draw.text((16, y), title, fill="black", font=font)
    y += limits.font_size + 16
    row_height = limits.font_size + 16
    scene_height = limits.image_height // 4 if source_frame else 0
    if y + scene_height + 16 + max(1, len(relations)) * row_height > limits.image_height - 16:
        raise ModalityParityError("complete relation panel exceeds the frozen image height")
    if source_frame:
        with Image.open(source_frame) as scene:
            thumbnail = ImageOps.contain(scene.convert("RGB"), (limits.image_width - 32, limits.image_height // 4))
            canvas.paste(thumbnail, (16, y))
            y += thumbnail.height + 16
    if not relations:
        draw.text((16, y), "No constraints" if not source_frame else "No facts", fill="black", font=font)
    for section, predicate, arguments in relations:
        x = 16
        for index, label in enumerate((section, predicate, *arguments)):
            width = int(draw.textlength(label, font=font)) + 20
            if x + width > limits.image_width - 16:
                raise ModalityParityError("complete relation row exceeds the frozen image width")
            draw.rounded_rectangle(
                (x, y, x + width, y + row_height - 4),
                radius=4,
                fill=("#e8eef7" if index < 2 else "#fff1d6"),
                outline="#536174",
            )
            draw.text((x + 10, y + 4), label, fill="black", font=font)
            x += width + 8
        y += row_height
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path)
    return RelationImage(path, relations, source_frame)
