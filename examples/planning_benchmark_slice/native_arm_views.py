"""Frozen image-only state/history observation arms (#128).

Two additive observation contracts on the frozen expanded panel machinery:

- ``visual-nomem-state``: the frozen ``visual-state`` page set (static task
  context, initial-state scene, current-state scene, goal pages) with the
  textual payload reduced to the static interface plus an *unscored*
  candidate menu.  Search Memory, accepted deltas, current g/h/priority and
  every candidate score/membership column are removed, so state facts and
  search history have no image or text channel beyond the standing pages.
- ``visual-seq-state``: the same reduced payload plus a bounded history frame
  window — the rendered current-state pages of the last K visited states
  along the current search path, in visit order, each labelled with its
  absolute path position (initial state = 0).

Both arms share the frozen system message, greedy decoding and the 32K input
gate of the expanded replay machinery.  The reduced payload keeps
``current.state_id`` (the operation must echo the popped frontier head) and
drops every other search-process signal.  Contracts are frozen in
``configs/experiments/native-arms/native-arms-protocol.json``; the constants
here must byte-match that protocol (validated by the runner's ``validate``
stage).
"""

from __future__ import annotations

from typing import Any, Callable

from PIL import Image

from .best_first_model_input import serialize_best_first_message_prefix
from .expanded_views import ExpandedTaskViews
from .modality_pages import PAGE_SIZE
from .modality_view_preparation import frozen_processor, validate_process_state
from .scene_assets import read_json
from .scene_only_views import SCENE_SIZE

ARMS = ("visual-nomem-state", "visual-seq-state")
NOMEM_ARM, SEQ_ARM = ARMS
HISTORY_K = 8
NOMEM_RECIPE_ID = "visual-nomem-state-v1"
SEQ_RECIPE_ID = "visual-seq-state-v1"
CONTEXT_TOKENS = 32768
OUTPUT_TOKENS = 384

NOMEM_LEGEND = (
    "Static task context, initial-state scene, current-state scene and partial-goal pages are attached. "
    "Initial/current states are unlabelled 128px scenes without text annotations. "
    "Infer dynamic state from the scene; no symbolic initial/current-state fact panels are included. "
    "Black robot silhouettes identify the agent. "
    "Goal constraints do not describe a complete solved state: unspecified facts are unconstrained. "
    "Goal blocks ALL, ANY, NOT, FOR EVERY and THERE EXISTS retain their labelled variable scopes. "
    "No Search Memory, accepted-delta window, scalar search values, candidate scores or membership flags "
    "are provided: the candidate menu lists each successor's action name and arguments only, unscored, "
    "in grounded order. No search history is provided."
)

SEQ_LEGEND = (
    "Static task context, initial-state scene, current-state scene and partial-goal pages are attached. "
    "Initial/current states are unlabelled 128px scenes without text annotations. "
    "Infer dynamic state from the scene; no symbolic initial/current-state fact panels are included. "
    "Black robot silhouettes identify the agent. "
    "Goal constraints do not describe a complete solved state: unspecified facts are unconstrained. "
    "Goal blocks ALL, ANY, NOT, FOR EVERY and THERE EXISTS retain their labelled variable scopes. "
    "No Search Memory, accepted-delta window, scalar search values, candidate scores or membership flags "
    "are provided: the candidate menu lists each successor's action name and arguments only, unscored, "
    "in grounded order. "
    "The current search path's most recent visited states precede the current state, attached in visit "
    "order before the current-state scene, each labelled with its absolute path position "
    "(the initial state is position 0); the current state itself is the current-state scene."
)

# Payload keys of the reduced contract (frozen).  ``current`` retains only
# ``state_id``; candidates retain only ``name``/``args``.
REDUCED_PAYLOAD_KEYS = frozenset(
    {"algorithm", "current", "representation", "schema_version", "successor_candidates", "view_legend"}
)
REMOVED_PAYLOAD_KEYS = (
    "search_memory",
    "accepted_deltas",
    "task_context",
    "goal_atoms",
    "observation",
    "expanded_state",
    "semantic_blocks",
)
REMOVED_CURRENT_KEYS = ("g", "h", "priority", "state_facts", "state_atoms")
REMOVED_CANDIDATE_KEYS = (
    "g",
    "h",
    "priority",
    "best_cost",
    "best_cost_before",
    "closed",
    "frontier",
    "dominated",
    "pruned",
    "target_state_id",
)
COMPACT_SCHEMA = "best_first_compact_model_input_v2"
FORBIDDEN_USER_TEXT_MARKERS = (
    '"search_memory"',
    '"accepted_deltas"',
    '"semantic_blocks"',
    '"frontier_head"',
    '"best_cost"',
    '"dominated"',
    '"pruned"',
    '"target_state_id"',
    '"state_facts"',
    '"goal_atoms"',
    '"frontier_count"',
    '"visited_count"',
    '"closed_count"',
    '"priority"',
)


