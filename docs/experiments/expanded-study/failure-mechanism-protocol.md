# Failure-mechanism calibration analysis protocol (frozen)

Issue: #125 (parent #38, feeds #121). Program: expanded-nine-day-v1.
Status: **frozen before outcome computation**. The machine-readable copy is
[`configs/experiments/expanded-study/failure-mechanism-protocol.json`](../../../configs/experiments/expanded-study/failure-mechanism-protocol.json);
the two are committed together and the JSON is authoritative on key names.

This protocol recasts the historical proposal's RQ3 calibration question —
"when does multimodal context remain insufficient" — as a purely descriptive
first-failure analysis over already executed, independently replay-verified
episode evidence. No CGAS machinery is involved. Budget: 0 GPU-h, CPU only;
no new model outcomes, no retraining, no re-rendering.

## Fixed inputs

Only these replay-verified episode stores are mined. Episodes are
deduplicated by repository-relative path: an episode reused as a comparator
by another branch is mined once and carries all of its branch memberships.

| Branch | Issue | Episode store | Expected episodes | Replay anchor |
| --- | --- | --- | ---: | --- |
| expanded_baseline | #118 | `outputs/expanded-study/v1/baseline/episodes` | 1,152 | `baseline-evaluation.json`, `baseline-independent-replay.json` |
| generalization_robustness_v2 | #124 | `outputs/expanded-study/v1/generalization-robustness/episodes` | 1,200 | `outputs/.../generalization-robustness/evaluation.json`, `issue-124-closeout.md` |
| dagger | #84 | `outputs/expanded-study/v1/dagger/evaluation` (162 new) + reused comparators: unseen `bfs` arms from the baseline store (216), development `bfs` arms from `outputs/matched_modalities/v5/evaluation` (27) | 405 | `dagger-comparison.json` |
| successor_prediction | #89/#99 | `outputs/expanded-study/v1/successor/evaluation/episodes` | 90 | `successor-evaluation.json` |
| curriculum_modality | #119 | `outputs/expanded-study/v1/curriculum/evaluation` (243 new) + 324 comparators listed in `curriculum-evaluation.json` `comparator_provenance.sources` | 567 | `curriculum-evaluation.json` |

Exclusions: view bundles (`-views`, `/views/`); transfer, second-backbone and
historical v5 branches (outside the five named sources); v5 development
episodes enter only through their dagger/curriculum branch membership.

## Arm classification

- **learned**: `process_sft`, `learned_adapter`, `dagger_iteration_2`,
  `continued_sft_iteration_2`, `model_generated_successor`, and the nine
  curriculum arms `<modality>__<staged|shuffled|mixed_order>`.
- **base**: `pretrained_base`.
- **oracle_control**: `random_valid` (oracle-assisted valid-operation
  control; never a learned policy).
- **reference**: `exact_reference`, `trusted_successor` (reference bounds).

## Failure taxonomy

The first-failure event is the first event with `accepted == false` (verified
to always be the terminal event for invalid-operation terminations). Search
policies (baseline, generalization v2, dagger, curriculum and their
comparators) classify the first failure as:

1. `malformed_output` — raw output not parseable or missing the operation
   payload the algorithm schema requires.
2. `source_state_mismatch` — parsed action whose `source_state_id` differs
   from the current state.
3. `unknown_operator` — action name absent from every candidate set of the
   episode.
4. `inapplicable_grounded_action` — known operator whose grounded arguments
   are not applicable in the failing state.
5. `invalid_frontier_operation` — rejected BFS frontier operation
   (`operation_type`/`state_id` shape); the precise invariant is not
   recoverable from the log.
6. `other_invariant_violation` — parsed action passing the checks above but
   still rejected.
7. `expansion_budget_exhausted` — budget ran out with every emitted
   operation valid; failure position is the final decision count.

Successor-prediction episodes use the event's own
`verification.failure_kind` verbatim: `schema`, `static_context`,
`source_identity`, `action_identity`, `applicability`, `state_identity`,
`effect`. An explicit `unclassified` escape must remain zero; any nonzero
count is an analysis defect and is reported, never silently dropped.

## Grouping keys

- **Algorithm family**: `bfs`, `best_first_width`, `best_first_add_greedy`,
  `best_first_add_w3`.
- **Modality**: `text-state`, `visual-state`, `multimodal-state`; **arm
  class** and raw arm as above.
- **Horizon position**: first-failure decision index (0-based) over frozen
  buckets `0, 1, 2, 3-4, 5-8, 9-16, 17-32, 33+`; plus
  `horizon_ratio = first_failure_step / reference_decisions` against the same
  task+algorithm+modality `exact_reference` decision count in the same store
  (successor episodes carry their own `reference_decisions`); missing
  reference yields null and is counted.
- **Operation type**: action name of the first failing operation;
  `frontier:<operation_type>` for rejected BFS frontier operations; null for
  budget exhaustions.
- **Frontier/branching difficulty** at the first-failure event (final event
  for budget exhaustions): frontier size, branching factor (successor
  candidate count), visited/known-state count, and current g/h where the
  best-first schema logs them. Buckets: frontier size `0, 1-2, 3-5, 6-10,
  11+`; branching factor `0-1, 2-3, 4-6, 7-12, 13+`.

## Tiny-strata rule

Any stratum with fewer than 8 episodes is reported as descriptive-only,
listed explicitly in the analysis document, and never silently pooled across
strata or dropped.

## Missingness rule

Coverage and missingness are stated per source branch, including scope
reductions frozen by the source branches: generalization v2 evaluated 2 of 4
algorithm families, 25 of 120 variants and 6 of 12 adapters, with the base
arm capped at one call; successor covered 15 of 27 panel tasks; dagger is
`bfs` only; curriculum is `best_first_add_greedy` only.

## Claim discipline

Descriptive only — no causal claims beyond what the underlying verified
experiments established. `random_valid` is oracle-assisted; controls are
bounds, not learned ability. P3 name-compression lossy strata are reported
separately and never pooled with semantics-preserving variants. v5
development-task comparator episodes carry no `schema_version` but entered
only via replay-verified dagger/curriculum audits. All learned arms rest on
training seed 17 and evaluation seed 17; no seed-variance claims.

## Outputs

- `docs/experiments/expanded-study/failure-mechanism-matrix.json` —
  machine-readable matrix: input manifest (per-store digests), coverage, one
  record per failed episode, grouped cells and horizon/difficulty summaries.
- `docs/experiments/expanded-study/failure-mechanism-tables/*.csv` — summary
  tables.
- `docs/experiments/expanded-study/failure-mechanism-analysis.md` — the
  committed analysis document.
- `scripts/failure_mechanism_analysis.py` — regenerates all outputs;
  `--check` byte-compares against the published artifacts.
