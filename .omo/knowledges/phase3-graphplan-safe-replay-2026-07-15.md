# Phase 3 Graphplan Safe Replay Boundary

- Graphplan proposition/action layers, mutex data, and the extraction description remain `planner_semantics`. Reject any semantic payload containing concrete-state, asset, frame, or render-eligibility fields.
- Replay candidates originate only from a validated extraction `selected_plan`, replayed atomically from PDDL init through normalized, grounded, applicable actions to the PDDL goal. A malformed, unknown, inapplicable, or non-goal plan produces no replay candidates.
- Every replay candidate has `state_source="extracted_plan_replay"`, frozen source identity, a stable extraction event ID, and a deterministic parent chain. The initial replay state links to the semantic extraction event; each successor links to the prior validated replay event.
- Candidate reports must keep semantic-event exclusions visible, rather than silently treating planning-graph layers as states.
