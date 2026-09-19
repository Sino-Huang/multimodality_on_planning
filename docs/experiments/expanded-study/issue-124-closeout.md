# Issue #124 closeout (generalization-robustness v2)

#124 asked for the reduced-scope execution of the frozen Goal-11
generalization/robustness suite under the new versioned protocol
`expanded-generalization-robustness-v2`: the learned additive-best-first cells
plus frozen controls on a deterministically selected, cost-admitted subset of the
93-eligible/27-missing variant suite, membership and runtime estimand frozen before
recomputation, qualification freeze preserved exactly, every episode
independently replayed, and lossy P3 name-compression reported separately. The
branch has now fully executed: 1,200/1,200 episodes, evaluation outcome PASS,
membership sha256 `008deaf35b710a941aa31d447d456b7d681c581760c28df4130c72a21adb2d60`
verified. GPU cutoff 2026-09-21T11:55:19Z respected.

## Delivered

- Protocol and admission:
  `configs/experiments/expanded-study/generalization-robustness-protocol-v2.json`,
  `outputs/expanded-study/v1/generalization-robustness/admission-v2.json`
  (schema `expanded_generalization_admission_v2`, decision PASS, k=5 uniform,
  25 variants, required 29.4945 GPU-h vs 31.3727 remainder), recompute script
  `scripts/qualify_expanded_generalization_v2.py`, design doc
  [generalization-robustness-v2-design.md](generalization-robustness-v2-design.md).
- Evaluation code: `examples/planning_benchmark_slice/expanded_generalization_eval.py`
  (bindings from the frozen admission, `V2VisualSession` base-arm one-call cap,
  resumable episodes); runner stages `evaluate-inputs`, `evaluate-worker`,
  `evaluate-finalize` and scheduler completion hooks `audit-evaluate-worker`,
  `audit-evaluate-final` in `scripts/run_expanded_generalization.py`.
- Job configs: `configs/experiments/expanded-study/generalization-v2-{controls-0,
  controls-1,models-0,models-1,evaluate-final}-job.json`, sequenced by the
  operational chain script `outputs/expanded-study/v1/v2-chain/v2_chain.py`
  (untracked orchestrator artifact).
- Evidence: `evaluation-bindings.json` (1,200 bindings),
  `episodes/` (1,200 gzipped `expanded_baseline_episode_v1` reports + `views/`),
  `evaluation.json` (schema `expanded_generalization_evaluation_v1`, outcome PASS,
  episodes_replayed 1,200/1,200, missing []), all under
  `outputs/expanded-study/v1/generalization-robustness/`.
- Tests: `tests/planning_benchmark/test_expanded_generalization_eval.py` (12
  CPU-only tests: binding coverage, control-episode schema, base-arm cap,
  both audit hooks).

## Execution summary

| Job | Attempts | GPU-h | Episodes | Hook |
| --- | --- | ---: | ---: | --- |
| gr-v2-controls-0 (CPU) | 1 succeeded | 0.0 | 450 random_valid | PASS |
| gr-v2-controls-1 (CPU) | 1 succeeded | 0.0 | 150 exact_reference + 300 random_valid | PASS |
| gr-v2-models-0 (GPU 0, port 18800) | 1 failed + 1 succeeded | 0.0206 + 3.0030 | 150 learned_adapter | failed attempt hook correctly exited 1; attempt 2 PASS |
| gr-v2-models-1 (GPU 1, port 18801) | 1 succeeded | 0.1681 | 150 pretrained_base | PASS |
| gr-v2-evaluate-final (CPU) | 1 succeeded | 0.0 | replay 1,200/1,200 | PASS |

Every hook ran CPU-only with `CUDA_VISIBLE_DEVICES=""`, 300 s timeout; all
succeeded attempts verified by their audit hooks (worker provenance, completed
count vs frozen partition, episode-file existence; final provenance, replay
completeness, missingness gate).

**Production failure fixed en route.** `gr-v2-models-0` attempt 1 crashed before
its first episode (74 s, 0.0206 GPU-h retained): `evaluate-worker` called
`Path(...).relative_to(root)` on adapter paths already stored in the frozen
root-relative form (`outputs/matched_modalities/v3/...`), so every learned binding
raised before generation. CPU smoke tests never reached this GPU-only path. Fixed
by recording the checkpoint string verbatim (`8faa498`); the failed attempt,
its traceback and its hook failure (`did not terminate cleanly`) are retained in
`outputs/expanded-study/v1/jobs/gr-v2-models-0/1/`. No episodes were produced or
rerun-selected by it; attempt 2 executed the identical frozen bindings.

## Coverage

25 admitted variants (uniform k=5 per family: scale-up, shifted-init,
object-renaming, render-restyle, name-compression) x 48 episodes each = 1,200
logical bindings. Per variant: 6 learned cells (`best_first_add_greedy` +
`best_first_add_w3` x text/visual/multimodal-state, 6 of the 12 frozen adapters)
+ 6 base cells (hard-capped at 1 model call, per the estimand) = 12 GPU episodes;
controls on CPU: `random_valid` x 5 frozen seeds (17/1013/2027/3041/4001) +
`exact_reference` per cell = 36. The 93/27 qualification freeze is preserved
exactly (suite sha256 `a20c30cc…42`, qualification sha256 `cb5badf…8f`); no
variants replaced, none added; derived-task scores never selected scope.

