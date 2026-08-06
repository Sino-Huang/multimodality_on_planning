# Production P0 - owner decision packet assembled - 2026-08-06

## Summary

Todo 4 remains blocked and unchecked. This session assembled the owner decision packet at
`.claude/evidence/production-p0-corpus-experiment-readiness/task-4/owner-decision-packet/`
(entry point `DECISION.md`, three re-runnable read-only scripts).

Read-only session. No plan edit, no constant change, no round run, no cursor advance, no
selector feedback, no commit. All four immutable digests and `proof.json` re-verified
byte-exact before and after.

## What the packet asks the owner to rule on

1. **`EXPECTED_OBJECT_COUNTS[4] = 190`** — already proven unsatisfiable (ceiling 136,
   expected ~33). Options A/B/C are priced in `quota-options.txt` as arithmetic only; no
   recommendation is made, per the standing instruction on this constant.
2. **A persistence-only trace revision** that stops writing three redundant event fields.
3. **Ceasing to persist, and reclaiming, contract-ineligible BFS traces.**

## The three findings that were new this session

### Only `n=4` is blocked

`n=8` (capacity 19,514,880) and `n=12` (capacity 2.84e12) are open and not exhausted. Their
quotas are a cost question, not a feasibility question. Decision-relevant rate is
`exact/consumed`, not `exact/emitted`, because disk and wall-clock scale with ranks consumed:
`n=4` 7.4%, `n=8` 11.6%, `n=12` 17.2%, overall 11.0%.

### The snapshot fields are exactly reconstructible, not merely compressible

`frontier_before` / `frontier_after` / `visited_after` are 98.5-99.5% of BFS stream bytes and
make stream size O(expansions squared). Reading the emitter
(`scripts/phase3/cgas_bfs.py:122-137`) gives exact reconstruction rules:

- `frontier_before[i] == [state_id[i]]` — line 132 emits `[state_id]` verbatim, zero information.
- `frontier_after[i] == frontier_after[i-1][1:] + enqueued(i)` — FIFO deque, `popleft` at line 41,
  append of `enqueued=True` successors at lines 65-74.
- `visited_after[i] == sorted(visited_after[i-1] | enqueued(i))` — `_visited` maintained by
  `insort` at line 120 from the ids added at line 73.

Verified on every event of two real streams (3,953 events, 0 violations) by
`measure_trace_event_growth.py`. The repo's own tests assert the same shapes at
`tests/planning_benchmark/test_experts_bfs_iw.py:67-70`.

**So the fields can be dropped, not delta-encoded.** An earlier handoff proposed delta encoding;
that was weaker than necessary. Two consequences make the change cheaper than it looked:

- `NEW_CONTRACT_SHA256 = 5649fc7b...0b9d` covers stream *framing* only
  (`scripts/phase3/cgas_trace_contract_v2.py:41-59`: format, encoding, newline, hash chain,
  stream hash, trailer fields). It does **not** enumerate event-body fields, so dropping three
  of them leaves the digest unchanged. Whether the existing `trace_v2_persistence_only`
  approval therefore carries is an owner call, not a worker call.
- Only one consumer reads a full snapshot. `scripts/phase3/cgas_certificate_contracts.py:37-38`
  already reduces `frontier_before` to `[0]` (which is `state_id`) and `visited_after` to a
  delta. Only `frontier_order_summary` needs the ordered frontier, rebuildable by a running
  FIFO fold. Scope is one reader shim, not a corpus migration.

Root cause: Todo 1 bounded stream *record count* but never per-record *size*.

### Round 2 cannot fit on disk — this reorders the plan

Round-1 BFS corpus is 2.20 TiB; free on the project quota is 1.27 TiB. **0.58 rounds fit.** A
second Todo 3 round would exhaust the quota partway through, before producing a checkpoint.

Reclaiming the 150 contract-ineligible streams raises headroom to 3.33 TiB (1.51 rounds). Only
the persistence revision fixes it properly: ~6.6 GB per round, a 342x reduction.

Therefore quota options A and B are **blocked on decisions 2 and 3** — those are prerequisites,
not cleanups. Option C (fail-closed) is the only path needing neither.

## Corpus composition (measured, tail-read of every trailer)

```
BFS  skipped_resource_limit   150 files  2101.38 GB  1,500,000 records   26.9% files / 93.3% bytes
BFS  success_full_trace       408 files   151.37 GB    268,295 records   73.1% files /  6.7% bytes
IW   failed_no_plan_extracted 445 files     0.07 GB     26,961 records   79.7%
IW   success_full_trace       113 files     0.00 GB      1,761 records   20.3%
```

`require_full_trace_source` (`scripts/phase3/cgas_partition_contracts.py:45-56`) accepts only
`eligible_complete_trace`, so the 150 `skipped_resource_limit` streams can never contribute a
row. IW width-1 success at 20.3% is the true ceiling on paired-exact yield, since paired-exact
needs both planners exact.

Note on wording: an earlier draft called the 93.3% a file share. It is the **byte** share; the
file share is 26.9%.

## Correction to prior evidence

`.claude/evidence/production-p0-corpus-experiment-readiness/task-3/round-2/runtime-stack-diagnosis.md:121`
concludes "H2 (planner search / trace emission): CONFIRMED". The *emission* half is wrong. All
three samples show `flags: 02100000` on fd 4, which decodes to
`O_CLOEXEC (0o2000000) | O_LARGEFILE (0o100000)` with access-mode bits `0` = **`O_RDONLY`**. The
process held the stream open read-only with an advancing offset — it was verifying, consistent
with the `verify_trace_stream` traceback at the stop. Does not affect the infeasibility proof.

## Reproducing

```bash
cd /data/scratch/projects/punim0478/sukaih/multimodality_on_planning
source ~/cd_vlaplan
P=.claude/evidence/production-p0-corpus-experiment-readiness/task-4/owner-decision-packet
python "$P/measure_corpus_eligibility.py"   # ~1 min, trailer tail-reads only
python "$P/measure_trace_event_growth.py"   # ~20 s, reads 2.2 GB, re-derives R1-R3
python "$P/derive_quota_options.py"         # instant
```

`measure_trace_event_growth.py` is the one to attack: a single R1/R2/R3 violation anywhere
invalidates decision 2.

## Still true, still binding

- Todo 4 stays unchecked until an exact selector-feasible 481-row manifest passes independent
  re-characterization and parity, or accepted finite exhaustion terminates the plan fail-closed.
- Do not implement the persistence revision before an owner ruling; `scripts/phase3/` changes
  carry a RED/GREEN TDD obligation, which the evidence scripts here deliberately do not.
- Do not run Todo 3 round 2. It cannot produce `selector_feasible` and now cannot fit on disk.
- Never `git clean`; preserve the dirty shared worktree. No commits, no PRs.
- Do not recreate `.omo/boulder.json`.
