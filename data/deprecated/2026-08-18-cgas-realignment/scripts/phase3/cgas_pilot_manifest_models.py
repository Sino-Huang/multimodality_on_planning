from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PilotRecord:
    candidate_id: str
    instance_id: str
    raw_rank: int
    object_count: int
    composition_signature: str
    source_record_sha256: str
    source_split: str
    domain_sha256: str
    bfs_trace_sha256: str
    iw_trace_sha256: str
    on_plan_row_capacity: int
    off_plan_row_capacity: int
    role: str


@dataclass(frozen=True, slots=True)
class PilotDiversity:
    object_count: int
    instances: int
    repeated_composition_signatures: int
    stack_profiles: int
    goal_edge_levels: int


@dataclass(frozen=True, slots=True)
class PilotSelection:
    records: tuple[PilotRecord, ...]
    diversity: tuple[PilotDiversity, ...]
