# High-Level Execution Plan: Certificate-Guided Adaptive Scaffolding

## Purpose

This plan turns `doc/research_proposal.md` into a runnable, method-centered study of **Certificate-Guided Adaptive Scaffolding (CGAS)**. The target is not a broad modality ablation or an attention-analysis paper. The target is a learned controller that selects the least costly bounded support required to preserve a verifier-checked planning certificate.

The execution sequence is intentionally narrow:

1. make BFS and IW trace semantics, images, and verifiers trustworthy;
2. build bounded, live certificate memory;
3. run a small calibration pass that fixes the scaffold palette;
4. train CGAS against matched static and generic-routing baselines; and
5. evaluate the structural fidelity-cost frontier before expanding to other planners or domains.

## Current Baseline

### What already exists

- A deterministic symbolic Blocksworld benchmark loop and expert-trace infrastructure.
- Planning-data generation, Planimation/VFG rendering work, modality serializers, and release-validation machinery.
- Historical BFS, FF, IW, and Graphplan documentation plus a later multi-domain GBFS/FF/IW/Graphplan path.

### What is missing

- A trainable planner model, real VLM/SFT run, or GPU-backed experimental result.
- Semantically validated, aligned visual step records for the CGAS core dataset.
- A live external-memory interface; current scratchpad packaging is not a tool-use experiment.
- A certificate schema, counterfactual certificate generator, and route-label verifier.
- A resolved BFS versus GBFS provenance decision and exact labels for FF/Graphplan approximations.

### Existing-scope caveat

Phase 1-3 closeout documents are engineering evidence, not empirical support for CGAS. In particular, no Phase 4 training, planner model, SFT, real VLM, GPU, API, or external-service execution is complete. Generated data and historical output roots must be revalidated before they become research inputs.

## Guiding Decisions

| Decision | Rationale |
|---|---|
| BFS and IW are the P0 algorithms. | Their certificate invariants and memory dependence are precise. |
| Keep the core observation fixed to VLA. | CGAS must not confound support allocation with added task information. |
| FF and Graphplan are P2 only. | Their current semantics require validation or precise approximation labels. |
| Memory is live, bounded, state-keyed, and auditable. | A serialized gold queue is not a valid tool-use condition. |
| Analysis is calibration-sized. | One failure matrix, one route-calibration curve, and one controller ablation are enough for the main story. |
| Every main comparison is budget-matched. | CGAS must beat direct decoding on fidelity and always-on memory on cost. |

---

## Phase 0 - Trace Readiness and Scope Repair

### Objective

Create a versioned, reproducible core corpus whose planner traces and visual records can support verifier-derived labels.

### Main tasks

- Resolve and document whether the P0 systematic-search condition is canonical BFS or GBFS. Do not mix them.
- Audit BFS and IW trace fields against executable state transitions.
- Generate aligned pre-action images for every P0 training and evaluation step; reject missing or unaligned visual records.
- Version the source root, planner implementation, render profile, and trace-contract version in every record.
- Define the P0 Blocksworld structural split: horizon, object count, branching factor, compositional arrangement, naming, and renderer shift.
- Keep FF and Graphplan out of P0 until their semantics and source provenance are independently validated.

### Deliverable

A manifested BFS/IW corpus with replay-valid plans, semantic certificate targets, aligned images, and explicit source provenance.

### Gate

Every P0 row has a decodable image, a replay-valid action transition, and an accepted certificate target. A row that lacks any one of these is excluded, not repaired by inference.

---

## Phase 1 - Certificate and Counterfactual Verifier

### Objective

Make each core search update mechanically checkable and generate minimal counterfactual training targets.

### Main tasks

- Define typed BFS certificates: frontier head/order summary, visited delta, and expanded state.
- Define typed IW certificates: novelty tuple, seen-feature delta, and width decision.
- Implement a pure verifier that checks each field against the planner transition.
- Generate one-invariant counterfactuals such as FIFO/LIFO order, omitted visited update, already-seen novelty tuple, or invalid width transition.
- Reject counterfactuals that change multiple invariants or accidentally preserve verifier validity.
- Produce route labels by evaluating each permitted scaffold and selecting the minimum-cost valid one.

### Repo surfaces

- `examples/planning_benchmark_slice/` or a new planning benchmark package for certificates and verifiers.
- `scripts/phase3/` only where existing trace schemas can be safely reused.
- `tests/` for verifier and counterfactual contracts.

### Deliverable

A versioned certificate schema, deterministic verifier, counterfactual generator, and route-label dataset builder.

---

## Phase 2 - Bounded Live Certificate Memory

### Objective

Implement the support palette used by CGAS without leaking oracle planner state.

### Main tasks

- Implement `read`, `append`, `replace`, and `delete` for an environment-owned certificate store.
- Key records by search-state identity and certificate version.
- Enforce byte, operation-count, and latency budgets.
- Allow only model predictions or prior verifier-approved certificate entries to be stored.
- Log every operation and returned payload for cost and provenance evaluation.
- Implement identical stores for CGAS and always-on-memory baselines.

