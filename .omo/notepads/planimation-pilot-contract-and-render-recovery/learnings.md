## 2026-07-25 Work initialization
- The approved contract is `context_status="extraction_bound"` with exact extraction step/action equality; action-layer metadata is optional enrichment only.
- The frozen selection contains 52 unique pair IDs and binds source root SHA `a8c1fe317f5f3909aea4af28c519aa4af9c4eefb406667c644b46cd15aba3214`.
- Preserve the existing pilot cache and keep semantic validation strict.

## 2026-07-25 Read-only baseline evidence
- Existing focused Graphplan/traversal baseline passed: 60 tests.
- Existing semantic validator baseline passed: 10 tests.
- Retained failures remain correctly classified: Gripper `sprite_degenerate_bounds`; Ferry, Elevators, and Logistics `coincident_sprite_bounds`.

## 2026-07-25 Todo 1 Graphplan extraction binding
- Graphplan reasoning now binds only to `extracted_plan_replay` transitions with a nonempty extraction event ID, an in-range non-Boolean integer step, and exact normalized equality to `extraction.selected_plan[step_index]`.
- Action layers are optional enrichment after binding: matching normalized actions produce numeric-layer-sorted metadata; absent matches do not invalidate a valid extraction action.
- The five retained action-layer-mismatched cases now report `extraction_bound` at a 256-character requested budget. Their truthful mandatory payloads are 267-268 characters, so mandatory provenance is intentionally returned intact rather than truncated or rejected.
- Focused pairing/traversal suites passed twice with 69 tests each; forged source, extraction-event, boolean-step, and action mismatch cases retain `trace_event_not_bound_to_replay_transition`.

## 2026-07-25 Todo 2 profile contracts
- The normalized structural profile regressions failed red exactly once per profile, then the focused profile-plus-semantic suite passed twice: 14 tests each run.
- Gripper is now 30x60; Ferry car is 100x70 while location remains 150x150; Elevators `served` no longer redistributes passenger x; Logistics uses `%p`, `%t`, `%a`, `%l`, and `%c` selectors.
- Retained old artifacts remain fail-closed under the unchanged semantic gate: Gripper is `sprite_degenerate_bounds`; Ferry, Elevators, and Logistics are `coincident_sprite_bounds`.
- `render_semantics.py` retained SHA-256 `89738283d69ea51e2885eff3f421528d3940d05e7848b61595d1816528b3a8ae`.
- A failed post-edit byte check found one terminal newline appended after the entire `(:image` section in Gripper, Ferry, and Logistics. The upstream profile bytes matched the pre-edit receipts and retained VFG image tables confirmed every base64 payload; removing only those three newline bytes restored exact parity.
- The profile regression suite now locks the SHA-256 of every byte after the first `(:image` marker independently of the approved pre-image contracts. The recovered profile-plus-semantic suite passed twice with 18 tests per run.

## 2026-07-25 Todo 3 launcher resume contract
- Fresh existing-root refusal was characterized before launcher edits: `PILOT_OUTPUT_ROOT=.git` exits 1 before activation.
- Red tests proved current gaps for invalid arguments, missing resume root/selection, pilot-root active-writer detection, and selection-bound verifier invocation.
- The focused launcher suite passed twice after the minimal change: 8 passed in 1.72s, then 8 passed in 2.06s; every shell subprocess is bounded to five seconds.
- Bounded direct QA retained fresh refusal for `.git` and rejected a nonexistent `--resume` root, both with exit 1 before activation.
- `bash -n` passed and direct basedpyright reported 0 errors, 0 warnings, 0 notes. The workspace basedpyright LSP client was alive, but its diagnostics calls timed out without returning a result.
- No successful resume, generator, verifier, remote render, output/cache mutation, commit, or git operation occurred. Evidence: `.omo/evidence/planimation-pilot-contract-and-render-recovery/task-3-launcher.txt`.

