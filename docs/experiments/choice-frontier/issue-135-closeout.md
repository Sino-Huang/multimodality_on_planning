# Issue #135 closeout — choice-frontier instrument validation (fresh larger-C* panel + graded exact-eps ladder)

Executed under the frozen protocol `docs/experiments/choice-frontier/issue-135-protocol.md` (committed and pushed before any task generation) with the frozen panel `configs/experiments/choice-frontier-v2/membership.json` (committed and pushed before any evaluation episode). The schedule was `docs/experiments/choice-frontier/schedule-v2.json` (cap 4.0 GPU-h, new ledger). Every episode was independently replayed. No frozen #132/#133 file or evidence was modified, and the held-out manifest was never read. This ticket measures the **instrument**, not model planning ability.

## Results summary

### Pre-registered instrument-validity test — verdict **PASS**

All four adjacent ladder pairs have a strictly positive paired task-cluster 95% lower bound. Details: 12 tasks, bootstrap seed 133, 10,000 draws, percentile interval; each arm is averaged over its 5 seeds within each (task, algorithm) cell and then over the two algorithms. Source: `outputs/choice-frontier/v2/metrics/analysis.json` → `instrument_validity`.

| pair (left − right) | M1 left | M1 right | difference | 95% CI |
| --- | --- | --- | --- | --- |
| exact_reference − exact-eps-0.25 | 0.875 | 0.793 | +0.082 | [+0.051, +0.111] |
| exact-eps-0.25 − exact-eps-0.50 | 0.793 | 0.603 | +0.190 | [+0.126, +0.252] |
| exact-eps-0.50 − exact-eps-0.75 | 0.603 | 0.347 | +0.256 | [+0.184, +0.339] |
| exact-eps-0.75 − random_valid | 0.347 | 0.021 | +0.326 | [+0.233, +0.422] |

On a panel where random-valid control is discriminative, M1 recovers the full graded dose ladder in order. This settles the #133 question: selectors that fall between random and exact are now observed, and M1 ranks them.

### All arms (primary 2× episodes, 12 tasks × 2 algorithms)

Column notes:
- M1 = solve-versus-budget AUC.
- "2× solves" = solved fraction at m = 2.
- M2 = geometric expansion overhead ρ on solved runs only (survivor-conditioned).
- M3 = mean κ = C/C\* on solved runs only.

