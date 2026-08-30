# Manuscript Design Tree

## Evidence Boundary

- Issue #38 is the ratified, still-open authority for the Search Process Policy program. A direct audit on 2026-08-31 inspected every issue and substantive comment from #54 through #111. Seven issues are closed (#54--#58, #110, #111); #59 and #60--#109 remain open.
- Issue #111 released the observable BFS v6 text-state process corpus: 90 trusted/replay traces and 25,109 process rows, split into 12,994 train and 12,115 dev rows. Inputs expose canonical task context, exact grounded successor candidates, and full visited membership. Release audits record zero semantic/input/input-target overlap, conflicting identical-input labels, teacher-operation rejection, and live/corpus mismatch under 8,192 total tokens and a 384-token output allowance.
- Issue #54 is closed with governed outcome `VALID_STOP` under the resource-bounded v8 successor. On a frozen outcome-blind 15-task BFS development panel, final checkpoints from five process-SFT seeds achieved 1.0 invariant-valid success and 0.0 invalid-operation rate; the base achieved 0.0 and random-valid achieved 1.0. The learned policy therefore showed executable BFS behavior on the selected panel but zero gain over the strongest control, so `scientific_completion=false` and downstream work received `gated-not-run`.
- Issue #55 found that independent IW(1), IW(2), and IW(3) attempts were not corpus-complete and selected the complete unpruned `full_bfws_goal_count` successor. Issue #56 froze a 105-task development panel and an inaccessible fresh 45-task held-out manifest. Issue #57 released exact replay-verified BFWS traces for all 105 tasks and 69,019 decisions. Issue #58 released 69,019 process records, 67,215 operational records, and a 47,780-train/21,239-dev process projection with zero recorded overlap, mismatch, rejection, token, or held-out-access counters.
- Issue #59 remains open. The BFWS training/evaluation runner exists, but the actual single-training-seed experiment and structural-gate adjudication are incomplete. The supervisor budget correction authorizes one training run at seed 17 per distinct future model/cell configuration; repeated rollout/reference seeds do not estimate training-seed variance.
- A* adapters/corpora/results, modality corpora and matrices, DAgger, end-to-end successor prediction, final evaluation, replication, and transfer remain open under #60--#109. No final comparative efficacy finding or scientific completion exists.
- Issue #110 supplies deterministic compact delta/event evidence with semantic replay while preserving search semantics. Historical planning, rendering, and Integration Certification remain feasibility evidence only.

## Root Decision

**D1. Manuscript genre and truthful contribution**

- Selected: an empirical Search Process Policy paper drafted as a result-ready skeleton until the runtime and evaluation program complete.
- Constraint: distinguish completed bounded development-panel findings from final efficacy. The title, abstract, and conclusion may report the #54 BFS v8 result only with its 15-task coverage, random-valid ceiling, `VALID_STOP`, and `scientific_completion=false`; they must not imply final algorithmic advantage, modality effects, or scientific completion.

Status: SET on 2026-08-18. This decision determines the title, abstract, section structure, and permissible conclusion.

## Dependent Decisions

- D2: precise central claim and title, after D1. SET: assess whether a VLM can execute declared classical search algorithms as a Search Process Policy by issuing Typed Search Operations whose explicit operands determine exploration. The Trusted Search Runtime validates, applies, persists, and rejects operations without choosing omitted operands, reordering candidates for the policy, or silently repairing outputs. The working title is "Can Vision-Language Models Learn to Execute Classical Search Algorithms?" Primary evidence is full-episode budgeted success, reported separately from operation validity, invariant compliance, invalid-operation budget charges, and learned-to-control gain. Transfer beyond planning is gated and secondary. Any priority claim requires [TODO: cite] support.
- D3: abstract commitment and reader promise, after D1 and D2. SET: report the bounded #54 BFS v8 `VALID_STOP` exactly, including its 15-task coverage and random-valid ceiling, while keeping BFWS, A*, modality, DAgger, and final evaluation prospective. Do not imply final efficacy or scientific completion.
- D4: section architecture, after D1 through D3. SET: Abstract; Introduction; Related Work; Search Process Policy; Experimental Design; Results; Discussion and Limitations; Conclusion; Appendix. The mandatory Appendix contains the full evidence contract. Historical infrastructure is confined to feasibility and implementation context or appendices.
- D5: evidence tables and figures, after D4. SET: make the primary display an algorithm-by-condition matrix for base, process SFT, process SFT plus DAgger, random-valid, and exact-classical references. Report full-episode budgeted success, operation validity, Algorithm Invariant compliance, invalid-operation rate, charged budget, and learned-to-best-control gain separately. Use secondary panels for modality cells, trusted-successor versus model-generated-successor results, and gated transfer.
- D6: related-work comparison and novelty claim, after D1 and D2. SET: use a citation-supported, scoped comparison around algorithm-conditioned Typed Search Operation policies, model-owned search decisions, a no-repair Trusted Search Runtime, invariant-checked full episodes, and matched modalities.
- D7: limitations and negative-result policy, after D1 and D4. SET: once gates are frozen, report each as PASS, VALID_STOP, INVALID, or ANCESTOR_STOP; show null effects, invariant failures, invalid-operation charges, and validity separately; limit conclusions to passed gates.

