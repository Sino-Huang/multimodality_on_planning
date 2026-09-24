# Choice-frontier DAgger round protocol (3 seeds) — issue #140

Frozen and committed before any #140 rollout, training or GPU launch (2026-09-24 UTC). Machine-readable twin: `configs/experiments/choice-frontier-v5/protocol.json`. This follow-up amends no #132–#139 protocol, script, config or evidence. Frozen files (`scripts/*choice_frontier*.py` up to v4, `outputs/choice-frontier/{v1,o4,v2,v3,v4}/`, `configs/experiments/choice-frontier{,-v2,-v3,-v4}/`) are imported or read, never edited. The held-out manifest `data/bfws_phase_v1/fresh-test-manifest.jsonl` and `data/curriculum_pddl/*/dev/` are never read.

Why: #138 found the 3-seed #136 adapters POSITIVE against uniform choice (D3 = +0.285 [+0.140, +0.433]) but NOT_SEPARATED from the exact-eps-0.75 rung (S = −0.041 [−0.187, +0.102]). They were trained by imitation on teacher-visited states only. One DAgger round (Ross et al., 2011) rolls each adapter out, labels every visited decision with the teacher and continues training on the aggregate.

## Base policies

Six adapters, (algorithm × seed), algorithms `best_first_add_greedy` and `best_first_add_w3`:

- seed 17: `outputs/choice-frontier/v3/training/<alg>/seed-17/final/` (#136);
- seeds 29 and 71: `outputs/choice-frontier/v4/seeds/training/<alg>/seed-<s>/final/` (#138).

Each adapter is the base of its own collection and its own continue-training cell.

## Rollout collection (per algorithm × seed; GPU)

- **Tasks.** `configs/experiments/choice-frontier-v3/training-tasks.json`, rows with `excluded: false`, in the #136 frozen walk order (file order). Filters, in order, each a recorded skip:
  1. `candidate_overlap`: `problem_sha256` matches any #135 candidate (`configs/experiments/choice-frontier-v2/candidates.json`) or any #139 candidate row (`configs/experiments/choice-frontier-v4/candidates.json`, **rejected overlap rows included**). The #139 generation rejected 267 candidates as overlaps with #136 training tasks, so those training tasks share a hash with a #139 candidate row. They are skipped, and the runner asserts that no rolled-out task matches either set.
  2. `no_136_views`: the task lacks its frozen #136 derivation episode or its #136 scene-only train views (`TRAIN_VIEWS_PASS`). The #136 visual observation contract exists only for those tasks. 177 tasks remain after filters 1–2.
  3. `zero_reference_expansions`: R_task = 0.
- **R_task** = the number of `expanded` decisions in the #136 uncapped exact-reference derivation episode for the algorithm (`outputs/choice-frontier/v3/preparation/episodes/`; every episode is complete). Decision cap = expansion cap = 2 × R_task.
- **Policy.** The frozen choice-frontier contract: `ChoiceFrontierModelSession` arm `process_sft`, greedy decoding, inference seed 17, the #136 inference settings. The adapter is called at every decision (menu size 1 included), and **its own choice drives the rollout**.
- **Views.** `ChoiceFrontierTaskViews` over the frozen #136 train views (static pages, goal pages and pre-rendered teacher scenes, read-only). Unseen states are rendered live by the planimation backend (`http://127.0.0.1:18092`) under `outputs/choice-frontier/v5/collection/views/`.
- **Records.** Every decision whose menu has ≥ 2 states yields a record:
  - the menu binding, state-index binding and page sources, exactly as the model saw them;
  - the **teacher label**: the menu label of `controller.frontier_head_state_id()` on the *current* on-policy frontier (minimum (priority, generation serial)), computed before the adapter's choice is submitted;
  - agreement: the parsed `expand_choice` equals the teacher label. An unparseable output counts as disagreement, and its record is kept.
- **Overflow (recorded decision).** If a decision's observation exceeds the 32K context (`OBSERVATION_OVERFLOW`), the episode stops there with termination `observation_overflow`, and that decision yields no record.
- **Stop rule.** At most **32** records per task episode (the first 32 in episode order). Complete episodes run in walk order until the cell holds ≥ **1024** records, and `build-corpus` takes the first 1024 in walk/episode order. If the walk is exhausted first, every record is used provided there are ≥ 512; otherwise blocked exit.
- Record id: `dagger:<task_id>:<alg>:s<seed>:<decision_index>`.
- Episodes are logged under `outputs/choice-frontier/v5/collection/episodes/`. `audit-collect` independently replays every one (inputs, menus, view bindings, runtime results, result, overflow stop) and recomputes every teacher label as the heap head of the replayed frontier.

## Aggregated training set (per algorithm, seed)

- The on-policy records (1024 at target), plus **1024** records sampled without replacement from the frozen #136 corpus of the algorithm: `random.Random(f"replay:{alg}:{s}").sample(training_record_ids[alg], 1024)`. The list is read from `configs/experiments/choice-frontier-v3/membership.json` in its frozen order; the #136 `membership_sha256` `f5cc9b2a…c077` is asserted.
- The #136 menu-order augmentation ×2 (`scripts/run_choice_frontier_v3.py::augment_menu`, imported unchanged, seeds `aug:{record_id}:0/1`). The target is the teacher state's label after permutation. This gives 2 × (1024 + 1024) = **4096 samples**.
- Sample order: `samples = [(rid, copy) for rid in on_policy_ids + replay_ids for copy in (0, 1)]`, then `random.Random(f"order:dagger:{alg}:{s}").shuffle(samples)`, then sequential.
- Diagnostic split: the frozen #136 diagnostic records of the algorithm (16, unaugmented). They give a teacher-forced loss only.
- `build-corpus` writes `configs/experiments/choice-frontier-v5/membership.json` (record ids per cell, sample counts, `membership_sha256`) and `outputs/choice-frontier/v5/preparation/store.json`. The membership is committed and pushed before any training.

## Training

- **Continue training** the base adapter (alg, s): `PeftModel.from_pretrained(base, is_trainable=True)` with a fresh optimizer and scheduler. `train_visual` gains an optional `init_adapter` argument; its default behaviour is unchanged.
- The #136 recipe otherwise: study-v5 training block, 1 epoch, global batch 32, microbatch 1, lr 1e-4 cosine, warmup 0.03, bf16. LoRA r 64 / alpha 128 / dropout 0.05 / all-linear minus visual (unchanged). Training seed s, `max_seconds_per_cell` 18000.
- `audit-train`: loaded-from path equals the base adapter, r = 64, alpha = 128, dropout 0.05, steps = ceil(samples / 32) = 128, seed, and sample count equals the membership.
- Adapters: `outputs/choice-frontier/v5/training/<alg>/seed-<s>/final/`. Two cells at a time, one per GPU.

## Smoke gate

The #132 definition: `expanded-final/{storage-compact-919000, elevators-compact-914002, ferry-compact-915000}` × 2 algorithms (6 episodes), on the **seed-17 DAgger adapters** (job `cfv5-smoke-s17`). PASS iff accepted calls / model calls ≥ 0.5; `audit-smoke` replays all 6 episodes. On FAIL, the verdict is `SMOKE_FAIL` and no evaluation runs.

## Evaluation

- 6 DAgger adapters × 2 panels = 12 jobs `cfv5-evaluate-<panel>-<alg>-s<seed>`:
  - `v2`: the frozen #135 panel `configs/experiments/choice-frontier-v2/membership.json` (12 tasks; sha `b2d909ca…1cd07`, asserted);
  - `p2`: the frozen #139 P2 panel `configs/experiments/choice-frontier-v4/membership-p2.json` (11 tasks; sha `5c009e85…114e5`, asserted).
- `learned_adapter`, greedy decoding, inference seed 17, cap 2 × R_t (the #135/#139 exact expansions in the membership rows).
- Native views come read-only from `outputs/choice-frontier/v2/reference-views.json` and `outputs/choice-frontier/v4/panels/p2/reference-views.json`. Live renders go under `outputs/choice-frontier/v5/evaluation/<panel>/views`.
- `finalize` independently replays every episode (0 missing, 0 mismatches).
- **Reused, not rerun:**
  - pre-DAgger learned episodes: #135 panel from #136 (s17) and #138 (s29/71); P2 from #139;
  - controls and the exact-eps ladder: the #135 zoo and the #139 P2 zoo.
- If the #139 P2 evidence is incomplete at analysis, wait for #139 to close (poll `gh issue view 139 --json state` with ~10-minute sleeps).

## Primary endpoint (pre-registered)

Pooled 23-task set = #135 panel (12) ∪ P2 (11), clustered by task. M1 per task and seed is the #135 `summarize` per-task AUC (mean over the two algorithms).

- **S_pool** = M1(DAgger, 3-seed mean) − M1(exact-eps-0.75, averaged over its 5 seeds).
- Paired task-cluster bootstrap, `random.Random(133)`, 10,000 draws, seeds averaged inside each draw, 95% percentile interval.
- Verdict: `SEPARATED_ABOVE` if lo > 0; `SEPARATED_BELOW` if hi < 0; otherwise `NOT_SEPARATED`. `SMOKE_FAIL` if the smoke gate fails.

## Co-primary

- **Δ_pool** = M1(DAgger) − M1(pre-DAgger), paired by (task, algorithm, seed), 3-seed mean, same bootstrap.
- Verdict, in order: `IMPROVED` if lo > 0; `EQUIVALENT` if −0.05 < lo and hi < 0.05; `WORSE` if hi < 0; otherwise `INCONCLUSIVE`.

## Secondary (descriptive)

- Per panel: S, Δ and D3 = M1(DAgger) − M1(random_valid) under the #138 rule.
- Per-seed M1 with CI.
- Teacher agreement − chance.
- Last-label rate.
- On-policy teacher-agreement rate during collection.
- Ladder position per panel.

Output: `outputs/choice-frontier/v5/metrics/analysis.json`, with blocks `primary`, `co_primary`, `per_panel`, `per_seed`, `collection` and `ladder_position`.

## Budget

New ledger `outputs/choice-frontier/v5/budget.json`, schedule `docs/experiments/choice-frontier/schedule-v5.json`: cap **40 GPU-h**, allocation `choice_frontier` 40, ports 18830–18833, GPU cutoff 2026-10-20. All GPU work goes through `scripts/run_expanded_study.py launch`, at most one job per GPU.

**Cross-ledger rule.** While `outputs/choice-frontier/v4/budget.json` has a `reserved` or `running` attempt, launch only on a GPU that attempt does not hold, after `nvidia-smi` shows < 1 GB used there.

Estimate:

| component | calculation | GPU-h |
|---|---|---:|
| collection | 6 × 1024 calls × ~6 s | ≈ 10 |
| training | 6 × 4096 × 2.75 s | ≈ 19 |
| evaluation | 12 × 0.5 | ≈ 6 |
| **total** | | **≈ 35** (cap 40) |

#136 measured about 1.9 GPU-h per 4096-sample cell, so training is likely below the estimate.

**Fallback (pre-registered).** If the scheduler would exceed 40 GPU-h, drop evaluation cells in the order seed 71, then seed 29, and report which cells were dropped.

Infrastructure failures are relaunched at most 2 times; the recipe never changes.

## Code

- `scripts/run_choice_frontier_v5_dagger.py` (stages `validate`, `collect`, `audit-collect`, `build-corpus`, `train`, `audit-train`, `smoke`, `audit-smoke`, `evaluate-inputs`, `evaluate-worker`, `audit-evaluate-worker`, `finalize`). It imports the frozen v3/v4 machinery instead of copying it.
- `scripts/analyze_choice_frontier_v5_dagger.py`.
- Job files: `configs/experiments/choice-frontier-v5/cfv5-*-job.json`.
- Test: `tests/planning_benchmark/test_choice_frontier_v5_dagger.py`. It checks that the teacher label is the current heap head on a deviating rollout, that the replay sampler is deterministic, and the pooled verdict boundaries.
