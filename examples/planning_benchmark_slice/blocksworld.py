from __future__ import annotations

import hashlib
import json
import re
from collections import deque
from dataclasses import dataclass
from typing import Any, Iterable, TypeAlias


AtomSet: TypeAlias = frozenset[str]

BLOCKSWORLD_ACTIONS: tuple[str, ...] = ("pickup", "putdown", "stack", "unstack")
BLOCKSWORLD_PREDICATE_ARITY: dict[str, int] = {
    "arm-empty": 0,
    "clear": 1,
    "holding": 1,
    "on-table": 1,
    "on": 2,
}


class BlocksworldParseError(ValueError):
    """Raised when PDDL is outside the supported Blocksworld STRIPS subset."""


class IllegalActionError(ValueError):
    """Raised when a transition is requested for an illegal action."""


@dataclass(frozen=True, order=True)
class BlocksworldAction:
    """Ground Blocksworld action in deterministic canonical form.

    Actions serialize as ``name(arg1,arg2)`` or ``name(arg1)``. The serializer is
    used for sorted legal-action lists, tests, and downstream prompt packages.
    """

    name: str
    args: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.name not in BLOCKSWORLD_ACTIONS:
            raise ValueError(f"unsupported Blocksworld action: {self.name}")
        expected_arity = 1 if self.name in {"pickup", "putdown"} else 2
        if len(self.args) != expected_arity:
            raise ValueError(f"{self.name} expects {expected_arity} arguments, got {len(self.args)}")

    def serialize(self) -> str:
        return f"{self.name}({','.join(self.args)})"


