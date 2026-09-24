# Issue #140 closeout — choice-frontier DAgger round (seed 17 under Amendment A1)

Protocol `docs/experiments/choice-frontier/issue-140-protocol.md` (frozen 43d9152 before any rollout; Amendment A1 c22a926 before any training or evaluation outcome). Machine-readable twin `configs/experiments/choice-frontier-v5/protocol.json`. Analysis `outputs/choice-frontier/v5/metrics/analysis.json` (`scripts/analyze_choice_frontier_v5_dagger.py`, committed 762717d / 129b37e before any v5 outcome).

**Amendment A1 (hard 14:21 UTC deadline):** seed 17 only. The two seed-29 collection jobs were cancelled; seed 71 was not run. Each cell's corpus is the first 512 on-policy records plus the first 512 replay draws, ×2 augmentation = 2048 samples (64 steps). The primary and co-primary use the unchanged rules on seed 17.

## Results

**Primary (pooled 23 tasks, seed 17): NOT_SEPARATED.** S_pool = M1(DAgger) − M1(exact-eps-0.75) = **+0.115 [−0.026, +0.258]**. M1(DAgger s17) is 0.394 [0.264, 0.527]; eps-0.75 (5-seed mean) is 0.279.

**Co-primary: INCONCLUSIVE.** Δ_pool = M1(DAgger s17) − M1(pre-DAgger s17) = **−0.030 [−0.114, +0.057]**. The pre-DAgger s17 M1 is 0.424. The interval does not fall inside ±0.05, so this is not EQUIVALENT.

Per panel (descriptive, seed 17):

