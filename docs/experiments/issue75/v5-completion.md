# Issue 75: completed visual development experiment

The operator completed `issue-75-visual-development-32k-v5/attempt-001` in
274,431.03 seconds (**76.23 hours**). All four training runs and all **864**
selected episodes finished. The experiment's frozen performance gate returned
**VALID_STOP**, with `scientific_completion: false`. The failure is BFWS learned
success of **66.7%**, below the required **80%**; it is not incomplete coverage,
a GPU timeout, or a reason to repeat training until successful.

## Actual executed scope

The original v5 command was already running when the deadline pilot was prepared.
The operator continued it rather than switching. This completed experiment used
43,876 training records across four algorithms, two epochs, one training seed
(17), and five evaluation seeds (17, 29, 43, 71, 101). Exact reference runs use
seed 17 only. Four final adapters are retained. The evaluation panel contains
42 task groups and 54 algorithm/task cases selected by cost before learned
outcomes. The selected scope excludes 55 of the 97 development task groups.

The 512-record/one-epoch/four-hour pilot was **not executed**. Issue closure records
completion of the actual v5 experiment and its mixed results. It does not assert
compliance with the later pilot budget, change the frozen thresholds, or turn the
retained VALID_STOP into PASS.

## Results

| Algorithm | SFT success | Random-valid success | Base success | SFT invalid-operation rate |
| --- | ---: | ---: | ---: | ---: |
| BFS | 100% (75/75) | 70.7% (53/75) | 0% | 0% |
| BFWS | 66.7% (50/75) | 52.0% (39/75) | 0% | 0.443% |
| Additive w3 | 100% (60/60) | 100% (60/60) | 0% | 0% |
| Additive greedy | 100% (60/60) | 100% (60/60) | 0% | 0% |

Exact references succeed on all 54/54 cases. There are 54 exact-reference,
270 random-valid, 270 pretrained-base and 270 SFT episodes. Base invalid-operation
rate is 100% under this protocol; the comparison includes output-format and
operation compliance, not just abstract planning ability.

The saved whole-problem-instance bootstrap lower bound on gain over the best
control is +14.7 percentage points for BFS, -14.7 for BFWS, and zero for each
additive setting. BFS is the only algorithm with a positive bound in this selected
development panel. Additive controls saturate, so 100% learned success there is
not evidence of an advantage. Repeated evaluation seeds are not independent
training replicates; do not claim training-seed variance or held-out generalization.

## Evidence and verification

All paths below are relative to the repository:

- Run: `outputs/visual_development/issue75-32k-v5/attempt-001/`.
- Frozen settings and task panel: `attempt.json`.
- Reused passed hardware qualification: `qualification.json`.
- Training outcomes and final adapter paths: `training.json`.
- Complete reference and model episode manifests: `references.json`, `evaluation.json`.
- Complete replay and metrics: `adjudicate.json` (864 episodes, complete selected coverage).
- Preserved final gate receipt: `result.json` (VALID_STOP).
- Independent closure audit: `docs/experiments/issue75/v5-completion-verification.json`.

The closure audit checks frozen settings, qualification provenance, all four
final adapter files, exact condition/task/seed coverage, independently replays
all 864 episodes with read-only views, and compares the recomputed adjudication
with every field of the saved report. It launches no model calls and does not
rewrite the original attempt. Worker logs retain progress and trained-adapter
qualification checks for both GPUs; MASTER_PORT mappings are 18575 and 18576.

Memory figures in reused qualification are calibration measurements, not a
whole-run v5 peak. The saved stage reports do not contain an aggregate v5 peak
memory statistic, so that measurement is unavailable. Do not substitute the
qualification peak or intermittent nvidia-smi snapshots for it.

## Handoff

No additional #75 training or evaluation is required to document this completed
experiment. Preserve all final adapters and negative findings. The saved
`scientific_completion: false` remains authoritative for the frozen gate.

#76 and #77 must reconcile the executed full-corpus/two-epoch schedule with the
planned 512-record/one-epoch multimodal pilot before making matched-modality claims.
Evaluating the v5 adapters on fewer common tasks would not remove that training
mismatch. Keep downstream spending caps; do not automatically launch a multi-day
multimodal replication or retrain visual adapters. #77 can use this evidence for
its go/no-go analysis, including the failed BFWS threshold and saturated additive
controls. #90/#93–#95 must inherit the reconciled protocol before final comparisons.
Neither #76 nor final evaluation, DAgger, replication or transfer is complete here.
