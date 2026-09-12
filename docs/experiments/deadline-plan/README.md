# Deadline study execution record

The selected route is **#76 → #77 (NO_GO) → #100 → #108**. The multimodal pilot
completed and was independently replayed, but every learned setting failed its
existing success and invalid-operation thresholds. Further GPU work stops.

#75's older visual v5 run completed on its larger scope in 76.23 hours; the proposed
four-hour visual pilot was never run. #76 completed its 512-record/one-epoch pilot
in 64.92 minutes under the four-hour cap. Their unequal schedules do not identify
a controlled modality effect. Original negative performance outcomes remain intact.

## Ticket dispositions

- **Completed:** #75 visual execution/replay, #76 multimodal execution/replay,
  #77 go/no-go synthesis, #100 development feasibility/limitations report.
- **Final release:** #108 packages and publishes the verified retained evidence;
  its publication record is maintained in the completion ledger.
- **Closed as not planned after NO_GO:** #90–#95, #97, #109 (conditional final
  branch), and #78–#84 (optional DAgger). These experiments were not executed.
- **Remain deferred/open:** #85–#89, #96, #98–#99, #101–#107. No end-to-end,
  broad robustness, replication or transfer result is claimed.

No additional model command is part of this deadline study. Old reproduction
commands and unselected specifications remain available for a new future protocol;
they are not pending work on the selected route.

## Evidence and artifacts

- [#75 completion](../issue75/v5-completion.md)
- [#76 completion](../issue76/completion.md)
- [#77 decision](../issue77/decision.md)
- [Final feasibility/limitations report](../deadline-study/report.md)
- [Condition metrics](../deadline-study/core-results.csv)
- [Compute accounting](../deadline-study/compute-accounting.json)
- [Completion/skip/defer ledger](../deadline-study/completion-ledger.json)
- [Artifact preparation and portable replay](../deadline-study/release-tools.md)

The original full ticket bodies/comments are archived in `original-issues.json`;
`revised-issues.json` records the earlier deadline proposal. That initial proposal
allocated 16 GPU-stage wall-clock hours plus an optional two-hour DAgger branch.
It was not the actual historical spend: visual v5 alone exceeded it before this
automation, while #76 respected its cap. Known timed #75 attempts plus #76 total
80.42 wall-clock hours; this excludes earlier BFS/curriculum training and is not
GPU-hours. Unused final-evaluation/DAgger budgets were not reassigned.

A completed execution or artifact release does not turn a failed scientific gate
into PASS. The retained scope supports development feasibility and limitations,
not held-out generalization or completion of the broader parent research program.
