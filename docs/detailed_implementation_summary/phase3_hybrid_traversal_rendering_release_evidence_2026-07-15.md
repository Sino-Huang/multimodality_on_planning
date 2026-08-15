# Phase 3 Hybrid Traversal Rendering and Release Evidence

Date: 2026-07-15

## Scope and Status

Phase 3 now has a strict hybrid full and step supervision format, versioned traversal contracts, provenance-safe state projection, validated Planimation rendering, hardened cache and archive handling, release verification, and staged rollout receipts.

The completed technical work and the corpus rollout status are different facts:

- The fresh temporary fixture release passed every release and fixture-promotion gate.
- The frozen active-source promotion did not pass. The probed 15-puzzle root has 688 legacy rows and zero strict-v1 eligible rows because every row lacks `trace_contract_version`.
- Changed-canary rendering, stratified pilot rendering, complete-domain rendering, and frozen-full rendering have not started from the active source roots.
- This document does not claim an active corpus release, frozen-full release, or Phase 3 corpus completion.

## Hybrid Output Format

The generator writes separate strict JSONL families for each split:

- `full_reasoning_{train,dev,test}.jsonl` uses `record_type=full_reasoning_record` and `supervision_mode=hybrid_full`. One eligible pair can produce one full record, anchored to the validated step-zero pre-action render, with the planner-trace supervision target.
- `step_vlm_{train,dev,test}.jsonl` uses `record_type=step_vlm_record` and `supervision_mode=hybrid_step`. It produces one next-action target for each validated pre-action plan step.

Both formats carry exact pair, event, state, trace, and render provenance. Their artifact paths are repository-relative. The root and nested schemas reject omitted fields and unexpected fields. Full and step schemas are separate, and only step records declare `step_index` at the record boundary.

Rendering produces one pre-action frame per plan action and one terminal diagnostic frame. Only pre-action frames become next-action supervision rows. A zero-action solved case has one initial and terminal full frame and no step rows. Missing step zero yields no full record and prevents production completion.

## Strict Snapshot and Trace Identity

Each pair reloads its source row from the frozen source root and records:

- `source_root_id` and `source_root_sha256`
- root-relative `source_jsonl` and physical `source_line_index`
- `source_record_sha256` and `source_split_sha256`
- `pair_id`, `example_id`, `plan_hash`, planner, split, and instance identity

The required traversal contract is `phase3_traversal_trace_v1` for FF, GBFS, IW, and Graphplan. Missing, malformed, legacy, unsupported-version, and legacy `bfs` traces are controlled exclusions. There is no compatibility alias, inferred version, or plan-level fallback.

Rollout preparation freezes selected pair IDs and the same source-root, JSONL, line, record, planner, split, domain, and plan-length identity. The selection receives its own SHA-256 and the input pairing-manifest SHA-256 before rendering.

## Concrete State and Graphplan Boundary

FF, GBFS, and IW may produce render candidates only from strict concrete events. FF successor atoms must match deterministic PDDL action application. GBFS and IW successors are reconstructed only from a validated parent state and an applicable normalized action. Expansion, generation, revisit, and backtrack labels remain explicit event semantics even when states share one content-addressed asset.

Graphplan proposition layers, action layers, mutexes, and extraction events are planner semantics, not concrete visual states. They never claim a frame or renderable state. Only the extraction event's validated `selected_plan` can be replayed from the PDDL initial state. Every action must be grounded and applicable, and the replay must reach the goal before its `extracted_plan_replay` states can render.

## Render, Cache, and Semantic Gates

The render cache identity includes the managed profile path and SHA-256, domain and problem hashes, concrete state hash, renderer configuration, schema identity, derived-PDDL hash, VFG hash, PNG hash, and decoded dimensions. A cache hit is accepted only after those receipts, the derived state, VFG structure, PNG decoding, and semantic image checks pass. Stale metadata or a corrupt image forces a rerender.

Raster archive extraction rejects escaping paths, symlinks, non-PNG members, oversized members, excessive compression, and excessive aggregate payloads before writing any member.

Semantic image validation decodes each PNG, validates stage-zero VFG sprite geometry, and rejects malformed, boolean, nonnumeric, out-of-canvas, degenerate, or coincident bounds. Each required sprite needs at least 1 percent non-background coverage inside its projected image bounds.

Render verification requires exactly `plan_length + 1` successful state renders for each training-eligible pair. Release verification also checks artifact hashes, strict record validation, split isolation, unique IDs, expected pair coverage, and reconciled manifest counts.

## Generator and Verifier Modes

`scripts/phase3/generate_planimation_vlm.py` supports these output boundaries:

- Default `--mode production`: rejects `--render-limit`. A releasable root must have `partial=false`, `production_complete=true`, no render limit, and complete contiguous step-zero coverage.
- `--mode bounded-smoke --render-limit N`: writes a partial diagnostic manifest with selected pair and state IDs. It is never production-complete or promotable.
- `--manifest-only`: builds and reports the immutable pairing boundary without rendering.
- `--render-only`: builds the manifest and state renders but does not emit hybrid JSONL records.
- `--selection-file`: restricts materialization to the frozen pair IDs produced by rollout preparation.

