# cgas-dataloader-and-experiment-support - Work Plan

## TL;DR (For humans)
<!-- Fill this LAST, after the detailed plan below is written, so it summarizes the REAL plan. -->
<!-- Plain English for a non-engineer: NO file paths, NO todo numbers, NO wave/agent/tool names. -->

**What you'll get:** A strict, versioned dataset path that turns verified Blocksworld BFS/IW transitions into Qwen-VL training examples with aligned images and typed certificate targets. Every emitted record will prove its source, transition, image alignment, and safe model-input boundary before the loader reads it.

**Why this approach:** The existing corpus has useful raw BFS traces, but no usable IW examples and no aligned visual supervision. Repairing those scientific contracts before implementing the loader protects the CGAS novelty claim and prevents a model from learning from mismatched images or leaked oracle state.

**What it will NOT do:** It will not train CGAS, implement live memory, finalize minimum-cost route labels, or create a broad attention-analysis project. It will not relabel GBFS as BFS, fabricate IW traces, or train on unaligned images.

**Effort:** Large
**Risk:** High - availability of canonical IW traces and replay-proven image alignment determine whether a multimodal P0 corpus can be emitted at all.
**Decisions to sanity-check:** P0 is Blocksworld-only; canonical FIFO BFS and width-1 IW remain separate; rows failing any gate produce no trainable output.

Your next move: execute in a separate worker session with `$start-work cgas-dataloader-and-experiment-support` after confirming the required pixi or conda Python environment. Full execution detail follows below.

---

> TL;DR (machine): Large/high-risk C1-C3 milestone: provenance-locked Blocksworld BFS/IW corpus, step-aligned render evidence, typed certificate/counterfactual primitives, and strict Qwen-VL conversion/preflight; no CGAS method training.

## Scope
### Must have
- A confirmed pixi or conda environment before Python changes or package-backed tests; record the selected environment in root `AGENTS.md` and update `pyrightconfig.json` as required by the project rule.
- A Blocksworld-only P0 readiness manifest with split isolation, source hashes, canonical planner identity/version, replay evidence, structural-OOD partition membership, and a hard zero-output gate.
- Separate canonical BFS and width-1 IW trace production with all fields needed for typed certificate verification.
- An image-to-transition alignment manifest that proves each selected PNG depicts `state_before` for one supervised transition.
- `planning_cgas_v1` step records with explicit model-input and target-only fields; BFS/IW certificate verifiers and one-invariant counterfactual primitives.
- Strict conversion and registration for the existing Qwen-VL `image`/`conversations` SFT path, plus row-level preflight that cannot substitute a later sample after an error.
### Must NOT have (guardrails, anti-slop, scope boundaries)
- Do not use `vision_available_unaligned` rows as VLA supervision, and do not accept alignment based only on frame count.
- Do not relabel GBFS as BFS, create synthetic/fake IW traces, or aggregate FF/Graphplan into P0.
- Do not include the gold action, gold certificate, route label, queue/novelty table, replay trace, final state, or evaluation metadata in human-turn text, controller inputs, or memory payloads.
- Do not finalize route labels, add bounded live memory, train a direct baseline, implement CGAS, or add attention-map analysis in this milestone.
- Do not reuse `examples/planning_benchmark_slice/train_files/data_registry/data_config.py` as a training adapter; it is a registry smoke surface with a no-op transform.

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: TDD with `pytest`; new verifiers/converters begin with a failing fixture test, then implementation, followed by deterministic CLI and loader-preflight checks.
- Environment prerequisite: the worker must obtain the user's pixi-or-conda environment confirmation before running Python code with third-party dependencies. The worker records the selected command prefix in `AGENTS.md` and `pyrightconfig.json`; no system Python installation is allowed.
- Evidence: `<attemptDir>/task-<N>-cgas-dataloader-and-experiment-support/` (where `attemptDir` is `.omo/evidence/` outside `ulw-loop`) contains pytest output, manifest JSON, rejected-row reports, and Qwen preflight summaries.
- Dataset acceptance rule: a record is emitted only if all provenance, split, replay, typed-certificate, counterfactual, no-oracle, and image-alignment checks pass. Any P0 planner/split gate failure returns nonzero and writes zero trainable rows.
- Strict loader preflight: first preflight every converted row through `_build_messages()` and `preprocess_qwen_visual()` with identity-preserving diagnostics, then run a real `LazySupervisedDataset`/collator batch. Assert one consumed image placeholder, non-null `pixel_values` and `image_grid_thw`, non-empty assistant labels, and emitted-row identity equality.

