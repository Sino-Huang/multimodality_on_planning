from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from .pddl import Atom, GroundAction, PDDLTask

PlannerName: TypeAlias = Literal["ff", "iw", "graphplan"]
JSONValue: TypeAlias = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]


@dataclass(frozen=True, slots=True)
class LocalPlannerRequest:
    planner: PlannerName
    task: PDDLTask
    grounded: tuple[GroundAction, ...]
    limits: dict[str, int]


@dataclass(frozen=True, slots=True)
class LocalPlannerResult:
    plan: list[str]
    trace: dict[str, JSONValue]
    status: str


@dataclass(frozen=True, slots=True)
class SearchNode:
    state: frozenset[Atom]
    plan: tuple[str, ...]
