# Phase 3 Concrete Traversal State Projection

- Candidate `event_id` must retain frozen root, JSONL, line, source record, planner event, and candidate-role provenance. A sorted state hash is solely an asset-sharing key and must never identify a graph event.
- FF successor atoms are recorded but must still equal deterministic normalized-action application from the recorded parent. GBFS and IW successor atoms are not recorded, so they are created only after canonical action lookup and precondition validation.
- A failed successor edge is an exclusion, not a candidate: malformed action, unknown action, unsupported PDDL, inapplicability, and atom mismatch must schedule no frame job.
- Existing 15-puzzle curriculum rows are legacy/unversioned and therefore correctly excluded by the strict Todo 2 boundary; do not add a compatibility fallback.

## Semantic Label Correction

- Concrete traversal trace records must carry an explicit `event_kind`: `expansion`, `generation`, `revisit`, or `backtrack`. The candidate projector copies this trace field and must never infer it from an action, parent link, state equality, novelty, or enqueue relationship.
- Local FF and GBFS emit parent `expansion` plus successor `generation`/`revisit` labels. Local IW emits expand `expansion`, prune `backtrack`, and labels each successor from the recorded search outcome before serialization.
- The semantic fixture uses PDDL-valid repeated `(move a b)` transitions. It proves candidates can share a state asset hash while retaining distinct generation, revisit, and backtrack event IDs.
