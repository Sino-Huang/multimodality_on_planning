# Content Brief

## Progress
- Manuscript genre and central contribution: DRAFTED
- GitHub issue audit: ALIGNED on 2026-08-31 after direct inspection of all 58 issues and 118 comments from #54 through #111.
- Manuscript design artifacts and local domain model: REVISED to the current BFS/BFWS evidence and model/runtime ownership boundary.
- Title and abstract: REVISED (bounded BFS result version)
- Introduction: REVISED (prior-work motivation cited; four-thread literature placeholders remain)
- Related Work: NOT STARTED
- Method and evidence contract: NOT STARTED
- Evaluation protocol or results: NOT STARTED
- Limitations and conclusion: NOT STARTED
- Appendix: NOT STARTED

## Section Summary
- The issue audit found seven closed tickets in the range: #54--#58, #110, and #111. Issue #59 and #60--#109 remain open.
- Issue #111 released the observable BFS v6 text-state corpus: 90 trusted/replay traces and 25,109 process rows (12,994 train; 12,115 dev). Inputs expose canonical task context, exact grounded successor candidates, and full visited membership. The release records zero semantic/input/input-target overlap, conflicting identical-input labels, teacher-operation rejection, and live/corpus mismatch under 8,192 total tokens and a 384-token output allowance.
- Issue #54 is closed with a governed v8 `VALID_STOP`. On a frozen outcome-blind 15-task BFS development panel (11 easy, three medium, one hard), final checkpoints from five process-SFT training seeds achieved 1.0 invariant-valid success and 0.0 invalid-operation rate. The base achieved 0.0; random-valid achieved 1.0. The learned policy therefore demonstrated executable BFS behavior on the selected panel but zero gain over the strongest control. `scientific_completion=false`, and the result is not a final efficacy finding.
- Issue #55 replaced capped IW as the active structural gate after IW(1), IW(2), and IW(3) proved not corpus-complete. The successor is the complete unpruned `full_bfws_goal_count` BFWS variant.
- Issues #56--#58 froze a 105-task BFWS development panel and inaccessible fresh 45-task held-out manifest, released exact replay-verified traces for 69,019 decisions, and released 69,019 process records plus 67,215 operational records. The process projection contains 47,780 train and 21,239 dev rows, with all recorded overlap, mismatch, rejection, token, and held-out-access counters at zero.
- Issue #59 remains open. Its runner and governance contract exist, but the actual BFWS training, rollout, replay, and structural-gate adjudication are incomplete. Future model/cell configurations are limited to one training run at seed 17; repeated rollout/reference seeds do not estimate training-seed variance.
- A* adapters and corpora, visual-state and multimodal-state corpora, DAgger, model-generated successors, final primary evaluation, replication, and transfer remain open under #60--#109. No final comparative efficacy finding or scientific completion exists.
- Issue #110 provides deterministic compact delta/event episode evidence with semantic replay while preserving search semantics.
- The Search Process Policy ownership contract now requires the model emission to include every exploration-determining operand. The Trusted Search Runtime may validate, apply, persist, and reject the emission, but may not choose omitted operands, reorder candidates for the policy, repair invalid outputs, or inject default search decisions. Raw emissions plus the same task and prior Search Memory must replay to the same explored trace.
- Stepwise validity and Algorithm Invariant compliance are explicitly separate from termination, completeness, optimality, episode success, and learned advantage.
- The active checkpoint conditions are pretrained base, process SFT, and process SFT plus DAgger, with random-valid and exact-classical references. Operational-only SFT is not authorized.
- The working title is "Can Vision-Language Models Learn to Execute Classical Search Algorithms?" It poses the empirical question without asserting a result.
- The revised abstract reports the bounded BFS v8 result and its random-valid ceiling, then identifies BFWS traces/corpus as completed infrastructure and A*, modalities, DAgger, and final evaluation as prospective.
- The paper architecture is Abstract; Introduction; Related Work; Search Process Policy; Experimental Design; Results; Discussion and Limitations; Conclusion; Appendix. The Appendix is mandatory and carries the full evidence contract.
- The revised Introduction now opens from symbolic planning as a controlled probe of model reasoning and explicitly positions this paper as a training-based extension of arXiv:2607.11197. It summarizes the prior observational separation between operational reasoning and structural enumeration, while limiting that evidence to item-level, text-only, off-the-shelf models.
- The first three Introduction paragraphs now cite the prior study directly and use Valmeekam et al. (2023) as the external methodological anchor for symbolic planning as a formally specified, mechanically verifiable reasoning probe.
- The Introduction treats structural enumeration as closely tied to global search-space reasoning rather than equivalent to complete search capability. It motivates the present intervention as a test of whether direct training on declared search algorithms can produce model-attributable structural/process competence beyond valid but uninformed exploration.
- The Introduction retains the distinction between local validity and algorithmic correctness, the replay-determinative model/runtime ownership boundary, the bounded negative comparative BFS result, the IW-to-BFWS migration, and the three bounded contributions.
- Every Introduction paragraph now has a non-rendered LaTeX `% Paragraph purpose:` comment that records its role in the argument, from motivation and prior-work diagnosis through evidence boundaries.
- Historical critic-6 was correct that the previous draft failed to define model/runtime ownership and conflated stepwise checking with correctness. Those prose defects have been revised. Its premise that no governed model result existed is now superseded by the issue #54 v8 outcome. The historical critic file remains unchanged; a new review is required.

