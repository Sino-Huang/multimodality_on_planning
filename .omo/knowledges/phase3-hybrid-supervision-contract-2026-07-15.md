# Phase 3 Hybrid Supervision Contract

- `full_reasoning_*.jsonl` records use `supervision_mode=hybrid_full` and a `planner_trace` target; `step_vlm_*.jsonl` uses `supervision_mode=hybrid_step` and a next-action target.
- Every record has strict pair/event/state/trace/render provenance and only portable relative artifact paths. The schema and `validate_vlm_record` reject absent or unexpected nested fields.
- `diagnostics/hybrid_output_manifest.json` is the stable handoff for later release verification. Bounded smoke is always `partial=true`, includes selected pair/state IDs and `render_limit`, and is never production-complete.
- Production rejects `--render-limit`; it can emit only complete contiguous plan coverage beginning at step zero. Missing initial coverage yields no full record and makes `production_complete=false`.
- `search_traversal_<split>.jsonl` is a third, separately validated record family for strict FF/GBFS/IW concrete events. It retains event IDs independently from content-addressed state assets; raw Graphplan layers are excluded.