## Execution strategy
### Parallel execution waves
- Wave 0: environment confirmation and existing-contract characterization (Todo 1).
- Wave 1: P0 provenance/IW corpus gate and state-to-image alignment (Todos 2-3, independent after Todo 1).
- Wave 2: typed records/verifiers and Qwen conversion/preflight (Todos 4-6, ordered by the accepted-manifest dependency).
- Route labels, bounded memory, calibration, model heads, and CGAS baselines are intentionally separate follow-up plans after this milestone.

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| 1 | user confirms pixi/conda environment | 2-6 | none |
| 2 | 1 | 4-6 | 3 |
| 3 | 1 and accepted source transitions from 2 | 4-6 | none |
| 4 | 2-3 | 5-6 | none |
| 5 | 4 | 6 | none |
| 6 | 5 | milestone handoff | none |

## Todos
> Implementation + Test = ONE todo. Never separate.
<!-- APPEND TASK BATCHES BELOW THIS LINE WITH edit/apply_patch - never rewrite the headers above. -->
- [x] 1. Confirm the Python environment and characterize the existing Phase 3 and Qwen contracts before implementation.
  What to do / Must NOT do: Obtain explicit user confirmation of a pixi environment or conda environment/path before installing or importing third-party packages. Add the selected environment to root `AGENTS.md` and create/update root `pyrightconfig.json`. Record existing P0 facts in a machine-readable input-contract snapshot: current corpus counts, planner statuses, vision statuses, the active GBFS-only Phase 3 planner list, and the Qwen conversation/image contract. Do not alter datasets or install packages before confirmation; do not treat `.venv` as authorization.
  Parallelization: Wave 0 | Blocked by: user environment confirmation | Blocks: 2-6.
  References (executor has NO interview context - be exhaustive): root `AGENTS.md` project Python-environment rule; `pyproject.toml:1-56`; `data/phase3_supervised_planning/summary.json:1-39`; `scripts/phase3/pipeline.py:158-182,300-340,450-498`; `starVLA/dataloader/qwenvl_llavajson/qwen_data_config.py:5-55`; `starVLA/dataloader/vlm_datasets.py:142-201,246-305,348-378,538-604,681-715`; `.omo/drafts/cgas-dataloader-and-experiment-support.md`.
  Acceptance criteria (agent-executable): `pytest -q tests/phase3/test_phase3_pipeline.py tests/planning_benchmark/test_dataset_registry.py` passes in the confirmed environment; a new read-only readiness command writes `outputs/cgas_readiness/input_contract.json` with `current_bfs_examples=411`, `current_iw_examples=0`, `current_vision_alignment_rows=0`, and the active `gbfs,ff,iw,graphplan` planner list; its exit code is zero only for observation, not readiness approval.
  QA scenarios (name the exact tool + invocation): Happy - run `pytest -q tests/phase3/test_phase3_pipeline.py tests/planning_benchmark/test_dataset_registry.py` and the read-only readiness command; require all tests pass and the snapshot matches the corpus. Failure - run the readiness command against a copied summary with a missing required key; require nonzero exit and a field-specific error. Evidence `<attemptDir>/task-1-cgas-dataloader-and-experiment-support/{pytest.txt,input-contract.json,missing-key.txt}`.
  Commit: Y | `chore(cgas): record dataset and environment readiness contract`

