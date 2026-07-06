# High-Level Plan for Implementing `doc/research_proposal.md`

## Purpose

This document translates the research proposal into a repo-specific execution plan for this codebase, which currently has:

- a StarVLA-derived modular training and evaluation stack,
- a standalone Planimation API client under `modules/api-tools`, and
- no proposal-specific planning benchmark, planner implementation, scratchpad tool interface, or evaluation pipeline yet.

The goal is to build the minimum complete research pipeline needed to test the proposal's core question: which planning algorithm families are best afforded by vision, language, and tool-based external memory.

---

## Current Baseline

### What already exists

- **Training infrastructure** in `starVLA/training/`.
- **Framework registry and model abstraction** in `starVLA/model/framework/`.
- **Dataset and dataloader plumbing** in `starVLA/dataloader/`.
- **Benchmark-style example structure** in `examples/`.
- **Deployment/evaluation server pattern** in `deployment/model_server/`.
- **Planimation client wrapper** in `modules/api-tools/planimation_api.py` and `modules/api-tools/planimation.py`.

### What is missing

- A **planning benchmark package** for the proposal's first runnable domain: Blocksworld with optional Planimation rendering.
- A **Planimation-aware environment adapter** integrated into the StarVLA workflow.
- A **zero-shot diagnostic path** that tests algorithmic knowledge vs. modality affordance before SFT.
- A **data generation pipeline** for expert demonstrations across the four proposal-aligned P0 families: BFS / Fast Forward / Iterated Width / Graphplan.
- A **planner framework** that consumes the chosen modality inputs and optionally uses tool memory.
- A **scratchpad tool interface** (`read` / `write`) exposed to the planner.
- A **frozen world-model interface** that can feed cached state representations into the planner without entangling planner training with world-model learning.
- A **proposal-specific evaluation suite** for zero-shot diagnostics, success rate, sample efficiency, generalization, process metrics, and failure-taxonomy analysis.

---

## High-Level Research Strategy

The cleanest path is to treat this project as a **new planning benchmark and planner extension on top of StarVLA**, not as a modification of StarVLA's existing robotics benchmarks.

In practice, that means:

1. build a new environment/data/eval slice for planning tasks,
2. reuse StarVLA's config, training, and checkpointing infrastructure,
3. keep Planimation as a visualization and environment-side utility rather than deeply coupling it into the model core,
4. introduce the research-specific planner variants as new frameworks or framework extensions,
5. stage the work so that the **zero-shot diagnostic and P0 experiments** from the proposal become runnable first.

---

## Recommended Phases

## Phase 1-3 closeout status

Phase 1, Phase 2, and the original Phase 3 smoke closure are complete for the Blocksworld-only P0 milestone. A later complete Phase 3 supervised-data corpus now exists under `data/phase3_supervised_planning` for all 15 curriculum domains with per-instance and per-planner accounting; this status still does not complete Phase 4 or any training/model work.

Evidence index:

- Phase 1 scope, symbolic core, and zero-shot diagnostic packaging: `.sisyphus/evidence/phase1-3-task-1-scope-lock.json`, `.sisyphus/evidence/phase1-3-task-2-valid-instance.json`, `.sisyphus/evidence/phase1-3-task-3-zero-shot-build.json`.
- Phase 2 direct Python benchmark loop: `.sisyphus/evidence/phase1-3-task-4-oracle-loop.json`, `.sisyphus/evidence/phase1-3-task-4-invalid-action.json`.
- Phase 3 expert schema, BFS, Fast Forward, Iterated Width, Graphplan, modality serializers, and registry smoke: `.sisyphus/evidence/phase1-3-task-5-schema-valid.json`, `.sisyphus/evidence/phase1-3-task-6-bfs-iw.json`, `.sisyphus/evidence/phase1-3-task-7-ff.json`, `.sisyphus/evidence/phase1-3-task-8-graphplan.json`, `.sisyphus/evidence/phase1-3-task-9-serialize.json`, `.sisyphus/evidence/phase1-3-task-10-registry.txt`.
- Documentation closeout checks: `.sisyphus/evidence/phase1-3-task-11-docs-check.json` and `.sisyphus/evidence/phase1-3-task-11-no-overclaim.json`.

Caveats:

- The original Phase 1-3 smoke closure is Blocksworld-only P0. The complete Phase 3 supervised-data corpus is the separate 15-domain JSONL pipeline documented in `doc/detailed_implementation_summary/phase3_complete_supervised_planning_data_summary.md`.
- The Phase 2 loop is a direct Python benchmark loop.
- Generated smoke outputs under `outputs/planning_artifacts/**` are reproducible local artifacts. Do not commit large generated data unless explicitly requested.
- No Phase 4 training, planner model implementation, SFT run, real VLM call, GPU run, API call, or external-service execution is complete.
- `doc/detailed_implementation_summary/phase2_curriculum_pddl_generation_summary.md` documents curriculum PDDL generation. It is not itself proof of Phase 3 expert demonstrations.

