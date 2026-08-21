from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterable, TypeAlias

from examples.planning_benchmark_slice.pddl_state import (
    GroundedAction,
    InvalidActionError,
    PDDLStateAuthority,
    PDDLTransition,
)

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
    (``on(b1,b2)``). State IDs are canonical JSON-encoded sorted atom strings,
    so repeated runs and different PDDL atom orderings produce the same identity
    for the same symbolic state without an extra integrity field.
    """

    domain_name: str
    problem_name: str
    problem_domain_name: str
    objects: tuple[str, ...]
    goal_atoms: AtomSet
    action_vocabulary: tuple[str, ...]
    _authority: PDDLStateAuthority = field(repr=False, compare=False)

    @property
    def authority(self) -> PDDLStateAuthority:
        return self._authority

    @property
    def initial_atoms(self) -> AtomSet:
        return frozenset(self._authority.initial_state.atoms)

    @property
    def goal_is_empty(self) -> bool:
        return not self.goal_atoms

    def state_id(self, state: Iterable[str] | None = None) -> str:
        atoms = self.initial_atoms if state is None else frozenset(state)
        return self._authority.canonical_state(tuple(atoms)).state_id

    def initial_state(self) -> AtomSet:
        return self.initial_atoms

    def is_goal(self, state: Iterable[str]) -> bool:
        return self._authority.is_goal(self._authority.canonical_state(tuple(state)))

    def legal_actions(self, state: Iterable[str] | None = None) -> tuple[BlocksworldAction, ...]:
        atom_set = self.initial_atoms if state is None else frozenset(state)
        actions = self._authority.applicable_actions(self._authority.canonical_state(tuple(atom_set)))
        return tuple(BlocksworldAction(action.name, action.args) for action in actions)

    def legal_action_strings(self, state: Iterable[str] | None = None) -> tuple[str, ...]:
        return tuple(action.serialize() for action in self.legal_actions(state))

    def transition(self, state: Iterable[str], action: BlocksworldAction) -> AtomSet:
        return frozenset(self.transition_record(state, action).target_state.atoms)

    def transition_record(self, state: Iterable[str], action: BlocksworldAction) -> PDDLTransition:
        atom_set = frozenset(state)
        try:
            return self._authority.apply(
                self._authority.canonical_state(tuple(atom_set)),
                GroundedAction(action.name, action.args),
            )
        except InvalidActionError as error:
            raise IllegalActionError(f"illegal action in current state: {action.serialize()}") from error

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
    try:
        authority = PDDLStateAuthority.from_pddl(domain_pddl, problem_pddl)
    except (AssertionError, StopIteration, ValueError) as error:
        raise BlocksworldParseError(str(error)) from error
    _validate_required_actions(set(authority.action_vocabulary))
    if authority.goal_atoms is None:
        raise BlocksworldParseError("Blocksworld goals must be conjunctions of positive atoms")
    return BlocksworldProblem(
        domain_name=authority.domain_name,
        problem_name=authority.problem_name,
        problem_domain_name=authority.problem_domain_name,
        objects=authority.objects,
        goal_atoms=frozenset(authority.goal_atoms),
        action_vocabulary=authority.action_vocabulary,
        _authority=authority,
    )


def canonical_atom(predicate: str, *args: str) -> str:
    return _atom(predicate, *args)


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


def _validate_required_actions(action_vocabulary: set[str]) -> None:
    missing = sorted(set(BLOCKSWORLD_ACTIONS) - action_vocabulary)
    extra = sorted(action_vocabulary - set(BLOCKSWORLD_ACTIONS))
    if missing:
        raise BlocksworldParseError(f"missing required Blocksworld actions: {', '.join(missing)}")
    if extra:
        raise BlocksworldParseError(f"unsupported Blocksworld actions: {', '.join(extra)}")


__all__ = [
    "BLOCKSWORLD_ACTIONS",
    "BLOCKSWORLD_PREDICATE_ARITY",
    "AtomSet",
    "BlocksworldAction",
    "BlocksworldParseError",
    "BlocksworldProblem",
    "IllegalActionError",
    "canonical_atom",
    "parse_blocksworld",
]