### Deliverable

A deterministic, audited live-memory interface with a testable no-oracle-leakage contract.

---

## Phase 3 - Baseline and Calibration Run

### Objective

Use a small static VLA baseline to freeze CGAS design choices without turning analysis into the paper.

### Main tasks

- Train a direct VLA action-plus-certificate baseline on short BFS/IW traces.
- Evaluate held-out calibration instances and record the first verifier failure.
- Choose and freeze the certificate field set, scaffold palette, operation cost, and counterfactual sampling policy.
- Build one failure matrix and one route-calibration target report.
- Preregister the resulting CGAS configuration and main evaluation split before the method run.

### Deliverable

A compact calibration report and a frozen CGAS specification.

### Gate

At least one recurrent, certificate-localized failure must exist. Otherwise there is no justified adaptive-scaffolding method and the research direction must be reconsidered.

---

## Phase 4 - CGAS Planner Model

### Objective

Implement the method and matched baselines in the existing training stack.

### Main tasks

- Add action and typed-certificate prediction heads to the selected planner backbone.
- Add a small scaffold controller consuming the predicted certificate, prior support use, and a fixed-size observation representation.
- Implement direct, compact-certificate, and memory paths with the same backbone and action head.
- Train route selection from counterfactual minimum-cost labels.
- Implement a parameter-matched confidence or entropy router.
- Keep raw VLA observation, context budget, training examples, and action vocabulary fixed across core methods.

### Repo surfaces

- `starVLA/model/framework/`
- `starVLA/config/training/`
- `starVLA/training/`
- a planning-specific module under `examples/` for certificate and memory adapters

### Deliverable

A runnable CGAS model and direct, always-on-certificate, always-on-memory, and generic-router baselines.

---

## Phase 5 - Main Method Evaluation

### Objective

Measure the structural fidelity-cost frontier with matched baselines.

### Main tasks

- Run at least five seeds when compute permits.
- Evaluate in-distribution and structural OOD grids for horizon, object count, branching, composition, naming, and rendering.
- Report verified certificate fidelity, valid-plan success, scaffold cost, latency, and route optimality.
- Compare at matched cost and matched fidelity against direct and always-on baselines.
- Add uniform certificate/process supervision and a robust-fusion or modality-dropout comparator where feasible.
- Run one controller ablation that removes certificate inputs; do not require an attention-map study.

### Deliverable

Paper-ready tables and figures showing whether CGAS separates from generic routing and from fixed support policies.

---

## Phase 6 - Secondary Generalization and Extensions

### Objective

Test scope only after the main method result is established.

### Main tasks

- Add FF and Graphplan-style certificates only after their exact semantics or approximation labels are locked.
- Run vision-only and language-only stress tests as secondary resource analyses.
- Extend to additional planning domains only if the P0 certificate verifier remains valid.
- Treat cross-task transfer, continuous world models, and broad attention analysis as follow-on work rather than ICLR requirements.

### Deliverable

Clearly labelled generalization evidence that does not weaken the core CGAS causal comparison.

---

## Practical Build Order

1. Reconcile planner provenance and regenerate or validate P0 BFS/IW rows.
2. Add aligned-image and semantic-certificate gates.
3. Implement the certificate verifier and minimal counterfactual generator.
4. Implement audited bounded memory.
5. Run the direct-VLA calibration baseline.
6. Freeze the scaffold palette and route labels.
7. Implement CGAS and matched baselines.
8. Run the main structural OOD and budget sweep.
9. Decide whether FF/Graphplan transfer is justified.

## Recommended First Milestone

**Produce one Blocksworld BFS/IW dataset slice with aligned images, replay-valid actions, typed certificates, deterministic verifier results, one-invariant counterfactuals, and an audited memory stub.**

This milestone proves that the method's supervision signal is real before model training begins.

## Immediate Next Steps

1. Write a short decision record that fixes BFS versus GBFS for P0.
2. Define the BFS and IW certificate JSON schemas and verifier contracts.
3. Add a dataset audit for image alignment, certificate validity, and provenance.
4. Implement the counterfactual generator with one mutation per record.
5. Implement a local bounded certificate-store API and no-oracle-leakage tests.
6. Create one direct-VLA calibration configuration and one evaluation command that reports first certificate failures.

## Success Criteria for the Research Infrastructure

The repository is ready for the main CGAS experiment when it can:

- emit aligned VLA observations and replay-valid action transitions;
- generate and verify BFS/IW certificates and one-invariant counterfactuals;
- run a live bounded certificate store with complete operation logs;
- train direct, always-on, generic-router, and CGAS variants from the same dataset;
- evaluate fidelity, plan validity, scaffold cost, and route optimality on structural OOD splits; and
- reproduce every reported result from a versioned manifest and configuration.
