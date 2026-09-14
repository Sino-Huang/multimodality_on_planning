# Expanded nine-day research program

Prepared on 14 September 2026 following the user's approval of nine days with
the same two A100s. This document prepares work; it does not launch experiments
or claim their completion. [schedule.json](schedule.json) contains the numeric
allocation and absolute cutoffs. [goals.md](goals.md) contains runnable agent goals.

## Time and resources

| Milestone | UTC | Australia/Melbourne |
| --- | --- | --- |
| Program start | 14 September 2026 11:55:19 | 14 September 21:55:19 |
| GPU experiment cutoff | 21 September 2026 11:55:19 | 21 September 21:55:19 |
| Submission-package handoff | 23 September 2026 11:55:19 | 23 September 21:55:19 |

These are internal project deadlines, not verified ICLR deadlines. The intended
ICLR cycle/track must be resolved before submission formatting. Starting a later
goal does not restart this nine-day window. Final 48 hours are reserved for CPU
analysis, writing, verification and release; begin that work earlier as possible.

| Branch | Aggregate GPU-hour ceiling | Tickets |
| --- | ---: | --- |
| Readiness, new panel and expanded baseline | 56 | #116 -> #117 -> #118 |
| DAgger | 48 | #78 -> #79 -> #80/#81/#82 -> #83 -> #84 |
| Model-generated successors | 64 | #85 -> #86 -> #87 -> #88 -> #89 -> #99 |
| Curriculum by modality | 48 | #119; historical #67 is separate |
| Structural generalization and robustness | 32 | #96, #98 |
| Second-backbone replication | 40 | #101 -> #102 -> #103 |
| Transfer | 24 | #104 -> #105/#106/#107 |
| Recovery reserve | 24 | prospectively assigned, never hidden |
| Total | **336** | seven days x two GPUs, a ceiling not a runtime promise |

Account for the sum of this program's allocated model-worker durations across
GPUs: two occupied GPUs for one hour consume two GPU-hours. Include loads, saves,
qualification, diagnostics, failures and retries. Record CPU time, wall time,
available VRAM and worker duration separately; worker duration is not utilization.
Unrelated workloads remain running, so measured capacity may be below the ceiling.

Implement the new shared ledger at `outputs/expanded-study/v1/budget.json` under
#116. Do not edit/reset v5 or historical ledgers. Track concurrent allocations
centrally and enforce branch caps, the total cap and the absolute cutoff.
Document prospective transfers before launching work; retain their reasons and
spent amounts. Transfers cannot extend the total or calendar cutoff, hide missing
coverage, or silently remove a research program. Report concrete infeasibility
and measured alternatives if the declared workload cannot fit.

## Proposed matrices to qualify before activation

These are concrete feasibility targets, not claims of qualified capacity. Freeze
each final matrix, dataset membership, selection rules and measured estimate in
an ordinary branch config before collecting its new final outcomes. Design is
informed by known v5 results; it is not retrospectively preregistered. A failed
qualification is missing work, not permission to select easier successful cases.

