# Manuscript Design Tree

## Evidence Boundary

- Issue #38 is the ratified, still-open authority for the current Search Process Policy program. Terminology ratification completed in #39 and bounded pytest discovery completed in #40.
- The repository contains reusable historical planning, modality-serialization, trace, verifier, and planning-rendering provenance infrastructure. Certified 4-, 8-, and 12-object smoke Attempts support Integration Certification for their declared fixtures only.
- Fetched `origin/main` at commit `12031ef` contains a bounded BFS-only, text-state v6 pilot. It includes an observable Search Memory interface, a Search Episode Harness, Typed Search Operations, trusted/replay traces, and a released process-SFT corpus.
- The v6 release contains 90 trusted/replay traces and 25,109 process rows, split into 12,994 train rows and 12,115 dev rows. Its observations provide decision-sufficient task context, grounded successor candidates, and exact visited status. Release qualification records zero train/dev input overlap, input-target overlap, semantic-task overlap, conflicting identical-input labels, live/training mismatch, and teacher-operation rejection. The allowance is 8,192 context tokens and 384 output tokens. These are corpus and release-qualification evidence, not efficacy evidence.
- Issue #54 records corpus-release qualification `PASS` with `scientific_completion=false`, while the issue remains open/reopened. No clean governed SFT outcome exists. The current attempt cannot be retained because its release metadata records `accepted_delta_limit` 21 against the frozen limit of 16. The reported corrected 16-delta regeneration is byte-identical in learning payload and changes metadata and audit records only. This governance defect does not indicate changed training examples. See [the issue #54 qualification comment](https://github.com/Sino-Huang/multimodality_on_planning/issues/54#issuecomment-5407836531).
- No trained Search Process Policy, retained governed SFT outcome, IW or A* corpus, multimodal corpus, comparative efficacy result, or scientific completion exists.
- The full test suite remains blocked by 13 documented historical phase-3 collection errors. Retained rendering uses locally supplied plans; it is not planning or Search Process Policy evidence.

## Root Decision

**D1. Manuscript genre and truthful contribution**

- Selected: an empirical Search Process Policy paper drafted as a result-ready skeleton until the runtime and evaluation program complete.
- Constraint: before empirical gates complete, the title, abstract, and conclusion must not imply demonstrated performance, modality effects, or algorithmic success.

Status: SET on 2026-08-18. This decision determines the title, abstract, section structure, and permissible conclusion.

## Dependent Decisions

- D2: precise central claim and title, after D1. SET: assess whether a VLM can learn to execute declared classical search algorithms as a Search Process Policy by issuing Typed Search Operations, including model-owned exploration decisions, under a Trusted Search Runtime that validates and applies operations without repair. The working title is "Can Vision-Language Models Learn to Execute Classical Search Algorithms?" Primary evidence is full-episode budgeted success, reported separately from operation validity, invariant compliance, and invalid-operation budget charges. Transfer beyond planning is gated and secondary. Any priority claim requires [TODO: cite] support.
- D3: abstract commitment and reader promise, after D1 and D2. SET: use study language that states the question, intervention, controls, planned staged evaluation, and explicit result placeholders; reserve performance claims for completed gates. Do not call the evaluation frozen before its preregistration prerequisites are fixed.
- D4: section architecture, after D1 through D3. SET: Abstract; Introduction; Related Work; Search Process Policy; Experimental Design; Results; Discussion and Limitations; Conclusion; Appendix. The mandatory Appendix contains the full evidence contract. Historical infrastructure is confined to feasibility and implementation context or appendices.
- D5: evidence tables and figures, after D4. SET: make the primary display an algorithm-by-training-arm matrix with separate columns for full-episode budgeted success, operation validity, Algorithm Invariant compliance, invalid-operation rate, and charged budget. Do not combine these measures into a composite. Use secondary panels for modality cells, trusted-successor versus model-generated-successor results, and gated transfer.
- D6: related-work comparison and novelty claim, after D1 and D2. SET: use a citation-supported, scoped comparison around algorithm-conditioned Typed Search Operation policies, model-owned search decisions, a no-repair Trusted Search Runtime, invariant-checked full episodes, and matched modalities.
- D7: limitations and negative-result policy, after D1 and D4. SET: once gates are frozen, report each as PASS, VALID_STOP, INVALID, or ANCESTOR_STOP; show null effects, invariant failures, invalid-operation charges, and validity separately; limit conclusions to passed gates.

## Section Decisions

