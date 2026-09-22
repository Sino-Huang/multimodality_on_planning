"""Frozen visual observation contract for the choice-sensitive arm (#132).

One arm: ``visual-choice-frontier`` (recipe ``visual-choice-frontier-v1``). The
policy sees the static task-context pages, the unlabelled 128px initial-state
scene, one unlabelled 128px scene per live frontier state in a seeded permuted
menu order (labelled ``frontier-choice (label c<i>)``), and the partial-goal
pages. The payload carries only the choice labels: no state identifiers,
scores, search memory, deltas or history — the scenes are the only
decision-relevant channel. The output contract is canonical JSON
``{"expand_choice": "c<i>"}``; replay recomputes identical menus and token
counts (deterministic seeded permutation).
"""

from __future__ import annotations

import json
from typing import Any, Callable

from .choice_frontier import (
    CHOICE_ARM,
    CHOICE_LEGEND,
    CHOICE_RECIPE_ID,
    CHOICE_SCHEMA,
    CHOICE_SYSTEM_MESSAGE,
)
from .expanded_views import ExpandedTaskViews
from .modality_pages import PAGE_SIZE
from .modality_view_preparation import frozen_processor
from .pddl_state import CanonicalState
from .scene_only_views import SCENE_SIZE

CONTEXT_TOKENS = 32768
OUTPUT_TOKENS = 384
PAYLOAD_KEYS = frozenset({"algorithm", "frontier_menu", "representation", "schema_version", "view_legend"})
FORBIDDEN_USER_TEXT_MARKERS = (
    '"search_memory"',
    '"accepted_deltas"',
    '"semantic_blocks"',
    '"successor_candidates"',
    '"frontier_head"',
    '"frontier_count"',
    '"visited_count"',
    '"closed_count"',
    '"best_cost"',
    '"dominated"',
    '"pruned"',
    '"closed"',
    '"priority"',
    '"target_state_id"',
    '"state_facts"',
    '"state_id"',
    '"goal_atoms"',
    '"task_context"',
    '"current"',
    '"history_window"',
    '"generation_serial"',
    '"g"',
    '"h"',
)


def choice_payload(model_input: dict[str, Any]) -> dict[str, Any]:
    """The frozen payload: contract keys plus the legend, fail-closed on drift."""

    payload = {**model_input, "view_legend": CHOICE_LEGEND}
    if set(payload) != PAYLOAD_KEYS:
        raise ValueError("choice-frontier payload keys differ from the frozen contract")
    if payload["schema_version"] != CHOICE_SCHEMA:
        raise ValueError("choice-frontier payload schema differs")
    if set(payload["frontier_menu"]) != {"choices"}:
        raise ValueError("choice-frontier menu keys differ")
    return payload


def assert_no_text_leak(example: dict[str, Any]) -> None:
    """Fail closed if any forbidden key marker survives in the payload text."""

    text = example["messages"][-1]["content"][0]["text"]
    for marker in FORBIDDEN_USER_TEXT_MARKERS:
        if marker in text:
            raise ValueError(f"choice-frontier user payload leaks forbidden key marker {marker}")


def choice_label(choice: str) -> str:
    return f"frontier-choice (label {choice})"


def assemble_choice_messages(payload: dict[str, Any], pages: list[tuple[str, Any]]) -> list[dict[str, Any]]:
    """System + payload user text + role-labelled image parts (frozen layout)."""

    user_text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
    for label, image in pages:
        content.extend([{"type": "text", "text": f"Page role: {label}"}, {"type": "image", "image": image}])
    return [
        {"role": "system", "content": CHOICE_SYSTEM_MESSAGE},
        {"role": "user", "content": content},
    ]


