# Issue 63 paired additive best-first expert traces

Issue 63 supersedes the stopped optimal-A* trace design with two deterministic,
deliberately suboptimal settings over the unchanged 75-task panel:

- `best_first_add_w2` uses scalar priority `g + 2*h_add`, generation-serial
  tie-breaking, and cheaper-path reopening.
- `best_first_add_greedy` uses scalar priority `h_add`, generation-serial
  tie-breaking, and does not reopen closed states.

Both settings use the same eager Trusted Search Runtime and additive relaxed
heuristic. There are no landmarks, preferred operators, multiple open lists,
lazy evaluation, or optimal-plan claims. The issue-62 v1 A* attempt remains an
immutable `VALID_STOP`; it is not rerun or rewritten.

## Selection evidence

An independent Fast Downward screen covered all 25 fixed development tasks.
The quality setting solved 25/25 with 16,622 total expansions and aggregate
plan cost 1,699. The greedy setting solved 25/25 with 9,542 total expansions
and aggregate plan cost 2,098. Intermediate additive weights 3 and 5 fell
between these endpoints. Weighted LM-cut was rejected because heuristic
evaluation timed out on hard VisitAll despite a small expansion count.

The frozen replacement contract is
`configs/experiments/best-first-paired-design-v2.json`, with its start authority
in `configs/experiments/best-first-paired-authorization-v2.json`. It binds the
unchanged issue-62 task manifest by path, byte size, and SHA-256 before any new
qualification outcome exists. The authorization embeds the matching phase-gate
receipt; qualification publishes a separate `PASS`, `VALID_STOP`, or `INVALID`
receipt, and trace generation requires its exact `PASS` receipt.

## Compact text trace

`best_first_compact_trace_v1` stores:

- the task once per pair;
- each state actually presented to the model once, under deterministic short
  references `s0`, `s1`, and so on;
- one expansion record containing frontier count/head summaries before and
  after expansion;
- for each candidate decision, the canonical typed target, compact trusted
  result, and SHA-256 of the exact canonical model input.

The trace never stores full frontier arrays or repeated complete model inputs.
Independent replay reparses the task, recomputes `h_add`, rebuilds duplicate
detection and the frontier, applies every transition, reconstructs every
candidate and bounded accepted delta, and requires each reconstructed model
input digest to match. Therefore the compact representation remains a complete
mechanical source for teacher/live byte parity without storing heuristic proof
internals or a raw frontier history.

The exact persisted canonical bytes, including their terminating newline, are
subject to all three immutable ceilings:

- 15,000 expansions;
- 55,000 decision records (10% headroom above the 49,462-successor development
  maximum);
- 37,400,000 uncompressed trace bytes, matching the prior BFS maximum.

There is no trace segmentation. Any ceiling exhaustion is a governed
`VALID_STOP`, and an incomplete pair is never published as a completed pair.

## Operator commands

The short dry runs execute authority validation and an end-to-end two-setting
fixture generation/replay without writing repository outputs:

```bash
source ~/cd_vlaplan
cd /data/scratch/projects/punim0478/sukaih/multimodality_on_planning
python scripts/qualify_best_first_paired_panel.py --dry-run
python scripts/generate_best_first_paired_expert_traces.py --fixture-dry-run
python scripts/generate_best_first_paired_expert_traces.py --dry-run
```

The real run is deliberately split so trace generation cannot start without a
complete fixed-panel qualification:

```bash
source ~/cd_vlaplan
cd /data/scratch/projects/punim0478/sukaih/multimodality_on_planning
python scripts/qualify_best_first_paired_panel.py
python scripts/generate_best_first_paired_expert_traces.py
```

Both commands flush JSON progress. A long task reports expansion, decision,
reopen, visited-state, and elapsed-time counters every ten seconds. Interrupted
qualification can continue with `--resume`; completed immutable pair directories
can likewise be reused with generator `--resume`. Verify finished artifacts with:

```bash
python scripts/qualify_best_first_paired_panel.py --check
python scripts/generate_best_first_paired_expert_traces.py --check
```
