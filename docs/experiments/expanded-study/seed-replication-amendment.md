# Prospective training-seed replication — frozen amendment (#127)

Frozen on 20 September 2026 before any seed-29 or seed-71 artifact exists.
Machine-readable protocol (authoritative on key names):
`configs/experiments/expanded-study/seed-replication-protocol.json`.

## Lineage and deliverable

plan.md:67-69 froze a single training seed (17) for the expanded-nine-day-v1
program and stated that any extra seeds require a prospective amendment; this
ticket is that amendment. The lineage is the historical proposal's statistical
protocol (`docs/research_proposal.md` §6.4 "at least five training seeds") and
spec #38 ("Headline cells use five seeds"), partially honoured: the current
synthesis explicitly claims no training-seed variance
(`docs/experiments/expanded-study/synthesis-v1/README.md` claim boundaries);
this amendment lets the headline contrasts report seed robustness instead.

Deliverable: replicate two decision-relevant training cells with two additional
prospective training seeds, evaluate each new seed run under the original
cell's frozen evaluation contract with independent episode replay, and append a
seed-variance addendum to the synthesis reporting every seed individually and
aggregated. Null or noisy outcomes are reported as-is; no seed is dropped after
outcomes. Closed tickets' verdicts are not modified; this amendment appends
seed-variance evidence only.

## Frozen seeds

| Seed | Role |
| ---: | --- |
| 17 | original training seed (all original cells already trained and verified) |
| 29 | additional prospective seed #1 |
| 71 | additional prospective seed #2 |

29 and 71 are arbitrary primes disjoint from every seed used by the
expanded-nine-day-v1 program (17 training/evaluation, 64 curriculum shuffled
ordering, 1729 analysis bootstrap, 90717 modality-stress bootstrap, 42613
corruption master, 1013/2027/3041/4001 random-valid rollout seeds). Seeds 29
and 71 appear in the deprecated CGAS-era issue54 `bfs_phase` outputs (different
corpus, trainer and cells, predating this program); that unrelated historical
usage shares no data or cell with this amendment and cannot taint the
selection. They are frozen before launch: no seed-29 or seed-71 artifact
exists for either selected cell family (every expanded-program cell was
trained with seed 17 only), so no outcome was observed for either seed on the
selected cells.

What a new training seed changes (trainer-code evidence):

- **Fresh-adapter cell (A):** the fresh LoRA A/B initialization
  (`set_seed(training_seed)` immediately before `get_peft_model` in
  `load_training_model`) and the `lora_dropout` 0.05 RNG. Data order is
  seed-independent (`SequentialSampler` over the frozen membership order).
- **Continuation cells (B):** only the `lora_dropout` 0.05 RNG — starting
  adapter weights are loaded from the verified seed-17 checkpoints and never
  re-initialized, the sampler is a `SequentialSampler` over the verified
  seed-17 memberships, and each cell starts a new optimizer and scheduler.
- **Evaluation:** evaluation seed 17 with greedy decoding in every arm and
  seed, identical to the original frozen contracts.

## Frozen cell selection

Selected by decision relevance, not by outcome; no outcome-based swapping.

**Cell A — the main process-SFT cell behind the expanded matched baseline
contrast:** `best_first_add_greedy × multimodal-state`, the headline algorithm
family of the program's primary positive contrast (process_sft −
pretrained_base = +0.903 pooled, synthesis-v1 §2) in the program's titular
modality. One training cell per new seed (2 total), each a fresh LoRA adapter
trained from the same pinned base (`Qwen/Qwen3-VL-8B-Instruct` @ `0c351dd0`)
on the identical frozen 512-record `membership.json` membership
(sha256 `f939f864…bc23`), one epoch, 16 optimizer updates, all hyperparameters
identical to the original v5 cell (`study-v5.json` sha256 `1f151846…d72b`).

**Cell set B — the DAgger iteration-1 vs exposure-matched continued-SFT
comparison:** `bfs × {text-state, visual-state, multimodal-state} × {dagger,
continued_sft}`. The frozen estimand is the within-modality difference of the
two arms from the same starting adapter, so all six cells are required;
dropping an arm or modality would break it. Six training cells per new seed
(12 total), each a continuation from the verified seed-17 v5 BFS starting
adapter on the verified seed-17 iteration-1 memberships: the three DAgger
aggregations (`outputs/expanded-study/v1/dagger/collection/iteration-1/…`) and
the three retained continued-SFT memberships
(`outputs/expanded-study/v1/dagger/training/membership/…`). Every replicated
cell must consume exactly the 512 record IDs in exactly the order recorded
under `training_record_ids` of the matching verified seed-17 cell report; the
runner hard-fails on any difference and never rewrites or re-stamps a verified
membership. 512 records, one epoch, 16 updates, hyperparameters identical to
the original cells (`dagger-protocol.json` sha256 `9789bf3a…f26e`).

## Frozen evaluation (same contracts as the original cells)

- **Cell A:** the expanded-baseline contract — the 24-problem unseen panel
  `expanded-panel-v2-qualified` (sha256 `f888c1b2…37cc`), process_sft arm,
  greedy float32 decoding, evaluation seed 17, per-episode call limit 2× the
  matching exact-reference decisions. 24 new episodes per seed (48 total).
  Seed 17 evidence already exists (21/24, replay-verified,
  `baseline-evaluation.json`) and is not re-run. Comparators
  (pretrained_base, random_valid, exact_reference) are reused from the
  replay-verified baseline episodes at zero new GPU cost.
