# Phase 3 Medium Trace Generation Fix

## Summary

Phase 3 medium trace generation now handles additional supported medium cases that previously timed out or skipped before producing valid traces. The original BFS-era fix targeted three root causes: overly conservative BFS pre-gating, over-grounding in untyped STRIPS domains, and blind search explosion in medium transportation-style tasks. As of the 2026-07-07 GBFS replacement, active all-four runs use `gbfs`, `ff`, `iw`, and `graphplan`; old `bfs` selection is rejected rather than aliased.

## Implementation

`scripts/phase3/pddl.py` now uses static unary predicates as parameter-domain constraints for untyped domains. It also prunes grounded actions when substituted static preconditions are false in the initial state. This reduces gripper from 28,224 grounded actions to 164 and visitall from 625 all-pair moves to 80 valid connected moves.

Current `scripts/phase3/pipeline.py` uses the corrected grounded-action estimate through `gbfs_estimate_exceeds_resource_gate()` before full grounding. GBFS can also use bounded goal-regression recovery after exact GBFS is skipped or exhausted, and the trace metadata marks that recovery as non-exact GBFS with `is_exact_gbfs: false`.

`scripts/phase3/local_goal_regression.py` adds a bounded goal-regression recovery planner. It supports transportation-style goal achievement and a VisitAll path extractor. FF-style, IW, and Graphplan use this only as a recovery path and record non-exact metadata.

`scripts/phase3/generate_curriculum_trace_dataset.py` exposes the new recovery controls:

```bash
--local-goal-regression-goal-threshold
--local-goal-regression-max-attempts
```

## Test Coverage

Added `tests/phase3/test_phase3_medium_trace_targets.py` covering:

- `visitall-dev-medium-0000` corrected grounding and active GBFS gate behavior.
- `gripper-dev-medium-0000` static unary grounding and replay validity.
- Pipeline default all-four planner success for `gripper-dev-medium-0000`.
- Pipeline default all-four planner success for `visitall-dev-medium-0000`.
- Pipeline default all-four planner success for `logistics-dev-medium-0000`.

## Verification Commands

Focused medium suite:

```bash
source ~/cd_vlaplan && source .venv/bin/activate
pytest tests/phase3/test_phase3_medium_trace_targets.py -q
```

Expected signal: `6 passed`.

Real CLI matrix:

```bash
source ~/cd_vlaplan && source .venv/bin/activate
timeout 600s python scripts/phase3/generate_curriculum_trace_dataset.py \
  --input-root tmp/phase3_medium_trace_targets_input \
  --planner gbfs --planner ff --planner iw --planner graphplan \
  --output-root tmp/phase3_medium_trace_targets_cli_verify \
  --quiet
```

Expected signal: `success_full_trace` is `16` and `extracted_trace_count` is `16`.

Validators:

```bash
source ~/cd_vlaplan && source .venv/bin/activate
python -m scripts.phase3.verify_planner_attempts --accepted-manifest tmp/phase3_medium_trace_targets_input/accepted_manifest.jsonl --planner-attempts tmp/phase3_medium_trace_targets_cli_verify/diagnostics/planner_attempts.jsonl --planners gbfs ff iw graphplan
python -m scripts.phase3.verify_replay_validated_examples --dataset-root tmp/phase3_medium_trace_targets_cli_verify
python -m scripts.phase3.verify_fidelity_labels --dataset-root tmp/phase3_medium_trace_targets_cli_verify
```

Expected signals: missing attempts `0`, failed replay examples `0`, invalid fidelity labels `0`.

## Caveats

This is not a complete solution for all medium instances. A one-dev-medium-per-domain probe after the fix showed all-four success for blocksworld, elevators, ferry, gripper, logistics, towers_of_hanoi, and visitall. `snake` and `sokoban` remain unsupported by the current PDDL parser. `15puzzle`, depot, driverlog, freecell, grid, and storage still require additional lifted planning, domain heuristics, or stronger search to avoid timeouts broadly.
