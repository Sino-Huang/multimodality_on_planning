# Issue Migration Plan: CGAS Tracker to Search-Process Research Target

**Status:** Approved migration record, amended 2026-08-21 to remove the operational-only SFT arm from current scope.
**Repository:** `Sino-Huang/multimodality_on_planning`.

This document records the migration proposal that was subsequently approved and realized in the issue tree rooted at GitHub [issue #38](https://github.com/Sino-Huang/multimodality_on_planning/issues/38). It does not itself authorize tracker mutations. The transaction details below are retained as history; #38 is the current scope authority, including the 2026-08-21 removal of operational-only SFT from planned work.

Companion documents:

- Current state audit: [`research_target_assessment.md`](../../research_target_assessment.md)
- Concurrent terminology/policy realignment brief: [`search-process-policy-realignment.html`](./search-process-policy-realignment.html)
- Current research proposal: [`research_proposal.md`](../research_proposal.md)
- Current specification: [`research_implementation_spec.md`](../high_level_plans/research_implementation_spec.md)
- Current execution plan: [`research_execution_plan.md`](../high_level_plans/research_execution_plan.md)
- Accepted ADR: [`0001-use-local-lama-first-for-planimation-production.md`](../adr/0001-use-local-lama-first-for-planimation-production.md)
- Canonical terminology: [`CONTEXT.md`](../../CONTEXT.md)
- Tracker conventions: [`issue-tracker.md`](../agents/issue-tracker.md), [`triage-labels.md`](../agents/triage-labels.md)

---

## 1. Why migration is needed

The current tracker implements the CGAS target: stepwise Joint Action-and-Certificate SFT over replayed BFS/IW plan transitions, measured by Verified Joint Step, with Adaptive Scaffolding over Support Routes backed by Live Memory and Route Labels (canonical terms per [`CONTEXT.md`](../../CONTEXT.md)).

The proposed target is different in kind: teach algorithm-conditioned, executable search behavior from canonical planner-derived ReAct traces with typed operations. The model owns the search decisions; a trusted PDDL runtime stores and validates state and returns modality-specific observations but cannot choose or repair evaluation decisions. The core algorithm set is BFS (positive control), IW, A*+h_max, and A*+landmark-count, where the A* pair is a heuristic-representation comparison. Training is organized as matched algorithm-by-modality cells (text-state, visual-state, multimodal-state with state+goal semantic parity and a fixed search-memory API/capacity), across base, process SFT, and process SFT+DAgger arms, under a staged curriculum with a mixed-order control. The operational-only SFT arm was removed on 2026-08-21 to prioritize learning the search process under the available time; this is a scope decision, not evidence that operational SFT cannot affect search. Experience Distillation is at most a gated comparison, not a headline arm.

Because the scientific target, the model/runtime responsibility split, the algorithm set, the training arms, and the evaluation gates all change, the existing issue tree cannot simply be relabeled. It must be superseded by a new dependency-ordered tree, with reusable evidence and infrastructure carried forward explicitly.

The terms "Search Process Policy", "typed operation", "search-trace segment", and related names used below are **proposed terminology** from the realignment brief. They are not current canonical terminology; [`CONTEXT.md`](../../CONTEXT.md) remains unchanged until the supervisor approves a terminology revision through the normal documentation process.

---

## 2. Non-negotiable preservation

The following constraints hold regardless of the migration outcome:

1. Closed certification milestones (#2-#7) and their recorded evidence remain closed and untouched. No history rewriting.
2. Every Attempt and Evidence Bundle produced to date is retained. Completed work is archived, never deleted.
3. ADR-0001 (local LAMA-first supplied plans for Planimation production) remains accepted. Nothing in the proposed target reopens it.
4. The existing Integration Certification, deterministic verifier, trace contracts, provenance records, rendering path, and one-invariant counterfactual generator are retained as infrastructure. The proposed target reuses them; it does not replace them.
5. No current document (proposal, specification, execution plan, CONTEXT.md) is edited before supervisor approval. Documentation revision is a separate step in the migration order, executed through the approved process.
6. The 13 documented pre-existing collection errors and the missing ADR referenced by issue #8 remain visible as evidence limitations in any migrated plan.

---

## 3. Group-level disposition of the existing tracker

Per-issue states inside each open group are **not** individually known from the assessment; each open issue requires fresh triage before any action. Dispositions use: `retain`, `fresh triage`, `supersede-after-approval`, `reuse-under-new-target`.

| Group | Issues | Disposition | Notes |
| --- | --- | --- | --- |
| Master specification | #1 | retain until approval; supersede-after-approval | Remains authoritative until the supervisor approves the new master spec. Closed only after the replacement is accepted and cross-linked. |
| Closed certification milestones | #2-#7 | retain | Closed evidence of Integration Certification work. No action. |
| Plan sourcing / no-hosted revision | #8 | fresh triage; likely supersede-after-approval | Scope-revision issue; the assessment notes the ADR it references is missing. Triage must record that limitation rather than resolve it silently. |
| Pilot, calibration, routing, final evaluation | #9-#21 | fresh triage per issue | Pilot-corpus and calibration material is likely `reuse-under-new-target` (data and evaluation machinery). Live Memory, Route Labels, and Adaptive Scaffolding routing items are demoted from the headline; expected `supersede-after-approval` or `wontfix` with a pointer to the demotion rationale. Exact per-issue mapping requires fresh triage. |
| Backbone and generalization | #22-#29 | fresh triage per issue; likely reuse-under-new-target | The proposed target keeps one primary VLM plus a targeted second-backbone replication, so some items remap; the prior three-backbone plan does not carry over wholesale. |
| FF / Graphplan transfer | #30-#37 | fresh triage per issue; likely supersede-after-approval | The proposed target's gated transfer set is FOLIO / HumanEval / GSM8K, not FF/Graphplan. These issues do not map onto the new transfer branch. |

No per-issue disposition is asserted beyond the group level. Any issue whose body turns out to contradict this table during fresh triage is escalated to the supervisor rather than silently reclassified.

---

## 4. Proposed new issue tree

Issue numbers below are placeholders (N1-N15); real numbers are assigned at creation time and are an open decision (Section 7). Every issue is created with a canonical triage label from [`triage-labels.md`](../agents/triage-labels.md). Creation order is dependency order.

### N1 - Master spec: Search Process Policy research target and terminology decision
- **Objective:** Ratify the new headline (algorithm-conditioned executable search behavior from planner-derived ReAct traces with typed operations), adopt or reject the proposed terminology (Search Process Policy and related names), and record the demotion of Planning Certificates as headline mechanism, Joint Action-and-Certificate SFT, Adaptive Scaffolding, Support Routes, Live Memory, Route Labels, and CGAS efficacy claims.
- **Acceptance evidence:** Supervisor-approved spec document merged; CONTEXT.md terminology revision approved through the documentation process; explicit cross-reference to issue #1.
- **Depends on:** none (supervisor approval of this plan).
- **Label:** `ready-for-human`

### N2 - Trusted PDDL runtime and typed-operation contract
- **Objective:** Define the runtime boundary: the trusted PDDL runtime stores/validates state, applies transitions, and returns modality-specific observations; the model owns all search decisions; the runtime cannot choose or repair evaluation decisions. Specify the typed operation set and rejection-cost semantics.
- **Acceptance evidence:** Versioned contract document plus hermetic tests demonstrating that runtime responses contain no decision content and that rejected operations have declared cost.
- **Depends on:** N1.
- **Label:** `needs-triage`

### N3 - Trace and verifier support for BFS, IW, A*+h_max, A*+landmark-count
- **Objective:** Extend the retained trace/verifier infrastructure to emit canonical ReAct traces with typed operations for the four core algorithms, reusing existing BFS/IW contracts and adding the two A* variants.
- **Acceptance evidence:** Deterministic regeneration with byte-identical replay for all four algorithms; verifier checks for each typed operation; A* pair documented as a heuristic-representation comparison.
- **Depends on:** N2.
- **Label:** `needs-triage`

### N4 - Search-trace segment contract
- **Objective:** Define the training/evaluation segment unit over canonical traces (observation, memory state, typed operation, outcome) with no-oracle-leakage guarantees.
- **Acceptance evidence:** Signed segment contract with tests proving no test-time access to teacher decisions, future states, or hidden planner ordering.
- **Depends on:** N3.
- **Label:** `needs-triage`

### N5 - Matched text/visual/multimodal corpus
- **Objective:** Build the matched corpus: text-state, visual-state, and multimodal-state renderings of the same symbolic tasks with state+goal semantic parity, fixed search-memory API/capacity, and problem-level splits.
- **Acceptance evidence:** Released corpus with parity checks (identical symbolic content across modalities), problem-level split manifest, and integration-certification evidence for the rendering path under ADR-0001.
- **Depends on:** N4.
- **Label:** `needs-triage`

### N6 - Gate: BFS text sanity
- **Objective:** First evidence gate: the process-SFT text-state cell on BFS traces must demonstrate nontrivial executable search behavior under the frozen harness.
- **Acceptance evidence:** Budgeted full-episode search success and deterministic algorithm-fidelity checks above the random policy and declared learned controls, reported per seed; the gap to the exact classical reference is reported rather than required to be positive.
- **Depends on:** N5.
- **Label:** `needs-triage`

### N7 - Gate: IW text
- **Objective:** Second gate: IW text-state cell, testing generalization beyond the BFS positive control before any A* or modality spend.
- **Acceptance evidence:** Same harness and measures as N6 on IW; pass/fail threshold fixed in N1's spec.
- **Depends on:** N6.
- **Label:** `needs-triage`

### N8 - Gate: A* pair (heuristic-representation comparison)
- **Objective:** A*+h_max vs A*+landmark-count text-state cells as the heuristic-representation comparison.
- **Acceptance evidence:** Matched-budget comparison of the two heuristic representations with algorithm-fidelity checks.
- **Depends on:** N7.
- **Label:** `needs-triage`

### N9 - Modality matrix experiment
- **Objective:** The matched algorithm-by-modality cells (four algorithms x three modalities) across base and process SFT, with staged curriculum and mixed-order control.
- **Acceptance evidence:** Full cell matrix results under problem-level splits and frozen operational/structural diagnostics.
- **Depends on:** N8.
- **Label:** `needs-triage`

### N10 - DAgger experiment
- **Objective:** Process SFT+DAgger arm on the cells justified by N9, measuring whether correction data improves executable search behavior.
- **Acceptance evidence:** Budget-matched comparison of process SFT vs process SFT+DAgger with declared correction-budget accounting.
- **Depends on:** N9.
- **Label:** `needs-triage`

### N11 - Frozen evaluation and structural shifts
- **Objective:** Final frozen-harness evaluation of headline cells: five seeds, held-out structural shifts, random/classical references, frozen operational/structural diagnostics.
- **Acceptance evidence:** Pre-registered evaluation report on untouched test splits; every seed reported.
- **Depends on:** N10.
- **Label:** `needs-triage`

### N12 - Second-backbone replication
- **Objective:** Targeted replication of headline cells on one second VLM backbone (primary backbone plus exactly one targeted replication, per the confirmed target).
- **Acceptance evidence:** Matched-cell replication report against the primary-backbone result.
- **Depends on:** N11.
- **Label:** `needs-triage`

### N13 - Gated transfer: FOLIO / HumanEval / GSM8K
- **Objective:** Secondary, gated transfer evaluation with behavioral and error signatures, opened only after headline gates pass.
- **Acceptance evidence:** Transfer report with prespecified behavioral/error-signature analysis; explicitly secondary to the headline result.
- **Depends on:** N11.
- **Label:** `needs-triage`

### N14 - Gated comparison: Experience Distillation (optional)
- **Objective:** If and only if the supervisor approves, a bounded Experience Distillation comparison arm. Not part of the headline.
- **Acceptance evidence:** Budget-matched comparison against the process-SFT cell it parallels.
- **Depends on:** N9.
- **Label:** `needs-triage`

### N15 - Final manuscript and evidence synthesis
- **Objective:** Synthesize all gated results into the manuscript, including negative results at any gate, with full provenance to retained CGAS-era evidence.
- **Acceptance evidence:** Manuscript draft whose every empirical claim traces to an accepted gate artifact.
- **Depends on:** N11, N12, N13 (N14 if opened).
- **Label:** `needs-triage`

Dependency chain summary: N1 -> N2 -> N3 -> N4 -> N5 -> N6 -> N7 -> N8 -> N9 -> N10 -> N11 -> {N12, N13} -> N15; N14 optional off N9.

---

## 5. Migration transaction order

Execute in this exact order, each step gated on the previous:

1. **Supervisor approval.** The supervisor approves or rejects this plan and the proposed target. No tracker or documentation change happens before this.
2. **Snapshot current state.** Record the full current tracker state (`gh issue list --state all --json ...` export committed to the repo or an evidence directory) so the pre-migration state is recoverable.
3. **Create new tree.** Create N1-N15 in dependency order with labels per Section 4. N1 is created first and carries the supervisor decision.
4. **Cross-link.** Add one comment on each existing open issue pointing to the relevant new issue(s), and one comment on each new issue naming the old issues it supersedes or reuses. Issue #1 gets a pointer to N1.
5. **Close or supersede only after replacement acceptance.** An old issue is closed (as superseded or `wontfix`) only after its replacement issue exists, is cross-linked, and its acceptance evidence is defined. Closed issues #2-#7 are never reopened or edited.
6. **Revise documentation.** Revise the proposal, implementation spec, execution plan, and CONTEXT.md terminology through the approved documentation process, after N1 is accepted.
7. **Freeze, then test, then execute.** Freeze the harness and configuration; run gates in the N6 -> N7 -> N8 order; no modality or transfer spend before the text gates pass.

---

## 6. Stop conditions and rollback

1. **Supervisor rejects the target:** make no issue changes, no documentation changes, no deletions. This plan is archived as a rejected proposal; issue #1 and current specs remain authoritative unchanged.
2. **BFS or IW text gates fail (N6/N7):** do not open the A*, modality-matrix, DAgger, or transfer branches (N8-N10, N13). Report the gate result and return to the supervisor before any further spend.
3. **Any migration step fails partway:** stop the transaction. The snapshot from step 2 plus cross-link comments already placed are sufficient to reconstruct intent; no compensating deletion is performed.
4. **Absolute rule:** old issues, Attempts, Evidence Bundles, corpora, and infrastructure are never deleted as part of this migration, under any circumstance. Superseded work is archived in place.

---

## 7. Open decisions and TBD

The following are deliberately unspecified and must be resolved at or after supervisor approval, not assumed by this plan:

- Real issue numbers for N1-N15 and the exact numbering convention.
- Owner/assignee for each new issue.
- Exact pass/fail effect thresholds for gates N6, N7, N8 (fixed in the N1 spec, not here).
- Corpus sizes, per-cell instance counts, and split ratios for N5.
- Primary and second backbone model IDs for N9/N12.
- Compute budget, training hyperparameters, DAgger correction budget, and seed list beyond "five seeds for headline cells".
- Whether N14 (Experience Distillation comparison) is opened at all.
- Mapping of individual issues within groups #9-#21, #22-#29, #30-#37 to specific new issues (requires fresh triage of each body).

---

## 8. Approval checklist

By approving this plan, the supervisor approves exactly the following, and nothing more:

1. The proposed research target (Section 1) replaces the CGAS headline as the direction for new work.
2. Creation of the new issue tree N1-N15 with the stated objectives, dependencies, and triage labels.
3. The group-level dispositions in Section 3 as instructions for fresh per-issue triage, including the demotion of Adaptive Scaffolding, Support Routes, Live Memory, Route Labels, Joint Action-and-Certificate SFT as headline mechanism, Planning Certificates as headline mechanism, and CGAS efficacy from the headline claim.
4. The migration transaction order in Section 5, including the rule that no old issue is closed before its replacement is accepted.
5. The stop conditions and rollback rules in Section 6, including the no-deletion rule.
6. Subsequent revision of the proposal, specification, execution plan, and CONTEXT.md terminology through the approved documentation process.

The supervisor is **not** approving: any specific gate threshold, corpus size, backbone ID, hyperparameter, or the deletion of any existing issue or artifact.
