# Issue #141 closeout — second realisable policy through the choice-frontier instrument (zero-shot base Qwen3-VL-8B)

Protocol `docs/experiments/choice-frontier/issue-141-protocol.md` and twin `configs/experiments/choice-frontier-v6/protocol.json`, frozen and pushed in `0fa497c` before any GPU launch or model episode. The runner, analyzer, focused test and job files were committed in `2332c2a` before the first model episode. Analysis: `outputs/choice-frontier/v6/metrics/analysis.json` (`scripts/analyze_choice_frontier_v6_zero_shot.py`). **No amendments.** No frozen #132–#140 file or evidence was modified. The held-out manifest and `data/curriculum_pddl/*/dev/` were never read.

## Arm (decided before any outcome)

- **InternVL3.5-8B with the #138 recipe was infeasible within the 30 GPU-h cap.** It was measured on CPU only. The frozen #136 choice observations average 11,748 InternVL tokens against 3,111 Qwen tokens (×3.78). The measured InternVL training step implies 7.2–9.2 GPU-h per 4,096-sample cell, so 43–55 GPU-h for the 6 cells before any evaluation. It was not run in any reduced form.
- **The arm run instead is `zero_shot_base`:**
  - the frozen base Qwen3-VL-8B with no adapter and the frozen #136 inference settings (greedy, seed 17);
  - the frozen scene-only choice observation, with one appended system sentence stating the output format and "choose the frontier state whose scene appears closest to satisfying the goal pages" (sha `d2ea2b65…9022`);
  - a deterministic output extractor;
  - the relaxed call cap 2 × R_t, the same cap as the learned adapter.
- Each (task, algorithm) has one realisation.

## Results

M1 = the #135 trapezoidal solve-versus-budget AUC. Intervals are the paired task-cluster bootstrap (`Random(133)`, 10,000 draws, 95% percentile). The sign-flip p-values are exact over all 2^n sign vectors and are descriptive.

| panel | M1 zero-shot [CI] | random_valid | eps-0.75 | Qwen adapter (3-seed) | **D3** (primary) | **S** vs eps-0.75 | **A** vs adapter |
|---|---|---:|---:|---:|---|---|---|
| #135 panel (12, development) | 0.026 [0.000, 0.063] | 0.021 | 0.347 | 0.306 | +0.005 [−0.025, +0.044] **EQUIVALENT**, p = 0.906 | −0.321 [−0.422, −0.226] **SEPARATED_BELOW**, p = 0.00049 | −0.280 [−0.425, −0.142] **SEPARATED_BELOW**, p = 0.0039 |
| P2 (11, held-out confirmatory) | 0.017 [0.000, 0.051] | 0.016 | 0.205 | 0.432 | +0.001 [−0.048, +0.051] **INCONCLUSIVE**, p = 1.000 | −0.188 [−0.239, −0.140] **SEPARATED_BELOW**, p = 0.00098 | −0.415 [−0.589, −0.248] **SEPARATED_BELOW**, p = 0.0039 |
| pooled 23 (descriptive) | 0.022 [0.003, 0.046] | 0.018 | 0.279 | 0.366 | +0.003 [−0.024, +0.033] EQUIVALENT, p = 0.896 | −0.257 [−0.324, −0.197] SEPARATED_BELOW, p = 2.4e−7 | −0.344 [−0.459, −0.232] SEPARATED_BELOW, p = 7.6e−6 |

JSON keys:

- `primary.<v2|p2>.{D3,ci95,verdict,sign_flip_p}`
- `co_primary.<v2|p2>.{S,A}.{value,ci95,verdict,sign_flip_p}`
- `pooled.{D3,S,A}`
- `permutation`

About the P2 D3 verdict: it is INCONCLUSIVE rather than EQUIVALENT only because the upper bound (+0.0511) exceeds the ±0.05 margin by 0.001. The rule was applied as frozen.

