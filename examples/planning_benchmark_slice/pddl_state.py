from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeAlias, cast

from plado import pddl
from plado.parser import parse_and_normalize, tokenize
from plado.semantics.applicable_actions_generator import ApplicableActionsGenerator
from plado.semantics.goal_checker import GoalChecker
from plado.semantics.successor_generator import SuccessorGenerator
from plado.semantics.task import State, Task

GroundActionRef: TypeAlias = tuple[int, tuple[int, ...]]


class InvalidActionError(ValueError):
    """Raised when a grounded action is not applicable in the supplied state."""


class ReplayError(ValueError):
    """Raised when recorded transition provenance does not replay exactly."""


def _json_sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _pddl_tokens(source: str) -> tuple[tuple[str, str], ...]:
    return tuple((token.cat.name, token.tok) for token in tokenize(source))


def _authority_id(domain_pddl: str, problem_pddl: str) -> str:
    return _json_sha256({"domain": _pddl_tokens(domain_pddl), "problem": _pddl_tokens(problem_pddl)})


@dataclass(frozen=True)
class CanonicalState:
    """Deterministic, serializable representation of a PDDL state."""

    atoms: tuple[str, ...]
    authority_id: str
    fluents: tuple[str, ...] = ()
    state_id: str = field(init=False)

    def __post_init__(self) -> None:
        atoms = tuple(sorted(set(self.atoms)))
        fluents = tuple(sorted(set(self.fluents)))
        object.__setattr__(self, "atoms", atoms)
        object.__setattr__(self, "fluents", fluents)
        payload: object = list(atoms) if not fluents else {"atoms": atoms, "fluents": fluents}
        object.__setattr__(self, "state_id", _json_sha256(payload))


@dataclass(frozen=True, order=True)
class GroundedAction:
    name: str
    args: tuple[str, ...]

    def serialize(self) -> str:
        return f"{self.name}({','.join(self.args)})"


@dataclass(frozen=True)
class TransitionProvenance:
    authority_id: str
    source_state_id: str
    action: GroundedAction
    target_state_id: str
    provenance_id: str = field(init=False)

    def __post_init__(self) -> None:
        payload = {
            "action": {"args": self.action.args, "name": self.action.name},
            "authority_id": self.authority_id,
            "source_state_id": self.source_state_id,
            "target_state_id": self.target_state_id,
        }
        object.__setattr__(self, "provenance_id", _json_sha256(payload))

    def to_dict(self) -> dict[str, object]:
        return {
            "action": {"args": list(self.action.args), "name": self.action.name},
            "authority_id": self.authority_id,
            "provenance_id": self.provenance_id,
            "source_state_id": self.source_state_id,
            "target_state_id": self.target_state_id,
        }


@dataclass(frozen=True)
class PDDLTransition:
    source_state: CanonicalState
    action: GroundedAction
    target_state: CanonicalState
    provenance: TransitionProvenance

    @property
    def transition_id(self) -> str:
        return self.provenance.provenance_id