`scripts/phase3/verify_planimation_vlm.py` has three fail-closed modes:

- `--mode manifest` validates the nonempty pairing manifest, schema, strict pair records, and immutable source reload.
- `--mode render` adds render reports, the hybrid output manifest, state-render records, semantic image receipts, and exact render cardinality.
- `--mode release` adds both strict schemas, all six split JSONL files, production-complete policy, artifacts and hashes, split isolation, IDs, coverage, and count reconciliation.

## Rollout Stages and Receipts

`scripts/phase3/rollout_gates.py prepare` freezes a deterministic selection. `assess` requires selection integrity, release-mode verification, stage coverage, and any required prior approved receipt. The ordered stages are `fixture`, `changed-canary`, `stratified-pilot`, `complete-domain`, and `frozen-full`.

The approved fixture receipt records one pair, two state renders, one train full record, one train step record, verified semantic image QA, and hashes for the hybrid output and state-render manifests. Its evidence root is `tmp/phase3_release_fixture_task9_fixture_cli_20260715`.

The active-source changed-canary receipt is blocked. `tmp/phase3_task9_active_probe_20260715/reports/pairing_summary.json` records 688 pairs and `training_eligible=0`; all 688 have `trace_contract_exclusion:missing_required_field: trace_contract_version`. Its frozen selection has no pair IDs, and its promotion receipt is not approved. No active-source canary image or contact sheet exists, so none is claimed.

## Reproducible Fixture Commands

All commands below were run from the repository root on 2026-07-15. Each exited zero. They write only under `tmp/` or pytest-managed temporary directories.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.trace_contracts --fixtures tests/phase3/fixtures/traversal_trace_contract_cases.json --report tmp/phase3_task10_trace_contract_report.json
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.traversal_state_projection_cli --fixtures tests/phase3/fixtures/traversal_state_projection_cases.json --domain tests/phase3/fixtures/traversal_state_domain.pddl --problem tests/phase3/fixtures/traversal_state_problem.pddl --report tmp/phase3_task10_traversal_projection_report.json
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_planimation_pairing.py::test_generated_hybrid_schemas_validate_emitted_records_and_reject_extra_root_field tests/phase3/test_verify_planimation_vlm.py::test_release_mode_accepts_complete_output_and_rejects_required_failures -q
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/verify_planimation_vlm.py --output-root tmp/phase3_release_fixture_task9_fixture_cli_20260715 --mode release
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/rollout_gates.py assess --output-root tmp/phase3_release_fixture_task9_fixture_cli_20260715 --stage fixture --selection-file tmp/phase3_release_fixture_task9_fixture_cli_20260715/diagnostics/rollout_selection.json
```

Observed results:

- Trace fixtures projected valid FF, GBFS, and IW events, plus three valid Graphplan semantic events. Four malformed fixtures were excluded with stable missing-field reasons.
- State projection emitted two candidates each for FF, GBFS, and IW. The Graphplan fixture emitted two extracted-plan replay candidates and excluded its proposition and action layers as nonvisual.
- The focused schema and release fixture tests returned `2 passed in 1.90s`.
- Release verification reconciled one pair, two state renders, one train full record, and one train step record.
- Fixture assessment returned `approved=true`, no reasons, one pair, and two state renders.

## Evidence Index

- `.omo/evidence/phase3-task-3-render-cache.json`
- `.omo/evidence/phase3-task-4-traversal-projection.json`
- `.omo/evidence/phase3-task-5-graphplan-traversal.json`
- `.omo/evidence/phase3-task-6-render-validation.json`
- `.omo/evidence/phase3-task-7-hybrid-supervision.json`
- `.omo/evidence/phase3-task-8-release-verifier.json`
- `.omo/evidence/phase3-task-9-rollout-gates-2026-07-15.json`
- `.omo/evidence/phase3-task-10-documentation-command-log-2026-07-15.json`
- `tmp/phase3_task10_trace_contract_report.json`
- `tmp/phase3_task10_traversal_projection_report.json`
- `tmp/phase3_task2_pytest_runtime_report.md`

Todo 1 and Todo 2 implementation history is retained in the dated pairing and traversal-contract summaries and the append-only notepads. No separate `.omo/evidence/phase3-task-1-*.json` or `.omo/evidence/phase3-task-2-*.json` file exists, so this document does not invent one.

## Known Limitations

The frozen active sources predate the strict trace contract. Promotion requires source rows emitted with `trace_contract_version=phase3_traversal_trace_v1`; this work did not backfill, mutate, or reinterpret legacy rows.

The broad Phase 3 pytest run also has an independent generator timeout. A 106-test run stopped at `test_15puzzle_easy_first_ten_curriculum_trace_cli_defaults_emit_all_planner_traces` after 600.01 seconds with exit 124, and the isolated node stopped after 180.00 seconds with exit 124. The nested curriculum generator and its timeout cleanup are outside the hybrid pairing and rendering path. Focused fixture gates pass, but no broad-suite pass is claimed.

Final verification still follows Todo 10. The approved temporary fixture is release evidence for the fixture boundary only, not proof of active corpus promotion or release completion.
