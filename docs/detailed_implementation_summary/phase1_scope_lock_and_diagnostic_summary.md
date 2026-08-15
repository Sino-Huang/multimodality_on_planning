# Phase 1 Scope Lock and Diagnostic Summary

## Purpose

This artifact locks the Phase 1 through Phase 3 acceptance scope for the planning benchmark work. It turns the proposal and high level execution plan into explicit decisions that later benchmark, diagnostic, expert generation, modality serialization, and registry tasks can validate against.

Phase 1 is not marked complete by this artifact alone. Completion still depends on the later Blocksworld core and zero shot diagnostic tasks passing their own tests and evidence commands.

## Decision Artifact Index

### blocksworld_p0_scope_decision

The Phase 1 through Phase 3 P0 acceptance scope is `blocksworld` only. Blocksworld is the first runnable planning domain because it is the proposal's diagnostic anchor and already has Planimation rendering evidence in the repo.

The existing broader Planimation corpus remains future-compatible. The 15 domain curriculum and the larger all domain Planimation validation set can support later expansion, but support for those domains is not Phase 1-3 acceptance scope.

### algorithm_matrix_decision

The locked P0 algorithm set is:

- `bfs`, breadth first search with explicit frontier and visited state handling.
- `fast_forward`, greedy search guided by delete relaxation style heuristic state.
- `iterated_width`, novelty based structured exploration.
- `graphplan`, proposition layer and mutex based planning.

Additional planners, approximations, and external solver comparisons are out of scope for Phase 1 through Phase 3 acceptance unless a later task marks them as non P0 exploratory baselines.

### modality_matrix_decision

The locked P0 modality set is:

- `vision`, rendered observation only.
- `language`, symbolic or natural language state and goal text only.
- `vision_language`, rendered observation plus language state and goal text.
- `vision_language_tool`, rendered observation plus language text plus deterministic scratchpad state.

The modality boundary is part of the diagnostic design. Later serializers must avoid leaking language fields into `vision` examples or rendered frame fields into `language` examples.

### planimation_role_decision

Planimation is an offline rendering and visualization utility for this milestone. It may provide rendered frames, VFG traces, and visual audit artifacts, but it is not environment authority.

The environment authority for Phase 1 through Phase 3 is the local deterministic Blocksworld symbolic benchmark slice. Action legality, state transitions, goals, state IDs, and expert trajectory correctness must come from local symbolic code, not from human visual confirmation or hosted rendering behavior.

### frozen_world_model_decision

The frozen world model v0 is a deterministic symbolic representation. It consists of canonical objects, canonical atoms, legal actions, transitions, goals, state IDs, and optional render references.

No learned encoder is required for Phase 1 through Phase 3. A trainable or frozen neural encoder interface can be added later, but it is not required for the P0 Blocksworld closure and must not block the zero shot diagnostic gate.

### artifact_policy_decision

Small source files, fixtures, tests, decision artifacts, and JSON evidence files belong in the repo. Large generated data should stay under local artifact paths such as `.sisyphus/evidence/`, `outputs/planning_artifacts/`, or `data/planning_artifacts/` and should not be treated as committed source unless a later task explicitly asks for it.

Raw PDDL domain files, raw PDDL problem files, final plans, and Planimation traces alone do not count as expert demonstrations. Expert artifacts must include algorithm specific planner state annotations in later Phase 3 tasks.

### zero_shot_gate_decision

The zero shot diagnostic gate runs before any large supervised fine tuning run. It packages each `blocksworld` instance across every locked algorithm and modality pair and scores model output offline.

The go or no go criteria are:

1. The response is parseable JSON with the required fields.
2. The next action is legal in the current deterministic symbolic state.
3. The planner state update matches the target algorithm family, including FIFO frontier behavior for `bfs`, delete relaxation heuristic state for `fast_forward`, novelty state for `iterated_width`, and proposition layer or mutex state for `graphplan`.
4. Failure categories distinguish parse errors, action errors, and algorithmic fidelity errors.

The gate may report that the model lacks zero shot algorithmic knowledge, that the task is too easy, or that modality affordance differs by algorithm. Any of those outcomes can guide later work, but none should broaden Phase 1 through Phase 3 acceptance beyond Blocksworld P0.

## Current Status Boundary

This artifact only locks decisions and creates a machine checkable boundary. It does not implement the Blocksworld parser, transition system, benchmark loop, zero shot package builder, expert generators, modality serializers, StarVLA data registry, real VLM calls, GPU runs, or Phase 4 model training.

## Verification Command

Run the scope lock checker with:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.scope_lock validate --path doc/detailed_implementation_summary/phase1_scope_lock_and_diagnostic_summary.md --json
```

Expected result: exit code 0 and JSON containing `valid=true` and `required_decisions_present=true`.


## Task 11 closeout evidence links

Phase 1 is complete for the Blocksworld-only P0 closeout when read together with the local symbolic core and zero-shot diagnostic evidence. The scope remains narrow: deterministic symbolic world model v0 is the environment authority, Planimation is offline rendering and visualization only, and zero-shot diagnostic packaging/scoring is offline without real VLM, GPU, API, or external-service execution.

Evidence paths:

- `.sisyphus/evidence/phase1-3-task-1-scope-lock.json`
- `.sisyphus/evidence/phase1-3-task-1-scope-lock-error.txt`
- `.sisyphus/evidence/phase1-3-task-2-valid-instance.json`
- `.sisyphus/evidence/phase1-3-task-2-empty-goal-error.json`
- `.sisyphus/evidence/phase1-3-task-3-zero-shot-build.json`
- `.sisyphus/evidence/phase1-3-task-3-illegal-action.json`

Final closeout command:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.docs_check --phase 1 --json
```

Expected signal: exit code 0 and JSON with `valid=true` and `phase_results.1.valid=true`.
