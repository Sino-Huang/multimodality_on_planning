# Issue #123 closeout (second-backbone v2, L1 reduced scope)

#123 asked to train and evaluate the pinned second backbone
(`OpenGVLab/InternVL3_5-8B-HF` @ `741a7d03020411e666c6109218ab71e08151ef86`) on the
frozen reference-cost-reduced key-cell panel under protocol
`expanded-second-backbone-v2`: 12 lowest-reference-BFS-decision tasks of
`expanded-panel-v2-qualified` x 3 modalities x base/SFT = 72 model episodes,
comparators reused from the verified baseline evidence at zero new comparator
GPU cost, matched exposure (512 records, 16 optimizer updates, seed 17, fresh
adapter per modality), independent replay of every episode, verified
checkpoints, and a paired whole-problem comparison against the primary
backbone's matched L1 cells. All of it executed and passed. The branch is
closed as delivered; per the ticket's own supersedes-not clause, #102 and #103
remain OPEN.

## Delivered

- Protocol and admission: `configs/experiments/expanded-study/second-backbone-protocol-v2.json`,
  [second-backbone-v2-design.md](second-backbone-v2-design.md);
  `outputs/expanded-study/v1/second-backbone-v2/admission.json` — decision **L1**,
  outcome **PASS**, required incl. spent **48.1409** vs amended remainder **48.1523**
  (cap 52.11, headroom 0.0115 GPU-h).
- Training: `outputs/expanded-study/v1/second-backbone-v2/training/training-report.json`
  — three cells (text-state / visual-state / multimodal-state), each 512 records,
  16 optimizer updates, 504/504 adapter tensors changed, final-checkpoint-only;
  fresh seed-17 LoRA init identical across cells (`sha256:9530a9ed…`, 504 tensors).
  Jobs `sb-v2-train-0` (GPU 0, port 18800, 0.8316 GPU-h) + `sb-v2-train-1`
  (GPU 1, port 18801, 0.7418 GPU-h).
- Evaluation: `outputs/expanded-study/v1/second-backbone-v2/evaluation/evidence.json`
  — status **PASS**, 72/72 model episodes, complete coverage true, zero missing
  bindings. Jobs `sb-v2-evaluate-0` (0.2535 GPU-h) + `sb-v2-evaluate-1` (0.2460 GPU-h).
- Analysis: `outputs/expanded-study/v1/second-backbone-v2/evaluation/analysis.json`
  — outcome PASS, 12 paired units, bootstrap seed 1729, 10,000 resamples, 0.95.
- Published docs (all byte-identical copies, sha256-verified):
  [second-backbone-training.md](second-backbone-training.md),
  [second-backbone-evaluation.md](second-backbone-evaluation.md),
  [second-backbone-analysis.md](second-backbone-analysis.md), plus admission,
  probe and qualification JSONs (probe/qualification are the reused v1 artifacts).
- Launch provenance: scheduler chain job `v2-compute-chain` (launched
  2026-09-19T12:58Z, head `5ebea39`), complete marker
  `outputs/expanded-study/v1/v2-chain/complete.json`; every stage ran a CPU audit
  completion hook; all 9 `sb-v2` attempts ended before the
  2026-09-21T11:55:19Z cutoff.

## Acceptance criteria → evidence

| #123 criterion | Evidence |
| --- | --- |
| Pinned backbone trained on frozen L1 panel (72 model episodes) | training-report PASS (3 cells from the pinned base); admission `authorized_scope` = the 12 frozen key-cell tasks; evidence 72/72 |
| Comparators reused, zero new comparator GPU cost | 72 unique baseline comparator episodes (random_valid, exact_reference) sha256-pinned and replayed, never regenerated (144 verification records, `expected_comparator_episodes` 72); comparator model_calls 0 |
| Matched exposure: 512 records, 16 updates, seed 17, fresh adapter per modality | per-cell 512 records / 16 updates, sequential membership order, one epoch, batch 32; fresh init `sha256:9530a9ed…` identical across cells; 504/504 tensors changed per cell |
| Independent replay of every episode | evidence assembled from replay of all 72 retained episode files; `sb-v2-evaluate-final` audit-final re-derived evidence and analysis byte-identically |
| Verified checkpoints | per-worker checkpoint audits + `audit-training-final` independent re-verification of all three cells (fingerprints in training-report) |
| Paired whole-problem comparison vs primary backbone L1 cells | cross-backbone contrasts in analysis.json — see boundary note below |
| Budget: documented 12.11 GPU-h transfer, cap 52.11, total 336 and cutoff unchanged, failures retain hours | `budget.json` transfers[0]; allocations sum 336; cutoff untouched; failed attempts retain their entries (see fixes below) |
| Execution rules (shared scheduler, distinct ports, hooks, no outcome-selected reruns, single seed, cutoff) | chain job with per-stage hooks, MASTER_PORTs 18800/18801, scope frozen pre-outcomes, seed 17 everywhere, all attempts pre-cutoff |