def arm_recipe_id(arm: str) -> str:
    if arm == NOMEM_ARM:
        return NOMEM_RECIPE_ID
    if arm == SEQ_ARM:
        return SEQ_RECIPE_ID
    raise ValueError(f"unknown native-arm contract: {arm}")


def arm_legend(arm: str) -> str:
    if arm == NOMEM_ARM:
        return NOMEM_LEGEND
    if arm == SEQ_ARM:
        return SEQ_LEGEND
    raise ValueError(f"unknown native-arm contract: {arm}")


def arm_history_k(arm: str) -> int:
    return 0 if arm == NOMEM_ARM else HISTORY_K


def unscored_candidates(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-candidate ``{name, args}`` only, in the trusted grounded order."""

    table = raw.get("successor_candidates")
    if not isinstance(table, dict) or set(table) != {"columns", "rows"} or table["columns"][0] != "action":
        raise ValueError("native arms require the compact successor-candidate table")
    menu = []
    for row in table["rows"]:
        action = row[0]
        if not isinstance(action, list) or not action or not all(isinstance(item, str) for item in action):
            raise ValueError("compact candidate action column is malformed")
        menu.append({"name": action[0], "args": list(action[1:])})
    return menu


def reduce_payload(raw: dict[str, Any], arm: str, legend: str | None = None) -> dict[str, Any]:
    """Build the frozen reduced payload and fail closed on any leak."""

    if raw.get("schema_version") != COMPACT_SCHEMA:
        raise ValueError("native arms require the frozen compact live input schema")
    payload = {
        "algorithm": raw["algorithm"],
        "current": {"state_id": raw["current"]["state_id"]},
        "representation": arm,
        "schema_version": raw["schema_version"],
        "successor_candidates": unscored_candidates(raw),
        "view_legend": legend if legend is not None else arm_legend(arm),
    }
    if set(payload) != REDUCED_PAYLOAD_KEYS or set(payload["current"]) != {"state_id"}:
        raise ValueError("reduced payload keys differ from the frozen contract")
    if any(key in payload for key in REMOVED_PAYLOAD_KEYS):
        raise ValueError("reduced payload retains a removed search-process key")
    if any(key in payload["current"] for key in REMOVED_CURRENT_KEYS):
        raise ValueError("reduced payload retains a removed current-state scalar")
    if any(key in candidate for candidate in payload["successor_candidates"] for key in REMOVED_CANDIDATE_KEYS):
        raise ValueError("reduced candidate menu retains a removed score/membership column")
    menu = unscored_candidates(raw)
    expected = [(row[0][0], tuple(row[0][1:])) for row in raw["successor_candidates"]["rows"]]
    if [(c["name"], tuple(c["args"])) for c in menu] != expected:
        raise ValueError("reduced candidate menu differs from the trusted grounded order")
    return payload


def history_window(states: list[dict[str, Any]], index: int, k: int) -> list[int]:
    """Last ``k`` predecessor state indices on the first-acceptance path."""

    if k < 0:
        raise ValueError("history window size must be non-negative")
    if not 0 <= index < len(states):
        raise ValueError("history window state index is out of range")
    chain = []
    current = index
    while states[current]["parent"] is not None:
        current = states[current]["parent"]["state"]
        chain.append(current)
    chain.reverse()  # initial -> ... -> immediate predecessor
    return chain[-k:] if k else []


def assemble_messages(payload: dict[str, Any], pages: list[tuple[str, Any]]) -> list[dict[str, Any]]:
    """System + payload user text + role-labelled image parts (frozen layout)."""

    messages = [dict(message) for message in serialize_best_first_message_prefix(payload)]
    content: list[dict[str, Any]] = [{"type": "text", "text": messages[-1]["content"]}]
    for label, image in pages:
        content.extend([{"type": "text", "text": f"Page role: {label}"}, {"type": "image", "image": image}])
    messages[-1] = {"role": "user", "content": content}
    return messages


def history_label(position: int) -> str:
    return f"history-state (visit ordinal {position})"


def build_observation(
    payload: dict[str, Any],
    static_pages: list[str],
    goal_pages: list[str],
    scene_path: Callable[[int], str],
    state: int,
    window: list[int],
    loader: Callable[[str, str], Any] | None = None,
) -> dict[str, Any]:
    """Assemble one native-arm observation from frozen page sources.

    ``loader(label, relative_path)`` returns the attached image object for
    pixel-bearing observations; ``None`` keeps path references only.
    """

    def image_of(label: str, path: str):
        if loader is None:
            return path
        return loader(label, path)

    pages: list[tuple[str, Any]] = []
    bindings: list[list] = []
    for i, path in enumerate(static_pages):
        label = "task-context"
        pages.append((label, image_of(label, path)))
        bindings.append([label, None, i])
    pages.append(("initial-state", image_of("initial-state", scene_path(0))))
    bindings.append(["initial-state", 0, 0])
    for state_index in window:
        label = history_label(state_index)
        pages.append((label, image_of(label, scene_path(state_index))))
        bindings.append(["history-state", state_index, 0])
    pages.append(("current-state", image_of("current-state", scene_path(state))))
    bindings.append(["current-state", state, 0])
    for i, path in enumerate(goal_pages):
        label = "goal"
        pages.append((label, image_of(label, path)))
        bindings.append([label, None, i])
    messages = assemble_messages(payload, pages)
    sizes = [PAGE_SIZE] * len(static_pages) + [(SCENE_SIZE, SCENE_SIZE)] * (1 + len(window) + 1)
    sizes += [PAGE_SIZE] * len(goal_pages)
    if len(sizes) != len(pages):
        raise ValueError("native-arm page/size layout differs")
    count = frozen_processor().count(messages, image_sizes=sizes)
    if count + OUTPUT_TOKENS > CONTEXT_TOKENS:
        raise RuntimeError("VALID_STOP: native-arm complete input exceeds 32K")
    return {
        "messages": messages,
        "images": [image for _, image in pages],
        "image_sizes": sizes,
        "page_roles": [label for label, _ in pages],
        "binding": {
            "state": state,
            "input_pages": bindings,
            "input_tokens": count,
            "state_representation": "native-arm",
        },
    }


def assert_no_text_leak(example: dict[str, Any]) -> None:
    """Fail closed if any removed key survives in the serialized payload text."""

    text = example["messages"][-1]["content"][0]["text"]
    for marker in FORBIDDEN_USER_TEXT_MARKERS:
        if marker in text:
            raise ValueError(f"native-arm user payload leaks removed key marker {marker}")


class NativeArmTaskViews(ExpandedTaskViews):
    """ExpandedTaskViews under a frozen native-arm observation contract.

    ``corruption`` applies the frozen #126 visual families (visual-blank,
    visual-degraded) to the assembled observation, mirroring StressTaskViews:
    applied in place after page assembly, token count recomputed on the
    corrupted messages and the 32K gate re-checked.
    """

    def __init__(
        self,
        *args: Any,
        arm: str = NOMEM_ARM,
        corruption: str | None = None,
        master_seed: int = 42613,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        if arm not in ARMS:
            raise ValueError(f"unknown native-arm contract: {arm}")
        self.arm = arm
        self._corruption = corruption
        self._master_seed = master_seed

    def observe(self, raw, algorithm, *, modality=None, pixels=True):
        arm = modality or self.arm
        if arm not in ARMS or arm != self.arm:
            raise ValueError("observation modality differs from the episode's frozen native arm")
        if not algorithm.startswith("best_first_add"):
            raise ValueError("native arms support the additive best-first families only")
        state = self.state(raw, algorithm)
        index = self.indices[self.key(state.atoms, state.fluents)]
        entry = self.states[index]
        validate_process_state(raw, algorithm, entry)
        native = self.scene_views.tasks[self.row["task_id"]]
        if str(index) not in native["scenes"]:
            self._scene_only_current(index)
        window = history_window(self.states, index, arm_history_k(arm))
        if any(w >= index for w in window):
            raise ValueError("history window leaks a state outside the accepted past")

        def scene_path(state_index: int) -> str:
            path = native["scenes"].get(str(state_index))
            if path is None:
                raise ValueError(f"native-arm scene for state {state_index} is unbound")
            return path

        def loader(label: str, path: str):
            if not pixels:
                return path
            with Image.open(self.root / path) as stored:
                return stored.convert("RGB")

        payload = reduce_payload(raw, arm)
        example = build_observation(
            payload,
            native["static_pages"],
            native["goal_pages"],
            scene_path,
            index,
            window,
            loader,
        )
        example["binding"]["arm"] = arm
        example["binding"]["history_window"] = list(window)
        example["binding"]["state_representation"] = arm_recipe_id(arm)
        assert_no_text_leak(example)
        if self._corruption is not None:
            if self._corruption not in ("visual-blank", "visual-degraded"):
                raise ValueError(f"native arms support the frozen visual families only: {self._corruption}")
            from .expanded_modality_stress import corrupt_example

            corrupt_example(example, self._corruption, self._master_seed)
            count = self.page_processor.count(example["messages"], image_sizes=example["image_sizes"])
            if count + OUTPUT_TOKENS > CONTEXT_TOKENS:
                raise RuntimeError("VALID_STOP: corrupted native-arm input exceeds the approved 32K context")
            example["binding"]["input_tokens"] = count
        return example


def load_catalog_states(root, manifest_path: str) -> list[dict[str, Any]]:
    manifest = read_json(root / manifest_path)
    catalog = read_json(root / manifest["scene_catalog"])
    return list(catalog["states"])
