<!-- EXPANDED-GOAL6-CLOSEOUT-V1 -->

Goal 6 and the complete two-iteration `expanded-dagger-v1` comparison are
finished.

- Iteration one trained DAgger and continued-SFT for all three modalities from
  their declared inputs. Iteration-two collection used the corresponding
  DAgger iteration-one final checkpoint, never the original policy.
- Iteration two retained 307 text, 357 visual and 290 multimodal student
  decisions. Every modality reached exactly 128 expert queries/corrections and
  retained one final rejected output without an expert query. All tasks are in
  the frozen training split.
- Independent replay verified the 384 new corrections and all 37 completed
  iteration-two episodes. The cumulative 512-record aggregations contain 201
  unique text corrections, 203 visual corrections and 181 multimodal
  corrections after deterministic cross-iteration deduplication.
- Both training rounds independently verified all six DAgger/continued-SFT
  checkpoints: 512 records, seed 17, one epoch and 16 optimizer updates per
  cell, with the declared two-step lineage and all 504 adapter tensors changed.
- Evaluation covered all five arms, three modalities, three development tasks
  and 24 unseen tasks. All 405 episodes and 81 whole-problem paired rows replayed
  successfully with zero missing coverage.
- On the 72 unseen modality-task rows, DAgger and continued SFT each achieved
  1 invariant-valid success (one paired win, one paired loss, 70 ties). Original
  SFT achieved 0, random-valid 45 and exact reference 72. DAgger's invalid
  operation rate was 71/225 (31.56%), compared with 71/406 (17.49%) for
  continued SFT. The result does not show a DAgger advantage.
- The branch used 10.909219 of 48 GPU-hours, including all retained failures:
  2.220535 for qualification/iteration-one collection, 3.197716 for training,
  2.898848 for iteration-two collection and 2.592120 for evaluation. No budget
  transfer or extension occurred.
- The evaluation infrastructure retry followed commit `a0b8d53` and resumed the
  same frozen completed episodes and journals. No final-task correction,
  outcome-selected rerun, task replacement or repeat-until-positive update
  occurred.

Tracked evidence:

- [`dagger-comparison.json`](https://github.com/Sino-Huang/multimodality_on_planning/blob/main/docs/experiments/expanded-study/dagger-comparison.json)
- [`goal6-completion-audit.json`](https://github.com/Sino-Huang/multimodality_on_planning/blob/main/docs/experiments/expanded-study/goal6-completion-audit.json)
- [`dagger-protocol.md`](https://github.com/Sino-Huang/multimodality_on_planning/blob/main/docs/experiments/expanded-study/dagger-protocol.md)

This evidence fulfills the complete two-iteration collection requirements in
#80–#82, independent correction verification in #83, and matched training and
fixed-panel comparison in #84.
