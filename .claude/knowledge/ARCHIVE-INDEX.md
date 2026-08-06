# Archived knowledge index

The 98 notes below were written during completed phases and were **not** carried into
`.claude/knowledge/` verbatim. Nothing is unrecoverable — each row says where the content lives now.

Recovery routes, in order of preference:

1. **`doc/…`** — a tracked, curated write-up of the same work. Prefer this; it is the maintained version.
2. **`git show <rev>:<path>`** — the note itself, from git history. All of these were tracked at removal.
3. **`.claude/archive/omo-evidence-2026-08-07.tar.gz`** — the raw evidence the note describes.

Removed 2026-08-07 together with `.omo/` and `.sisyphus/`. The last commit containing them is the
one immediately preceding that removal.

| Note | What it covered | Maintained write-up |
| --- | --- | --- |
| `cgas-certificate-publication-transaction-2026-07-28.md` | - Certificate publication owns only `steps/`, `schema/`, and | `doc/detailed_implementation_summary/phase3_cgas_certificate_publication_transaction_2026-07-28.md` |
| `cgas-certificates-2026-07-28.md` | - `scripts.phase3.cgas_provenance` is the authoritative source gate and | `doc/detailed_implementation_summary/phase3_cgas_certificates_2026-07-28.md` |
| `cgas-characterization-assembly-2026-07-29.md` | Date: 2026-07-29 | `doc/detailed_implementation_summary/phase3_cgas_characterization_assembly_2026-07-29.md` |
| `cgas-characterization-checkpoint-2026-07-29.md` | Date: 2026-07-29 | `doc/detailed_implementation_summary/phase3_cgas_characterization_checkpoint_2026-07-29.md` |
| `cgas-characterization-cli-2026-07-29.md` | Date: 2026-07-29 | git history |
| `cgas-characterization-determinism-oracles-2026-07-30.md` | - Use only the explicit synthetic 481-row fixture for finalization determinism tests; do not run product da... | `doc/detailed_implementation_summary/phase3_cgas_characterization_determinism_oracles_2026-07-30.md` |
| `cgas-characterization-final-bundle-2026-07-29.md` | - The only final publication profile is `regular_bundle_linkat_v1`, bound under `policies.final_publication... | `doc/detailed_implementation_summary/phase3_cgas_characterization_final_bundle_2026-07-29.md` |
| `cgas-characterization-kernel-isolation-2026-07-29.md` | - `cgas_partition_characterization.py` is the orchestration facade. Its `_characterize()` normalized AST is... | `doc/detailed_implementation_summary/phase3_cgas_characterization_kernel_isolation_2026-07-29.md` |
| `cgas-characterization-runner-2026-07-29.md` | Date: 2026-07-29 | `doc/detailed_implementation_summary/phase3_cgas_characterization_runner_2026-07-29.md` |
| `cgas-characterization-static-import-policy-2026-07-29.md` | Date: 2026-07-29 | `doc/detailed_implementation_summary/phase3_cgas_characterization_static_import_policy_2026-07-29.md` |
| `cgas-characterization-typed-primitives-2026-07-29.md` | Date: 2026-07-29 | git history |
| `cgas-characterization-verification-call-contract-2026-07-29.md` | Phase 3 work verification is structural and must not call `_characterize`. Checkpoints carry a canonical ro... | git history |
| `cgas-characterization-verifier-2026-07-29.md` | Date: 2026-07-29 | `doc/detailed_implementation_summary/phase3_cgas_characterization_verifier_2026-07-29.md` |
| `cgas-characterization-work-initialization-2026-07-29.md` | - `scripts/phase3/cgas_characterization_work.py` uses `.initializing` as a durable incomplete-state marker.... | `doc/detailed_implementation_summary/phase3_cgas_characterization_work_initialization_2026-07-29.md` |
| `cgas-concurrent-shard-admission-2026-07-30.md` | - One command-wide descriptor `flock` serializes every mutating lifecycle command for one work root. Concur... | `doc/detailed_implementation_summary/phase3_cgas_concurrent_shard_admission_2026-07-30.md` |
| `cgas-dataloader-resume-blocker-2026-07-30.md` | Resuming `.omo/plans/cgas-dataloader-and-experiment-support.md` stops before Todo 5 because the final parti... | git history |
| `cgas-dataset-readiness-2026-07-28.md` | Date: 2026-07-28 | git history |
| `cgas-f2-remediation-import-boundary-2026-07-31.md` | Date: 2026-07-31 | git history |
| `cgas-finalize-wait-private-root-2026-07-30.md` | The isolated finalize-wait fixture must pass the nested fixture repository as | git history |
| `cgas-full-stored-row-binding-2026-07-28.md` | - `verify_steps()` deterministically regenerates its expected rows through | git history |
| `cgas-native-qwen-loader-release-gate-2026-07-30.md` | - `LazySupervisedDataset.__getitem__` can retry the next row after a loader failure, so CGAS strict preflig... | git history |
| `cgas-p0-provenance-gate-2026-07-28.md` | Date: 2026-07-28 | `doc/detailed_implementation_summary/phase3_cgas_p0_provenance_gate_2026-07-28.md` |
| `cgas-partition-approval-gate-2026-07-30.md` | - `scripts/phase3/cgas_partition_approval.py` is the new executable owner-approval boundary. | `doc/detailed_implementation_summary/phase3_cgas_partition_approval_gate_2026-07-30.md` |
| `cgas-partition-characterization-2026-07-29.md` | Date: 2026-07-29 | `doc/detailed_implementation_summary/phase3_cgas_partition_characterization_2026-07-29.md` |
| `cgas-partition-draft-integration-2026-07-30.md` | - The authoritative accepted manifest digest is `9a9817058e36f72468682c8b43a46c04591995bcb8fe28ee37819313f9... | `doc/detailed_implementation_summary/phase3_cgas_partition_draft_integration_2026-07-30.md` |
| `cgas-partition-feasibility-2026-07-30.md` | - `scripts/phase3/cgas_partition_feasibility.py` parses final bundle bytes through `parse_bundle()` and cal... | `doc/detailed_implementation_summary/phase3_cgas_partition_feasibility_2026-07-30.md` |
| `cgas-partition-selection-2026-07-30.md` | - `scripts/phase3/cgas_partition_selection.py` consumes only `parse_bundle()` final-member bytes and does n... | `doc/detailed_implementation_summary/phase3_cgas_partition_selection_2026-07-30.md` |
| `cgas-persisted-alignment-acceptance-binding-2026-07-28.md` | - `scripts.phase3.cgas_alignment.verify_persisted_alignment()` is the trust boundary for Todo 3 persisted a... | `doc/detailed_implementation_summary/phase3_cgas_persisted_alignment_acceptance_binding_2026-07-28.md` |
| `cgas-planner-alternative-profile-probe-2026-07-30.md` | - CLI: `python -m scripts.phase3.cgas_planner_alternative_profile_probe --output tmp/cgas-planner-alternati... | `doc/detailed_implementation_summary/phase3_cgas_planner_alternative_profile_probe_2026-07-30.md` |
| `cgas-planner-blocker-investigation-2026-07-30.md` | Separate planner diagnosis from partition feasibility. Representative search failures can establish a confi... | `doc/detailed_implementation_summary/phase3_cgas_planner_blocker_investigation_2026-07-30.md` |
| `cgas-planner-blocker-probe-2026-07-30.md` | - `scripts/phase3/cgas_planner_blocker_probe.py` is isolated from characterization, selection, and publicat... | `doc/detailed_implementation_summary/phase3_cgas_planner_blocker_probe_2026-07-30.md` |
| `cgas-production-single-writer-artifact-2026-07-30.md` | The retained partition-selection input is: | git history |
| `cgas-qwenvl-conversion-2026-07-28.md` | - The conversion boundary must call Todo4 `verify_steps()` first and consumes only its accepted serialized ... | `doc/detailed_implementation_summary/phase3_cgas_qwenvl_conversion_2026-07-28.md` |
| `cgas-qwenvl-todo5-strict-conversion-2026-07-30.md` | - Todo 5 Qwen conversion should consume only `verify_steps()`-accepted `planning_cgas_v1` steps and emit on... | `doc/detailed_implementation_summary/phase3_cgas_qwenvl_todo5_strict_conversion_2026-07-30.md` |
| `cgas-relative-private-root-2026-07-30.md` | `scripts/phase3/cgas_characterization_cli.py` resolves a relative | `doc/detailed_implementation_summary/phase3_cgas_relative_private_root_2026-07-30.md` |
| `cgas-release-boundary-manifest-handoff-2026-07-31.md` | Date: 2026-07-31 | git history |
| `cgas-replay-image-alignment-2026-07-28.md` | For CGAS P0 rows, image alignment cannot be proven by frame count. Verify the | git history |
| `cgas-steps-manifest-binding-2026-07-28.md` | - `scripts.phase3.cgas_certificates._steps_manifest()` is the single deterministic constructor for the pers... | `doc/detailed_implementation_summary/phase3_cgas_steps_manifest_binding_2026-07-28.md` |
| `cgas-trusted-state-gpfs-2026-07-30.md` | - The shared repository `tmp` is only a current-owner, non-group/other-writable parent. CGAS state is pinne... | `doc/detailed_implementation_summary/phase3_cgas_trusted_state_gpfs_2026-07-30.md` |
| `fast_forward_expert_task7_2026-06-24.md` | - `examples/planning_benchmark_slice/experts/fast_forward.py` implements the Phase 3 Fast Forward-style exp... | git history |
| `opencode-session-token-audit-2026-07-27.md` | - Audited active OpenCode session `ses_09964dc0cfferuEvG3FH5an6BT`. | git history |
| `output-layout-completed-apply-and-copy-publication-2026-07-27.md` | - A repository `flock` is not reentrant across separately opened descriptors. Code already holding `exclusi... | git history |
| `outputs-vlm-dataset-integrity-audit-2026-07-27.md` | Read-only audit of the active structured output roots: | git history |
| `outputs-vlm-layout-planning-2026-07-27.md` | - Requested end state: `outputs/reasoning_traces/`, `outputs/image_frames/`, and `outputs/deprecated/` are ... | git history |
| `phase3-15puzzle-easy-trace-fix.md` | Date: 2026-07-06 | `doc/detailed_implementation_summary/phase3_15puzzle_easy_trace_fix.md` |
| `phase3-blocksworld-medium-0011-search-size.md` | Measured for `data/curriculum_pddl/blocksworld/train/medium/blocksworld-train-medium-0011` after raising Ph... | git history |
| `phase3-concrete-traversal-state-projection-2026-07-15.md` | - Candidate `event_id` must retain frozen root, JSONL, line, source record, planner event, and candidate-ro... | `doc/detailed_implementation_summary/phase3_concrete_traversal_state_projection_2026-07-15.md` |
| `phase3-f2-facade-remediation-2026-07-16.md` | - Legacy import paths now expose compact compatibility facades for Phase 1, curriculum rendering, and Phase... | `doc/detailed_implementation_summary/phase3_f2_facade_remediation_2026-07-16.md` |
| `phase3-f2-image-rollout-remediation-2026-07-16.md` | - Local perimeter variation, rather than one corner pixel, is required to distinguish sprite contrast from ... | `doc/detailed_implementation_summary/phase3_f2_image_rollout_remediation_2026-07-16.md` |
| `phase3-f2-pairing-release-modularization-2026-07-16.md` | - The stable `planimation_pairing.py` facade delegates to `planimation_pairing_implementation.py`, which sy... | `doc/detailed_implementation_summary/phase3_f2_pairing_release_modularization_2026-07-16.md` |
| `phase3-f2-persisted-contract-remediation-2026-07-16.md` | - Persisted pair and state manifests cross a typed JSON boundary in `scripts/phase3/planimation_persisted_c... | `doc/detailed_implementation_summary/phase3_f2_persisted_contract_remediation_2026-07-16.md` |
| `phase3-f2-phase1-module-decomposition-2026-07-16.md` | `scripts.planimation_phase1` is now an explicit compatibility facade over focused modules: | `doc/detailed_implementation_summary/phase3_f2_phase1_module_decomposition_2026-07-16.md` |
| `phase3-f2-rendering-module-decomposition-2026-07-16.md` | The legacy `src.data_collect.rendering` import path remains a compatibility facade. Its exports now come fr... | `doc/detailed_implementation_summary/phase3_f2_rendering_module_decomposition_2026-07-16.md` |
| `phase3-f2-strict-contract-2026-07-16.md` | - Traversal traces reject booleans in integer fields and validate planner-specific scalar and nested succes... | `doc/detailed_implementation_summary/phase3_f2_strict_contract_remediation_2026-07-16.md` |
| `phase3-ferry-shared-location-lanes-2026-07-25.md` | For Ferry state `33b9c9648b4b132c94467949b8427b34`, both cars are `at l2`. | git history |
| `phase3-gbfs-replacement.md` | Date: 2026-07-07 | `doc/detailed_implementation_summary/phase3_gbfs_replacement.md` |
| `phase3-graphplan-safe-replay-2026-07-15.md` | - Graphplan proposition/action layers, mutex data, and the extraction description remain `planner_semantics... | `doc/detailed_implementation_summary/phase3_graphplan_safe_replay_2026-07-15.md` |
| `phase3-hard-one-per-domain-config-investigation.md` | Date: 2026-07-05 | git history |
| `phase3-hybrid-supervision-contract-2026-07-15.md` | - `full_reasoning_*.jsonl` records use `supervision_mode=hybrid_full` and a `planner_trace` target; `step_v... | git history |
| `phase3-hybrid-traversal-release-evidence-2026-07-15.md` | Date: 2026-07-15 | git history |
| `phase3-live-output-root-consumers.md` | New curriculum-trace generation defaults to `outputs/reasoning_traces/curriculum`. | git history |
| `phase3-local-planner-iw-ff-blocksworld-0011.md` | - `scripts/phase3/local_iw.py` now reads `local_iw_width` from planner limits, defaulting through callers t... | git history |
| `phase3-local-planner-traces.md` | Phase 3 supervised data generation lives under `scripts/phase3`. The pipeline uses `scripts/phase3/pddl.py`... | git history |
| `phase3-medium-trace-generation-fix.md` | Date: 2026-07-06 | `doc/detailed_implementation_summary/phase3_medium_trace_generation_fix.md` |
| `phase3-organize-outputs-todo4-synthetic-2026-07-27.md` | The Task 4 organizer is coordinated by `scripts/phase3/organize_outputs.py`. Existing helpers remain `scrip... | git history |
| `phase3-output-dataset-audit-2026-07-09.md` | Audit scope: non-deprecated roots under `outputs/`; explicitly ignored `outputs/deprecated/` and any `depre... | git history |
| `phase3-output-layout-lock-2026-07-27.md` | `scripts/phase3/output_layout_lock.py` provides the repository-wide advisory lock used to coordinate Phase ... | git history |
| `phase3-output-layout-receipt-fixed-sidecar-verification-2026-07-27.md` | The receipt persistence protocol uses only `.<receipt>.txn` and `.<receipt>.swap` for crash recovery. A rep... | git history |
| `phase3-output-layout-shared-writer-lock-2026-07-27.md` | Phase 3 writers select the output-layout lock from the repository, not from the output root. Both use `shar... | `doc/detailed_implementation_summary/phase3_output_layout_shared_writer_lock_2026-07-27.md` |
| `phase3-output-layout-wave1-repair-2-2026-07-27.md` | > Superseded retention note: Repair 3 removed the `<stage>.cleanup` namespace transition. Current failed st... | `doc/detailed_implementation_summary/phase3_output_layout_wave1_repair_2_2026-07-27.md` |
| `phase3-output-layout-wave1-repair-3-2026-07-27.md` | Filesystem publication success must stay descriptor-bound through the final exact-tree, protected-target, a... | `doc/detailed_implementation_summary/phase3_output_layout_wave1_repair_3_2026-07-27.md` |
| `phase3-output-layout-wave1-security-hardening-2026-07-27.md` | Wave 1 receipt reads must open untrusted receipt and fixed-sidecar names with | `doc/detailed_implementation_summary/phase3_output_layout_wave1_security_hardening_2026-07-27.md` |
| `phase3-output-vlm-dataset-layout-wave1-review-repair-2026-07-27.md` | - Metadata checks do not make later path opens safe. Reopen untrusted regular | git history |
| `phase3-parallel-jobs-generation.md` | - Added native `--jobs` support to `scripts/phase3/generate_curriculum_trace_dataset.py` and `python -m scr... | `doc/detailed_implementation_summary/phase3_parallel_jobs_generation.md` |
| `phase3-planimation-pilot-contract-and-render-recovery-2026-07-25.md` | `input_pairing_manifest_sha256` identifies the full source pairing manifest | `doc/detailed_implementation_summary/phase3_planimation_pilot_contract_and_render_recovery_2026-07-25.md` |
| `phase3-planimation-production-run-scope-2026-07-22.md` | - Output root: `outputs/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800`. | git history |
| `phase3-planimation-render-cache-hardening-2026-07-15.md` | - Resolve Planimation profiles from `src/data_collect/configs/curriculum_15_domains.yaml` through `load_cur... | `doc/detailed_implementation_summary/phase3_planimation_render_cache_hardening_2026-07-15.md` |
| `phase3-planimation-render-observability-and-semantics-2026-07-21.md` | 1. The legacy Blocksworld animation profile used `(:predicate ontable ...)`, but the current domain declare... | `doc/detailed_implementation_summary/phase3_planimation_render_observability_and_semantics_2026-07-21.md` |
| `phase3-planimation-used-pddl-url-contract-2026-07-22.md` | `render_state_with_planimation()` returns `used_pddl_url` on successful PDDL uploads. `_render_one_state()`... | `doc/detailed_implementation_summary/phase3_planimation_used_pddl_url_contract_2026-07-22.md` |
| `phase3-planimation-vlm-pairing-2026-07-15.md` | - Added `scripts/phase3/planimation_pairing.py`, `scripts/phase3/generate_planimation_vlm.py`, and `scripts... | git history |
| `phase3-pytest-runtime-classification-2026-07-15.md` | - `pytest tests/phase3 -vv --durations=0` collects 106 items and stalls at `test_15puzzle_easy_first_ten_cu... | git history |
| `phase3-release-verifier-2026-07-15.md` | The Planimation verifier has three explicit boundaries: `manifest` validates nonempty pairing provenance an... | git history |
| `phase3-render-validation-gates-2026-07-15.md` | - Todo 6 treats a render receipt as valid only when stage-zero VFG sprites have numeric, in-canvas, noncoin... | git history |
| `phase3-rollout-gates-2026-07-15.md` | `rollout_gates.py prepare` freezes deterministic eligible pair IDs and immutable source provenance from a f... | git history |
| `phase3-search-trace-fidelity.md` | For `outputs/phase3_traces/<instance_id>/traces/*.planner_trace.json`, interpret the four planner traces as... | git history |
| `phase3-task-4-compatibility-reference-relocation.md` | When relocating Phase 3 compatibility references, keep each destination basename identical to its source ba... | git history |
| `phase3-traversal-trace-contracts-2026-07-15.md` | - The active planner set is exactly `ff`, `gbfs`, `iw`, and `graphplan`; reject `bfs` instead of translatin... | `doc/detailed_implementation_summary/phase3_traversal_trace_contracts_2026-07-15.md` |
| `phase3_curriculum_extension_fd_plans_2026-06-28.md` | - Current root `data/curriculum_pddl` has been extended in place through the shard/safety-merge workflow to... | git history |
| `phase3_f2_exception_boundaries_2026-07-16.md` | Planimation production paths must distinguish expected operational failures from adapter and programming de... | git history |
| `phase3_supervised_planning_pipeline_2026-06-28.md` | - Dedicated package: `scripts/phase3/`. | git history |
| `planimation-pilot-launcher-conda-nounset-2026-07-25.md` | `temp_fast_planimation_render.sh` enables Bash strict mode with `set -euo pipefail`. | git history |
| `planning_benchmark_graphplan_expert.md` | - `examples/planning_benchmark_slice/experts/graphplan.py` implements the Phase 1-3 P0 Graphplan generator ... | git history |
| `planning_docs_check_task11_2026-06-24.md` | `examples.planning_benchmark_slice.docs_check` is the narrow Phase 1-3 closeout verifier. It checks that re... | git history |
| `planning_modality_serializers.md` | - Task 9 modality serialization lives in `examples/planning_benchmark_slice/modality_serializers.py` with C... | git history |
| `planning_registry_smoke_task10_2026-06-24.md` | - StarVLA registry auto-discovery scans `examples/*/train_files/data_registry/data_config.py` and merges to... | git history |
| `planning_trajectory_schema_task5_2026-06-24.md` | - Canonical expert trajectory validation is implemented in `examples/planning_benchmark_slice/trajectory_sc... | git history |
| `project-status-assessment-2026-07-15.md` | - `doc/research_proposal.md` is the study's canonical scope: test the Computational Resource Substitution H... | git history |
| `research_plan_alignment_2026-06-24.md` | - `doc/research_proposal.md` is the canonical source of truth for the current study scope. | git history |