- [x] 2. Build a strict Blocksworld P0 planner-provenance and trace-coverage gate for canonical FIFO BFS and width-1 IW.
  What to do / Must NOT do: Add a dedicated CGAS readiness module under `scripts/phase3/` and tests under `tests/phase3/`. Define P0 as Blocksworld-only; preserve train/dev/test instance IDs and predeclare the structural-OOD partition by held-out object count, horizon, and compositional arrangement. Require source command, planner implementation/version/hash, limits, action tie-break, trace-contract version, replay-validation ID, and source file digest for every row. Implement canonical FIFO BFS with a deque and sorted legal-action tie-break as a distinct algorithm from GBFS; source IW from the repository's local IW implementation with `width=1`, and require novelty-table before/after, novelty item, and width-decision fields. Reject an unresolved/GBFS-labelled BFS row and produce zero P0 output rather than relabelling it.
  Parallelization: Wave 1 | Blocked by: 1 | Blocks: 4-6 | Can parallelize with: 3 once it receives accepted source transitions.
  References (executor has NO interview context - be exhaustive): `doc/research_proposal.md:84-108,128-164`; `doc/high_level_plans/research_execution_plan.md:53-69,213-238`; `doc/detailed_implementation_summary/phase3_gbfs_replacement.md:7-18`; `scripts/phase3/pipeline.py:343-360,450-454`; `scripts/phase3/gbfs.py`; `scripts/phase3/local_iw.py`; `examples/planning_benchmark_slice/generate_experts.py`; `tests/planning_benchmark/test_experts_bfs_iw.py:33-89`; `tests/phase3/test_phase3_pipeline.py:132-158,250-253`; `data/phase3_supervised_planning/summary.json:10-39`.
  Acceptance criteria (agent-executable): a new P0 generator/readiness CLI emits `data/planning_cgas_v1/source/{train,dev,test}.jsonl` plus `manifest.json` only when both planners have at least one accepted row in every split, all rows replay successfully, every BFS row declares `algorithm=breadth_first_search` and FIFO/sorted-action metadata, every IW row declares `width=1` and all novelty fields, and structural-OOD IDs are disjoint from calibration/dev/test IDs. `python -m pytest -q tests/phase3/test_cgas_provenance.py tests/planning_benchmark/test_experts_bfs_iw.py` passes.
  QA scenarios (name the exact tool + invocation): Happy - run the new P0 CLI on the existing Blocksworld fixture corpus, then run its `--verify` mode; require nonzero BFS and IW counts in train/dev/test, zero replay/provenance/split errors, and no GBFS records. Failure - mutate a fixture manifest row from BFS provenance to GBFS or remove an IW novelty field; require `--verify` to exit nonzero, emit zero accepted output, and name the exact rejected record/reason. Evidence `<attemptDir>/task-2-cgas-dataloader-and-experiment-support/{pytest.txt,p0-manifest.json,verify.json,gbfs-rejection.txt,iw-rejection.txt}`.
  Commit: Y | `feat(cgas): gate canonical BFS and IW P0 traces`

- [x] 3. Produce replay-proven, pre-action image alignment records for every accepted P0 transition.
  What to do / Must NOT do: Extend the existing Planimation pairing/rendering flow rather than inferring alignment from `frame_count`. For transition `t`, emit an alignment record containing the source transition ID, `state_before` hash, action, frame path/hash, VFG action index, source trace/render digests, and mapping rationale. Require the initial-state render at `t=0`; for `t>0`, render the replay-derived `state_before[t]`, verify the preceding VFG action sequence equals replay actions through `t-1`, and validate the image/file plus symbolic-state linkage against the derived render input. Mark accepted rows `vision_available_step_aligned`; any mismatch/missing/unreadable frame excludes that transition and can make the P0 generator fail closed.
  Parallelization: Wave 1 | Blocked by: 1 and source transitions from 2 | Blocks: 4-6 | Can parallelize with: none.
  References (executor has NO interview context - be exhaustive): `scripts/phase3/pipeline.py:129-155,468-498`; `scripts/phase3/generate_planimation_vlm.py:13-64`; `scripts/phase3/planimation_pairing_manifest.py`; `scripts/phase3/planimation_pairing_replay.py`; `scripts/phase3/planimation_pairing_rendering.py`; `scripts/phase3/planimation_persisted_contracts.py`; `tests/phase3/test_planimation_pairing.py:1000-1058`; `tests/phase3/test_verify_planimation_vlm.py`; `data/phase3_supervised_planning/diagnostics/vision_validation.jsonl`.
  Acceptance criteria (agent-executable): the alignment CLI emits `data/planning_cgas_v1/alignment/{train,dev,test}.jsonl` and accepts a source transition only when one decodable PNG has a one-to-one transition mapping, matching action/order evidence, and matching replay-derived state identity. `python -m pytest -q tests/phase3/test_cgas_alignment.py tests/phase3/test_planimation_pairing.py tests/phase3/test_verify_planimation_vlm.py` passes; its verification JSON reports zero missing, duplicate, unreadable, action-order, and state-linkage failures for emitted rows.
  QA scenarios (name the exact tool + invocation): Happy - render a bounded Blocksworld fixture with the alignment CLI, then run `--verify`; require exactly one aligned pre-action image per emitted step. Failure - swap two frame paths, mutate one VFG action, or remove the initial frame in copied test fixtures; require nonzero `--verify`, no accepted row for the affected transition, and an explicit `frame_action_order_mismatch`, `missing_initial_frame`, or `state_linkage_mismatch` reason. Evidence `<attemptDir>/task-3-cgas-dataloader-and-experiment-support/{pytest.txt,alignment.jsonl,verify.json,swapped-frame.txt,missing-frame.txt}`.
  Commit: Y | `feat(cgas): verify pre-action planning images`

