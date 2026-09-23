# Issue #136 closeout — choice-frontier adapter scale-up (larger corpus, menu-order augmentation, 1 seed)

Run under the frozen protocol `docs/experiments/choice-frontier/issue-136-protocol.md` and its machine-readable twin `configs/experiments/choice-frontier-v3/protocol.json`. The protocol was committed and pushed before any training-task generation (`ecdda03`). The corpus membership was committed and pushed before any training (`f16dfef`). The schedule, job files, analyzer and test were committed before the first GPU launch (`f26875b`). The ledger is new (`outputs/choice-frontier/v3/budget.json`, cap 30 GPU-h). Every model episode was independently replayed.

No frozen #132/#133/#135 file or evidence was modified, and the held-out manifest was never read. The precondition was checked first: #135 is CLOSED with `Verdict: PASS`, and `instrument_validity.verdict == "PASS"`.

## Results — verdict **POSITIVE**

Primary endpoint on the frozen #135 panel (12 tasks, 7 domains, membership_sha256 `b2d909ca…11cd07`). D = M1(learned, seed 17) − M1(random_valid). The interval is a task-cluster bootstrap: `random.Random(133)`, 10,000 draws, 95% percentile. Source: `outputs/choice-frontier/v3/metrics/analysis.json` → `primary`.

