# Phase 3 output dataset audit - 2026-07-09

Audit scope: non-deprecated roots under `outputs/`; explicitly ignored `outputs/deprecated/` and any `deprecat*` folders.

Environment used for audit commands:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && <command>
```

Audited dataset roots:

- `outputs/phase3_curriculum_traces_safe_no_visitall_20260708_122431`
- `outputs/phase3_curriculum_traces_15puzzle_easy_20260709_002417`
- `outputs/phase3_curriculum_traces_visitall_20260708_191916`

Aggregate inventory across the three roots:

- Raw emitted examples: 6,197
- Unique emitted examples: 6,197
- Duplicate examples: 0
- Split totals: `train=5,135`, `dev=630`, `test=432`
- Planner totals: `gbfs=1,634`, `ff=1,533`, `iw=1,533`, `graphplan=1,497`

Domain totals:

- `15puzzle`: 688 examples from 172 unique solved instances, all 4 planners per instance
- `blocksworld`: 1,214 examples from 388 unique solved instances; 252 instances have all 4 planners, 35 have 3, 101 have only 1
- `elevators`: 752 examples from 188 unique solved instances, all 4 planners per instance
- `ferry`: 752 examples from 188 unique solved instances, all 4 planners per instance
- `gripper`: 708 examples from 177 unique solved instances, all 4 planners per instance
- `logistics`: 1,300 examples from 325 unique solved instances, all 4 planners per instance
- `towers_of_hanoi`: 708 examples from 177 unique solved instances, all 4 planners per instance
- `visitall`: 75 examples from 19 unique solved instances; 18 instances have all 4 planners, 1 has 3

Important split imbalance:

- `visitall` emitted examples only in `dev` (`dev=75`, `train=0`, `test=0`).
- `visitall` was not absent by configuration: instance accounting selected train/dev/test easy+medium instances, but attempts mostly hit resource limits.
- `blocksworld` and `logistics` dominate the safe corpus by count.

Per-root validator results:

```bash
python -m scripts.phase3.verify_replay_validated_examples --dataset-root outputs/phase3_curriculum_traces_safe_no_visitall_20260708_122431
python -m scripts.phase3.verify_fidelity_labels --dataset-root outputs/phase3_curriculum_traces_safe_no_visitall_20260708_122431
```

Result: `examples_checked=5434`, `examples_with_failed_replay=0`, `examples_without_replay_validation=0`, `invalid_external_full_trace_labels=0`.

```bash
python -m scripts.phase3.verify_replay_validated_examples --dataset-root outputs/phase3_curriculum_traces_15puzzle_easy_20260709_002417
python -m scripts.phase3.verify_fidelity_labels --dataset-root outputs/phase3_curriculum_traces_15puzzle_easy_20260709_002417
```

Result: `examples_checked=688`, `examples_with_failed_replay=0`, `examples_without_replay_validation=0`, `invalid_external_full_trace_labels=0`.

```bash
python -m scripts.phase3.verify_replay_validated_examples --dataset-root outputs/phase3_curriculum_traces_visitall_20260708_191916
python -m scripts.phase3.verify_fidelity_labels --dataset-root outputs/phase3_curriculum_traces_visitall_20260708_191916
```

Result: `examples_checked=75`, `examples_with_failed_replay=0`, `examples_without_replay_validation=0`, `invalid_external_full_trace_labels=0`.

Trace-size risk across unique examples, measured as JSON chars of `supervised_target.planner_trace`:

- Overall: `p50=120,834`, `p90=1,090,109`, `p95=1,677,594`, `p99=3,522,729`, `max=8,702,382`
- Large examples: `>100k=3,450`, `>500k=1,185`, `>1M=659`, `>2M=205`, `>5M=17`
- Largest-risk domains/planners: `visitall` has `p50=843,192`, `p90=6,944,893`, `max=7,873,207`; `ferry` max is `8,702,382`; `ff` and `iw` have the largest maxima.

Recommendation:

- The data is enough for first-round supervised experiments if the initial goal is to test Phase 3 reasoning-trace training on replay-valid examples from safe/easy domains.
- Do not run another broad collection pass yet. Move to curation/merge/filtering and run a training smoke or pilot first.
- Treat `visitall` as separate/diagnostic, not as a normal trainable domain in the main corpus, because it has only 75 emitted examples, all in `dev`, with most train/test attempts skipped by resource limits.
- Add trace-size filtering or bucketing before training. A raw full-trace corpus includes hundreds of >1M-char traces and some >5M-char traces, which are likely to stress tokenization, context windows, memory, and dataloader throughput.
- If more collection is needed later, collect targeted data only: underrepresented safe-domain/planner gaps or a deliberately smaller/easier `visitall` configuration. Avoid hard broad-domain collection until pilot training shows a clear data gap.

Update after `visitall` long-timeout recollection on 2026-07-10:

- New root: `outputs/phase3_curriculum_traces_visitall_train_test_long_timeout_20260710_000503`
- New root examples: 619 total, `train=555`, `test=64`, `dev=0`
- New root planner counts: `ff=155`, `gbfs=155`, `iw=155`, `graphplan=154`
- New root unique instances: 155; planner coverage per instance: 154 with 4 planners, 1 with 3 planners
- New root attempt statuses: `success_full_trace=619`, `skipped_resource_limit=37`, `failed_planner_timeout=8`, `failed_no_plan_extracted=4`
- New root validation: `examples_checked=619`, `examples_with_failed_replay=0`, `examples_without_replay_validation=0`, `invalid_external_full_trace_labels=0`

Updated aggregate across non-deprecated output roots:

- Roots: previous three roots plus `phase3_curriculum_traces_visitall_train_test_long_timeout_20260710_000503`
- Raw/unique examples: 6,816 / 6,816; duplicates: 0
- Split totals: `train=5,690`, `dev=630`, `test=496`
- Planner totals: `gbfs=1,789`, `ff=1,688`, `iw=1,688`, `graphplan=1,651`
- `visitall` now has 694 examples: `train=555`, `dev=75`, `test=64`
- `visitall` planner counts: `ff=174`, `gbfs=174`, `iw=174`, `graphplan=172`
- `visitall` unique solved instances: 174; 172 with all 4 planners, 2 with 3 planners

Frame/render readiness for planimation pairing:

- Checked 1,970 `instance_accounting` rows across the four non-deprecated roots.
- Missing render/frame paths: 0.
- All emitted examples have `vision_supervision_available=true`.
- Accounting `vision_status` is `vision_available_unaligned` for all selected instances.
- Frame counts are mostly 4, but some safe-domain selected instances have 1 or 3 frames: blocksworld has 96 one-frame and 84 three-frame emitted examples; ferry has 64 one-frame examples; logistics has 96 one-frame examples. `visitall` has 4 frames for all 694 examples.
- Because Planimation rendering currently captures a bounded frame window, frame counts do not generally match full plan length. Pairing is ready at the artifact-link level, but full step-by-step visual supervision may require rerendering with a larger `stop_step` or a per-plan render window.

Updated recommendation:

- Move on from data collection to the planimation-frame pairing phase.
- Keep trace-size controls in the pairing/training pipeline: updated full corpus has `p95=1,870,191` trace JSON chars, `p99=6,995,722`, `90` examples above 5M chars, and `1` above 10M chars.