- [x] 4. Define `planning_cgas_v1` and implement executable BFS/IW certificate and one-invariant counterfactual primitives.
  What to do / Must NOT do: Add a versioned JSON Schema and a deterministic builder consuming only the accepted source and alignment manifests. Emit one record per transition with stable ID, source hash, planner/version, split/OOD label, task text, single aligned image path, action target, typed certificate target, replay/verifier evidence, and target-only counterfactual variants. BFS certificate fields are frontier head/order summary, visited delta, and expanded state; IW fields are novelty tuple, seen-feature delta, and width decision. The verifier must prove correct transitions and reject exactly one named invariant per counterfactual. Keep route label, memory payload, and scaffold costs absent/deferred; do not include gold target or diagnostic fields in the future model input object.
  Parallelization: Wave 2 | Blocked by: 2-3 | Blocks: 5-6 | Can parallelize with: none.
  References (executor has NO interview context - be exhaustive): `doc/research_proposal.md:22-36,84-108,110-122`; `doc/high_level_plans/research_execution_plan.md:73-96`; `scripts/phase3/schema.py`; `scripts/phase3/trace_contracts.py`; `scripts/phase3/verifiers.py:39-91`; `examples/planning_benchmark_slice/trajectory_schema.py`; `tests/planning_benchmark/test_experts_bfs_iw.py:53-89`; Todo 2-3 manifests.
  Acceptance criteria (agent-executable): `data/planning_cgas_v1/schema/planning_cgas_v1.schema.json` validates every generated step; the new verifier accepts every canonical certificate and rejects each generated counterfactual for exactly its declared invariant, with no second failing invariant. `python -m pytest -q tests/phase3/test_cgas_certificates.py tests/phase3/test_cgas_counterfactuals.py` passes and the builder's `--verify` output reports `invalid_schema_rows=0`, `valid_certificate_failures=0`, `counterfactual_wrong_failure_count=0`, and `counterfactual_multi_invariant_count=0`.
  QA scenarios (name the exact tool + invocation): Happy - build and verify a fixture containing BFS and IW transitions; require one valid certificate plus one accepted one-invariant counterfactual per required invariant. Failure - mutate two BFS fields or place a gold queue in the declared input object; require verifier rejection as `multiple_invariants_changed` or `oracle_field_in_input`. Evidence `<attemptDir>/task-4-cgas-dataloader-and-experiment-support/{pytest.txt,schema.json,certificate-verify.json,multi-invariant.txt,oracle-input.txt}`.
  Commit: Y | `feat(cgas): add verifier-backed planning step records`

