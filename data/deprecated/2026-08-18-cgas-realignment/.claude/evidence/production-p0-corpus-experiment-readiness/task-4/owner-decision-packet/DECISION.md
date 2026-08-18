# Owner decision packet — Todo 4 blocker and trace persistence

**Plan:** `.claude/plans/production-p0-corpus-experiment-readiness.md` (unmodified)
**Task:** Todo 4 — assemble and independently re-characterize the exact 481-row population
**Date:** 2026-08-06
**Status:** three decisions requested. No constant, contract, or corpus artifact was changed.

This packet is read-only. It creates no checkpoint, cursor, trace, selector result, or process.
Every number below is reproduced by a script in this directory — see **Reproducing this packet**.

---

## Preconditions re-verified before writing this

| Check | Result |
| --- | --- |
| `reservoir_checkpoint_000001.json` | `fa70f298…4853` — unchanged |
| `current.json` | `1b23b2c7…acdf` — unchanged, still binds round 1 |
| `selector_attempt_000001.json` | `4a594ae9…4c60` — unchanged |
| trace-v1 release manifest | `3bc89431…6b3c` — unchanged |
| `reservoir_checkpoint_000002.json` | absent, as required |
| `proof.json` | re-derived byte-identically, `b739f148…5e51` |
| 558 BFS + 558 IW streams | present, complete, no `.tmp`/`.partial` |

Nothing has run since the block was recorded.

---

## Decision 1 — `EXPECTED_OBJECT_COUNTS[4] = 190` is combinatorially unsatisfiable

Already proven. See
`.claude/evidence/production-p0-corpus-experiment-readiness/task-4/selector-infeasibility-proof/`
(`README.md`, `proof.json`, re-runnable `derive_infeasibility.py`). Ceiling 136, expected ≈ 33,
requirement 190. **No engineering work fixes this** — the 4-object stream is exhausted at its full
capacity of 600 raw ranks and the universe is closed at 210 nontrivial identities.

One clarification worth recording: **only `n=4` is blocked.** `n=8` (capacity 19,514,880) and
`n=12` (capacity 2.84 × 10¹²) are open, so their quotas are a *cost* question, not a feasibility
question.

| n | consumed | emitted | paired-exact | exact/emitted | exact/consumed | required | stream |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | 190 | 88 | 14 | 15.9% | 7.4% | 190 | **exhausted** |
| 8 | 198 | 129 | 23 | 17.8% | 11.6% | 198 | open |
| 12 | 93 | 64 | 16 | 25.0% | 17.2% | 93 | open |
| all | 481 | 281 | 53 | 18.9% | 11.0% | 481 | |

`exact/consumed` is the decision-relevant rate: disk and wall-clock scale with ranks *consumed*.
Duplicates and subset-solved candidates are rejected before characterization and cost almost nothing.

### Options — arithmetic only, none recommended

The plan forbids the worker from altering quotas, and the standing instruction on this constant was
to report without proposing. The following is priced, not preferred. Full table in
`quota-options.txt`.

- **A — keep 481 rows, rebalance the object vector.** Whatever comes off `n=4` must go onto `n=8`
  and/or `n=12`. At an `n=4` target of 33 (the expected landing point), the 157-row shift costs
  ~2,858 further `n=8` ranks or ~1,360 further `n=12` ranks.
- **B — keep the proportions, lower `EXPECTED_ROW_COUNT`.** Scaling the vector by what `n=4` can
  actually reach gives 345 rows at the absolute ceiling, 83 at the expected rate, 36 at what round 1
  achieved. Any of these also breaks `EXPECTED_SPLIT_COUNTS` (dev 39 / test 40 / train 402), which
  sums to 481 and would need rebalancing in the same edit.
- **C — accept fail-closed termination.** No constant changes, zero compute. Todo 4 terminates as
  proven-infeasible and Todos 5–16 / F1–F4 stay dependency-gated permanently.

---

## Decision 2 — trace-v2 event size is quadratic in expansions, and the fix is smaller than expected

### The measurement

Every BFS event carries three full snapshots — `frontier_before`, `frontier_after`, `visited_after` —
as lists of 64-char SHA-256 hashes. Because they grow with the search, per-event size is O(sequence)
and stream size is O(expansions²).