- **Cell set B:** the DAgger evaluation contract — the 3-task development
  panel plus the 24-task unseen panel, BFS, evaluation seed 17, the same call
  limits. Arms: `dagger_iteration_1` and `continued_sft_iteration_1` for seeds
  17, 29 and 71 (3 × 2 × 3 × 27 = 486 new episodes). The original program
  evaluated only iteration-two final checkpoints
  (`goal6-completion-audit.json` fixed_evaluation), so the verified seed-17
  iteration-1 checkpoints were never panel-evaluated; they are evaluated here
  inference-only under the same frozen contract — without them the named
  comparison's seed-17 point could not be reported. No seed-17 artifact is
  retrained or modified. Comparators (original_process_sft, random_valid,
  exact_reference) are reused from the replay-verified original DAgger
  evaluation episodes at zero new GPU cost.
- **Independent replay:** every new episode (534 total: 48 + 486) is replayed
  CPU-only via `replay_visual_episode` over read-only persisted views — the
  same machinery as the original cells (`independently_replay`,
  `verify_episode`) — by the per-stage audit hooks and again at finalize.

## Frozen analysis

Per seed, reported individually: per-cell successes, invalid operations,
decisions and expansions; per-seed paired whole-problem contrasts (cell A:
process_sft − pretrained_base over 24 tasks; cell set B: dagger_iteration_1 −
continued_sft_iteration_1 per modality and pooled over the 72 unseen + 9
development rows) with the program's bootstrap convention (10,000 resamples,
95% percentile, seed 1729). Aggregated: mean and min–max range across the
three seeds for every rate and contrast; cross-seed aggregation is descriptive
only (n = 3). Cells and strata below 8 paired units are descriptive-only under
the tiny-subgroup rule. Publication:
`docs/experiments/expanded-study/synthesis-v1/seed-variance-addendum.md` +
`seed-variance.json` (+ CSV). `synthesis-v1/README.md` and all closed-ticket
verdicts stay byte-untouched (the synthesis regeneration anchors pin the
pre-#126 ledger); the addendum appends seed-variance evidence only.

## Budget (frozen)

Measured basis from the shared ledger: DAgger iteration-1 training
1.5938946 GPU-h per 6-cell round; DAgger evaluation 2.3913864 GPU-h per 162
fresh episodes; v5 image-modality training ≈ 0.36 GPU-h per cell; baseline
model episodes ≈ 0.0101 GPU-h each.

| Scope | Train | Evaluate | Total | Branch | Remainder |
| --- | ---: | ---: | ---: | --- | ---: |
| Cell A | 0.72 | 0.49 | **1.21 GPU-h** | expanded_baseline | 49.4711 |
| Cell set B | 3.19 | 7.17 | **10.36 GPU-h** | dagger | 37.0908 |
| **Total** | | | **≈ 11.57 GPU-h** | | |

Both remainders cover the frozen estimates with wide margin: **no transfer**;
the ticket's 6–15 GPU-h envelope holds; the 336 GPU-h total cap is unchanged.
Failed and cutoff attempts retain their hours per the accounting policy.

**Cutoff.** The shared scheduler admits a GPU job only if
`now + max_seconds` precedes the 2026-09-21T11:55:19Z program cutoff. The
ticket's not-bound-by-the-cutoff clause is a VALID_STOP safety valve, not a
schedule amendment (identical reading to #126): if the frozen scope cannot
launch inside the admissible window, the ticket declares VALID_STOP without
partial-outcome harvesting. Estimated critical path is ≈ 8 GPU-wall hours on
GPU 0 plus CPU finalize/replay — inside the window if authorized promptly.

## Execution contract

Launches go through `scripts/run_expanded_study.py launch` against the shared
production ledger; one model worker per GPU; `MASTER_PORT` from the frozen
pool 18800–18805; per-stage CPU completion audit hooks; a CPU chain job
advances stages exactly once and never relaunches a completed attempt.
Outputs live under per-seed roots
`outputs/expanded-study/v1/seed-replication/{baseline,dagger}/seed-{17,29,71}`
so no replicated artifact collides with or overwrites an original artifact.
Worker modality split follows the original DAgger mapping (worker 0:
text-state + multimodal-state; worker 1: visual-state). Backend endpoints
`http://127.0.0.1:18092` (already serving) and `18093` (started before
evaluation; CPU service, not a GPU launch).

Declared code changes (no frozen gate of the original protocols is loosened):

1. `examples/planning_benchmark_slice/visual_model.py::train_visual` —
   `TrainingArguments` `seed`/`data_seed` and the report `seed` field read
   `config["training_seed"]` instead of the hardcoded 17. Byte-identical
   behavior for every seed-17 study config; no historical artifact is re-run
   or altered.
2. `examples/planning_benchmark_slice/expanded_dagger_evaluation.py::run_cell`
   — the frozen arm gate reads `protocol["evaluation"].get("new_arms", ARMS)`
   instead of the module constant alone; the original dagger protocol declares
   `new_arms` equal to `ARMS`, so its behavior is unchanged.
3. New `scripts/run_expanded_seed_replication.py`, job configs
   `configs/experiments/expanded-study/seed-replication-*-job.json`, and a
   chain driver under `outputs/expanded-study/v1/seed-replication-chain/`.

## Design gate

GPU launches require explicit user authorization after this frozen amendment
is presented. CPU preparation (`prepare`/`validate` stages, the 18093 backend
service) is not a GPU launch. Execution rules: no outcome-based cell swapping,
no favourable reruns, only final checkpoints enter evaluation, every episode
independently replayed, complete declared coverage or explicit terminal
partial/failure report, commit/push and close only against verified evidence
including the synthesis addendum.
