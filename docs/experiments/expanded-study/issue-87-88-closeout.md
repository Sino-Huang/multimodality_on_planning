Goal 8 collected and independently verified the complete frozen successor data
matrix: 512 interactions per modality, 1,536 total, from the same 25 BFS training
tasks. No development or final task supplied training labels.

Versioned local dataset:
`outputs/expanded-study/v1/successor/dataset/release-001/report.json`.
`docs/experiments/expanded-study/successor-data.json` publishes every artifact
path/hash and exact membership. Separate interaction and teacher-label files
retain predictions and corrections without substitution. Raw predictions,
verification errors, full source states/producing paths, original decision and
trace links, bounded Search Memory, view and runtime identities remain intact.
The shared live/training builder reproduces declared observations and limits.

Independent replay verifies every interaction and all 1,536 complete teacher
targets. Released gzip payloads regenerate byte-identically, source splits are
preserved, and identical authoritative inputs have no conflicting labels. The
task-level reference-cost/source-hash receipt is published in
`successor-data-provenance.json`; the additional audit is
`successor-data-independent-audit.json`.

Original-adapter outcomes are retained: 119 exact successors, 1,274 schema
failures, 75 state-identity failures and 68 effect failures. Incorrect predictions
were neither applied nor repaired. Downstream search is explicitly not evaluated
and belongs to Goal 9, along with persistent successor training.

Technical recovery preserved the four first-attempt returned predictions, all
failed logs/terminal/hook records and their compute charge. The token-binding
fix changed no scientific input, membership, target or decoding rule. Distinct
ports were 18800/18801. Goal 8 consumed 9.294947 GPU-hours including failed
attempts; cumulative successor spend is 9.515907/64 with no budget transfer or
extension. All scheduled hooks, standalone release replay, independent teacher
audit, 77 affected tests and Ruff pass.

The deliverables of #87 and #88 are satisfied. Dataset documentation and the
requirement-by-requirement completion audit are committed with the evidence.