| Branch | Proposed experiment |
| --- | --- |
| Core panel | 24 new problems: two per each of the 12 supported source domains, with domain-relative structural strata fixed before selection. Freeze generator profiles, seed ranges and reference-cost criteria in #117. |
| Baseline | Four algorithms x three modalities x 24 problems x base/SFT/random/exact = 1,152 logical bindings, including 576 model episodes. Reuse all twelve verified v5 checkpoints without retraining. Reference traces may be shared only with identical contracts and all logical bindings retained. |
| DAgger | BFS x three modalities; two iterations, at most 128 expert corrections and 512 collection decisions per modality/iteration. Each update uses exactly 512 records, one epoch and 16 updates. Compare original SFT, matched continued-SFT and DAgger. #79 must fix aggregation/sampling before collection. |
| Successor prediction | BFS x three modalities, proposed 512 complete-state training targets per cell, one epoch and 16 updates. Freeze a full dynamic-state/fluents schema and static-context checks; measure the necessary output allowance instead of truncating states to the old 384-token operation allowance. Compare with trusted-successor controls. |
| Curriculum | Additive greedy best-first x three modalities x staged/shuffled/mixed order = nine fresh adapters from the same base. Same 512 unique records per algorithm, one epoch, 16 updates, seed 17. Use deterministic source-difficulty ordering, seed-64 shuffled order and difficulty-interleaved order; disable trainer reshuffling. |
| Generalization | Two predeclared structural-shift variants per core problem; determine profiles and semantic eligibility before outcomes. Primary cells are the twelve baseline adapters plus declared controls. |
| Robustness | Three predeclared name/render perturbation families per core problem. Audit whether each variant preserves semantics and information availability; report lossy perturbations separately. |
| Replication | One additional locally executable backbone, BFS x three modalities, matched 512-record/16-update exposure and declared core-panel controls. #101 chooses and pins the model by capability, license and measured capacity, not final success. |
| Transfer | FOLIO, HumanEval and GSM8K: up to 200 examples per benchmark, or its complete official evaluation set if smaller. Freeze selection before outputs and label subsets. Compare the base with the three BFS modality-trained baseline adapters using matched benchmark prompts. This is zero-shot transfer unless a separate adaptation protocol is explicitly added. |

Use training seed 17 per cell; do not automatically add independent seeds or
restore the old five-seed/full-factorial workload. Second-backbone replication
does not estimate training-seed variance. Any extra seeds require a prospective
allocation and complete accounting. Representative BFS and additive-greedy cells
limit workload while covering correction, transition prediction and curriculum;
do not generalize their effects to unmeasured algorithms.

## Evidence and scientific controls

- Preserve v5's completed training/evaluation/analysis, all original #72–#74
  assets, collect-003/004, and the historical #67/#75/#76/#77/#100/#108 results.
  Do not turn an old not-planned closure into evidence that an experiment ran.
- The new panel must be disjoint at whole-instance semantic level from training,
  development, v5 and other previously observed final tasks. Select candidates
  by frozen structural/reference criteria, not model scores. Only new-task assets
  may be generated; do not copy or regenerate the complete historical corpus.
- Keep unlabelled 128x128 initial/current state PNGs and separate complete context
  and source-goal pages. Changes of representation need an explicit prospective
  experiment; no hidden annotations or trusted-state substitution. Information
  can be lost, and the processor may resize images. Do not claim equal information.
- Revalidate full source goals, quantified scope, input bounds, shared bounded
  Search Memory and the producing-operation boundary for successor images.
- DAgger collects from training tasks only, querying the expert from the last valid
  state. Default to per-modality on-policy data: equal quotas/updates are not equal
  collected examples. Continued-SFT controls match extra update exposure. Fix
  treatment of unused correction quotas before collection, without duplicating
  records to pretend quotas were met or inventing expert corrections.
- Successor prediction retains raw full-state predictions. Wrong states must not
  become trusted states or be silently replaced. Measure applicability, effects,
  schema/identity errors and downstream search separately. Verify static facts
  without conflating them with model-predicted dynamic state.
- Random-valid is an oracle-assisted valid-operation control, not an equally
  assisted learned policy. Separate operation validity from subsequent search
  quality. Validity-conditioned success is selected and is not repaired-policy
  counterfactual performance. Preserve native invariant flags and uniform invalid
  operation counts rather than assuming their meanings match across families.
- Only predeclared final checkpoints enter held-out comparisons. No favourable
  reruns, test-driven hyperparameter changes, repeated training until positive,
  or selection of algorithms from final outcomes. Independent replay verifies
  completed episodes; ordinary invalid-operation/budget failures remain outcomes.
