# Issue #138 closeout — choice-frontier adapter 3-seed replication + separation from the exact-eps-0.75 rung

This ran under the frozen protocol `docs/experiments/choice-frontier/issue-138-protocol.md` and its machine-readable twin `configs/experiments/choice-frontier-v4/seeds-protocol.json`. Commit order:

- The protocol was committed and pushed before any GPU launch (`f06c7ac`).
- The runner, the shared v4 schedule and the job files were committed before the first launch (`00ac5bf`).
- The analyzer and test were committed before any v4 outcome existed (`dd6e458`).

This ticket created the shared v4 ledger `outputs/choice-frontier/v4/budget.json` (cap 24 GPU-h). Every model episode was independently replayed. No frozen #132/#133/#135/#136 file or evidence was modified. The held-out manifest and `data/curriculum_pddl/*/dev/` were never read.

## Results — primary **POSITIVE**; separation vs exact-eps-0.75 **NOT_SEPARATED**

Panel: the frozen #135 panel (12 tasks, 7 domains, membership_sha256 `b2d909ca…11cd07`). CI: task-cluster bootstrap, `random.Random(133)`, 10,000 draws, 95% percentile. Each draw resamples tasks and then averages the 3 seeds inside the draw. Source: `outputs/choice-frontier/v4/seeds/metrics/analysis.json`.

