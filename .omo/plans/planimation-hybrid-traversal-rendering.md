# planimation-hybrid-traversal-rendering - Work Plan

## TL;DR (For humans)
<!-- Fill this LAST, after the detailed plan below is written, so it summarizes the REAL plan. -->
<!-- Plain English for a non-engineer: NO file paths, NO todo numbers, NO wave/agent/tool names. -->

**What you'll get:** A provenance-safe visual dataset that pairs Planimation frames with both final-plan replay states and planner search-traversal events. Every record will identify whether its frame represents a final-plan step, an expanded node, a generated successor, a revisit, or a Graphplan planning-graph event.

**Why this approach:** Concrete PDDL states can be faithfully rendered by Planimation, while search semantics are graph-shaped. Keeping `plan_replay` and `search_traversal` separate prevents branches and backtracking from being mislabeled as a final plan.

**What it will NOT do:** It will not reuse unaligned historical frames as training targets, fabricate concrete Graphplan states, or release stale, partial, unreadable, or semantically invalid renders.

**Effort:** Large
**Risk:** High - renderer behavior and planner trace semantics must stay valid under a much larger workload.
**Decisions to sanity-check:** Hybrid supervision is intentional; Graphplan raw traversal remains nonvisual; historical frames remain diagnostics only.

Your next move: start execution with the approved plan, or request a high-accuracy review first. Full execution detail follows below.

---

> TL;DR (machine): Large/high-risk hybrid traversal renderer with strict provenance, adapters, cache/image validation, staged canaries, and release gates.

## Scope
### Must have
- Freeze a source selection from the four current non-deprecated `outputs/phase3_curriculum_traces_*` roots, persisting root/split hashes and every selected JSONL row identity.
- Replace standalone `traces/**.full_example.json` loading with `source_jsonl`, line index, `example_id`, and record-hash provenance.
- Add strict versioned trace adapters and traversal-event schemas for `gbfs`, `ff`, `iw`, and `graphplan`.
- Emit distinct `plan_replay` and `search_traversal` records. State assets may be shared only through verified canonical state content hashes.
- Project FF states directly; project GBFS/IW selected states directly and reconstruct successor states only by deterministic PDDL action application; retain Graphplan layer/mutex/extraction events as nonvisual and render only explicitly labeled extracted-plan replay states.
- Enforce strict render/cache/image contracts, complete production coverage, bounded-smoke identification, release verification, staged canaries, tests, and Phase 3 documentation.
### Must NOT have (guardrails, anti-slop, scope boundaries)
- Do not silently alias legacy `bfs` to active `gbfs`, use stale `data/phase3_supervised_planning` as this source snapshot, or mutate the four output roots.
- Do not fabricate concrete world states for raw Graphplan layers, malformed traces, failed attempts, missing parents, or unreconstructible successors.
- Do not treat `--render-limit` output as production-complete, a PNG signature as a valid image, cache file presence as a valid hit, or absolute historical profile paths as runtime input.
- Do not change planner search behavior or use unaligned historical Planimation frames as supervision.

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: TDD with `pytest`; write each focused failing test before its production change.
- Evidence: `.omo/evidence/planimation-hybrid-traversal-rendering/task-<N>.{txt,json,png}`.
- Happy: valid FF/GBFS/IW events emit a provenance-complete traversal row, derived PDDL equal to the event state, decodable frame, and strict VLM record.
- Edge: revisited states share a verified state asset but retain unique graph event IDs; zero-action solved examples yield one initial/terminal full record and zero action records.
- Adjacent regression: Graphplan layer events never obtain a concrete `frame_path`; only `state_source=extracted_plan_replay` events do.
- Failure: malformed traces, stale cache metadata, incomplete coverage, corrupt images, or a bounded-smoke root supplied to release mode exit nonzero with controlled errors.

## Execution strategy
### Parallel execution waves
> Target 5-8 todos per wave. Fewer than 3 (except the final) means you under-split.

- Wave 1: source snapshot/provenance, trace contracts, and render/cache contracts (Todos 1-3).
- Wave 2: planner traversal extraction (Todos 4-5).
- Wave 3: state rendering and hybrid record emission (Todos 6-7).
- Wave 4: release verification, staged canaries, and documentation (Todos 8-10).

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| 1 | None | 2-10 | 2, 3 |
| 2 | 1 | 4-10 | 3 |
| 3 | 1 | 6-10 | 2 |
| 4 | 2 | 6-10 | 5 |
| 5 | 2 | 6-10 | 4 |
| 6 | 3-5 | 7-10 | None |
| 7 | 6 | 8-10 | None |
| 8 | 7 | 9-10 | 9 |
| 9 | 7-8 | 10 | None |
| 10 | 8-9 | Final verification | None |

