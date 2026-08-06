# Research execution plan revision 2 - owner decisions - 2026-08-07

## Summary

`doc/high_level_plans/research_execution_plan.md` was rewritten as revision 2. Four owner decisions
were taken and are recorded here. The rewrite changes the phase ORDER, not the research question:
the calibration gate now precedes the production corpus, and a cheap planner probe precedes any
contract change.

Documentation-only session. No planner, contract, corpus, or selector constant was changed. All
four immutable digests remain exact and `reservoir_checkpoint_000002.json` remains absent.

## The finding that reframed the block

Todo 4's infeasibility proof is correct and stands (ceiling 136 < required 190). Its *diagnosis* was
not. Measuring exactness per planner rather than per pair:

| n | emitted | BFS-exact | IW-exact | paired | BFS rate | IW rate |
|---|---|---|---|---|---|---|
| 4 | 88 | 88 | 14 | 14 | **100.0%** | 15.9% |
| 8 | 129 | 89 | 23 | 23 | 69.0% | 17.8% |
| 12 | 64 | 33 | 16 | 16 | 51.6% | 25.0% |
| all | 281 | 210 | 53 | 53 | 74.7% | 18.9% |

IW-exact is a strict subset of BFS-exact in all three streams (14/14, 23/23, 16/16), so
**"paired-exact" is exactly "IW-exact"**. BFS alone solves 100% of the 4-object universe. The corpus
was never gated by a quota; it was gated by IW width-1 solvability on a domain that is not width-1
solvable. This is a planner-configuration defect, not a quota needing to be weakened.

## The four decisions

| # | Decision | Consequence |
|---|---|---|
| 1 | Raise IW to true iterative width 1→2 (rather than decoupling the BFS/IW arms) | Makes `width_decision` a real invariant; lifts the gating yield; invalidates the frozen policy digest and the 558 existing streams |
| 2 | Drop the three redundant BFS snapshot fields from persistence | 2.25 TB/round → ~6.6 GB; this is what makes decision 1 affordable |
| 3 | No starVLA. Three backbones, not four | Phase 4 moves to a standalone `planning_vlm/` package; generalization evidence without 4x runtime work |
| 4 | Re-derive corpus scale from experiment needs rather than holding 481 | `EXPECTED_*` selector constants become derived quantities |

Decisions 1 and 2 ship as **one** contract (v3) with **one** owner approval and **one** regeneration,
because both invalidate the existing streams.

## Two latent defects found while planning — both block decision 1

### `run_iterated_width` does not iterate

`scripts/phase3/local_iw.py` reads `local_iw_width` as a single fixed width and runs one pass. With
width frozen at 1, `width_decision` is the constant `"width_1_novel"` in every emitted certificate
(6/6 fixture rows). The proposal names "valid width transition" as an IW verifier invariant; at
fixed width there is no transition, so the field carries zero information. True 1→2 escalation is
what makes it meaningful — and is what the proposal actually describes.

`novelty_items(state, width)` already supports width >= 2, and `DEFAULT_LOCAL_IW_MAX_WIDTH` is 3,
so the novelty machinery needs no change; only the search loop does.

### The IW novelty table truncates at 200 entries

`MAX_IW_TRACE_NOVELTY_ITEMS = 200` in `scripts/phase3/local_iw_novelty.py`, applied by
`serialized_novelty_table` to the *accumulated* table, not to per-state items.

- At width 1 this never bites. Max table observed across all 558 IW streams: **150**.
- At width 2 the table is bounded by pairs of the atom universe: **325 / 3,321 / 14,365** for
  n=4/8/12. All exceed 200.

`cgas_certificate_contracts.py` computes `seen_feature_delta` as the difference of two truncated
snapshots, so at width 2 it would silently under-report novelty. **Same snapshot-versus-delta defect
as the BFS side; same fix.** Must be corrected in contract v3 before any width-2 corpus is built.

## Why calibration moved ahead of the corpus

