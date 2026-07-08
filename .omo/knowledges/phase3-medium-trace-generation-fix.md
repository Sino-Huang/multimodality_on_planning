# Phase 3 Medium Trace Generation Fix

Date: 2026-07-06

Update 2026-07-07: active Phase 3 search now uses `gbfs` instead of `bfs`. Historical notes below describe the original BFS-era fix, but current commands and all-four planner sets should use `gbfs ff iw graphplan`; old `bfs` planner selection is rejected rather than aliased.

## Problem

Medium Phase 3 instances could still fail to emit replay-valid traces for all four local planners. A one-dev-medium-per-domain probe showed existing 4/4 success for blocksworld, elevators, ferry, and towers_of_hanoi, but gripper, visitall, logistics, and several other domains timed out or skipped.

## Root Causes

- BFS pre-gate rejected supported medium tasks with many goals even when grounding was small.
- Untyped STRIPS domains over-grounded parameters because static unary sort predicates were not used as parameter domains.
- Grounding kept actions whose substituted static binary preconditions were false, such as impossible VisitAll `connected` moves.
- Blind BFS/serial extraction is too expensive for medium transportation-style tasks even after grounding is corrected.

## Changes

- `scripts/phase3/pddl.py` narrows untyped parameters with static unary predicates and skips grounded actions with false static preconditions.
- Historical BFS-era note: `scripts/phase3/pipeline.py` used the corrected grounded-action estimate for the BFS pre-gate. Current active Phase 3 uses `gbfs_estimate_exceeds_resource_gate()` and `is_exact_gbfs: false` recovery metadata.
- `scripts/phase3/local_goal_regression.py` adds bounded goal-regression recovery, including a VisitAll path extractor.
- GBFS, FF-style, IW, and Graphplan call recovery only as an honest non-exact recovery path, with metadata such as `is_exact_gbfs: false`, `is_exact_search_algorithm: false`, `is_exact_iw: false`, or `is_exact_graphplan_extraction: false`.
- `scripts/phase3/generate_curriculum_trace_dataset.py` exposes `--local-goal-regression-goal-threshold` and `--local-goal-regression-max-attempts`.

## Verification

RED evidence:

```bash
source ~/cd_vlaplan && source .venv/bin/activate
pytest tests/phase3/test_phase3_medium_trace_targets.py -q
```

Earlier failures included `visitall-dev-medium-0000` BFS gate returning true despite small grounding, `gripper-dev-medium-0000` grounding 28,224 actions instead of 164, and gripper pipeline defaults returning `skipped_resource_limit` for all four planners.

GREEN evidence:

```bash
source ~/cd_vlaplan && source .venv/bin/activate
pytest tests/phase3/test_phase3_medium_trace_targets.py -q
```

Result: `6 passed`.

Real CLI surface:

```bash
source ~/cd_vlaplan && source .venv/bin/activate
timeout 600s python scripts/phase3/generate_curriculum_trace_dataset.py \
  --input-root tmp/phase3_medium_trace_targets_input \
  --planner gbfs --planner ff --planner iw --planner graphplan \
  --output-root tmp/phase3_medium_trace_targets_cli_verify \
  --quiet
```

Result: `attempt_status_summary: {"success_full_trace": 16}`, `extracted_trace_count: 16` for `blocksworld-train-medium-0011`, `gripper-dev-medium-0000`, `logistics-dev-medium-0000`, and `visitall-dev-medium-0000`.

Validators must be run with `python -m`:

```bash
python -m scripts.phase3.verify_planner_attempts --accepted-manifest tmp/phase3_medium_trace_targets_input/accepted_manifest.jsonl --planner-attempts tmp/phase3_medium_trace_targets_cli_verify/diagnostics/planner_attempts.jsonl --planners gbfs ff iw graphplan
python -m scripts.phase3.verify_replay_validated_examples --dataset-root tmp/phase3_medium_trace_targets_cli_verify
python -m scripts.phase3.verify_fidelity_labels --dataset-root tmp/phase3_medium_trace_targets_cli_verify
```

Results: missing attempts `0`, failed replay examples `0`, invalid fidelity labels `0`.

## Caveats

- This improves representative supported medium cases; it is not an exhaustive guarantee for all 1,961 accepted medium instances.
- `snake` and `sokoban` remain skipped by unsupported PDDL features.
- `15puzzle`, `depot`, `driverlog`, `freecell`, `grid`, and `storage` still need separate lifted/search improvements for broad medium completion.
- Recovery traces are replay-valid but are marked as non-exact for the nominal search algorithm when recovery is used.
