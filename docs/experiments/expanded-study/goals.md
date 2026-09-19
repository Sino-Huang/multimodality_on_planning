# Copyable goals for the nine-day program

Preparation documents and ticket reactivation are already done. Start with Goal 1; do not repeat planning or restart the absolute clock. Every goal inherits the execution rules and allocations in [plan.md](plan.md) and [schedule.json](schedule.json). A goal invocation authorizes that branch, not all independent branches at once.

## 1. Shared execution readiness — #116

```text
/goal Complete #116 in Sino-Huang/multimodality_on_planning. Read AGENTS.md and docs/experiments/expanded-study/plan.md, schedule.json and linked comments. Implement and test shared GPU-hour accounting, absolute cutoffs, duplicate-launch refusal, port allocation, safe resume, background logs and completion hooks. Revalidate the twelve v5 checkpoints and available hardware without retraining. The documents already define the nine-day budget; do not restart its clock. Produce the tested readiness/scheduler commands, branch integration contracts and readiness evidence; do not claim unimplemented branches runnable. Commit/push and close only fulfilled #116 requirements. Do not launch every branch from this readiness goal.
```

## 2. Prepare the broader panel — #117

```text
/goal Complete #117 in Sino-Huang/multimodality_on_planning under docs/experiments/expanded-study/plan.md and schedule.json; read AGENTS.md and comments first. Prepare and qualify the proposed 24-problem, 12-domain unseen panel with whole-instance separation, frozen structural/reference selection rules, source goals, 128px unlabelled views, common Search Memory and complete input bounds. Reuse old assets without corpus regeneration. Run actual bounded hardware qualification automatically. Freeze the measured feasible panel before new model outcomes; report infeasible strata without silently dropping them. Verify all bindings, commit/push and close only on qualified coverage.
```

## 3. Execute expanded matched baseline — #118

```text
/goal Complete #118 in Sino-Huang/multimodality_on_planning under docs/experiments/expanded-study/plan.md and schedule.json; read AGENTS.md and comments. Consume the qualified #117 panel and reuse the twelve verified v5 adapters without retraining. Automatically run the declared four-algorithm, three-modality base/SFT/random/exact matrix through the shared background scheduler and completion hooks. Preserve fixed inputs, raw failures and cumulative costs. Independently replay every episode; distinguish oracle-assisted random validity from learned operation generation. Publish complete coverage or explicit missingness, commit/push and close only fulfilled evaluation requirements.
```

## 4. DAgger interface and protocol — #78–#79

```text
/goal Complete revised #78 and #79 in Sino-Huang/multimodality_on_planning under docs/experiments/expanded-study/plan.md and schedule.json; read AGENTS.md and comments. Implement last-valid-training-state expert correction, raw-output provenance, split isolation and replay. Freeze BFS across three modalities, two bounded iterations, correction/collection quotas, aggregation and 512-record/16-update schedules. Declare treatment of unused quotas before collection. Include continued-SFT controls matched for additional updates. Per-modality on-policy trajectories need not be identical; state the estimand accurately. Test and qualify runnable commands within the branch allocation, commit/push and close satisfied protocol tickets.
```

## 5. Collect and verify DAgger data — #80–#83

```text
/goal Complete the collectors and first-iteration collection/replay stage of #80, #81, #82 and #83 in Sino-Huang/multimodality_on_planning under docs/experiments/expanded-study/plan.md and the frozen #79 config; read AGENTS.md and comments. Implement the reusable collectors and automatically collect iteration-one correction sets for all three modalities using training tasks only, preserving invalid attempts, expert queries and accepted-state links. Use the shared scheduler and completion hooks. Do not fill shortfalls with invented or duplicated corrections or expand quotas after outcomes. Independently replay every correction and verify aggregation, membership, splits and budgets. Publish iteration-one datasets and coverage, commit/push, and keep any two-iteration coverage requirements open for Goal 6.
```

## 6. Run the DAgger comparison — #84

```text
/goal Complete #84 in Sino-Huang/multimodality_on_planning under docs/experiments/expanded-study/plan.md and schedule.json; read AGENTS.md, comments and verified #83 evidence. Automatically train iteration one from its verified corrections, then collect iteration two using those updated policies, independently verify the new corrections through #83, and train iteration two. Run exposure-matched continued-SFT updates in the same declared schedule. Preserve checkpoints and cumulative accounting; do not collect both iterations with the original policy. Compare original SFT, continued SFT and DAgger on the same declared development and unseen panel contracts. Never collect corrections from final tasks or iterate until positive. Verify final checkpoints and independently replay evaluation. Separate validity, search quality, expert-query cost and training compute. Commit/push complete evidence and close #80–#84 only after all required iteration coverage is verified.
```

## 7. Successor prediction interface — #85–#86

```text
/goal Complete #85 and #86 in Sino-Huang/multimodality_on_planning under docs/experiments/expanded-study/plan.md and schedule.json; read AGENTS.md and comments. Define complete predicted dynamic-state/fluents targets, immutable static-context checks, and trusted applicability/effect/identity verification for the declared BFS modality cells. Preserve raw predictions and never replace an incorrect predicted state with the trusted one. Freeze collection, training, output allowance, controls and budgets before outcomes; measure target lengths rather than truncating full states to the old operation limit. Test malformed states and replay, qualify exact commands, commit/push and close fulfilled protocol tickets.
```

## 8. Collect and verify successor data — #87–#88