## Todos
> Implementation + Test = ONE todo. Never separate.
<!-- APPEND TASK BATCHES BELOW THIS LINE WITH edit/apply_patch - never rewrite the headers above. -->
- [x] 1. Freeze the four-root output snapshot and adopt JSONL row provenance.
  What to do / Must NOT do: Build an immutable selection manifest containing root ID, relative JSONL path, line index, `example_id`, record hash, root/split hashes, and planner ID. Reload source rows by that identity and reject hash/identity drift. Do not mutate source roots or depend on undeclared `traces/**` files.
  Parallelization: Wave 1 | Blocked by: None | Blocks: 2-10.
  References: `scripts/phase3/planimation_pairing.py` (`build_pairing_manifest`, `_pair_record`, `_load_source_example`); `scripts/phase3/io_utils.py`; all four non-deprecated roots in `outputs/`; `tests/phase3/test_planimation_pairing.py`.
  Acceptance criteria: focused tests freeze/reload a row and reject altered content, unknown planner, and hash mismatch; `pytest tests/phase3/test_planimation_pairing.py -q` passes.
  QA scenarios: happy `python scripts/phase3/generate_planimation_vlm.py --dataset-root <fixture-root> --manifest-only --output-root tmp/phase3_traversal_manifest_smoke`; failure alters fixture source after freeze and receives controlled `source_snapshot_mismatch`; evidence task-1 manifest/error JSON.
  Commit: Y | `feat(phase3): freeze planimation traversal sources`

- [x] 2. Define strict, versioned planner-trace and traversal-event contracts.
  What to do / Must NOT do: Add a trace-contract version and adapters for all four active planners. Define strict event fields: identity, supervision mode, planner, event kind/index, node/parent IDs, action, state source/hash when concrete, and planner metadata. Reject malformed or unsupported versions instead of falling back to plan-level reasoning.
  Parallelization: Wave 1 | Blocked by: 1 | Blocks: 4-10.
  References: `scripts/phase3/{gbfs,local_planners,local_iw,local_graphplan}.py`; `scripts/phase3/planimation_pairing.py` (`compact_reasoning`); `scripts/phase3/schema.py`; relevant Phase 3 planner tests.
  Acceptance criteria: each planner has valid and malformed fixtures; valid traces project only documented events and malformed/legacy traces receive controlled exclusions.
  QA scenarios: strict-schema validation of one valid trace per planner; remove a required state/action/layer field and assert rejection; evidence task-2 projection reports.
  Commit: Y | `feat(phase3): add traversal trace contracts`

- [x] 3. Harden profile resolution, state cache identity, image verification, and raster archive extraction.
  What to do / Must NOT do: Resolve profiles from repo-managed configuration and persist relative path/hash. Content-address cache key by domain/problem/profile/state/renderer/config/schema hashes; validate `result.json`, derived PDDL, VFG, PNG digest/dimensions, and semantic QA before reuse. Replace unbounded ZIP extraction with member-by-member containment/resource validation. Do not rely on historical absolute paths, PNG signatures, or cache file existence.
  Parallelization: Wave 1 | Blocked by: 1 | Blocks: 6-10.
  References: `scripts/phase3/planimation_pairing.py` (`_render_one_state`, `_profile_path`, `_valid_png`); `src/data_collect/rendering.py` (`PlanimationRenderer.render`, `_extract_png_archive`); `tests/data_collect/test_rendering.py`.
  Acceptance criteria: relocation, changed profile/config, stale cache metadata, corrupt PNG, and malicious `../../outside.png` ZIP fixtures fail; a valid hit hydrates the new-render contract.
  QA scenarios: render identical state twice and verify a fully validated cache hit; alter cache input or inject malicious archive and assert rerender/rejection with no escaped write; evidence task-3 hashes.
  Commit: Y | `fix(phase3): harden planimation render cache`

