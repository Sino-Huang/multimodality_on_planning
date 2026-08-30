# Content Brief

## Progress
- Manuscript genre and central contribution: DRAFTED
- Fetched-main implementation evidence from `origin/main` at `12031ef` is ALIGNED. The v6 BFS-only, text-state process corpus is corpus and release-qualification evidence, not an efficacy finding.
- Manuscript design artifacts: ALIGNED. The stale-tree critic item is resolved.
- Title and abstract: DRAFTED (temporary/OpenReview registration version)
- Introduction and related work: NOT STARTED
- Method and evidence contract: NOT STARTED
- Evaluation protocol or results: NOT STARTED
- Limitations and conclusion: NOT STARTED
- Appendix: NOT STARTED

## Section Summary
- The title and temporary abstract have been drafted. The rest of `manuscript/iclr2026/iclr2026_conference.tex` remains the ICLR template shell, and no results prose has been drafted.
- The current research direction is the #38 Search Process Policy specification: a VLM intended to emit Typed Search Operations under a Trusted Search Runtime across matched text-state, visual-state, and multimodal-state observations.
- Demonstrated evidence includes reusable historical planning, modality, and rendering infrastructure, including Integration Certification on declared 4-, 8-, and 12-object smoke Attempts, and the bounded v6 pilot in fetched `origin/main` at `12031ef`. Neither is a Search Process Policy efficacy finding.
- Fetched `origin/main` at `12031ef` contains a bounded BFS-only, text-state v6 pilot with an observable Search Memory interface, a Search Episode Harness, Typed Search Operations, trusted/replay traces, and a released process-SFT corpus. The corpus has 90 trusted/replay traces and 25,109 process rows, split into 12,994 train rows and 12,115 dev rows.
- Its decision-sufficient observations contain task context, grounded successor candidates, and exact visited status. Release qualification records zero train/dev input overlap, input-target overlap, semantic-task overlap, conflicting identical-input labels, live/training mismatch, and teacher-operation rejection. The release allows 8,192 context tokens and 384 output tokens. These are corpus and release-qualification checks, not policy-efficacy results.
- Issue #54 has corpus-release qualification `PASS` and `scientific_completion=false`, but remains open/reopened. No clean governed SFT result exists. The current attempt cannot be retained because metadata records `accepted_delta_limit` 21 against the frozen limit of 16. The reported corrected 16-delta regeneration is byte-identical for the learning payload and changes metadata and audit records only, so the defect does not imply changed examples.
- The current v6 BFS process corpus is distinct from the historical 411-example CGAS corpus recorded in `manuscript/supervisor_brief.md`. That historical corpus does not supply current Search Process Policy training or efficacy evidence.
- The v6 process-SFT corpus does not establish a trained Search Process Policy, checkpoint, calibration, IW or A* corpus, multimodal corpus, comparative efficacy result, or scientific completion.
- #39 terminology ratification and #40 bounded pytest discovery are not the full account of completed work. Fetched `origin/main` at `12031ef` supplies bounded BFS pilot artifacts. The remaining gated work, including IW, A*, the modality matrix, DAgger, final comparative evaluation, replication, and transfer, has no governing evidence of completion.
- No final comparative efficacy finding exists.
- The planned empirical manuscript asks whether a VLM can learn model-owned Typed Search Operations for declared classical algorithms under a no-repair Trusted Search Runtime; operational controls and modality conditions are secondary, and transfer is gated.
- The working title is "Can Vision-Language Models Learn to Execute Classical Search Algorithms?" It poses the empirical question without asserting a result.
- The temporary abstract defines a Search Process Policy that emits Typed Search Operations from text, visual, or multimodal state observations under a Trusted Search Runtime.
- It describes a planned BFS, IW, and A* evaluation that separates local operational competence from full-episode structural/process competence and reports success, validity, invariant compliance, and invalid-operation charges separately.
- It presents matched text-state, visual-state, and multimodal-state conditions and four planned training conditions. Comparative experiments remain ongoing.
- The paper architecture is Abstract; Introduction; Related Work; Search Process Policy; Experimental Design; Results; Discussion and Limitations; Conclusion; Appendix. The Appendix is mandatory and carries the full evidence contract.
- The settled section blueprint: structural/process gap in the Introduction; four-thread related-work map and axis table; one algorithm-conditioned typed policy; four-arm staged evaluation; receipt-first results; runtime-boundary discussion; and a gate-bounded conclusion. Full-episode budgeted success is reported separately from operation validity, invariant compliance, and invalid-operation budget charges.

## Open Items
- [TODO: protocol] Before any final evaluation is called frozen, specify the arm-level data and Search-Trace Segment construction contract, compute parity, checkpoint selection rule, seed count, per-algorithm allocation, episode-budget unit, whole-instance split procedure, estimands, uncertainty, and gate thresholds.
- [TODO: corpus protocol] Every algorithm-specific corpus must expose a decision-sufficient Modality Observation and pass no-conflict, no-leakage, live/training-parity, and token-budget checks. This is a protocol requirement, not an efficacy result. The following is design inference, not implemented evidence. Future IW corpus work should expose novelty and pruning information required by its Algorithm Invariant. Future A* corpus work should expose the frontier-order quantities required by its declared heuristic, for example `g`, `h`, and `f` under h_max or landmark-count. No IW or A* corpus now exists, and these schemas need not be identical.
- [TODO: result] Run and evaluate a governed SFT attempt and evaluation for the bounded BFS-only, text-state v6 pilot in fetched `origin/main` at `12031ef`. Corpus-release qualification does not substitute for that work. Complete the separately gated IW/A* work, modality matrix, DAgger, final evaluation, replication, and transfer under #41--#108.
- [TODO: abstract] Revise the temporary abstract after governed results are available. Replace its ongoing-evaluation sentence with findings bounded to the retained results.
- [TODO: evidence] Restore full test collection (#41); it remains blocked by 13 documented historical phase-3 import errors. Preserve the local-supplied-plan and no-hosted-solver boundary for retained rendering evidence.
- [TODO: cite] Bound and substantiate the scoped comparison against search-learning, neural algorithm execution, planning, and runtime-verification literature. Do not assert a priority claim without support.
- [RESOLVED: critic] `manuscript/critics/2026-08-25-critic-3.md` identified the stale-tree contradiction. `writing_design_tree.md` now records the bounded BFS-only, text-state v6 evidence at `12031ef` while retaining the no-efficacy boundary.

## Next
- Unless explicitly overridden, the next session must first address critic-4's MAJOR issues before drafting the Introduction or Related Work. Treat fetched `origin/main` at `12031ef` as corpus and release-qualification evidence for the bounded BFS-only, text-state v6 pilot, not as a trained policy or efficacy result. Before drafting a Results section or claiming a frozen evaluation, complete the protocol prerequisites and obtain a retainable governed SFT outcome. Do not present [TODO: result] placeholders as findings.
