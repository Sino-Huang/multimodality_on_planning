---
slug: cgas-dataloader-and-experiment-support
status: approved
intent: clear
review_required: false
pending-action: formal plan written; execution remains deferred to $start-work
approach: This approved milestone covers only C1-C3: strict P0 corpus readiness, typed step-level certificate derivation, and native Qwen-VL conversion. Memory, route-label finalization, calibration, and CGAS are follow-up work.
---

# Draft: cgas-dataloader-and-experiment-support

## Components (topology ledger)
<!-- Lock the SHAPE before depth. One row per top-level component that can succeed or fail independently. -->
<!-- id | outcome (one line) | status: active|deferred | evidence path -->
| id | outcome (one line) | status | evidence path |
|---|---|---|---|
| C1 | Audit and lock a P0 BFS/IW corpus with valid split, provenance, replay, and pre-action visual alignment. | active | `data/phase3_supervised_planning/summary.json:10-39`; `diagnostics/vision_validation.jsonl` |
| C2 | Derive versioned, step-level certificate records and counterfactual labels from accepted planner transitions. | active | `doc/research_proposal.md:84-108` |
| C3 | Convert only accepted records to the native Qwen-VL conversation/image format and register a dedicated training dataset. | active | `starVLA/dataloader/vlm_datasets.py:142-201,246-305`; `qwen_data_config.py:5-55` |
| C4 | Supply bounded, auditable certificate memory and a direct-VLA calibration runner before CGAS. | deferred after C1-C3 | `doc/high_level_plans/research_execution_plan.md:100-141` |
| C5 | Implement CGAS and matched baselines only after calibration freezes the certificate palette and route labels. | deferred after C4 | `doc/high_level_plans/research_execution_plan.md:123-141,213-223` |

## Open assumptions (announced defaults)
<!-- Record any default you adopt instead of asking, so the user can veto it at the gate. -->
<!-- assumption | adopted default | rationale | reversible? -->
| assumption | adopted default | rationale | reversible? |
|---|---|---|---|
| P0 training format | A separate versioned `planning_cgas_v1` step-record corpus, converted to Qwen-VL JSON only after validation. | Phase 3's nested example schema and registry are not the native VLM SFT contract. | yes |
| Core planners | Keep BFS and IW as the desired P0 methods; first repair the missing IW corpus rather than fabricating it. | The proposal's novelty requires precise FIFO/visited and novelty invariants. | no for the planned P0 claim |
| Vision eligibility | Exclude `vision_available_unaligned` rows from multimodal supervision and retain them only for non-visual diagnostics. | A valid image file is not proof that it represents the planner state before the supervised transition. | yes after rerendering/realignment |
| Analysis scope | Use a direct-VLA calibration and one controller ablation; do not build a broad attention-analysis pipeline. | This maintains the method-centered CGAS story. | yes |
| Model integration | First reuse existing Qwen-VL SFT conversations and collator; add planning-specific heads/controller only after the data contract is proven. | The current SFT loader already tokenizes conversations, labels assistant spans, and batches images. | yes |

## Findings (cited - path:lines)
- The current Phase 3 artifact is a reproducible raw source, not a CGAS-ready training corpus: it contains 411 BFS `success_full_trace` examples (363/28/20), while FF, Graphplan, and IW are all `skipped_planner_unavailable`. `data/phase3_supervised_planning/summary.json:10-39`.
- Every emitted Phase 3 row is marked `vision_supervision_available=true`, but the visual diagnostics classify 3,600 inspected instances as `vision_available_unaligned`. The records provide frame paths, but the status does not establish pre-action frame-to-transition alignment. `data/phase3_supervised_planning/diagnostics/vision_validation.jsonl`; `data/phase3_supervised_planning/train.jsonl`.
- The Phase 3 records expose useful raw supervision: BFS `planner_trace.queue_events` and replay transitions, but their JSON schema leaves `model_facing`, `supervised_target`, and `evaluation_metadata` as opaque objects rather than typed step-level contracts. `data/phase3_supervised_planning/schema/supervised_planning_example.schema.json:8-58`.
- The planning registry is deliberately only discoverability/smoke infrastructure. Its transform is a no-op and its docstring explicitly says it does not claim StarVLA/LeRobot tensor conversion. `examples/planning_benchmark_slice/train_files/data_registry/data_config.py:45-53,56-62,88-105`.
- The native Qwen-VL SFT path reads named datasets from `qwen_data_config.data_dict`, loads records containing `conversations`, resolves every `<image>` placeholder against `image` paths, then labels assistant spans and collates token/image tensors. `starVLA/dataloader/qwenvl_llavajson/qwen_data_config.py:5-55`; `starVLA/dataloader/vlm_datasets.py:142-201,246-305,538-604,681-715`.
- The active Phase 3 pipeline was historically changed from BFS to GBFS, while this corpus says `bfs`; provenance must be reconciled before making FIFO claims. `doc/detailed_implementation_summary/phase3_gbfs_replacement.md:7-18`; `doc/research_proposal.md:90-98`.
- The research design explicitly requires BFS/IW certificate verifiers, one-invariant counterfactuals, non-oracular bounded memory, calibration before CGAS, and a fidelity-cost evaluation. `doc/research_proposal.md:10-16,90-122,142-164`; `doc/high_level_plans/research_execution_plan.md:53-117,123-141`.