- [x] 5. Convert only accepted `planning_cgas_v1` steps into strict Qwen-VL SFT JSONL and register dedicated train/dev datasets.
  What to do / Must NOT do: Add a planning-specific converter and strict preflight module under `starVLA/dataloader/` or `scripts/phase3/`, with tests. For each record, write exactly one relative `image` path rooted at a dedicated `data_path`, exactly one `<image>` in the human turn, fixed non-oracular task/planner metadata, and a parseable assistant JSON target containing only action plus certificate. Register separate training and development nicknames in `starVLA/dataloader/qwenvl_llavajson/qwen_data_config.py`; do not use the no-op LeRobot-style planning registry, full-plan supervision, a list of images, or unresolved absolute paths. The preflight must enforce the human-input allowlist and target-only denylist before writing output.
  Parallelization: Wave 2 | Blocked by: 4 | Blocks: 6 | Can parallelize with: none.
  References (executor has NO interview context - be exhaustive): `starVLA/dataloader/qwenvl_llavajson/qwen_data_config.py:5-55`; `starVLA/dataloader/vlm_datasets.py:142-201,204-244,246-305`; `examples/planning_benchmark_slice/train_files/data_registry/data_config.py:45-53,88-105`; `doc/research_proposal.md:28-36,101-112`; Todo 4 schema and accepted manifests.
  Acceptance criteria (agent-executable): converter writes `data/planning_cgas_v1/qwenvl/{train,dev,test}.jsonl` plus a digest manifest; every record has one image, one matching `<image>` token, one human and one assistant conversation turn, a valid JSON assistant target, an existing relative asset, and no denied field in model inputs. `python -m pytest -q tests/phase3/test_cgas_qwenvl_conversion.py tests/planning_benchmark/test_dataset_registry.py` passes; converter `--verify` reports zero path, token, schema, input-policy, and split-leakage errors.
  QA scenarios (name the exact tool + invocation): Happy - convert accepted fixture steps and run `--verify`; require one JSONL record per accepted step and correct Qwen dataset nicknames. Failure - add a second image token, absolute image path, `replay_transitions`, `route_label`, or `planner_trace` to a human turn; require nonzero preflight with the exact policy violation and no output record. Evidence `<attemptDir>/task-5-cgas-dataloader-and-experiment-support/{pytest.txt,conversion-manifest.json,verify.json,extra-token.txt,oracle-leak.txt}`.
  Commit: Y | `feat(cgas): convert verified planning steps for Qwen VL`

- [x] 6. Add a strict native-Qwen loader smoke and fail-closed corpus release gate.
  What to do / Must NOT do: Add a preflight that calls the same message building/tokenization code as the native loader once per record and records the originating `step_id`; do this before constructing `LazySupervisedDataset`, whose retry behavior can hide a corrupt source row. Then instantiate the actual registered train dataset and `DataCollatorForSupervisedDataset` with the configured Qwen processor to exercise a real batch. Assert identity preservation, non-empty assistant labels, and non-null image tensors/grid metadata. Publish `data/planning_cgas_v1/release_manifest.json` only after provenance, alignment, certificate, conversion, and strict loader checks pass; otherwise exit nonzero and delete/no-publish the pending release manifest without modifying prior approved releases.
  Parallelization: Wave 2 | Blocked by: 5 | Blocks: milestone handoff | Can parallelize with: none.
  References (executor has NO interview context - be exhaustive): `starVLA/dataloader/vlm_datasets.py:142-201,204-244,348-378,538-604,681-715`; `starVLA/dataloader/qwenvl_llavajson/qwen_data_config.py:30-55`; `doc/research_proposal.md:152-164`; `scripts/phase3/verifiers.py:39-91`; Todos 2-5 output manifests.
  Acceptance criteria (agent-executable): `python -m pytest -q tests/phase3/test_cgas_qwenvl_preflight.py tests/phase3/test_cgas_release_gate.py` passes. The strict preflight CLI reports `records_checked == records_emitted`, `row_identity_mismatches=0`, `message_build_failures=0`, `tokenization_failures=0`, `empty_assistant_label_rows=0`, and `null_image_tensor_rows=0`; the real loader/collator smoke creates one batch with non-null `pixel_values` and `image_grid_thw`. The release gate returns nonzero and does not publish a new manifest when any prerequisite report fails.
  QA scenarios (name the exact tool + invocation): Happy - run the strict preflight followed by the real Qwen processor/dataloader smoke on all emitted train rows; require all counts clean and a batch with image tensors. Failure - corrupt an image path or assistant JSON in a copied row; require preflight to fail on that exact `step_id`, rather than fall back to a later row, and require release-gate refusal. Evidence `<attemptDir>/task-6-cgas-dataloader-and-experiment-support/{pytest.txt,preflight.json,loader-batch.json,corrupt-row.txt,release-refusal.txt}`.
  Commit: Y | `feat(cgas): gate verified planning VLM releases`