| arm | M1 AUC [95% CI] | 2× solves | M2 ρ (solved-only) | M3 κ (solved-only) |
| --- | --- | --- | --- | --- |
| exact_reference | 0.875 [0.875, 0.875] | 1.000 | 1.000 | 1.021 |
| exact-eps-0.25 | 0.793 [0.764, 0.824] | 0.992 | 1.089 | 1.024 |
| exact-eps-0.50 | 0.603 [0.528, 0.670] | 0.950 | 1.246 | 1.032 |
| exact-eps-0.75 | 0.347 [0.252, 0.445] | 0.717 | 1.374 | 1.023 |
| random_valid | 0.021 [0.007, 0.038] | 0.083 | 1.692 | 1.042 |
| hadd-greedy (descriptive, privileged h_add) | 0.882 [0.774, 0.955] | 0.958 | 0.962 | 1.083 |
| bfs-order (descriptive) | 0.000 [0.000, 0.000] | 0.000 | — | — |
| novelty-first (descriptive) | 0.021 [0.000, 0.052] | 0.167 | 1.909 | 1.000 |
| worst-first (descriptive) | 0.000 [0.000, 0.000] | 0.000 | — | — |
| learned_adapter (#132 adapter, descriptive) | 0.026 [0.010, 0.042] | 0.208 | 1.810 | 1.050 |
| pretrained_base (descriptive, 1-call cap) | 0.000 [0.000, 0.000] | 0.000 | — | — |

Adapter re-evaluation (`adapter_reevaluation`, descriptive; not part of the validity test):
- The frozen #132 adapters reach M1 0.026 [0.010, 0.042], at the random_valid level.
- Heap-head teacher agreement minus chance = +0.021 over 794 on-policy decisions with menu ≥ 2.
- Last-label rate is 0.300.
- The base emits no valid first choice under its frozen 1-call cap, so its M1 is 0.
- The M1 AUC gives weight to budgets m < 2 where the adapter rarely solves; its 2× solve fraction is 0.208.

## Panel

240 candidates were generated: 12 `expanded` snapshots × fresh seeds 935000–935019. Per-domain counts are in `configs/experiments/choice-frontier-v2/{candidates,membership}.json`.
- 127 were kept (8 ≤ C\* ≤ 20; no `cstar_too_expensive` rejection).
- 38 were admitted by controls-only screening.
- The freeze rule (sorted by domain and seed, ≤ 2 per domain) gave **12 tasks from 7 domains, C\* 8–15**.
- membership_sha256 `b2d909cafc22efd3997fdfaa312fd8b04af5725f0e672ffa2f0d9be70311cd07`.

R is the uncapped exact_reference expansion count (the #133 R_t). The screen column counts random-valid goals over 10 episodes (seeds 101/202/303/404/505 × 2 algorithms at cap 2R).

| task (`choice-frontier-v2/…`) | C\* | R greedy | R w3 | screen random goals |
| --- | --- | --- | --- | --- |
| `15puzzle-expanded-935006` | 8 | 46 | 12 | 1/10 |
| `blocksworld-expanded-935001` | 10 | 26 | 26 | 4/10 |
| `blocksworld-expanded-935004` | 10 | 13 | 13 | 2/10 |
| `depot-expanded-935005` | 10 | 14 | 15 | 1/10 |
| `depot-expanded-935011` | 9 | 13 | 13 | 1/10 |
| `elevators-expanded-935000` | 8 | 11 | 11 | 2/10 |
| `elevators-expanded-935013` | 8 | 11 | 11 | 2/10 |
| `grid-expanded-935016` | 8 | 9 | 9 | 4/10 |
| `storage-expanded-935000` | 10 | 20 | 17 | 1/10 |
| `storage-expanded-935001` | 8 | 18 | 15 | 2/10 |
| `towers_of_hanoi-expanded-935000` | 13 | 24 | 25 | 1/10 |
| `towers_of_hanoi-expanded-935002` | 15 | 24 | 26 | 2/10 |

## Execution record

- **Commits:**
  - protocol `f823850`
  - membership `47de39c`
  - code/schedule before the GPU launch `71eb31d`
  - evidence: this closeout commit
- **Seed substitution:** documented in the protocol. Generation calls the frozen `expanded_candidates.generate()` with the panel-protocol-v2 `expanded` profiles, which reproduces all 12 snapshots byte-for-byte at their own seeds.
- **Generator race:**
  - The first generation run called generators concurrently. The blocksworld generator's shared `STATES` temp file produced 11 spurious `generator_failed` records and silently corrupted the "successful" blocksworld runs.
  - That run was discarded. All candidates were regenerated serially, and only blocksworld hashes differed.
  - A second serial run reproduced the hashes. The committed candidates.json is from the serial run, and this was disclosed on the issue before evaluation.
- **CPU zoo:** `outputs/choice-frontier/v2/zoo/manifest.json`, complete=true.
  - 696/696 episodes observed = 12 × 2 × 29; 0 missing, 0 error.
  - Every episode was replayed with `replay_choice_episode` against a fresh PDDL authority.
  - Smoke `--limit 4` passed first.
- **GPU adapter re-evaluation:**
  - `scripts/run_choice_frontier_v2.py` (copy of the #132 runner): v1 adapters, v1 smoke gate PASS, seed 17.
  - Native views were prepared for the 12 frozen tasks only, after the membership freeze, by the `prepare_expanded_views.prepare_task` recipe; 12/12 `REFERENCE_VIEWS_PASS`.
  - **Deviation:** only the two additive native references seed the view catalog. The protocol text said four algorithms, but native bfs exceeds the expanded-study 128-expansion reference ceiling on these C\* ≥ 8 tasks. The references only seed pre-rendered states, and unseen states are rendered live. Native additive exact expansions equal the choice-contract R on every task (asserted).
  - finalize: 48/48 model episodes independently replayed, complete=true.
- **Scheduler jobs** (ledger `outputs/choice-frontier/v2/budget.json`):
  - `cfv2-evaluate-models-0`: best_first_add_greedy, GPU 0, MASTER_PORT **18818**.
  - `cfv2-evaluate-models-1`: best_first_add_w3, GPU 1, MASTER_PORT **18819**.
  - Both succeeded with launch head `71eb31d`.

## Budget accounting

Realized **1.190 GPU-h** against the 4.0 GPU-h cap:
- cfv2-evaluate-models-0: 0.687
- cfv2-evaluate-models-1: 0.503

All other stages were CPU. These hours are not added to any other ledger.

## Evidence index (sha256, first 16)

```
daffb4973e48bee5  budget.json
858bed652fcb9add  reference-views.json
321ebe4de537c47b  zoo/manifest.json
3aac0c3355fa69af  zoo/episodes/** (696 files)
d9825939c14313c4  evaluation/bindings.json
4970bfcb133a5396  evaluation/cells.json
0fede8fac98e3bfc  evaluation/evaluation.json
50c1cdb1c7cf6fcf  evaluation/episodes/** (48 files)
8c1624d8be1dac9f  evaluation/views/** (1428 files)
e7e848b3daadb342  metrics/analysis.json
7ed77da11ff0ea22  metrics/all-episode-metrics.json
38d22f5fbedcd1ed  metrics/optimal-costs.json
75b983ab1a6a9502  candidates/** (1244 files)
628e05342f67e82e  screen/** (1524 files)
1673508f6114d7cf  views/** (1277 files)
c125f1078ae72657  jobs/cfv2-evaluate-models-0/** (9 files)
821709e04ff855eb  jobs/cfv2-evaluate-models-1/** (9 files)
18b4bb87b988c537  evidence-index.json (sha256 of all 6245 files)
```

Root: `outputs/choice-frontier/v2/` (untracked per repo convention). Each directory digest (`/**`) is the sha256 of its sorted `path sha256` lines, taken from the full per-file index `evidence-index.json`. Tracked inputs:
- `configs/experiments/choice-frontier-v2/{candidates,membership,cfv2-evaluate-models-*-job}.json`
- `scripts/{build_choice_frontier_v2_panel,run_choice_frontier_v2_zoo,analyze_choice_frontier_v2,run_choice_frontier_v2}.py`
- `tests/planning_benchmark/test_choice_frontier_v2_selectors.py` (8 passed; ruff clean)

## Limitations

- **Single adapter seed**: the adapter row reflects one #132 training seed. It is descriptive and does not enter the validity test.
- **Privileged selectors**: exact-eps reads the heap head and hadd-greedy reads stored h_add. The ladder validates the metric's ordering, not any realizable policy.
- **One panel**: 12 tasks from 7 domains, C\* 8–15, admitted by controls-only screening. Screening selects for tasks where random control is discriminative. It does not bias evaluation, because screening and evaluation seeds are disjoint.
- **M2/M3 are survivor-conditioned**, and M1 weights sub-2× budgets.
