# Owner decision packet — trace contract v3

**Plan:** `doc/high_level_plans/research_execution_plan.md`, Phase 0b / build-order step 2 (Gate 0b)
**Date:** 2026-08-07 · **HEAD:** `977cc65` · **Status:** two decisions requested
**Nothing was implemented.** No contract, constant, quota, planner limit, cursor, or corpus artifact
was changed. This packet is read-only; every number in it is reproduced by a script in this
directory — see **Reproducing this packet**.

---

## Scope note — this packet carries two decisions, not three

The session brief asked for one packet with three decisions: contract v3, off-plan expansion
certificates, and whether the calibration pilot needs release-grade provenance. The third has been
split into a companion packet, `DECISION-pilot-provenance.md`, in this same directory. The reason is
not process tidiness:

**Decision 3's answer depends on decision 2's, and on a bar this packet does not carry.** Whether
the pilot needs the audited production release path is largely a question of how big the pilot is.
At the loose stability bar with off-plan harvesting it is 6 instances and a few thousand renders —
auditable by hand. At the conventional bar without off-plan harvesting it is 917 instances, i.e.
*larger than the production corpus*, at which point it plainly needs the production path. Asking the
owner to rule on 3 in the same document that asks them to rule on 2 asks them to answer a question
whose input is on the next page.

The second reason is the one the brief already anticipated: decisions 1 and 2 are on the critical
path and decision 3 is not. v3 must be ruled on now to unblock M1; decision 3 does not bind until
M2, one full milestone and a regeneration later. If the owner is uneasy about pilot provenance, the
natural response is to hold the packet — and that would stall a contract change that has no
dependency on it whatsoever.

Splitting costs the owner nothing. Both packets can be ruled on in one sitting. It only removes the
coupling.

---

## Preconditions re-verified before writing this

| Check | Result |
| --- | --- |
| `reservoir_checkpoint_000001.json` | `fa70f298…4853` — unchanged |
| `current.json` | `1b23b2c7…acdf` — unchanged, still binds round 1 |
| `selector_attempt_000001.json` | `4a594ae9…4c60` — unchanged |
| trace-v1 release manifest | `3bc89431…6b3c` — unchanged |
| `proof.json` | `b739f148…5e51` — unchanged |
| `reservoir_checkpoint_000002.json` | absent, as required |
| 558 BFS + 558 IW streams | present, 1,116 files, 2,252.82 GiB, every trailer parses |
| approved trace-v2 packet digest | `f7b93250…e289b` reproduces from `build_migration_packet()` |

That last row matters: the v2 approval chain is intact and verifiable, so what follows is a
supersession rather than a repair.

---

## Decision 1 — authorize trace contract v3

Five changes, one contract, one approval, one regeneration. Taken separately below because they have
different costs and two of them are larger than the plan's one-line task descriptions imply.

### 1a — Turn width escalation on in the approved policy

Escalation is **already implemented** (`scripts/phase3/local_iw.py`, commit `1aff5e3`, TDD, 9 tests).
It is opt-in behind a `local_iw_escalate` limit, and the frozen policy pins `local_iw_max_width: 1`,
so nothing is escalating today. The ask is to move the policy, not to write code.

Phase A measured what that buys: **IW-exact 18.9% → 58.7%**, with plan length essentially unchanged
(157/165 width-2 solutions match BFS optimal; mean inflation +0.013 actions).

Three consequences the plan does not currently record:

**The policy digest moves, and this is the item that forces re-approval.**

```
NEW_CONTRACT_SHA256   5649fc7b…0b9d   unchanged — it describes stream FRAMING only
POLICY_SHA256         559c3a7c…6c1e   MOVES → 51acff53…5266
packet_sha256         f7b93250…e289b  MOVES (it embeds policy_sha256)
```

The field drops in 1b–1c leave `NEW_CONTRACT_SHA256` untouched. It is turning escalation on that
invalidates the approval, because `POLICY_LIMITS` gains `local_iw_escalate` and moves
`local_iw_max_width` 1 → 2. Worth being explicit about, because the prior packet's "the contract
digest does not cover the event field set" is still true and could be misread as "no re-approval
needed".

**The IW record-count bound is wrong under escalation.** The v2 formula
`1 + 2 · local_iw_novelty_max_expansions · local_max_applicable_actions + 2` prices one search pass.
Escalation runs up to `max_width` passes into one stream. At the unchanged cap the bound must go
**40,000,003 → 80,000,003**. This is a correctness fix to `bounds_proof`, not margin.

