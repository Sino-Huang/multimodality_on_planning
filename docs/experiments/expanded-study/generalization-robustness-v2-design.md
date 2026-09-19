# Generalization/robustness v2 protocol design

Date: 2026-09-19. Program `expanded-nine-day-v1`, branch `generalization_robustness`
(cap 32 GPU-h, spent 0.627256, remainder 31.372744334340094).

The v1 branch terminated `VALID_STOP` at its cost-admission gate (decision L4;
`outputs/expanded-study/v1/generalization-robustness/admission.json`). This document
freezes the legitimate-future-path successor required by the valid-stop ruling: a new
versioned protocol `expanded-generalization-robustness-v2`
(`configs/experiments/expanded-study/generalization-robustness-protocol-v2.json`), its
admission artifact `outputs/expanded-study/v1/generalization-robustness/admission-v2.json`
(schema `expanded_generalization_admission_v2`), and the recompute script
`scripts/qualify_expanded_generalization_v2.py`.

**Scope status.** v2 cannot close issues #96/#98. The v1 L4 `VALID_STOP` result is
retained; #96/#98 remain open. v2 is tracked under issue #124 (parent #38).

## Preserved qualification freeze

The 93/27 qualification freeze is preserved unchanged — no variant is replaced,
re-screened, re-audited, or dropped by outcome:

- suite `outputs/expanded-study/v1/generalization-robustness/suite.json`,
  sha256 `a20c30cc7b57a784e955626b07e4eea28a956964c300b6404467d956e092a742`
- qualification `outputs/expanded-study/v1/generalization-robustness/qualification.json`,
  sha256 `cb5badf72543e351fff2a822b0cf4e2fc3b754405f7ef1d1369118891921118f`

Derived-task scores do not exist and are never used to select scope. All selection
below uses only qualification reference-cost statistics, frozen probe timing, and
historical baseline behaviour.

## Frozen v2 estimand

Justification (independent of v1's completion-reservation bound, frozen before any
recomputation on outcomes):

- **Learned cells** — price per episode = runtime-enforced decision cap
  `2 x reference_costs(task, algorithm).decisions` x per-combo **max observed** probe
  call time (`probe.json per_combo_bounds[].max_observed_call_seconds`, i.e.
  `bound_seconds / 1.5`). Full cap is charged even though realized runs may stop
  earlier.
- **pretrained_base** — priced at exactly `1 call x per-combo max observed call time`
  per episode. Justification: on the frozen baseline panel the pretrained base
  terminated on an invalid first operation in every episode — 288/288 episodes,
  288 decisions (1 each), 288 invalid operations, 0 successes
  (`docs/experiments/expanded-study/baseline-evaluation.json`,
  `by_condition.pretrained_base`). The learned conditions (process_sft) used 3,918
  decisions over 288 episodes with 125 successes, so the base's single-decision
  termination is a measured behaviour, not an assumption.
- **Controls** — `random_valid` (5 frozen seeds) and `exact_reference` are CPU-only,
  priced at 0 GPU-h.
- **Aggregate** — matrix sum x 1.25 safety + measured worker overhead per planned
  worker job (2 jobs x 112.25402885861695 s, matching the v1 admission's two planned
  model workers) + **0** for probe spend: the probe 0.627256 GPU-h is already inside
  the ledger branch spend. The v1 admission's separate `+0.6273` GPU-h probe term was
  a recorded double-count nit and is not repeated.

Per-algorithm modality-summed max observed call seconds (learned cells):

| algorithm | text | visual | multimodal | sum |
| --- | ---: | ---: | ---: | ---: |
| best_first_add_greedy | 10.6555 | 16.7381 | 21.7181 | 49.1118 |
| best_first_add_w3 | 10.6915 | 16.7409 | 22.0228 | 49.4552 |

Per-variant estimand seconds =
`2*dec_greedy*49.11179646663368 + 2*dec_w3*49.45515729859471 + 98.56695376522839`
(the constant term is the base condition: 6 combos x 1 call).

**Not a completion guarantee.** The estimand is a budget reservation. The execution
contract hard-caps every GPU episode at its priced decision calls and declares up-front
that scheduler-enforced caps turn overruns into explicit missingness: failed or cutoff
attempts retain their ledger GPU hours and are reported per family and stratum, never
as silent scope reduction, and partial coverage does not satisfy the gate.

## Frozen matrix (cost-only justification)

Learned cells = `best_first_add_greedy` + `best_first_add_w3` x 3 modalities (6 cells).
Over the 93 eligible variants the dropped algorithms carry the highest reference
decision costs — bfs 7,348 and best_first_width 3,807 summed decisions versus
best_first_add_greedy 2,810 and best_first_add_w3 2,756 — and the slowest probe combos
(best_first_width__multimodal-state bound 98.12 s, bfs__multimodal-state 90.31 s).
Dropping them minimizes the priced matrix per admitted variant using qualification cost
statistics only. Controls per v1 rollout rules: pretrained_base (GPU, priced at 1 call),
random_valid (5 seeds 17/1013/2027/3041/4001), exact_reference; identical task sets
across conditions; greedy decoding.

