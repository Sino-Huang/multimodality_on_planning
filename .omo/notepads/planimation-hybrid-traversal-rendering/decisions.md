
## Todo 1 Decisions

- `generate_planimation_vlm.py` defaults to the documented four current non-deprecated output roots, while explicit `--dataset-root` values remain available for fixtures and bounded runs.
- Source snapshots are memoized only within one render, VLM-build, or validation operation. This prevents repeated full-file hashing while avoiding a process-global cache that could mask later source changes.
- Verification still reopens the selected JSONL row and compares its exact raw-line SHA-256, `example_id`, and active planner ID. `bfs` is rejected rather than aliased.

## Todo 1 Review-Blocker Decisions

- Validation, rendering, and VLM construction now keep an operation-local index of raw JSONL rows by physical line index. The index retains the exact original bytes used for row SHA-256 validation.
- Manifest `planner`, `active_planner_id`, `split`, `domain`, `instance_id`, and `plan_hash` must now exactly match the indexed source row. Missing or malformed provenance is reported as `source_snapshot_mismatch` rather than leaking lookup/type errors.

## Todo 2 Decisions

- A trace version is mandatory at the nested planner-trace boundary. Existing unversioned source traces are intentionally excluded rather than heuristically interpreted.
- Projection events carry only documented output fields. FF, GBFS, and IW use `concrete_state`; Graphplan proposition/action layers and extraction use `planner_semantics` and never carry a concrete-state source/hash or frame identity.
- `build_vlm_records` validates the frozen reloaded row and raises `trace_event_not_bound_to_replay_transition` instead of emitting plan-level reasoning when a transition cannot bind to a strict trace event.

## Todo 5 Decisions

- Planning-graph layers, mutex, and raw extraction metadata remain semantic-only. A semantic payload with a concrete state, asset, frame, or render-eligibility field is rejected at the trace boundary.
- Graphplan render candidates are created only after the complete extracted plan normalizes, grounds, applies from PDDL init, and satisfies the PDDL goal. The entire extraction is excluded if any transition fails.
- Replay candidates link to the extraction event and to the preceding replay candidate; raw extraction metadata cannot supply a parent link.

## F1 Search Traversal Decisions

- Search traversal is persisted as a third split JSONL family rather than mixed with plan replay, so record type, supervision mode, and release coverage remain unambiguous.
- Output/source overlap is rejected at manifest construction before `mkdir`, preserving immutable source roots.

## F2 Pairing And Release Modularization Decisions

- The existing `planimation_pairing.py` public surface remains stable. Compatibility imports and source-hook forwarding are centralized in `planimation_pairing_implementation.py` rather than duplicated across focused modules.
- Release validation is isolated from release orchestration so typed JSON/file/schema helpers can be independently checked without widening the CLI facade.

## F3 Final Manual QA Refresh (2026-07-16T01:55:10Z)

- The F3 verdict is scoped to the successfully released fixture and the verified fail-closed active-root boundary. Planner projection demonstrates FF/GBFS/IW concrete candidates and Graphplan extraction replay only; it does not fabricate rendered Graphplan layer images or active-root visual metrics.