**Raising `local_iw_novelty_max_expansions` is margin, not a fix.** The cap never bound in Phase A —
the largest single-width pass was **8,725** expansions and the largest total across widths was
**8,851**. But the v2 cap of 10,000 leaves only **1.15×** headroom over the largest observed pass,
which is uncomfortably tight for a corpus 5× larger than the probe. The proposal is 50,000 (5.73×
headroom), which takes the IW record bound to 400,000,003. State it as margin so it is not sold as
solving a problem it did not solve.

### 1b — Drop `frontier_before` / `frontier_after` / `visited_after`

**Re-verified, not inherited.** `measure_record_size_bound.py` re-derives the reconstruction rules
against the real corpus: **25,984 BFS events across 24 streams, 0 violations on all four rules.**

```
R1  frontier_before[i] == [state_id[i]]
R2  frontier_after[i]  == frontier_after[i-1][1:] + enqueued(i)
R3  visited_after[i]   == sorted(visited_after[i-1] ∪ enqueued(i))
R4  visited_delta[i]   == enqueued(i)          (and {start_id} ∪ enqueued(0) at i = 0)
```

**R4 is new and it shrinks the shim.** The prior packet stated R1–R3 and described the reader shim as
rebuilding the certificate fields by fold. R4 says that is more work than necessary: `visited_delta`
— what `cgas_certificate_contracts` actually computes from `visited_after` — is exactly this event's
enqueued successor ids, which the event already carries. So:

| certificate field | source under v3 | needs a fold? |
| --- | --- | --- |
| `frontier_head` | `state_id`, verbatim (R1) | no |
| `visited_delta` | `enqueued` successor ids (R4) | no |
| `frontier_order_summary` | running FIFO fold (R2) | **yes — the only one** |
| `expanded_state` | `state_id`, already read directly | no |

**The consumer claim, audited.** The prior packet asserted `cgas_certificate_contracts.py` is the
only consumer of a full snapshot. `audit_v3_contract_surface.py` censuses every occurrence of the
five affected field names across `scripts/`, `tests/`, and `examples/` — **62 occurrences, all 62
classified** (census refreshed after the 2026-08-08 runner cutover; count unchanged), and it fails
loudly if the census and the classification ever disagree. It was 70
before slice 1 and 65 before slice 2. Slice 2 removed four IW emitter occurrences and added one more
explicit absence assertion; the remaining CGAS production reads are confined to legacy-v1 fixture
compatibility. Before slice 1, the claim had three refinements:

1. **It was two call sites in that module, not one.** `expected_certificate` (line 38) and
   `_prior_bfs_visited` (line 118). The second reads the *previous* expansion's `visited_after`, so a
   stateless per-event shim silently returns the wrong `visited_delta` for every event after the
   first. Slice 1 applies R4 directly and deletes `_prior_bfs_visited`.
2. **Two CGAS tests asserted on the raw fields:** `test_cgas_provenance.py:112` and
   `test_cgas_planner_semantic_parity.py:103`. Slice 1 changes them to assert the fields are absent.
3. **`examples/planning_benchmark_slice/` is a separate lineage.** It has its own BFS and IW
   emitters, its own `trajectory_schema` requiring these names, and 15 test assertions on them. It
   does not read CGAS streams and v3 does not touch it. 43 of the 62 occurrences are there, which is
   why a raw grep makes this change look much larger than it is.

`scripts/phase3/trace_contracts.py` does **not** cover BFS, so it is unaffected by 1b. It is very
much affected by 1c.

### 1c — Replace the truncated IW novelty snapshots with an emitted delta

The defect is now measured, not predicted. `MAX_IW_TRACE_NOVELTY_ITEMS = 200` clips the serialized
table (`local_iw_novelty.py:30`), so a trace-visible 200 means "≥200, unknown":

| n | runs | visible peak | true peak | understated, max | mean | saturated |
| --- | --- | --- | --- | --- | --- | --- |
| 4 | 8 | 200 | 229 | 4.5× | 1.5× | 3/8 |
| 8 | 8 | 200 | 2,681 | 13.4× | 9.0× | 8/8 |
| 12 | 8 | 200 | **12,185** | **60.9×** | 36.6× | 5/8 |

`seen_feature_delta` is the difference of two clipped snapshots
(`cgas_certificate_contracts.py:41-43`), so at width 2 it is unsound by those factors.

> **Correction to a recorded finding.** Commit `43a9d1b` says the trace understates "by up to 12×".
> That is the n=8 figure. The per-instance maximum at n=12 is **60.9×**. The hazard is five times
> worse than recorded, and it is worst at the object count that most determines corpus scale.

