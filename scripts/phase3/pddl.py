from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

Atom = tuple[str, ...]


@dataclass(frozen=True)
class ActionSchema:
    name: str
    parameters: tuple[tuple[str, str], ...]
    preconditions: frozenset[Atom]
    add_effects: frozenset[Atom]
    del_effects: frozenset[Atom]


@dataclass(frozen=True)
class GroundAction:
    name: str
    args: tuple[str, ...]
    preconditions: frozenset[Atom]
    add_effects: frozenset[Atom]
    del_effects: frozenset[Atom]

    @property
    def canonical(self) -> str:
        return canonical_action(self.name, self.args)


@dataclass(frozen=True)
class PDDLTask:
    domain_name: str
    problem_name: str
    objects_by_type: dict[str, tuple[str, ...]]
    init: frozenset[Atom]
    goal: frozenset[Atom]
    actions: tuple[ActionSchema, ...]
    unsupported_features: tuple[str, ...]


class PDDLError(ValueError):
    pass


UNSUPPORTED_MARKERS = {
    ":negative-preconditions": "negative_preconditions_requirement",
    ":adl": "adl_requirement",
    ":conditional-effects": "conditional_effects_requirement",
    ":derived-predicates": "derived_predicates_requirement",
    ":numeric-fluents": "numeric_fluents_requirement",
    ":fluents": "numeric_fluents_requirement",
    ":quantified-preconditions": "quantified_preconditions_requirement",
    ":disjunctive-preconditions": "disjunctive_preconditions_requirement",
    ":equality": "equality_requirement",
    "forall": "quantifier_forall",
    "exists": "quantifier_exists",
    "when": "conditional_effect_when",
    "increase": "numeric_effect",
    "decrease": "numeric_effect",
}


def normalize_action_string(text: str) -> str:
    stripped = text.strip().lower()
    if not stripped:
        raise PDDLError("empty action string")
    stripped = re.sub(r"[();]", " ", stripped)
    parts = [part for part in re.split(r"\s+", stripped) if part]
    if not parts:
        raise PDDLError("empty action string")
    return canonical_action(parts[0], parts[1:])


def canonical_action(name: str, args: tuple[str, ...] | list[str]) -> str:
    return "(" + " ".join([name.lower(), *[arg.lower() for arg in args]]) + ")"


def canonical_atom(atom: Atom) -> str:
    return "(" + " ".join(atom) + ")"


def parse_task(domain_path: Path, problem_path: Path) -> PDDLTask:
    domain_text = _strip_comments(domain_path.read_text(encoding="utf-8", errors="replace")).lower()
    problem_text = _strip_comments(problem_path.read_text(encoding="utf-8", errors="replace")).lower()
    unsupported = sorted(set(_unsupported(domain_text) + _unsupported(problem_text)))
    domain_expr = _parse_sexpr(domain_text)
    problem_expr = _parse_sexpr(problem_text)
    domain_name = _name_after(domain_expr, "domain")
    problem_name = _name_after(problem_expr, "problem")
    types = _domain_types(domain_expr)
    actions = tuple(_parse_action(item) for item in domain_expr if isinstance(item, list) and item and item[0] == ":action")
    objects_by_type = _problem_objects(problem_expr, types)
    init = frozenset(_atoms_from_section(_section(problem_expr, ":init")))
    goal = frozenset(_positive_atoms(_section(problem_expr, ":goal")))
    unsupported.extend(_unsupported_tree(_section(problem_expr, ":goal"), in_precondition=True))
    for action in actions:
        if any(atom[0] == "not" for atom in action.preconditions):
            unsupported.append("negative_precondition")
    return PDDLTask(
        domain_name=domain_name,
        problem_name=problem_name,
        objects_by_type={key: tuple(value) for key, value in objects_by_type.items()},
        init=init,
        goal=goal,
        actions=actions,
        unsupported_features=tuple(sorted(set(unsupported))),
    )


