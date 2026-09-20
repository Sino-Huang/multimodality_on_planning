# Failure-mechanism calibration analysis from replayed episodes

Issue: #125 (parent #38, feeds the #121 manuscript analysis section).
Protocol: frozen as
[`failure-mechanism-protocol.md`](failure-mechanism-protocol.md) +
[`configs/experiments/expanded-study/failure-mechanism-protocol.json`](../../../configs/experiments/expanded-study/failure-mechanism-protocol.json)
**before** any outcomes were computed from the logs, per the issue's execution
rules. This document is descriptive only: it mines existing, independently
replay-verified episode evidence and makes no causal claim beyond what the
underlying verified experiments established. Budget: 0 GPU-h, CPU only; no new
model outcomes, no retraining, no re-rendering.

## Inputs, coverage and missingness

905 failed episodes were mined out of
2910 unique replay-verified episodes
(3414 branch bindings across the five
named sources; episodes reused as comparators are mined once).

| store | files | sha256 (prefix) |
| --- | --- | --- |
| baseline | 1152 | `0b36fe642e1c0042…` |
| curriculum_new | 243 | `f2cf00c2cd417f7d…` |
| dagger_new | 162 | `90bb4fba6e295771…` |
| genrob | 1200 | `be0307afa0b65efb…` |
| successor | 90 | `9af4b9b5a3793dfc…` |
| v5 | 63 | `e0a531a89879212d…` |

| branch | issue | expected | consumed | missing | failed | succeeded |
| --- | --- | --- | --- | --- | --- | --- |
| expanded_baseline | #118 | 1152 | 1152 | 0 | 499 | 653 |
| generalization_robustness_v2 | #124 | 1200 | 1200 | 0 | 172 | 1028 |
| dagger | #84 | 405 | 405 | 0 | 265 | 140 |
| successor_prediction | #89/#99 | 90 | 90 | 0 | 44 | 46 |
| curriculum_modality | #119 | 567 | 567 | 0 | 103 | 464 |

Replay anchors re-verified while mining:

| anchor check | outcome |
| --- | --- |
| baseline evaluation PASS with 1,152 bindings | PASS |
| baseline independent replay 1,152/1,152 | PASS |
| generalization v2 evaluation PASS with 1,200/1,200 replayed | PASS |
| dagger comparison PASS with 405 episodes replayed | PASS |
| successor evaluation PASS with 90/90 replayed | PASS |
| curriculum evaluation PASS with 243 model + 324 comparator bindings | PASS |

Missingness by construction, stated per source branch:

- **generalization_robustness_v2 (#124)** evaluated only the two additive
  best-first families (not `bfs`/`best_first_width`), 25 of the 120-variant
  suite (k=5 cheapest prefix per family) and 6 of the 12 frozen adapters; the
  base arm was capped at one model call per episode. These were frozen
  cost-only decisions of the source branch, not outcome-based exclusions.
- **successor_prediction (#89/#99)** covered 15 of the 27 panel tasks (3
  development + 12 outcome-blind unseen); the full 24-task panel was priced
  infeasible by the source branch and remains missing.
- **dagger (#84)** is `bfs` only; **curriculum (#119)** is
  `best_first_add_greedy` only; **baseline (#118)** is the only branch
  covering all four algorithm families.
- Development-panel comparators for dagger/curriculum are v5 episodes without
  a `schema_version`; they entered only through the replay-verified
  dagger/curriculum audits.

Per-branch panel strata (episodes and failures per branch x panel x modality x
arm; `tiny` marks strata below the frozen 8-episode limit):

| branch | panel | modality | arm | episodes | failures | tiny |
| --- | --- | --- | --- | --- | --- | --- |
| curriculum_modality | development | multimodal-state | exact_reference | 3 | 0 | yes |
| curriculum_modality | development | multimodal-state | multimodal-state__mixed_order | 3 | 0 | yes |
| curriculum_modality | development | multimodal-state | multimodal-state__shuffled | 3 | 0 | yes |
| curriculum_modality | development | multimodal-state | multimodal-state__staged | 3 | 0 | yes |
| curriculum_modality | development | multimodal-state | pretrained_base | 3 | 3 | yes |
| curriculum_modality | development | multimodal-state | process_sft | 3 | 0 | yes |
| curriculum_modality | development | multimodal-state | random_valid | 3 | 0 | yes |
| curriculum_modality | development | text-state | exact_reference | 3 | 0 | yes |
| curriculum_modality | development | text-state | pretrained_base | 3 | 3 | yes |
| curriculum_modality | development | text-state | process_sft | 3 | 1 | yes |
| curriculum_modality | development | text-state | random_valid | 3 | 0 | yes |
| curriculum_modality | development | text-state | text-state__mixed_order | 3 | 0 | yes |
| curriculum_modality | development | text-state | text-state__shuffled | 3 | 0 | yes |
| curriculum_modality | development | text-state | text-state__staged | 3 | 1 | yes |
| curriculum_modality | development | visual-state | exact_reference | 3 | 0 | yes |
| curriculum_modality | development | visual-state | pretrained_base | 3 | 3 | yes |
| curriculum_modality | development | visual-state | process_sft | 3 | 0 | yes |
| curriculum_modality | development | visual-state | random_valid | 3 | 0 | yes |
| curriculum_modality | development | visual-state | visual-state__mixed_order | 3 | 0 | yes |
| curriculum_modality | development | visual-state | visual-state__shuffled | 3 | 0 | yes |
| curriculum_modality | development | visual-state | visual-state__staged | 3 | 0 | yes |
| curriculum_modality | unseen | multimodal-state | exact_reference | 24 | 0 |  |
| curriculum_modality | unseen | multimodal-state | multimodal-state__mixed_order | 24 | 0 |  |
| curriculum_modality | unseen | multimodal-state | multimodal-state__shuffled | 24 | 0 |  |
| curriculum_modality | unseen | multimodal-state | multimodal-state__staged | 24 | 2 |  |
| curriculum_modality | unseen | multimodal-state | pretrained_base | 24 | 24 |  |
| curriculum_modality | unseen | multimodal-state | process_sft | 24 | 3 |  |
| curriculum_modality | unseen | multimodal-state | random_valid | 24 | 0 |  |
| curriculum_modality | unseen | text-state | exact_reference | 24 | 0 |  |
| curriculum_modality | unseen | text-state | pretrained_base | 24 | 24 |  |
| curriculum_modality | unseen | text-state | process_sft | 24 | 2 |  |
| curriculum_modality | unseen | text-state | random_valid | 24 | 0 |  |
| curriculum_modality | unseen | text-state | text-state__mixed_order | 24 | 2 |  |
| curriculum_modality | unseen | text-state | text-state__shuffled | 24 | 3 |  |
| curriculum_modality | unseen | text-state | text-state__staged | 24 | 2 |  |
| curriculum_modality | unseen | visual-state | exact_reference | 24 | 0 |  |
| curriculum_modality | unseen | visual-state | pretrained_base | 24 | 24 |  |
| curriculum_modality | unseen | visual-state | process_sft | 24 | 2 |  |
| curriculum_modality | unseen | visual-state | random_valid | 24 | 0 |  |
| curriculum_modality | unseen | visual-state | visual-state__mixed_order | 24 | 1 |  |
| curriculum_modality | unseen | visual-state | visual-state__shuffled | 24 | 0 |  |
| curriculum_modality | unseen | visual-state | visual-state__staged | 24 | 3 |  |
| dagger | development | multimodal-state | continued_sft_iteration_2 | 3 | 2 | yes |
| dagger | development | multimodal-state | dagger_iteration_2 | 3 | 1 | yes |
| dagger | development | multimodal-state | exact_reference | 3 | 0 | yes |
| dagger | development | multimodal-state | process_sft | 3 | 3 | yes |
| dagger | development | multimodal-state | random_valid | 3 | 1 | yes |
| dagger | development | text-state | continued_sft_iteration_2 | 3 | 2 | yes |
| dagger | development | text-state | dagger_iteration_2 | 3 | 3 | yes |
| dagger | development | text-state | exact_reference | 3 | 0 | yes |
| dagger | development | text-state | process_sft | 3 | 3 | yes |
| dagger | development | text-state | random_valid | 3 | 1 | yes |
| dagger | development | visual-state | continued_sft_iteration_2 | 3 | 3 | yes |
| dagger | development | visual-state | dagger_iteration_2 | 3 | 2 | yes |
| dagger | development | visual-state | exact_reference | 3 | 0 | yes |
| dagger | development | visual-state | process_sft | 3 | 2 | yes |
| dagger | development | visual-state | random_valid | 3 | 1 | yes |
| dagger | unseen | multimodal-state | continued_sft_iteration_2 | 24 | 24 |  |
| dagger | unseen | multimodal-state | dagger_iteration_2 | 24 | 23 |  |
| dagger | unseen | multimodal-state | exact_reference | 24 | 0 |  |
| dagger | unseen | multimodal-state | process_sft | 24 | 24 |  |
| dagger | unseen | multimodal-state | random_valid | 24 | 9 |  |
| dagger | unseen | text-state | continued_sft_iteration_2 | 24 | 24 |  |
| dagger | unseen | text-state | dagger_iteration_2 | 24 | 24 |  |
| dagger | unseen | text-state | exact_reference | 24 | 0 |  |
| dagger | unseen | text-state | process_sft | 24 | 24 |  |
| dagger | unseen | text-state | random_valid | 24 | 9 |  |
| dagger | unseen | visual-state | continued_sft_iteration_2 | 24 | 23 |  |
| dagger | unseen | visual-state | dagger_iteration_2 | 24 | 24 |  |
| dagger | unseen | visual-state | exact_reference | 24 | 0 |  |
| dagger | unseen | visual-state | process_sft | 24 | 24 |  |
| dagger | unseen | visual-state | random_valid | 24 | 9 |  |
| expanded_baseline | final | multimodal-state | exact_reference | 96 | 0 |  |
| expanded_baseline | final | multimodal-state | pretrained_base | 96 | 96 |  |
| expanded_baseline | final | multimodal-state | process_sft | 96 | 53 |  |
| expanded_baseline | final | multimodal-state | random_valid | 96 | 16 |  |
| expanded_baseline | final | text-state | exact_reference | 96 | 0 |  |
| expanded_baseline | final | text-state | pretrained_base | 96 | 96 |  |
| expanded_baseline | final | text-state | process_sft | 96 | 54 |  |
| expanded_baseline | final | text-state | random_valid | 96 | 16 |  |
| expanded_baseline | final | visual-state | exact_reference | 96 | 0 |  |
| expanded_baseline | final | visual-state | pretrained_base | 96 | 96 |  |
| expanded_baseline | final | visual-state | process_sft | 96 | 56 |  |
| expanded_baseline | final | visual-state | random_valid | 96 | 16 |  |
| generalization_robustness_v2 | final | multimodal-state | exact_reference | 50 | 0 |  |
| generalization_robustness_v2 | final | multimodal-state | learned_adapter | 50 | 7 |  |
| generalization_robustness_v2 | final | multimodal-state | pretrained_base | 50 | 50 |  |
| generalization_robustness_v2 | final | multimodal-state | random_valid | 250 | 0 |  |
| generalization_robustness_v2 | final | text-state | exact_reference | 50 | 0 |  |
| generalization_robustness_v2 | final | text-state | learned_adapter | 50 | 6 |  |
| generalization_robustness_v2 | final | text-state | pretrained_base | 50 | 50 |  |
| generalization_robustness_v2 | final | text-state | random_valid | 250 | 0 |  |
| generalization_robustness_v2 | final | visual-state | exact_reference | 50 | 0 |  |
| generalization_robustness_v2 | final | visual-state | learned_adapter | 50 | 9 |  |
| generalization_robustness_v2 | final | visual-state | pretrained_base | 50 | 50 |  |
| generalization_robustness_v2 | final | visual-state | random_valid | 250 | 0 |  |
| successor_prediction | development | multimodal-state | model_generated_successor | 3 | 3 | yes |
| successor_prediction | development | multimodal-state | trusted_successor | 3 | 0 | yes |
| successor_prediction | development | text-state | model_generated_successor | 3 | 3 | yes |
| successor_prediction | development | text-state | trusted_successor | 3 | 0 | yes |
| successor_prediction | development | visual-state | model_generated_successor | 3 | 3 | yes |
| successor_prediction | development | visual-state | trusted_successor | 3 | 0 | yes |
| successor_prediction | unseen | multimodal-state | model_generated_successor | 12 | 11 |  |
| successor_prediction | unseen | multimodal-state | trusted_successor | 12 | 0 |  |
| successor_prediction | unseen | text-state | model_generated_successor | 12 | 12 |  |
| successor_prediction | unseen | text-state | trusted_successor | 12 | 0 |  |
| successor_prediction | unseen | visual-state | model_generated_successor | 12 | 12 |  |
| successor_prediction | unseen | visual-state | trusted_successor | 12 | 0 |  |

## Headline failure profile

- **Base policy (`pretrained_base`):** 447 failures in
  447 episodes; 447 fail on the very first decision and
  379 of them emit a malformed output that never reaches the
  operation checker. The base never succeeds anywhere in the mined evidence.
- **Learned arms:** 407 failures across 906 learned
  episodes; 137 on the first decision. Failures concentrate in
  the BFS and best-first-width families: every baseline SFT BFS and
  best-first-width episode fails (144/144),
  the DAgger-iteration BFS arms fail 155/162, while the
  learned additive best-first families fail 56/546
  episodes (10.3%).
- **Oracle control (`random_valid`):** 51
  failures, all `expansion_budget_exhausted` — the control emits only valid
  operations but can starve its expansion budget; it is an oracle-assisted
  bound, not learned ability.
- **Reference arms** (0 failures): the
  reference bounds hold everywhere except where noted as tiny strata.

## Failure taxonomy distribution

| arm class | failure kind | failures | share of class |
| --- | --- | --- | --- |
| learned | other_invariant_violation | 229 | 56.3% |
| learned | malformed_output | 72 | 17.7% |
| learned | inapplicable_grounded_action | 56 | 13.8% |
| learned | effect | 27 | 6.6% |
| learned | schema | 16 | 3.9% |
| learned | invalid_frontier_operation | 5 | 1.2% |
| learned | source_state_mismatch | 1 | 0.2% |
| learned | static_context | 1 | 0.2% |
| base | malformed_output | 379 | 84.8% |
| base | invalid_frontier_operation | 67 | 15.0% |
| base | other_invariant_violation | 1 | 0.2% |
| oracle_control | expansion_budget_exhausted | 51 | 100.0% |

Successor-prediction rejection kinds (verbatim from the episodes'
`verification.failure_kind`):

| successor failure kind | episodes |
| --- | --- |
| effect | 27 |
| schema | 16 |
| static_context | 1 |

Generalization-v2 learned failures by perturbation/shift family (k=5 variants
per family; descriptive-only strata):

| family | learned failures |
| --- | --- |
| name-compression | 3 |
| object-renaming | 1 |
| render-restyle | 3 |
| scale-up | 4 |
| shifted-init | 11 |

## Horizon position (first-failure step distribution)

First-failure decision index over the frozen buckets `0, 1, 2, 3-4, 5-8,
9-16, 17-32, 33+`:

| arm class | horizon bucket | failures |
| --- | --- | --- |
| learned | 0 | 137 |
| learned | 1 | 88 |
| learned | 2 | 46 |
| learned | 3-4 | 87 |
| learned | 5-8 | 27 |
| learned | 9-16 | 15 |
| learned | 17-32 | 3 |
| learned | 33+ | 4 |
| base | 0 | 447 |
| oracle_control | 5-8 | 9 |
| oracle_control | 9-16 | 9 |
| oracle_control | 17-32 | 3 |
| oracle_control | 33+ | 30 |

Horizon ratio `first_failure_step / reference_decisions` against the matched
`exact_reference` decision counts (0
failure records lacked a reference and are excluded here):

| arm class | algorithm family | n | mean | median | min | max |
| --- | --- | --- | --- | --- | --- | --- |
| base | best_first_add_greedy | 156 | 0.000 | 0.000 | 0.000 | 0.000 |
| base | best_first_add_w3 | 147 | 0.000 | 0.000 | 0.000 | 0.000 |
| base | best_first_width | 72 | 0.000 | 0.000 | 0.000 | 0.000 |
| base | bfs | 72 | 0.000 | 0.000 | 0.000 | 0.000 |
| learned | best_first_add_greedy | 30 | 0.243 | 0.158 | 0.000 | 0.941 |
| learned | best_first_add_w3 | 26 | 0.198 | 0.098 | 0.010 | 0.667 |
| learned | best_first_width | 72 | 0.000 | 0.000 | 0.000 | 0.000 |
| learned | bfs | 279 | 0.097 | 0.031 | 0.000 | 0.750 |
| oracle_control | best_first_width | 21 | 0.971 | 0.985 | 0.875 | 1.056 |
| oracle_control | bfs | 30 | 0.993 | 0.994 | 0.929 | 1.040 |

## Operation type at first failure

Top operation types (action names; `frontier:<type>` for rejected BFS
frontier operations) across all failed episodes:

| arm class | operation type | failures |
| --- | --- | --- |
| learned | move | 111 |
| base | frontier:retire_frontier | 67 |
| learned | board | 24 |
| learned | drive | 19 |
| learned | sail | 19 |
| learned | lift | 18 |
| learned | load-truck | 17 |
| learned | walk | 16 |
| learned | drop | 13 |
| learned | drive-truck | 12 |
| learned | stack | 10 |
| learned | down | 9 |
| learned | fly-airplane | 9 |
| learned | pickup | 9 |
| learned | unstack | 8 |
| learned | go-out | 7 |
| learned | pick | 7 |
| learned | putdown | 6 |
| learned | frontier:retire_frontier | 5 |
| learned | up | 5 |

## Frontier/branching difficulty at first failure

Frontier size and branching factor (successor candidate count) logged at the
first-failure event, over the frozen buckets `0, 1-2, 3-5, 6-10, 11+` and
`0-1, 2-3, 4-6, 7-12, 13+`:

| arm class | frontier size bucket | branching factor bucket | failures |
| --- | --- | --- | --- |
| base | 0 | 0-1 | 3 |
| base | 0 | 2-3 | 216 |
| base | 0 | 4-6 | 78 |
| base | 0 | 7-12 | 6 |
| base | 1-2 | 2-3 | 102 |
| base | 1-2 | 4-6 | 42 |
| learned | 0 | 0-1 | 1 |
| learned | 0 | 2-3 | 1 |
| learned | 0 | 4-6 | 1 |
| learned | 1-2 | 0-1 | 9 |
| learned | 1-2 | 2-3 | 222 |
| learned | 1-2 | 4-6 | 87 |
| learned | 3-5 | 0-1 | 3 |
| learned | 3-5 | 2-3 | 49 |
| learned | 3-5 | 4-6 | 16 |
| learned | 3-5 | 7-12 | 1 |
| learned | 6-10 | 0-1 | 1 |
| learned | 6-10 | 2-3 | 8 |
| learned | 6-10 | 4-6 | 4 |
| learned | 11+ | 2-3 | 1 |
| learned | 11+ | 4-6 | 3 |
| oracle_control | 1-2 | 2-3 | 6 |
| oracle_control | 3-5 | 2-3 | 3 |
| oracle_control | 6-10 | 2-3 | 9 |
| oracle_control | 6-10 | 4-6 | 6 |
| oracle_control | 11+ | 0-1 | 3 |
| oracle_control | 11+ | 2-3 | 21 |
| oracle_control | 11+ | 4-6 | 3 |

## Tiny-strata register

Strata with fewer than 8 episodes are descriptive-only; they are
listed here and in `tiny-strata.csv`, never silently pooled or dropped:

| stratum scope | stratum | failure kind | failures | stratum episodes |
| --- | --- | --- | --- | --- |
| branch x panel x modality x arm | curriculum_modality / development / multimodal-state / exact_reference |  | 0 | 3 |
| branch x panel x modality x arm | curriculum_modality / development / multimodal-state / multimodal-state__mixed_order |  | 0 | 3 |
| branch x panel x modality x arm | curriculum_modality / development / multimodal-state / multimodal-state__shuffled |  | 0 | 3 |
| branch x panel x modality x arm | curriculum_modality / development / multimodal-state / multimodal-state__staged |  | 0 | 3 |
| branch x panel x modality x arm | curriculum_modality / development / multimodal-state / pretrained_base |  | 3 | 3 |
| branch x panel x modality x arm | curriculum_modality / development / multimodal-state / process_sft |  | 0 | 3 |
| branch x panel x modality x arm | curriculum_modality / development / multimodal-state / random_valid |  | 0 | 3 |
| branch x panel x modality x arm | curriculum_modality / development / text-state / exact_reference |  | 0 | 3 |
| branch x panel x modality x arm | curriculum_modality / development / text-state / pretrained_base |  | 3 | 3 |
| branch x panel x modality x arm | curriculum_modality / development / text-state / process_sft |  | 1 | 3 |
| branch x panel x modality x arm | curriculum_modality / development / text-state / random_valid |  | 0 | 3 |
| branch x panel x modality x arm | curriculum_modality / development / text-state / text-state__mixed_order |  | 0 | 3 |
| branch x panel x modality x arm | curriculum_modality / development / text-state / text-state__shuffled |  | 0 | 3 |
| branch x panel x modality x arm | curriculum_modality / development / text-state / text-state__staged |  | 1 | 3 |
| branch x panel x modality x arm | curriculum_modality / development / visual-state / exact_reference |  | 0 | 3 |
| branch x panel x modality x arm | curriculum_modality / development / visual-state / pretrained_base |  | 3 | 3 |
| branch x panel x modality x arm | curriculum_modality / development / visual-state / process_sft |  | 0 | 3 |
| branch x panel x modality x arm | curriculum_modality / development / visual-state / random_valid |  | 0 | 3 |
| branch x panel x modality x arm | curriculum_modality / development / visual-state / visual-state__mixed_order |  | 0 | 3 |
| branch x panel x modality x arm | curriculum_modality / development / visual-state / visual-state__shuffled |  | 0 | 3 |
| branch x panel x modality x arm | curriculum_modality / development / visual-state / visual-state__staged |  | 0 | 3 |
| branch x panel x modality x arm | dagger / development / multimodal-state / continued_sft_iteration_2 |  | 2 | 3 |
| branch x panel x modality x arm | dagger / development / multimodal-state / dagger_iteration_2 |  | 1 | 3 |
| branch x panel x modality x arm | dagger / development / multimodal-state / exact_reference |  | 0 | 3 |
| branch x panel x modality x arm | dagger / development / multimodal-state / process_sft |  | 3 | 3 |
| branch x panel x modality x arm | dagger / development / multimodal-state / random_valid |  | 1 | 3 |
| branch x panel x modality x arm | dagger / development / text-state / continued_sft_iteration_2 |  | 2 | 3 |
| branch x panel x modality x arm | dagger / development / text-state / dagger_iteration_2 |  | 3 | 3 |
| branch x panel x modality x arm | dagger / development / text-state / exact_reference |  | 0 | 3 |
| branch x panel x modality x arm | dagger / development / text-state / process_sft |  | 3 | 3 |
| branch x panel x modality x arm | dagger / development / text-state / random_valid |  | 1 | 3 |
| branch x panel x modality x arm | dagger / development / visual-state / continued_sft_iteration_2 |  | 3 | 3 |
| branch x panel x modality x arm | dagger / development / visual-state / dagger_iteration_2 |  | 2 | 3 |
| branch x panel x modality x arm | dagger / development / visual-state / exact_reference |  | 0 | 3 |
| branch x panel x modality x arm | dagger / development / visual-state / process_sft |  | 2 | 3 |
| branch x panel x modality x arm | dagger / development / visual-state / random_valid |  | 1 | 3 |
| branch x panel x modality x arm | successor_prediction / development / multimodal-state / model_generated_successor |  | 3 | 3 |
| branch x panel x modality x arm | successor_prediction / development / multimodal-state / trusted_successor |  | 0 | 3 |
| branch x panel x modality x arm | successor_prediction / development / text-state / model_generated_successor |  | 3 | 3 |
| branch x panel x modality x arm | successor_prediction / development / text-state / trusted_successor |  | 0 | 3 |
| branch x panel x modality x arm | successor_prediction / development / visual-state / model_generated_successor |  | 3 | 3 |
| branch x panel x modality x arm | successor_prediction / development / visual-state / trusted_successor |  | 0 | 3 |

## Claim discipline and boundaries

- Descriptive only: no causal claims beyond the underlying verified
  experiments; no intervals are computed over tiny strata.
- `random_valid` is oracle-assisted; controls are bounds, not learned
  ability. Validity-conditioned success is selected and is not
  repaired-policy counterfactual performance.
- P3 name-compression lossy strata (generalization v2) are reported
  separately per family above and never pooled with semantics-preserving
  variants.
- All learned arms rest on training seed 17 and evaluation seed 17; no
  seed-variance claims. The base arm in generalization v2 was capped at one
  call, so its horizon statistics are structurally step-0.
- #96, #98, #102, #103, #121 and #122 are neither closed nor modified by
  this analysis.

## Reproducibility

`python3 scripts/failure_mechanism_analysis.py` regenerates
`failure-mechanism-matrix.json`, `failure-mechanism-tables/*.csv` and this
document; `--check` byte-compares a fresh regeneration against the published
artifacts and re-verifies the anchor checks, the zero-`unclassified` gate and
the frozen coverage counts. The machine-readable matrix records one row per
failed episode with the raw failing output preserved.
