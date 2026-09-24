# Choice-frontier adapter 3-seed replication protocol — issue #138

Frozen and committed before any #138 GPU launch (2026-09-24 UTC). Machine-readable twin: `configs/experiments/choice-frontier-v4/seeds-protocol.json`. This follow-up to #136 amends no #132/#133/#135/#136 protocol, script, config or evidence. Frozen files are copied, never edited. The held-out manifest `data/bfws_phase_v1/fresh-test-manifest.jsonl` and `data/curriculum_pddl/*/dev/` are never read.

Precondition: #136 is CLOSED with `Verdict: POSITIVE`, D = +0.328 [+0.155, +0.508] (`outputs/choice-frontier/v3/metrics/analysis.json`).

## Training

- **Cells:** seeds **29** and **71** × {`best_first_add_greedy`, `best_first_add_w3`} = **4 cells**. Seed-17 adapters are reused read-only from `outputs/choice-frontier/v3/training/<algorithm>/seed-17/final/`.
- **Frozen corpus.** The corpus is read read-only from `configs/experiments/choice-frontier-v3/{protocol,membership,training-tasks}.json` and `outputs/choice-frontier/v3/preparation/store.json`. The runner recomputes the #136 `membership_sha256` and requires `f5cc9b2ac3b2fe8e94b7a8039e6b9cd828c701a8c5b707ddd7a3b01b2ca8c077`. The augmentation (`scripts/run_choice_frontier_v3.py::augment_menu`, imported unchanged, 2 copies, seeds `aug:{record_id}:k`) and the 2048 records per algorithm are identical to #136.
- **Recipe:** the #136 recipe, byte-identical (study-v5 training block via `train_visual`, 1 epoch over 4096 samples = 128 updates, global batch 32, lr 1e-4 cosine, warmup 0.03, LoRA r 64 / alpha 128 / dropout 0.05, bf16, `max_seconds_per_cell` 18000). Only `training_seed` changes.
- **Sample order (recorded decision).** The #136 code (`run_choice_frontier_v3.py::AugmentedChoiceDataset`) ties the sample order to the training seed: `random.Random(f"order:{training_seed}")`, which was `order:17` for #136. The ticket requires the sample order to be identical to #136 so that the seed changes **only** the LoRA init and dropout. v4 therefore **pins `random.Random("order:17")`** for seeds 29 and 71. The sequence of (record, augmentation) samples is then byte-identical to #136. The training seed still reaches `transformers.set_seed` and `TrainingArguments.seed` (LoRA init, dropout). `data_seed` has no effect under the #132 `SequentialSampler`.
- **Audit-train:** the #136 checks: adapter present, r = 64, alpha = 128, dropout 0.05, steps = ceil(4096 / 32) = 128, seed, 2048 records and 4096 samples.
- Adapters: `outputs/choice-frontier/v4/seeds/training/<algorithm>/seed-<seed>/final/` (the #139 contract path).

## Smoke gate

This is the #132/#136 definition: `expanded-final/storage-compact-919000`, `expanded-final/elevators-compact-914002` and `expanded-final/ferry-compact-915000` × 2 algorithms (6 episodes), `learned_adapter`, seed 17, greedy, cap 2 × #132 R, native views `outputs/expanded-study/v1/panel-v2/reference-views.json`. It runs on the **seed-29** adapters (job `cfv4-smoke-s29`). PASS iff accepted calls / model calls ≥ 0.5, and `audit-smoke` replays all 6 episodes. On FAIL: no evaluation, verdict `SMOKE_FAIL`, closeout and close.

## Evaluation

- `learned_adapter` for the 4 new cells on the frozen #135 panel `configs/experiments/choice-frontier-v2/membership.json` (12 tasks; membership_sha256 `b2d909cafc22efd3997fdfaa312fd8b04af5725f0e672ffa2f0d9be70311cd07`, asserted). Greedy decoding, inference seed 17, and the frozen #132/#136 inference settings.
- Cap = 2 × R_t, where R_t = the #135 uncapped exact_reference expansions (`reference_costs[alg]["expansions"]`). It is both the decision and the expansion cap, as in #135/#136.
- Jobs `cfv4-evaluate-<algorithm>-s<seed>` (4 jobs × 12 episodes = 48 episodes). `finalize` independently replays every episode and must report 0 missing and 0 mismatches.
- Reused, not rerun:
  - from #135: controls (`exact_reference` s17; `random_valid` and `exact-eps-0.25/0.50/0.75` at seeds 17/5077/6131/7409/8527; `outputs/choice-frontier/v2/zoo`), `pretrained_base` and optimal costs;
  - from #136: the seed-17 learned episodes (`outputs/choice-frontier/v3/evaluation`, finalized complete).

  The analyzer recomputes the reused control M1 per task and asserts equality with the frozen #135 analysis. It recomputes the seed-17 learned M1 and asserts equality with the frozen #136 analysis.

## Primary endpoint (the #136 rule, 3 seeds)

D3 = mean over seeds s ∈ {17, 29, 71} of [M1(learned, s) − M1(random_valid)]. M1 is the #133/#135 trapezoidal solve-vs-budget AUC (functions imported from `scripts/analyze_choice_frontier_v2.py`). Per task it is averaged over the two algorithms, with random_valid first averaged over its 5 seeds.

CI: task-cluster bootstrap, `random.Random(133)`, 10,000 draws, 95% percentile with the #135 convention. Each draw resamples the 12 tasks with replacement and averages the 3 seeds inside the draw.

Margins δ = 0.05 and equivalence ±0.05 (unchanged). Rules are applied in order:

- **POSITIVE:** lo > 0 **and** D3 ≥ 0.05 **and every** seed's point estimate > 0.
- **EQUIVALENT:** −0.05 < lo **and** hi < 0.05.
- **NEGATIVE:** hi < 0.
- **INCONCLUSIVE:** otherwise.

## Pre-registered separation test (co-primary)

S = M1(learned, 3-seed mean) − M1(exact-eps-0.75), with eps-0.75 averaged over its 5 #135 seeds. It uses a paired task-cluster bootstrap with the same settings (per-task differences; seeds averaged inside each draw).

- **SEPARATED_ABOVE** if lo > 0.
- **SEPARATED_BELOW** if hi < 0.
- **NOT_SEPARATED** otherwise.

Per-seed S points are reported. The same test against exact-eps-0.50 is reported as descriptive only.

## Seed variance (descriptive)

- Per-seed M1 with task-cluster CI.
- Per-seed teacher heap-head agreement − chance with CI (ratio bootstrap, as in #136).
- Per-seed last-label rate.
- The between-seed SD of M1 (`statistics.stdev` over the 3 seed values).
- `ladder_position` for the 3-seed mean and for each seed.

## Budget (estimated from #136 measured hours)

- Training: 4 cells × 1.89 GPU-h = **7.56 GPU-h**.
- Evaluation: 4 cells × 0.5 = **2.0 GPU-h**.
- Smoke: **0.1 GPU-h**.
- Expected **9.66 GPU-h**; worst case × 1.25 = **12.08 GPU-h**.

The shared v4 ledger `outputs/choice-frontier/v4/budget.json` with schedule `docs/experiments/choice-frontier/schedule-v4.json` is created by this ticket: cap **24 GPU-h**, allocation `choice_frontier` 24, MASTER_PORT pool **18826–18829**. It is shared with #139, and the scheduler refuses to double-book a GPU.

- All GPU work goes through `scripts/run_expanded_study.py launch`.
- At most one job per GPU, with a distinct port per concurrent job.
- An infrastructure failure is relaunched at most twice.
- The recipe never changes.

## Code

`scripts/run_choice_frontier_v4_seeds.py` is copied from `run_choice_frontier_v3.py`. Its output root is `outputs/choice-frontier/v4/seeds/`, and it points at the v4 ledger and schedule. It reads the v3 corpus and store read-only, runs train/evaluate for seeds 29/71, and uses the completion-hook `EXPANDED_ATTEMPT_DIR` fix (the attempt dir is derived from `EXPANDED_TERMINAL_PATH`'s parent). The analysis is in `scripts/analyze_choice_frontier_v4_seeds.py` and the test in `tests/planning_benchmark/test_choice_frontier_v4_seeds.py`.

No number above changes after any result is seen.