@dataclass(frozen=True)
class BlocksworldProblem:
    """Parsed Blocksworld problem and deterministic symbolic world model v0.

    Canonical atoms are lower-case strings with sorted deterministic
    serialization: zero-arity predicates use the bare predicate name
    (``arm-empty``), unary predicates use ``predicate(object)``
    (``clear(b1)``), and binary predicates use ``predicate(left,right)``
    (``on(b1,b2)``). State IDs are SHA-256 hashes over JSON-encoded sorted atom
    strings, so repeated runs and different PDDL atom orderings produce the same
    identifier for the same symbolic state.
    """

    domain_name: str
    problem_name: str
    problem_domain_name: str
    objects: tuple[str, ...]
    initial_atoms: AtomSet
    goal_atoms: AtomSet
    action_vocabulary: tuple[str, ...]

    @property
    def goal_is_empty(self) -> bool:
        return not self.goal_atoms

    def state_id(self, state: Iterable[str] | None = None) -> str:
        atoms = sorted(self.initial_atoms if state is None else state)
        payload = json.dumps(atoms, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def initial_state(self) -> AtomSet:
        return self.initial_atoms

    def is_goal(self, state: Iterable[str]) -> bool:
        atom_set = frozenset(state)
        return self.goal_atoms.issubset(atom_set)

    def legal_actions(self, state: Iterable[str] | None = None) -> tuple[BlocksworldAction, ...]:
        atom_set = self.initial_atoms if state is None else frozenset(state)
        actions: list[BlocksworldAction] = []

        for block in self.objects:
            if _has_all(atom_set, _atom("clear", block), _atom("on-table", block), _atom("arm-empty")):
                actions.append(BlocksworldAction("pickup", (block,)))
            if _has_all(atom_set, _atom("holding", block)):
                actions.append(BlocksworldAction("putdown", (block,)))

        for block in self.objects:
            for other in self.objects:
                if block == other:
                    continue
                if _has_all(atom_set, _atom("holding", block), _atom("clear", other)):
                    actions.append(BlocksworldAction("stack", (block, other)))
                if _has_all(atom_set, _atom("on", block, other), _atom("clear", block), _atom("arm-empty")):
                    actions.append(BlocksworldAction("unstack", (block, other)))

        return tuple(sorted(actions, key=lambda action: action.serialize()))

    def legal_action_strings(self, state: Iterable[str] | None = None) -> tuple[str, ...]:
        return tuple(action.serialize() for action in self.legal_actions(state))

    def transition(self, state: Iterable[str], action: BlocksworldAction) -> AtomSet:
        atom_set = frozenset(state)
        if action not in self.legal_actions(atom_set):
            raise IllegalActionError(f"illegal action in current state: {action.serialize()}")

        add: set[str]
        delete: set[str]
        if action.name == "pickup":
            block = action.args[0]
            add = {_atom("holding", block)}
            delete = {_atom("clear", block), _atom("on-table", block), _atom("arm-empty")}
        elif action.name == "putdown":
            block = action.args[0]
            add = {_atom("clear", block), _atom("arm-empty"), _atom("on-table", block)}
            delete = {_atom("holding", block)}
        elif action.name == "stack":
            block, other = action.args
            add = {_atom("arm-empty"), _atom("clear", block), _atom("on", block, other)}
            delete = {_atom("clear", other), _atom("holding", block)}
        elif action.name == "unstack":
            block, other = action.args
            add = {_atom("holding", block), _atom("clear", other)}
            delete = {_atom("on", block, other), _atom("clear", block), _atom("arm-empty")}
        else:  # pragma: no cover - dataclass validation keeps this unreachable.
            raise IllegalActionError(f"unsupported action: {action.name}")

        return frozenset((atom_set - delete) | add)

    def shortest_plan_length(self, *, max_depth: int = 64) -> int | None:
        if self.is_goal(self.initial_atoms):
            return 0

        frontier: deque[tuple[AtomSet, int]] = deque([(self.initial_atoms, 0)])
        visited = {self.state_id(self.initial_atoms)}
        while frontier:
            state, depth = frontier.popleft()
            if depth >= max_depth:
                continue
            for action in self.legal_actions(state):
                next_state = self.transition(state, action)
                next_id = self.state_id(next_state)
                if next_id in visited:
                    continue
                if self.is_goal(next_state):
                    return depth + 1
                visited.add(next_id)
                frontier.append((next_state, depth + 1))
        return None

    def to_summary(self) -> dict[str, Any]:
        return {
            "action_vocabulary": list(self.action_vocabulary),
            "domain_name": self.domain_name,
            "goal_atoms": sorted(self.goal_atoms),
            "goal_is_empty": self.goal_is_empty,
            "initial_atoms": sorted(self.initial_atoms),
            "initial_state_id": self.state_id(self.initial_atoms),
            "legal_actions": list(self.legal_action_strings(self.initial_atoms)),
            "legal_actions_count": len(self.legal_actions(self.initial_atoms)),
            "objects": list(self.objects),
            "problem_domain_name": self.problem_domain_name,
            "problem_name": self.problem_name,
        }


def parse_blocksworld(domain_pddl: str, problem_pddl: str) -> BlocksworldProblem:
    domain_tree = _parse_single_pddl_form(domain_pddl, source="domain PDDL")
    problem_tree = _parse_single_pddl_form(problem_pddl, source="problem PDDL")
    domain_name, action_vocabulary = _parse_domain(domain_tree)
    problem_name, problem_domain_name, objects, init_atoms, goal_atoms = _parse_problem(problem_tree)
    _validate_required_actions(action_vocabulary)
    return BlocksworldProblem(
        domain_name=domain_name,
        problem_name=problem_name,
        problem_domain_name=problem_domain_name,
        objects=objects,
        initial_atoms=init_atoms,
        goal_atoms=goal_atoms,
        action_vocabulary=tuple(sorted(action_vocabulary)),
    )


def canonical_atom(predicate: str, *args: str) -> str:
    return _atom(predicate, *args)


def _has_all(state: AtomSet, *atoms: str) -> bool:
    return all(atom in state for atom in atoms)


def _atom(predicate: str, *args: str) -> str:
    normalized_predicate = predicate.lower()
    expected_arity = BLOCKSWORLD_PREDICATE_ARITY.get(normalized_predicate)
    if expected_arity is None:
        raise BlocksworldParseError(f"unsupported Blocksworld predicate: {predicate}")
    if len(args) != expected_arity:
        raise BlocksworldParseError(f"{predicate} expects {expected_arity} arguments, got {len(args)}")
    normalized_args = tuple(arg.lower() for arg in args)
    if not normalized_args:
        return normalized_predicate
    return f"{normalized_predicate}({','.join(normalized_args)})"


def _strip_comments(text: str) -> str:
    return "\n".join(line.split(";", 1)[0] for line in text.splitlines())


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\(|\)|[^\s()]+", _strip_comments(text).lower())


def _parse_single_pddl_form(text: str, *, source: str) -> list[Any]:
    tokens = _tokenize(text)
    if not tokens:
        raise BlocksworldParseError(f"{source} is empty")

    position = 0

    def parse_expression() -> Any:
        nonlocal position
        if position >= len(tokens):
            raise BlocksworldParseError(f"unexpected end of {source}")
        token = tokens[position]
        position += 1
        if token == "(":
            expression: list[Any] = []
            while position < len(tokens) and tokens[position] != ")":
                expression.append(parse_expression())
            if position >= len(tokens):
                raise BlocksworldParseError(f"unbalanced parentheses in {source}")
            position += 1
            return expression
        if token == ")":
            raise BlocksworldParseError(f"unexpected ')' in {source}")
        return token

    expression = parse_expression()
    if position != len(tokens):
        raise BlocksworldParseError(f"trailing tokens in {source}")
    if not isinstance(expression, list) or not expression:
        raise BlocksworldParseError(f"{source} must contain a PDDL list form")
    return expression


def _parse_domain(tree: list[Any]) -> tuple[str, set[str]]:
    if len(tree) < 2 or tree[0] != "define" or not _is_named_header(tree[1], "domain"):
        raise BlocksworldParseError("domain PDDL must start with (define (domain ...))")
    domain_name = str(tree[1][1])
    actions: set[str] = set()
    for section in tree[2:]:
        if isinstance(section, list) and len(section) >= 2 and section[0] == ":action":
            actions.add(str(section[1]))
    return domain_name, actions


def _parse_problem(tree: list[Any]) -> tuple[str, str, tuple[str, ...], AtomSet, AtomSet]:
    if len(tree) < 2 or tree[0] != "define" or not _is_named_header(tree[1], "problem"):
        raise BlocksworldParseError("problem PDDL must start with (define (problem ...))")
    problem_name = str(tree[1][1])
    domain_name = ""
    objects: tuple[str, ...] | None = None
    init_atoms: AtomSet | None = None
    goal_atoms: AtomSet | None = None

    for section in tree[2:]:
        if not isinstance(section, list) or not section:
            continue
        label = section[0]
        if label == ":domain" and len(section) >= 2:
            domain_name = str(section[1])
        elif label == ":objects":
            objects = tuple(sorted(_parse_objects(section[1:])))
        elif label == ":init":
            init_atoms = _extract_atoms(section[1:], objects=objects or ())
        elif label == ":goal":
            if len(section) != 2:
                raise BlocksworldParseError("problem :goal section must contain one expression")
            goal_atoms = _extract_goal_atoms(section[1], objects=objects or ())

    if not domain_name:
        raise BlocksworldParseError("problem PDDL is missing :domain")
    if objects is None:
        raise BlocksworldParseError("problem PDDL is missing :objects")
    if init_atoms is None:
        raise BlocksworldParseError("problem PDDL is missing :init")
    if goal_atoms is None:
        raise BlocksworldParseError("problem PDDL is missing :goal")
    return problem_name, domain_name, objects, init_atoms, goal_atoms


def _is_named_header(value: Any, expected: str) -> bool:
    return isinstance(value, list) and len(value) == 2 and value[0] == expected and isinstance(value[1], str)


def _parse_objects(items: list[Any]) -> set[str]:
    objects: set[str] = set()
    pending_names: list[str] = []
    index = 0
    while index < len(items):
        item = items[index]
        if not isinstance(item, str):
            raise BlocksworldParseError("nested forms are not supported in :objects")
        if item == "-":
            objects.update(pending_names)
            pending_names = []
            index += 2
            continue
        pending_names.append(item)
        index += 1
    objects.update(pending_names)
    if not objects:
        raise BlocksworldParseError("problem must define at least one object")
    return objects


def _extract_goal_atoms(expression: Any, *, objects: tuple[str, ...]) -> AtomSet:
    if isinstance(expression, list) and expression and expression[0] == "and":
        return _extract_atoms(expression[1:], objects=objects)
    return _extract_atoms([expression], objects=objects)


def _extract_atoms(expressions: list[Any], *, objects: tuple[str, ...]) -> AtomSet:
    object_set = set(objects)
    atoms: set[str] = set()
    for expression in expressions:
        if not isinstance(expression, list) or not expression:
            raise BlocksworldParseError("expected positive atom list")
        predicate = expression[0]
        if predicate in {"and", "not"}:
            raise BlocksworldParseError(f"unsupported atom wrapper in positive state/goal: {predicate}")
        if not isinstance(predicate, str):
            raise BlocksworldParseError("atom predicate must be a symbol")
        args = tuple(str(arg) for arg in expression[1:])
        for arg in args:
            if arg not in object_set:
                raise BlocksworldParseError(f"atom references unknown object: {arg}")
        atoms.add(_atom(predicate, *args))
    return frozenset(atoms)


def _validate_required_actions(action_vocabulary: set[str]) -> None:
    missing = sorted(set(BLOCKSWORLD_ACTIONS) - action_vocabulary)
    extra = sorted(action_vocabulary - set(BLOCKSWORLD_ACTIONS))
    if missing:
        raise BlocksworldParseError(f"missing required Blocksworld actions: {', '.join(missing)}")
    if extra:
        raise BlocksworldParseError(f"unsupported Blocksworld actions: {', '.join(extra)}")


__all__ = [
    "AtomSet",
    "BLOCKSWORLD_ACTIONS",
    "BLOCKSWORLD_PREDICATE_ARITY",
    "BlocksworldAction",
    "BlocksworldParseError",
    "BlocksworldProblem",
    "IllegalActionError",
    "canonical_atom",
    "parse_blocksworld",
]