class PDDLStateAuthority:
    """Plado-backed source of truth for one normalized PDDL task."""

    def __init__(self, domain: pddl.Domain, problem: pddl.Problem, authority_id: str) -> None:
        self._domain = domain
        self._problem = problem
        self._task = Task(domain, problem)
        self._applicable = ApplicableActionsGenerator(self._task)
        self._successors = SuccessorGenerator(self._task)
        self._goal_checker = GoalChecker(self._task)
        self.domain_name = domain.name
        self.problem_name = problem.name
        self.problem_domain_name = problem.domain_name
        self.objects = tuple(sorted(obj.name for obj in problem.objects))
        self.action_vocabulary = tuple(sorted(action.name for action in domain.actions))
        self.goal_atoms = _positive_goal_atoms(problem.goal)
        self.authority_id = authority_id
        self.initial_state = self._canonicalize(self._task.initial_state)
        self._states: dict[str, tuple[CanonicalState, State]] = {
            self.initial_state.state_id: (self.initial_state, self._task.initial_state.duplicate())
        }
        self._applicable_by_state: dict[str, dict[GroundedAction, GroundActionRef]] = {}

    @classmethod
    def from_pddl(cls, domain_pddl: str, problem_pddl: str) -> "PDDLStateAuthority":
        with tempfile.TemporaryDirectory(prefix="pddl-state-") as directory:
            authority_id = _authority_id(domain_pddl, problem_pddl)
            root = Path(directory)
            domain_path = root / "domain.pddl"
            problem_path = root / "problem.pddl"
            domain_path.write_text(domain_pddl, encoding="utf-8")
            problem_path.write_text(problem_pddl, encoding="utf-8")
            domain, problem = parse_and_normalize(str(domain_path), str(problem_path))
        return cls(domain, problem, authority_id)

    def canonical_state(self, atoms: tuple[str, ...], fluents: tuple[str, ...] = ()) -> CanonicalState:
        return CanonicalState(atoms, self.authority_id, fluents)

    def applicable_actions(self, state: CanonicalState) -> tuple[GroundedAction, ...]:
        return tuple(sorted(self._applicable_action_refs(state), key=GroundedAction.serialize))

    def _applicable_action_refs(self, state: CanonicalState) -> dict[GroundedAction, GroundActionRef]:
        plado_state = self._resolve_state(state)
        applicable = self._applicable_by_state.get(state.state_id)
        if applicable is None:
            applicable = {self._grounded_action(ref): ref for ref in self._applicable(plado_state)}
            self._applicable_by_state[state.state_id] = applicable
        return applicable

    def apply(self, state: CanonicalState, action: GroundedAction) -> PDDLTransition:
        return self._apply(state, action, register_target=True)

    def preview_apply(self, state: CanonicalState, action: GroundedAction) -> PDDLTransition:
        return self._apply(state, action, register_target=False)

    def _apply(
        self,
        state: CanonicalState,
        action: GroundedAction,
        *,
        register_target: bool,
    ) -> PDDLTransition:
        plado_state = self._resolve_state(state)
        action_ref = self._applicable_action_refs(state).get(action)
        if action_ref is None:
            raise InvalidActionError(f"action is not applicable in state {state.state_id}: {action.serialize()}")

        successors = self._successors(plado_state, cast(Any, action_ref))
        if len(successors) != 1 or successors[0][1] != 1:
            raise ValueError(f"grounded action does not have one deterministic successor: {action.serialize()}")
        successor = successors[0][0]
        target = self._canonicalize(successor)
        if register_target:
            self._states[target.state_id] = (target, successor.duplicate())
        provenance = TransitionProvenance(self.authority_id, state.state_id, action, target.state_id)
        return PDDLTransition(state, action, target, provenance)

    def is_goal(self, state: CanonicalState) -> bool:
        return self._goal_checker(self._resolve_state(state))

    def replay(self, transitions: tuple[PDDLTransition, ...]) -> tuple[CanonicalState, ...]:
        current = self.initial_state
        states = [current]
        for index, recorded in enumerate(transitions):
            provenance = recorded.provenance
            if recorded.source_state != current or provenance.source_state_id != current.state_id:
                raise ReplayError(f"transition {index} source state does not match replay state")
            if provenance.authority_id != self.authority_id:
                raise ReplayError(f"transition {index} was produced by a different authority")
            if provenance.action != recorded.action:
                raise ReplayError(f"transition {index} action does not match its provenance")
            if provenance.target_state_id != recorded.target_state.state_id:
                raise ReplayError(f"transition {index} target state does not match its provenance")
            try:
                reproduced = self.apply(current, recorded.action)
            except InvalidActionError as error:
                raise ReplayError(
                    f"transition {index} records an invalid action: {recorded.action.serialize()}"
                ) from error
            if reproduced.target_state != recorded.target_state:
                raise ReplayError(f"transition {index} target state was not reproduced")
            if reproduced.provenance != provenance:
                raise ReplayError(f"transition {index} provenance was not reproduced")
            current = reproduced.target_state
            states.append(current)
        return tuple(states)

    def _resolve_state(self, state: CanonicalState) -> State:
        if state.authority_id != self.authority_id:
            raise ValueError(f"state belongs to a different authority: {state.authority_id}")
        known = self._states.get(state.state_id)
        if known is None or known[0] != state:
            raise ValueError(f"state is not known to this authority: {state.state_id}")
        return known[1].duplicate()

    def _grounded_action(self, action_ref: GroundActionRef) -> GroundedAction:
        action_id, arguments = action_ref
        return GroundedAction(
            self._task.actions[action_id].name,
            tuple(self._task.objects[index] for index in arguments),
        )

    def _canonicalize(self, state: State) -> CanonicalState:
        atoms: list[str] = []
        for predicate_id, relation in enumerate(state.atoms):
            predicate = self._task.predicates[predicate_id].name
            for arguments in relation:
                args = tuple(self._task.objects[index] for index in arguments)
                atoms.append(_canonical_term(predicate, args))

        fluents: list[str] = []
        for function_id, values in enumerate(state.fluents):
            function = self._task.functions[function_id].name
            for arguments, value in values.items():
                args = tuple(self._task.objects[index] for index in arguments)
                fluents.append(f"{_canonical_term(function, args)}={value}")
        return self.canonical_state(tuple(atoms), tuple(fluents))


def _canonical_term(name: str, args: tuple[str, ...]) -> str:
    return name if not args else f"{name}({','.join(args)})"


def _positive_goal_atoms(goal: pddl.BooleanExpression) -> tuple[str, ...] | None:
    if isinstance(goal, pddl.Truth):
        return ()
    formulas = goal.sub_formulas if isinstance(goal, pddl.Conjunction) else (goal,)
    if not all(isinstance(formula, pddl.Atom) for formula in formulas):
        return None
    return tuple(
        sorted(
            _canonical_term(formula.name, tuple(argument.name for argument in formula.arguments))
            for formula in formulas
            if isinstance(formula, pddl.Atom)
        )
    )


__all__ = [
    "CanonicalState",
    "GroundedAction",
    "InvalidActionError",
    "PDDLStateAuthority",
    "PDDLTransition",
    "ReplayError",
    "TransitionProvenance",
]