Matrix totals at the admitted scope: 25 tasks x 12 GPU episodes (6 learned + 6 base)
= 300 GPU episodes; 25 x 36 = 900 CPU control episodes (150 exact_reference,
750 random_valid); 1,200 logical bindings.

## Frozen membership rule

Keep all five families represented. Within each family, rank eligible variants by
(`reference_costs.best_first_add_greedy.decisions + reference_costs.best_first_add_w3.decisions`,
then `variant_id`) and take the cheapest prefix of size k per family. Choose the single
uniform k maximizing total admitted variants subject to the frozen estimand fitting the
budget: first the branch remainder 31.372744334340094 GPU-h alone; only if no k fits may
a transfer of at most 11.89 GPU-h be proposed with exact arithmetic for design-gate
ratification. STOP and report instead of freezing a toy scope if even k=1 per family
(5 variants) does not fit, or if the largest remainder-feasible scope is under k=2 per
family (<10 variants).

### Ladder (uniform k over 5 families)

| k | variants | matrix GPU-h | required GPU-h | fits 31.3727 | fits 43.2627 |
| ---: | ---: | ---: | ---: | --- | --- |
| 1 | 5 | 2.6558 | 3.3822 | yes | yes |
| 2 | 10 | 6.3521 | 8.0025 | yes | yes |
| 3 | 15 | 11.0340 | 13.8549 | yes | yes |
| 4 | 20 | 16.1540 | 20.2549 | yes | yes |
| 5 | 25 | 23.5457 | **29.4945** | **yes** | yes |
| 6 | 30 | 33.7583 | 42.2603 | no (needs +10.8875) | yes |

Chosen: **k=5, 25 variants, required 29.494477929438386 GPU-h**, headroom
1.8782664049017086 GPU-h. **No transfer is proposed** — k=5 fits the branch remainder
alone, and the preference is to avoid touching recovery_reserve (already reduced to
11.89 for the second-backbone branch). k=6 would require a 10.88752309316433 GPU-h
transfer; that arithmetic is recorded in the admission artifact but not proposed.
The triviality guard is not triggered (25 >= 10 variants).

### Membership table (k=5 per family)

Membership list sha256 (canonical form: sha256 of
`json.dumps(sorted(variant_ids), sort_keys=True, separators=(",", ":""))`):
`008deaf35b710a941aa31d447d456b7d681c581760c28df4130c72a21adb2d60`.

| family | variant_id | dec greedy | dec w3 | estimand s |
| --- | --- | ---: | ---: | ---: |
| scale-up | ferry-scale-up-930011 | 13 | 13 | 2,661.31 |
| scale-up | ferry-scale-up-930010 | 26 | 26 | 5,224.05 |
| scale-up | grid-scale-up-930012 | 41 | 41 | 8,181.06 |
| scale-up | logistics-scale-up-930016 | 43 | 43 | 8,575.33 |
| scale-up | depot-scale-up-930005 | 76 | 67 | 14,190.55 |
| shifted-init | gripper-shifted-init-940014 | 6 | 6 | 1,281.37 |
| shifted-init | storage-shifted-init-940019 | 6 | 6 | 1,281.37 |
| shifted-init | elevators-shifted-init-940009 | 9 | 9 | 1,872.77 |
| shifted-init | depot-shifted-init-940004 | 12 | 12 | 2,464.17 |
| shifted-init | ferry-shifted-init-940011 | 16 | 16 | 3,252.71 |
| object-renaming | storage-object-renaming-950054 | 9 | 9 | 1,872.77 |
| object-renaming | elevators-object-renaming-950024 | 11 | 11 | 2,267.04 |
| object-renaming | ferry-object-renaming-950030 | 11 | 11 | 2,267.04 |
| object-renaming | 15puzzle-object-renaming-950000 | 12 | 12 | 2,464.17 |
| object-renaming | towers_of_hanoi-object-renaming-950060 | 15 | 15 | 3,055.58 |
| render-restyle | storage-render-restyle-950055 | 9 | 9 | 1,872.77 |
| render-restyle | elevators-render-restyle-950025 | 11 | 11 | 2,267.04 |
| render-restyle | ferry-render-restyle-950031 | 11 | 11 | 2,267.04 |
| render-restyle | 15puzzle-render-restyle-950001 | 12 | 12 | 2,464.17 |
| render-restyle | towers_of_hanoi-render-restyle-950061 | 15 | 15 | 3,055.58 |
| name-compression | storage-name-compression-950056 | 9 | 9 | 1,872.77 |
| name-compression | elevators-name-compression-950026 | 11 | 11 | 2,267.04 |
| name-compression | ferry-name-compression-950032 | 11 | 11 | 2,267.04 |
| name-compression | 15puzzle-name-compression-950002 | 12 | 12 | 2,464.17 |
| name-compression | towers_of_hanoi-name-compression-950062 | 15 | 15 | 3,055.58 |

Estimand matrix cost per family at k=5 (GPU-h, before safety):

