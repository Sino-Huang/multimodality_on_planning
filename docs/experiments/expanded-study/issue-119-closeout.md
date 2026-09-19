# Issue #119 closeout (Goal 10)

Goal 10 asked whether staged, shuffled or mixed-order exposure changes
additive-greedy best-first performance differently across text, visual and
multimodal state inputs. The frozen `expanded-curriculum-v1` protocol required
the same 512 unique v5 records and targets in every cell, seed 17, one epoch,
16 optimizer updates, trainer reshuffling disabled and a fresh adapter from the
same base for each of the nine modality-by-ordering cells.

## Delivered

- Nine final adapters passed independent checkpoint and exposure verification.
  The training report records 512 records, 16 updates and 504/504 changed
  adapter tensors per cell, with identical record membership, exact frozen
  orders and identical fresh LoRA initialization across all cells.
- Fixed modality-matched evaluation completed 243/243 model episodes: 27 tasks
  x 3 modalities x 3 orderings. All 324/324 reused base, sequential-order SFT,
  random-valid and exact-reference comparator bindings were replay-verified
  against their audited Goal 3 provenance; no binding is missing.
- `audit-final` independently reconstructed the evidence and predeclared
  analysis and returned `PASS: 243/243 curriculum episodes replayed`.
- The whole-problem paired analysis ran as declared with seed 1729, 10,000
  bootstrap resamples, 95% confidence and materiality margin 0.05. Historical
  #67 remains separately reported under its unmatched schedule and was not
  pooled.

## Results

| Modality | Staged | Shuffled | Mixed order |
| --- | ---: | ---: | ---: |
| text-state | 24/27 | 24/27 | 25/27 |
| visual-state | 24/27 | 27/27 | 26/27 |
| multimodal-state | 25/27 | 27/27 | 27/27 |

Interaction contrasts are paired success-rate differences in percentage
points, shown as point estimate [95% interval]:

| Modality x ordering interaction | Point [95% interval], pp |
| --- | ---: |
| (visual staged-shuffled) - (text staged-shuffled) | -11.11 [-25.93, 3.70] |
| (multimodal staged-shuffled) - (text staged-shuffled) | -7.41 [-25.93, 7.41] |
| (visual mixed-shuffled) - (text mixed-shuffled) | -7.41 [-25.93, 11.11] |
| (multimodal mixed-shuffled) - (text mixed-shuffled) | -3.70 [-18.52, 11.11] |

All four interaction intervals include zero. Neither all curriculum arms nor
all comparator controls saturated; the predeclared conclusion is to interpret
the paired intervals rather than rank the point estimates.

## Attempt history

The ledger preserves every evaluation launch. For `curriculum-evaluate-0`,
attempt 1 failed on the curriculum-arm whitelist bug, attempt 2 reached its
wall-clock cap, attempt 3 failed retained-episode provenance validation with
zero new episodes, attempt 4 reached its cap at 160/162, and attempt 5 produced
the two missing episodes and succeeded. For `curriculum-evaluate-1`, attempt 1
failed on the same whitelist bug, attempt 2 reached its cap, attempt 3 failed on
the same provenance defect with zero new episodes, and attempt 4 succeeded.

The two code defects were fixed in `2946e18` (curriculum-arm behavior mapping)
and `8c95077` (policy-identity plus committed-lineage provenance). The three
wall-clock cutoffs retained their journals. Mixed-attempt evidence is bound per
episode to evaluate-0 attempts 2, 4 and 5 and evaluate-1 attempts 2 and 4; it
does not attribute retained episodes only to the final successful processes.

Gate 3 found that the original validator accepted any ancestor runtime head,
while cutoff attempts had no `worker-result.json` and the scheduler had not
persisted their launch head. Commit/launch ordering was used retrospectively to
reconcile and freeze the exact mapping:

| Job | Attempt | Required runtime head |
| --- | ---: | --- |
| curriculum-evaluate-0 | 2 | `2946e18465e7a7724c65e4e29caf21118cc76db6` |
| curriculum-evaluate-0 | 4 | `8c950773a63e29864ad6e684e40d9475f3fe3a1b` |
| curriculum-evaluate-0 | 5 | `8c950773a63e29864ad6e684e40d9475f3fe3a1b` |
| curriculum-evaluate-1 | 2 | `2946e18465e7a7724c65e4e29caf21118cc76db6` |
| curriculum-evaluate-1 | 4 | `8c950773a63e29864ad6e684e40d9475f3fe3a1b` |

The remediated validator requires exact mapped-head equality with no ancestor
fallback, and the scheduler records `launch_head` for future attempts. The
strict read-only audit still replayed all 243 frozen episodes successfully.

## Accounting

Training consumed 2.2241236 GPU-hours. Evaluation consumed 9.5544646 GPU-hours
across all failed, cutoff and successful launches on GPU 0 / port 18800 and GPU
1 / port 18801; the finalizer was CPU-only. Curriculum branch cumulative
consumption is 11.7785882 / 48 GPU-hours
(9.5544646 + 2.2241236 = 11.7785882).

## Limitations

- One training seed (17) was used per cell; no training-seed variance is
  claimed.
- The modality-matched design estimates ordering effects within modality and
  does not estimate cross-modality transfer.
- Several arms and controls reached 27/27, so the saturation analysis directs
  interpretation to paired intervals rather than point-estimate ranking.

## Evidence

- Frozen contract: [curriculum-protocol.json](../../../configs/experiments/expanded-study/curriculum-protocol.json)
- Training evidence: [curriculum-training.json](curriculum-training.json) and
  [curriculum-training.md](curriculum-training.md)
- Evaluation evidence: [curriculum-evaluation.json](curriculum-evaluation.json)
  and [curriculum-evaluation.md](curriculum-evaluation.md)
- Predeclared runtime analysis:
  `outputs/expanded-study/v1/curriculum/evaluation/analysis.json`
- Requirement audit: [goal10-completion-audit.json](goal10-completion-audit.json)

The experimental and audit deliverables of #119 are satisfied. Evidence comment
[`5715451375`](https://github.com/Sino-Huang/multimodality_on_planning/issues/119#issuecomment-5715451375)
and issue closure followed at HEAD `363169d`; this terminal-state amendment
follows that published record.