| quantity | value |
| --- | --- |
| **D3** = mean_s M1(learned, s) − M1(random_valid) | **+0.285 [+0.140, +0.433]** |
| per-seed D: s17 / s29 / s71 | +0.328 [+0.155, +0.508] / +0.229 [+0.108, +0.354] / +0.297 [+0.134, +0.466] |
| M1 learned, 3-seed mean | 0.306 [0.158, 0.455] |
| M1 random_valid (#135, reused) | 0.021 [0.007, 0.038] |
| primary verdict | **POSITIVE**: lo 0.140 > 0; D3 0.285 ≥ δ 0.05; every seed point estimate > 0 |
| **S** = M1(learned, 3-seed mean) − M1(exact-eps-0.75, 5-seed mean 0.347) | **−0.041 [−0.187, +0.102]** |
| per-seed S: s17 / s29 / s71 | +0.002 / −0.097 / −0.029 |
| separation verdict (co-primary) | **NOT_SEPARATED**: lo −0.187 ≤ 0 and hi +0.102 ≥ 0 |
| S vs exact-eps-0.50 (0.603), descriptive | −0.298 [−0.468, −0.129] → SEPARATED_BELOW; per seed −0.254 / −0.353 / −0.285 |

The margins, rules and bootstrap are exactly as pre-registered. Nothing was changed after results.

Two consistency checks hold:

- The seed-17 per-seed interval reproduces the #136 primary interval exactly ([0.155, 0.508]).
- The recomputed #135 control M1 (exact_reference, eps-0.50, eps-0.75, random_valid) and the #136 seed-17 per-task M1 equal the frozen analyses.

Reading: the #136 effect over uniform frontier choice **replicates across 3 training seeds**. The pooled learned adapter is **statistically indistinguishable from the exact-eps-0.75 rung**. It is **clearly below eps-0.50**. The learned policy is roughly as good as a selector that follows the heap head on 25% of decisions and chooses uniformly otherwise. It is not demonstrably better than that.

## Seed variance (descriptive; `per_seed`, `seed_variance`)

| seed | M1 [CI] | teacher agreement − chance [CI] | last-label rate | first-label rate | solved at 2× | M2 ρ (solved) | M3 κ (solved) | decisions (menu ≥ 2) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 17 (#136, reused) | 0.349 [0.172, 0.531] | +0.085 [+0.020, +0.177] | 0.205 | 0.090 | 0.583 | 1.326 | 1.140 | 691 |
| 29 | 0.250 [0.125, 0.375] | +0.056 [+0.004, +0.137] | 0.192 | 0.121 | 0.500 | 1.386 | 1.125 | 725 |
| 71 | 0.318 [0.151, 0.490] | +0.086 [+0.004, +0.207] | 0.171 | 0.094 | 0.542 | 1.311 | 1.247 | 701 |

Between-seed SD of M1 = **0.051** (n − 1). The mean is 0.306 and the range 0.250–0.349. Seed 17 (the #136 adapter) is the best of the three.

Ladder position (#135 M1): exact 0.875 > eps-0.25 0.793 > eps-0.50 0.603 > eps-0.75 0.347 > **3-seed learned 0.306** > random 0.021.

- s17 sits at eps-0.75 (0.349 ≥ 0.347).
- s29 and s71 sit just below it.
- pretrained_base (#135, reused) scores 0.000.

Per-task M1 (averaged over both algorithms):

| task (`choice-frontier-v2/…`) | s17 | s29 | s71 | S vs eps-0.75 (seed mean) |
| --- | --- | --- | --- | --- |
| 15puzzle-expanded-935006 | 0.000 | 0.000 | 0.000 | −0.550 |
| blocksworld-expanded-935001 | 0.000 | 0.000 | 0.000 | −0.388 |
| blocksworld-expanded-935004 | 0.000 | 0.312 | 0.000 | −0.183 |
| depot-expanded-935005 | 0.062 | 0.062 | 0.000 | −0.121 |
| depot-expanded-935011 | 0.750 | 0.312 | 0.625 | +0.300 |
| elevators-expanded-935000 | 0.500 | 0.625 | 0.625 | +0.121 |
| elevators-expanded-935013 | 0.688 | 0.500 | 0.750 | +0.308 |
| grid-expanded-935016 | 0.438 | 0.438 | 0.625 | +0.287 |
| storage-expanded-935000 | 0.750 | 0.375 | 0.500 | −0.096 |
| storage-expanded-935001 | 0.750 | 0.375 | 0.500 | −0.033 |
| towers_of_hanoi-expanded-935000 | 0.250 | 0.000 | 0.188 | −0.079 |
| towers_of_hanoi-expanded-935002 | 0.000 | 0.000 | 0.000 | −0.062 |

The learned adapter beats eps-0.75 on depot-935011, both elevators tasks and grid. It loses heavily on 15puzzle and both blocksworld tasks, where eps-0.75 still solves some episodes and the adapter solves none (except s29 on blocksworld-935004).

v4 evaluation terminations over 48 episodes:

| cell | goal_reached | decision_budget_exhausted |
| --- | --- | --- |
| s29 greedy | 5 | 7 |
| s29 w3 | 7 | 5 |
| s71 greedy | 7 | 5 |
| s71 w3 | 6 | 6 |

There were 0 invalid operations over 1,501 model calls.

## Training

The corpus is the frozen #136 corpus, read-only: `configs/experiments/choice-frontier-v3/membership.json`, membership_sha256 **f5cc9b2a…c077**, asserted by `train`, `audit-train` and `validate`. The store is `outputs/choice-frontier/v3/preparation/store.json`. The recipe is the #136 recipe byte-for-byte: `validate` compares every recipe key with the #136 protocol.

**Sample order (recorded decision).** The #136 code ties the order to the training seed (`order:{training_seed}`, i.e. `order:17` in #136). v4 pins `order:17` (`PinnedOrderDataset`). A CPU check confirmed that the 4,096-sample sequence equals the #136 sequence for both algorithms. As a consequence, the step-1 loss is identical across seeds 17/29/71: greedy 5.1141, w3 5.0416. With LoRA B = 0 at init, the first forward pass is seed-independent. Only the LoRA init and dropout differ.

| cell | steps | samples | train_runtime | loss first → last (mean) | diagnostic eval loss (step 42 / 84) | audit |
| --- | --- | --- | --- | --- | --- | --- |
| best_first_add_greedy / seed 29 | 128 | 4096 | 6,927.6 s | 5.114 → 0.153 (0.310) | 0.158 / 0.148 | PASS |
| best_first_add_w3 / seed 29 | 128 | 4096 | 6,804.3 s | 5.042 → 0.134 (0.295) | 0.262 / 0.248 | PASS |
| best_first_add_greedy / seed 71 | 128 | 4096 | 6,825.1 s | 5.114 → 0.142 (0.294) | 0.152 / 0.107 | PASS |
| best_first_add_w3 / seed 71 | 128 | 4096 | 6,767.8 s | 5.042 → 0.131 (0.296) | 0.260 / 0.242 | PASS |

`audit-train` checked each cell: adapter present, r 64, alpha 128, dropout 0.05, 128 steps, the seed, 2048 records, 4096 samples, sample order `order:17`, and the corpus membership sha.

**Adapters (the #139 contract path):** `outputs/choice-frontier/v4/seeds/training/<algorithm>/seed-<29|71>/final/`. Seed-17 adapters remain at `outputs/choice-frontier/v3/training/<algorithm>/seed-17/final/`.

## Smoke gate, evaluation and replay

- **Smoke** (the #132 definition on the seed-29 adapters: storage-compact-919000, elevators-compact-914002, ferry-compact-915000 × 2 algorithms, seed 17, cap 2 × #132 R): 31/31 calls accepted (rate 1.0 ≥ 0.5) → **PASS**, and 6/6 episodes reached the goal. `audit-smoke` replayed 6/6 and matches the stored result.
- **Evaluation**: 48 `learned_adapter` episodes (12 panel tasks × 2 algorithms × training seeds 29/71), inference seed 17, greedy, cap 2 × R_t (the #135 uncapped exact expansions). Model calls: greedy-s29 425, w3-s29 340, greedy-s71 389, w3-s71 347.
- **finalize**: 48/48 independently replayed, **0 missing, 0 mismatches**, `complete: true`. Every evaluation completion hook returned `ok: true`. The hook derives the attempt dir from `EXPANDED_TERMINAL_PATH`'s parent (the #136 fix), so no hook rerun was needed.
- **Reuse**: controls, ladder rungs and the base come from #135, and the seed-17 learned episodes from #136 (`outputs/choice-frontier/v3/evaluation`, finalized complete). Their recomputed M1 equals the frozen analyses.
- **Relaunch (infrastructure, 1 of the allowed 2)**: `cfv4-evaluate-best_first_add_w3-s29` attempt 1 failed after 23 s. I launched it from a Python kernel whose environment lacked `~/cd_vlaplan` (HF_HOME unset), so the offline tokenizer load raised `TypeError` (vocab_file None) before any episode or model call. Attempt 2 is unchanged except for `resume_reason`: `configs/experiments/choice-frontier-v4/relaunch/cfv4-evaluate-best_first_add_w3-s29-attempt-2-job.json`, launched with the project environment. It succeeded. The failed attempt's 0.0064 GPU-h is charged.

## Budget (shared v4 ledger)

| job | GPU | MASTER_PORT | status | GPU-h |
| --- | --- | --- | --- | --- |
| cfv4-train-best_first_add_greedy-s29 | 0 | 18826 | succeeded | 1.9413 |
| cfv4-train-best_first_add_w3-s29 | 1 | 18827 | succeeded | 1.9068 |
| cfv4-smoke-s29 | 0 | 18826 | succeeded | 0.0487 |
| cfv4-train-best_first_add_w3-s71 | 1 | 18827 | succeeded | 1.8970 |
| cfv4-train-best_first_add_greedy-s71 | 0 | 18826 | succeeded | 1.9061 |
| cfv4-evaluate-best_first_add_w3-s29 (attempt 1) | 1 | 18827 | failed (infra) | 0.0064 |
| cfv4-evaluate-best_first_add_w3-s29 (attempt 2) | 1 | 18827 | succeeded | 0.4863 |
| cfv4-evaluate-best_first_add_greedy-s29 | 0 | 18826 | succeeded | 0.7321 |
| cfv4-evaluate-best_first_add_w3-s71 | 1 | 18827 | succeeded | 0.5199 |
| cfv4-evaluate-best_first_add_greedy-s71 | 0 | 18826 | succeeded | 0.6620 |
| **total (this ticket)** | | | | **10.107 / 24** |

- Scheduling: concurrent jobs always held distinct ports (18826 on GPU 0, 18827 on GPU 1), with at most one job per GPU and two training cells at a time.
- Estimate: the protocol estimated 9.66 GPU-h (12.08 worst case).
- Remaining: at closeout the whole ledger holds only this ticket's jobs, leaving 13.89 GPU-h for #139.

## Evidence index (sha256, first 16)

```
eb18f4268f3e0742  budget.json (at closeout)
2acc6eae853decee  seeds/evaluation/bindings.json
7a6ac6aaab1f7107  seeds/evaluation/evaluation.json
3f89bfdfc55050da  seeds/evaluation/cells.json
38560c93df15f360  seeds/smoke/smoke.json
2dcf441a3489dc2d  seeds/smoke/audit.json
07421efa5c786231  seeds/training/audit.json
6c42a8ea8668bdff  seeds/metrics/analysis.json
59cb5430b07f83df  seeds/metrics/all-episode-metrics.json
5627afc1698c4700  seeds/training/best_first_add_greedy/seed-29/report.json
cbcf73b6b53bc2ee  seeds/training/best_first_add_greedy/seed-29/final/adapter_model.safetensors
237ecbaf41e04120  seeds/training/best_first_add_w3/seed-29/report.json
f46dbe10da67ff31  seeds/training/best_first_add_w3/seed-29/final/adapter_model.safetensors
a3f46dec03bcd32e  seeds/training/best_first_add_greedy/seed-71/report.json
bea3c006d6d8c59d  seeds/training/best_first_add_greedy/seed-71/final/adapter_model.safetensors
8511ae3189fcb362  seeds/training/best_first_add_w3/seed-71/report.json
a07e5bb99e114688  seeds/training/best_first_add_w3/seed-71/final/adapter_model.safetensors
ac24bb37807bd604  seeds/evaluation/episodes/** (48 files)
91d2a7616a4a9883  seeds/evaluation/views/** (2848 files)
c5be942669499ae1  seeds/smoke/episodes/** (6 files)
1c0947c5a79cef12  jobs/cfv4-evaluate-best_first_add_greedy-s29/** (9 files)
c22edfc4b394c7bb  jobs/cfv4-evaluate-best_first_add_greedy-s71/** (9 files)
862bf99f1ad9f52f  jobs/cfv4-evaluate-best_first_add_w3-s29/** (16 files, attempts 1+2)
8f7e956a00e18cc6  jobs/cfv4-evaluate-best_first_add_w3-s71/** (9 files)
58375f0320b48e63  jobs/cfv4-smoke-s29/** (8 files)
9880183be4fdcc7e  jobs/cfv4-train-best_first_add_greedy-s29/** (8 files)
26676150a1557c86  jobs/cfv4-train-best_first_add_greedy-s71/** (8 files)
1146557988ae5a74  jobs/cfv4-train-best_first_add_w3-s29/** (8 files)
ce47672745ffbb9a  jobs/cfv4-train-best_first_add_w3-s71/** (8 files)
e199616d65fa2d2b  seeds/evidence-index.json (sha256 of all 3,124 files)
```

The root is `outputs/choice-frontier/v4/`, untracked by repo convention. Each directory digest (`/**`) is the sha256 of the sorted `path sha256` lines from `seeds/evidence-index.json`. `budget.json` is shared with #139, so its digest is the closeout snapshot.

Tracked inputs:

- `configs/experiments/choice-frontier-v4/{seeds-protocol,cfv4-*-job}.json` and `relaunch/cfv4-evaluate-best_first_add_w3-s29-attempt-2-job.json`
- `docs/experiments/choice-frontier/{issue-138-protocol.md,schedule-v4.json}`
- `scripts/{run_choice_frontier_v4_seeds,analyze_choice_frontier_v4_seeds}.py`. The runner imports the unchanged #136 machinery from the frozen `run_choice_frontier_v3.py` rather than duplicating it.
- `tests/planning_benchmark/test_choice_frontier_v4_seeds.py`: 8 passed, and ruff is clean on both scripts.

## Limitations

- **One panel.** 12 tasks from 7 domains, admitted by #135's controls-only screening. The effect is concentrated on depot-935011, elevators ×2, grid and storage ×2. 15puzzle, blocksworld-935001 and hanoi-935002 stay at 0 for every seed. #139 re-evaluates all 3 seeds on fresh held-out panels.
- **Separation is not established.** With 12 task clusters, the S interval is ±0.14 wide. The data cannot exclude a learned policy up to 0.10 M1 above eps-0.75, or up to 0.19 below it. The pooled point estimate is slightly below the rung.
- **Seed 17 was the #136 headline seed and is the best of three.** The single-seed #136 D (+0.328) overstated the 3-seed D3 (+0.285) by about 0.04.
- **Reuse.** Controls, ladder rungs and base are reused from #135, and seed-17 episodes from #136. Their equality with the frozen analyses was asserted, not re-sampled.
- **Imitation, not planning.** Teacher agreement above chance is modest (+0.06 to +0.09 per seed), and learned M1 sits at the eps-0.75 rung, far below exact (0.875).
- M2/M3 condition on solving, and M1 weights sub-2× budgets.
- **Recorded interpretation choice:** the sample order is pinned to `order:17` for all seeds (see Training).