## Decisions (with rationale)
- **Do not start with a generic dataloader.** Start with a `planning_cgas_v1` adapter/verifier preparation slice: without typed step targets and aligned images, a loader would only serialize an ambiguous full-plan target and could not supervise CGAS's action, certificate, or route objectives.
- **Use raw BFS traces as source material, not as a finished training target.** Queue events and replay transitions can derive valid BFS certificates after semantic provenance is locked; no IW placeholder, heuristic imitation, or inferred trace may substitute for the required IW source.
- **Keep the VLA observation fixed in principal CGAS comparisons.** The adapter may emit language-only and vision-language variants for controlled stress tests, but it must not let the controller obtain new task information by choosing a scaffold.
- **Make data acceptance mechanical.** A step is eligible only when source provenance, split membership, action replay, typed certificate verification, counterfactual one-invariant proof, and (for VLA) pre-action image alignment all pass.
- **Prevent oracle leakage at the dataset boundary.** Gold certificates and minimum-cost route labels are assistant targets/evaluation references only; the future model input may contain only current observation, bounded prior verifier-approved certificate context, and allowed live-memory outputs.

## Scope IN
- A manifest-lock audit covering split isolation, file/image readability, trace-to-replay linkage, planner/version provenance, and frame-to-pre-action alignment.
- A versioned step-level `planning_cgas_v1` intermediate schema with identifiers, source record hash, planner family/version, split, task text, image path, action target, typed certificate target, verifier result, route label, and token/tool-cost metadata.
- Pure BFS/IW certificate verifiers plus one-invariant counterfactual generation and deterministic acceptance tests.
- Conversion of eligible records to the existing Qwen-VL `image` plus `conversations` contract, with a planning-specific dataset registration rather than reuse of the no-op registry.
- Bounded certificate-memory interface, direct action-plus-certificate calibration baseline, and the logging/evaluator needed to freeze the CGAS scaffold palette.
- Later CGAS/direct/always-on/generic-router comparisons with identical backbone, observation, memory budget, and action vocabulary.

## Scope OUT (Must NOT have)
- No training on `vision_available_unaligned` rows as multimodal step supervision.
- No fabricated IW, FF, or Graphplan traces; FF/Graphplan remain P2 after semantic validation.
- No full gold queue, novelty table, replay trace, or oracle route label in model inputs or live memory.
- No attention-map suite or broad model-interpretability project as a prerequisite for the paper.
- No conversion of planning targets to continuous robot actions and no replacement of StarVLA's existing SFT collator before a demonstrated need.

## Open questions
- No owner decision blocks a detailed plan. The default is to make data acceptance strict and to schedule IW regeneration/aligned render repair ahead of model training.

## Plan-review resolutions
- Metis review identified that route labels cannot be finalized until executable supports, measured costs, and calibration freeze the scaffold palette. This milestone therefore creates certificate and counterfactual primitives only; final route labels are deferred.
- Metis review identified a scope contradiction. This plan contains C1-C3 only; bounded memory, calibration, and CGAS/baselines remain follow-up plans.
- A `bfs` row is accepted only if its source manifest identifies an actual FIFO BFS implementation and sorted successor tie-break. A GBFS row is never relabelled as BFS; unresolved rows are rejected and regenerated.
- P0 is Blocksworld-only. The future readiness manifest must prescribe disjoint train/dev/test and structural-OOD partitions before the converter reads a row.
- For a supervised transition at index `t`, the eligible image must be proven to depict `state_before[t]`; use the initial rendering for `t=0` and derive later state renderings from the replay transition, with action/order/state evidence in the alignment manifest.
- The Qwen human input allowlist contains only task text, current image reference, planner identity/version, and permitted bounded prior context. Gold action/certificate, route label, queue/novelty state, replay trace, final-state metadata, and evaluation metadata are target-only and must be rejected if present in inputs or memory payloads.
- Require a strict row-level Qwen preflight before `LazySupervisedDataset`: do not rely on its retry path because a bad record may otherwise be replaced with a different sample.

## Proposed TODO sequence
1. **Lock P0 provenance and audit the corpus.** Resolve BFS-versus-GBFS provenance, verify split/source hashes and replay linkage, and emit a machine-readable readiness manifest. This prevents a certificate verifier from validating the wrong algorithm.
2. **Repair P0 coverage and multimodal alignment.** Produce or acquire full IW traces and generate a single decodable pre-action image for every candidate step. Reject ambiguous or unaligned rows rather than guessing an offset.
3. **Define `planning_cgas_v1`.** Flatten accepted planner transitions into one step per sample with typed target fields, stable IDs, provenance, and explicit input-versus-target separation.
4. **Implement the executable certificate pipeline.** Add BFS/IW verifiers, generate exactly-one-invariant counterfactuals, prove their expected validity/failure, and compute minimum-cost route labels from the permitted scaffold palette.
5. **Build the Qwen-VL conversion and dataset registration.** Convert only accepted step records into one-turn action-plus-certificate conversations and aligned image references; validate them through the actual `LazySupervisedDataset` and collator, not only registry discovery.
6. **Add a bounded live certificate store.** Enforce state keys, byte/operation/latency limits, audit logs, and no-oracle-leakage tests shared with the always-on-memory baseline.
7. **Run the direct-VLA calibration.** Train only the action-plus-certificate baseline on the frozen core corpus; use first-failure statistics to set the certificate fields, scaffold palette, costs, and counterfactual policy.
8. **Implement and evaluate CGAS.** Add the route controller and matched direct/always-on/generic-router baselines, then measure verified structural fidelity, plan validity, cost, latency, and route optimality on fixed structural OOD splits.

## Approval gate
status: awaiting-approval
approach: The formal plan covers P0 Blocksworld BFS/IW provenance and aligned renders, `planning_cgas_v1` certificates/counterfactual primitives, strict Qwen-VL conversion, and loader preflight only. Route labels, memory, calibration, and CGAS are explicitly deferred.
next workflow action: Execute only in a later `$start-work cgas-dataloader-and-experiment-support` session after the required Python environment is confirmed, or request a high-accuracy plan review first.