- [x] 4. Extract FF, GBFS, and IW concrete traversal states and reconstruct eligible successors.
  What to do / Must NOT do: Project FF selected/successor states directly; project GBFS/IW selected states directly; derive a successor only by applying the normalized recorded action to a validated source state. Preserve separate events for expansion, generation, revisit, and backtrack semantics even if the state asset repeats. Do not fabricate state or parent linkage.
  Parallelization: Wave 2 | Blocked by: 2 | Blocks: 6-10.
  References: `scripts/phase3/{gbfs,local_planners,local_iw,pddl}.py`; `scripts/phase3/planimation_pairing.py`; nonzero-plan examples in frozen roots.
  Acceptance criteria: direct/reconstructed states equal the corresponding recorded or replayed atoms; repeated states share an asset but not event ID; inapplicable edge is excluded.
  QA scenarios: project nonzero-plan FF/GBFS/IW examples and inspect event/state hashes; inject inapplicable action and assert no frame job; evidence task-4 manifest.
  Commit: Y | `feat(phase3): project concrete search traversal states`

- [x] 5. Represent Graphplan traversal safely and only render extracted-plan states.
  What to do / Must NOT do: Emit nonvisual planning-graph layer, mutex, and extraction events. Render only replay states explicitly derived from Graphplan extraction and label them `state_source=extracted_plan_replay`. Do not represent action/proposition layers as concrete PDDL states.
  Parallelization: Wave 2 | Blocked by: 2 | Blocks: 6-10.
  References: `scripts/phase3/{local_graphplan,local_planners,planimation_pairing}.py`; Graphplan examples in frozen roots; `tests/phase3/test_planimation_pairing.py`.
  Acceptance criteria: graph-layer events have no `frame_path`; extracted replay events have validated frame candidates; a layer supplied as atoms fails schema validation.
  QA scenarios: generate Graphplan manifest and distinguish layer/extracted events; malformed layer-as-state input fails; evidence task-5 event JSON.
  Commit: Y | `feat(phase3): represent graphplan traversal safely`

- [x] 6. Render validated plan-replay and traversal state sets with explicit cardinality and visual-semantic gates.
  What to do / Must NOT do: Render `N` pre-action plan frames for `N` actions and one additional terminal state only for traversal diagnostics; zero-action solved examples render one initial/terminal full frame and zero next-action rows. Require PNG decode, VFG numeric/in-canvas/noncoincident required sprites, and pixel expected-object coverage against domain golden canaries. Do not use a nonzero step as the full-record initial image.
  Parallelization: Wave 3 | Blocked by: 3-5 | Blocks: 7-10.
  References: `scripts/phase3/planimation_pairing.py` (`render_replay_states`, `_render_one_state`, `build_vlm_records`); `src/data_collect/rendering.py`; `scripts/planimation_phase1.py`; pairing tests.
  Acceptance criteria: one-action, repeated-state, zero-action, step-zero-failure, and invalid-sprite fixtures have exact render/full/step counts and expected controlled errors.
  QA scenarios: render state zero and a changed state for each concrete-state planner/domain; corrupt PNG or overlap/boolean sprite coordinates and assert `semantic_image_invalid`; evidence task-6 images and hashes.
  Commit: Y | `feat(phase3): render validated traversal frames`

- [x] 7. Emit strict hybrid full/step records and distinguish bounded smoke from production completion.
  What to do / Must NOT do: Emit per-split records with `supervision_mode`, event/state/trace/render provenance, relative paths, and strict nested schemas. Require contiguous step-zero coverage for production plan records. Mark bounded outputs `partial=true` with selected IDs and forbid `--render-limit` in production. Do not let partial artifacts resemble production data.
  Parallelization: Wave 3 | Blocked by: 6 | Blocks: 8-10.
  References: `scripts/phase3/{generate_planimation_vlm,planimation_pairing,io_utils}.py`; output naming conventions under `outputs/`.
  Acceptance criteria: schemas reject missing target/provenance; production rejects render limits; bounded smoke writes a partial manifest; missing step zero yields zero full records.
  QA scenarios: production fixture emits all splits/reconciled counts; `--render-limit 1` fails production and succeeds bounded smoke with partial manifest; evidence task-7 summaries.
  Commit: Y | `feat(phase3): emit hybrid planimation supervision`