| | mid-sized `success_full_trace` (complete scan) | largest stream in corpus (2 GB prefix) |
| --- | --- | --- |
| first event | 2,411 B (frontier 3) | 5,775 B (frontier 8) |
| last event | 367,714 B (frontier 2,137, visited 3,326) | 1,497,276 B (frontier 9,756, visited 12,520) |
| growth | **152×** | **259×** |
| snapshot share of bytes | **98.5%** | **99.5%** |

Corpus-wide, that is 2,252.75 GB of BFS traces where the non-snapshot content is ~4 KB/event across
1,768,295 events — **a projected ~6.6 GB, a 342× reduction.**

### The fields are not merely compressible — they are exactly reconstructible

The handoff that preceded this packet proposed *delta-encoding* the three fields. Reading the emitter
(`scripts/phase3/cgas_bfs.py:122-137`, `_StateIndex.expansion`) shows a stronger result — they can be
**dropped entirely**, because each is a pure function of data the event already carries:

| rule | | source |
| --- | --- | --- |
| R1 | `frontier_before[i] == [state_id[i]]` | line 132 emits `[state_id]` verbatim — zero information |
| R2 | `frontier_after[i] == frontier_after[i-1][1:] + enqueued(i)` | line 131 emits the FIFO deque; each expansion `popleft()`s the head (line 41) and appends exactly the `enqueued=True` successors (lines 65-74) |
| R3 | `visited_after[i] == sorted(visited_after[i-1] ∪ enqueued(i))` | line 136 emits `_visited`, maintained by `insort` (line 120) from the same ids added at line 73 |

`enqueued` is already recorded per successor row. **R1–R3 were verified against the real corpus on
every event of two streams — 3,953 events, 0 violations** (`trace-event-growth.txt`). The repo's own
tests assert the same shapes independently (`tests/planning_benchmark/test_experts_bfs_iw.py:67-70`).

### Two facts that make this cheaper than the handoff assumed

1. **The contract digest does not cover the event field set.** `_NEW_CONTRACT`
   (`scripts/phase3/cgas_trace_contract_v2.py:41-59`) describes stream *framing* only — format,
   encoding, newline, hash chain, stream hash, trailer fields. Dropping three event-body fields
   leaves `NEW_CONTRACT_SHA256 = 5649fc7b…0b9d` unchanged, and the existing approval
   (`.claude/evidence/cgas-production-p0/approved-trace-v2.json`, scope
   `trace_v2_persistence_only`) is already scoped to persistence. **Whether that means no
   re-approval is needed is the owner's call, not the worker's** — but the change is narrower
   than "new contract, 558 streams invalidated".
2. **Only one consumer reads a full snapshot.** `scripts/phase3/cgas_certificate_contracts.py:37-38`
   already reduces `frontier_before` to its `[0]` element (which *is* `state_id`) and `visited_after`
   to a delta against the previous expansion. Only `frontier_order_summary` needs the full ordered
   frontier, and R2 rebuilds it with a running FIFO fold. The engineering scope is one reconstruction
   shim in the reader, not a corpus-wide migration.

### Root cause

Todo 1's acceptance criteria bounded stream *record count* (BFS ≤ 1,000,010,002) but never bounded
per-record *size*. A size bound belongs in whatever contract revision the owner authorizes.

**Decision requested:** authorize a persistence-only revision that stops writing the three
reconstructible fields, with a reconstruction shim for `frontier_order_summary`, and confirm whether
the unchanged contract digest means the existing approval carries.

---

## Decision 3 — 93.3% of the trace corpus is provably ineligible and is persisted anyway

`require_full_trace_source` (`scripts/phase3/cgas_partition_contracts.py:45-56`) accepts only
`eligible_complete_trace`. A BFS run that ends `skipped_resource_limit` never produces one, so those
streams can never contribute a corpus row.

