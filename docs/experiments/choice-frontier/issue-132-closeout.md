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
storage-w3. (Efficiency wording corrected — see the erratum below; do not cite an expansion-parity
claim from earlier revisions of this section.)

### Read of the evidence

1. **Redesign goal met**: choice sensitivity is no longer unmeasurable — it is measured. The
   pre-registered failure condition (random ≡ exact persists) did not occur.
2. **Training teaches the contract**: 16 updates on the 512-record frozen corpus takes the base
   model from 0/18 (cannot emit one parseable in-menu choice) to 7/18 with a 100% valid-choice
   rate — the +0.389 over base is a contract-fluency gain.
3. **Choice quality above uniform is not established at the frozen cap**: the learned − random
   success contrast is +0.033 (non-material). Per the post-close review this establishes neither
   superiority nor equivalence (no pre-registered equivalence margin), and the contrast rests on
   one discriminative task. No remedy (recipe, data scale) is implied by this evidence; see the
   erratum below.

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

## Erratum (2026-09-23, post-close methodological review)

Two independent reviewers recomputed the stored episodes after close. The following corrects and
qualifies this closeout; every number below was re-verified against the stored episodes and the
frozen panel before recording. Full verdicts: `docs/experiments/choice-frontier/metric-adjudication-2026-09-23.md`.

1. **Correction (was wrong above)**: the earlier revision claimed "depot/elevators/ferry one extra
   expansion over reference". Stored `expansion_count` values: depot learned 8 vs exact 5,
   elevators 6 vs 4, ferry 7 vs 4 (+60/+50/+75%); only storage-greedy matches the reference (3 vs
   3). The earlier sentence conflated `decision_count` with `expansion_count` (exact spends R+1
   decisions because goal selection is uncharged). No efficiency parity exists. Notably, learned's
   expansion counts on those three tasks equal the frozen BFS reference counts exactly (8/6/7).
2. **Precision**: the 18 cells are 9 tasks x 2 algorithms; exact_reference and random_valid
   expansion sequences are identical across greedy and w3 on all 9 panel tasks, so the controls
   contribute 9 distinct tasks. The frozen bootstrap resamples cells; task-clustered CIs
   (recomputed, same seed/resamples): learned − random [0.000, +0.100] (degenerate — one task
   carries the signal), learned − exact [−0.889, −0.278], random − exact [−0.889, −0.333].
3. **Precision**: the learned − random +0.033 rests entirely on storage (random seed-frequency is
   1.0 on depot/elevators/ferry, 0.0 on 15puzzle x2/blocksworld/hanoi/visitall; only storage sits
   at 0.2). The discriminative subset is one task — below the frozen "< 8 cells descriptive-only"
   rule.
4. **New exploratory finding (post-hoc, CPU)**: the learned policy does not track its teacher
   on-policy. Across 132 multi-option decisions it selects the heap-head state 17.4% of the time
   against a chance rate of 26.9% (random_valid: 28.9% vs 26.2% on 636 decisions; exact: 100%),
   and emits the LAST menu label in 54.5% of decisions (first label 2.3%), while the teacher
   corpus targets the last label at 12.0% (chance 10.4%, 978 records). Per-decision menus are
   seeded-permuted, so a last-label habit is operationally a random picker: learned ≈ random is a
   behavioral finding (label-position shortcut), not a power artifact. Teacher-distillation
   framing: the imitation gap is the honest capability contrast (learned − exact = −0.611).
5. **Budget note**: the frozen decision budget is 2x reference expansions with goal selection
   uncharged, so exact's 18/18 holds by construction; exact must be read as the imitation target,
   not as ground-truth planning ability.

The primary deliverables stand unchanged: the contract is choice-sensitive (identity gate 18/18
divergent, random − exact = −0.644), training yields contract fluency (+0.389 over base, 0
invalid operations), and complete coverage with independent replay of 144/144 episodes. What
changes: no wording in this closeout or downstream may cite expansion parity, and any
choice-quality claim (either direction) requires the pre-registered follow-up metric set
(solve rate vs budget-multiplier curve, expansion-overhead ratio, cost suboptimality,
chance-corrected on-policy teacher agreement, discriminative-cell subset, algorithm-zoo
positioning) — see the follow-up ticket referenced from #131.