---

## Phase 1 - Pre-flight validation and scope lock

### Objective

Confirm the research can be implemented in this repo without first solving unrelated architecture problems, and lock the exact proposal-aligned P0 scope before broader build-out.

### Main tasks

- Decide the first domain to operationalize.
  - Recommended order: **Blocksworld/Planimation first**, then expand to additional domains.
- Lock the proposal's first-priority algorithm/modality matrix explicitly:
  - **Algorithms:** BFS, Fast Forward, Iterated Width, Graphplan.
  - **Modalities:** Vision-only, Language-only, VLA, VLA+Tool.
- Decide whether Blocksworld is handled as:
  - a purely symbolic planning environment with rendered images added for vision input, or
  - a more general StarVLA-style embodied environment.
- Verify how Planimation will be used:
  - visualization only,
  - state rendering source,
  - or both.
- Define the **zero-shot diagnostic gate** before any large SFT run:
  - fixed per-algorithm prompt format,
  - modality-specific input packaging,
  - JSON output schema for algorithm-state updates,
  - pass/fail criteria for algorithmic fidelity vs. action validity.
- Decide how the frozen world-model assumption is represented in the repo for P0:
  - cached symbolic/state features only for the first Blocksworld milestone, or
  - an explicit frozen encoder interface from the start.
- Fix the practical Planimation integration assumption early:
  - `modules/api-tools/planimation_api.py` currently points to localhost-style endpoints and should be made configurable before it is used in experiments.

### Deliverable

A frozen implementation scope for the first runnable benchmark, plus a written go/no-go definition for the zero-shot diagnostic, domain representation, visualization source, and Planimation usage.

### Status update

Phase 1 complete for Blocksworld-only P0. Evidence: `.sisyphus/evidence/phase1-3-task-1-scope-lock.json`, `.sisyphus/evidence/phase1-3-task-2-valid-instance.json`, and `.sisyphus/evidence/phase1-3-task-3-zero-shot-build.json`. Caveat: this does not claim all 15 curriculum domains as acceptance scope and does not claim real VLM or GPU zero-shot execution.

---

## Phase 2 - Build the planning benchmark slice

### Objective

Create a benchmark package that fits StarVLA's conventions but represents planning tasks rather than robot control.

### Main tasks

- Add a new example package under `examples/` for the planning benchmark.
- Define the task format for:
  - initial state,
  - goal,
  - action vocabulary,
  - state transition interface,
  - optional rendered observations,
  - optional language descriptions.
- Implement an adapter layer that can:
  - generate or load PDDL domain/problem files,
  - call Planimation when visual output is required,
  - cache returned renders or videos,
  - expose training/evaluation observations in a StarVLA-compatible format.
- Decide whether the benchmark loop runs:
  - directly in Python with local state transitions, or
  - through a server/client split similar to existing StarVLA deployment patterns.

### Repo surfaces

- `examples/`
- `deployment/model_server/`
- `modules/api-tools/`

### Deliverable

A minimal benchmark package that can load one planning instance and emit the modality views required by the proposal.

### Status update

Phase 2 complete for Blocksworld-only P0. Evidence: `.sisyphus/evidence/phase1-3-task-4-oracle-loop.json` and `.sisyphus/evidence/phase1-3-task-4-invalid-action.json`. Caveat: the accepted P0 loop is direct Python, not a WebSocket or server-client requirement.

---

## Phase 3 - Data and demonstration generation

### Objective

Generate the supervised training data needed for algorithm-specific learning.

### Main tasks

- Implement expert trajectory generation for the four proposal-aligned P0 algorithm families:
  - systematic search: BFS,
  - greedy heuristic search: Fast Forward,
  - structured exploration: Iterated Width,
  - constraint-based proposition planning: Graphplan.
- Keep any additional planners or approximations out of the core dataset unless they are explicitly marked as non-P0 exploratory baselines.
- Define a unified trajectory schema containing:
  - state or latent reference,
  - visual observation,
  - language description,
  - target planner decision,
  - optional queue/heuristic/novelty/planning-graph state,
  - final plan metadata.
- Build separate serialization paths for the four modality conditions:
  - Vision-only,
  - Language-only,
  - Vision + Language,
  - Vision + Language + Tool.
- Add a lightweight artifact path for zero-shot diagnostic instances so the same task packaging can be reused before and after SFT.
- Add dataset registration so the new data can flow through `starVLA/dataloader/`.

### Repo surfaces

- `starVLA/dataloader/`
- `examples/<planning-benchmark>/train_files/data_registry/`
- new offline data generation scripts under the planning example package

