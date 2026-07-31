# CGAS P0 Provenance Gate

Date: 2026-07-28

## Contract

- P0 accepts only Blocksworld `breadth_first_search` records from `scripts.phase3.cgas_bfs.run_fifo_bfs` and exact width-1 `iterated_width` records from `scripts.phase3.local_iw.run_iterated_width`.
- BFS provenance must bind its FIFO `deque` implementation, sorted canonical action tie-break, implementation digest, limits, command, source digest, trace version, split, and replay-validation ID.
- IW recovery plans are excluded. All real IW expansion and prune events retain novelty table before/after, novelty item, and `width_decision`.
- A manifest must predeclare a non-empty structural-OOD partition, including held-out object count, horizon, and composition; its IDs cannot overlap emitted train/dev/test IDs.

## Verification

`python -m scripts.phase3.cgas_provenance --verify --output-root <candidate>` reports zero accepted rows whenever any provenance, split, replay, or novelty error exists. Rejections use a stable `record_id` and a machine-readable reason.

Publication stages an entire candidate, validates it, then replaces the destination only after a clean report. An invalid generated candidate is removed without modifying an existing published root.