## Section Decisions

- D8: Introduction. SET: foreground the gap between local operational competence and full-episode structural/process competence; direct plans or local transition accuracy do not establish algorithm execution.
- D9: Related Work. SET: compare four threads: classical planning/search, neural algorithm execution, LLM/VLM planning, and runtime verification/tool use.
- D10: Search Process Policy. SET: present a formal task and interface contract before examples: Modality Observation, Typed Search Operation, Search Memory, model/runtime ownership, Algorithm Invariants, and learning objective.
- D11: Experimental Design. SET: present the current staged sequence: bounded BFS pilot, BFWS structural gate, paired A* variants, modality matrix, DAgger, final primary evaluation, replication, and gated transfer. Capped IW is retained as qualification history, not the active structural gate. The final evaluation remains unfrozen until the preregistration prerequisites below are decided.
- D12: Results. SET: lead with gate receipts, then interpret effects only within passed scope; primary display is the structural algorithm-by-condition matrix with separate success, validity, invariant, invalid-operation, budget, and learned-to-control-gain measures.
- D13: Discussion and Limitations. SET: distinguish trusted-successor structural/process competence from model-generated-successor end-to-end competence; modality and transfer claims are conditional secondary findings.
- D14: Appendix. SET: include operation schemas, invariants, runtime pseudocode, data/splits, receipt tables, statistics, adapters, and retained-infrastructure feasibility details.

## Preregistration Prerequisites

Before the planned final evaluation is called frozen, define and record:

- the condition-level data source, Search-Trace Segment construction, and per-algorithm allocation;
- compute parity and checkpoint-selection rules; future cells use one training run at seed 17 per model/cell under the supervisor budget, while any repeated rollout/reference seeds and whole-instance uncertainty must be identified separately and must not be described as training-seed replication;
- the episode-budget unit, whole-instance split procedure, and fixed Search Memory capacity;
- the estimand, uncertainty interval or statistical test, success threshold, invariant-compliance rule, and validity and invalid-operation reporting denominators for every algorithm-by-condition cell.

Until these choices are set, the paper is a result-ready empirical skeleton rather than a preregistered evaluation protocol.

## Algorithm-Specific Corpus Prerequisites

Every algorithm-specific corpus must expose a decision-sufficient Modality Observation and pass no-conflict, no-leakage, live/training-parity, and token-budget checks. These requirements qualify corpus construction and release. They do not establish policy training or efficacy.

BFWS corpus evidence is implemented under #57--#58. Its shared bounded input exposes the candidate duplicate, novelty, priority, insertion, and enqueue facts needed by the exact teacher, and its released rows are bound to replay-verified positions. A future A* corpus must expose the exact frontier-order, reopen, best-cost, heuristic, landmark-progression, tie-breaking, and termination facts required by the declared h_max or landmark-count adapter. No A* corpus currently exists, and its schema need not be identical to BFS or BFWS.

## Section Blueprint