Emitting the delta removes the clip from the correctness path entirely. The delta is bounded by
`novelty_items(state, 2)` = |atoms| + C(|atoms|, 2), which does not grow with the search. Measured on
the existing IW streams, all 28,722 events scanned: **76.5 MB → 31.7 MB**, largest event
**6,455 B → 2,063 B**; worst-case projection at width 2 is **11,662 B**.

**A second consumer the plan's task line does not name.**
`scripts/phase3/trace_contracts.py:196` hard-requires *both* novelty snapshot keys on every IW expand
event, and lines 238–239 type-check them. This is the trace-**v1** traversal validator, and
`tests/phase3/test_cgas_fixture_archive.py` pins its behaviour against release digest
`3bc89431…6b3c` — one of the four immutable digests.

That is not a blocker, but it constrains the implementation: `_iw_required_fields` must **dispatch on
the trace contract version** rather than have its required set edited in place. Removing the two keys
from the required set keeps the pinned `iw_valid` fixture passing; adding `seen_feature_delta` as
unconditionally required would break it. Naming this now avoids discovering it against a frozen
digest mid-implementation.

### 1d — Add the per-record size bound v2 omitted

**Root cause, precisely.** Todo 1 bounded stream record count as
`1 + max_expansions · (1 + max_grounded_actions) + 1`. That formula prices **one record per
successor**. The emitter packs all successors of an expansion into **one** record
(`cgas_bfs.py:129-137`). So the `(1 + max_grounded_actions)` factor moved out of the count and into
the record — where nothing bounded it. The 2.25 TB is that factor, unbounded, multiplied by the
snapshot growth.

**The check is already half-built, on the wrong side.** `verify_trace_stream` refuses any line over
**16 MiB** (`cgas_trace_stream_v2.py:114`). `write_trace_stream` has no counterpart. A writer can
therefore produce a stream its own verifier will reject — and it discovers this only in the
post-write `verify_trace_stream(temporary)` call, after the bytes are on disk. The largest v2 record
this packet observed is 4,012,949 B, so it has not happened yet; it is reachable.

**Bytes or element counts? Both — but they are enforced in different places, and only bytes belong
in the writer.**

| | bytes | element counts |
| --- | --- | --- |
| enforceable at write time | **yes** — `cgas_trace_stream_v2.py:68` computes `line` and its length one statement before `handle.write(line)`; the record-count bound is already enforced five lines later at `:73`, so this is the same shape | no — the writer takes `Mapping[str, JSONValue]` and is schema-agnostic; checking `len(successors)` there pushes planner structure into the stream layer |
| bounds the actual failure mode | **yes** — disk, and the 16 MiB reader ceiling | no — atom strings are unbounded, so a count bound does not bound bytes |
| makes the constant *derived* rather than chosen | no | **yes** — this is what a `bounds_proof` entry is for |

The trap is deriving the byte bound from the policy's element ceilings. `max_grounded_actions` and
`max_grounded_atoms` are both 100,000, against observed maxima of **10 successors** and **23 atoms**.
A byte bound derived from those is ~10¹⁰ and enforces nothing.

**Proposal:**

- `MAX_EVENT_BYTES = 65,536`, enforced in `write_trace_stream` on `len(line)`, failing closed with a
  `TraceStreamError("trace_v3_record_size_exceeded", output)`. That is **5.6×** the largest projected
  v3 record (11,662 B, the width-2 IW worst case) and **256× below** the existing reader ceiling, so
  a stream the writer accepts is always one the verifier can read.
- Element-count bounds — `len(successors) ≤ max_grounded_actions`, `len(state_atoms) ≤
  max_grounded_atoms`, `len(seen_feature_delta) ≤ a + C(a, 2)` — asserted in the **emitters**, where
  the structure is known, and recorded in the migration packet's `bounds_proof` so the byte constant
  is auditable rather than a magic number.

### 1e — Release the v2 stream bytes

```
planner/status                  files        GiB      records
bfs/skipped_resource_limit        150    2101.38    1,500,000
bfs/success_full_trace            408     151.37      268,295
iw/failed_no_plan_extracted       445       0.07       26,961
iw/success_full_trace             113       0.00        1,761
TOTAL                           1,116    2252.82    1,797,017
```

Projected under v3: **1.7 – 6.6 GiB** (midpoint 3.3 GiB), from the min and max per-stream v3 mean
across 24 sampled streams. The plan's ~6.6 GB figure sits at the top of that range.