def ground_actions(task: PDDLTask, *, max_grounded_actions: int, max_grounded_atoms: int) -> tuple[list[GroundAction], str | None]:
    atoms = set(task.init) | set(task.goal)
    grounded: list[GroundAction] = []
    all_objects = tuple(sorted(task.objects_by_type.get("object", ())))
    for schema in task.actions:
        domains: list[tuple[str, ...]] = []
        for _param, type_name in schema.parameters:
            domains.append(tuple(sorted(task.objects_by_type.get(type_name, ()) or all_objects)))
        for combo in itertools.product(*domains):
            if len(grounded) >= max_grounded_actions:
                return grounded, "skipped_grounding_limit"
            mapping = {param: arg for (param, _type), arg in zip(schema.parameters, combo)}
            action = GroundAction(
                name=schema.name,
                args=tuple(combo),
                preconditions=frozenset(_substitute(atom, mapping) for atom in schema.preconditions),
                add_effects=frozenset(_substitute(atom, mapping) for atom in schema.add_effects),
                del_effects=frozenset(_substitute(atom, mapping) for atom in schema.del_effects),
            )
            atoms.update(action.preconditions)
            atoms.update(action.add_effects)
            atoms.update(action.del_effects)
            if len(atoms) > max_grounded_atoms:
                return grounded, "skipped_grounding_limit"
            grounded.append(action)
    return grounded, None


def replay_plan(task: PDDLTask, actions: list[str], *, grounded_actions: list[GroundAction]) -> dict[str, Any]:
    by_name = {action.canonical: action for action in grounded_actions}
    state = set(task.init)
    transitions: list[dict[str, Any]] = []
    if not actions and task.goal.issubset(state):
        return _replay_result(True, True, "success", transitions, state)
    for index, raw_action in enumerate(actions):
        try:
            canonical = normalize_action_string(raw_action)
        except PDDLError:
            return _replay_result(False, False, "failed_action_normalization", transitions, state, failed_step=index)
        action = by_name.get(canonical)
        if action is None or not action.preconditions.issubset(state):
            return _replay_result(False, False, "failed_replay_invalid_action", transitions, state, failed_step=index, action=canonical)
        before = sorted(canonical_atom(atom) for atom in state)
        state.difference_update(action.del_effects)
        state.update(action.add_effects)
        transitions.append(
            {
                "step_index": index,
                "action": canonical,
                "state_before": before,
                "state_after": sorted(canonical_atom(atom) for atom in state),
            }
        )
    goal_satisfied = task.goal.issubset(state)
    status = "success" if goal_satisfied else "failed_replay_goal_not_satisfied"
    return _replay_result(goal_satisfied, goal_satisfied, status, transitions, state)


def _replay_result(replay_ok: bool, goal_satisfied: bool, status: str, transitions: list[dict[str, Any]], state: set[Atom], **extra: Any) -> dict[str, Any]:
    return {
        "replay_ok": replay_ok,
        "goal_satisfied": goal_satisfied,
        "status": status,
        "transition_count": len(transitions),
        "transitions": transitions,
        "final_state_atoms": sorted(canonical_atom(atom) for atom in state),
        **extra,
    }


def _strip_comments(text: str) -> str:
    return "\n".join(line.split(";", 1)[0] for line in text.splitlines())


def _unsupported(text: str) -> list[str]:
    found: list[str] = []
    for marker, label in UNSUPPORTED_MARKERS.items():
        if re.search(r"(?<![a-z0-9_-])" + re.escape(marker) + r"(?![a-z0-9_-])", text):
            found.append(label)
    return found


def _parse_sexpr(text: str) -> list[Any]:
    tokens = re.findall(r"\(|\)|[^\s()]+", text)
    stack: list[list[Any]] = []
    current: list[Any] = []
    for token in tokens:
        if token == "(":
            stack.append(current)
            current = []
        elif token == ")":
            if not stack:
                raise PDDLError("unbalanced parentheses")
            parent = stack.pop()
            parent.append(current)
            current = parent
        else:
            current.append(token)
    if stack:
        raise PDDLError("unbalanced parentheses")
    if len(current) != 1 or not isinstance(current[0], list):
        raise PDDLError("expected one top-level expression")
    return current[0]


def _name_after(expr: list[Any], keyword: str) -> str:
    for item in expr:
        if isinstance(item, list) and len(item) >= 2 and item[0] == keyword:
            return str(item[1])
    return "unknown"


