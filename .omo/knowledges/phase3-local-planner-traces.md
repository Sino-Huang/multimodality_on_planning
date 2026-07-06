# Phase 3 Local Planner Traces

Phase 3 supervised data generation lives under `scripts/phase3`. The pipeline uses `scripts/phase3/pddl.py` for lightweight STRIPS parsing/grounding/replay and `scripts/phase3/pipeline.py` for corpus generation.

Local non-BFS trace generation is implemented in `scripts/phase3/local_planners.py`, with Graphplan-specific code in `scripts/phase3/local_graphplan.py` and shared dataclasses/types in `scripts/phase3/local_planner_types.py`. `_attempt_planner` probes configured external planners first; successful external plans are labeled `success_plan_replayed`, while local Python trace generation is used when external modules are unavailable or do not produce a replayable plan. It supports deterministic small-instance traces for:

- `ff`: FF-style/local delete-relaxation approximation using relaxed heuristic metadata and bounded best-first recovery when greedy successor choice dead-ends. It remains `is_exact_fast_downward_ff = false`.
- `iw`: configurable IW(k) novelty search events. The default is IW(3) with `local_iw_max_width=3`, which lets `blocksworld-train-medium-0011` emit a replay-valid local trace without per-run IW overrides.
- `graphplan`: proposition/action planning graph layers, action mutex pairs, action-mutex-only extraction metadata, and a replay-validated serial extraction plan.

Generation refuses unsafe output roots before recursive cleanup. Allowed generated-output parents are repo-local `data/`, `outputs/`, and `tmp/`; the allowlist roots themselves, input root, any output root that contains the input root, repository root, current directory, home, filesystem root, and paths outside the allowlist are rejected.

Primary verification command:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3 tests/planning_benchmark tests/data_collect
```

Latest post-refactor verification signal: `pytest tests/phase3` passed 39 tests, and `pytest tests/phase3 tests/planning_benchmark tests/data_collect` passed 168 tests. Small CLI smoke over blocksworld/ferry/gripper produced 7 replay-validated `success_full_trace` examples from 12 planner attempts with zero schema, replay, or fidelity verifier failures.

Review follow-up fixes: IW expands the root even when the initial atom set is empty, enforces `max_plan_length`, and enforces `local_max_applicable_actions`. Generated examples and replay diagnostics now record/use merged generation limits, and oversized-example skips reset attempt metadata to a non-success shape.

Implementation summaries: `doc/detailed_implementation_summary/phase3_local_planner_trace_generation_summary.md` and `doc/detailed_implementation_summary/phase3_blocksworld_medium_0011_local_trace_recovery.md`.