## 2026-07-25 Todo 4 frozen pilot verification
- The frozen selection's `input_pairing_manifest_sha256` identifies the full source pairing manifest (`de298...`), not the pilot subset manifest (`6f78...`); release verification must not compare those two different artifacts.
- Selection parsing is now a frozen typed contract for the selected IDs and per-pair split, source root/path/line, source record/root/split hashes, plan hash, planner, domain, and bucket. Exact output pair-set equality and every selected-pair provenance field remain fail-closed.
- `_validate_manifest()` now passes its existing source snapshot and source-row caches to `_load_source_example()`, eliminating repeated full JSONL decoding without weakening source validation. The exact selection-bound 52-pair manifest CLI completed successfully in 46.576 seconds.
- The focused verifier suite passed serially twice after isolated test-root cleanup: 11 passed in 14.39s, then 11 passed in 15.36s. Evidence: `.omo/evidence/planimation-pilot-contract-and-render-recovery/task-4-{pytest,hashes,selection-contract,manifest-cli}.*`.

## 2026-07-25 Todo 4 independent-review remediation
- Independent review found four immutable fields already present in both frozen `selected_pairs` and pilot pairing records but omitted from selection comparison: `source_root_id`, `example_id`, `active_planner_id`, and `instance_id`.
- Parameterized red probes mutated each field and initially observed CLI exit 0. The typed frozen selection now parses these fields when present and emits deterministic `selection provenance mismatch: <pair_id>:<field>` failures for every mutation; absent optional fields remain compatible with generic selection fixtures.
- The corrected focused suite passed twice with 16 tests (13.98s, 13.82s). The real frozen selection-bound manifest verifier still exits 0 with 52 pairs in 42.705s; no full-source/pilot-subset manifest hash comparison was restored. Evidence: `.omo/evidence/planimation-pilot-contract-and-render-recovery/task-4-review-remediation.txt`.

## 2026-07-25 Todo 5 resumed verification
- After the independently approved Ferry remediation, the exact six-module focused suite passed with 112 tests; direct basedpyright, compileall, shell syntax, diff, and all seven scoped LSP diagnostics were clean.
- The existing fresh Gripper canary still validates at 13/13 coverage. The independently approved Ferry canary validates at 6/6 coverage with the unchanged validator; its raw artifacts were copied without alteration into the Todo 5 evidence bundle.
- The next exact retained Elevators state reached Planimation successfully in one bounded remote attempt but still failed strict VFG validation as `coincident_sprite_bounds`; the required stop fence left Logistics unrendered.

## 2026-07-25 Elevators collision diagnosis
- The failed stage-zero VFG has exactly one coincident pair: `p0` (`img-emotionless`) and served `p1` (`img-happy`) both occupy `(0.059, 0.118, 0.476, 0.535)` with `x=0`, `y=142`; floors and lift have distinct bounds.
- The retained state has `(origin p0 f2)`, `(origin p1 f0)`, `(destin p1 f2)`, `(lift-at f2)`, and `(served p1)`. Per-floor `origin` distribution assigns each lone passenger `x=0`; `served` correctly preserves x while moving `p1` to its destination floor, causing the collision with `p0`.
- The unchanged validator still returns `semantic_image_invalid: coincident_sprite_bounds` for the preserved failed VFG/PNG before image coverage evaluation. The next repair must assign stable global origin lanes without reintroducing served-time x redistribution.

## 2026-07-25 Elevators collision remediation
- Replacing only the `origin` x-assignment with `distributex (objects ?p)` retains served-time x stability and assigns `p1` a different lane from `p0` on the retained state.
- The failing-first regression `test_elevators_served_passengers_use_distinct_global_origin_lanes` preserved the actual failed `p0`/`p1` VFG duplicate and fail-closed receipt, then failed against the former floor-local profile rule and passed after the one-expression repair.
- The fresh retained-problem canary completed on remote attempt 1 with `status=success`, `reason=validated_expected_object_coverage`, and `7/7` covered sprites. It has distinct passenger x bounds (`p0=[0.059, 0.118]`, `p1=[0.176, 0.235]`) and no coincident stage-zero bounds. Evidence: `.omo/evidence/planimation-pilot-contract-and-render-recovery/task-5-planimation-pilot-contract-and-render-recovery/elevators-repaired-global-lanes-attempt/`.

## 2026-07-25 Todo 5 final Logistics canary
- The exact retained Logistics state was rendered once with the current `%p/%t/%a/%l/%c` profile selectors. The fresh artifact passed unchanged semantic validation at 11/11 coverage on one bounded remote attempt.
- Stage zero contains plane `a0`, cities `c0/c1`, trucks `t0/t1`, locations `l0-0/l0-1/l1-0/l1-1`, and packages `p0/p1`; there are no duplicate, degenerate, or out-of-canvas bounds. Direct visual review found low-canvas placement, not clipping or unintended overlap.
- The final six-module focused suite passed with 113 tests; direct basedpyright, compileall, shell syntax, and diff checks passed. The LSP client remained alive but its seven fresh diagnostics requests timed out at the harness's 3-second deadline.