### Deliverable

A reproducible demonstration-generation pipeline with enough data to train at least the P0 experiments.

### Status update

Phase 3 complete for Blocksworld-only P0 expert demonstration generation and packaging. Evidence: `.sisyphus/evidence/phase1-3-task-5-schema-valid.json`, `.sisyphus/evidence/phase1-3-task-6-bfs-iw.json`, `.sisyphus/evidence/phase1-3-task-7-ff.json`, `.sisyphus/evidence/phase1-3-task-8-graphplan.json`, `.sisyphus/evidence/phase1-3-task-9-serialize.json`, and `.sisyphus/evidence/phase1-3-task-10-registry.txt`. Phase 3 also has a complete multi-domain supervised-data artifact at `data/phase3_supervised_planning`, generated and verified by `scripts.phase3`; see `doc/detailed_implementation_summary/phase3_complete_supervised_planning_data_summary.md`. Current generation probes configured external FF/IW/Graphplan executables first and falls back to repo-local deterministic traces for supported small STRIPS instances when external final-plan sources are unavailable; see `doc/detailed_implementation_summary/phase3_local_planner_trace_generation_summary.md`. Caveat: not all planner attempts succeed, external-only successes are labeled `success_plan_replayed` rather than full internal traces, and no Phase 4 training is complete.

---

## Phase 4 - Planner model and modality interfaces

### Objective

Create the planning model path that actually learns the algorithm families under different modality conditions.

### Main tasks

- Decide whether to implement the planner as:
  - a new framework under `starVLA/model/framework/`, or
  - a lightweight extension of an existing Qwen-based framework.
- Implement input handling for the proposal's modality matrix:
  - rendered image inputs,
  - language/PDDL/text state inputs,
  - optional combined multimodal inputs,
  - optional scratchpad reads/writes.
- Separate the planning outputs from standard action-decoding assumptions in current StarVLA VLA heads.
- Represent algorithm-specific supervision clearly:
  - next node expansion,
  - queue updates,
  - delete-relaxation heuristic value or choice,
  - novelty-table decision,
  - planning-graph layer, mutex, or extraction step.

### Repo surfaces

- `starVLA/model/framework/`
- `starVLA/model/framework/share_tools.py`
- `starVLA/model/framework/base_framework.py`

### Deliverable

A trainable planner framework that can run one algorithm family under one modality condition end-to-end.

### Status update

Phase 4 remains not complete and not implemented by the Phase 1-3 closeout. No training, planner model, SFT, real VLM, GPU, API, or external-service result is claimed. No training, planner model, SFT, real VLM, GPU, API, or external-service result is claimed.

---

## Phase 5 - Scratchpad tool interface

### Objective

Implement the external memory condition required by the proposal.

### Main tasks

- Add a minimal scratchpad abstraction with operations equivalent to:
  - `read(slot)`
  - `write(slot, content)`
- Support the two proposal conditions:
  - **Tool-Template**: algorithm-specific required usage pattern,
  - **Tool-Learned**: optional later extension where usage is chosen by the model.
- Make tool state observable and logged for later analysis.
- Keep the tool memory implementation simple and deterministic at first; avoid building a general agent tool system.
- Treat context-window pressure as a first-class requirement for planning traces. For `blocksworld-train-medium-0011`, the final plan is only 10 actions, but raw traces are roughly 95k-108k estimated tokens for BFS, 32k-37k for FF-style, 461k-527k for Graphplan, and 2.57M-2.93M for IW(3). The memory path must keep frontier, visited, novelty, mutex, and planning-graph tables outside the LLM context and retrieve only the current path, selected candidates, and relevant facts for each decision.

### Repo surfaces

- likely a new planning-specific module under `starVLA/model/` or `examples/<planning-benchmark>/`
- `deployment/model_server/` only if evaluation needs remote stateful tool calls

### Deliverable

A working external-memory path that supports the proposal's Tool-Template condition for BFS, Fast Forward, Iterated Width, and Graphplan, with the strongest memory dependence expected for BFS, Iterated Width, and raw Graphplan layer/mutex traces.

---

## Phase 6 - Training recipes and experiment configs

### Objective

Turn the benchmark and planner into structured experiment runs.

### Main tasks

- Add training configs for the proposal matrix.
- Prioritize experiments exactly as proposed:
  - **P0**: Zero-shot diagnostic + BFS, Fast Forward, Iterated Width, Graphplan × 4 modalities × 3 seeds.
  - **P1**: Cross-task transfer after Blocksworld P0 is stable.
  - **P2/P3** only after P0 is stable.
- Keep configuration naming explicit so runs can be grouped by:
  - domain,
  - algorithm family,
  - modality condition,
  - seed,
  - tool condition.
