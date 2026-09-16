# Issue #89/#99 closeout (Goal 9)

#89 (train and verify successor-prediction checkpoints) was closed earlier with
[successor-training.md](successor-training.md) and
[successor-training.json](successor-training.json): three frozen successor-SFT
cells, 512 verified release-001 teacher labels each, one epoch, exactly 16
optimizer updates, seed 17, final checkpoint only, source BFS adapters
byte-unchanged, 0.693779 GPU-hours.

#99 (held-out successor-prediction comparison) is now complete. The frozen
model-predicted versus trusted-successor comparison ran on the qualified
fallback coverage — 3 development + 12 outcome-blind unseen tasks, 3 modalities,
2 arms: 90/90 episodes, zero missing bindings, complete independent replay.

- Published evidence: [successor-evaluation.json](successor-evaluation.json)
  (byte-identical to the audited runtime artifact) and
  [successor-evaluation.md](successor-evaluation.md); requirement audit:
  [goal9-completion-audit.json](goal9-completion-audit.json).
- Trusted arm 45/45 goal-reached. Model arm 1/45 (unseen multimodal
  `elevators-compact-914002`); the remaining 44 terminate as
  `invalid_successor` with per-check failure classification (schema,
  static context, source/action identity, applicability, state identity,
  effect) reported separately from downstream search, model calls and compute.
- No predicted state was repaired or replaced by a trusted state anywhere;
  all 109 raw predictions are retained; 109 of the 4,062 model-call allowance
  used (early rejection terminates episodes — a measured outcome, not reduced
  coverage).
- Evaluation consumed 0.641443 GPU-hours over two single-attempt GPU workers
  (ports 18800/18801) plus a CPU finalizer; successor branch cumulative
  10.851129 / 64 GPU-hours; all GPU work ended before the cutoff.
- The attempt-1 audit hooks exposed a replay-verifier defect (missing
  terminating `next_request()`), fixed at `7456808`; because the scheduler
  refuses relaunch after succeeded workers, passing disclosed re-audits
  (`reaudit-result.json`, embedding the original rc=1 receipts) were recorded
  at `7f1f893`, and `audit-final` independently recomputed the published
  evidence byte-for-byte. Both the failure and the repair are disclosed in the
  published evidence.

The deliverables of #89 and #99 are satisfied.
