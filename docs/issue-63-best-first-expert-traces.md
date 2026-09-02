# Issue 63 paired additive best-first expert traces

Issue 63 uses two deterministic, deliberately suboptimal settings over the
unchanged 75-task panel:

- `best_first_add_w3` uses scalar priority `g + 3*h_add`, generation-serial
  tie-breaking, and cheaper-path reopening.
- `best_first_add_greedy` uses scalar priority `h_add`, generation-serial
  tie-breaking, and does not reopen closed states.

Both settings use the same eager Trusted Search Runtime and additive relaxed
heuristic. There are no landmarks, preferred operators, multiple open lists,
lazy evaluation, or optimal-plan claims.

## Immutable predecessor

The issue-63 v2 qualification attempted all 150 jobs and retained 149
`goal_reached` results. `best_first_add_w2` reached the frozen 55,000-decision
ceiling on `visitall-train-hard-0013`, so the phase published `VALID_STOP` with
reason `resource_exhaustion`. Its receipt, manifest, and 150 measurements remain
under `data/best_first_paired_phase_v2/qualification-v1/`; v3 binds the exact v2
receipt by path, byte size, and SHA-256. V2 is never resumed, rewritten, or
treated as scientific completion.

## Selection evidence

An independent Fast Downward screen covered all 25 fixed development tasks.
The retired w2 setting solved 25/25 with 16,622 total expansions, maximum
12,971 expansions, and aggregate plan cost 1,699. W3 solved 25/25 with 13,001
total expansions, maximum 10,045 expansions, and aggregate plan cost 1,899:
21.78% fewer total expansions and 22.56% fewer maximum-case expansions than
w2, with the expected plan-quality tradeoff. Greedy solved 25/25 with 9,542
total expansions and aggregate plan cost 2,098.

The in-project bounded regression on frozen
`visitall-train-easy-0038` independently exercises the implemented runtime. W2
uses 448 expansions / 1,689 decisions / cost 44; w3 uses 331 expansions / 1,261
decisions / cost 48. This establishes that the implementation can reduce
expansion on the target workload. It is not a claim that w3 dominates w2 on
every task. V3 was selected after the v2 stop and before any v3 full-panel
outcome; that outcome-informed successor relationship is recorded explicitly.

The successor contract is `configs/experiments/best-first-paired-design-v3.json`,
with start authority in
`configs/experiments/best-first-paired-authorization-v3.json`. It binds the
unchanged issue-62 task manifest and the v2 `VALID_STOP` receipt. V3 uses new
contract, authorization, gate, qualification-attempt, generation-attempt, and
output identities. Qualification publishes `PASS`, `VALID_STOP`, or `INVALID`;
trace generation requires the exact v3 `PASS` receipt.

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
- 55,000 decision records (44.7% headroom above the 38,011-successor w3
  development maximum);
- 37,400,000 uncompressed trace bytes, matching the prior BFS maximum.

There is no trace segmentation. Any ceiling exhaustion is a governed
`VALID_STOP`, and an incomplete pair is never published as a completed pair.

## Operator commands

The short dry runs execute v3 authority validation and an end-to-end two-setting
fixture generation/replay without writing repository outputs:

```bash
source ~/cd_vlaplan
cd /data/scratch/projects/punim0478/sukaih/multimodality_on_planning
python scripts/qualify_best_first_paired_panel.py --dry-run
python scripts/generate_best_first_paired_expert_traces.py --fixture-dry-run
python scripts/generate_best_first_paired_expert_traces.py --dry-run
```

The real run is deliberately split so trace generation cannot start without a
complete fixed-panel qualification. Qualification defaults to up to eight
parallel isolated subprocesses and writes to
`data/best_first_paired_phase_v3/qualification-v1`:

```bash
source ~/cd_vlaplan
cd /data/scratch/projects/punim0478/sukaih/multimodality_on_planning
python scripts/qualify_best_first_paired_panel.py
python scripts/qualify_best_first_paired_panel.py --check
```

Qualification runs one isolated subprocess per job and schedules up to eight in
parallel by default (bounded by the process CPU affinity). Use `--workers N` to
set a smaller explicit concurrency. Per-job search order and immutable
measurement bytes do not depend on completion order.

Inspect the final qualification receipt. Only when its outcome is `PASS` and
`qualification_complete` is true, run:

```bash
python scripts/generate_best_first_paired_expert_traces.py
python scripts/generate_best_first_paired_expert_traces.py --check
```

Both commands flush JSON progress. A long task reports expansion, decision,
reopen, visited-state, and elapsed-time counters every ten seconds. Interrupted
qualification can continue with `--resume`; completed immutable pair directories
can likewise be reused with generator `--resume`. A v3 `VALID_STOP` is retained
and reported; it never authorizes generation.
