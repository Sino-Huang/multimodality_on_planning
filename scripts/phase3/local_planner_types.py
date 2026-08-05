from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import IntEnum
from typing import Literal, Protocol, TypeAlias, TypeVar

from .pddl import Atom, GroundAction, PDDLTask

PlannerName: TypeAlias = Literal["ff", "iw", "graphplan"]
JSONValue: TypeAlias = bool | int | float | str | Sequence["JSONValue"] | Mapping[str, "JSONValue"] | None
TraceEventT = TypeVar("TraceEventT", bound=Mapping[str, JSONValue])


class TraceEventSink(Protocol):
    def append(self, event: Mapping[str, JSONValue], /) -> None: ...


def record_trace_event(
    retained: list[TraceEventT], sink: TraceEventSink | None, event: TraceEventT
) -> None:
    if sink is None:
        retained.append(event)
    else:
        sink.append(event)


class RecoveryPolicy(IntEnum):
    DISABLED = 0
    ENABLED = 1


@dataclass(frozen=True, slots=True)
class LocalPlannerRequest:
    planner: PlannerName
    task: PDDLTask
    grounded: tuple[GroundAction, ...]
    limits: dict[str, int]
    trace_sink: TraceEventSink | None = None

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
