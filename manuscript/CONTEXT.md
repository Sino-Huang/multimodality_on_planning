# Manuscript Domain Model

This manuscript-local glossary preserves the #38 canonical planning-research language while the paper's argument is decided. It does not supersede the project-wide glossary.

## Canonical Terms

**Search Process Policy**: A VLM policy trained to execute a declared search algorithm by emitting Typed Search Operations under a Trusted Search Runtime, rather than proposing a complete plan directly.

**Typed Search Operation**: A discrete, runtime-checkable search step, such as expanding a node, generating a successor, updating a frontier, or applying a goal test, issued by the policy within a declared algorithm.

**Search-Trace Segment**: A bounded, ordered slice of Typed Search Operations and state observations used as a training or evaluation unit.

**Search Episode Harness**: The evaluation seam into which a formal task, declared algorithm, Modality Observation adapter, policy adapter, and frozen budget enter, and from which one complete episode and evidence record leaves.

**Trusted Search Runtime**: The deterministic executor that applies Typed Search Operations, maintains algorithm state, and checks invariants, so the model does not own unbounded search bookkeeping.

**Search Memory**: The external runtime/data boundary that holds frontier, visited or best-depth, novelty, and landmark state for the runtime; it is not internal unbounded model state.

**Algorithm Invariant**: A deterministic property of the declared algorithm, such as BFS FIFO order, BFWS novelty/goal-count priority and duplicate handling, or additive best-first frontier order under h_add (weighted w3 or greedy), checked by the Trusted Search Runtime on every operation.

**Modality Observation**: A task state rendered in one declared modality (text, image, or paired) and presented to the policy under a fixed adapter contract.

**text-state**: The state and goal represented as a compact relational serialization.

**visual-state**: The same state and goal represented as a rendered state plus a partial-goal constraint image.

**multimodal-state**: The same state and goal represented by both text-state and visual-state.

## Model and Runtime Ownership

The policy must emit the operation type and every operand that determines exploration, including the selected source or frontier state and any successor, action, or insertion decision required by the declared operation. The Trusted Search Runtime may validate, apply, persist, and reject that emission, but it may not choose omitted operands, reorder candidates on the policy's behalf, silently repair an invalid emission, or substitute a default search decision. Replaying the raw policy emissions against the same task and prior Search Memory must reproduce the explored trace. This is the manuscript's test for attributing a search decision to the model rather than to runtime bookkeeping.

Stepwise validity and Algorithm Invariant compliance do not establish termination, completeness, optimality, or episode success. Those outcomes are reported separately under the declared task, heuristic, tie-breaking, and budget contract.

## Retained Infrastructure Terms

**Plan Submission**: Transmission of a particular supplied plan from the project adapter to a planning or rendering backend.

**Plan Interpretation**: Conversion of a submitted plan into the backend's ordered action representation.

**Action Sequence**: The canonical identity of a supplied plan as a normalized, ordered sequence of grounded action predicates; casing and whitespace are not part of its identity.

**Render Production**: Creation of a visualisation output and its rendered image for a planning state.

**Render Validation**: Confirmation that a produced visualisation and image satisfy declared structural and semantic checks.

**Plan Provenance**: Evidence that links a produced visualisation to the exact supplied plan that the backend interpreted.

**Integration Certification**: The complete finding that Plan Submission, Plan Interpretation, Plan Provenance, Render Production, Render Validation, and required execution-isolation checks all passed.

**Attempt**: One authorized, immutable execution with its own identity and retained outcome, whether successful or unsuccessful.

**Evidence Bundle**: The self-contained records from an Attempt that allow an independent reproducer to verify its claims offline.

## Historical CGAS Terms

Planning Certificate, Joint Action-and-Certificate SFT, Adaptive Scaffolding, Support Route, Live Memory, Verified Joint Step, and Route Label are historical CGAS terms. They may describe retained infrastructure but cannot support a current Search Process Policy efficacy claim.

## Claim Status Terms

**Demonstrated infrastructure finding**: A claim supported by committed code, focused verification, and retained Evidence Bundles. It is not an efficacy finding.

**Planned method component**: A specified mechanism without training or evaluation evidence. It must be described as proposed, not as an established result.

**Bounded empirical finding**: A comparative model result supported within one governed development panel but not licensed as a final or general efficacy conclusion. Issue #54's outcome-blind 15-task BFS v8 panel is the current example: process SFT achieved 1.0 invariant-valid success with zero invalid operations, the base model achieved 0.0, and random-valid also achieved 1.0. The zero gain over the best control produced `VALID_STOP` with `scientific_completion=false`. Further examples: the 2026-09 expanded matched baseline (issue #118: process SFT 125/288 versus random-valid 240/288, successes only in additive best-first cells), the reduced-scope v2 branches (issues #123/#124), and the bounded descriptive observation-corruption channel finding (issue #126), which is a contract-bound channel-reliance result, not an efficacy finding.