## 2026-07-25T12:01:19Z Todo 6 interrupted first-resume evidence
- The exact required first resume reached the generator's `state_render_started` receipt but the execution surface terminated its owning shell after 120 seconds before launcher exit. There was no live `generate_planimation_vlm` process afterward and no launcher exit-code receipt, so no retry or second resume was attempted.
- The full cache-path inventory and per-domain cache-key counts were unchanged across the interrupted attempt: Blocksworld 16, Elevators 82, Ferry 19, Gripper 458, Logistics 3, and Towers of Hanoi 181. Frozen selection, source JSONLs, and semantic-validator hashes were also unchanged.
- Evidence is under `.omo/evidence/planimation-pilot-contract-and-render-recovery/task-6-planimation-pilot-contract-and-render-recovery/`, including `resume-first.log`, inventories, before/after hashes, `post-timeout-status.json`, and `done-claim.json`.

## 2026-07-25T12:14:49Z Todo 6 first semantic failure correction
- The persistent owned resume reached 200 processed states with 195 successes, 5 failures, and 148 cache hits before it was stopped at the first reported semantic failure. The original cache inventory remains a strict subset of the post-failure inventory: 0 pre-existing paths are missing and 249 new cache files were added under 62 new cache-key directories.
- The diagnosis is not a profile-byte mismatch: current SHA-256 values for Elevators, Ferry, Gripper, and Logistics exactly equal their approved successful-canary SHA-256 values.
- The concrete failure is Ferry `ferry-dev-easy-0000`, state hash `33b9c9648b4b132c94467949b8427b34`, recorded as `semantic_image_invalid: coincident_sprite_bounds` under cache keys `84b7d426976a5d2acb7e0ea89f056f69` and `beb1b18d1e76532e3f3e12beda158fad`. No source remediation or retry occurred in Todo 6.

## 2026-07-25 Ferry shared-location remediation
- The retained failure state places both `c0` and `c1` at `l2`. The current-profile trace from cache key `84b7d426976a5d2acb7e0ea89f056f69` gives both cars exact bounds `(0.679, 0.868, 0.038, 0.17)`; the older key has the same coordinate collision with historical 150x150 car geometry. This rules out cache-only and `on`-predicate explanations.
- The first corrective rule used Gripper's `distribute_within_objects_vertical` primitive in Ferry `at`, but its one permitted fresh canary showed `l2.y=false` and consequently `c0=c1=(false, false)`. The primitive was recognized, but Ferry locations lacked the concrete y-origin required by container distribution.
- The final local profile sets `(equal (?l y) 0)` in `location` and keeps `(assign (?c x y) (function distribute_within_objects_vertical (objects ?c ?l)(settings (spacebtw 20) (row_count 5))))` in `at`.
- The regression captures the recorded duplicate `c0`/`c1` stage-zero bounds, validates the unchanged fail-closed receipt, and asserts both the location anchor and per-location vertical distributor.
- Local verification passed twice: `pytest tests/phase3/test_planimation_profile_regressions.py tests/phase3/test_render_semantics.py -q` reported `21 passed` on both runs. `basedpyright tests/phase3/test_planimation_profile_regressions.py` reported 0 errors, 0 warnings, 0 notes; `python -m compileall -q scripts/phase3 tests/phase3` and `git diff --check` passed.
- Ferry's post-`(:image` suffix remains `871681463f96a3bd8af434bccbf54b2d7f8cbf0bf4cf14e6117fbfddcdaea355`. The patch engine adds a terminal newline to this untracked raw asset, so the verified recovery removes that one byte only after asserting the exact approved suffix hash.