def _section(expr: list[Any], keyword: str) -> list[Any]:
    for item in expr:
        if isinstance(item, list) and item and item[0] == keyword:
            return item[1:]
    return []


def _domain_types(expr: list[Any]) -> set[str]:
    section = _section(expr, ":types")
    types = {"object"}
    for token in section:
        if isinstance(token, str) and token != "-":
            types.add(token)
    return types


def _problem_objects(expr: list[Any], types: set[str]) -> dict[str, list[str]]:
    section = _section(expr, ":objects")
    objects_by_type: dict[str, list[str]] = {"object": []}
    pending: list[str] = []
    index = 0
    while index < len(section):
        token = section[index]
        if token == "-" and index + 1 < len(section):
            type_name = str(section[index + 1])
            for obj in pending:
                objects_by_type.setdefault(type_name, []).append(obj)
                objects_by_type["object"].append(obj)
            pending = []
            index += 2
            continue
        if isinstance(token, str):
            pending.append(token)
        index += 1
    for obj in pending:
        objects_by_type["object"].append(obj)
    for type_name in types:
        objects_by_type.setdefault(type_name, list(objects_by_type["object"]))
    return {key: sorted(set(value)) for key, value in objects_by_type.items()}


def _parse_action(expr: list[Any]) -> ActionSchema:
    name = str(expr[1])
    params = _typed_parameters(_value_after(expr, ":parameters"))
    preconditions = frozenset(_positive_atoms(_value_after(expr, ":precondition")))
    add_effects, del_effects = _effects(_value_after(expr, ":effect"))
    return ActionSchema(name=name, parameters=tuple(params), preconditions=preconditions, add_effects=frozenset(add_effects), del_effects=frozenset(del_effects))


def _value_after(expr: list[Any], keyword: str) -> Any:
    for index, item in enumerate(expr):
        if item == keyword and index + 1 < len(expr):
            return expr[index + 1]
    return []


def _typed_parameters(value: Any) -> list[tuple[str, str]]:
    if not isinstance(value, list):
        return []
    params: list[tuple[str, str]] = []
    pending: list[str] = []
    index = 0
    while index < len(value):
        token = value[index]
        if token == "-" and index + 1 < len(value):
            type_name = str(value[index + 1])
            params.extend((param, type_name) for param in pending)
            pending = []
            index += 2
            continue
        if isinstance(token, str):
            pending.append(token)
        index += 1
    params.extend((param, "object") for param in pending)
    return params


def _positive_atoms(value: Any) -> list[Atom]:
    if not isinstance(value, list):
        return []
    if value and value[0] == "and":
        atoms: list[Atom] = []
        for item in value[1:]:
            atoms.extend(_positive_atoms(item))
        return atoms
    if value and value[0] == "not":
        return []
    if value and all(isinstance(item, str) for item in value):
        return [tuple(str(item) for item in value)]
    atoms = []
    for item in value:
        atoms.extend(_positive_atoms(item))
    return atoms


def _atoms_from_section(section: list[Any]) -> list[Atom]:
    atoms: list[Atom] = []
    for item in section:
        atoms.extend(_positive_atoms(item))
    return atoms


def _effects(value: Any) -> tuple[list[Atom], list[Atom]]:
    add: list[Atom] = []
    delete: list[Atom] = []
    items = value[1:] if isinstance(value, list) and value and value[0] == "and" else [value]
    for item in items:
        if isinstance(item, list) and item and item[0] == "not":
            delete.extend(_positive_atoms(item[1]))
        else:
            add.extend(_positive_atoms(item))
    return add, delete


def _unsupported_tree(value: Any, *, in_precondition: bool) -> list[str]:
    found: list[str] = []
    if isinstance(value, list):
        if value and value[0] == "not" and in_precondition:
            found.append("negative_precondition")
        for item in value:
            found.extend(_unsupported_tree(item, in_precondition=in_precondition))
    return found


def _substitute(atom: Atom, mapping: dict[str, str]) -> Atom:
    return tuple(mapping.get(part, part) for part in atom)
