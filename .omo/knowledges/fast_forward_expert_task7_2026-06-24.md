# Fast Forward-style planning expert Task 7

- `examples/planning_benchmark_slice/experts/fast_forward.py` implements the Phase 3 Fast Forward-style expert as a documented P0 approximation, not full Fast Downward FF.
- Approximation ID: `deterministic_p0_hmax_relaxed_reachability`.
- Heuristic: ground the four supported Blocksworld operators, ignore delete effects during relaxed reachability, propagate h-max-style atom costs, then count deterministic supporter-action closure size as approximate relaxed-plan length.
- Successor selection rule: sort all legal successors by `(heuristic_value, canonical_action_string)` and emit `min_heuristic_then_action_lexicographic`.
- Required evidence files from verification: `.sisyphus/evidence/phase1-3-task-7-ff.json`, `.sisyphus/evidence/phase1-3-task-7-validator.json`, and `.sisyphus/evidence/phase1-3-task-7-tiebreak.txt`.
