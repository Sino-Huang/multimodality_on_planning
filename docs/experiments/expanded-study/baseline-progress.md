# Expanded matched baseline

Goal 3 consumes the 24-task panel frozen by Goal 2 and the twelve checkpoints
verified in `readiness.json`. The outcome-blind execution protocol is frozen in
`configs/experiments/expanded-study/baseline-protocol.json` before any final
baseline episode. It retains four algorithms, three modalities and four
conditions: 1,152 logical bindings, including 576 model episodes. No adapter is
trained or selected in this goal.

Two CPU scheduler jobs own the exact-reference and random-valid controls. Two
GPU scheduler jobs own pretrained-base and process-SFT episodes, with physical
GPU mappings 0 and 1 and scheduler-assigned distinct `MASTER_PORT` values. Every
cell is split by task index modulo two. Each worker therefore owns 288 bindings;
the four partitions are disjoint and exhaustive.

Every episode has an isolated persistent live-view directory. Completed events
and each generated raw output are atomically journalled before the trusted
runtime consumes the output. Resume first replays committed events and any
persisted pending output. A completed episode is accepted only after read-only
replay; worker completion hooks independently replay their partition, and the
final CPU audit independently replays all 1,152 reports again.

Random-valid remains labelled as an oracle-assisted valid-operation control.
Raw invalid model outputs remain in episode events and consume the native
family budget. Input-bound failures and scheduler cutoffs remain explicit
missingness; no input is truncated and no task or cell is removed.

The GPU jobs each reserve at most 99,000 seconds (27.5 GPU-hours). Together with
the 0.733140 GPU-hours already consumed by readiness and panel qualification,
the maximum reservation is 55.733140 GPU-hours under the unchanged 56-hour
branch cap. The historical-consumption estimate remains conditional, so full
completion is not asserted until the terminal replay audit passes.

The first control-worker completion hook exposed a report-schema adapter defect:
expanded reports name the binding `protocol_id`, while the shared replay helper
accepts the same value as `contract_id`. The retained reports and episode outputs
were correct. The replay adapter now passes the frozen protocol ID under the
shared helper's field name; the original failed hook evidence is retained.

## Final evaluation

All four execution workers completed their frozen 288-binding partitions. The
two model workers used physical GPUs 0 and 1 with `MASTER_PORT` 18800 and 18801,
respectively. Their actual durations were 2.159681 and 3.636098 GPU-hours. The
expanded-baseline branch consumed 6.528918 cumulative GPU-hours including
readiness and panel qualification, below its unchanged 56 GPU-hour ceiling.

The final corpus contains 1,152 unique completed reports and no partial reports.
Each of the 48 modality/algorithm/condition cells contains exactly 24 episodes;
576 episodes invoke a model. The complete cell-level counts and outcomes are in
`baseline-evaluation.json`.

| Condition | Successes / episodes | Decisions | Invalid operations |
| --- | ---: | ---: | ---: |
| pretrained base | 0 / 288 | 288 | 288 |
| process SFT | 125 / 288 | 3,918 | 163 |
| random valid | 240 / 288 | 12,582 | 0 |
| exact reference | 288 / 288 | 12,930 | 0 |

Random-valid is an oracle-assisted control that selects a valid operation; it is
not evidence of learned operation generation. The pretrained base produced an
invalid first operation in every episode. Process SFT succeeded only for the two
additive best-first algorithms: text 22/24 greedy and 20/24 weighted, visual
22/24 greedy and 18/24 weighted, and multimodal 21/24 greedy and 22/24 weighted.
Its BFS and best-first-width cells were 0/24 in every modality. These failures
remain outcomes rather than triggers for replacement tasks or reruns. Across all
model conditions, 451 raw invalid outputs are retained in the episode journals.

Worker completion hooks independently replayed every 288-episode partition. The
first control-worker hook's original schema-adapter failure remains preserved;
the corrected audit for that unchanged partition passed 288/288. The final
scheduler-run CPU audit then independently replayed all 1,152 persisted episodes
and its completion hook returned zero. `baseline-independent-replay.json`
records complete read-only replay with no missing bindings.
