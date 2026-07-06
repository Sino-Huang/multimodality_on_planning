# Phase 3 Search Trace Fidelity

For `outputs/phase3_traces/<instance_id>/traces/*.planner_trace.json`, interpret the four planner traces as follows:

- `bfs` is a close canonical BFS trace: FIFO queue events, successor novelty, frontier size, visited count, and expansion count.
- `ff` is an FF-style deterministic local delete-relaxation approximation using delete-relaxed reachability, relaxed proposition/action layers, relaxed-plan supporter closure, successor relaxed-plan ranking, and bounded best-first recovery when the greedy path dead-ends. It is not full canonical Fast Forward with enforced hill-climbing/helpful-action internals. The trace records `planner_source: local_delete_relaxed_hmax_supporter_closure` and `is_exact_fast_downward_ff: false`.
- `iw` is configurable IW(k), defaulting to IW(3): novelty table before/after, novel item, successor novelty, enqueue/prune decisions. `blocksworld-train-medium-0011` is the default-capability target; IW(1) and IW(2) do not find a valid plan for that instance.
- `graphplan` is a Graphplan-style local approximation: proposition/action layers and action mutex pairs, with `proposition_mutex_computed: false` and `mutex_scope: action_level_only`. It is not full Graphplan backward search with proposition mutexes and no-good sets.

Longer review note: `doc/detailed_implementation_summary/phase3_search_algorithm_trace_concepts.md`.

FF upgrade note: `doc/detailed_implementation_summary/phase3_ff_relaxed_trace_upgrade.md`.

Curriculum trace dataset helper: `scripts/phase3/generate_curriculum_trace_dataset.py`. Full command: `source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/generate_curriculum_trace_dataset.py --output-root outputs/phase3_curriculum_traces`. It prints JSON-lines progress to stderr by default, defaults IW to width 3 with `local_iw_max_width=3`, and bounds local Graphplan with `local_max_applicable_actions=2000` plus `local_graphplan_max_expansions=100000` so `blocksworld-train-medium-0011`-class traces are allowed by default.

Focused `blocksworld-train-medium-0011` command: `source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/generate_curriculum_trace_dataset.py --instance-id blocksworld-train-medium-0011 --planner bfs --planner ff --planner iw --planner graphplan --output-root tmp/phase3_bwm0011_all_local_verify --quiet`. Expected signal: four `success_full_trace` attempts and four extracted traces.