## 2026-07-25 Ferry final y-anchor canary result
- [resolved] The explicitly authorized final canary for state `33b9c9648b4b132c94467949b8427b34` succeeded on its first actual attempt against `https://planimation.planning.domains`. Unchanged `validate_render_artifacts()` returned `success`, `validated_expected_object_coverage`, and `6/6` covered sprites for the `1024x1024` frame.
- The final profile SHA-256 was `9295ea8b1ed5f60a05a98fcd5c2eac6c7cccef156c4572d59e5668300d4351b4`; the immutable semantic-validator SHA-256 remained `89738283d69ea51e2885eff3f421528d3940d05e7848b61595d1816528b3a8ae`.
- Fresh VFG evidence records `c0` at `(345, 5)` with bounds `(0.689, 0.877, 0.047, 0.179)` and `c1` at `(345, 75)` with bounds `(0.689, 0.877, 0.179, 0.311)`. Both cars are in `l2`, vertically distinct, in canvas, and non-overlapping.
- The earlier successful control still validates at `6/6`; the retained pre-remediation failure still fails closed at `5/6`. The new review receipt is `ferry-shared-location-final-y-anchor-attempt/done-claim.json` in the scoped Task 5 evidence directory.

## 2026-07-25T19:15:16Z Todo 6 resumed recovery evidence
- The final Ferry profile SHA-256 `9295ea8b1ed5f60a05a98fcd5c2eac6c7cccef156c4572d59e5668300d4351b4` recovered the formerly failing state in the full pilot. The first persistent exact resume exited 0 with 2,568 semantic successes, zero failures, 2,058 cache hits, exact frozen 52-pair selection, all six domains represented, production-complete output, required split totals, and launcher manifest/render/release verification receipts.
- The second persistent exact resume also exited 0; all 2,568 state records are cache hits, no cache path was added or lost after first green, and all three launcher verifier modes passed. The isolated missing-root and missing-selection-pair probes each exited 1 while the post-probe generated diagnostic/report hashes remained unchanged.
- The strict first-green versus second-green byte-identity condition is not met: `state_render_manifest.jsonl` and `state_render_summary.json` have different SHA-256 values. The first summary records 2,058 cache hits and the second records 2,568. The first snapshot also omitted root VLM JSONL hashes, so their first-versus-second identity cannot be claimed.

## 2026-07-25T20:59:12Z Todo 6 third-resume interruption evidence
- The single third launcher invocation reached `state_render_finished` with 2,568 successes, zero failures, and 2,568 cache hits, but the host terminated the owning shell before the launcher verifier loop and before it wrote an exit-code receipt. No generator or launcher process remains.
- The complete canonical path set remains 15 paths; cache inventory remains 5,324 paths with zero additions/deletions; source, selection, launcher, and semantic-validator hashes are unchanged. Fourteen canonical hashes match the complete warm baseline.
- The only canonical mismatch is `diagnostics/hybrid_output_manifest.json`. It now has zero full/step/traversal VLM records and `production_complete=false`, so the interrupted state cannot certify stable warm-cache idempotence or production completeness.

## 2026-07-26T00:06:53Z Todo 6 authorized replacement proof
- [resolved] The single authorized detached replacement exact resume exited 0 after all 2,568 states completed as cache hits and semantic successes. Its log contains the required manifest, render, and release verifier receipts; release reported 52 full records, 331 step records, and 2,185 search-traversal records across the required splits.
- Complete second-green-versus-replacement comparison is byte-identical: all 15 canonical paths and hashes, all 5,324 cache-relative paths, and frozen source/selection/launcher/validator hashes match. No cache path was added or removed.
- The independent structured reconciliation establishes the frozen 52-pair set, six-domain state distribution, unchanged profile hashes, production-complete hybrid manifest, 2,568 successful semantic state rows, and zero remote rendering attempts. The latter follows from every state row being `cache_hit=true`, the replacement completion event reporting 2,568 cache hits, and no remote/endpoint/attempt marker in the replacement log.
- The earlier interrupted third run and first-green-versus-second-green mismatch remain historical evidence only; the passing stability claim is limited to the complete second-green warm baseline versus the authorized replacement run.

## 2026-07-26T06:11:38Z Todo 7 contract and promotion closure
- The rollout selection's `input_pairing_manifest_sha256` remains full-source provenance. Exact complete frozen selected-pair record multiset equality permits the output to be the selected subset without weakening rejection of missing, extra, mutated, or duplicate records.
- The clean cache-only chain approved a 1-state fixture with receipt `0df245b600361967bb5c1e24f0cdf8912956356337df329b99e1fec79d153941`, then a 39-state changed-canary across 18 cache directories with receipt `f82b4585eff12a14d38e2f018d77e49a5d14a5aba66701c6f9cf84eac06fdab9`.
- The actual pilot assessment approved 52 pairs and 2,568 successful cache-hit states with receipt `1bef38d5571cd3e8276f4d925e13553475914fe0e51f3d459ec83a16c25694e7`. All 5,343 original files and 5,324 cache paths remained unchanged; only the promotion receipt was added.
- The isolated mutation probe rejected `source_record_sha256` provenance drift. The full 2,328-pair, 537,696-state corpus remains incomplete.

