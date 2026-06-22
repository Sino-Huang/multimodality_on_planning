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

- A **planning benchmark package** for the proposal domains.
- A **Planimation-aware environment adapter** integrated into the StarVLA workflow.
- A **data generation pipeline** for expert demonstrations across PDDL-native planners: BFS / DFS / Greedy / A* / Width-based / Planning Graph, with Partial Order Planning as a secondary extension.
- A **planner framework** that consumes the chosen modality inputs and optionally uses tool memory.
- A **scratchpad tool interface** (`read` / `write`) exposed to the planner.
- A **proposal-specific evaluation suite** for success rate, search quality, generalization, and Pareto analysis.

---

## High-Level Research Strategy

The cleanest path is to treat this project as a **new planning benchmark and planner extension on top of StarVLA**, not as a modification of StarVLA's existing robotics benchmarks.

In practice, that means:

1. build a new environment/data/eval slice for planning tasks,
2. reuse StarVLA's config, training, and checkpointing infrastructure,
3. keep Planimation as a visualization and environment-side utility rather than deeply coupling it into the model core,
4. introduce the research-specific planner variants as new frameworks or framework extensions,
5. stage the work so that the **P0 experiments** from the proposal become runnable first.

---

## Recommended Phases

## Phase 1 - Pre-flight validation and scope lock

### Objective

Confirm the research can be implemented in this repo without first solving unrelated architecture problems.

### Main tasks

- Decide the first domain to operationalize.
  - Recommended order: **Blocksworld/Planimation first**, then expand to additional domains.
- Decide whether Blocksworld is handled as:
  - a purely symbolic planning environment with rendered images added for vision input, or
  - a more general StarVLA-style embodied environment.
- Verify how Planimation will be used:
  - visualization only,
  - state rendering source,
  - or both.
- Fix the practical Planimation integration assumption early:
  - `modules/api-tools/planimation_api.py` currently points to localhost-style endpoints and should be made configurable before it is used in experiments.

### Deliverable

A frozen implementation scope for the first runnable benchmark and a written decision on domain representation, visualization source, and Planimation usage.

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

---

## Phase 3 - Data and demonstration generation

### Objective

Generate the supervised training data needed for algorithm-specific learning.

### Main tasks

- Implement expert trajectory generation for complementary algorithm families that directly consume ordinary IPC/classical PDDL tasks and cover four P0 paradigms:
  - blind state-space search: BFS and DFS,
  - heuristic state-space search: Greedy Best-First and A*,
  - novelty/width-based search: Width-based Search,
  - graph-structured planning: Planning Graph / Graphplan,
  - least-commitment plan-space reasoning: Partial Order Planning as a P1 extension.
- Exclude Hierarchical Subgoal Decomposition from the core set unless subgoals or decompositions are derived automatically from the PDDL task without extra annotations.
- Define a unified trajectory schema containing:
  - state or latent reference,
  - visual observation,
  - language description,
  - target planner decision,
  - optional queue/stack/heuristic/novelty/planning-graph/ordering-constraint state,
  - final plan metadata.
- Build separate serialization paths for the four modality conditions:
  - Vision-only,
  - Language-only,
  - Vision + Language,
  - Vision + Language + Tool.
- Add dataset registration so the new data can flow through `starVLA/dataloader/`.

### Repo surfaces

- `starVLA/dataloader/`
- `examples/<planning-benchmark>/train_files/data_registry/`
- new offline data generation scripts under the planning example package

### Deliverable

A reproducible demonstration-generation pipeline with enough data to train at least the P0 experiments.

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
  - queue/stack updates,
  - heuristic choice,
  - novelty-feature choice,
  - planning-graph level, mutex, or extraction step,
  - partial-order causal-link or ordering update.

### Repo surfaces

- `starVLA/model/framework/`
- `starVLA/model/framework/share_tools.py`
- `starVLA/model/framework/base_framework.py`

### Deliverable

A trainable planner framework that can run one algorithm family under one modality condition end-to-end.

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

### Repo surfaces