| family | matrix GPU-h |
| --- | ---: |
| scale-up | 10.786747 |
| shifted-init | 2.820110 |
| object-renaming | 3.312945 |
| render-restyle | 3.312945 |
| name-compression | 3.312945 |
| **total** | **23.545692** |

Required = 23.545692 x 1.25 + 0.062363 = **29.494478 GPU-h** vs remainder
31.372744 → **decision PASS**, transfer request null, `ledger_mutated=false`.

The three perturbation families have identical prefix costs because P1/P2/P3 variants
of the same source problem carry identical reference costs (semantics-preserving
transforms; P3 references remain valid under renaming), and each prefix selects the
same five source problems.

## Analysis strata

Strata: domain, stratum-origin, variant-family. Name-compression (P3) is never pooled
with semantics-preserving variants: measured classifications on the frozen P3 family
are text-state 24/24 lossy, multimodal-state 18/24 lossy, visual-state 0/24 lossy, so
all admitted P3 text cells and most P3 multimodal cells are lossy and are reported as
a separate stratum. Missingness is reported per family and stratum. Other v1 analysis
rules carry over unchanged (paired whole-instance contrasts, random-valid frequency
aggregation over the five frozen seeds, bootstrap seed 90717, tiny-subgroup
descriptive-only rule, saturation rule per #54, no training-seed-variance claims).

## Budget block

- branch cap 32, spent 0.6272556656599044 (probe), remainder 31.372744334340094
- required 29.494477929438386 (matrix 23.54569166405799 + overhead 0.0623633493658983,
  x1.25 safety on matrix), headroom 1.8782664049017086
- transfer proposed: none; max available with transfer 43.2627443343401 recorded
- admission: decision PASS, outcome PASS, `ledger_mutated=false`

## Execution contract

Inherited from v1 with one addition: every GPU episode is hard-capped at its priced
decision calls (2 x reference decisions for learned cells, 1 call for
pretrained_base); cap hits, failures, and cutoffs are explicit missingness with ledger
hours retained, never silent scope reduction; partial coverage does not satisfy the
gate; independent replay of every completed episode; resume from partial journals; GPU
cutoff 2026-09-21T11:55:19Z unchanged.

## Phase-4 implementation notes (evaluation stage — not implemented)

`scripts/run_expanded_generalization.py` currently stops at the `admit` stage; no
run/evaluate stage exists. Minimal implementation path for the v2 evaluation stage,
reusing the baseline episode engine:

1. **Binding enumeration** — add an `evaluate-inputs` stage that mirrors
   `examples/planning_benchmark_slice/expanded_baseline.py:bindings()` /
   `assigned_bindings()`: enumerate membership (from `admission-v2.json`) x 2 learned
   algorithms x 3 modalities x conditions. GPU group: `learned_adapter`,
   `pretrained_base`; CPU group: `random_valid` (5 frozen seeds), `exact_reference`.
   Bindings carry the variant's materialized asset root
   (`outputs/expanded-study/v1/generalization-robustness/candidates/<family>/<variant_id>/`)
   instead of a panel task path. Extend bindings with a `seed` field so random_valid
   emits the 5 required episodes per cell (the baseline engine uses a single
   evaluation seed per binding).
2. **Episode execution** — reuse `run_binding()` almost verbatim
   (`expanded_baseline.py:173`): it already provides per-episode partial journals and
   resume (`_restore_events`/`_commit_pending`), deterministic greedy decoding via the
   passed `generate` callable, oracle-assisted random_valid, exact_reference through
   `generate=None` (`session.reference_output()`), and per-call measurements. Pass the
   v2 protocol's 6-entry `fixed_adapters` bank (instead of `readiness.json`) to
   `VisualPolicy` per modality, and map the condition name `learned_adapter` to the
   baseline engine's trained-arm name (`process_sft`) at the call site.
3. **Decision caps** — `VisualSession` already enforces the protocol's
   `reference_decision_multiplier` cap and records expansion/decision exhaustion as a
   valid unsuccessful episode; for v2 the base arm is additionally capped at 1 call per
   the estimand, and the estimand equation itself must be applied as the scheduler
   wall-clock cap so overruns become the declared explicit missingness.
4. **Inputs** — tasks load from the already-materialized `task-with-views.json`
   candidate assets (with `views/`), exactly as the probe worker does via
   `ExpandedTaskViews(..., read_only=True)`; no regeneration, screening, or audit reruns.
5. **Outputs** — write episodes under
   `outputs/expanded-study/v1/generalization-robustness/episodes/<modality>/<variant>/<algorithm>-<condition>.json.gz`
   following `binding_paths()`, then an aggregate `evaluation.json` (per-condition,
   per-cell, per-stratum summaries with the missingness block) and replay every
   completed episode via `independently_replay()` before publishing.
6. **Worker plan** — 2 GPU model workers (one per A100, distinct `MASTER_PORT` from
   the pool) plus CPU control workers, matching the admission's 2 planned worker jobs.

## Validation

- `python -m json.tool` clean on the protocol and admission-v2 JSON.
- Recompute script rerun is deterministic (byte-identical admission content).
- Ruff clean on the new script; `git status` shows only the intended additions;
  ledger untouched; no GPU work performed.
