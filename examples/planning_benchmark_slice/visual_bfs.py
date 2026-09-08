"""FIFO evaluation controller accepting algorithm-valid successor ties."""

from types import SimpleNamespace

from .bfs_model_input import build_bounded_bfs_model_input_v4
from .model_search_episode import _parse_model_output
from .search_context import IncrementalSearchContext
from .search_memory import (
    AcceptedRetirement,
    AcceptedTransition,
    SearchMemory,
    SearchRetireRequest,
    apply_search_retirement,
    apply_search_transition,
)
from .search_trace import TraceSegmentLimits


class VisualBFSSession:
    def __init__(self, authority, max_calls, max_expansions):
        self.authority = authority
        self.max_calls, self.max_expansions = max_calls, max_expansions
        self.context = IncrementalSearchContext(
            SearchMemory.initial(authority),
            accepted_delta_limit=16,
            limits=TraceSegmentLimits(max_records=max_calls, max_bytes=100_000_000),
        )
        self.active = None
        self.expansions = []
        self.events = []
        self.invalid_operation_count = 0
        self.termination_reason = None
        self.exited_through_goal_check = False
        self.pending = None

    def next_request(self):
        if self.pending is not None:
            return self.pending
        while self.termination_reason is None:
            memory = self.context.memory
            if self.active is None:
                if not memory.frontier:
                    self.termination_reason = "frontier_exhausted"
                    break
                if self.authority.is_goal(memory.state(memory.frontier[0])):
                    self.exited_through_goal_check = True
                    self.termination_reason = "goal_reached"
                    break
                if len(self.expansions) >= self.max_expansions:
                    self.termination_reason = "expansion_budget_exhausted"
                    break
                self.active = memory.frontier[0]
            if len(self.events) >= self.max_calls:
                self.termination_reason = "decision_budget_exhausted"
                break
            state = memory.state(self.active)
            rolling = self.context.rolling_context()
            raw, _ = build_bounded_bfs_model_input_v4(
                authority=self.authority,
                goal_atoms=list(self.authority.goal_atoms or ()),
                observation={
                    "state_id": state.state_id,
                    "state_atoms": list(state.atoms),
                    "frontier": list(memory.frontier),
                    "modality": "text-state",
                },
                checkpoint=rolling.checkpoint,
                accepted_deltas=rolling.accepted_deltas,
                max_bytes=3840,
            )
            available = [c for c in raw["search_memory"]["successor_candidates"] if not c["visited"]]
            if not available and self.active not in memory.frontier:
                self.expansions.append(self.active)
                self.active = None
                continue
            self.pending = SimpleNamespace(model_input=raw)
            return self.pending
        return None

    def submit_output(self, output):
        if self.pending is None:
            raise ValueError("BFS has no pending decision")
        parsed, error = _parse_model_output(output)
        memory = self.context.memory
        operation = parsed["operation"] if parsed else None
        available = [c for c in self.pending.model_input["search_memory"]["successor_candidates"] if not c["visited"]]
        result = None
        if operation is not None:
            if isinstance(operation, SearchRetireRequest):
                if not available and operation.state_id == self.active:
                    result = apply_search_retirement(memory, operation)
            else:
                retire = self.active in memory.frontier
                if (
                    operation.source_state_id == self.active
                    and operation.visit_target
                    and not operation.evaluate_target
                    and operation.frontier_intent.retire_source == retire
                    and operation.frontier_intent.target_position == len(memory.frontier) - int(retire)
                    and any(
                        c["grounded_action"] == {"name": operation.action.name, "args": list(operation.action.args)}
                        for c in available
                    )
                ):
                    result = apply_search_transition(memory, operation, evaluator=_no_evaluation)
        self.events.append({"raw_output": output})
        if error or not isinstance(result, (AcceptedTransition, AcceptedRetirement)):
            self.invalid_operation_count += 1
            self.termination_reason = "deterministic_invalid_operation"
        else:
            assert operation is not None
            self.context.accept(record_index=len(self.events) - 1, operation=operation, result=result)
            if isinstance(result, AcceptedRetirement):
                self.expansions.append(self.active)
                self.active = None
        self.pending = None


def _no_evaluation(_state):
    raise ValueError("BFS does not request heuristic evaluation")