def build_choice_observation(
    payload: dict[str, Any],
    static_pages: list[str],
    goal_pages: list[str],
    menu_choices: list[str],
    scene_path: Callable[[int], str],
    menu_indices: list[int],
    loader: Callable[[str, str], Any] | None = None,
) -> dict[str, Any]:
    """Assemble one choice-arm observation from frozen page sources.

    ``loader(label, relative_path)`` returns the attached image object for
    pixel-bearing observations; ``None`` keeps path references only.
    """

    def image_of(label: str, path: str):
        return path if loader is None else loader(label, path)

    pages: list[tuple[str, Any]] = []
    bindings: list[list] = []
    for i, path in enumerate(static_pages):
        label = "task-context"
        pages.append((label, image_of(label, path)))
        bindings.append([label, None, i])
    pages.append(("initial-state", image_of("initial-state", scene_path(0))))
    bindings.append(["initial-state", 0, 0])
    for choice, state_index in zip(menu_choices, menu_indices, strict=True):
        label = choice_label(choice)
        pages.append((label, image_of(label, scene_path(state_index))))
        bindings.append(["frontier-choice", state_index, 0])
    for i, path in enumerate(goal_pages):
        label = "goal"
        pages.append((label, image_of(label, path)))
        bindings.append([label, None, i])
    messages = assemble_choice_messages(payload, pages)
    sizes = [PAGE_SIZE] * len(static_pages) + [(SCENE_SIZE, SCENE_SIZE)] * (1 + len(menu_choices))
    sizes += [PAGE_SIZE] * len(goal_pages)
    if len(sizes) != len(pages):
        raise ValueError("choice-frontier page/size layout differs")
    count = frozen_processor().count(messages, image_sizes=sizes)
    if count + OUTPUT_TOKENS > CONTEXT_TOKENS:
        raise RuntimeError("OBSERVATION_OVERFLOW: choice-frontier complete input exceeds 32K")
    return {
        "messages": messages,
        "images": [image for _, image in pages],
        "image_sizes": sizes,
        "page_roles": [label for label, _ in pages],
        "binding": {
            "menu_size": len(menu_choices),
            "input_pages": bindings,
            "input_tokens": count,
            "state_representation": CHOICE_RECIPE_ID,
        },
    }


class ChoiceFrontierTaskViews(ExpandedTaskViews):
    """ExpandedTaskViews under the frozen choice-frontier observation contract."""

    def observe_choices(
        self,
        model_input: dict[str, Any],
        menu_states: list[CanonicalState],
        *,
        pixels: bool = True,
    ) -> dict[str, Any]:
        if model_input.get("schema_version") != CHOICE_SCHEMA:
            raise ValueError("choice-frontier observation input schema differs")
        native = self.scene_views.tasks[self.row["task_id"]]
        menu_indices = [self.indices[self.key(state.atoms, state.fluents)] for state in menu_states]
        for index in menu_indices:
            if str(index) not in native["scenes"]:
                self._scene_only_current(index)

        def scene_path(state_index: int) -> str:
            path = native["scenes"].get(str(state_index))
            if path is None:
                raise ValueError(f"choice-frontier scene for state {state_index} is unbound")
            return path

        def loader(label: str, path: str):
            if not pixels:
                return path
            from PIL import Image

            with Image.open(self.root / path) as stored:
                return stored.convert("RGB")

        payload = choice_payload(model_input)
        example = build_choice_observation(
            payload,
            native["static_pages"],
            native["goal_pages"],
            list(model_input["frontier_menu"]["choices"]),
            scene_path,
            menu_indices,
            loader if pixels else None,
        )
        assert_no_text_leak(example)
        return example


__all__ = [
    "CHOICE_ARM",
    "CONTEXT_TOKENS",
    "FORBIDDEN_USER_TEXT_MARKERS",
    "OUTPUT_TOKENS",
    "PAYLOAD_KEYS",
    "ChoiceFrontierTaskViews",
    "assemble_choice_messages",
    "assert_no_text_leak",
    "build_choice_observation",
    "choice_label",
    "choice_payload",
]