## Headline results

- **Neither arm ever reaches a goal.** pretrained_base 0/36 — every episode emits
  one invalid operation and stops at 1 decision. process_sft 0/36 — episodes run
  1–4 decisions (26x1, 2x2, 3x3, 5x4; 59 total) with invalid-operation rates
  0.52 (text) / 0.67 (visual) / 0.67 (multimodal): a decision-depth difference
  without a success difference.
- process_sft − pretrained_base = **+0.000 [0.000, 0.000]** in all three modalities.
- process_sft − random_valid = **−0.750 [−1.000, −0.500]** in all three modalities
  (random_valid, oracle-assisted, succeeds 54/72 = 18/24 per modality;
  exact_reference 72/72).
- Cross-backbone InternVL-SFT − Qwen3-VL-SFT = **+0.000 [0.000, 0.000]** on the 12
  L1 tasks (Qwen pinned process-SFT BFS success rate 0.0).
- 95 model calls total (36 base + 59 SFT) against a priced decision-call allowance
  of 640 per modality-condition cell.

## Production failures fixed en route (all retained in the ledger)

- `5440116` — finalize-training derived its job-id prefix from the protocol
  identity; `sb-v2-train-final` attempt 1 failed before any training artifact was
  written, attempt 2 passed audited.
- `87d07c8` — build_evidence joined episode policy identity by a composite
  `modality__arm` key; `sb-v2-evaluate-final` attempt 1 failed after replaying all
  72 episodes (files retained), attempt 2 reran.
- `fd04151` — reused baseline comparators are replayed under their producing
  (Qwen) processor, not the InternVL one; attempt 2 failed in comparator
  verification, attempt 3 passed with evidence PASS and complete coverage.
- All three failed attempts are CPU finalization steps with 0.0 GPU-h, retained
  per the failures-retain-hours rule.

## Boundaries kept explicit

- **Reduced scope:** the executed panel is 12/24 tasks selected by lowest
  reference BFS decision count only, frozen before any model outcome; it is not
  the v1 full panel and not outcome-selected. The tight null intervals are
  descriptive on these 12 tasks.
- **Cross-backbone contrast is descriptive, not paired:** the pinned baseline
  evidence holds aggregate cells, not per-task L1 outcomes, so the analysis
  conditions on the Qwen pinned full-panel process-SFT BFS rate (0.0); the
  interval reflects InternVL task-level variation around it. A strictly paired
  per-task cross-backbone interval was not computable from pinned evidence and
  was not invented.
- Single training seed 17; no seed-variance claim. random_valid is
  oracle-assisted. Architecture-difference limitation: InternVL3.5-8B shares the
  Qwen3-8B LLM family; the replication contrast is the vision tower, connector,
  image tokenization and multimodal recipe.
- The conservative admission bound priced evaluation at 32.64 GPU-h (2 x
  reference decisions x p95 per episode); realized evaluation cost 0.4995 GPU-h
  because episodes terminate after 1–4 calls. The bound was not relaxed
  retroactively.

## Accounting

Branch `second_backbone` totals **6.0305 / 52.11 GPU-h**: v1-retained 3.9577
(CPU qualification 0 + probe/debug attempts) + v2 training 1.5734 (0.8316 +
0.7418) + v2 evaluation 0.4995 (0.2535 + 0.2460) + failed CPU finalize attempts
0.0. The v2 run consumed 2.0729 GPU-h of the 44.18 required-including-spent
frozen authorization. Program-wide the ledger stands at 53.5166 / 336 GPU-h as
of this closeout (other branches, including concurrent #124 work, included).
The recovery reserve transfer of 12.11 GPU-h was prospective, documented before
execution, and preserved both the 336 total and the absolute cutoff.

## Disposition

#123 closes on this evidence: the reduced-scope second-backbone replication was
executed exactly as frozen, fully verified, and published. #102 and #103 remain
OPEN — the v1 full-panel scope (144 episodes) was certified infeasible at the
frozen cost-admission gate (terminal VALID_STOP, decision L2) and was never
executed; v2 is a documented reduced-scope branch and does not satisfy them.