> **This makes the prior packet's decision 3 unnecessary.** That packet asked whether to stop
> persisting BFS traces for `skipped_resource_limit` runs, on the grounds that they are 93.3% of
> corpus bytes and can never contribute a row. Under v3 those 150 streams project to roughly 3.3 GiB
> in total. The 93.3% was entirely the snapshot fields. Recorded so it is not re-litigated as a
> separate decision.

### What v3 does not change

Quotas, selector constants, `EXPECTED_*`, the fixture release, the four immutable digests, the
characterization checkpoint chain, `max_expansions`, `max_plan_length`, the grounding ceilings,
stream framing, the hash chain, the trailer, or trace completeness for successful runs.

### Implementation shape, so the ask is priced honestly

| | |
| --- | --- |
| production modules touched | `cgas_bfs.py`, `local_iw.py`, `cgas_certificate_contracts.py`, `trace_contracts.py`, `cgas_trace_stream_v2.py`, plus a new `cgas_trace_contract_v3.py` |
| tests that go RED | `test_cgas_provenance.py` (lines 74, 112, 118) and `test_cgas_planner_semantic_parity.py` (lines 103, 184, 202, 203) — 7 assertion sites, all enumerated in `contract-surface.txt` |
| tests that must stay GREEN | `test_cgas_fixture_archive.py` (pinned to `3bc89431…`), `test_cgas_certificates.py`, `test_cgas_counterfactuals.py` |
| new artifacts | v3 migration packet + owner-approval template at **new paths** — `_require_compatible_destination` (`cgas_trace_contract_v2.py:197`) raises rather than overwrites, so v3 cannot publish over the v2 paths |
| obligation | `scripts/phase3/` is production code and carries RED/GREEN TDD |

**Decision requested:** authorize contract v3 as specified — width escalation on in policy, the three
reconstructible BFS fields dropped with an R2 fold shim, the IW novelty snapshots replaced by an
emitted delta behind version dispatch, `MAX_EVENT_BYTES` enforced at write time, the IW record-count
formula corrected for escalation — and authorize release of the 2,252.82 GiB of v2 stream bytes once
regeneration verifies.

---

## Decision 2 — off-plan expansion certificates: retained or not?

**v3 as specified does not foreclose this, and the owner should be told that rather than left to
infer it.** The three dropped BFS fields are exactly the reconstructible ones. Everything an off-plan
certificate needs — `state_atoms`, `successors`, `enqueued`, `actions_considered` — is retained
verbatim. Under R1/R4 a certificate can be built for **any** expansion in the stream, not only for the
expansions the replayed plan happens to visit. Deferring the harvesting question prejudices nothing.

### The measurement

On the 158 width-2 paired-exact instances, reproduced from the round-1 checkpoint and the Phase A
probe:

```
mean plan length                 5.23   (median 6, max 10)
mean BFS expansions / instance  274.8   (median 39)
off-plan ratio                   52.6x
certificate rows per instance    10.46 on-plan  →  549.6 off-plan
```

### What that actually buys, and what it does not

| harvest | bar | fail% | rows | **renders** | instances |
| --- | --- | --- | --- | --- | --- |
| on-plan | ≥10 | 40% | 3,197 | 1,598 | 306 |
| on-plan | ≥10 | 60% | 2,131 | 1,066 | 204 |
| on-plan | ≥30 | 40% | 9,590 | 4,795 | 917 |
| on-plan | ≥30 | 60% | 6,393 | 3,197 | 612 |
| off-plan | ≥10 | 40% | 3,197 | 1,598 | **6** |
| off-plan | ≥10 | 60% | 2,131 | 1,066 | **4** |
| off-plan | ≥30 | 40% | 9,590 | 4,795 | **18** |
| off-plan | ≥30 | 60% | 6,393 | 3,197 | **12** |

**Read the render column: it does not move.** Every certificate row needs an aligned pre-state PNG
(`cgas_certificates` requires `alignment.png_sha256` and `vision_status`), so renders track *rows*,
and the row target is set by the matrix, not by the harvesting mode. Off-plan harvesting cuts
enumeration, planning, and BFS tracing by ~50×. It cuts the external render bill by **nothing**.

That is a correction to how the 53× lever has been described. It is still decisive at the
conventional bar — it turns "the pilot is larger than production" into "the pilot is 18 instances" —
but the saving is in characterization, not in the part of the pipeline that depends on an external
service.

**And 4–18 instances is not a usable pilot.** The first-failure matrix stratifies by object count, so
6 instances gives ~2 per count and no structural-OOD coverage at all. An instance-diversity floor
binds independently of the observations-per-cell bar, and nothing in the repo states it.

