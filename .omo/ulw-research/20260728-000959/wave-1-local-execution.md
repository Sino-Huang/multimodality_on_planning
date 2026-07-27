# Wave 1: Local Execution Evidence

## Key findings

- Phases 1-3 provide planning data, trace, serialization, and rendering infrastructure. The plan explicitly excludes trained planner, SFT, real VLM, GPU, and external-service results.
- The existing ignored corpus has 411 historical BFS records and no FF/IW/Graphplan records; it cannot support the proposed four-family experiment.
- Phase 3 later moved to GBFS/FF/IW/Graphplan and rejects BFS, introducing a study-defining provenance conflict.
- Vision is `vision_available_unaligned` in the current historical corpus; tool use is static packaging. Neither is a completed causal treatment.

## Evidence anchors

- `doc/high_level_plans/research_execution_plan.md:57-72, 203-364`
- `doc/detailed_implementation_summary/phase3_complete_supervised_planning_data_summary.md:11-26, 90-95`
- `doc/detailed_implementation_summary/phase3_gbfs_replacement.md:5-18`
- `doc/detailed_implementation_summary/phase3_expert_trajectories_summary.md:5-7, 71, 136-138`

## EXPAND

- LEAD: Regenerate one versioned, aligned corpus only after resolving canonical planner semantics. WHY: dataset provenance is currently incompatible with the claimed experiment.
