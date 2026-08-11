# Notes: Phase 3 Pilot Rendering and Replay Alignment

## Repository Baseline
- Required and observed HEAD: `bf512c72ff8659158c8afa8887e6a6ee5ff9ca36`.
- Branch: `main`.
- Working tree contains pre-existing untracked `.claude/logs/`, `.omo/`, `phase3_pilot_materialization_closeout.md`, `task_plan.md`, and `notes.md` paths; unrelated content must remain untouched.

## Evidence Audit
- The required evidence is internally consistent on source rows, request size/digest, zero covered required states, owner action-policy status, and immutable roots.
- Existing coverage also reports two historical render-collision states, but neither overlaps the 16,822 required states; this does not contradict zero pilot coverage.
- Gate 0b focused tests passed 95; its broad evidence records 460 passed and 9 pre-existing failures. Regeneration and replay command strings are identical even though logs record `read_only` false/true respectively; retain this as an evidence limitation.
- No newer owner-approved artifact selects one authoritative off-plan action target.

## Renderer and Cache Audit
- No existing renderer CLI consumes `missing-render-request.jsonl`.
- The reusable low-level renderer is `render_state_with_planimation()` in `scripts/phase3/planimation_pairing_rendering.py`.
- Historical `_render_one_state()` uses a pair-driven cache and a list-order-sensitive/truncated state hash, so a CGAS adapter must bind the full canonical CGAS state digest independently.
- Historical render manifests are pairing/VLM records and cannot safely represent direct CGAS BFS records without a new contract.
- Existing resumability comes from validated per-state cache hits, not an append-only request checkpoint.

## Binding Validation
- `pilot-expansion-index.jsonl`: 31,171 lines; SHA-256 `46d1e7c1c0a6a133372782e691888840a74f3d3732dd625b5e2d8611fdf5d390`.
- `missing-render-request.jsonl`: 16,822 lines; SHA-256 `13db7cba5fb1cf885bd203ff657e5c7714bda6f832c5970dbfe5a9dee36d0585`.
- Materialization report: 790 replay-plan rows and 30,381 off-plan-only rows.
- Immutable-input checksum verification passed for both v2/v3 checkpoint/current files, approved trace v3, and pilot-scope report.

## Rendering Progress
- Requested: 16,822.
- Processed: 0.
- Succeeded: 0.
- Failed: 0.
- Duplicate: 0.
- Collision: 0 in the unstarted production adapter run.
- Coverage audit: 2 historical render collisions; neither belongs to the required request.
- Remaining: 16,822.
- The explicitly authorized one-state smoke transmitted the 1,002-byte Blocksworld domain, one derived 8-object/449-byte problem, and the 9,368-byte Blocksworld animation profile to the canonical `https://planimation.planning.domains/upload/pddl` endpoint. No credentials, traces, manifests, models, or secrets were sent.
- Smoke result: requested=1, processed=1, succeeded=0, failed=1, duplicate=0, collision=0, remaining=1. The endpoint returned `API error: The process ends with an exception / Unexpected status from the server`; no VFG or PNG was produced.
- The saved failed-smoke run contract predates final implementation-digest and canonical-endpoint hardening. It is evidence of the remote failure only and must not be resumed. A new authorized operator must use the exact production command in `.claude/evidence/cgas-phase3-pilot-rendering/operator-command.md`.
- The repository has a verified local VFG-to-PNG renderer, but no local PDDL/state/profile-to-VFG producer. Fast Downward is a symbolic planner and does not fill that gap.

## Canonical VFG Root Cause
- Authoritative Planimation backend source confirms `/upload/pddl` is valid: `pddl` is the route's arbitrary `filename` path parameter. The handler requires multipart fields `domain`, `problem`, and `animation`; it does not inspect multipart filenames or per-part MIME types.
- The official `planimation/api-tools` client uses the same `(None, content)` multipart shape as `scripts/planimation_phase1_client.py`. The local client is contract-correct; changing filenames, MIME types, or field names would be speculative and is not justified.
- The backend wraps its planner stage as `The process ends with an exception`. Its planner client raises the exact inner `Unexpected status from the server` when the downstream solver returns a status other than `ok` or `PENDING`. This localizes the supported boundary to a downstream non-success/non-pending response before VFG generation, but does not distinguish service availability from solver-side domain/problem compatibility.
- The exact derived smoke problem is valid STRIPS locally: 8 objects, 12 initial atoms, 5 nonempty goal atoms, no unsupported features, 144 grounded actions, and a four-step GBFS solution. The domain/profile predicate vocabulary matches (`on`, `on-table`, `holding`); the animation name `blocksworld` versus domain name `blocksworld-4ops` is an unproven compatibility concern, not the reported planner-stage failure.
- No client defect was proven, so no production transport code or testing-only HTTP fixture was added. No further external request was made. Source-backed details are in `.claude/evidence/cgas-phase3-pilot-rendering/canonical-vfg-root-cause-20260810.md`.
- Independent review found a separate pre-network provenance defect: 5,339 state digests have duplicate expansion-index rows; 4,293 span distinct candidates, 4,282 produce distinct candidate goals, and one state has 52 source rows. The frozen request contains only state atoms/digest/partitions and binds no canonical source candidate. The adapter previously selected the first index row by file order.
- RED/GREEN correction: the adapter now compares `candidate_id`, `object_count`, `raw_rank`, and `source_record_sha256` for repeated same-state rows and raises `request_state_source_ambiguous` before renderer/network use when they differ. Frozen request/index bytes and cardinalities are unchanged. This intentionally means the current 16,822-state production command will fast-fail until an owner-approved representative mapping or goal-independent VFG producer exists.
- An adapter CLI preflight was not run because the runtime denied the command as potentially transmitting repository-derived data to the configured external endpoint. The focused unit test proves the new failure precedes renderer invocation (`calls == []`); no attempt was made to bypass the denial.