**Choice-quality claim (redesigned choice-frontier arm)**: Permitted only as a development-stage choice-quality claim, relative to uniform choice (random-valid) and the pre-registered exact-ε selector ladder, on three panels (the issue #135 validation panel, the fresh held-out panel P2, and the unscreened panel P2u) with 3 training seeds. No planning-ability or generality claim. "Held-out" means the fresh P2 panel only; the frozen 45-task final evaluation is unexecuted (the prose never calls it "held-out", so the word has one referent). P2 uses the #135 controls-only screen; only P2u is unscreened. The screen admits tasks on which near-uniform choice sometimes succeeds; the P2u result is descriptive evidence that the gain survives without it, not evidence about where choice discriminates. The ladder rungs read the privileged heap head, so the ladder validates the ordering of the measurement, not any realisable policy. Ladder position is always reported for all three results together (not separated from the exact-ε 0.75 rung on #135, interval-separated above it on P2, not separated on P2u or pooled), never for P2 alone. No equivalence margin was pre-registered for the separation S, so a non-separated S is never written as "at the rung". The #140 DAgger round is single-seed and inconclusive. This entry replaces the round-4 single-seed, one-panel entry (author decisions, 2026-09-25), which itself replaced the earlier rule that no choice-quality claim is made for the redesigned arm.

**External audit claim**: The complete-set identity failure (48/48) is shown only on this project's runtime. On ScienceWorld (#137) random-valid registers choice. On LLM-First Search (#142, local Qwen3-30B-A3B substitute for GPT-4o, 80 tasks from four configurations) every decision diverges, and random-valid success saturates under the paper's token budget by construction: the frontier keeps every alternative, so a zero-token chooser is a complete randomized search, and the pre-audit probe already won 100/100. It is reported as a by-construction demonstration of why a success budget must bind decisions (the compute-matched-baseline principle), not as a tested failure mode, and never as "a failure the per-decision audit does not detect". Counted in expansions, random-valid is reported by its stored budget curve (0.0775 at 1x to 0.19 at 2x the reference's expansions), and the reference's matched-budget success equals its token-budget success by construction. The paper may not generalise this to agent benchmarks at large or claim the published GPT-4o results are invalid (LLM-First Search reports no random-valid control). The second realisable policy (#141) is the zero-shot base model, prompted with the JSON format and a goal-similarity instruction; equivalence to uniform choice is claimed only on the validation panel (development-stage verdict), and P2 (confirmatory) is inconclusive (author decisions, 2026-09-25).

**Final empirical efficacy finding**: A comparative result from the authorized final primary evaluation. None exists in the current evidence base.

**Claim boundary**: The narrowest statement directly supported by the available evidence. The manuscript must preserve this boundary.

## Prose Names (author decision 2026-09-25)

Prose only. Labels, citation keys, table headers, figure text, and JSON keys are unchanged.

| Object | Prose name | Retired prose variants | Symbol use |
|---|---|---|---|
| Panel P2 (#139, 11 tasks) | the held-out panel | P2 in prose | P2 only in tables, figures, and the first defining clause |
| Panel P2u (#139, 12 tasks) | the unscreened panel | P2u in prose | P2u only in tables, figures, and the first defining clause |
| #135 12-task panel | the validation panel | #135 panel | none |
| Frozen 45-task manifest | the frozen 45-task final evaluation (unexecuted) | held-out final evaluation, held-out manifest | none |
| Per-decision comparison of random-valid with the exact reference | the identity audit | identity check, identity gate, per-pair identity audit | none |
| Declared algorithm run exactly | the exact reference | exact-classical, exact teacher | ScienceWorld keeps its own "gold trajectory" |
| Control under the enumeration contract | random-valid, glossed once as uniform over valid operations | none | none |
| Control under the choice-frontier contract | random-valid, glossed once as uniform over the offered frontier | uniform menu choice, uniform frontier choice | none |
| Contract where each expansion submits its complete candidate set | the enumeration contract | complete-set submission contract | "the 48/48 identity failure" or "the enumeration-contract identity failure" may replace "complete-set identity failure" |
| Area under the solve-versus-budget curve | M1, defined once in words | none | formulas, tables, headline sentences |
| Adapter minus random-valid M1, three-seed mean | D3, defined once in words | none | formulas, tables, headline sentences |
| Adapter minus the exact-ε 0.75 rung | the adapter's difference from the 0.75 rung | S in prose | S only in tables |
| Trained choice-frontier adapter (#136/#138) | the adapter | scaled adapter | the earlier small-corpus adapter is "the first adapter", named once in Results |
| Ladder rungs' information | privileged: the rungs read the reference's own priority order, which no policy sees | none | none |
| Development-stage | measured on development panels, not on the frozen final evaluation | none | none |

Body retirements: M2, M3, M4, C*, CHOICE_SENSITIVE, and ZERO_DECISION_HEADROOM leave the body (appendix only). BFWS and SFT are expanded once, and VALID_STOP is glossed once or leaves the body.

Caveat placement: each repeated caveat (claim frame, privileged rungs, 45-task final evaluation unexecuted, held-out definition) is stated in full once in the abstract, once at its result, and once in the Limitations or Conclusion, and elsewhere as a short clause. No caveat is deleted outright.

## Framing (author decision 2026-09-25)

**Title**: "Can Vision-Language Models Learn to Execute Classical Search Algorithms?" (registered on OpenReview). The abstract, Discussion, and Conclusion answer the title question at development stage, scoped as follows: under the validated measurement, a trained, scene-only VLM adapter learns to choose which frontier state to expand in greedy best-first search and weighted A* (the only choice-frontier algorithms) better than random-valid on three development panels, without approaching the reference. Under the enumeration contract no BFS or BFWS cell shows learned success. No planning-ability or generality claim.

**Primary contribution (validate-before-score measurement)**: An interface is admitted only after the identity audit finds divergent decisions and a decision-counted budget binds them (the compute-matched-baseline principle, Li & Talwalkar). M1 then passes a pre-registered exact-ε ladder on the validation and held-out panels before any policy is scored. The rungs are privileged, so the ladder validates the measurement, not a policy. The adapter is a worked use of the measurement. The budget check is never listed as a contribution of this paper.

**Box 1 (the procedure)**: The protocol box at the end of Section 4. Prose name "Box 1" or "the procedure in Box 1". It uses only thresholds and outcomes already rendered, each with a copied evidence comment.

**Identity-audit framing**: The 48/48 follows from the executed serial rule, which the contract specification does not reveal. The per-decision audit (or a reading of the executed controller) finds it, and the Counterfactual appendix confirms it by re-running the audit under both tie orders ("confirms", not "predicted"). Success saturation alone cannot find it, because random-valid also saturated the BFS development panel whose expanded-baseline decisions diverge. The 48/48 is shown only on our runtime. Box 1 step 1 reports the divergent fraction and the first-divergence index, and success reads as choice only if random-valid's success also falls below the reference's.

**External audits**: ScienceWorld is "a positive control" for the identity audit. LLM-First Search is "a by-construction illustration" of the budget check. Neither is described as testing "each check".

**Ladder license**: A higher M1 reads as choice closer to the reference's along the ladder's ε axis only. The ladder does not validate M1 off that axis: a privileged selector that reaches the goal in fewer decisions scores above the reference. The trained adapter is read as beating random-valid in M1, with no closeness gloss. The reference's M1 of 0.875 is fixed by construction (goal selection is the (R+1)-th decision).

**Observation scope**: The choice-frontier observation is scene-only, and no modality is compared under that contract. The text, visual, and multimodal matrix belongs to the enumeration contract.

## Visual Evidence Conventions (#145)

Figures use manuscript-local reproducible Python scripts, a shared arm palette, editable PDF/SVG and final-size PNG previews. Every plotted number is read from a pinned JSON/CSV and checked against its printed value at three decimals using Decimal half-up rounding; every new printed number has an adjacent `% Evidence:` comment in the TeX source. Tables use booktabs rules, a `mygray` bold header and symbol verdicts rather than prose cells. Development-stage and descriptive labels remain attached to their respective results. The exact-$\epsilon$ rungs use privileged priority information and validate the measurement, not a policy.

Qualitative examples are illustrative, not new efficacy claims. Selection rules must be frozen in the figure script before candidate episodes are viewed; the returned task is used regardless of whether it matches an expected example. Captions give the interpretation, while the appendix and source evidence comments record image resolutions and selection provenance. Filmstrips show unaltered policy-visible cached PNGs or re-renders of their VFGs. A larger label-free VFG re-render is permitted only after its original-resolution pixels match the cached policy scene. If a VFG re-render differs (as with embedded 15-puzzle tile glyphs), use the unchanged cached PNG instead and describe the discrepancy. State content is never retouched or composited.
