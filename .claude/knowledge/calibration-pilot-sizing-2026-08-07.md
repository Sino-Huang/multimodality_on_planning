---
name: calibration-pilot-sizing
description: Revision 2's "pilot rather than full corpus" premise is bar-dependent — sound at >=10 obs/cell, false at >=30; off-plan expansions are the lever that settles it.
metadata:
  type: project
---

Revision 2 moved the calibration gate ahead of the production corpus on the grounds that
"it needs a pilot corpus rather than the full one". That premise was never tested. Resolved
2026-08-07 by arithmetic over the round-1 checkpoint and the Phase A result.

**Answer: the premise is conditionally sound, and the condition — the stability bar for the
first-failure matrix — has never been stated. It should be stated before Phase 3 starts.**

## The matrix

7 certificate invariant families, from `cgas_certificate_contracts.step_schema`:

- BFS: `frontier_head`, `frontier_order_summary`, `visited_delta`, `expanded_state`
- IW: `novelty_tuple`, `seen_feature_delta`, `width_decision`

Against 3 object counts (4/8/12) that is **21 cells**. Held-out fraction is dev 39 + test 40 of
481 = 16.4%.

## Sizing, at 10.4 steps per instance

| bar | assumed failure rate | failures | held-out steps | total steps | instances |
|---|---|---|---|---|---|
| >=10/cell | 40% | 210 | 525 | 3,197 | **306** |
| >=10/cell | 60% | 210 | 350 | 2,131 | **204** |
| >=30/cell | 40% | 630 | 1,575 | 9,590 | **919** |
| >=30/cell | 60% | 630 | 1,050 | 6,393 | **613** |

Production target is 481 instances. So:

- At **>=10 observations per cell**, the pilot is 204–306 instances — genuinely smaller than the
  production corpus, and revision 2's reorder holds.
- At **>=30 per cell**, the conventional bar for a stable rate, it is 613–919 — *larger* than the
  production target. The reorder would buy nothing, because you would be building the production
  corpus in order to run the gate that was supposed to size it.

The failure-rate column is an assumption, not a measurement; nothing in the repo constrains it yet.
The bar is the owner's call and is the single number that decides whether the reorder is worth it.

## Width escalation already improved the picture

Steps per instance equals plan length because training transitions come from the replayed plan.
Under width-1 paired-exactness that was mean 3.09 (n=53, reproduced exactly from the checkpoint),
giving ~6.2 steps/instance. Under width-2 paired-exactness the set grows to 158 instances **and
admits longer plans** — mean 5.22, median 6, max 10 — giving **~10.4 steps/instance**.

481 instances therefore now yields ~5,000 steps rather than the ~2,977 revision 2 recorded. The
"thin for SFT of an 8B VLM" concern is materially reduced, though not eliminated.

## The lever that actually settles this

BFS expands a mean of **275 states per instance** against a 5.22-step plan — a **53x ratio**.
Harvesting certificate targets from off-plan expansions rather than only from the replayed plan
multiplies steps per instance by roughly that factor, which puts every row of the table above within
reach of 50–100 instances. The plan already names this lever (Phase 3 scale note) but defers it.

**This should be decided before Phase 0b, not during Phase 3**, because it is a question about what
the trace contract must retain. Good news: contract v3 as specified does not foreclose it. The three
fields being dropped — `frontier_before`, `frontier_after`, `visited_after` — are exactly the
reconstructible ones (rules R1–R3), and the per-event data off-plan certificates need
(`state_atoms`, `successors`, `enqueued`) is retained. So v3 can ship as specified without
prejudging this.

## Recommendation

1. State the stability bar for the first-failure matrix before Phase 3 is planned. It decides
   whether the calibration-before-corpus reorder pays for itself.
2. Decide the off-plan-expansion question before Phase 0b ships. If off-plan certificates are in,
   the pilot is small under any bar and the reorder is clearly right.
3. Do not treat "pilot < production" as established. At a conventional bar it is false.

## Related

- [[phase-a-width-escalation-result]] — the width-2 measurement these numbers rest on
- [[research-execution-plan-revision-2-2026-08-07]] — the reorder this tests, and its open item 2
- [[cgas-p0-trace-corpus-oversized]] — the R1–R3 reconstruction that keeps off-plan harvesting open