```text
/goal Complete #87 and #88 in Sino-Huang/multimodality_on_planning under docs/experiments/expanded-study/plan.md and the frozen #86 config; read AGENTS.md and comments. Automatically collect training-only successor interactions with raw predictions, trusted targets, verification errors and trajectory links. Keep predictions distinct from corrected training labels. Preserve whole-instance splits and declared observations. Independently replay and verify full-state records, membership and provenance; publish the versioned dataset required by #88 without overwriting old releases. Use background logs/hooks for long work, commit/push and close only verified deliverables.
```

## 9. Train and evaluate successor prediction — #89/#99

```text
/goal Complete #89 then #99 in Sino-Huang/multimodality_on_planning under docs/experiments/expanded-study/plan.md and schedule.json; read AGENTS.md and comments. Consume verified #88 data, automatically train the frozen three-modality BFS cells, verify checkpoints and run the declared final comparison against trusted-successor controls on the qualified unseen panel. Never silently repair predicted states, tune on final outcomes or change the output contract mid-run. Preserve all operational, state-prediction and downstream search failures. Independently replay results, account for actual compute, commit/push and close only fulfilled tickets.
```

## 10. Curriculum by modality — #119

```text
/goal Complete #119 in Sino-Huang/multimodality_on_planning under docs/experiments/expanded-study/plan.md and schedule.json; read AGENTS.md and comments. Run the qualified nine-cell staged/shuffled/mixed-order by text/visual/multimodal experiment for additive greedy best-first. Match the same 512 unique records, targets, seed 17, one epoch and 16 updates, with trainer reshuffling disabled. Train fresh from the same base, automatically execute fixed evaluation and independently verify exposure and replay. Analyze the declared whole-problem interaction and control saturation. Keep historical #67 separate; do not infer an interaction by pooling old studies. Commit/push and close verified requirements.
```

## 11. Generalization and robustness — #96/#98

```text
/goal Complete #96 and #98 in Sino-Huang/multimodality_on_planning under docs/experiments/expanded-study/plan.md and schedule.json; read AGENTS.md and comments. Freeze and qualify the proposed structural-shift and name/render perturbation suites before observing their model outcomes. Verify semantic mappings, distinguishing information loss from semantics-preserving perturbations. Automatically evaluate fixed declared checkpoints and controls within the shared allocation, without test-driven retraining or favourable replacement tasks. Independently replay all episodes and report paired whole-instance validity, success, search/compute costs and missingness. Commit/push and close only fulfilled tickets.
```

## 12. Second-backbone replication — #101–#103

```text
/goal Complete #101, #102 and #103 in Sino-Huang/multimodality_on_planning under docs/experiments/expanded-study/plan.md and schedule.json; read AGENTS.md and comments. Select and pin one additional backbone by official capability/license documentation and measured capacity, not final-test performance. Qualify exact inputs and the declared three-modality BFS matrix. Automatically integrate, train matched-exposure adapters and evaluate fixed final checkpoints against the same panel and controls. Verify all checkpoints and replay. Report architecture-specific differences, negative results and the single-training-seed limitation; do not claim seed replication. Commit/push and close only complete deliverables.
```

## 13. FOLIO, HumanEval and GSM8K transfer — #104–#107

```text
/goal Complete #104 then #105/#106/#107 in Sino-Huang/multimodality_on_planning under docs/experiments/expanded-study/plan.md and schedule.json; read AGENTS.md and comments. Freeze official benchmark versions, held-out subsets, metrics, prompts, decoding and the declared base/three BFS-adapter comparisons before transfer outputs. Verify benchmark protocols and prevent test leakage. Automatically run zero-shot transfer within the shared scheduler/allocation; sandbox generated HumanEval code with resource limits and no unnecessary network access. Do not choose adapters or reruns by transfer-test success. Verify predictions/scores, report subsets, costs and failures accurately, commit/push and close fulfilled tickets.
```

## 14. Synthesize all expanded results — #120

```text
/goal Complete #120 in Sino-Huang/multimodality_on_planning under docs/experiments/expanded-study/plan.md; read AGENTS.md and linked terminal artifacts. Verify every declared branch’s actual coverage, provenance and accounting. Produce reproducible whole-instance analyses, tables/figures and a claim-to-evidence inventory for matched modalities, DAgger, successor prediction, curriculum, robustness/generalization, replication and transfer. Preserve negative results and incomplete branches; separate v5 and historical results. Distinguish operation validity, predicted-state correctness, search quality and compute. Run CPU commands automatically with no additional GPU experiments. Commit/push and close only verified synthesis requirements.
```

## 15. Write and compile the manuscript — #121

```text
/goal Complete #121 in Sino-Huang/multimodality_on_planning under docs/experiments/expanded-study/plan.md, using verified #120 evidence. Read AGENTS.md and comments. Resolve the intended ICLR cycle/track from project records or request that essential detail; verify official requirements and primary-source literature citations. Write and compile the manuscript and appendix, inspect figures/references, check anonymity and reconcile every numerical claim with evidence. State representative-cell, information-loss, control-assistance and seed limitations. Do not invent authorship or submission declarations. Run compilation/checks automatically, list indispensable author tasks, commit/push and close reviewable draft requirements. Do not submit to OpenReview.
```

## 16. Verify release and handoff — #122

```text
/goal Complete #122 in Sino-Huang/multimodality_on_planning under docs/experiments/expanded-study/plan.md after verified synthesis and manuscript. Read AGENTS.md and comments. Prepare a separate versioned artifact release with configurations, required adapters, traces, replay dependencies, analyses and declared reproduction limits. Automatically verify restored replay and manuscript-number consistency without retraining. Preserve historical #108/deadline-study-v1. This goal authorizes publication of the verified successor release when compatible with the intended cycle’s anonymity rules; resolve essential author decisions explicitly. Produce the final completion ledger and submission checklist, commit/push and close fulfilled requirements. Do not submit to OpenReview.
```
