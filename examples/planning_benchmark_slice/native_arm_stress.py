"""Reviewer-blocking stress extensions for the native arms (#130).

R1 menu manipulation (inference-only, copyability-preserving):
- ``menu-permutation``: the unscored candidate menu's entries permuted by a
  seeded Fisher-Yates; entries stay intact and copyable.
- ``distractor-injection``: up to K schema-valid but currently inapplicable
  grounded actions (harvested from the task's frozen scene-catalog producing
  actions) injected at seeded positions; the trusted runtime still validates
  against the true state, so picking a distractor is an invalid operation.

R2 text-corruption decomposition is CPU-only over the published #126 episode
store (see the runner's ``r2-decompose`` stage).

Determinism: every transform is a pure function of the clean payload, the
frozen master seed and (for distractors) the frozen catalog action pool, so
independent replay recomputes identical menus and token counts.
"""

from __future__ import annotations

import hashlib
import json
import random
from typing import Any

from .native_arm_views import (
    CONTEXT_TOKENS,
    OUTPUT_TOKENS,
    NativeArmTaskViews,
    build_observation,
    reduce_payload,
)

MENU_PERMUTATION = "menu-permutation"
DISTRACTOR_INJECTION = "distractor-injection"
MENU_FAMILIES = (MENU_PERMUTATION, DISTRACTOR_INJECTION)
DISTRACTOR_K = 3
MENU_MASTER_SEED = 51121


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def menu_seed(master_seed: int, family: str, clean_menu: list[dict[str, Any]]) -> int:
    digest = hashlib.sha256(canonical(clean_menu).encode()).hexdigest()
    return int.from_bytes(hashlib.sha256(f"{master_seed}|{family}|{digest}".encode()).digest()[:8], "big")


def parse_catalog_actions(states: list[dict[str, Any]]) -> list[list[str]]:
    """Distinct grounded producing actions recorded in the task's catalog."""

    seen: dict[str, list[str]] = {}
    for state in states:
        parent = state.get("parent")
        if not parent:
            continue
        words = parent["action"].strip("()").split()
        if not words:
            continue
        entry = [words[0], *words[1:]]
        seen[canonical(entry)] = entry
    return list(seen.values())


def transform_menu(
    payload: dict[str, Any],
    family: str,
    master_seed: int,
    catalog_actions: list[list[str]],
) -> list[list[str]]:
    """Apply one frozen menu transform in place; return the injected distractors."""

    menu = payload["successor_candidates"]
    if family == MENU_PERMUTATION:
        rng = random.Random(menu_seed(master_seed, family, menu))
        shuffled = list(menu)
        rng.shuffle(shuffled)
        payload["successor_candidates"] = shuffled
        return []
    if family == DISTRACTOR_INJECTION:
        applicable = {(c["name"], tuple(c["args"])) for c in menu}
        pool = [
            entry
            for entry in catalog_actions
            if (entry[0], tuple(entry[1:])) not in applicable and len(entry) > 1
        ]
        rng = random.Random(menu_seed(master_seed, family, menu))
        k = min(DISTRACTOR_K, len(pool))
        if k == 0:
            return []
        chosen = [rng.choice(pool) for _ in range(k)]
        positions = sorted(rng.sample(range(len(menu) + k), k))
        augmented = list(menu)
        for position, entry in zip(positions, chosen, strict=True):
            augmented.insert(position, {"name": entry[0], "args": list(entry[1:])})
        payload["successor_candidates"] = augmented
        return chosen
    raise ValueError(f"unknown menu family: {family}")


class MenuStressTaskViews(NativeArmTaskViews):
    """NativeArmTaskViews plus a frozen menu transform (R1)."""

    def __init__(self, *args: Any, menu_family: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if menu_family is not None and menu_family not in MENU_FAMILIES:
            raise ValueError(f"unknown menu family: {menu_family}")
        self._menu_family = menu_family

    def observe(self, raw, algorithm, *, modality=None, pixels=True):
        if self._menu_family is None:
            return super().observe(raw, algorithm, modality=modality, pixels=pixels)
        arm = modality or self.arm
        state = self.state(raw, algorithm)
        index = self.indices[self.key(state.atoms, state.fluents)]
        entry = self.states[index]
        from .modality_view_preparation import validate_process_state

        validate_process_state(raw, algorithm, entry)
        native = self.scene_views.tasks[self.row["task_id"]]
        if str(index) not in native["scenes"]:
            self._scene_only_current(index)
        from .native_arm_views import arm_history_k, history_window

        window = history_window(self.states, index, arm_history_k(arm))
        payload = reduce_payload(raw, arm)
        catalog_actions = parse_catalog_actions(self.states)
        injected = transform_menu(payload, self._menu_family, MENU_MASTER_SEED, catalog_actions)
        from PIL import Image

        def loader(label: str, path: str):
            if not pixels:
                return path
            with Image.open(self.root / path) as stored:
                return stored.convert("RGB")

        example = build_observation(
            payload,
            native["static_pages"],
            native["goal_pages"],
            lambda state_index: native["scenes"][str(state_index)],
            index,
            window,
            loader,
        )
        example["binding"]["arm"] = arm
        example["binding"]["history_window"] = list(window)
        example["binding"]["state_representation"] = "menu-stress"
        example["binding"]["menu_family"] = self._menu_family
        example["binding"]["injected_distractors"] = injected
        if example["binding"]["input_tokens"] + OUTPUT_TOKENS > CONTEXT_TOKENS:
            raise RuntimeError("VALID_STOP: menu-stressed input exceeds 32K")
        return example
