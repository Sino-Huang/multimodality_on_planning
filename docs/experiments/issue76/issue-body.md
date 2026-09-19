**Parent:** #38

<!-- DEADLINE-SCOPE-V1 -->
This deadline scope supersedes the older full-matrix, five-seed and approval-manifest requirements for this ticket. Use one training/evaluation seed (17), retain raw evidence and never treat incomplete coverage as a completed experiment.

## Actual #75 handoff — supersedes assumed pilot completion

#75 completed the cost-ranked v5 run: 43,876 training records across four algorithms, two epochs, training seed 17, five evaluation seeds and 864 episodes in 76.23 hours. The four-hour visual pilot was not run. The retained scientific gate is VALID_STOP (BFWS 66.7% < 80%) with complete selected coverage. See `docs/experiments/issue75/v5-completion.md`.

Before new GPU launches or matched-modality claims, reconcile this executed training scope with the planned 512-record/one-epoch multimodal/text pilots. Do not compare them as a controlled modality effect; filtering evaluation to common tasks alone cannot repair the training mismatch. Preserve the existing future compute caps and checkpoints. Do not automatically expand to multi-day replication or repeat #75. If a matched comparison cannot fit, report separate feasibility evidence and limitations through #77/#100 instead.

## Reconciled execution: standalone multimodal feasibility

For this execution, retain the declared 512-record/one-epoch pilot and four-hour cap. Its comparison is **within multimodal-state**: pretrained base, process SFT, random-valid and exact-reference controls on identical inputs/tasks/budgets. The completed full-corpus/two-epoch visual v5 result is contextual evidence only; no controlled modality-effect claim is made. This reconciles scope without repeating #75 or silently enlarging #76. #77 will judge the evidence and remaining comparison limitations before any final evaluation.

The implementation uses `scripts/run_multimodal_issue76.py`, `configs/experiments/issue76/experiment.json`, and the unchanged shared pilot record/task manifest. Fresh multimodal hardware qualification runs eight largest/smallest input probes across four algorithms on each GPU. The largest retained multimodal input is 5,431 tokens. Both training and rollout/replay use the declared multimodal projection; complete images, facts, goals and Search Memory are retained. Progress and 20-second heartbeats are visible. Explicit MASTER_PORT values are 18675 and 18676.

## Deadline status
Required development evidence for the deadline go/no-go decision.

## Budget
4 hours wall-clock total on the two A100s.

## What to do
Execute the reconciled standalone multimodal feasibility protocol above, retaining the pilot membership and spending cap below.

## Acceptance criteria
- Reuse the shared pilot membership and 512-record/one-epoch training schedule; do not recollect scenes or create a larger corpus.
- Qualify only the bounded pilot input shapes, scalar/batch semantics and adapter isolation for the actual multimodal processor. Visual-only timing is not multimodal qualification.
- Run base, process SFT, random-valid and exact-reference conditions on the same 12 algorithm/task cases (48 episodes).
- Keep complete text-image semantic parity and independent episode replay. Preserve partial evidence if time expires.
- Run after #75 on the two A100s, or explicitly allocate disjoint resources and adjust the schedule; never overlap two workers per GPU.

## Blocked by
#74

## Scheduling
Use at most one model worker per GPU, with distinct MASTER_PORT values. The two-GPU #75/#76 and #93/#94/#95 jobs must be serialized on the available two A100s. Timeouts retain evidence and stop new work; no automatic budget extension or repeat-until-positive runs.

The deadline roadmap is documented in docs/experiments/deadline-plan/README.md. Terms retain their meanings from CONTEXT.md.