- likely a new planning-specific module under `starVLA/model/` or `examples/<planning-benchmark>/`
- `deployment/model_server/` only if evaluation needs remote stateful tool calls

### Deliverable

A working external-memory path that supports at least BFS, DFS, A*, Width-based Search, and Planning Graph / Graphplan in the Tool-Template setting, with Partial Order Planning support treated as a secondary extension.

---

## Phase 6 - Training recipes and experiment configs

### Objective

Turn the benchmark and planner into structured experiment runs.

### Main tasks

- Add training configs for the proposal matrix.
- Prioritize experiments exactly as proposed:
  - **P0**: BFS/DFS, Greedy/A*, Width-based, Planning Graph × 4 modalities × 3 seeds.
  - **P1**: Partial Order Planning × 4 modalities × 3 seeds after linear trajectory extraction is stable.
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
  - success rate,
  - sample efficiency,
  - length generalization,
  - compositional generalization,
  - search efficiency,
  - robustness.
- Log proposal-specific diagnostics such as:
  - nodes expanded,
  - queue/stack correctness,
  - optimality gap,
  - planning-graph level/mutex quality,
  - scratchpad usage patterns.
- Build the final analysis outputs needed for the paper:
  - modality × algorithm summary tables,
  - Pareto frontier plots,
  - failure-mode breakdowns,
  - asymmetric repair analysis.

### Repo surfaces

- `examples/<planning-benchmark>/eval_files/`
- analysis scripts under `doc/`, `examples/`, or a dedicated research results folder

### Deliverable

A paper-aligned evaluation pipeline that can produce the core figures and tables for the proposal.

---

## Phase 8 - Expansion beyond the first benchmark

### Objective

Generalize the initial implementation into the full cross-domain story described in the proposal.

### Main tasks

- After Blocksworld/Planimation is stable, add the next domains from the proposal.
- Decide how frozen world-model support differs by domain:
  - discrete symbolic domain,
  - continuous visual/control domain.
- Only then extend the benchmark matrix to test whether the observed affordance pattern transfers across domains.

### Deliverable

Multi-domain evidence for the paper's stronger claims, rather than a single-domain proof of concept.

---

## Practical Build Order

To avoid getting stuck, implement in this order:

1. **One planning benchmark with one domain**.
2. **One demonstration generator**.
3. **One planner framework**.
4. **One modality condition**.
5. **One algorithm family**.
6. **One evaluation script**.
7. Expand to the full **P0 matrix**.
8. Expand to **P1**, then optional **P2/P3**.

This order matters because it gets you to a runnable research loop quickly, instead of spending weeks on a fully general architecture before the first experiment works.

---

## Recommended First Milestone

The best first milestone for this repo is:

**Run Blocksworld with Planimation-based visual observations, generate expert demonstrations for BFS / Greedy / A* / Width-based / Planning Graph, train a first planner under one modality condition, and evaluate basic success plus trajectory correctness.**

This milestone is strong because it tests the proposal's core logic while keeping scope controlled.

---

## Immediate Next Steps

If you start implementation now, the next concrete actions should be:

1. **Create a planning benchmark package under `examples/`** for the first domain.
2. **Make Planimation endpoints configurable** in `modules/api-tools/planimation_api.py`.
3. **Define the planning trajectory schema** for demonstrations and evaluation logs.
4. **Implement expert generators** for the P0 algorithms first.
5. **Register a new dataset path** through `starVLA/dataloader/`.
6. **Create a first planner framework/config pair** under `starVLA/model/framework/` and `starVLA/config/training/`.
7. **Build one evaluation script** that reports success, plan quality, and scratchpad behavior.

---

## Success Criteria for the Research Infrastructure

You are ready to run the main study when the repo can do all of the following:

- launch one planning benchmark instance,
- emit visual and language views of the same task,
- generate expert traces for at least the P0 algorithms,
- train one planner variant using the existing StarVLA training stack,
- evaluate that planner with proposal-specific metrics,
- scale the same code path to modality sweeps and seed sweeps.

At that point, the codebase has moved from initialization-only to a true research platform for the proposal.