## Representative Mapping
- Owner approval on 2026-08-10 selected policy `replay_then_held_out_then_stable_source_v1`: replay-plan rows first, then held-out calibration, then lower raw rank, candidate ID, BFS before IW, event sequence, and row ID.
- The local generator and adapter binding preserve frozen request/index bytes and make one source explicit per requested state; they do not infer action targets or claim to remove goal ambiguity.
- Materialized mapping: 16,822 rows, SHA-256 `3d6ff222e3662319d9429e18e3bd0d33a7ea1aee67a07e6d9b1a25c506ad7de3`.
- Report SHA-256: `bf20b3da0baf66bae787b7fff7760cae764571a96e8e1b6d2c6bd85c7533b1da`.
- Report counts: 5,339 duplicate groups, 4,293 multi-candidate groups, 4,282 distinct-goal ambiguity groups, 321 cross-role groups, 108 replay-containing duplicate groups, maximum group size 52, and 325 selections differing from the first physical index row.
- Representative distribution: 16,815 BFS and 7 IW; 4,844 held-out calibration and 11,978 train.
- Publication was rerun against the same output root and accepted byte-identically. No network call occurred.
- Mapping milestone committed `f9a5081` and pushed to `origin/main` on 2026-08-11 after 40 focused / 198 regression passes, clean Ruff/basedpyright, and independent review PASS.

## Mapping-Bound Smoke (2026-08-11, Red)
- Owner authorized exactly one fresh mapping-bound smoke on 2026-08-11. It ran against the canonical endpoint with one attempt, zero delay, and a new output root `outputs/image_frames/cgas-phase3-pilot-planimation-adapter-smoke-v2`; the pre-hardening `...-v1-smoke` directory was not resumed.
- Subset: 1 requested state `00014e0bdf...`, 2-row index, 1-row mapping. Mapping SHA `e7703cb4faf05b69496dd244b545ee7171ab37f5abc419dad3d4af30059bb4bd` pinned via `--expected-mapping-sha256`. Mapping-selected representative: `cgas-pilot-expansion-20b7ac18577176c1fa927b68` (candidate `0322c69e...`, 8 objects, raw_rank 93, bfs, train) — the same row the frozen 16,822-row production mapping selects for this state under `replay_then_held_out_then_stable_source_v1`.
- Client-side binding validated end to end: mapping pin matched, `source_record_sha256 37d284f8...`, run contract `880a79c99f35505385d63aaab1c8743de2384cae6415ee2168801020ad25b40b`, renderer config `ad0ca46c...`, domain `2eed94c5...`, profile `9ded071f...`. The derived `problem.pddl` persisted in the state cache and `candidate_problems/`.
- Remote result: requested 1, processed 1, succeeded 0, failed 1, remaining 1. Single recorded attempt returned the byte-identical 2026-08-10 error: `Failed to submit PDDL bundle. Attempts: https://planimation.planning.domains/upload/pddl -> API error: The process ends with an exception \n\n Unexpected status from the server`. No VFG or PNG returned.
- This confirms the mapping milestone did not change the remote boundary: the failure remains localized to the hosted Planimation backend's downstream planner path per `canonical-vfg-root-cause-20260810.md`.
- No production render (Phase 7) was started and no replay alignment (Phase 8) was generated. No fallback was attempted and no further external request is authorized. Evidence: `.claude/evidence/cgas-phase3-pilot-rendering/verification-20260811.md`.


## Replay Alignment
- Adapter implemented and unit-tested with frozen defaults (790 authoritative rows and the frozen index digest), artifact containment, digest revalidation, and semantic revalidation. The real 790-row output was deliberately not generated because replay render prerequisites are incomplete.

## Verification
- Focused adapter/alignment suite: 23 passed.
- Relevant rendering, coverage, expansion-index, and replay regression suite: 143 passed.
- Ruff passes for all four changed Python files; basedpyright reports 0 errors, 0 warnings, 0 notes; `git diff --check` passes.
- Frozen index/request cardinalities and SHA-256 digests match 31,171/`46d1e7c1...d390` and 16,822/`13db7cba...0585`. The read-only coverage rerun regenerated the identical 16,822-row request digest with covered=0 and missing=16,822.
- All six immutable input checks pass.
- Independent code review passes after fixes for output-root/symlink containment, replay artifact containment, frozen replay defaults, production resume arguments, renderer implementation drift, and dynamic Planimation facade/client/frame-renderer drift. Accepted debt: `cgas_pilot_planimation_adapter.py` remains 552 pure LOC and should be split by responsibility before further feature growth.
- Secret Guard reports no secrets in the 12 explicitly staged milestone files.
- Final retry verification after the provenance correction: 156 relevant tests passed, scoped Ruff passed, scoped basedpyright reported 0 errors/warnings/notes, frozen coverage remained 0/16,822 with the identical request digest, all six immutable inputs passed, both staged/unstaged diff checks passed, staged Secret Guard found no secrets across 13 explicit milestone files, and the fresh independent re-review returned PASS.
- Broader Ruff/basedpyright probes that added unchanged legacy `scripts/planimation_phase1_client.py` and `tests/test_planimation_phase1.py` exposed pre-existing import/type diagnostics outside this milestone; scoped milestone checks remain green, and `git diff` confirms those legacy files were not modified.
- Final mapping verification: 29 focused tests and 151 relevant Phase 3 tests passed; Ruff and basedpyright are clean; six immutable inputs and both diff checks pass; final independent re-review returned PASS with no CRITICAL or HIGH blocker.
- No commit or push has occurred.