- [x] 8. Add manifest/render/release verifier modes with complete output validation.
  What to do / Must NOT do: Release mode requires every manifest/schema/split, source snapshot equality, unique IDs, strict record validation, expected coverage, valid hashes/files/images, split isolation, and production-complete mode. Do not count absent JSONL as empty valid data.
  Parallelization: Wave 4 | Blocked by: 7 | Blocks: 9-10.
  References: `scripts/phase3/{verify_planimation_vlm,planimation_pairing,io_utils}.py`; existing Planimation audit/smoke outputs; pairing tests.
  Acceptance criteria: empty/missing/malformed/duplicate/partial/stale/invalid-image roots exit nonzero in release mode; a complete fixture exits zero with reconciled counts.
  QA scenarios: `python scripts/phase3/verify_planimation_vlm.py --output-root <fixture> --mode release`; assert exact exit status/error codes; evidence task-8 verifier JSON.
  Commit: Y | `fix(phase3): enforce planimation release gates`

- [x] 9. Execute deterministic fixtures, stratified canaries, and promotion gates before full rendering.
  What to do / Must NOT do: Run fixtures, then 5-10 changed transitions per domain, then a 250-500 transition stratified pilot covering every nonempty domain-planner-split cell, then one complete domain, and only then the frozen full selection. Freeze each run’s inputs/config/counts/QA receipts. Do not reuse smoke caches or promote canaries.
  Parallelization: Wave 4 | Blocked by: 7-8 | Blocks: 10.
  References: generator/verifier scripts; four source roots; `doc/detailed_implementation_summary/phase1_planimation_all_domains_validation_summary.md`.
  Acceptance criteria: every stage has zero provenance, coverage, and semantic-image failures; a failing domain blocks promotion.
  QA scenarios: fresh-root generator plus release verifier at each stage; retain canary image metrics/contact sheet; evidence task-9 reports.
  Commit: N | generated artifacts remain uncommitted unless explicitly requested

- [x] 10. Document the hybrid format, commands, limitations, and final release evidence.
  What to do / Must NOT do: Write dated Phase 3 implementation documentation and project knowledge with exact commands, hybrid semantics, Graphplan boundary, snapshot identity, and canary receipts. Do not claim completion before final release/image gates pass.
  Parallelization: Wave 4 | Blocked by: 8-9 | Blocks: Final verification.
  References: Phase 3 implementation summaries; `.omo/knowledges/phase3-output-dataset-audit-2026-07-09.md`; Todo 9 reports.
  Acceptance criteria: every documented fixture command exits zero and every evidence path exists.
  QA scenarios: execute documented fixture verification commands verbatim; missing evidence blocks completion; evidence task-10 command log.
  Commit: Y | `docs(phase3): document hybrid traversal rendering`

## Final verification wave
> Runs in parallel after ALL todos. ALL must APPROVE. Surface results and wait for the user's explicit okay before declaring complete.
- [x] F1. Plan compliance audit: verify every required source snapshot, adapter, mode, schema, cache, visual gate, rollout stage, and documentation receipt in this plan has evidence; fail on omitted Must-have or added Must-NOT-Have behavior.
- [x] F2. Code quality review: inspect all changed Phase 3/rendering files and focused tests for strict type/schema contracts, controlled failure paths, no silent legacy aliases, no `as any`/suppression equivalents, and safe archive handling.
- [x] F3. Real manual QA: run the fixture and fresh-root CLI workflows, decode sampled images, verify derived PDDL/state/image provenance, and inspect canary visual-semantic metrics for every supported domain/planner class.
- [x] F4. Scope fidelity: verify source roots were not mutated, original planner behavior did not change, Graphplan layers stayed nonvisual, and generated outputs were not committed without explicit user authorization.

## Commit strategy

- Commit 1: source snapshot/provenance and trace contracts (Todos 1-2).
- Commit 2: profile/cache/archive/image hardening (Todo 3).
- Commit 3: concrete adapters and safe Graphplan events (Todos 4-5).
- Commit 4: rendering, hybrid record emission, and release verifier (Todos 6-8).
- Commit 5: final Phase 3 documentation (Todo 10). Do not commit generated corpus outputs unless explicitly requested.

## Success criteria

- Every emitted record resolves to a frozen JSONL source row; no runtime path depends on undeclared standalone traces or workstation-specific absolute profiles.
- GBFS, FF, IW, and Graphplan each have validated traversal contracts; only concrete, provenance-valid states receive Planimation frames.
- `plan_replay` and `search_traversal` are unambiguous, while repeated concrete states safely share assets without collapsing graph-event semantics.
- Release mode rejects absent, stale, partial, malformed, unreadable, semantically invalid, split-leaking, or cardinality-mismatched artifacts.
- A fixture suite, per-domain canary, stratified pilot, and one-domain production run pass before corpus-scale rendering is allowed.