Steps-per-instance equals plan length, because training transitions come from the replayed plan, not
from search expansions:

```
BFS plan length  mean 3.09  median 2  max 8   (n=53 paired-exact instances)
IW  plan length  mean 3.09  median 2  max 8
steps/instance   6.2 (both planners)

481 instances -> ~2,977 steps  (~2,490 train)
```

For SFT of an 8B VLM that is thin. Since the right corpus size is unknown until the calibration study
runs, and calibration only needs a pilot corpus, building the production corpus first risks paying
for the wrong size. The calibration gate is also the go/no-go for the whole method, so it should be
reached before the most expensive artifact, not after.

## Revised phase order

```
A    Planner configuration probe  (new, cheap, first)   -> Gate A
0b   Trace contract v3 + regeneration                   -> Gate 0b
3    Pilot corpus + calibration                         -> Gate 3  (HARD STOP / go-no-go)
0c   Production corpus at the derived scale             -> Gate 0c
2    Bounded live memory + route labels  (parallel with 0c)
4    CGAS model in planning_vlm/, 3 backbones
5    Main evaluation                                    -> Gate 5
6    Secondary generalization
```

Phase A re-materializes candidates at known raw ranks through the existing pure range API — no trace
persistence, no BFS, no cursor advance — runs IW with width escalation, and reports exact rate,
expansions, and peak novelty-table size per object count. Hours, not days. If width 2 does not lift
the rate materially, return to the owner with the decoupled-arms fallback.

## Status corrections to revision 1

Revision 1's "What is missing" list was stale. Actually complete: BFS-vs-GBFS provenance resolved
(canonical FIFO BFS); aligned renders, replay-valid transitions, semantic verifier, versioned
provenance all released at fixture scale (`data/planning_cgas_v1`, digest `3bc89431...6b3c`); typed
BFS/IW certificates in the released schema; one-invariant counterfactual generator with contract
tests; no-oracle-leakage contract that already forward-declares `route_label`, `scaffold_costs`,
`memory_payload`. 159 modules in `scripts/phase3/`, 109 test files in `tests/phase3/`.

**Revision 1's "Recommended First Milestone" is complete** except the memory stub. It was retired,
not repeated.

Genuinely missing: bounded live memory, route labels, any trained model, and a production-scale
corpus.

## Backbone selection

Recommended three: `Qwen/Qwen3-VL-8B-Instruct` (primary — training, calibration, main result),
`OpenGVLab/InternVL3_5-8B-HF`, `allenai/Molmo2-8B`. Dropped: `Zyphra/Zamba2-VL-7B`, as the highest
integration risk. To be confirmed at detailed-planning time. Production-plan Todo 14 loses its
Zamba2 half.

## Open items for the detailed planning session

1. Confirm which backbone is dropped.
2. Pilot corpus size for Phase 3, and whether it can reuse the 53 already-characterized paired-exact
   instances.
3. Whether v3 should also address `state_atoms` duplication inside successor rows — per-event, not
   quadratic, so a size question rather than a correctness one.
4. Disposition of the 2.25 TB of v2 streams: release immediately after v3 approval, or retain a
   sample as evidence. The width change invalidates them regardless.
5. Whether the structural-OOD signature requirement (>=10) survives re-derivation of the quota vector.

## Still binding

- No commits, no PRs. Never `git clean`; preserve the dirty shared worktree.
- `source ~/cd_vlaplan` for Python work.
- Do not implement contract v3 before an owner ruling on the packet; `scripts/phase3/` changes carry
  a RED/GREEN TDD obligation.
- Do not run a Todo 3 round under the v2 contract. It cannot produce a feasible selector result and
  cannot fit on disk (0.58 rounds).
- Do not recreate `.omo/boulder.json`.

## Related

- [[production-p0-owner-decision-packet-2026-08-06]] — the packet these decisions answer
- [[production-p0-todo4-infeasibility-2026-08-06]] — the proof, still valid