- **Per-seed adapter contrast (A).** #135 panel: s17 −0.323, s29 −0.224, s71 −0.292. P2: s17 −0.489, s29 −0.267, s71 −0.489. Source: `per_panel.<panel>.A.adapter_per_seed_difference`. Every seed of the adapter is above the zero-shot arm on both panels.
- **Ladder position (both panels).** The zero-shot arm sits between random_valid and eps-0.75 on each panel and on the pooled set, and is only just above random_valid:

  | set | zero-shot | random_valid | eps-0.75 | eps-0.50 | eps-0.25 | exact |
  |---|---:|---:|---:|---:|---:|---:|
  | #135 panel | 0.026 | 0.021 | 0.347 | 0.603 | 0.793 | 0.875 |
  | P2 | 0.017 | 0.016 | 0.205 | 0.507 | 0.745 | 0.875 |
  | pooled | 0.022 | 0.018 | 0.279 | 0.557 | 0.770 | 0.875 |

  The zero-shot arm is also below eps-0.50 (descriptive): #135 panel −0.577, P2 −0.490, pooled −0.535, all SEPARATED_BELOW. The rule selectors from #135/#139 score 0.000–0.028 on the same panels, and the frozen 1-call `pretrained_base` scores 0.000.
- **Behaviour.** Every model output was valid:

  | panel | calls | valid | solved at 2× | teacher agreement − chance | last-label rate (chance ≈ 0.13–0.14) |
  |---|---:|---:|---:|---:|---:|
  | #135 panel | 836 | 836 | 3/24 | +0.003 | 0.33 |
  | P2 | 756 | 756 | 1/22 | +0.001 | 0.28 |

  Every output used the `json_object` extractor rule (no bare-label or raw fallbacks). Generated outputs averaged 9.3 tokens, and a call took about 4.6 s. With the format stated, the untrained base is a fully valid chooser. Its choices carry no teacher signal and have a positional (last-label) bias.
- **Reuse checks.** The recomputed control/ladder M1 and the adapter per-task seed means equal `outputs/choice-frontier/v4/panels/metrics/analysis.json` exactly (`reuse_checks`, max abs diff 0.0).

**Pre-registered prediction:**

- D3 within ±0.05: held.
- S SEPARATED_BELOW on both panels: held.
- A SEPARATED_BELOW on both panels: held.
- Ladder position at the random_valid rung: held.

**Reading.** The instrument separates a second realisable policy family from the trained adapter by the margin it was built to detect, on both the development panel and the held-out P2. Every A and S interval excludes 0 by at least 0.14, and every sign-flip p is ≤ 0.004 at 11–12 task clusters. It places an untrained but fully valid chooser at the uniform-choice rung. The adapter's advantage over random-valid is therefore specific to training. It is not produced by a model that emits valid choices and follows a goal-similarity instruction.

## Smoke check, evaluation, replay

