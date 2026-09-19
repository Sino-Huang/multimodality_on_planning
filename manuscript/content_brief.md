# Content Brief

## Progress
- Manuscript genre and central contribution: REVISED to a development-stage map of when executable search control is learnable and when it fails to generalize.
- Evidence audit: ALIGNED through `origin/main` commit `abe99f2` on 2026-09-19 and merged into `manuscript` at `4a5d06a`.
- Title: RETAINED — "Can Vision-Language Models Learn to Execute Classical Search Algorithms?"
- Abstract: REVISED on 2026-09-19 to a concise 164-word deadline version with one bounded BFWS result and a high-level broader-evidence boundary.
- Introduction: REVISED and synchronized to evidence through 2026-09-19.
- Related Work: NOT STARTED
- Method and evidence contract: NOT STARTED
- Evaluation protocol or results: NOT STARTED
- Limitations and conclusion: NOT STARTED
- Appendix: NOT STARTED

## Section Summary
- The paper extends the prior diagnosis of operational reasoning versus structural enumeration by directly training Search Process Policies to execute declared search algorithms under a replay-determinative Trusted Search Runtime.
- The policy must emit every exploration-determining operand. The runtime validates, applies, checks Algorithm Invariants, and maintains bounded Search Memory without filling omitted choices or repairing invalid outputs. Operation validity, invariant compliance, episode success, and advantage over random-valid remain separate measurements.
- BFWS supplies the only clear positive learned-control comparison. On a frozen 15-task text-state development panel, one fixed-seed process-SFT run achieved 0.933 success versus 0.467 for oracle-assisted random-valid, 0.0 for the pretrained base, and 1.0 for exact execution. The absolute gain is 0.467 and the paired whole-instance bootstrap lower bound is 0.2. This is a single-seed development result; the held-out manifest was not accessed.
- On BFS and two additive best-first development panels, process SFT matched but did not exceed random-valid at 100%. These saturated controls show that executable behavior alone does not identify learned advantage.
- The active algorithm matrix is BFS, width-based best-first (the complete unpruned BFWS variant), additive weighted best-first, and additive greedy best-first. The optimal A* h_max/landmark design was retired after a governed stop; its original heuristic-representation estimand remains unidentified.
- The expanded matched baseline covers 24 tasks from 12 domains in text-state, visual-state, and multimodal-state conditions. The pretrained base achieved 0/288, process SFT 125/288, random-valid 240/288, and exact execution 288/288. Process-SFT successes occurred only in additive best-first cells; BFS and width-based best-first scored 0/24 in every modality.
- The matched-modality evaluation found SFT success of 5/12 text, 6/12 visual, and 6/12 multimodal versus 10/12 random-valid in each modality and 0/12 base. The evidence does not support an intrinsic modality effect.
- Two DAgger iterations produced 1 success versus 1 for exposure-matched continued SFT on 72 unseen modality-task rows; DAgger showed no advantage and a higher invalid-operation rate.
- Under model-generated dynamic-state successors, the model arm reached 1/45 goals versus 45/45 with trusted successors. Most failures were exact state-identity or effect failures rather than schema failures.
- Curriculum ordering by modality produced no material interaction: all four interaction intervals include zero. Several conditions and controls saturated.
- Generalization/robustness evaluation and second-backbone model evaluation terminated as resource-bounded no-runs. The second backbone was qualified, but no training or model outcome exists. Transfer, synthesis, and the authorized final primary evaluation remain unexecuted.
- All current model comparisons use a single training seed. Repeated rollout or reference seeds do not estimate training-seed variance. No overall final comparative efficacy finding is licensed.
- The revised 164-word Abstract asks whether process supervision can teach declared search execution, summarizes the policy/runtime separation, reports the bounded BFWS development result, and states that broader development panels show no consistent advantage across algorithms or modalities. It omits experiment-ledger detail and concludes only that learned-control advantage appeared in one development setting while broader planning efficacy remains open.
- The synchronized Introduction preserves the domain motivation, prior observational diagnosis, training/full-episode gap, and policy/runtime mechanism. Its latter half now uses the active BFS/BFWS/additive-best-first matrix, treats modality/DAgger/successor/curriculum studies as completed, reports the BFWS positive comparison and expanded-baseline failures, and marks held-out primary evaluation, generalization, second-backbone outcomes, and transfer as unresolved.
- Its three contributions are now an executed diagnosis-to-intervention test, the replay-determinative interface, and a headroom-dependent empirical map rather than a BFS-only pilot plus pending BFWS infrastructure.

## Open Items
- [TODO: final efficacy] No authorized held-out final primary evaluation exists. Goal 14 synthesis, Goal 15 manuscript, and Goal 16 release/handoff remain open.
- [TODO: generalization] The qualified generalization/robustness suite was not evaluated because of the frozen compute admission rule.
- [TODO: replication] The InternVL3.5-8B input/runtime interface passed qualification, but adapter training and panel evaluation were not launched; there is no second-backbone outcome.
- [TODO: transfer] FOLIO, HumanEval, GSM8K, and other transfer evaluations remain unrun.
- [TODO: uncertainty] Every current model cell uses one training seed; training-seed variance is unestimated.
- [TODO: random-valid definition] Method/Results must define the oracle-assisted validity-constrained sampling distribution, candidate access, runtime filtering, budget parity, and absence of retry/repair.
- [TODO: modality boundary] Unlabelled 128px views may lose symbolic identities, static/goal pages still contain text, and the available evidence does not establish semantic parity or an intrinsic modality effect.
- [TODO: Related Work citations] Substantiate the scoped comparison against search learning, neural algorithm execution, planning, and runtime-verification literature. Do not assert priority without support.
- [TODO: project glossary] The root `CONTEXT.md` remains stale about the ticket range and still names IW/A* invariant examples. This writing session cannot edit files outside `manuscript/`.
- [RESOLVED: BFWS result] BFWS process-SFT training and the structural gate completed with a development-panel PASS.
- [RESOLVED: A* status] Optimal A* was retired and superseded by additive best-first variants; it is not a prospective active study arm.
- [RESOLVED: modality/DAgger/successor/curriculum execution] These development comparisons are complete, although none establishes broad learned advantage.
- [RESOLVED: Introduction sync] The design, evidence snapshot, contribution list, and boundary statement now match the merged 2026-09-19 evidence.
- [RESOLVED: test collection] Issue #41 is closed; historical collection errors no longer block the evidence program.
- [RESOLVED: prior-work citations] The Introduction cites the original planning-probe sources and arXiv:2607.11197 at their appropriate claim boundaries.

## Next
- The revised 164-word deadline Abstract compiled successfully on 2026-09-19 with `manuscript/build_pdf.sh`; the three-page PDF has no LaTeX errors, undefined citations, or layout warnings, and the complete eight-sentence Abstract was verified from the rendered PDF.
- The following session should either reconcile any critical Abstract wording issue or begin Results. The detailed experimental ledger belongs in Results rather than the deadline Abstract and can be reflected in later paper-stage Abstract revisions.
