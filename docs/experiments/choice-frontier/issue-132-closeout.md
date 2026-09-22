# Issue #132 closeout — O3: audit-driven contract redesign (choice-sensitive additive arm)

Executed under the frozen protocol `configs/experiments/choice-frontier/choice-frontier-protocol-v1.json`
(protocol_id `choice-frontier-v1`, committed pre-launch in the design-freeze commit) with the
frozen schedule `docs/experiments/choice-frontier/schedule.json` (cap 12.0 GPU-h). All four
deliverables landed; every episode independently replayed; no prior published evidence touched.

## Results summary

### Contract redesign — the identity gate (primary deliverable)

The #130 identity audit re-ran as a pre-registered gate on the new arm's control episodes:
**18/18 (task, algorithm) control pairs divergent** — random_valid ≠ exact_reference on every
panel cell (`outputs/choice-frontier/v1/evaluation/identity-audit.json`). Final-audit verdict:
`CHOICE_SENSITIVE` (`outputs/choice-frontier/v1/evaluation/final-audit.json`, `ok: true`).

The old contract's finding (random ≡ exact on 48/48 pairs) is structurally impossible under the
new contract: the policy selects *which frontier state to expand next* from the runtime-owned
frontier; exact replays the reference expansion order and random picks a uniformly random valid
frontier state, so expansion orders diverge by construction wherever the frontier offers a real
choice. The preparation audit confirmed every corpus episode carries ≥1 decision with menu ≥ 2
(max menu 315).

In frequency terms on the frozen 9-task panel (18 cells): exact_reference 18/18, random_valid
32/90 across the five frozen seeds → paired contrast **random − exact = −0.644, 95% CI
[−0.856, −0.422]** — material. The instrument now measures choice quality.

### Frozen panel evaluation (144 episodes, all independently replayed, complete coverage)

| condition | goal rate | failures | invalid ops |
| --- | --- | --- | --- |
| exact_reference | **18/18** | — | 0 |
| learned_adapter | **7/18** | 11 × decision_budget_exhausted | **0** (every emitted choice schema-valid + in-menu) |
| pretrained_base | **0/18** | 18 × deterministic_invalid_operation (first call) | 18 |
| random_valid (5 frozen seeds) | **32/90** | 58 × decision_budget_exhausted | 0 |

Paired whole-problem bootstrap (seed 61813, 10000 resamples, percentile 95%, frozen conventions;
`outputs/choice-frontier/v1/evaluation/analysis.json`):

| contrast | mean Δ | 95% CI | material |
| --- | --- | --- | --- |
| learned − pretrained_base | **+0.389** | [+0.167, +0.611] | yes |
| learned − random_valid | **+0.033** | [−0.033, +0.133] | no |
| random − exact_reference | **−0.644** | [−0.856, −0.422] | yes |

Per-cell learned detail: solves depot, elevators, ferry (both algorithms) and storage-greedy;
budget-exhausts on 15puzzle (compact+expanded), blocksworld, towers_of_hanoi, visitall, and
storage-w3. Exact-path efficiency where solved: storage-greedy 3 expansions = reference (4
decisions incl. goal select); depot/elevators/ferry one extra expansion over reference.

### Read of the evidence

1. **Redesign goal met**: choice sensitivity is no longer unmeasurable — it is measured. The
   pre-registered failure condition (random ≡ exact persists) did not occur.
2. **Training teaches the contract**: 16 updates on the 512-record frozen corpus takes the base
   model from 0/18 (cannot emit one parseable in-menu choice) to 7/18 with a 100% valid-choice
   rate — the +0.389 over base is a contract-fluency gain.
3. **Choice quality above uniform is not yet demonstrated**: learned ≈ random (+0.033,
   non-material) on this panel at this recipe. The arm now exposes this as a measurable gap
   rather than an invariant — the follow-up lever is recipe/data scale, not contract surgery.

## Execution record

- **Corpus (CPU-only)**: 29 training tasks derived independently of the stored exact traces;
  1046 records (512 training + 11 diagnostic per algorithm), 3544 scenes; preparation audit PASS
  (58 episodes re-derived bit-exact, membership/token/image/headroom gates all true)
  (`outputs/choice-frontier/v1/preparation/visual-choice-frontier/{report,audit}.json`).
- **Training**: 2 cells (best_first_add_greedy, best_first_add_w3), frozen recipe seed 17,
  LoRA r64/α128, 16 updates, 512 records each; loss 4.89→0.31 / 4.94→0.32; audit-train PASS
  (`outputs/choice-frontier/v1/training/visual-choice-frontier/audit.json`).
- **Smoke gate**: 40/40 model calls accepted (rate 1.0 ≥ 0.5) before panel evaluation.
- **Replay**: 144/144 episodes independently replayed at finalize (`complete: true`, no missing
  bindings, no smoke-gated cells). A replay termination-settling bug affecting
  budget-exhausted episodes was fixed pre-launch in both replay paths (library + runner).
- **Scheduler jobs**: cf-v1-train-{0,1}, cf-v1-smoke, cf-v1-evaluate-models-{0,1},
  cf-v1-evaluate-controls-{0,1} — admitted against the frozen schedule; distinct MASTER_PORTs
  18814/18815 (train), ledger `outputs/choice-frontier/v1/budget.json`.

## Budget accounting

Realized **1.069 GPU-h** against the 12.0 GPU-h cap (ticket estimate 4–8 GPU-h): train-0 0.409 +
train-1 0.401 + smoke 0.052 + evaluate-models-0 0.180 + evaluate-models-1 0.028; controls CPU
(0.000). The two train attempts are recorded `failed` with hours retained: both cells completed
all 16 steps and saved final adapters, then crashed in post-save summary construction
(`dataset.records` missing on the new dataset class; fixed in the follow-up commit). Reports were
recovered from the `training_state.json` primary artifacts with provenance marked; no retraining
was needed and audit-train passes on the recovered reports.

## Evidence index (sha256, first 16)

```
5901ee176263fdc8  preparation/visual-choice-frontier/store.json
bc03a4143c84b016  preparation/visual-choice-frontier/report.json
e7108d68f0cf26e4  preparation/visual-choice-frontier/audit.json
e9ccfdd1928671f5  training/visual-choice-frontier/report-0.json
cc9f6a1256c915bf  training/visual-choice-frontier/report-1.json
3de0bad92f307765  training/visual-choice-frontier/audit.json
875f2b164d06898c  smoke/smoke.json
24687a50977487d1  evaluation/evaluation.json
bb22da5ec59c7c3a  evaluation/identity-audit.json
0796996ea5e36c5d  evaluation/analysis.json
bf1b2cc2aa98247d  evaluation/final-audit.json
f8ef6d69a62db5fc  budget.json
```

Root: `outputs/choice-frontier/v1/` (untracked per repo convention; episodes under
`evaluation/episodes/**` gzip). Frozen inputs: protocol + membership + 7 scheduler job CLIs under
`configs/experiments/choice-frontier/` (tracked).

## Documentation notes

- `examples/planning_benchmark_slice/choice_frontier{,_corpus,_views}.py` — the new trusted
  runtime session, corpus derivation/materialization, and prompt/image views (tracked).
- `scripts/run_choice_frontier.py` — the stage runner (validate → prepare → audit-prepare →
  train → audit-train → smoke → evaluate → finalize → identity-audit → analyze → audit-final).
- The replay termination-settling fix applies to budget-exhausted episodes in both replay paths;
  generation was unaffected (generation settles termination inside the request loop).
