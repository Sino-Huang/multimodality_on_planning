from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping, Sequence
from enum import IntEnum
from typing import Literal, TypeAlias

from .pddl import Atom, GroundAction, PDDLTask

PlannerName: TypeAlias = Literal["ff", "iw", "graphplan"]
JSONValue: TypeAlias = None | bool | int | float | str | Sequence["JSONValue"] | Mapping[str, "JSONValue"]


class RecoveryPolicy(IntEnum):
    DISABLED = 0
    ENABLED = 1


@dataclass(frozen=True, slots=True)
class LocalPlannerRequest:
    planner: PlannerName
    task: PDDLTask
    grounded: tuple[GroundAction, ...]
    limits: dict[str, int]

    @property
    def recovery_policy(self) -> RecoveryPolicy:
        return (
            RecoveryPolicy.DISABLED
            if self.limits.get("local_iw_recovery", RecoveryPolicy.ENABLED) == RecoveryPolicy.DISABLED
            else RecoveryPolicy.ENABLED
        )


@dataclass(frozen=True, slots=True)
class LocalPlannerResult:
    plan: list[str]
    trace: dict[str, JSONValue]
    status: str


@dataclass(frozen=True, slots=True)
class SearchNode:
    state: frozenset[Atom]
    plan: tuple[str, ...]