```
BFS streams by completion_status
  skipped_resource_limit    150 files   2101.38 GB   mean 14.0 GB   1,500,000 records   26.9% of files, 93.3% of bytes
  success_full_trace        408 files    151.37 GB   mean  380 MB     268,295 records   73.1% of files,  6.7% of bytes
  TOTAL                     558 files   2252.75 GB                  1,768,295 records

IW streams by completion_status
  failed_no_plan_extracted  445 files      0.07 GB   mean  0.2 MB      26,961 records   79.7%
  success_full_trace        113 files      0.00 GB   mean  0.0 MB       1,761 records   20.3%
  TOTAL                     558 files      0.07 GB                      28,722 records
```

The plan forbids truncating a *successful* trace. These are not successful. Bounding or discarding
them is a different act from weakening trace completeness, but it is still the owner's call.

**Decision requested:** (a) stop persisting full BFS traces for `skipped_resource_limit` runs, and
(b) reclaim the 150 existing dead streams — 2.05 TiB.

---

## The disk situation makes decisions 2 and 3 prerequisites, not cleanups

This is new since the last handoff and changes the ordering.

```
round-1 BFS corpus            2.20 TiB      per rank consumed   4.68 GB
free on the project quota     1.27 TiB      per emitted cand.   8.02 GB
rounds that fit               0.58
```

**A second Todo 3 round cannot complete at trace-v2 sizes.** It would fill the project quota partway
through, before producing a checkpoint. Reclaiming the 150 ineligible streams (decision 3b) raises
headroom to 3.33 TiB — 1.51 rounds. Only decision 2 removes the constraint properly: at ~6.6 GB per
round, hundreds of rounds fit.

Options A and B under decision 1 both require further rounds, so **they are blocked on decisions 2
and 3.** Option C is the only path that needs neither. The correct sequencing is therefore:

1. Rule on decision 1 (quota) → this sets the row target and the required round count.
2. If A or B: authorize decisions 2 and 3 → otherwise no round can run.
3. Implement the persistence revision under the repo's RED/GREEN TDD obligation
   (`scripts/phase3/` is production code; the evidence scripts here are not).
4. Re-run Todo 3 rounds, then Todo 4 against the new `current.json`.

---

## Correction to prior evidence

`production-p0-corpus-experiment-readiness/task-3/round-2/runtime-stack-diagnosis.md:121`
(archived — see `.claude/archive/omo-evidence-2026-08-07.tar.gz`)
concludes **"H2 (planner search / trace emission): CONFIRMED"**. The trace-*emission* half is wrong.
All three samples record `flags: 02100000` on fd 4. Octal `02100000` decodes to
`O_CLOEXEC (0o2000000) | O_LARGEFILE (0o100000)`, with access-mode bits `0` — that is **`O_RDONLY`**.
The process held the BFS stream open read-only with a monotonically advancing offset: it was
*verifying* a stream, consistent with the `verify_trace_stream` traceback observed at the stop, not
emitting one. The rising `utime`/RSS in that document are equally consistent with CPU-bound parsing.
Worth correcting if that document is ever cited; it does not affect the infeasibility proof.

---

## What the worker did not do

- Did not edit the plan, any quota, selector constant, planner limit, or trace contract.
- Did not run Todo 3 round 2 or Todo 4. No cursor advanced, no selector feedback emitted.
- Did not delete, truncate, migrate, or regenerate any of the 558 trace pairs.
- Did not recommend a quota vector.
- No commit, no PR, no `git clean`. Unrelated worktree edits preserved.

---

## Reproducing this packet

```bash
cd /data/scratch/projects/punim0478/sukaih/multimodality_on_planning
source ~/cd_vlaplan
P=.claude/evidence/production-p0-corpus-experiment-readiness/task-4/owner-decision-packet

python "$P/measure_corpus_eligibility.py"     # -> corpus-eligibility.{txt,json}   (~1 min, tail reads)
python "$P/measure_trace_event_growth.py"     # -> trace-event-growth.{txt,json}   (~20 s, 2.2 GB read)
python "$P/derive_quota_options.py"           # -> quota-options.json              (instant)
```

All three are read-only and idempotent. `measure_trace_event_growth.py` is the one that matters most
if you want to challenge this packet: it re-derives R1–R3 against the corpus and prints a per-rule
violation count. A single violation anywhere invalidates decision 2.