- **Smoke** (`cfv6-smoke`, the #132 definition, descriptive): 42/42 calls accepted (rate 1.0 ≥ 0.5), 4/6 goals reached. `audit-smoke` replayed 6/6 and matches the stored summary.
- **Evaluation:** 46 episodes (24 on the #135 panel, 22 on P2). `finalize` replayed 24/24 and 22/22 independently, with **0 missing and 0 mismatches**. It re-applied the extractor to every stored model text. Every completion hook returned 0.

## Budget (`outputs/choice-frontier/v6/budget.json`, cap 30, own ledger)

| job | GPU | MASTER_PORT | status | GPU-h |
|---|---|---|---|---:|
| cfv6-smoke | 0 | 18840 | succeeded | 0.056 |
| cfv6-evaluate-v2-best_first_add_greedy | 0 | 18840 | succeeded | 0.664 |
| cfv6-evaluate-v2-best_first_add_w3 | 0 | 18840 | succeeded | 0.487 |
| cfv6-evaluate-p2-best_first_add_greedy | 0 | 18840 | succeeded | 0.571 |
| cfv6-evaluate-p2-best_first_add_w3 | 0 | 18840 | succeeded | 0.466 |
| **total** | | | | **2.245 / 30** |

- Launch mechanics:
  - All jobs went through `scripts/run_expanded_study.py launch` and ran sequentially on GPU 0.
  - Each job reused port 18840, since only one ran at a time.
  - The render backend was a dedicated `scripts/serve_issue70_planimation.py --port 18848` (hub process `cfv6-render`). It was stopped after finalize.
  - The last three jobs were launched by a sequential hub process (`cfv6-chain`). It waited for each job's `terminal.json`, then called the same launcher.
- Estimate: ≈ 3 GPU-h expected, ≤ 15.5 worst case. No relaunches.

## Evidence index (sha256, first 16)

```
36c4546fe6f218bf  budget.json
8b92ffa00a8321ff  smoke/smoke.json
f70b76430a512099  smoke/audit.json
213ed6c6e6e996db  evaluation/v2/bindings.json
65353510604f3b6c  evaluation/v2/evaluation.json
80fd0b7fb728a678  evaluation/v2/cells.json
430b0199bacfb269  evaluation/p2/bindings.json
e046f432205f03ab  evaluation/p2/evaluation.json
3d129108b3156c19  evaluation/p2/cells.json
23d6ef011fe15545  metrics/analysis.json
885fb6843386f433  metrics/zero-shot-episode-metrics.json
ff9df29025734775  smoke/episodes/** (6 files)
d51693f9ba98ac33  evaluation/v2/episodes/** (24 files)
8eb4c9a737657a18  evaluation/v2/views/** (1434 files)
db9ad10e64b431d3  evaluation/p2/episodes/** (22 files)
26b429fa98e27117  evaluation/p2/views/** (1514 files)
cfaa9eda59a6934e  jobs/** (44 files)
e45a4ec7bc166372  evidence-index.json (sha256 of all 3083 files)
c9361dfa08616adc  configs/experiments/choice-frontier-v6/protocol.json (tracked)
```

- The root is `outputs/choice-frontier/v6/`, untracked by repo convention.
- Each directory digest (`/**`) is the sha256 of the sorted `path sha256` lines in `evidence-index.json`.
- Tracked inputs:
  - `configs/experiments/choice-frontier-v6/{protocol,cfv6-*-job}.json`
  - `docs/experiments/choice-frontier/{issue-141-protocol.md,schedule-v6.json}`
  - `scripts/{run,analyze}_choice_frontier_v6_zero_shot.py`
  - `tests/planning_benchmark/test_choice_frontier_v6_zero_shot.py` (12 passed: extractor rules, arm-vs-adapter verdict order, exact sign-flip p-value against brute force)

## Judgement calls

1. **InternVL arm not run in any form** (cap, measured on CPU; see the protocol).
2. **Prompt change for the zero-shot arm.** The frozen system message never states the output format. The adapters learned it in training, and the #135 base answered bare `c0`. The arm therefore appends one pre-registered sentence (format plus goal-similarity instruction), and a deterministic extractor is part of the policy. The observation is otherwise byte-identical to the adapter's, and no privileged information is added.
3. **Smoke is non-gating** (pre-registered). It was never needed: the rate was 1.0.
4. **P2u was not evaluated** (optional in the ticket).

## Limitations

- **One untrained family, one prompt, one realisation.** Greedy decoding with content-seeded menus gives a single realisation per (task, algorithm). The prompt was not tuned, since tuning it on panel tasks would have been outcome selection. A better zero-shot prompt, a larger VLM or a chain-of-thought chooser could score higher. This result says nothing about them.
- **Not an independently trained policy.** This is the weaker of the ticket's two arms. It shows that the instrument separates trained from untrained realisable choosers. It does not show that the instrument ranks two differently trained policies against each other, which is what the InternVL arm would have tested.
- **The #135 panel is development-stage**, used throughout #136–#140. P2 (11 tasks) is the held-out panel. Its D3 verdict is INCONCLUSIVE by 0.001 above the equivalence margin.
- **Small clusters.** There are 11–12 tasks per panel. The exact sign-flip p-values for S and A are ≤ 0.004 per panel, so the separations do not rest on the bootstrap alone. The D3 equivalence reading does rest on the bootstrap (sign-flip p ≈ 0.9–1.0, as expected for a null-sized effect).
- **Same backbone as the adapter.** The zero-shot arm is the adapter's own base model without the LoRA. That isolates training as the cause, but it is not a different model family.
