# Choice-frontier adapter scale-up protocol — issue #136

Frozen and committed before any #136 training-task generation (2026-09-24 UTC). Machine-readable twin: `configs/experiments/choice-frontier-v3/protocol.json`. This is a new follow-up to #132/#135. It amends no #132/#133/#135 protocol, script, config or evidence: frozen files are copied, never edited. The frozen held-out manifest `data/bfws_phase_v1/fresh-test-manifest.jsonl` and `data/curriculum_pddl/*/dev/` are never read.

Precondition verified before this protocol was written: #135 is CLOSED with closing comment `Verdict: PASS`, and `outputs/choice-frontier/v2/metrics/analysis.json` has `instrument_validity.verdict == "PASS"`.

## Seeds (ticket edit: "1 seed (to speed up)")

The ticket was edited by its author to train **one** seed. Wherever the ticket text still says "seeds 17, 29, 71", "6 cells", or "per-seed <s29>, <s71>", this protocol reads it as the single training seed **17**:

- Training seeds: **{17}**. Cells: 2 algorithms × 1 seed = **2 cells** (`best_first_add_greedy`/seed-17, `best_first_add_w3`/seed-17).
- The primary endpoint's "mean over seeds" is the seed-17 value; the POSITIVE rule's "each seed's point estimate > 0" is the seed-17 point estimate > 0. Bootstrap draws average over the one seed present (a no-op).
- Only s17 is reported in the closing comment.

## Step-2 budget estimate (computed before generation)

Measured inputs (from the ticket): #132 `train_runtime` 1408.67 s for 512 samples ≈ **2.75 s/sample**.

