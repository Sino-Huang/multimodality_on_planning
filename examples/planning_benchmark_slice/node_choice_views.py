"""Text / visual / multimodal observations for the node-choice contract (#146).

Every observation type exposes the same semantics: the static task context, the
initial state, the partial-goal constraints and one entry per live open-list
node in the seeded permuted menu order. Only the channel differs:

- ``text``: the #72 fact blocks as text lines (``label: facts``); each menu
  node carries its state's fact lines.
- ``visual``: the frozen #132 layout (static-context pages, the unlabelled
  128px initial-state scene, one unlabelled 128px scene per menu node labelled
  ``frontier-choice (label c<i>)``, partial-goal pages).
- ``multimodal``: the text payload plus the visual pages.

No state identifiers, depth, serials, scores, novelty or search history appear
in any type; menu labels carry no order information (the per-decision seeded
permutation). The complete input token count is measured with the frozen
Qwen3-VL processor; the session's overflow rule consumes it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from .choice_frontier import CHOICE_LEGEND
from .choice_frontier_views import CONTEXT_TOKENS, OUTPUT_TOKENS, ChoiceFrontierTaskViews, choice_label
from .modality_pages import PAGE_SIZE, fact_blocks
from .modality_view_preparation import frozen_processor
from .node_choice import NODE_CHOICE_SCHEMA, OBSERVATIONS, REPRESENTATIONS, SYSTEM_MESSAGES, TokenCounter
from .pddl_state import CanonicalState, PDDLStateAuthority
from .scene_only_views import SCENE_SIZE, static_blocks
from .source_goal import source_task

TOKEN_LIMIT = CONTEXT_TOKENS - OUTPUT_TOKENS
_MENU_TAIL = (
    "The frontier menu lists one choice label per live frontier state, unscored, in a seeded permuted order; "
    "no state identifiers, scalar search values, scores, membership flags, search memory, accepted deltas or "
    "search history are provided. The policy selects which frontier state the trusted runtime expands next; "
    "selecting the goal state solves the task."
)
_GOAL_NOTE = (
    "Goal constraints do not describe a complete solved state: unspecified facts are unconstrained. Goal blocks "
    "ALL, ANY, NOT, FOR EVERY and THERE EXISTS retain their labelled variable scopes. "
)
TEXT_LEGEND = (
    "The static task context, the initial state and the partial-goal constraints are given as text fact blocks "
    "(label: facts). frontier_menu.states gives one fact list per frontier state in menu order. "
    + _GOAL_NOTE
    + _MENU_TAIL
)
MULTIMODAL_LEGEND = (
    "The static task context, the initial state and the partial-goal constraints are given as text fact blocks "
    "(label: facts), and frontier_menu.states gives one fact list per frontier state in menu order. The same "
    "static-context and partial-goal pages, the unlabelled 128px initial-state scene and one unlabelled 128px "
    "scene per frontier state in menu order, each labelled frontier-choice (label c<i>), are attached. Black "
    "robot silhouettes identify the agent. " + _GOAL_NOTE + _MENU_TAIL
)
LEGENDS = {"text": TEXT_LEGEND, "visual": CHOICE_LEGEND, "multimodal": MULTIMODAL_LEGEND}
_BASE_KEYS = frozenset({"algorithm", "frontier_menu", "representation", "schema_version", "view_legend"})
_TEXT_KEYS = frozenset({"static_context", "initial_state", "goal_constraints"})
PAYLOAD_KEYS = {"text": _BASE_KEYS | _TEXT_KEYS, "visual": _BASE_KEYS, "multimodal": _BASE_KEYS | _TEXT_KEYS}
MENU_KEYS = {
    "text": frozenset({"choices", "states"}),
    "visual": frozenset({"choices"}),
    "multimodal": frozenset({"choices", "states"}),
}


def _lines(blocks: list[dict[str, str]]) -> list[str]:
    return [f"{block['label']}: {block['text']}" for block in blocks]


@dataclass(frozen=True)
class TextContext:
    """Per-task fact blocks shared by every decision (text and multimodal)."""

    task_context: dict[str, Any]
    source: dict[str, Any]
    static_context: list[str]
    initial_state: list[str]
    goal_constraints: list[str]
    _facts: dict[tuple, list[str]] = field(default_factory=dict, compare=False, repr=False)

    def state_facts(self, state: Any) -> list[str]:
        """Fact lines of a state (any object with ``atoms`` and ``fluents``)."""

        key = (tuple(state.atoms), tuple(state.fluents))
        facts = self._facts.get(key)
        if facts is None:
            state_view = {"atoms": list(state.atoms), "fluents": list(state.fluents)}
            facts = _lines(fact_blocks(self.task_context, state_view, self.source)["current-state"])
            self._facts[key] = facts
        return list(facts)


def text_context(authority: PDDLStateAuthority, domain_pddl: str, problem_pddl: str) -> TextContext:
    source = source_task(domain_pddl, problem_pddl)
    context = authority.task_context()
    initial = authority.initial_state
    blocks = fact_blocks(context, {"atoms": list(initial.atoms), "fluents": list(initial.fluents)}, source)
    return TextContext(
        task_context=context,
        source=source,
        static_context=_lines(static_blocks(blocks)),
        initial_state=_lines(blocks["current-state"]),
        goal_constraints=_lines(blocks["goal"]),
    )


def node_payload(
    model_input: dict[str, Any], observation: str, context: TextContext | None, menu_states: list[CanonicalState]
) -> dict[str, Any]:
    """The frozen payload for one decision, fail-closed on key drift."""

    if observation not in OBSERVATIONS:
        raise ValueError(f"node-choice observation is invalid: {observation}")
    if model_input.get("schema_version") != NODE_CHOICE_SCHEMA:
        raise ValueError("node-choice observation input schema differs")
    if model_input.get("representation") != REPRESENTATIONS[observation]:
        raise ValueError("node-choice representation differs from the observation type")
    choices = list(model_input["frontier_menu"]["choices"])
    if len(choices) != len(menu_states):
        raise ValueError("node-choice menu labels and states differ in length")
    payload = {**model_input, "view_legend": LEGENDS[observation]}
    if observation != "visual":
        if context is None:
            raise ValueError("text node-choice observations need the task text context")
        payload["frontier_menu"] = {
            "choices": choices,
            "states": [
                {"choice": choice, "facts": context.state_facts(state)}
                for choice, state in zip(choices, menu_states, strict=True)
            ],
        }
        payload["static_context"] = context.static_context
        payload["initial_state"] = context.initial_state
        payload["goal_constraints"] = context.goal_constraints
    if set(payload) != PAYLOAD_KEYS[observation] or set(payload["frontier_menu"]) != MENU_KEYS[observation]:
        raise ValueError("node-choice payload keys differ from the frozen contract")
    return payload


def build_node_observation(
    *,
    algorithm: str,
    observation: str,
    payload: dict[str, Any],
    static_pages: list[str],
    goal_pages: list[str],
    scene_path: Callable[[int], str] | None,
    menu_indices: list[int] | None,
    loader: Callable[[str, str], Any] | None = None,
) -> dict[str, Any]:
    """System + payload text (+ role-labelled pages for visual/multimodal) and its exact token count."""

    user_text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
    pages: list[tuple[str, Any]] = []
    sizes: list[tuple[int, int]] = []
    bindings: list[list] = []
    if observation != "text":
        if scene_path is None or menu_indices is None:
            raise ValueError("pixel-bearing node-choice observations need scene bindings")

        def image_of(label: str, path: str):
            return path if loader is None else loader(label, path)

        for i, path in enumerate(static_pages):
            pages.append(("task-context", image_of("task-context", path)))
            sizes.append(PAGE_SIZE)
            bindings.append(["task-context", None, i])
        pages.append(("initial-state", image_of("initial-state", scene_path(0))))
        sizes.append((SCENE_SIZE, SCENE_SIZE))
        bindings.append(["initial-state", 0, 0])
        for choice, state_index in zip(payload["frontier_menu"]["choices"], menu_indices, strict=True):
            label = choice_label(choice)
            pages.append((label, image_of(label, scene_path(state_index))))
            sizes.append((SCENE_SIZE, SCENE_SIZE))
            bindings.append(["frontier-choice", state_index, 0])
        for i, path in enumerate(goal_pages):
            pages.append(("goal", image_of("goal", path)))
            sizes.append(PAGE_SIZE)
            bindings.append(["goal", None, i])
        for label, image in pages:
            content.extend([{"type": "text", "text": f"Page role: {label}"}, {"type": "image", "image": image}])
    messages = [{"role": "system", "content": SYSTEM_MESSAGES[algorithm]}, {"role": "user", "content": content}]
    count = frozen_processor().count(messages, image_sizes=sizes)
    return {
        "messages": messages,
        "images": [image for _, image in pages],
        "image_sizes": sizes,
        "page_roles": [label for label, _ in pages],
        "binding": {
            "menu_size": len(payload["frontier_menu"]["choices"]),
            "input_pages": bindings,
            "input_tokens": count,
            "observation": observation,
            "state_representation": REPRESENTATIONS[observation],
        },
    }


def placeholder_counter(
    algorithm: str, observation: str, context: TextContext | None, page_counts: tuple[int, int]
) -> TokenCounter:
    """CPU token counter with placeholder page paths (pixels never read; sizes are fixed)."""

    static_count, goal_count = page_counts

    def count(model_input: dict[str, Any], menu_states: list[CanonicalState]) -> int:
        payload = node_payload(model_input, observation, context, menu_states)
        return build_node_observation(
            algorithm=algorithm,
            observation=observation,
            payload=payload,
            static_pages=["static"] * static_count,
            goal_pages=["goal"] * goal_count,
            scene_path=lambda index: f"scenes/state-{index:06d}.png",
            menu_indices=list(range(1, len(menu_states) + 1)),
        )["binding"]["input_tokens"]

    return count


class NodeChoiceTaskViews(ChoiceFrontierTaskViews):
    """Live panel views (retained scenes + on-demand renders) under the node-choice contract."""

    def __init__(self, root, task, output, endpoint, *, read_only=False):
        super().__init__(root, task, output, endpoint, read_only=read_only)
        from .scene_assets import read_json

        source = read_json(root / self.row["task_path"])
        self.text = text_context(self.authority, source["domain_pddl"], source["problem_pddl"])

    def page_counts(self) -> tuple[int, int]:
        native = self.scene_views.tasks[self.row["task_id"]]
        return len(native["static_pages"]), len(native["goal_pages"])

    def observe_nodes(
        self,
        algorithm: str,
        observation: str,
        model_input: dict[str, Any],
        menu_states: list[CanonicalState],
        *,
        pixels: bool = True,
    ) -> dict[str, Any]:
        payload = node_payload(model_input, observation, self.text, menu_states)
        native = self.scene_views.tasks[self.row["task_id"]]
        if observation == "text":
            return build_node_observation(
                algorithm=algorithm,
                observation=observation,
                payload=payload,
                static_pages=[],
                goal_pages=[],
                scene_path=None,
                menu_indices=None,
            )
        menu_indices = [self.indices[self.key(state.atoms, state.fluents)] for state in menu_states]
        for index in menu_indices:
            if str(index) not in native["scenes"]:
                self._scene_only_current(index)

        def scene_path(state_index: int) -> str:
            path = native["scenes"].get(str(state_index))
            if path is None:
                raise ValueError(f"node-choice scene for state {state_index} is unbound")
            return path

        def loader(label: str, path: str):
            from PIL import Image

            with Image.open(self.root / path) as stored:
                return stored.convert("RGB")

        return build_node_observation(
            algorithm=algorithm,
            observation=observation,
            payload=payload,
            static_pages=native["static_pages"],
            goal_pages=native["goal_pages"],
            scene_path=scene_path,
            menu_indices=menu_indices,
            loader=loader if pixels else None,
        )


__all__ = [
    "LEGENDS",
    "MULTIMODAL_LEGEND",
    "PAYLOAD_KEYS",
    "TEXT_LEGEND",
    "TOKEN_LIMIT",
    "NodeChoiceTaskViews",
    "TextContext",
    "build_node_observation",
    "node_payload",
    "placeholder_counter",
    "text_context",
]
