---
name: phase-a-width-escalation-result
description: Phase A probe result — width 2 lifts IW-exact 18.9% to 58.7%, plans stay optimal-length, the 200-entry novelty cap saturates, and n=4 still cannot reach 190.
metadata:
  type: project
---

Phase A ran on 2026-08-07 over all 281 round-1 candidate ranks. Full write-up and re-runnable script:
`.claude/evidence/phase-a-planner-configuration-probe/`.

```
   n  total     BFS    IW w1  IW w1->2    lift  inflation
   4     88  100.0%    15.9%     76.1%   +60.2      +0.03
   8    129   69.0%    17.8%     45.7%   +27.9      +0.00
  12     64   51.6%    25.0%     60.9%   +35.9      +0.00
 all    281   74.7%    18.9%     58.7%   +39.8      +0.01
```

Harness validated: the width-1 column reproduces the recorded round-1 rates exactly, 0/281 disagreements.

**Four things worth carrying forward.**

1. **Plan length does not degrade.** 157 of 165 width-2 solutions match BFS optimal length exactly;
   mean inflation +0.013, max +2, all non-zero cases at n=4. Width-2 plans are usable training
   targets. Previously unmeasured.

2. **`MAX_IW_TRACE_NOVELTY_ITEMS = 200` saturates in 16 of 24 instrumented instances** — including
   3/8 at n=4, which the atom-pair bound alone did not predict. Confirms the hazard revision 2
   flagged. Contract v3 must replace truncated snapshots with emitted deltas before any width-2
   corpus. See [[research-execution-plan-revision-2-2026-08-07]].

3. **`EXPECTED_OBJECT_COUNTS[4] = 190` is still unsatisfiable, by one row.** The n=4 universe is
   closed at 210; at the measured 76.1% the absolute ceiling is 67 + 122 = 189 and the expected
   landing is ~160. Width escalation alone does not rescue the original quota — but decision 4
   re-derives it anyway, so this is sizing input, not a block.
   See [[cgas-p0-four-object-quota-infeasible]].

4. **Do not read the probe as breaking IW-exact ⊆ BFS-exact.** At n=12 it shows 39 IW(2)-exact vs 33
   BFS-exact, but all 7 offending BFS runs stopped at exactly 10,001 expansions — the
   `max_expansions: 10_000` cap. The probe raised IW's cap to 200,000 and read BFS from the round-1
   checkpoint, so the comparison is unmatched. Whether the subset relation survives at width 2 needs
   a BFS re-run at a matched cap and is still open.

**Cost:** 330s for 281 candidates, slowest instance 3.3s. The plan's "hours, not days" was
conservative by two orders of magnitude.

**Implementation:** escalation in `scripts/phase3/local_iw.py` is **opt-in** via a
`local_iw_escalate` limit. Inferring it from `local_iw_max_width > local_iw_width` silently converted
existing fixed-width callers into escalating ones — `_blocksworld_medium_limits()` in
`tests/phase3/test_phase3_blocksworld_medium_traces.py` leaves `local_iw_max_width` unset, so it
falls back to 3. The frozen approved policy and all 558 existing streams are unaffected either way,
since `DEFAULT_LIMITS` pins `local_iw_max_width: 1`.
