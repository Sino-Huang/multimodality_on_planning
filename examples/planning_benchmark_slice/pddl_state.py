from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeAlias, cast

from plado import pddl
from plado.parser import parse_and_normalize
from plado.semantics.applicable_actions_generator import ApplicableActionsGenerator
from plado.semantics.goal_checker import GoalChecker
from plado.semantics.successor_generator import SuccessorGenerator
from plado.semantics.task import State, Task

GroundActionRef: TypeAlias = tuple[int, tuple[int, ...]]


class InvalidActionError(ValueError):
    """Raised when a grounded action is not applicable in the supplied state."""


class ReplayError(ValueError):
    """Raised when recorded transition provenance does not replay exactly."""


def _canonical_identity(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


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
        object.__setattr__(self, "state_id", _canonical_identity(payload))


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
        object.__setattr__(self, "provenance_id", _canonical_identity(payload))

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
        self.objects_by_type = _objects_by_declared_type(domain, problem)
        self.action_vocabulary = tuple(sorted(action.name for action in domain.actions))
        self.goal_atoms = _positive_goal_atoms(problem.goal)
        self.canonical_goal = _canonical_formula(problem.goal)
        modified_predicates = _modified_predicates(domain)
        self.static_initial_facts = tuple(
            sorted(
                _canonical_term(item.name, tuple(argument.name for argument in item.arguments))
                for item in problem.initial
                if isinstance(item, pddl.Atom) and item.name not in modified_predicates
            )
        )
        self.authority_id = authority_id
        self.initial_state = self._canonicalize(self._task.initial_state)
        self._states: dict[str, tuple[CanonicalState, State]] = {
            self.initial_state.state_id: (self.initial_state, self._task.initial_state.duplicate())
        }
        self._applicable_by_state: dict[str, dict[GroundedAction, GroundActionRef]] = {}
        self._previews: dict[tuple[str, GroundedAction], PDDLTransition] = {}

    @classmethod
    def from_pddl(cls, domain_pddl: str, problem_pddl: str) -> "PDDLStateAuthority":
        domain_pddl = _compile_either_parameter_types(domain_pddl)
        problem_pddl = _drop_undeclared_initial_fluents(domain_pddl, problem_pddl)
        with tempfile.TemporaryDirectory(prefix="pddl-state-") as directory:
            root = Path(directory)
            domain_path = root / "domain.pddl"
            problem_path = root / "problem.pddl"
            domain_path.write_text(domain_pddl, encoding="utf-8")
            problem_path.write_text(problem_pddl, encoding="utf-8")
            domain, problem = parse_and_normalize(str(domain_path), str(problem_path))
        return cls(domain, problem, f"{domain.name}/{problem.name}")

    def canonical_state(self, atoms: tuple[str, ...], fluents: tuple[str, ...] = ()) -> CanonicalState:
        return CanonicalState(atoms, self.authority_id, fluents)

    def task_context(self) -> dict[str, object]:
        """Return static task facts that are not carried in dynamic states."""

        return {
            "canonical_goal": self.canonical_goal,
            "initial_dynamic_atoms": list(self.initial_state.atoms),
            "initial_dynamic_fluents": list(self.initial_state.fluents),
            "objects_by_type": {type_name: list(objects) for type_name, objects in self.objects_by_type},
            "static_initial_facts": list(self.static_initial_facts),
        }

    def semantic_task_identity(self) -> str:
        """Canonical task semantics used to isolate train and development tasks."""

        return _canonical_identity(
            {
                "goal": self.canonical_goal,
                "initial_dynamic_atoms": self.initial_state.atoms,
                "initial_dynamic_fluents": self.initial_state.fluents,
                "objects_by_type": self.objects_by_type,
                "static_initial_facts": self.static_initial_facts,
            }
        )

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
        key = (state.state_id, action)
        preview = self._previews.get(key)
        if preview is None:
            preview = self._apply(state, action, register_target=False)
            self._previews[key] = preview
        return preview

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


def _drop_undeclared_initial_fluents(domain_pddl: str, problem_pddl: str) -> str:
    functions = _declared_functions(domain_pddl)
    section = _balanced_section(problem_pddl, "(:init")
    if section is None:
        return problem_pddl
    start, end, init_text = section
    assignment = re.compile(
        r"\(\s*=\s*\(\s*([^\s()]+)(?:\s+[^()]*)?\)\s*[^()]+\)",
        flags=re.IGNORECASE,
    )
    normalized_init = assignment.sub(
        lambda match: match.group(0) if match.group(1).lower() in functions else "",
        init_text,
    )
    return problem_pddl[:start] + normalized_init + problem_pddl[end:]


def _declared_functions(domain_pddl: str) -> set[str]:
    section = _balanced_section(domain_pddl, "(:functions")
    if section is None:
        return set()
    return {
        name.lower()
        for name in re.findall(r"\(\s*([^\s():]+)", section[2])
        if name.lower() != ":functions"
    }


def _compile_either_parameter_types(domain_pddl: str) -> str:
    if "(either" not in domain_pddl.lower():
        return domain_pddl
    parents = _declared_type_parents(domain_pddl)

    def replace(match: re.Match[str]) -> str:
        members = match.group(1).split()
        ancestor = _nearest_common_ancestor(members, parents)
        return ancestor if ancestor is not None else match.group(0)

    return re.sub(r"\(\s*either\s+([^()]+)\)", replace, domain_pddl, flags=re.IGNORECASE)


def _declared_type_parents(domain_pddl: str) -> dict[str, str]:
    section = _balanced_section(domain_pddl, "(:types")
    if section is None:
        return {}
    tokens = re.findall(r"[^\s()]+", section[2])[1:]
    parents: dict[str, str] = {}
    pending: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index].lower()
        if token == "-" and index + 1 < len(tokens):
            parent = tokens[index + 1].lower()
            for name in pending:
                parents[name] = parent
            pending = []
            index += 2
            continue
        pending.append(token)
        index += 1
    for name in pending:
        parents[name] = "object"
    return parents