## Open Items
- [TODO: BFWS result] Complete issue #59's single-training-seed BFWS experiment and structural-gate adjudication. Existing traces, corpora, runners, and dry-runs are not a model result.
- [TODO: A*] Complete #60--#67: h_max and landmark-count adapters, paired traces/corpora, training, development cells, and curriculum comparison.
- [TODO: modality] Complete #68--#77 before claiming modality parity or effects. Matched projections must expose the same authoritative task/candidate facts and Search Memory capacity; rendering and training-allocation estimands must be frozen.
- [TODO: later gates] DAgger (#78--#84), model-generated successors (#85--#89), final evaluation (#90--#100 and #109), replication (#101--#103), and transfer (#104--#108) remain open.
- [TODO: protocol] Before final evaluation is called frozen, specify condition-level data and Search-Trace Segment construction, compute parity, checkpoint selection, one-training-seed limitations, rollout/reference seeds, per-algorithm allocation, episode-budget units, whole-instance splits, estimands, uncertainty, and gate thresholds.
- [TODO: A* corpus contract] Future A* inputs must expose exact frontier order, reopen/best-cost policy, heuristic and landmark progression, tie-breaking, and termination facts. Serializing only `g`, `h`, and `f` is insufficient.
- [TODO: evidence] Restore full test collection (#41); it remains blocked by 13 documented historical phase-3 import errors. Preserve the local-supplied-plan and no-hosted-solver boundary for retained rendering evidence.
- [TODO: cite] Bound and substantiate the scoped comparison against search-learning, neural algorithm execution, planning, and runtime-verification literature. Do not assert a priority claim without support.
- [TODO: citation/gap-check] The Introduction's four-thread positioning (classical planning/search, neural algorithm execution, LLM/VLM planning, runtime-constrained execution) uses literal `[TODO: cite]` placeholders. A later pass must convert these into real citations and verify the gap framing and scoped novelty claim against the cited work before any priority assertion.
- [RESOLVED: cite prior work] Added verified bibliography entries for arXiv:2607.11197 and Valmeekam et al. (2023), and cited them in the first three Introduction paragraphs. The prose preserves the distinction between observational, item-level structural enumeration and this paper's training-based, full-episode hypothesis.
- [TODO: project glossary] The project-wide `CONTEXT.md` outside `manuscript/` still names IW novelty pruning as the structural example. This writing session is not permitted to edit it. A separately authorized governance update should align it to the issue #55 BFWS successor while preserving the historical IW qualification record.
- [RESOLVED: training conditions] The issue audit resolves the former four-arm discrepancy: operational-only SFT is not authorized. The active checkpoint conditions are base, process SFT, and process SFT plus DAgger, with random-valid and exact-classical references.
- [RESOLVED: critic-6 ownership] The abstract, Introduction, local domain model, and design tree now define explicit exploration operands, prohibit runtime-selected defaults, require replay-determinative emissions, and distinguish stepwise validity from algorithmic correctness.

## Next
- The motivation-revised manuscript compiled successfully on 2026-09-04 with `manuscript/build_pdf.sh`; the PDF is three pages and contains no LaTeX errors. Review whether the prior-work diagnosis, training-intervention gap, and distinction between structural enumeration and complete search capability are clear and defensible.
- The next writing session should choose between addressing the newest critic's CRITICAL issues and moving to Related Work. A Results section may report the bounded BFS v8 panel and BFWS trace/corpus receipts, but it must not imply BFWS efficacy, final evaluation, modality effects, or scientific completion.
