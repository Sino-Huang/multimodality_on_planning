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
