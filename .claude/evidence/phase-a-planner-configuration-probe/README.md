# Phase A — planner configuration probe

**Date:** 2026-08-07 · **Gate:** A (reporting milestone, per the amended plan) · **Read-only**

Measures what IW yields at fixed width 1 versus true iterative width 1→2, per object count, over
the 281 candidate ranks already characterized in round 1.

## Result

```
   n  total     BFS    IW w1  IW w1->2    lift  inflation   slowest
   4     88  100.0%    15.9%     76.1%   +60.2      +0.03    0.009s
   8    129   69.0%    17.8%     45.7%   +27.9      +0.00    0.232s
  12     64   51.6%    25.0%     60.9%   +35.9      +0.00     3.32s
 all    281   74.7%    18.9%     58.7%   +39.8      +0.01     3.32s
```

**Width 2 lifts the IW-exact rate from 18.9% to 58.7%.** Every object count improves materially.

## Harness validation

The width-1 column reproduces the round-1 recorded rates **exactly** — 15.9 / 17.8 / 25.0 / 18.9%,
the same figures as the owner decision packet — with **0 of 281** re-runs disagreeing with the
recorded `iw_width_1` result. The checkpoint digest was verified identical before and after the run.

## Four findings

### 1. Plan-length inflation is essentially zero

157 of the 165 width-2 exact solutions match the recorded BFS optimal length exactly. Mean
inflation +0.013 actions, max +2, and every non-zero case is at n=4. Width-2 plans are usable as
training targets without a length penalty. This was previously unmeasured.

### 2. The 200-entry novelty cap is an active correctness hazard at width 2

`MAX_IW_TRACE_NOVELTY_ITEMS = 200` saturated in **16 of 24** instrumented instances — 3/8 at n=4,
8/8 at n=8, 5/8 at n=12. Revision 2 predicted this from the atom-pair bound; it is now observed on
real instances, and at n=4 as well, which the bound alone did not imply. `seen_feature_delta` is
computed as the difference of two truncated snapshots, so it would silently under-report novelty on
any width-2 corpus. **Contract v3 must fix this before any width-2 corpus is built.**

### 3. `EXPECTED_OBJECT_COUNTS[4] = 190` stays unsatisfiable even at width 2 — but only just

The 4-object universe is closed at 210 nontrivial identities; 88 were emitted in round 1.

```
width 1:  14 exact of 88   ceiling 14 + 122 = 136    expected ~33
width 2:  67 exact of 88   ceiling 67 + 122 = 189    expected ~160
requirement                                    190
```

The absolute ceiling rises from 136 to **189 — still one short of 190**, and the expected landing
point is ~160. Revision 2 decision 4 already re-derives this constant, so this is a sizing input
rather than a new block. It does mean width escalation alone does not rescue the original quota.

### 4. The IW ⊆ BFS subset relation appears to break, but that is an artifact of this probe

At n=12, width-2 IW is exact on 39 candidates against BFS's 33, and 7 candidates are IW(2)-exact
but not BFS-exact — which would contradict the relation the whole diagnosis rested on.

It does not. **All 7 recorded BFS runs terminated at exactly 10,001 expansions**, i.e. they tripped
the `max_expansions: 10_000` cap in `DEFAULT_LIMITS`. This probe raised IW's cap to 200,000 but read
BFS results from the round-1 checkpoint, which was measured under the 10,000 cap. The comparison is
therefore not matched, and **this probe cannot say whether the subset relation survives at width 2**.
Answering that needs a BFS re-run at a matched cap, which is a separate measurement.

Paired-exact under width 2, with that caveat: 67 / 59 / 32 for n=4/8/12, 158 overall.

## Cost

**330 seconds for all 281 candidates**, slowest single instance 3.32s at n=12. The plan's "hours,
not days" estimate was conservative by two orders of magnitude; no parallelism or subsampling was
needed. The instrumented runs (24 of them) dominate, because attaching a trace sink makes the
planner serialize the novelty table on every expansion.

## What this does not decide

Gate A is a reporting milestone, not a stop — its original pass condition referred forward to a
number Phase 3 produces two phases later. Width escalation ships regardless of these numbers,
because at fixed width 1 the `width_decision` invariant records no transition. What these numbers
inform is corpus sizing and whether decoupling the BFS/IW arms is *also* needed.

## Reproducing

```bash
source ~/cd_vlaplan
P=.claude/evidence/phase-a-planner-configuration-probe
python "$P/run_probe.py" --output "$P/result" --instrument 8    # ~6 min, full sweep
python "$P/run_probe.py" --output /tmp/smoke --sample 3         # ~11 s, smoke test
```

Read-only and idempotent. It verifies the round-1 checkpoint digest before and after, re-materializes
candidates through the pure range API (`cgas_candidate_space.build_candidate`), and asserts each
rebuilt candidate still matches its recorded `candidate_id`. It persists no trace, re-runs no BFS,
advances no cursor, and writes nothing outside `--output`.

## Method notes

- **BFS is read, not re-run.** BFS-exactness and BFS plan length come from
  `reservoir_checkpoint_000001.json` — the same immutable bytes the infeasibility proof used.
- **The expansion cap is raised to 200,000** for IW only, above the width-2 novelty-table bound
  (325 / 3,321 / 14,365 for n=4/8/12), so an exhausted search is a planner result rather than a cap
  artifact. `DEFAULT_LIMITS` is copied, never mutated. See finding 4 for what this asymmetry costs.
- **"Exact" is not optimality.** It means solved by pure novelty search with no `plan_recovery`
  fallback and a valid replay, per `cgas_characterization_rows._planner_record`. That is why
  finding 1 measures length separately.
- **Escalation is opt-in** (`local_iw_escalate`). See the commit that added it for why.