- Use whole-problem paired analysis with explicit strata and tiny-subgroup limits.
  New curriculum-by-modality evidence is separate from #67's saturated development
  result; never pool unmatched historical training schedules. Follow official
  benchmark scoring for transfer and sandbox HumanEval execution.

## Execution contract for every copied goal

Read AGENTS.md, this plan, schedule.json and the linked ticket comments first.
Use `source ~/cd_vlaplan` for Python and explicitly specify
`--repo Sino-Huang/multimodality_on_planning` on every `gh` command.

Invocation of a branch goal authorizes its actual commands within its qualified
allocation. Do not hand training/evaluation commands back to the user. Ask only
for essential missing information or actions outside existing authorization.
Do not add approval manifests or infer a new permission requirement from an old
deadline ticket. Budget and hard cutoffs still apply.

Use at most one of this program's model workers per GPU. Give each concurrent
torchrun/ms-swift process a distinct explicit MASTER_PORT; the proposed pool is
18800–18805, subject to checking availability. A two-GPU job reserves both GPUs;
logically independent branches are not permission to oversubscribe them.

Run long jobs in the background. Retain per-stage logs, completed/total, elapsed
time, ETA and heartbeats at least every 30 seconds. Write terminal status on every
exit and use a completion callback/hook to trigger audit or failure diagnosis.
Avoid repetitive model-driven polling and routine waiting messages. If the host
automatically resumes a goal, check the same live handle minimally and never
relaunch solely because a wait timed out. Implement and test safe resume and
duplicate-launch refusal. Preserve incomplete traces/checkpoints and prior attempts.

Every branch ends with independently verified full declared coverage or an explicit
terminal partial/failure report. Fix technical defects without changing the frozen
scientific comparison. Never label an unfinished experiment complete. Commit/push
code, configurations and compact evidence; close only satisfied tickets.

## Schedule and dependencies

Days 1–2: #116 -> #117 -> #118; prepare DAgger and successor interfaces alongside
CPU panel work. Freeze branch matrices and cost admission before new final outcomes.

Days 2–6: run qualified DAgger, successor prediction, curriculum, generalization,
robustness, replication and transfer under one scheduler. Independent CPU work
can overlap model work. Start manuscript outline and analysis as results arrive.

Day 7: finish declared runs, independently replay, and spend recovery allocation
only on documented technical recovery. No new GPU jobs after the absolute cutoff.

Days 8–9: #120 synthesis -> #121 manuscript -> #122 release/handoff. Drafting and
release preparation may begin earlier, but final claims require verified artifacts.
Preserve incomplete branches explicitly if recovery could not complete them.

| Agent goal | Dependencies | Ownership |
| --- | --- | --- |
| 1 Shared readiness | preparation documents | #116 |
| 2 Broader panel | 1 | #117 |
| 3 Expanded baseline | 2 | #118 |
| 4 DAgger interface/config | 1; fixed v5 starting checkpoints | #78–#79 |
| 5 DAgger collection/replay | 4 | #80–#83 |
| 6 DAgger training/evaluation | 5 and 3 | #84 |
| 7 Successor interface/config | 1 | #85–#86 |
| 8 Successor data/replay | 7 | #87–#88 |
| 9 Successor training/final evaluation | 8 and 2 | #89, #99 |
| 10 Curriculum by modality | 2 and qualified exposure contract | #119 |
| 11 Generalization/robustness | 2 and fixed baseline checkpoints | #96, #98 |
| 12 Second backbone | 2 and fixed reference comparison | #101–#103 |
| 13 Transfer | 1 and fixed starting checkpoints | #104–#107 |
| 14 Synthesis | all declared experiment branches terminal | #120 |
| 15 Manuscript | 14 for final results; outline earlier | #121 |
| 16 Release/handoff | 14 and 15 | #122 |

Preparation verification consists of checking allocation arithmetic, absolute
dates, complete ticket mapping, dependency consistency and copyable goal coverage.
No hardware qualification or new experiment result is claimed by these documents.
