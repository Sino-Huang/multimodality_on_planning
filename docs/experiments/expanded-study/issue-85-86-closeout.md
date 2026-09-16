<!-- EXPANDED-GOAL7-CLOSEOUT-V1 -->

Goal 7 completed the `expanded-successor-v1` full-state interface and
outcome-blind qualification.

- The model predicts complete sorted dynamic atoms and numeric fluents plus the
  canonical identity of those exact values. Immutable static context is checked
  separately and never mixed into dynamic state.
- Raw predictions are retained. Strict schema, static-context, source/action
  identity, applicability, state identity and authoritative effects are reported
  separately. An incorrect state is never normalized, applied, repaired or
  replaced with the trusted state; downstream search has its own status.
- Independent replay starts with a fresh authority and registers each source
  through its complete producing-action path. All 512 training-only records,
  including 439 non-initial sources and paths up to 16 actions, reproduced.
- The frozen membership retains 421 accepted transitions from the original BFS
  membership and fills the 91 retirement positions by fixed round-robin order
  over accepted transitions from the same 25 training tasks. No model or held-out
  outcome entered selection.
- Complete targets measured 124–383 tokens. The output allowance is 512 tokens,
  derived from the measured maximum with a 1.25 margin and 64-token rounding;
  states are not truncated to the old 384-operation allowance.
- Text, visual and multimodal use identical record IDs and targets. All 512
  inputs and unlabelled 128px view bindings replayed; maximum supervised sizes
  are 2,352, 3,892 and 4,808 tokens respectively.
- Full-output scalar, batch and repeated-batch probes passed on both A100s at
  ports 18800 and 18801. Repeated outputs and scalar/batch first items were
  byte-identical in every modality. Finite discarded optimizer steps exercised
  all 174,587,904 trainable adapter parameters without changing checkpoints.
- Full 24-task unseen coverage projects to 147.658902 GPU-hours and is not
  admitted. The preregistered one-minimum-cost-task-per-domain fallback retains
  all 12 domains, all three modalities and all three development tasks at a
  projected 62.333058/64 GPU-hours. Selection used exact reference costs only.
- Qualification consumed 0.220960 GPU-hours including retained technical
  failures. It collected no scientific predictions and performed no persistent
  update. Goals 8 and 9 own collection, training and final evaluation.
- The affected suite passed 76 tests; lint and all scheduled/standalone audits
  passed.

Tracked evidence:

- [`successor-protocol.json`](https://github.com/Sino-Huang/multimodality_on_planning/blob/main/configs/experiments/expanded-study/successor-protocol.json)
- [`successor-protocol.md`](https://github.com/Sino-Huang/multimodality_on_planning/blob/main/docs/experiments/expanded-study/successor-protocol.md)
- [`successor-qualification.json`](https://github.com/Sino-Huang/multimodality_on_planning/blob/main/docs/experiments/expanded-study/successor-qualification.json)
- [`goal7-completion-audit.json`](https://github.com/Sino-Huang/multimodality_on_planning/blob/main/docs/experiments/expanded-study/goal7-completion-audit.json)

This fulfills the interface and trace requirements in #85 and the frozen data,
training, control, output, budget and hardware qualification requirements in
#86. It does not claim Goal 8 collection or Goal 9 training/evaluation.
