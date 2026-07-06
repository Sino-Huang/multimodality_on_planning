# Phase 3 Search Algorithm Trace Concepts

This note records how the Phase 3 trace artifacts should be interpreted when reviewing planner traces such as `outputs/phase3_traces/blocksworld-dev-easy-0004/traces/*.planner_trace.json`.

## Breadth-First Search

Breadth-first search expands reachable states in FIFO order by increasing plan depth. A BFS trace should therefore show dequeued states, generated successors, whether each successor is newly visited, the frontier size after expansion, and a visited-state count. The Phase 3 BFS trace is the closest of the four to a canonical algorithm trace: it records queue expansion events, visited-state growth, and the final expansion statistics.

For `blocksworld-dev-easy-0004`, the BFS trace has `expansion_count: 11`, `visited_count: 21`, and `queue_events` containing dequeued states and successor actions. This matches BFS well.

## Fast Forward Style Local Search

Fast Forward is based on relaxed planning heuristics, commonly using delete-relaxed reachability and relaxed-plan estimates to guide search. A full FF implementation includes more machinery, such as enforced hill-climbing and helpful-action pruning. The Phase 3 `ff` trace is therefore best read as a deterministic FF-style local trace, not as a complete canonical FF planner implementation.

The trace should show, at each step, the current state, delete-relaxed proposition/action layers, the current relaxed-plan proxy, relaxed heuristic estimates for applicable successors, the selected action, and a deterministic tie-break rule. For `blocksworld-dev-easy-0004`, the trace has four steps selecting `(unstack b4 b3)`, `(putdown b4)`, `(pickup b3)`, and `(stack b3 b4)`. It also records `planner_source: local_delete_relaxed_hmax_supporter_closure` and per-step `is_exact_fast_downward_ff: false` metadata. For harder local dead ends such as `blocksworld-train-medium-0011`, the local implementation uses bounded best-first recovery guided by the same delete-relaxed heuristic, then emits the selected plan as the same FF-style trace. This matches the intended local FF-style concept well, with the caveat that it is not full FF enforced hill-climbing.

## Iterated Width k

Iterated Width search prunes states by novelty. In IW(k), a state is expanded when it contains at least one tuple of atoms up to width `k` that has not previously been seen; otherwise it is pruned. The Phase 3 local trace defaults to IW(3) with `local_iw_max_width=3`, and the width is configurable through `local_iw_width` and the dataset helper's `--local-iw-width` flag. An IW(k) trace should therefore show novelty-table state, the novel item that justified expansion, successor novelty, enqueue decisions, and prune events.

For `blocksworld-dev-easy-0004`, the IW trace has `algorithm: iterated_width`, `width: 1`, and events with `novel_item`, `novelty_table_before`, `novelty_table_after`, successor `is_novel`, and `enqueued`. This matches IW(1) trace semantics well. For `blocksworld-train-medium-0011`, IW(1) and IW(2) do not emit a valid plan; `local_iw_width=3` emits a replay-valid 10-action plan and records `width: 3` in the trace.

## Graphplan Style Planning Graph

Graphplan builds alternating proposition and action layers, tracks mutex relations, and extracts a plan from a layer where the goals appear non-mutex. A full Graphplan implementation also computes proposition mutexes and maintains no-good sets during backward extraction. The Phase 3 Graphplan trace is a local deterministic approximation, not full canonical Graphplan.

The trace should show proposition layers, action layers, action mutex pairs, and extraction metadata that clearly states the approximation. For `blocksworld-dev-easy-0004`, the trace has `algorithm: graphplan`, four proposition layers, four action layers, action mutex pairs, and extraction metadata with `source: local_graphplan_serial_extraction`, `mutex_scope: action_level_only`, and `proposition_mutex_computed: false`. This matches the intended local Graphplan-style concept, provided reviewers preserve the caveat that proposition mutexes and no-good backward search are not implemented.

## Current Trace-Fidelity Judgment

The generated traces for `blocksworld-dev-easy-0004` are suitable as Phase 3 local planner traces if described precisely:

- `bfs`: strong match to canonical BFS trace semantics.
- `ff`: good match to an FF-style delete-relaxation trace with relaxed layers, relaxed-plan proxy, and bounded recovery search, not full FF.
- `iw`: good match to configurable IW(k) novelty trace semantics, defaulting to IW(3) for medium-instance trace collection.
- `graphplan`: good match to an action-mutex planning-graph approximation, not full Graphplan.

When using these traces in reports or model supervision descriptions, avoid saying the `ff` and `graphplan` traces are complete canonical planner internals. Use the labels "FF-style" and "Graphplan-style local approximation" unless the implementation is extended to include the missing canonical components.
