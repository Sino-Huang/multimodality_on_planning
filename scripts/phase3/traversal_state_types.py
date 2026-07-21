from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping

from .trace_contracts import FrozenSourceIdentity, TRACE_CONTRACT_VERSION


JSONValue = str | int | float | bool | None | list["JSONValue"] | dict[str, "JSONValue"]
JSONMapping = Mapping[str, JSONValue]
STATE_SOURCES = Literal["trace_recorded", "pddl_action_reconstruction", "extracted_plan_replay"]


@dataclass(frozen=True, slots=True)
class TraversalProjectionInput:
    source_identity: FrozenSourceIdentity
    source_row: JSONMapping
    domain_path: Path
    problem_path: Path
    max_grounded_actions: int = 100_000
    max_grounded_atoms: int = 200_000


@dataclass(frozen=True, slots=True)
class TraversalStateCandidate:
    event_id: str
    parent_event_id: str | None
    source_identity: FrozenSourceIdentity
    planner: str
    trace_contract_version: str
    event_kind: str
    state_role: str
    state_source: STATE_SOURCES
    normalized_action: str | None
    state_atoms: tuple[str, ...]
    state_asset_hash: str
    extraction_event_id: str | None = None
    extraction_step_index: int | None = None

    def to_record(self) -> dict[str, JSONValue]:
        return {
            "event_id": self.event_id,
            "parent_event_id": self.parent_event_id,
            "source_identity": self.source_identity.to_record(),
            "planner": self.planner,
            "trace_contract_version": self.trace_contract_version,
            "event_kind": self.event_kind,
            "state_role": self.state_role,
            "state_source": self.state_source,
            "normalized_action": self.normalized_action,
            "state_atoms": list(self.state_atoms),
            "state_asset_hash": self.state_asset_hash,
            "extraction_event_id": self.extraction_event_id,
            "extraction_step_index": self.extraction_step_index,
        }


@dataclass(frozen=True, slots=True)
class TraversalCandidateExclusion:
    event_id: str
    source_identity: FrozenSourceIdentity
    planner: str
    trace_contract_version: str
    reason: str

    def to_record(self) -> dict[str, JSONValue]:
        return {
            "event_id": self.event_id,
            "source_identity": self.source_identity.to_record(),
            "planner": self.planner,
            "trace_contract_version": self.trace_contract_version,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class TraversalStateProjection:
    candidates: tuple[TraversalStateCandidate, ...]
    exclusions: tuple[TraversalCandidateExclusion, ...]


def state_asset_hash(atoms: tuple[str, ...]) -> str:
    return hashlib.sha256(json.dumps(atoms, separators=(",", ":")).encode("utf-8")).hexdigest()


def exclusion(identity: FrozenSourceIdentity, planner: str, event_id: str, reason: str) -> TraversalCandidateExclusion:
    return TraversalCandidateExclusion(event_id, identity, planner, TRACE_CONTRACT_VERSION, reason)