| quantity | value |
| --- | --- |
| M1 learned_adapter (s17) | **0.349** [0.172, 0.531] |
| M1 random_valid (#135, reused) | 0.021 [0.007, 0.038] |
| **D** | **+0.328 [+0.155, +0.508]** |
| per-seed point (s17) | +0.328 |
| verdict | **POSITIVE**: lo 0.155 > 0; D 0.328 ≥ δ 0.05; the s17 point estimate is > 0 |

The margins (δ = 0.05, equivalence ±0.05) and the rule are exactly as pre-registered. Nothing was changed after results.

Secondary endpoints (descriptive; `per_seed.17`, `ladder_position`):

| endpoint | v3 adapter (s17) | #132 adapter on the same panel (#135) |
| --- | --- | --- |
| teacher heap-head agreement − chance | **+0.085 [+0.020, +0.177]** (observed 0.210 vs chance 0.125, 691 on-policy decisions, menu ≥ 2) | +0.021 (794 decisions) |
| last-label rate | **0.205** (first-label rate 0.090) | 0.300 |
| solved at 2× | 0.583 | 0.208 |
| M2 ρ (solved-only, geometric) | 1.326 | 1.810 |
| M3 κ (solved-only) | 1.140 | 1.050 |
| invalid operations | 0 / 24 episodes | — |

Ladder position (#135 M1 values): exact_reference 0.875 > eps-0.25 0.793 > eps-0.50 0.603 > **learned 0.349** ≥ eps-0.75 0.347 > random_valid 0.021. The adapter sits at the exact-eps-0.75 rung, i.e. roughly as good as a selector that takes the heap head on 25% of decisions and picks uniformly otherwise. The base (`pretrained_base`, reused from #135, 1-call cap) scores M1 0.000.

Per-task M1 (learned vs random_valid, averaged over the two algorithms):

| task (`choice-frontier-v2/…`) | learned | random | learned solved at 2× |
| --- | --- | --- | --- |
| 15puzzle-expanded-935006 | 0.000 | 0.063 | 0/2 |
| blocksworld-expanded-935001 | 0.000 | 0.000 | 0/2 |
| blocksworld-expanded-935004 | 0.000 | 0.000 | 0/2 |
| depot-expanded-935005 | 0.063 | 0.000 | 1/2 |
| depot-expanded-935011 | 0.750 | 0.038 | 2/2 |
| elevators-expanded-935000 | 0.500 | 0.000 | 2/2 |
| elevators-expanded-935013 | 0.688 | 0.000 | 2/2 |
| grid-expanded-935016 | 0.438 | 0.075 | 1/2 |
| storage-expanded-935000 | 0.750 | 0.013 | 2/2 |
| storage-expanded-935001 | 0.750 | 0.050 | 2/2 |
| towers_of_hanoi-expanded-935000 | 0.250 | 0.013 | 2/2 |
| towers_of_hanoi-expanded-935002 | 0.000 | 0.000 | 0/2 |

Terminations: 14/24 goal_reached (greedy 6, w3 8), 10/24 decision_budget_exhausted, 0 invalid.

## Corpus

- **Tasks** (`configs/experiments/choice-frontier-v3/training-tasks.json`): 2,400 generated serially (24 strata × seeds 945000–945099) with the frozen `expanded_candidates.generate`.
  - 336 dropped for overlap: 234 matched (a) a #135 candidate (all 240 hashed), 101 matched (b) the expanded-study final panel, and 1 matched (c) the #132 corpus.
  - 682 dropped as `duplicate_training_task`, 200 as `initial_goal`.
  - 1,182 eligible. `audit-prepare` confirms that no used task overlaps any exclusion source.
- **Walk**: seed-major, as the protocol pre-registered. The corpus reached its target inside seeds 945000–945015, so the extension seeds were not needed. It uses **236 tasks from all 12 domains**, with no task dropped for timeout or render failure and 0 token-gate overflows.
- **Records**: **2048 per algorithm** (the estimand kept 2048). Each record is the first ≤ 64 eligible exact-reference decisions (menu ≥ 2) per task, derived from PDDL (`trace_gate: not_applicable_fresh_tasks`). 465 of the training records are goal-selection decisions.
  - Menu size 2–49 (mean 10.1). Input tokens 2,048–5,840 (mean 3,111).
  - Per-domain counts (greedy / w3): blocksworld 440/456, driverlog 316/311, gripper 220/220, grid 209/209, visitall 200/200, 15puzzle 131/131, elevators 129/125, ferry 120/120, storage 90/78, depot 77/77, logistics 75/75, towers_of_hanoi 41/46.
  - Diagnostics: 16 per algorithm, never trained on.
- **Augmentation**: 2 copies per record (seeds `aug:{record_id}:0/1`), 8,192 samples in total.
  - Target-position histogram: first 1,450, middle 5,302, last 1,440.
  - Target-is-last share **17.58%** vs chance mean(1/menu_size) **17.58%** (difference +0.002 pp; tolerance ±5 pp) → PASS on the first attempt.
  - In 257 records (mostly menu size 2) the two copies have the same order.
  - Runtime projection (token-scaled): about 7,200 s per cell, below the 18,000 s cap, so the record ladder was not triggered.
- `membership_sha256` **f5cc9b2ac3b2fe8e94b7a8039e6b9cd828c701a8c5b707ddd7a3b01b2ca8c077**.
- `audit-prepare`: PASS. All 472 (task, algorithm) episodes were re-derived bit-exact, and the token, image-resolve, membership, teacher-label, no-overlap and augmentation gates all hold.

## Training

| cell | steps | samples | train_runtime | loss first → last | diagnostic eval loss (step 42 / 84) | audit |
| --- | --- | --- | --- | --- | --- | --- |
| best_first_add_greedy / seed 17 | 128 | 4096 | 6,738.7 s | 5.114 → 0.145 (mean 0.295) | 0.161 / 0.102 | PASS |
| best_first_add_w3 / seed 17 | 128 | 4096 | 6,743.1 s | 5.042 → 0.134 (mean 0.297) | 0.260 / 0.252 | PASS |

`audit-train` checked r = 64, alpha = 128, dropout 0.05, 128 steps, seed 17, 2048 records and 4096 samples. Observed cost was about 1.65 s/sample; the ticket's estimate was 2.75 s/sample. Adapters are under `outputs/choice-frontier/v3/training/<algorithm>/seed-17/final/`.

## Smoke gate, evaluation and replay

- **Smoke**: the #132 definition (storage-compact-919000, elevators-compact-914002, ferry-compact-915000 × 2 algorithms, seed 17, cap 2 × #132 R). 34/34 calls were accepted (rate 1.0 ≥ 0.5) → **PASS**, and all 6 episodes reached the goal. `audit-smoke` replayed 6/6 and matches the stored result.
- **Evaluation**: 24 `learned_adapter` episodes (12 panel tasks × 2 algorithms × training seed 17), inference seed 17, greedy decoding, cap 2 × R_t (the #135 uncapped exact_reference expansions); 730 model calls in total.
- **finalize**: 24/24 independently replayed, **0 missing, 0 mismatches**, `complete: true`.
- **Reuse**: the analyzer recomputed the #135 control M1 per task from the reused zoo episodes and asserted it equals the frozen #135 analysis.
- **Execution note (infrastructure, no relaunch)**: both evaluation completion hooks exited 1 with `KeyError: 'EXPANDED_ATTEMPT_DIR'`. The scheduler passes only `EXPANDED_TERMINAL_PATH` to hooks, and the #132 copy of `audit-evaluate-worker` assumed the worker environment. The fix derives the attempt dir from the terminal path's parent. The audit was then re-run on the same attempts, and both returned `ok: true` (`jobs/cfv3-evaluate-*/1/hook-rerun.json`). The GPU work and episodes were not affected.

## Budget

| job | GPU | MASTER_PORT | status | GPU-h |
| --- | --- | --- | --- | --- |
| cfv3-train-best_first_add_greedy-s17 | 0 | 18822 | succeeded | 1.8917 |
| cfv3-train-best_first_add_w3-s17 | 1 | 18823 | succeeded | 1.8929 |
| cfv3-smoke | 0 | 18822 | succeeded | 0.0495 |
| cfv3-evaluate-best_first_add_greedy-s17 | 0 | 18822 | succeeded | 0.5816 |
| cfv3-evaluate-best_first_add_w3-s17 | 1 | 18823 | succeeded | 0.4226 |
| **total** | | | | **4.838 / 30** |

Concurrent jobs always held distinct ports (18822/18823). The pool 18822–18825 was reused only across non-overlapping jobs. There were no failed attempts and no relaunches. For comparison, the worst-case estimand was 12.41 GPU-h. These hours are not added to any other ledger.

## Evidence index (sha256, first 16)

```
bb814180b0126a7c  budget.json
a35d9e7e280a6189  preparation/store.json
2b0d7c369cd5cb55  preparation/report.json
80fee09702c5bda8  preparation/audit.json
9b0f30f00cc2384c  preparation/episodes/** (240 files)
7df0de0c2121122d  train-tasks/** (12200 files)
8233fec852c693c9  train-views/** (15391 files)
86c07dbd4a16ab25  training/audit.json
42988c736ee98849  training/best_first_add_greedy/seed-17/report.json
b5fdfbe828953e72  training/best_first_add_w3/seed-17/report.json
0a556696d6100b38  training/best_first_add_greedy/seed-17/final/adapter_model.safetensors
b8976d58b08f98d7  training/best_first_add_w3/seed-17/final/adapter_model.safetensors
44d09ab0a263de9c  smoke/smoke.json
cb841787de317590  smoke/audit.json
042a853743e67074  smoke/episodes/** (6 files)
85c840cad5d89dbb  evaluation/bindings.json
f1e81e99e080a062  evaluation/evaluation.json
cac3c4d24801675f  evaluation/cells.json
57d0ac9a2d78feb5  evaluation/episodes/** (24 files)
039129f51c243f37  evaluation/views/** (1324 files)
96d7db859ab71cd2  metrics/analysis.json
070b0d1f38ff52d1  metrics/all-episode-metrics.json
0e6a28e53ac7e3d2  jobs/cfv3-train-best_first_add_greedy-s17/** (8 files)
5664183cae348d68  jobs/cfv3-train-best_first_add_w3-s17/** (8 files)
3bb6ef157f264204  jobs/cfv3-smoke/** (8 files)
f79454c4350aa793  jobs/cfv3-evaluate-best_first_add_greedy-s17/** (10 files)
3453327f35ae65f6  jobs/cfv3-evaluate-best_first_add_w3-s17/** (10 files)
93d12083de333118  evidence-index.json (sha256 of all 29,310 files)
```

Root: `outputs/choice-frontier/v3/` (untracked by repo convention). Each directory digest (`/**`) is the sha256 of the sorted `path sha256` lines from `evidence-index.json`.

Tracked inputs:
- `configs/experiments/choice-frontier-v3/{protocol,training-tasks,membership,cfv3-*-job}.json`
- `docs/experiments/choice-frontier/{issue-136-protocol.md,schedule-v3.json}`
- `scripts/{run_choice_frontier_v3,analyze_choice_frontier_v3}.py`
- `tests/planning_benchmark/test_choice_frontier_v3_augmentation.py` (13 passed; ruff clean on both scripts)

## Limitations

- **Development-stage, single training seed.** The ticket was edited to one seed, so seed-to-seed variance is unmeasured. "Each seed > 0" in the POSITIVE rule is the s17 estimate only.
- **One panel.** 12 tasks from 7 domains, C\* 8–15, admitted by #135's controls-only screening, which selects tasks where random control is discriminative. The effect is concentrated on depot-935011, elevators ×2, storage ×2, grid and hanoi-935000. 15puzzle, both blocksworld tasks and hanoi-935002 stay at 0.
- **Controls and base are reused from #135**, not rerun. Their equality with the frozen #135 analysis was asserted, not re-sampled.
- **Imitation, not planning.** Teacher agreement above chance is modest (+0.085), and learned M1 sits at the eps-0.75 rung, far below exact (0.875). The claim is "better than uniform frontier choice on this panel", not parity with the teacher.
- M2/M3 condition on solving, and M1 weights sub-2× budgets.
- Protocol-level interpretation choices were frozen before generation: the seed-major walk, goal-selection decisions counted as records, the seeded sample order, and the 2R_t cap (R_t = exact expansions, as in #135).