def _nearest_common_ancestor(members: list[str], parents: dict[str, str]) -> str | None:
    paths = [_type_path(member.lower(), parents) for member in members]
    common = set(paths[0]).intersection(*paths[1:]) if paths else set()
    return min(common, key=lambda item: max(path.index(item) for path in paths)) if common else None


def _type_path(name: str, parents: dict[str, str]) -> list[str]:
    path = [name]
    while path[-1] != "object":
        path.append(parents.get(path[-1], "object"))
    return path


def _balanced_section(text: str, token: str) -> tuple[int, int, str] | None:
    match = re.search(re.escape(token), text, flags=re.IGNORECASE)
    if match is None:
        return None
    depth = 0
    for index in range(match.start(), len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                end = index + 1
                return match.start(), end, text[match.start() : end]
    return None


def _objects_by_declared_type(
    domain: pddl.Domain,
    problem: pddl.Problem,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    grouped: dict[str, set[str]] = {}
    for item in (*domain.constants, *problem.objects):
        grouped.setdefault(item.type_name, set()).add(item.name)
    return tuple((type_name, tuple(sorted(objects))) for type_name, objects in sorted(grouped.items()))


def _modified_predicates(domain: pddl.Domain) -> frozenset[str]:
    names: set[str] = set()

    def collect(effect: pddl.ActionEffect) -> None:
        if isinstance(effect, pddl.AtomEffect):
            names.add(effect.name)
        elif isinstance(effect, pddl.NegativeEffect):
            names.add(effect.atom.name)
        elif isinstance(effect, pddl.ConjunctiveEffect):
            for child in effect.effects:
                collect(child)
        elif isinstance(effect, (pddl.ConditionalEffect, pddl.UniversalEffect)):
            collect(effect.effect)
        elif isinstance(effect, pddl.ProbabilisticEffect):
            for outcome in effect.outcomes:
                collect(outcome.effect)

    for action in domain.actions:
        collect(action.effect)
    return frozenset(names)


def _canonical_formula(formula: pddl.BooleanExpression) -> object:
    if isinstance(formula, pddl.Atom):
        return ["atom", formula.name, [argument.name for argument in formula.arguments]]
    if isinstance(formula, pddl.Negation):
        return ["not", _canonical_formula(formula.sub_formula)]
    if isinstance(formula, (pddl.Conjunction, pddl.Disjunction)):
        operator = "and" if isinstance(formula, pddl.Conjunction) else "or"
        children = [_canonical_formula(child) for child in formula.sub_formulas]
        return [operator, sorted(children, key=_canonical_identity)]
    if isinstance(formula, (pddl.Forall, pddl.Exists)):
        operator = "forall" if isinstance(formula, pddl.Forall) else "exists"
        parameters = sorted((parameter.name, parameter.type_name) for parameter in formula.parameters)
        return [operator, parameters, _canonical_formula(formula.sub_formula)]
    if isinstance(formula, pddl.Truth):
        return ["true"]
    if isinstance(formula, pddl.Falsity):
        return ["false"]
    return ["expression", formula.dump(0)]


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
