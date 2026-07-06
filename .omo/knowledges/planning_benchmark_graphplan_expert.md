
## 2026-06-24 Planning Benchmark Graphplan Expert
- `examples/planning_benchmark_slice/experts/graphplan.py` implements the Phase 1-3 P0 Graphplan generator using the existing Blocksworld symbolic core; do not introduce a separate world model.
- The implementation intentionally records action-level mutex only (`deterministic_p0_action_mutex_only_graphplan`) per `doc/research_proposal.md` feasibility simplification. Extraction metadata must keep `proposition_mutex_computed=false` unless full proposition mutex propagation is later implemented.
- `generate_experts` includes Graphplan summary fields `layer_count`, `mutex_pair_count`, and `goal_present_without_mutex`, and the non-trivial fixture should produce selected actions `pickup(a)`, `stack(a,b)`.
