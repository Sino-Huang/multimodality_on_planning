# Issue #126 closeout — modality corruption/removal stress tests on frozen checkpoints

Ask: evaluate frozen, already-verified checkpoints (no retraining) on a prospectively
frozen suite of modality-degradation variants of existing evaluation tasks;
inference-only through the existing replay machinery; controls under the frozen
rollout rules; paired whole-problem analysis with tiny-strata limits; complete
coverage or explicit missingness.

## Delivered

- **Frozen design gate**: `configs/experiments/expanded-study/modality-stress-protocol.json`
  + `docs/experiments/expanded-study/modality-stress-design.md`, frozen before any
  corrupted-observation model outcome (commit `78b51e0`). Admission
  `outputs/expanded-study/v1/modality-stress/admission.json` recomputed by
  `scripts/qualify_expanded_modality_stress.py` from existing evidence only:
  **PASS, k = 9 source tasks**, membership sha256
  `20ea888d5199d53bbbe2e7cfa14aeee11e3c4cd7cff956103147ed1a7328e854` (verified by
  every audit hook).
- **Budget**: frozen estimand required 26.250960870224514 GPU-h vs branch
  remainder 28.181063522166674 (no transfer; program cap 336 and the
  2026-09-21T11:55:19Z scheduler cutoff unchanged). **Actual GPU spend 2.2215
  GPU-h** (ms-v1-models-0 2.0071 + ms-v1-models-1 0.2144; CPU jobs 0) — branch
  generalization_robustness now 6.0404 / 32 GPU-h. All five jobs terminal
  `succeeded` with per-stage audit hooks PASS (`ms-v1-chain` completed
  2026-09-20T13:29:33Z, inside the cutoff).
- **Complete coverage, zero missingness**: 360/360 new bindings recorded and
  independently replayed (288 GPU model episodes: 144 learned_adapter capped at
  2× reference decisions, 144 pretrained_base hard-capped at 1 call; 72 CPU
  random_valid on the new frozen seeds 1013/2027/3041/4001) plus 144/144 reused
  replay-verified baseline comparators (clean process_sft/pretrained_base per
  (task, arm, algorithm), seed-17 random_valid and exact_reference per (task,
  algorithm)). Control arm-invariance re-verified on 96/96 baseline triples at
  admission. Published artifacts: `outputs/expanded-study/v1/modality-stress/evaluation.json`
  (PASS) and `analysis.json` (144 paired cells).
- **Machinery**: `examples/planning_benchmark_slice/expanded_modality_stress.py`
  (four deterministic corruption families applied at `observe()` time —
  visual-blank uniform-gray images, visual-degraded 16×16 mosaic,
  text-shuffled seeded token permutation (master seed 42613), text-masked
  alphanumeric→▮ — with token recount, 32K re-gate and replay-exact
  determinism), `scripts/run_expanded_modality_stress.py` (validate /
  evaluate-inputs / worker / finalize / audit stages), scheduler jobs
  `modality-stress-*-job.json`, audited chain `ms-v1-chain`. Corruption
  verifiably reached the model: text-masked first-call 1803 vs clean 1834
  tokens, text-shuffled 1834 (permutation), visual-blank 3655 = clean visual
  (corrupted pixels, preserved geometry).

## Results (paired, whole-problem; strata < 8 descriptive-only per the frozen rule)

Clean learned success on the 9 admitted tasks: 0.917 (text-state 0.944,
visual-state 0.889, multimodal-state 0.889; n = 9 tasks × 2 algorithms per cell).

| Corruption | Arm | Corrupted | Clean | Δ | 95% interval | Material |
| --- | --- | ---: | ---: | ---: | --- | --- |
| text-masked | text-state | 0.000 | 0.944 | −0.944 | [−1.000, −0.833] | yes |
| text-masked | multimodal-state | 0.000 | 0.889 | −0.889 | [−1.000, −0.722] | yes |
| text-shuffled | text-state | 0.000 | 0.944 | −0.944 | [−1.000, −0.833] | yes |
| text-shuffled | multimodal-state | 0.167 | 0.889 | −0.722 | [−0.889, −0.500] | yes |
| visual-blank | visual-state | 0.833 | 0.889 | −0.056 | [−0.167, +0.000] | no |
| visual-blank | multimodal-state | 0.778 | 0.889 | −0.111 | [−0.278, +0.000] | no |
| visual-degraded | visual-state | 0.833 | 0.889 | −0.056 | [−0.167, +0.000] | no |
| visual-degraded | multimodal-state | 0.778 | 0.889 | −0.111 | [−0.278, +0.000] | no |

**Multimodal channel isolation** (paired by task × algorithm, n = 18):
text-channel corruption −0.806 vs visual-channel corruption −0.111;
text − visual = **−0.694, 95% [−0.889, −0.472], material**. The learned
Search-Process-Policy depends on the language observation channel; corrupting
it is catastrophic (0–17% residual success — clean images rescue only part of
the multimodal arm), while removing or degrading the visual channel barely
moves success (≤11 points, intervals include zero) even on the visual-state
arm, whose only rendered-semantics channel was corrupted — the shared textual
search-memory/candidate serialization carries the decision-relevant state.

Controls: corrupted pretrained_base 0/144 (all first-decision invalid, same as
clean — floor, no measurable degradation); random_valid 72/72 new-seed
successes and reused seed-17 successes put the oracle-assisted control at
ceiling on these tasks, so per the frozen #54 saturation rule **no
structural-advantage claim is made**; exact_reference remains the oracle upper
bound (18/18). Domain (n ≤ 2) and stratum-origin (7 compact / 2 expanded)
strata are descriptive-only under the frozen tiny-strata rule; degradation is
uniform in sign across all 8 admitted domains (−0.375 … −0.688).

## Scope discipline

Does not close or modify #96/#98 (v1 scopes stay open under their own wording)
or any other ticket. No retraining, no outcome-selected variants, no favourable
replacements; membership, estimand and corruption definitions were frozen
before any corrupted-observation model outcome existed. GPU launches ran only
after the frozen design was presented and explicitly authorized.
