# Output VLM Dataset Integrity Audit - 2026-07-27

## Scope

Read-only audit of the active structured output roots:

- `outputs/reasoning_traces/curriculum/phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round`
- `outputs/reasoning_traces/vlm_records/stratified_pilot_20260725`
- `outputs/image_frames/phase3_planimation_frames_stratified_pilot_20260725`

## Verified Integrity

- The curriculum has 5,434 textual records over the six published domains: blocksworld (1,214), elevators (752), ferry (752), gripper (708), logistics (1,300), and towers_of_hanoi (708).
- The VLM corpus has 2,568 records: 52 `full_reasoning`, 331 `step_vlm`, and 2,185 `search_traversal` rows. Its split counts match `reports/vlm_record_summary.json` exactly.
- The 52 selected full trajectories cover every domain/split combination except `gripper/test`. The active curriculum has 48 `gripper/test` textual records, but the pilot has no paired VLM row or image for that split. The frozen selection metadata records deterministic ordering and transition limits but no exclusion reason, so treat this as an undocumented pilot-coverage limitation rather than a corrupt or missing-file condition.
- All nine VLM JSONLs in `reasoning_traces/vlm_records` are byte-identical to their canonical copies in the pilot image-frame root.
- Every VLM row has an existing remapped PNG, VFG trace, derived PDDL, and cache directory. PNG and VFG SHA-256 values match their stored provenance. Source JSONL line indices, record hashes, domain, split, and instance identifiers also match the active curriculum.
- The state-render manifest has 2,568 rows and 759 unique frame paths. Those 759 paths exactly equal the VLM record frame-path set, so no approved render-manifest frame lacks a VLM reference and no VLM record lacks a manifest frame.

## Scope and Cache Notes

- The active release is explicitly the `safe_no_visitall` six-domain corpus. Visitall traces were moved to `outputs/deprecated/phase3/curriculum_traces`; they are intentionally outside the active curriculum and VLM pilot.
- The pilot cache has 1,331 physical PNG/VFG/PDDL sets, but 572 sets are absent from the approved state-render manifest. They are cache residue, not missing VLM text or missing approved frames. Keep them unless a separately approved cache-pruning procedure determines they are safe to remove.

## Consumer Compatibility Risk

The nine VLM JSONLs are immutable copies, so all 2,568 values of each of `artifact_paths.image_path`, `artifact_paths.render_trace_path`, `artifact_paths.derived_problem_path`, and `provenance.render.cache_dir` retain the old `outputs/phase3_planimation_frames_stratified_pilot_20260725/...` prefix. Those old paths no longer exist after relocation. Consumers must translate that prefix to `outputs/image_frames/phase3_planimation_frames_stratified_pilot_20260725/...`; the repository has current-root constants and a migration journal, but this audit found no generic resolver for the embedded paths.

The migration's source-to-copy map and expected hashes are in `outputs/deprecated/receipts/output-reorganization-20260727/records.json`.
