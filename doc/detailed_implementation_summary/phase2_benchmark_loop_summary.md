# Phase 2 Benchmark Loop Summary

## Decision

Phase 2 uses a direct Python benchmark loop for P0 Blocksworld evaluation. There is no WebSocket, server/client split, model server integration, GPU call, external API call, or StarVLA deployment server requirement for this milestone.

The loop in `examples/planning_benchmark_slice/benchmark_loop.py` treats the canonical symbolic Blocksworld core as the environment authority. It validates a fixture with `validate_fixture`, reloads it with `load_fixture`, parses it with `parse_blocksworld`, and uses `BlocksworldProblem.legal_actions()` plus `BlocksworldProblem.transition()` for all action checks and state transitions.

## Implemented Surface

- `BlocksworldBenchmarkLoop.reset()` restores the validated initial state and clears logs.
- `BlocksworldBenchmarkLoop.observe()` emits `planning_benchmark_observation_v1` with current state atoms, state ID, goal atoms, legal actions, terminal goal status, fixture path, and instance ID.
- `BlocksworldBenchmarkLoop.step(action)` checks the action against the current legal-action set, transitions state, stops on goal or max steps, and records a step log.
- `run-oracle` uses deterministic local BFS over the same legal actions and transition function to select the next baseline action.
- `run-scripted` executes a JSON action sequence and returns structured `illegal_action` failures without tracebacks.

Each step log records the observation, selected action, pre-state ID, post-state ID, post-state atoms, legal-action check, and terminal status.

## Verification Commands

Targeted tests:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/planning_benchmark/test_benchmark_loop.py -q
```

Expected signal: all benchmark loop tests pass.

Oracle smoke evidence:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.benchmark_loop run-oracle --fixture tests/fixtures/planning/blocksworld_nontrivial.json --max-steps 20 --json > .sisyphus/evidence/phase1-3-task-4-oracle-loop.json
```

Expected signal: exit code 0, `solved=true`, `illegal_action_count=0`, and `steps=2` for the committed non-trivial fixture.

Invalid scripted-action evidence:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.benchmark_loop run-scripted --fixture tests/fixtures/planning/blocksworld_nontrivial.json --actions tests/fixtures/planning/actions_invalid.json --json > .sisyphus/evidence/phase1-3-task-4-invalid-action.json
```

Expected signal: nonzero exit code, JSON stdout with `error.code="illegal_action"`, concise stderr, and no Python traceback.

## Boundary

This task intentionally does not implement trajectory schemas, expert generators, modality serializers, registry integration, full StarVLA evaluation serving, WebSockets, real VLM calls, GPUs, or Phase 4 training. Those remain later tasks in the Phase 1-3 closure plan.


## Task 11 closeout evidence links

Phase 2 is complete for the Blocksworld-only P0 closeout through the direct Python benchmark loop. The direct Python loop is the required P0 path. WebSocket serving, server-client evaluation, StarVLA deployment serving, GPUs, real VLM calls, and Phase 4 model training remain outside this phase.

Evidence paths:

- `.sisyphus/evidence/phase1-3-task-4-oracle-loop.json`
- `.sisyphus/evidence/phase1-3-task-4-invalid-action.json`

Final closeout command:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.docs_check --phase 2 --json
```

Expected signal: exit code 0 and JSON with `valid=true` and `phase_results.2.valid=true`.