## Final verification wave
> Runs in parallel after ALL todos. ALL must APPROVE. Surface results and wait for the user's explicit okay before declaring complete.
- [x] F1. Plan compliance audit
  Verify every released P0 row is Blocksworld BFS or width-1 IW, no record claims BFS from GBFS provenance, all split/OOD sets are disjoint, and all required manifests agree. Run the release verifier and save `<attemptDir>/final-plan-compliance.json`; PASS is zero errors and no unpublished partial output.
- [x] F2. Code quality and contract review
  Review changed Python/schema/config files plus `git diff --check`; run `pytest -q tests/phase3/test_cgas_provenance.py tests/phase3/test_cgas_alignment.py tests/phase3/test_cgas_certificates.py tests/phase3/test_cgas_counterfactuals.py tests/phase3/test_cgas_qwenvl_conversion.py tests/phase3/test_cgas_qwenvl_preflight.py tests/phase3/test_cgas_release_gate.py`. PASS is all tests green and no static/input-boundary regression.
- [x] F3. Real loader QA
  Run the strict all-row Qwen preflight and the configured Qwen processor plus `LazySupervisedDataset`/collator smoke against the released train split. Save command output and batch summary in `<attemptDir>/final-loader-qa/`; PASS is one-to-one row identity, non-null image tensors/grid metadata, and non-empty assistant labels.
- [x] F4. Scope-fidelity and research-gate audit
  Inspect release and experiment docs for prohibited claims/fields: no unaligned images, fake IW traces, GBFS-to-BFS relabelling, oracle leakage, route labels, memory, calibration, CGAS, or attention analysis. PASS is a written scope receipt confirming these remain deferred and the future milestone starts only from the release manifest.

## Commit strategy
- Commit 1: environment/readiness snapshot and P0 provenance gate.
- Commit 2: aligned-render manifest and strict alignment verifier.
- Commit 3: `planning_cgas_v1` schema, certificates, and counterfactual primitives.
- Commit 4: Qwen-VL conversion, strict preflight, registration, release gate, and documentation.
- Do not commit generated corpus/image artifacts unless the project explicitly chooses a data-release strategy; retain their manifests and deterministic regeneration commands instead.

## Success criteria
- The only P0 corpus considered trainable is Blocksworld `planning_cgas_v1`, with separate canonical FIFO BFS and width-1 IW examples in every required split, explicit structural-OOD partitioning, replay validation, and immutable provenance.
- Every VLA example maps one pre-action image to one replay transition through explicit state/action/order evidence; unaligned/missing/unreadable cases are excluded.
- Every typed certificate verifies; each generated counterfactual fails exactly one declared invariant; no route label is emitted in this milestone.
- Every converted record satisfies the native Qwen image/conversation contract and the no-oracle field policy, and strict preflight proves the loader sees the intended record rather than a retry substitute.
- The release manifest is published only after all P0 readiness checks and final verification tasks pass. Live memory, route labels, calibration, CGAS training, and attention analysis remain unimplemented and explicitly deferred.

## 2026-07-30 Fail-Closed Partition Characterization Receipt

The 481-row final characterization was independently cross-checked against `data/curriculum_pddl/accepted_manifest.jsonl` and the deterministic unapproved selector draft. The selector feasibility review is complete, but it is not a successful P0 partition: 24 paired-exact rows are all four-object, all 93 twelve-object rows are ineligible, 457 rows are excluded, and `records` is empty with `owner_approved=false`. This does not satisfy the role-bearing partition acceptance criterion in the plan. The final verification checklist remains unchecked and Todos 5-6 remain blocked; no approval, promotion, rendering, Qwen conversion, loader preflight, or release is authorized by this receipt.
