# Seed-variance addendum — prospective training-seed replication (#127)

Protocol `expanded-seed-replication-v1` (frozen 2026-09-20 before any seed-29/71 artifact; amendment `docs/experiments/expanded-study/seed-replication-amendment.md`, machine-readable `configs/experiments/expanded-study/seed-replication-protocol.json`). This addendum appends training-seed-variance evidence to synthesis-v1; it does not modify any published verdict, and `synthesis-v1/README.md` remains the frozen #120 snapshot (its single-training-seed claim boundary is superseded only for the two cells below, which now report seed robustness). Seeds: original 17 plus prospective 29 and 71, frozen before launch; every seed is reported individually and aggregated; no seed was dropped after outcomes. Every new episode (534: 48 baseline + 486 DAgger) was independently replayed CPU-only; the 24 seed-17 baseline-cell episodes and all referenced comparator episodes were re-replayed at finalize. Machine-readable analysis: `seed-variance.json` (+ `seed-variance.csv`); canonical evidence: `outputs/expanded-study/v1/seed-replication/evidence.json` (sha256 `76f99253f73c083122d097bf3c4e31282e8026d144dfd0a244facacc6501dbdb`).

## Cell A — expanded-baseline headline process-SFT cell

Cell: `best_first_add_greedy x multimodal-state` process-SFT on the 24-problem unseen panel `expanded-panel-v2-qualified` (the headline cell of the primary positive contrast). Fresh LoRA adapter per seed (new init + dropout RNG; identical frozen 512-record membership, one epoch, 16 updates). Evaluation seed 17, greedy decoding, 2x reference decision call limit — the original cell's frozen contract; comparators reused from the replay-verified baseline episodes.

| Seed | Successes/24 | Invalid ops | Decisions | Expansions |
| ---: | ---: | ---: | ---: | ---: |
| 17 | 21/24 | 3 | 617 | 179 |
| 29 | 21/24 | 3 | 639 | 185 |
| 71 | 22/24 | 2 | 644 | 189 |

Aggregated (descriptive, n = 3): success rate mean 0.889, min 0.875, max 0.917; successes per seed 21/21/22 of 24.

Per-seed paired whole-problem contrasts over the 24 tasks (bootstrap seed 1729, 10,000 resamples, 95% percentile intervals):

| Contrast | Seed 17 | Seed 29 | Seed 71 |
| --- | ---: | ---: | ---: |
| process_sft_minus_pretrained_base | +0.875 [+0.708, +1.000] (wins 21, losses 0, ties 3) | +0.875 [+0.750, +1.000] (wins 21, losses 0, ties 3) | +0.917 [+0.792, +1.000] (wins 22, losses 0, ties 2) |
| process_sft_minus_random_valid | -0.125 [-0.292, +0.000] (wins 0, losses 3, ties 21) | -0.125 [-0.250, +0.000] (wins 0, losses 3, ties 21) | -0.083 [-0.208, +0.000] (wins 0, losses 2, ties 22) |
| process_sft_minus_exact_reference | -0.125 [-0.292, +0.000] (wins 0, losses 3, ties 21) | -0.125 [-0.250, +0.000] (wins 0, losses 3, ties 21) | -0.083 [-0.208, +0.000] (wins 0, losses 2, ties 22) |

## Cell set B — DAgger iteration-1 vs exposure-matched continued-SFT

Cells: `bfs x {text-state, visual-state, multimodal-state} x {dagger, continued_sft}` at iteration 1, continued from the verified seed-17 starting adapters on the verified seed-17 memberships (new seed perturbs only the dropout RNG). Evaluated on the original frozen panels (3 development + 24 unseen per modality) with evaluation seed 17 and the original call limits. The seed-17 iteration-1 checkpoints were never panel-evaluated in the original program (it evaluated iteration-2 finals only); they are evaluated here inference-only under the same contract so the comparison's seed-17 point exists. Comparators (original process SFT, random-valid, exact reference) are reused from the replay-verified original DAgger evaluation.

| Arm | Seed | Dev successes/9 | Unseen successes/72 | Unseen invalid rate |
| --- | ---: | ---: | ---: | ---: |
| dagger_iteration_1 | 17 | 0/9 | 0/72 | 0.268 |
| dagger_iteration_1 | 29 | 0/9 | 0/72 | 0.332 |
| dagger_iteration_1 | 71 | 0/9 | 0/72 | 0.320 |
| continued_sft_iteration_1 | 17 | 0/9 | 0/72 | 0.278 |
| continued_sft_iteration_1 | 29 | 0/9 | 0/72 | 0.326 |
| continued_sft_iteration_1 | 71 | 0/9 | 0/72 | 0.338 |

Aggregated (descriptive, n = 3): DAgger unseen rate mean 0.000 [min 0.000, max 0.000]; continued-SFT mean 0.000 [min 0.000, max 0.000].

Per-seed paired contrast dagger_iteration_1 - continued_sft_iteration_1 on the 72 unseen modality-task rows (bootstrap seed 1729, 10,000 resamples, 95% percentile intervals):

| Seed | Point | 95% interval | Wins | Losses | Ties |
| ---: | ---: | --- | ---: | ---: | ---: |
| 17 | +0.000 | [+0.000, +0.000] | 0 | 0 | 72 |
| 29 | +0.000 | [+0.000, +0.000] | 0 | 0 | 72 |
| 71 | +0.000 | [+0.000, +0.000] | 0 | 0 | 72 |

## Boundaries

- Cross-seed aggregation is descriptive only (n = 3 seeds); per-seed bootstrap intervals remain tiny-subgroup descriptive bounds over 24 (cell A) or 72/9 (cell B) units.
- Cell A covers one modality of the three in the pooled headline contrast; the other two modalities remain single-seed evidence as published.
- Cell set B is the iteration-1 comparison named by the ticket; the published iteration-2 comparison (single seed 17) is unchanged and remains the program's DAgger verdict.
- Random-valid is an oracle-assisted programmatic control; exact-reference bounds perfect decision-making. Neither measures learned ability.
- Training-seed variance is now reported for exactly these two cells; all other cells of the program remain single-seed (17) as published.