### Recommendation

Three separable questions; only the first needs an answer today.

1. **Retain the capability.** Free — v3 already keeps everything required. No action needed beyond
   *not* dropping `successors`/`state_atoms` in some future size-reduction pass. Recommend: yes, and
   record it as a contract property so it is not optimised away later.
2. **Harvest off-plan certificates in the pilot.** Recommend: defer to Phase 3 planning. It is a
   dataset-construction choice, it interacts with the unstated stability bar, and it does not
   constrain v3.
3. **Size the pilot on off-plan yield alone.** Recommend: no. The instance-diversity floor and the
   flat render bill mean the honest pilot size is set by structural coverage, not by row count.

**Decision requested:** confirm (1) — that retaining per-expansion certificate data is a v3 contract
property — and confirm that (2) and (3) are deferred to Phase 3 planning rather than silently
assumed either way.

---

## Sequencing

1. Rule on decision 1. Nothing downstream can move until v3 is authorized: no Todo 3 round fits on
   disk under v2, and no width-2 corpus can carry a sound `seen_feature_delta`.
2. Rule on decision 2 item (1). Items (2) and (3) can wait; item (1) is a one-line contract property
   that is expensive to add back later.
3. Implement v3 under RED/GREEN TDD. Publish the v3 migration packet and owner-approval template to
   new paths; re-approve through `cgas_trace_contract_approval.py`.
4. Regenerate. Verify streams under v3 and check certificates rebuilt from them against the fixture
   release's semantics on overlapping instances (Gate 0b).
5. Release the 2,252.82 GiB. **After** regeneration verifies, not before.
6. `DECISION-pilot-provenance.md` becomes rulable once decision 2 and the stability bar are settled.

---

## Flagged, deliberately not in this packet

- **The first-failure-matrix stability bar (≥10 vs ≥30 observations per cell).** It changes the pilot
  size by 3× and it changes the answer to the companion packet. It is a Phase 3 planning question and
  a fourth decision here would risk the packet being held over an item that does not block v3.
- **An instance-diversity floor for the pilot.** Surfaced by decision 2's arithmetic above. Same
  reasoning: Phase 3 planning.
- **`EXPECTED_OBJECT_COUNTS[4]`.** Width 2 lifts the n=4 ceiling from 136 to **189** against a
  requirement of 190 — still short, now by one row. Decision 4 of revision 2 re-derives that constant
  at Phase 0c anyway, so this is sizing input rather than a new block.
- **The 13 pytest collection errors** in the `output_layout_*` / `organize_outputs_*` subsystem.
  Unrelated to CGAS; five production modules import `VIEW_ROOT`, which has never existed. Resolving it
  means implementing or deleting an abandoned subsystem — an owner scope call, not hygiene.

---

## What the worker did not do

- Did not implement v3, edit any contract, policy, quota, selector constant, or planner limit.
- Did not run a corpus round, advance a cursor, emit selector feedback, or create a checkpoint.
- Did not delete, truncate, migrate, or regenerate any of the 1,116 trace streams. All opens were
  read-only.
- Did not publish a v3 migration packet or approval artifact.
- Wrote only inside this directory, plus the stale-milestone correction to
  `doc/high_level_plans/research_execution_plan.md` the session brief asked for.

---

## Reproducing this packet

```bash
cd /data/scratch/projects/punim0478/sukaih/multimodality_on_planning
source ~/cd_vlaplan
P=.claude/evidence/cgas-trace-contract-v3/owner-decision-packet

python "$P/audit_v3_contract_surface.py"                                 # instant
python "$P/measure_record_size_bound.py" --head-events 3000 --bfs-samples 24   # ~80 s, ~700 MB read
python "$P/derive_pilot_scope.py"                                        # instant
```

All three are read-only and idempotent, and each writes a `.txt` and a `.json` beside itself.

Two are designed to fail rather than mislead:

- `audit_v3_contract_surface.py` exits non-zero if any occurrence of the five field names is
  unclassified, or if a classified line has moved. **The consumer table in decision 1b is only worth
  reading if that script exits 0.**
- `measure_record_size_bound.py` exits non-zero on a single R1–R4 violation anywhere. One violation
  invalidates decision 1b.

`measure_record_size_bound.py` is the one to run if you want to challenge this packet. Raising
`--head-events` and `--bfs-samples` widens the rule check and the size sample at linear cost; the
defaults check 25,984 events across 24 of 558 BFS streams.
