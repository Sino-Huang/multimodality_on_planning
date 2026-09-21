# Issue #128 closeout — image-only state/history observation arms (visual-nomem, visual-seq)

Ask: train and evaluate new visual-native adapters (`visual-nomem-state`,
`visual-seq-state`) on a prospectively frozen protocol and admission, reusing
the existing replay/search machinery and the frozen task panels, under a
pre-registered admission feasibility gate. Executed under an explicitly
authorized follow-up window (`followup-native-arms-v1`, 12 GPU-h cap) after
the expanded-nine-day-v1 GPU cutoff.

## Outcome: VALID_STOP (pre-registered admission feasibility gate)

**Both arm gates failed; no training or evaluation was launched, per the
frozen rule.** The pretrained base emitted **0/18 schema-valid grounded first
actions under each arm contract** (frozen minimum: ≥ 9/18 = 0.5). The frozen
admission artifact records `decision: VALID_STOP` with both `arm_gates: FAIL`
— not a budget stop: the recomputed estimand (6.90 GPU-h required, minimum
meaningful scope 2.34 GPU-h) fit the authorized 12 GPU-h window with margin.

## What was executed, in the frozen order

1. **Freeze before any launch** (commits `12c623e`, `1e3d773`):
   `configs/experiments/native-arms/native-arms-protocol.json` (authoritative),
   `docs/experiments/native-arms/native-arms-design.md`, follow-up schedule
   `docs/experiments/native-arms/schedule.json`, the contract/corpus/runner
   code (`native_arm_views.py`, `native_arm_corpus.py`,
   `scripts/run_expanded_native_arms.py`) and two declared code changes that
   loosen no existing frozen gate (`train_visual` optional `dataset_factory`
   hook, byte-identical default; shared-scheduler explicit `--schedule`
   follow-up override, default behavior unchanged — old ledger/cutoffs
   untouched). The user had pre-authorized GPU use for this window and
   instructed not to wait; the first GPU launch happened only after the
   frozen design was committed and pushed. `validate` stage: **PASS** (all
   sha-pinned dependencies, membership sha256 `20ea888d…e854` re-derived from
   the frozen #126 protocol, code/protocol legend/K/recipe byte-match).
2. **CPU corpus materialization** (both arms, `prepare` stage): the frozen v5
   membership (512 training + 27 diagnostic records per algorithm ×
   `best_first_add_greedy`/`best_first_add_w3` = 1,078 records per arm, 29
   tasks) re-materialized under the new contracts. `visual-seq-state`
   rasterized **263 additional history states** from retained catalog VFG
   vector stages (the same unlabelled-128px rendering call as v5; no new
   pipeline). Structural qualification **PASS** for both arms: removed
   payload keys absent from every serialized user text, frame counts ≤ K=8
   (window histogram 0…8, 453/1078 records at the full 8), windows strictly
   past and visit-ordered, every image reference resolved, candidate menus
   equal to the trusted grounded order, max observed input 3,036 (nomem) /
   3,462 (seq) tokens against the 32,384 gate, targets unchanged.
3. **Admission feasibility probe** (first and only GPU use; two scheduler
   jobs `na-v1-probe-nomem` GPU 0 / `na-v1-probe-seq` GPU 1, distinct
   MASTER_PORTs 18806/18807, both terminal `succeeded`, audit hooks rc 0):
   pretrained base (no adapter, hard 1-call cap), first decision of each of
   the 9 frozen panel tasks × both algorithms under each arm's own contract.
   Results: **0/18 accepted under `visual-nomem-state`; 0/18 accepted under
   `visual-seq-state`**; max observed call 7.07 s / 6.90 s; every rejection is
   a `deterministic_invalid_operation` — the base emits planner-flavoured
   pseudo-code (e.g. `h_add("go-out", "hoist0", "depot48-2-2", "loadarea")`)
   instead of the strict `{"action": {name, args}, "source_state_id"}`
   operation. Full per-call evidence: `outputs/native-arms/v1/probe/<arm>/`
   (36 gzipped episode journals + probe.json).
4. **Technical soundness check (CPU, deterministic)**: a strict operation
   built from the reduced payload's own unscored menu plus
   `current.state_id` is **accepted** by the trusted runtime under both arm
   contracts (successor registered) — the contracts are executable and
   learnable; the 0/18 is genuine base non-compliance, not a machinery
   defect. This is consistent with the frozen baseline evidence (0/288
   first-decision invalid for the pretrained base under the full contract,
   `docs/experiments/expanded-study/baseline-evaluation.json`).
5. **Admission recompute** (`admit` stage, from preparation reports, probe
   evidence and frozen bases only): `decision: VALID_STOP`
   (`outputs/native-arms/v1/admission.json`). Per the frozen rule — "below
   threshold, that rung declares VALID_STOP with the probe evidence
   published, and visual-seq-state proceeds only if its own gate passes" —
   both rungs stopped; no partial-outcome harvesting.

## Budget

Follow-up window ledger `outputs/native-arms/v1/budget.json` (program
`followup-native-arms-v1`, branch `native_arms`, cap 12 GPU-h): actual spend
**0.0926 GPU-h** (two probe jobs, 0.0460 + 0.0466), no transfer from or to
expanded-nine-day-v1, whose ledger, caps and cutoffs are untouched. All
materialization, qualification, admission and analysis ran CPU-only.

## Interpretation (recorded, not a new claim)

The pre-registered gate asked whether the pretrained base can emit
schema-valid grounded actions at all under contracts whose textual scaffold
is reduced to an unscored menu. It cannot — even with the payload an order of
magnitude simpler than the frozen full contract, the base produced zero
format-compliant operations. Format compliance, not payload complexity, is
the base's barrier; the matched-modalities evidence shows process-SFT is what
teaches the output contract. The tickets' stronger question — whether a
*trained* policy can operate with state facts and search history carried only
by images — therefore remains open behind the pre-registered gate: under this
protocol the rung legitimately stops here, and any future attempt needs a new
prospective protocol whose gate does not condition on pretrained-base format
compliance (e.g. a post-SFT feasibility probe on a held-out split), ratified
before launch.

## Scope discipline

Strictly additive: no frozen arm, protocol, checkpoint or published evidence
was modified; no retraining, no outcome-selected variants, no favourable
replacements; the expanded-nine-day-v1 ledger and all closed-ticket verdicts
are untouched. Does not close or modify #85-era baselines, #123/#124, #126,
#127 or any other ticket. #128 closes on this verified VALID_STOP evidence:
the frozen decision procedure was executed exactly, and its pre-registered
gate fired on published probe evidence.
