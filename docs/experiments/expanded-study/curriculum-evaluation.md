# Curriculum-by-modality held-out evaluation closeout (#119, Goal 10)

Goal 10 Phase 3/4 evaluated the frozen nine-cell curriculum matrix on the same
3 development and 24 unseen tasks used by the expanded study. Evaluation was
modality-matched: each trained arm ran only in its own modality. Complete model
coverage is therefore 27 tasks x 3 modalities x 3 orderings = 243 episodes;
all 243 episodes and all 324 comparator bindings are present, with zero missing
bindings. The finalizer-produced evidence and predeclared analysis both report
`PASS` (`expanded_curriculum_evaluation_evidence_v1` and
`expanded_curriculum_analysis_v1`).

Published evidence: [curriculum-evaluation.json](curriculum-evaluation.json) is
a byte-identical copy of the frozen runtime artifact
`outputs/expanded-study/v1/curriculum/evaluation/evidence.json` (sha256
`7c587d19bc252cdc4ad4ae4e65600fa1dbf238d3fd07122c5d69d950f7335a85`).
Episode journals and replay records follow the repository's local outputs
convention and are not Git assets.

## Results

The predeclared whole-problem paired analysis contains 27 units. Success means
goal reached with algorithm invariants holding.

| Modality | Staged | Shuffled | Mixed order |
| --- | ---: | ---: | ---: |
| text-state | 24/27 | 24/27 | 25/27 |
| visual-state | 24/27 | 27/27 | 26/27 |
| multimodal-state | 25/27 | 27/27 | 27/27 |

The following are paired success-rate contrasts in percentage points, shown as
point estimate [95% bootstrap interval]. The frozen procedure used seed 1729,
10,000 paired resamples, 95% confidence and a materiality margin of 5 percentage
points.

| Modality | Staged - shuffled | Mixed - shuffled | Staged - mixed |
| --- | ---: | ---: | ---: |
| text-state | 0.00 [-11.11, 11.11] | 3.70 [-11.11, 18.52] | -3.70 [-18.52, 11.11] |
| visual-state | -11.11 [-25.93, 0.00] | -3.70 [-11.11, 0.00] | -7.41 [-22.22, 7.41] |
| multimodal-state | -7.41 [-18.52, 0.00] | 0.00 [0.00, 0.00] | -7.41 [-18.52, 0.00] |

| Ordering | Visual - text | Multimodal - text | Multimodal - visual |
| --- | ---: | ---: | ---: |
| staged | 0.00 [-14.81, 14.81] | 3.70 [-7.41, 14.81] | 3.70 [-11.11, 18.52] |
| shuffled | 11.11 [0.00, 25.93] | 11.11 [0.00, 25.93] | 0.00 [0.00, 0.00] |
| mixed order | 3.70 [-7.41, 14.81] | 7.41 [0.00, 18.52] | 3.70 [0.00, 11.11] |

| Modality x ordering interaction contrast | Point [95% interval], pp |
| --- | ---: |
| (visual staged-shuffled) - (text staged-shuffled) | -11.11 [-25.93, 3.70] |
| (multimodal staged-shuffled) - (text staged-shuffled) | -7.41 [-25.93, 7.41] |
| (visual mixed-shuffled) - (text mixed-shuffled) | -7.41 [-25.93, 11.11] |
| (multimodal mixed-shuffled) - (text mixed-shuffled) | -3.70 [-18.52, 11.11] |

All four predeclared interaction intervals include zero. With only 27 paired
units, the report retains the intervals rather than claiming an interaction
from the point estimates.

The four modality-matched controls were reused, not rerun:

| Modality | Base | SFT sequential-order | Random-valid | Exact-reference |
| --- | ---: | ---: | ---: | ---: |
| text-state | 0/27 | 24/27 | 27/27 | 27/27 |
| visual-state | 0/27 | 25/27 | 27/27 | 27/27 |
| multimodal-state | 0/27 | 24/27 | 27/27 | 27/27 |

Base, SFT sequential-order, random-valid and exact-reference records were
independently replay-verified from Goal 3 and bound by the audited Goal 3
evidence, independent-replay and checkpoint hashes. They required no new GPU
episodes. Neither all curriculum arms nor all comparator controls saturated;
the predeclared conclusion is to interpret the paired intervals.

Historical #67 is reported separately: its 60/60 saturated result used an
unmatched old v3 schedule. It is never pooled with this analysis
(`historical_issue67.pooled: false`).

## Provenance and disclosed attempt history

The frozen evidence contains 42 panel/modality/arm aggregates, 27 paired rows
and a producing-attempt identity for every retained model episode. Independent
`audit-final` replayed the retained records and returned exactly `PASS: 243/243
curriculum episodes replayed`.

`curriculum-evaluate-0` attempt 1 failed on the curriculum-arm whitelist bug;
attempt 2 reached its wall cap; attempt 3 failed retained-episode provenance
validation and produced zero new episodes; attempt 4 reached its wall cap at
160/162; attempt 5 replayed the retained records, produced the two missing
episodes and succeeded. `curriculum-evaluate-1` attempt 1 failed on the same
whitelist bug; attempt 2 reached its wall cap; attempt 3 failed on the same
retained-episode provenance check and produced zero new episodes; attempt 4
succeeded.

The mixed-attempt aggregate is auditable because each episode is bound to its
actual producing attempt: evaluate-0 attempts 2, 4 and 5, and evaluate-1
attempts 2 and 4. The retained fixes are commits `2946e18` (curriculum-arm
behavior mapping), `dcaa4ba` (mixed-attempt evidence and resume bounds) and
`8c95077` (policy-identity plus committed-lineage provenance). No episode is
attributed only to the final successful process.

## Accounting

The ledger charges all launches, including failures and cutoffs:
`curriculum-evaluate-0` (GPU 0, port 18800) consumed 6.171836 GPU-hours across
five attempts; `curriculum-evaluate-1` (GPU 1, port 18801) consumed 3.382629
GPU-hours across four attempts; `curriculum-evaluate-final` was CPU-only.
Evaluation consumed 9.554465 GPU-hours. Together with the separately published
2.224124 GPU-hours for training, the curriculum branch cumulative total is
11.778588 / 48 GPU-hours. The 243 model episodes made 6,030 model calls and
recorded 33,105.8 seconds of active episode wall time. Comparator reuse added
no GPU episodes.

## Verification

Read-only verification of the published evidence and analysis:

```bash
source ~/cd_vlaplan
EXPANDED_TERMINAL_PATH=outputs/expanded-study/v1/jobs/curriculum-evaluate-final/1/terminal.json \
  python scripts/run_expanded_curriculum_evaluation.py audit-final
```

`audit-final` independently reconstructs the complete evidence, recomputes the
predeclared analysis and requires equality with both frozen runtime JSON files.
`audit-worker` and `finalize` are mutating repair/republication operations; run
them only for a deliberate republication.

## Limitations

- One training seed (17) per cell; no training-seed variance is claimed.
- Modality matching answers the curriculum-ordering question within modality;
  it does not estimate cross-modality transfer.
- Several arms and two controls are at 27/27. The saturation check therefore
  directs interpretation to the paired intervals, not point-estimate ranking.