| panel | M1 DAgger | M1 pre-DAgger | eps-0.75 | random | S vs eps-0.75 | Δ vs pre-DAgger | D3 vs random (#138 rule) |
|---|---:|---:|---:|---:|---|---|---|
| #135 (12 tasks) | 0.313 | 0.349 | 0.347 | 0.021 | −0.034 [−0.197, +0.135] NOT_SEPARATED | −0.036 [−0.130, +0.052] | +0.292 [+0.133, +0.466] POSITIVE |
| P2 held-out (11 tasks) | 0.483 | 0.506 | 0.205 | 0.016 | +0.278 [+0.082, +0.473] SEPARATED_ABOVE | −0.023 [−0.170, +0.131] | +0.467 [+0.269, +0.670] POSITIVE |

**Reading.** One DAgger round at this scale (512 on-policy + 512 replay records, 64 steps, one seed) does not measurably change choice quality. Every Δ interval straddles 0 with point estimates slightly negative. The pooled separation from eps-0.75 remains unresolved, as it was for the pre-DAgger adapters in #139 (pooled 35-task S = +0.058 [−0.040, +0.156]). What does move is behaviour: the last-label rate drops (#135 panel 0.205 → 0.137) and teacher agreement minus chance stays about the same (P2 0.113 vs 0.120). The pre-DAgger interval-separation on held-out P2 (+0.227 in #139) reproduces with the DAgger adapter (+0.278).

M1 = the #135 trapezoidal solve-versus-budget AUC. Every interval is the paired task-cluster bootstrap, `Random(133)`, 10,000 draws, 95% percentile. Controls, the exact-eps ladder and the pre-DAgger learned episodes are reused read-only (#135 zoo, #139 P2 zoo, #136 s17 evaluation, #139 P2 evaluation). The analyzer recomputes the #138 panel separation from the reused data: S(pre-DAgger 3 seeds, #135) = −0.041 [−0.187, +0.102], matching #138.

## Collection (seed 17; `collection` block)

| cell | episodes walked | model calls | records (k ≥ 2) | agreement (all records) | agreement (512 used) | chance (1/k) | goal reached | replay |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| greedy s17 | 88 | 1252 | 1047 | 0.395 | 0.379 | 0.149 (first 45 eps) | 23/45 used eps | 88/88, 0 mismatch |
| w3 s17 | 89 | 1264 | 1045 | 0.389 | 0.361 | 0.153 (first 45 eps) | 25/45 used eps | 89/89, 0 mismatch |

- **Rollout tasks.** The universe is the #136 walk order after the recorded skips: 267 `candidate_overlap` rows (training tasks whose `problem_sha256` equals a #139 candidate row; the #139 generator rejected them as overlaps; 0 match a #135 candidate) and 738 `no_136_views` rows. This leaves 177 tasks. Seed 17 used the first 88/89 tasks to reach ≥ 1024 records. No observation overflow occurred.
- **Teacher labels.** Each label is the menu label of the exact heap head of the *current* on-policy frontier. `audit-collect` replayed every episode (inputs, menus, view bindings, runtime results, results) and recomputed every teacher label: 0 mismatches.
- The on-policy agreement is 0.36–0.40, against 0.15 chance. The adapters leave the teacher's choice on about 60% of their own decisions, which is the drift DAgger targets.

## Corpus and training

- Membership `configs/experiments/choice-frontier-v5/membership.json` (`membership_sha256` `b266b8e526d63013…`, committed c22a926 before training). Per algorithm:
  - the first 512 on-policy records (45 episodes);
  - 512 #136 replay records (the first 512 draws of `Random("replay:{alg}:17").sample(ids, 1024)`);
  - ×2 `augment_menu`, shuffled with `Random("order:dagger:{alg}:17")`: 2048 samples.
  - Store `outputs/choice-frontier/v5/preparation/store.json`.
- **Continue-training** from the #136 seed-17 adapter (`PeftModel.from_pretrained(..., is_trainable=True)` via the new optional `train_visual(init_adapter=...)`). The #136 recipe otherwise: 64 steps, global batch 32, lr 1e-4 cosine, warmup 0.03, LoRA r 64 / alpha 128 / dropout 0.05, bf16, seed 17.
- `audit-train` passes both cells: loaded-from = base adapter, r 64, alpha 128, dropout 0.05, 64 steps, 2048 samples, seed 17, membership sha.
- GPU-h: greedy 1.007, w3 0.982.

## Smoke gate

The #132 definition on the seed-17 DAgger adapters (`cfv5-smoke-s17`): 32/32 accepted calls, rate 1.0 ≥ 0.5, **PASS**. `audit-smoke` replayed all 6 episodes and matches.

## Evaluation

- DAgger s17 × 2 algorithms on the frozen #135 panel (12 tasks) and P2 (11 tasks). Greedy decoding, inference seed 17, cap 2R_t (#135/#139 exact expansions). Native views are the frozen #135 and #139 reports, read-only; live renders go under v5.
- `finalize`: #135 panel 24/24 and P2 22/22 episodes independently replayed, 0 missing, 0 mismatches.
- The P2 jobs finished at 13:28 UTC, before the 13:55 A1 fallback, so the pre-registered primary is evaluable. The deadline stopper `cfv5-p2` was stopped unused.

## Budget (`outputs/choice-frontier/v5/budget.json`, cap 40)

| job | GPU | port | GPU-h | status |
|---|---|---|---:|---|
| cfv5-collect-greedy-s17 | 1 | 18830 | 1.656 | succeeded |
| cfv5-collect-w3-s17 | 0 | 18831 | 1.660 | succeeded |
| cfv5-collect-greedy-s29 | 1 | 18830 | 0.897 | cancelled under A1 (charged) |
| cfv5-collect-w3-s29 | 0 | 18831 | 0.897 | cancelled under A1 (charged) |
| cfv5-train-greedy-s17 | 0 | 18830 | 1.007 | succeeded |
| cfv5-train-w3-s17 | 1 | 18831 | 0.982 | succeeded |
| cfv5-smoke-s17 | 0 | 18830 | 0.046 | succeeded |
| cfv5-evaluate-v2-greedy-s17 | 0 | 18830 | 0.629 | succeeded |
| cfv5-evaluate-v2-w3-s17 | 1 | 18831 | 0.440 | succeeded |
| cfv5-evaluate-p2-greedy-s17 | 1 | 18831 | 0.498 | succeeded |
| cfv5-evaluate-p2-w3-s17 | 0 | 18830 | 0.352 | succeeded |

**Total 9.06 / 40 GPU-h.** Concurrent jobs always ran on distinct ports from the 18830-18833 pool.

## Judgement calls

1. **Rollout-task filter** (pre-registered in the protocol, 43d9152). The ticket's assertion "no rollout task matches any #139 candidate" cannot hold over all #136 training tasks. 267 of them equal #139 candidate rows that #139 rejected as overlaps. They were skipped rather than asserted, and the assertion holds on the rolled-out set.
2. **Rollout universe limited to tasks with frozen #136 views** (177 tasks; the #136 visual observation contract). The walk never came close to exhausting it (88/89 tasks used).
3. **Observation overflow rule** (terminate the episode, no record). Pre-registered; it never fired.
4. **`train_visual(init_adapter=...)`** in `examples/planning_benchmark_slice/visual_model.py`. This is an optional argument; the default path is unchanged.
5. **Amendment A1** (orchestrator, on the author's behalf, 11:21 UTC): seed 17 only, 512 + 512 corpus, 2048 samples, 64 steps, s29 collection cancelled (1.79 GPU-h charged), s71 not run.
6. The P2 evaluation jobs were moved to the GPU that freed first (greedy on GPU 1, w3 on GPU 0; e4e30b2, committed before launch) to fit the 13:55 UTC fallback.

## Evidence index (sha256, first 16)

```
a9dfc32e0c46fe42  budget.json
f4b89ffede157dd6  collection/audit.json
a26f4ad6541784ff  preparation/store.json
c5795594dbc359f1  training/audit-best_first_add_greedy-s17.json
c324757b0296e315  training/audit-best_first_add_w3-s17.json
8d9c90b4c1d60e60  training/best_first_add_greedy/seed-17/report.json
ddb792f4350ee8fe  training/best_first_add_greedy/seed-17/final/adapter_model.safetensors
fdda0d4be278359d  training/best_first_add_w3/seed-17/report.json
a2edd7c818e7ec50  training/best_first_add_w3/seed-17/final/adapter_model.safetensors
6afa51e3d0b5686e  smoke/smoke.json
4886e536d2b5d57b  smoke/audit.json
546bed8b71cf9beb  evaluation/v2/evaluation/bindings.json
995c7be2eaf930fb  evaluation/v2/evaluation/evaluation.json
5658c181c419fbd6  evaluation/v2/evaluation/cells.json
6bc5470a7245cdc3  evaluation/p2/evaluation/bindings.json
1fd27c76ecb62e5e  evaluation/p2/evaluation/evaluation.json
c69e8667ab32c335  evaluation/p2/evaluation/cells.json
b5d422572d186d8a  metrics/analysis.json
5ab79e11cd7a4056  metrics/dagger-episode-metrics.json
eda3f8777f49eba1  collection/episodes/** (285 files)
dd4c432899fb109e  collection/views/** (8211 files)
cac3b8e618e9fc1f  smoke/episodes/** (6 files)
c54ff9cdfacca8d4  evaluation/v2/evaluation/episodes/** (24 files)
ed67023984762532  evaluation/v2/evaluation/views/** (1364 files)
678c90fbf6834e60  evaluation/p2/evaluation/episodes/** (22 files)
6958c5e933f896b3  evaluation/p2/evaluation/views/** (1222 files)
e1575daa547a449d  jobs/** (95 files)
165bb9ec7616dcd8  evidence-index.json (sha256 of all 11312 files)
766ada5de7f39e98  configs/experiments/choice-frontier-v5/membership.json (tracked)
409fe6c024008e4a  configs/experiments/choice-frontier-v5/protocol.json (tracked)
```

The root is `outputs/choice-frontier/v5/`, untracked by repo convention. Each directory digest (`/**`) is the sha256 of the sorted `path sha256` lines of `outputs/choice-frontier/v5/evidence-index.json`.

Tracked inputs:

- `configs/experiments/choice-frontier-v5/{protocol,membership,cfv5-*-job}.json`
- `docs/experiments/choice-frontier/{issue-140-protocol.md,schedule-v5.json}`
- `scripts/{run,analyze}_choice_frontier_v5_dagger.py`
- `tests/planning_benchmark/test_choice_frontier_v5_dagger.py`

Tests: `pytest tests/planning_benchmark/test_choice_frontier_v5_dagger.py` gives 15 passed. It checks that the teacher label equals the current heap head on a deviating rollout, that the replay sampler is deterministic, and the primary/co-primary verdict boundaries. `ruff check` passes on the new scripts and test.

## Limitations

- **One DAgger round, one seed** (A1). The pre-registered 3-seed design was not run, so seed variance is unmeasured for the DAgger adapters. #138 showed a between-seed spread comparable to the effects here.
- **Half-size aggregate** (512 on-policy + 512 replay, 64 steps) instead of 1024 + 1024 (128 steps).
- **Privileged teacher.** The label is the exact h_add heap head, the same privileged signal that defines the exact-eps ladder. DAgger imitates it more closely on on-policy states; it does not add non-privileged information.
- **Two panels, 23 tasks.** The #135 panel (12) was used in the #136/#138 development line. P2 (11) is the fresh held-out panel of #139.
- Continue-training restarts the optimizer and scheduler on a mixture that is 50% replay of the original corpus, so part of the update re-fits already-seen #136 records.