- D8: Introduction. SET: foreground the gap between local operational competence and full-episode structural/process competence; direct plans or local transition accuracy do not establish algorithm execution.
- D9: Related Work. SET: compare four threads: classical planning/search, neural algorithm execution, LLM/VLM planning, and runtime verification/tool use.
- D10: Search Process Policy. SET: present a formal task and interface contract before examples: Modality Observation, Typed Search Operation, Search Memory, model/runtime ownership, Algorithm Invariants, and learning objective.
- D11: Experimental Design. SET: present the staged #38 sequence: BFS sanity, IW structural gate, A* variants, modality matrix, DAgger, final primary evaluation, replication, and gated transfer. The final evaluation remains unfrozen until the preregistration prerequisites below are decided.
- D12: Results. SET: lead with gate receipts, then interpret effects only within passed scope; primary display is the structural algorithm-by-training-arm matrix with separate success, validity, invariant, and invalid-operation budget measures.
- D13: Discussion and Limitations. SET: distinguish trusted-successor structural/process competence from model-generated-successor end-to-end competence; modality and transfer claims are conditional secondary findings.
- D14: Appendix. SET: include operation schemas, invariants, runtime pseudocode, data/splits, receipt tables, statistics, adapters, and retained-infrastructure feasibility details.

## Preregistration Prerequisites

Before the planned final evaluation is called frozen, define and record:

- the arm-level data source, Search-Trace Segment construction, and per-algorithm allocation;
- compute parity, checkpoint-selection rule, and number of independent training and evaluation seeds;
- the episode-budget unit, whole-instance split procedure, and fixed Search Memory capacity;
- the estimand, uncertainty interval or statistical test, success threshold, invariant-compliance rule, and validity and invalid-operation reporting denominators for every algorithm-by-arm cell.

Until these choices are set, the paper is a result-ready empirical skeleton rather than a preregistered evaluation protocol.

## Algorithm-Specific Corpus Prerequisites

Every algorithm-specific corpus must expose a decision-sufficient Modality Observation and pass no-conflict, no-leakage, live/training-parity, and token-budget checks. These requirements qualify corpus construction and release. They do not establish policy training or efficacy.

The following is design inference, not implemented evidence. A future IW corpus should expose the novelty and pruning information required by its Algorithm Invariant. A future A* corpus should expose the frontier-order quantities required by its declared heuristic, for example `g`, `h`, and `f` under h_max or landmark-count. No IW or A* corpus currently exists, and their schemas need not be identical to the BFS corpus schema.

## Section Blueprint

- Title: "Can Vision-Language Models Learn to Execute Classical Search Algorithms?"
- Abstract: study language only. State the structural/process competence gap, the algorithm-conditioned Typed Search Operation intervention, no-repair Trusted Search Runtime, four-arm comparison, planned staged evaluation, and explicit [TODO: result] findings.
- Introduction: establish that action-level or transition-level operational competence does not establish full-episode algorithm execution. State three contributions: the Search Process Policy formulation, the no-repair runtime and planned evaluation protocol, and evidence reported only after gates run.
- Related Work: organize classical planning/search, neural algorithm execution, LLM/VLM planning, and runtime verification/tool use. Include a compact axis table covering algorithm conditioning, model-owned exploration, no-repair runtime, invariant-checked episodes, matched modalities, and transfer.
- Search Process Policy: formally define task inputs, Modality Observation, common Typed Search Operation envelope, Search Memory, Algorithm Invariants, learning objective, and model/runtime ownership. One algorithm-conditioned policy is used across named algorithms; the declared algorithm controls legality and invariants.
- Experimental Design: define the four arms (base, operational-only SFT, offline process SFT, process SFT plus DAgger), planned budgets, whole-instance splits, and the staged gate path from BFS through IW, A*, modality, DAgger, final evaluation, replication, and transfer. State the Preregistration Prerequisites before reporting final results.
- Results: present gate receipts before effects. The primary table is algorithm by training arm, with separate columns for full-episode budgeted success, operation validity, Algorithm Invariant compliance, invalid-operation rate, and charged budget; it does not combine these measures. Secondary panels cover modality, trusted-successor versus model-generated-successor results, and frozen-policy transfer only after the protocol is frozen.
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
- D15--D22 accepted on 2026-08-18: the contribution list, related-work axis table, shared policy design, four-arm control, separate primary reporting measures, frozen-policy transfer after preregistration, runtime limitation, and gate-bounded conclusion are fixed in the Section Blueprint.
- Evidence alignment was updated on 2026-08-26: commit `12031ef` supplies bounded BFS-only, text-state v6 corpus and release-qualification evidence. It does not alter the staged evaluation, paper architecture, or no-efficacy boundary.
- Author confirmation received on 2026-08-18: the Section Blueprint captures the intended manuscript. The grilling frontier is closed.