## Headline results (from evaluation.json and the 1,200 episode reports)

Invariant-valid success (goal reached, zero invalid operations), per family:

| family | learned_adapter | pretrained_base | random_valid | exact_reference |
| --- | ---: | ---: | ---: | ---: |
| object-renaming (P1) | 29/30 | 0/30 | 150/150 | 30/30 |
| name-compression (P3) | 27/30 | 0/30 | 150/150 | 30/30 |
| render-restyle (P2) | 27/30 | 0/30 | 150/150 | 30/30 |
| scale-up (V1) | 26/30 | 0/30 | 150/150 | 30/30 |
| shifted-init (V2) | 19/30 | 0/30 | 150/150 | 30/30 |
| **total** | **128/150** | **0/150** | **750/750** | **150/150** |

Per modality (learned): text-state 44/50, multimodal-state 43/50, visual-state
41/50. Per algorithm (learned): `best_first_add_greedy` 67/75 (8 invalid ops),
`best_first_add_w3` 61/75 (14 invalid ops).

- **Learned vs base.** The pretrained base emits an invalid first operation on
  every derived task (0/150, 150 decisions total — exactly one call per episode,
  confirming the estimand's 1-call pricing empirically). The learned adapters
  succeed on 128/150 (85.3%) of identical episodes; the learned>base contrast is
  supported on every family, strongest on the semantics-preserving perturbations
  (P1 29/30) and weakest on shifted-init (19/30).
- **Failure loci.** All 22 learned failures are single-invalid-operation
  terminations: 11 in shifted-init (fresh-seeded walks, e.g.
  ferry-shifted-init-940011 and gripper-shifted-init-940014 in every modality),
  4 in scale-up (depot-scale-up-930005 fails late at 42-43 decisions), 3 each in
  name-compression and render-restyle. No decision-budget or expansion-budget
  exhaustions occurred; episodes terminate far below the priced 2x-reference cap.
- **Controls saturate.** random_valid (oracle-assisted) reaches 750/750 and
  exact_reference 150/150; per the issue-#54 saturation rule no
  structural-advantage claim against controls is made — controls are bounds,
  not learned ability.
- **P3 lossy stratum, reported separately.** Of the 5 admitted name-compression
  variants, all 5 are text-lossy, 3 are multimodal-lossy (ferry, storage,
  towers_of_hanoi) and none visual-lossy, matching the family-wide measured
  classification (24/24 text, 18/24 multimodal, 0/24 visual). Learned success on
  the admitted P3 subset: text 9/10, visual 8/10, multimodal 10/10 (27/30);
  these cells are reported here and in `by_family`, never pooled with
  semantics-preserving variants.

## Accounting

Admission required 29.4945 GPU-h (matrix 23.5457 x 1.25 + 0.0624 overhead).
Actual branch spend: **3.8189/32 GPU-h** = probe 0.6273 + controls 0.0 +
models-0 failed attempt 0.0206 + models-0 attempt 2 (learned, 2,251 model calls)
3.0030 + models-1 (base, 150 calls) 0.1681 + finalize 0.0. The evaluation ran
~9x under the frozen estimate because episodes terminate early: actual learned
calls were 2,251 vs 5,010 priced (45%) — 128 episodes reached the goal well
below the 2x-reference cap and 22 died on their first or an early invalid
operation — and the base arm's realized cost equalled its pricing exactly
(150 calls). No recovery-reserve transfer was needed or
executed (reserve untouched at 11.89); the program total stands at
**53.5166/336 GPU-h** recomputed from the ledger, all attempts ended before the
cutoff, and failed attempts retain their hours.

## Boundaries kept explicit

- Reduced scope by construction: k=5 cheapest-prefix-per-family of the 93
  eligible variants (5/6 scale-up, 5/15 shifted-init, 5/24 per perturbation
  family), admitted by the frozen cost equation. The full 93-variant L0 matrix of
  #96/#98 remains unexecuted and infeasible within this branch.
- 6 of the 12 frozen adapters evaluated: `bfs` and `best_first_width` were
  priced out by the frozen admission (highest reference costs, slowest probe
  combos); their exclusion was a frozen cost-only decision, not an outcome-based
  one.
- Single evaluation seed 17 for learned/base/exact arms, greedy decoding; the
  five frozen random-valid seeds; no training-seed-variance claims.
- Family strata contain 5 problems each (<8): family-level rates above are
  descriptive-only under the tiny-subgroup rule; no interval claims are made.
  Domain- and stratum-origin-level paired aggregates were not published in
  `evaluation.json` (family/modality/condition only); per-variant episode
  identities remain joined to the frozen qualification for any later paired
  reanalysis.
- random_valid is oracle-assisted; unlabelled 128px views lose information;
  lossy P3 cells are never pooled with semantics-preserving variants.

## Status

#124 closes on this evidence. #96 and #98 remain OPEN: the v1 full-suite scope
(120 variants, 4 algorithms) was certified infeasible (terminal VALID_STOP,
decision L4, retained) and was never executed; v2 is a documented reduced-scope
branch under a new versioned protocol and does not satisfy their current wording.