## 2026-07-26T06:34:29Z Todo 7 final Oracle provenance hardening
- Exact selected-record subset equality is conditional on a valid `input_pairing_manifest_sha256`: exactly 64 lowercase hexadecimal characters. Missing, uppercase, wrong-length, and non-hexadecimal provenance rejects as `invalid_frozen_selection` before fallback.
- The negative regression recomputes `selection_sha256` after deleting or replacing provenance, isolating the provenance-format rejection from selection self-hash integrity.

## 2026-07-26T17:00:55+10:00 Todo 7 independent-review remediation
- Independent review rejected the evidence only because the operator command set was incomplete and the recovery summary mislabeled a receipt file-byte hash as a generic receipt hash.
- Independent `sha256sum` recorded fixture receipt file bytes as `d59677121f0b40b23df01b25e7802a7ccc1b30c3693ff5fbaf45b92ac92eed38`; `jq` recorded the distinct embedded `receipt_sha256` self-hash as `0df245b600361967bb5c1e24f0cdf8912956356337df329b99e1fec79d153941`.
- Both operator documents now contain the complete manifest, render, release, and promotion command lines. The required changed-canary prior receipt exists at `tmp/phase3_planimation_todo7_promotion_chain_20260726/recovery/changed-canary/diagnostics/rollout_promotion_receipt.json`.
- This remediation executed no pilot verifier, rollout assessment, generator, renderer, launcher, or Python command. Evidence checks used only `rg`, `jq`, `sha256sum`, `stat`, and read-only git commands.

## 2026-07-26T08:33:39Z F2 ignored-profile review remediation
- [resolved] The four PDDL profiles remain ignored by the exact rule `.gitignore:153:data/`; review no longer depends on staging them. Shared selection validators, exact ordered correspondence checks, and preserved `Counter` multiset semantics remain the selection boundary, while release validation reads and validates the source hash directly.
- [resolved] The launcher guard remains literal and process-aware through `/proc` argv inspection, so wrapper text isn't accepted as an operational launcher match. This evidence task didn't alter that guard or any runtime source.
- The whole-file SHA-256 values are Gripper `b549b24eb7f5fb699773d7c7f7e369488aa7826822faa049a351cb074918dbc4`, Ferry `9295ea8b1ed5f60a05a98fcd5c2eac6c7cccef156c4572d59e5668300d4351b4`, Elevators `ce32eb2e9edd007aeef9c93fada264202141b4e2b717752a0e5bd793ee9ef813`, and Logistics `c9aaa88d16da3c53a3fb4f2b01dfbf507aeda509a92635a877a02ee5bf293f79`. Their task-2 image-section hashes remain `9acbc33f9b0719cd4bb2e1f4e469a12d834e823719b180eab95165d0ca53216c`, `871681463f96a3bd8af434bccbf54b2d7f8cbf0bf4cf14e6117fbfddcdaea355`, `98eabfd7f6a20104385a146aee971c6331c00514a81254280fc7a1c1f8f39a19`, and `4d7044a096d5c3203214644fc3869e41c99cc1f417614cccc22f9e6873c29fb5` in the same order.
- Review evidence is `.omo/evidence/planimation-pilot-contract-and-render-recovery/f2-remediation/ignored-profile-contracts.json` at SHA-256 `deb1110b28b2af392a8d1303b6ab4225f43bdaf072b1c4f34ab3e47546de2fb2`, `ignored-profile-contracts.diff` at `eb6c6d06cbabc5a0ea3f6b422256122a30ccb253e3a6f71c10202164fae52f4f`, and `reproduce-profile-evidence.md` at `2eb58d1f14e37a84eff547c88ad20df0db743408b1947094daa8123bcc62a924`.
- Historical projection values come only from the repair entries in `task-2-profile-contracts.json`. The no-index projection excludes embedded image bytes, no real operational command or profile test ran, and no profile or evidence file was staged.