- Per cell: 2048 records × 2 augmentations = 4096 samples × 2.75 s = 11,264 s = **3.129 GPU-h**.
- Training: 2 cells × 3.129 = **6.258 GPU-h** (the ticket's 18.8 GPU-h figure was for 6 cells).
- X = #135 adapter re-evaluation GPU-h from `outputs/choice-frontier/v2/budget.json` = cfv2-evaluate-models-0 0.68687 + cfv2-evaluate-models-1 0.50273 = **X = 1.1896 GPU-h**.
- Evaluation: the ticket's "3 × X" was written for three seeds. With one seed the expected evaluation cost is 1 × X = 1.1896 GPU-h. The record-count decision below uses the ticket's conservative literal **3 × X = 3.5688 GPU-h**.
- Smoke gate: 0.1 GPU-h.
- **Worst-case estimand** = 1.25 × (6.258 + 3.5688 + 0.1) = 1.25 × 9.9268 = **12.41 GPU-h** ≤ 30. (With the one-seed 1 × X evaluation: 1.25 × 7.548 = 9.43 GPU-h.)
- Decision: **keep 2048 records per algorithm.** The seed-count fallback is moot.

Pre-registered runtime projection (before training, after `prepare`): the ticket's 2.75 s/sample was measured on the #132 corpus (mean input 4,867 tokens). After `prepare`, the projected per-cell training time is `4096 × 2.75 s × (mean v3 input tokens / 4,867.08)`. If this exceeds `max_seconds_per_cell` (18,000 s), the step-2 record ladder is applied in order: 1536 records (the first 1536 in walk order), then 1024. If it still exceeds 18,000 s at 1024, keep 1024. This check and its outcome are written into `report.json` and the membership, and happen before any training.

## Backbone and algorithms

- `Qwen/Qwen3-VL-8B-Instruct`, revision `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b` (the #132 pin, `choice-frontier-protocol-v1.json`).
- `best_first_add_greedy` and `best_first_add_w3`. One adapter per (algorithm, seed), as in #132.
- Observation, output and runtime contract: the frozen `visual-choice-frontier-v1` contract, byte-identical to #132. Menu order at inference uses `examples/planning_benchmark_slice/choice_frontier.py::permuted_menu` (the per-decision seeded Fisher-Yates via `menu_permutation_seed`, master seed 51131), unchanged.

## Training task source

- The 24 generator snapshots in `configs/experiments/expanded-study/tasks/` (all 12 domains × `compact` and `expanded`). Only the seed changes. Generation calls the frozen `examples/planning_benchmark_slice/expanded_candidates.generate(root, profile, seed, output)` with the `configs/experiments/expanded-study/panel-protocol-v2.json` stratum profiles. That call reproduces the snapshots and places the seed per generator (the #135 seed-substitution mechanism: `-s`, `-r`, `-e`, `--seed`, positional, or the legal initial-state walk for gripper/towers_of_hanoi and the 15puzzle goal walk).
- Seeds **945000–945099** (100 per stratum, 2,400 tasks). All generator runs are **serial** (the blocksworld generator shares a cwd `STATES` temp file; concurrent runs corrupt output, as found in #135).
- Task id `choice-frontier-v3-train/<domain>-<difficulty>-<seed>`. Task file `outputs/choice-frontier/v3/train-tasks/<domain>-<difficulty>-<seed>/task.json`, same format as the #135 candidates.

## Exclusion rule

`problem_sha256` = sha256 of the task's `problem_pddl` (UTF-8). A generated task is dropped, and the drop logged in `configs/experiments/choice-frontier-v3/training-tasks.json`, if its `problem_sha256` equals that of:

- (a) any of the 240 records in `configs/experiments/choice-frontier-v2/candidates.json` (the record's `problem_sha256`);
- (b) any task in `configs/experiments/expanded-study/final-panel.json` (sha of `problem_pddl` in each task's `task_path`);
- (c) any task in `configs/experiments/choice-frontier/membership.json` (sha of `problem_pddl` in `data/best_first_paired_phase_v3/exact-traces/pairs/<task>/task.json` for every task id in its training and diagnostic record ids).

Also dropped and logged: `generator_failed` (generator error), `initial_goal` (initial state satisfies the goal; no decision exists), and `duplicate_training_task` (the same `problem_sha256` as an earlier task in walk order, so that no problem is trained twice under two ids). Per task the file records `task_id, generator_command, problem_sha256, excluded, exclude_reason`.

## Walk order (ambiguity resolution, frozen here)

The ticket says "walk the tasks in order (domain, difficulty, seed)". A domain-major lexicographic sort would fill all 2048 records from `15puzzle-compact` alone, which contradicts drawing the corpus from the 24 snapshots. This protocol therefore walks **seed-major**: for seed = 945000, 945001, …, and within each seed the 24 strata in (domain, difficulty) order. Each (domain, difficulty, seed) task is visited exactly once, in a fixed, pre-registered order.

## Corpus records

- Teacher episode per (task, algorithm): the choice-contract `exact_reference` session (`ChoiceFrontierModelSession`, arm `exact_reference`, seed 17), derived **from PDDL** with no cap (the runtime always expands the heap head). There are no stored traces for fresh tasks, so the #132 trace gate does not apply: `trace_gate: "not_applicable_fresh_tasks"`.
- A decision is **eligible** iff its menu offers **≥ 2 states** and its observation passes the frozen 32K token gate (`input_tokens + 384 ≤ 32768`; overflowing decisions are skipped and counted). Goal-selection decisions count: the ticket defines records per decision, not per expansion.
- Per task and algorithm, take the **first 64 eligible decisions in episode order**. Derivation stops after the 64th eligible decision or at episode end. A (task, algorithm) derivation that takes longer than 600 s is dropped with reason `derivation_timeout`. A task whose scene rendering fails is dropped with reason `view_render_failed`.
- Per algorithm, walk the tasks in walk order and take records until the **target (2048)**. The last task may be partially taken. Record id: `<task_id>:<algorithm>:<decision_index>`.
- Diagnostics (the trainer's teacher-forced eval, never trained on): the **next 16 eligible records** in the same walk after the target, unaugmented.
- If the seeds run out before the target: use every record. If that is ≥ 1024 per algorithm, continue and record the real count. If it is < 1024, generate seeds 945100–945299 once (same rules). If still < 1024, take the blocked exit.
- Views: per task, one scene catalog holds every state of both algorithms' truncated teacher episodes (the initial state plus every admitted successor of each expansion before the last taken decision). It is rendered by the frozen planimation path (`collect_task_scenes`, backend `http://127.0.0.1:18092`, 128 px, the `configs/experiments/issue71/v2/render.json` profiles), with goal pages and unlabelled scene-only static pages exactly as `scripts/prepare_expanded_views.py::prepare_task` builds them for panel tasks. Training observations are assembled by the frozen `build_choice_observation` layout (the same function the evaluation views call).

## Menu-order augmentation (against the last-label shortcut)

- Each training record appears **2 times**. Sample k ∈ {0, 1} permutes the record's menu with `random.Random(f"aug:{record_id}:{k}").shuffle(...)` over the record's menu states (in the runtime menu order), then relabels `c0..cK` in the new order. Scenes stay bound to their states. The target is the label of the **teacher's (exact heap head) state after permutation**. Only the label↔scene pairing changes, so input text and token count are unchanged.
- Implemented in `scripts/run_choice_frontier_v3.py::augment_menu`; tested by `tests/planning_benchmark/test_choice_frontier_v3_augmentation.py`.
- Augmentation check (in `report.json`): a histogram of target label position (first / middle / last) over all samples, and the chance rate of "last" = mean of 1/menu_size. The target-is-last share must be within ±5 percentage points of that chance rate. Otherwise the code is fixed (never the rule) and `prepare`/`audit-prepare` re-run, at most 3 times, then the blocked exit.
- Sample order: the 4096 (record, augmentation) samples are shuffled once with `random.Random(f"order:{training_seed}")` and then fed sequentially (the #132 `SequentialSampler`). Unshuffled membership order would put 32 records of one task in every batch.

## Recipe

1 epoch over the augmented samples (4096 → **128 optimizer updates**), global batch 32, microbatch 1, lr 1e-4 cosine, warmup ratio 0.03, LoRA r=64, alpha=128, dropout 0.05, all-linear excluding visual, bf16, adamw_torch, weight decay 0, max grad norm 1, gradient checkpointing. Everything else is `configs/experiments/matched-modalities/study-v5.json` `training` via `train_visual`, as in #132. `max_seconds_per_cell` = 18000. Adapters: `outputs/choice-frontier/v3/training/<algorithm>/seed-<seed>/final/`. `audit-train` checks r=64, alpha=128, steps = ceil(samples/32), seed, record count and sample count.

## Smoke gate

Identical to the #132 definition: the three #132 panel tasks `expanded-final/storage-compact-919000`, `expanded-final/elevators-compact-914002` and `expanded-final/ferry-compact-915000`, both algorithms (6 episodes), `learned_adapter`, seed 17, greedy decoding, cap 2 × #132 reference expansions, native views from `outputs/expanded-study/v1/panel-v2/reference-views.json` (read-only). Rate = accepted calls / model calls; **PASS iff ≥ 0.5**. It runs on the seed-17 adapters (scheduler job `cfv3-smoke`, writes under `outputs/choice-frontier/v3/smoke/`) before any panel evaluation, then `audit-smoke` replays all 6 episodes. On FAIL: no evaluation, verdict `SMOKE_FAIL`.

## Evaluation

- `learned_adapter` for every (algorithm, seed) on the frozen #135 panel `configs/experiments/choice-frontier-v2/membership.json` (12 tasks). The runner asserts membership_sha256 `b2d909cafc22efd3997fdfaa312fd8b04af5725f0e672ffa2f0d9be70311cd07`. Greedy decoding, inference seed 17, frozen #132 inference settings.
- Decision cap: R_t = the uncapped `exact_reference` choice-contract **expansion** count, `reference_costs[alg]["expansions"]` in the #135 membership (the #133/#135 R_t). Cap = 2 × R_t, simultaneously the decision and the expansion cap, exactly as #135. The ticket says "2 × the exact reference decisions". The exact decision count is R_t + 1 (the goal selection is uncharged), and this protocol uses the #135 cap so that v3 learned episodes are directly comparable with the reused #135 controls and base.
- Native views: the #135 `outputs/choice-frontier/v2/reference-views.json` (read-only). Live-rendered states and per-episode caches go under `outputs/choice-frontier/v3/evaluation/`.
- Jobs `cfv3-evaluate-<algorithm>-s<seed>` (2 jobs: one per algorithm, 12 episodes each).
- Controls (`exact_reference` seed 17; `random_valid` seeds 17/5077/6131/7409/8527) and `pretrained_base` are **reused from #135**, not rerun: `outputs/choice-frontier/v2/zoo` and `outputs/choice-frontier/v2/evaluation`, with optimal costs from `outputs/choice-frontier/v2/metrics/optimal-costs.json`.
- `finalize` independently replays every v3 model episode and must report 0 mismatches and 0 missing.

## Primary endpoint

D = mean over training seeds of [M1(learned, seed) − M1(random_valid)], where M1 is the #133/#135 trapezoidal solve-versus-budget AUC (m ∈ {1, 1.25, 1.5, 1.75, 2}, weights 0.125/0.25/0.25/0.25/0.125). Per task, it is averaged over the two algorithms (random_valid first averaged over its 5 seeds within each cell). Metric functions are imported from `scripts/analyze_choice_frontier_v2.py` (`inspect_episode`, `summarize`), not copied.

Interval: task-cluster bootstrap, `random.Random(133)`, 10,000 draws. Each draw resamples the 12 tasks with replacement and averages the per-task difference (averaged over the seeds present) over the drawn tasks. Report the 95% percentile interval with the #135 percentile convention.

## Pre-registered margins and decision rule

Materiality margin **δ = 0.05** M1 units; equivalence margin **±0.05**. On D and its 95% CI [lo, hi], applied in this order:

- **POSITIVE**: lo > 0 **and** D ≥ 0.05 **and** each seed's point estimate > 0.
- **EQUIVALENT** (null): −0.05 < lo **and** hi < +0.05.
- **NEGATIVE**: hi < 0.
- **INCONCLUSIVE**: anything else.

No number above changes after any result is seen. The only allowed changes are the fallbacks written here and in the ticket.

## Secondary endpoints (descriptive)

- Per-seed M1 with task-cluster CI.
- Teacher heap-head agreement minus chance per seed (on-policy decisions with menu ≥ 2), with a task-cluster CI from the same bootstrap (ratio of summed agreement−chance over summed decisions per draw).
- Last-label rate.
- Learned M1 next to the #135 exact_reference, exact-eps-0.25/0.50/0.75 and random_valid M1 values (`ladder_position`).

## Budget and scheduling

Cap **30 GPU-hours** on the new ledger `outputs/choice-frontier/v3/budget.json`, schedule `docs/experiments/choice-frontier/schedule-v3.json`. These hours are never added to any other ledger, and failed attempts count. MASTER_PORT pool **18822–18825**, a distinct port per concurrent job, at most one job per GPU (2 × A100 80GB). All GPU work goes through `scripts/run_expanded_study.py launch`. An infrastructure failure is relaunched at most twice, then the cell is dropped and recorded. The recipe never changes.

## Commits

1. This protocol (+ protocol.json): before generation.
2. `scripts/run_choice_frontier_v3.py` + `training-tasks.json` + `membership.json`: before training.
3. Schedule, job files, analyzer, test and closeout: evidence commit.
