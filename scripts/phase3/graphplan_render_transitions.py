from __future__ import annotations

from dataclasses import dataclass

from .traversal_state_types import JSONValue, TraversalProjectionInput
from .traversal_states import project_traversal_state_candidates


@dataclass(frozen=True, slots=True)
class GraphplanRenderTransition:
    step_index: int
    action: str
    state_before: tuple[str, ...]
    state_after: tuple[str, ...]
    event_id: str
    extraction_event_id: str

    def to_record(self) -> dict[str, JSONValue]:
        return {
            "step_index": self.step_index,
            "action": self.action,
            "state_before": list(self.state_before),
            "state_after": list(self.state_after),
            "event_id": self.event_id,
            "extraction_event_id": self.extraction_event_id,
            "state_source": "extracted_plan_replay",
        }


def graphplan_render_transitions(request: TraversalProjectionInput) -> tuple[GraphplanRenderTransition, ...]:
    """Derive pre-action render inputs only from a validated Graphplan extraction."""
    candidates = project_traversal_state_candidates(request).candidates
    transitions: list[GraphplanRenderTransition] = []
    for before, after in zip(candidates, candidates[1:]):
        if before.state_source != "extracted_plan_replay" or after.state_source != "extracted_plan_replay":
            return ()
        if after.normalized_action is None or before.extraction_event_id is None:
            return ()
        transitions.append(
            GraphplanRenderTransition(
                step_index=before.extraction_step_index or 0,
                action=after.normalized_action,
                state_before=before.state_atoms,
                state_after=after.state_atoms,
                event_id=before.event_id,
                extraction_event_id=before.extraction_event_id,
            )
        )
    return tuple(transitions)