- Reuse StarVLA training entrypoints where possible instead of forking new training loops prematurely.

### Repo surfaces

- `starVLA/config/training/`
- `starVLA/training/`
- `examples/<planning-benchmark>/train_files/`

### Deliverable

A reproducible config set that can launch the P0 matrix with minimal manual edits.

---

## Phase 7 - Evaluation, analysis, and diagnostics

### Objective

Measure the exact claims in the proposal rather than only training loss or task success.

### Main tasks

- Implement evaluation scripts for:
  - zero-shot diagnostic pass rates,
  - success rate,
  - sample efficiency,
  - length generalization,
  - compositional generalization,
  - process-level metrics tied to CRSH.
- Log proposal-specific diagnostics such as:
  - convergence-curve shape,
  - effective search depth,
  - queue correctness,
  - heuristic deviation,
  - novelty accuracy,
  - mutex quality,
  - scratchpad usage patterns,
  - failure-taxonomy labels (memory overflow, heuristic fixation, novelty collapse, constraint violation, exploration collapse).
- Build the final analysis outputs needed for the paper:
  - modality × algorithm summary tables,
  - Pareto frontier plots,
  - failure-mode breakdowns,
  - asymmetric repair analysis,
  - hard/soft-boundary decision summaries.

### Repo surfaces

- `examples/<planning-benchmark>/eval_files/`
- analysis scripts under `doc/`, `examples/`, or a dedicated research results folder

### Deliverable

A paper-aligned evaluation pipeline that can produce the core figures and tables for the proposal.

---

## Phase 8 - Cross-task transfer and broader extensions

### Objective

Generalize the initial implementation into the proposal's transfer story, then extend to broader domains only after the Blocksworld diagnostic core is stable.

### Main tasks

- After Blocksworld/Planimation P0 is stable, add the proposal's **cross-task transfer** stage:
  - FOLIO-style logical reasoning,
  - HumanEval/code-debugging style reasoning,
  - the selected third transfer task used in the proposal write-up.
- Freeze the trained planner when evaluating transfer so the implementation matches the Algorithmic Bias Transfer claim.
- Treat additional planning domains or continuous-world-model extensions as later follow-ons, not as part of the minimum proposal-aligned path.

### Deliverable

Cross-task transfer evidence for the paper's stronger claims, with broader domain extensions explicitly treated as follow-on work.

---

## Practical Build Order

To avoid getting stuck, implement in this order:

1. **One planning benchmark with one domain**.
2. **One zero-shot diagnostic packaging path**.
3. **One evaluation script for the diagnostic gate**.
4. Run the **zero-shot diagnostic** as a gate.
5. **One demonstration generator**.
6. **One planner framework**.
7. **One modality condition**.
8. **One algorithm family**.
9. Expand to the full **P0 matrix**.
10. Expand to **P1**, then optional **P2/P3**.

This order matters because it gets you to a runnable research loop quickly, instead of spending weeks on a fully general architecture before the first experiment works.

---

## Recommended First Milestone

The best first milestone for this repo is:

**Run Blocksworld with Planimation-based visual observations, validate the zero-shot diagnostic packaging, generate expert demonstrations for BFS / Fast Forward / Iterated Width / Graphplan, train a first planner under one modality condition, and evaluate basic success plus algorithm-state correctness.**

This milestone is strong because it tests the proposal's core logic while keeping scope controlled.

---

## Immediate Next Steps

If you start implementation now, the next concrete actions should be:

1. **Create a planning benchmark package under `examples/`** for Blocksworld as the first domain.
2. **Make Planimation endpoints configurable** in `modules/api-tools/planimation_api.py`.
3. **Define the zero-shot diagnostic prompt + JSON schema** so pre-SFT checks use the same task packaging as training/eval.
4. **Define the planning trajectory schema** for demonstrations and evaluation logs.
5. **Implement expert generators** for BFS, Fast Forward, Iterated Width, and Graphplan first.
6. **Register a new dataset path** through `starVLA/dataloader/`.
7. **Create a first planner framework/config pair** under `starVLA/model/framework/` and `starVLA/config/training/`.
8. **Build one evaluation script** that reports zero-shot diagnostic status, success, algorithm-state correctness, and scratchpad behavior.

---

## Success Criteria for the Research Infrastructure

You are ready to run the main study when the repo can do all of the following:

- launch one planning benchmark instance,
- emit visual and language views of the same task,
- run the zero-shot diagnostic with proposal-aligned outputs,
- generate expert traces for at least the P0 algorithms,
- train one planner variant using the existing StarVLA training stack,
- evaluate that planner with proposal-specific metrics,
- scale the same code path to modality sweeps and seed sweeps.

At that point, the codebase has moved from initialization-only to a true research platform for the proposal.