- Title: "Can Vision-Language Models Learn to Execute Classical Search Algorithms?"
- Abstract: state the structural/process competence gap, the explicit model/runtime ownership contract, and the bounded BFS v8 result. Identify the `VALID_STOP` cause: random-valid matched process SFT at 1.0 on the 15-task panel. Keep BFWS, A*, modality, DAgger, and final evaluation prospective.
- Introduction: establish that action-level or transition-level operational competence does not establish full-episode algorithm execution. State three contributions: the replay-determinative Search Process Policy interface; the bounded governed BFS result; and the released BFWS structural-search traces/corpus plus staged evaluation contract.
- Related Work: organize classical planning/search, neural algorithm execution, LLM/VLM planning, and runtime verification/tool use. Include a compact axis table covering algorithm conditioning, model-owned exploration, no-repair runtime, invariant-checked episodes, matched modalities, and transfer.
- Search Process Policy: formally define task inputs, Modality Observation, the Typed Search Operation envelope and operands, Search Memory, Algorithm Invariants, learning objective, and model/runtime ownership. The runtime may validate and apply explicit policy decisions but may not supply missing exploration choices.
- Experimental Design: define the three checkpoint conditions (base, process SFT, process SFT plus DAgger), random-valid and exact-classical references, planned budgets, whole-instance splits, and the staged path from the bounded BFS pilot through BFWS, A*, modality, DAgger, final evaluation, replication, and transfer. Distinguish the historical five-seed BFS pilot from the one-training-seed policy governing future cells.
- Results: present gate receipts before effects. The primary table is algorithm by condition, with separate columns for full-episode budgeted success, operation validity, Algorithm Invariant compliance, invalid-operation rate, charged budget, and learned-to-best-control gain; it does not combine these measures. Secondary panels cover modality, trusted-successor versus model-generated-successor results, and frozen-policy transfer only after the protocol is frozen.
- Discussion and Limitations: distinguish trusted-successor structural/process competence from model-generated-successor end-to-end competence. Lead with the runtime boundary: the contract does not prove unassisted internal search or general autonomy. Interpret modality and transfer only at passed gates.
- Conclusion: give a gate-bounded answer to the main question, identify claims not yet supported, and state only the next gated step.
- Appendix: retain the complete evidence contract, including interfaces, invariants, pseudocode, data and splits, statistics, adapters, all receipts, and narrowly scoped feasibility details of retained infrastructure.

## Author Decision Log

- D1 accepted on 2026-08-18: write a result-ready empirical Search Process Policy manuscript skeleton, with unrun results explicitly marked as pending.
- D2 accepted on 2026-08-18: headline the question of direct learning and execution of classical search algorithms through a model-owned Typed Search Operation policy. Operational controls and modality conditions are secondary; transfer is gated and secondary.
- D3 accepted on 2026-08-18: the abstract uses study language and result placeholders rather than unearned outcome claims; the planned evaluation is not yet frozen.
- D6 accepted on 2026-08-18: novelty is a scoped, citation-dependent comparison, not a broad priority assertion.
- D4 accepted on 2026-08-18: use an empirical-study architecture that separates the intervention, evaluation contract, results, and limitations.
- D5 accepted on 2026-08-18: center results on the structural algorithm-by-training-arm matrix, reporting success, validity, invariant compliance, invalid-operation rate, and charged budget separately, with modality and transfer as secondary analyses.
- D7 accepted on 2026-08-18: preserve prespecified stop receipts, null findings, and failures in the main narrative.
- D8--D14 accepted on 2026-08-18: section scopes are fixed as above; the arm-level protocol parameters required for a frozen final evaluation remain open.
- D15--D22 were accepted on 2026-08-18 under the earlier four-condition proposal. The 2026-08-31 issue audit supersedes its operational-only arm and five-training-seed assumptions: the active design uses base, process SFT, and process SFT plus DAgger with random-valid and exact-classical references, and future cells authorize one training seed per model/cell.
- Evidence alignment was updated on 2026-08-31 after direct inspection of issues #54--#111. The previous no-efficacy boundary is superseded by the bounded #54 BFS v8 `VALID_STOP`: executable behavior is demonstrated on its 15-task development panel, but no learned advantage over random-valid and no scientific completion are established. The active structural gate is BFWS, not capped IW; operational-only SFT is not an authorized comparator; and future cells use one training seed per model/cell under the supervisor budget.
- Author confirmation received on 2026-08-18: the Section Blueprint captures the intended manuscript. The grilling frontier is closed.
