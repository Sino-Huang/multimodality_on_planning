# Issue #120 closeout (Goal 14)

Goal 14 asked for the terminal synthesis of the expanded-nine-day-v1 program:
reconcile every declared branch's coverage, provenance and accounting, and
produce reproducible whole-instance analyses, tables/figures and a
claim-to-evidence inventory, with negative results, incomplete branches and the
v5/historical studies kept explicit. No additional GPU experiments were run;
the synthesis is CPU-only (`CUDA_VISIBLE_DEVICES=''`, zero model calls).

## Delivered

- `scripts/synthesize_expanded_study.py` regenerates the full synthesis in
  about six CPU seconds; `--check` byte-compares every published JSON, CSV,
  claim and the report against a fresh regeneration and exits nonzero on any
  drift or failed verification check.
- [synthesis-v1/](synthesis-v1/README.md) publishes the narrative report,
  `analysis.json`, `verification.json` (ten reconciliation checks, all PASS),
  `claims.json` (eleven claims with supported/negative/incomplete/boundary
  status), ten CSV tables and seven PNG+PDF figures.
- Requirement audit: [goal14-completion-audit.json](goal14-completion-audit.json).

## Branch reconciliation

| Branch | Tickets | Terminal state | Coverage | GPU-h / cap |
| --- | --- | --- | --- | --- |
| expanded_baseline | #116 #117 #118 | complete | 1,152/1,152 episodes, replay PASS | 6.5289 / 56 |
| dagger | #78-#84 | complete | 405/405 episodes, 81 paired rows | 10.9092 / 48 |
| successor_prediction | #85-#89 #99 | complete | 90/90 episodes, 0 substitutions | 10.8511 / 64 |
| curriculum_modality | #119 | complete | 243/243 model + 324/324 comparator | 11.7786 / 48 |
| transfer | #104-#107 | complete | 39/39 cells, 36 comparisons | 3.5993 / 24 |
| second_backbone | #101-#103 | VALID_STOP (L2) | probe + CPU qualification only | 3.9577 / 40 |
| generalization_robustness | #96 #98 | VALID_STOP (L4) | 93 eligible / 27 missing variants | 0.6273 / 32 |
| recovery_reserve | - | untouched | - | 0 / 24 |

The ledger was recomputed from all 116 attempts: 48.2521/336 GPU-h total, no
transfers, every attempt ended before the 2026-09-21T11:55:19Z GPU cutoff, and
failed/cutoff attempts retain their hours. Ledger sums match every branch's
published cumulative total (exact differences recorded in verification.json;
the transfer docs' 3.5993 rounds the ledger's 3.59932, and the second-backbone
admission conservatively double-counts its 0.63 GPU-h probe window). All five
docs-vs-runtime evidence pairs are sha256 byte-identical.

## Headline synthesized results

- **Matched modalities (expanded baseline):** the pretrained base never emits a
  valid first operation (0/288); process SFT succeeds 125/288, concentrated in
  the additive best-first family — SFT driving BFS or best-first-width fails
  0/24 in every modality, all 144 episodes terminating on
  `deterministic_invalid_operation` (verified from the episode reports). The
  oracle-assisted random-valid control reaches 240/288 and exact-reference
  288/288; these are bounds, not learned ability.
- **DAgger:** null result — 1/72 unseen successes, tied with exposure-matched
  continued SFT (1 win, 1 loss, 70 ties), far below random-valid (45/72).
- **Successor prediction:** untrained exact acceptance 119/1,536; trained arm
  exact on 65/109 predictions with 1/45 downstream success against 45/45 for
  the trusted arm; the full 24-task panel is missing by design (projected
  147.66 GPU-h, infeasible within the 64 GPU-h cap).
- **Curriculum by modality:** no ordering x modality interaction — all four
  paired bootstrap intervals include zero (10,000 resamples, seed 1729);
  random-valid/exact controls saturate at 27/27.
- **Generalization/robustness and second backbone:** terminal VALID_STOP at the
  frozen cost-admission gates (L4 and L2); no model outcomes exist and none
  were invented. One model-free robustness finding stands: P3 name-compression
  is information-lossy in text (24/24) and multimodal (18/24) but not visual
  (0/24). #96, #98, #102 and #103 remain open.
- **Transfer:** no statistically reliable zero-shot transfer in any of the 36
  benchmark/adapter comparisons (Holm-corrected; min adjusted p = 0.8156);
  leakage screening found only trivial numeric 8-gram overlap (7/564 items).

## Boundaries kept explicit

Single training seed 17 throughout; validity, predicted-state correctness,
search quality and compute are reported as distinct axes; random-valid is
oracle-assisted; unlabelled 128px images lose information; v5 and historical
#67 remain separate unpooled studies; tiny-panel intervals are descriptive.

## Accounting

This goal spent 0 GPU-hours, launched no model jobs and did not mutate the
ledger. Program total stands at 48.2521/336 GPU-h with the 24 GPU-h recovery
reserve untouched.
