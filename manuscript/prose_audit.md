# Paragraph-level prose audit (2026-09-25)

One entry per paragraph or caption, in document order: what the paragraph is for (Point), why the previous wording fell short of expert style (Diagnosis), and what changed, including where any number removed from prose now lives (Action).


## Prose audit: AbstractIntro (abstract, Figure 1 caption, Introduction)

Files: `iclr2026/iclr2026_conference_abstract.tex` (teaser caption + abstract), `iclr2026/iclr2026_conference_introduction.tex`.

### Figure 1 caption — Search success measures a model's choices
Point: Task success reflects a model's choices only when those choices change the search. Panel (a) shows the case where they don't, panel (b) the case where they do.
Diagnosis: The takeaway came first, but (b) had three sentences: a generic sentence, a scene sentence, and a sentence scoped to the validation panel. It ran to 71 tokens, too long for the ≤200 file budget.
Action: Kept the bold takeaway, shortened. (a) keeps the additive-task scope and the random-valid gloss. (b) is one sentence: the two diverge, and a trained adapter scores between them. The illustrative blocksworld step stays as a parenthetical. The caption contains no numbers (48/48 and 18/18 are printed inside the figure), and the evidence comments are unchanged. 71 → 44 tokens.

### Abstract ¶1 — Can vision-language models learn to execute
Point: The question needs success that tracks choice. On our enumeration runtime it does not. So we validate the measure before scoring any policy, and the validation passes.
Diagnosis: The claim chain was there, but the paragraph opened with a spec-like sentence ("A policy can emit valid operations without controlling search: …"). It then stacked three sentences of mechanism detail.
Action: Now question → requirement → failure on our runtime (48 kept as the headline number) → where process supervision succeeds (additive pairs only, never breadth-first or width-based, scoped to "our baseline") → validate before score → choice-frontier admission (diverges, budget counts decisions) → ladder with privileged controls, which validates the measure, not a policy. The fresh held-out panel is named. Nothing was moved out of this paragraph. The BFS/BFWS negative moved from ¶2 into this paragraph, with its evidence comment.

### Abstract ¶2 — A trained scene-only adapter beats
Point: The bounded answer is that the trained adapter beats random-valid in greedy best-first and weighted A* without approaching the reference. The work is development-stage and the final evaluation is unexecuted.
Diagnosis: The paragraph carried an interval in prose, a panel size ("The held-out panel has 11 tasks"), and a separate BFS/BFWS sentence.
Action: The paragraph keeps one headline number, $+0.285$, glossed as a "validation gain … in solve-versus-budget area". The interval [+0.140, +0.433] is still in Table tab:results-panels and the Conclusion. The 11-task size is still in Table tab:results-panels and fig:ladder. "without approaching the reference" is restored (the CONTEXT answer wording). The boundary sentence keeps the development-stage frame, the no-general-planning-ability claim, and the unexecuted frozen 45-task final evaluation. Moved-number notes were added next to the evidence comments.

### Introduction ¶1 — Can a vision-language model learn
Point: The title question is a measurement problem. This paragraph sets up the policy, runtime, algorithms, both contracts, and random-valid.
Diagnosis: It was a setup list with no stated claim. The contracts were unnamed ("one of two decision contracts … the first … the second"), and additive best-first had a nested gloss ("which is best-first search ordered by …").
Action: Opens with the question, then the requirement (success must respond to choices, Figure 1). The contracts are named with their observations. The algorithm gloss is simplified. The random-valid gloss is kept. No numbers.

### Introduction ¶2 — Random-valid can make every decision
Point: Success reflects choice only when random-valid decides differently from the exact reference. Under the enumeration contract it doesn't, so SFT's successes are gains in validity.
Diagnosis: A fact chain with 48/48, 125/288, 0/24, +0.875 at two of three, and −0.125. The numbers carried the argument instead of the prose.
Action: Topic sentence states the condition. Mechanism: the complete candidate set leads to identity on 48/48 pairs (the only number kept). Evidence: every SFT success falls in these cells and none in BFS or BFWS. 125/288 and 0/24 are still in Table tab:results-identity. Implication sentence: "SFT's gains here are gains in validity". The replication cell is stated without numbers; +0.875 and −0.125 are still in Table tab:appendix-seeds, and the "descriptive, with no pre-registered rule" gloss is kept.

### Introduction ¶3 — The identity is a property
Point: The identity is hard to see because it comes from an executed tie-break rule, not the contract specification, and success saturation cannot detect it.
Diagnosis: The ledger listed 19/48, >24/48, 15/24 against 24/24, and a stacked pointer ("Counterfactual appendix, Appendix~\ref{…}").
Action: Claim → cause (sorted tie-break) → the audit confirms the cause, since 19/48 diverge under submission order (the only number kept), with the failed pre-registered majority prediction kept as a clause → saturation cannot detect it (the BFS development panel saturated even though decisions diverge). The >24/48 threshold is still in Results 5.2. 15/24 against 24/24 is still in Table tab:results-identity. Pointers are now plain `Appendix~\ref{app:results-counterfactual}`.

### Introduction ¶4 — We therefore validate the measurement
Point: Our approach is to validate the measurement before scoring any policy. Admit the choice-frontier contract with the identity audit and a decision-counted budget, then require M1 to pass the privileged ladder.
Diagnosis: The claim was buried in a long first clause. It had "12 fresh tasks from 7 domains" and a trailing clause ("and Box~… states the procedure"). The reason the ladder validates M1 was missing.
Action: Topic sentence first. 18/18 kept as the admission receipt. M1 is defined in words. A new explanatory clause says why the ladder tests the measure: each rung replaces a fraction ε of reference decisions, so a valid M1 must order the rungs by ε (Box 1 step 3 content). The pass is stated on both panels. The privileged-rung caveat is kept as a short causal sentence with the Box pointer. "12 tasks from 7 domains" is still in Section 4 (sec:design), with the comment updated. "runtime-owned" was dropped. RelatedPolicy was told the definitions it relies on remain.

### Introduction ¶5 — The validated measurement scores the
Point: Under the validated measurement the trained adapter beats random-valid, two other policies score at the random-valid level, and two limits bound the gain.
Diagnosis: A number dump: +0.285 [interval], +0.416 [interval], 4 of 12, "frozen before any evaluation episode" (process history), and "every seed positive".
Action: Topic sentence → D3 defined in words, with the two point estimates → "both intervals exclude zero" (Table tab:results-panels). The unscreened result is labelled descriptive: it "rests on a minority of them", and 4 of 12 is still in the Table tab:results-panels sign column and the Discussion Limitations. The zero-shot base (development stage) and earlier adapter (descriptive) are framed "by contrast". Limit sentence: separated above the 0.75 rung only on the held-out panel, and trained only by imitation. Intervals and per-seed values are in tab:results-panels and tab:appendix-seed-d. "Frozen before any evaluation episode" is dropped here because the held-out definition closes the Introduction.

### Introduction ¶6 — Steps 1 and 2 of
Point: The first two steps of Box 1 run on published interfaces. ScienceWorld is a positive control and LLM-First Search a by-construction illustration of the budget step, and the 48/48 failure is shown only on our runtime.
Diagnosis: Two receipts (0.915 and 0.0775) sat in a sequence of one-fact sentences, and the runtime-only bound interrupted the LLM-First Search pair.
Action: Numbers replaced by their meaning ("never succeeds, while the reference usually does"; "rarely within the reference's expansion count"). 0.915 is still in Results 5.5 and the ScienceWorld appendix. 0.0775 is still in Table tab:appendix-lfs and the LLM-First Search appendix prose. The LLM-First Search sentence now gives the reason: random-valid spends no tokens. The runtime-only bound moved to the end of the paragraph, with its evidence comment.

### Introduction ¶7 — This paper makes three contributions
Point: There are three contributions, with the validate-before-score measurement first.
Diagnosis: Each bullet was a fully bold sentence, and C3 was 50+ words.
Action: Each bullet is now a bold lead phrase plus one plain sentence. C1 keeps the Li and Talwalkar credit. C3 keeps its separate credit (a logged double-credit decision, held). C3 drops "the zero-shot base and an earlier small-corpus adapter at its level", which ¶5 states with its status labels.

### Introduction ¶8 — Every claim is development-stage
Point: The evidence boundary.
Diagnosis: "11-task", "seeds 17/29/71", and "descriptive $n{=}3$" were spec detail inside a caveat paragraph.
Action: Kept all four caveats (development-stage with the unexecuted 45-task final evaluation, the held-out definition, the single-seed scope, and no planning-ability or generality claim). Seeds are still in the seed-replication appendix and tab:appendix-seeds. 11 tasks is still in tab:results-panels and fig:ladder.

### Word counts (non-comment, `sed -E 's/(^|[^\\])%.*$/\1/' FILE | wc -w` rule)
No shell was available in this slice, so the "after" counts are manual whitespace-token counts under the same rule. The integrator should confirm them with `wc`.
- `iclr2026_conference_abstract.tex` (teaser block + abstract): 236 before (brief) → about 199 after. The caption went from about 71 to 44 tokens and the abstract body from about 165 to about 147.
- `iclr2026_conference_introduction.tex`: 885 before (brief) → about 776 after.

### Cross-file notes (not fixed)
- `iclr2026_conference_abstract.tex` comment L29–30 says 0.915, 0.0775, and "4 of 12" are kept in the Introduction. They are no longer there. A new comment L31 records where they live now.
- The Introduction no longer defines "task-algorithm-observation entries" or the 24-task panel size of the expanded baseline. Results/Design should define "expanded baseline" at first body use if a reader needs it. Results 5.2 already gives 125/288.
Discussion ¶1 still gives 48/48 and 19/48 in full. That is fine, but it is now the main-text place, besides Results, that states 19/48 with its tie-break framing.
- In `iclr2026_conference_experimental_design.tex`, the seeds 17/29/71 appear to have left the visible Section 4 text. The only visible home found is the seed-replication appendix (L1807 "seeds 17, 29, and 71") and Table tab:appendix-seeds (seed column). My moved-number comment points there.
- The abstract says "process supervision succeeds only there, never under breadth-first or width-based search", scoped by "In our baseline". The BFWS structural-gate development panel (0.933 against 0.467, Results 5.2, Table tab:results-bfws) is a separate earlier panel, so it does not contradict this, but the scope rests on "our baseline" meaning the expanded baseline.

## Prose audit: RelatedPolicy slice

Files: `iclr2026/iclr2026_conference_related_work.tex` (Section 2), `iclr2026/iclr2026_conference_search_process_policy.tex` (Section 3, including the Figure~\ref{fig:contracts} caption).

### Section 2 (Related Work)

### Related Work ¶1: "We evaluate how a model executes..."
Point: We score how a model executes a declared search algorithm, not the plan it returns. Planning benchmarks and trace-trained or step-imitating models do not type or validate steps. Two of our components have direct precedents.
Diagnosis: The claim came first, but the rest of the paragraph listed citations with glosses. The choice-frontier gloss repeated the Introduction's definition (Introduction L53, which comes before Related Work). "Likewise lack" had no clear antecedent.
Action: The opening is now "how a model executes … rather than the plan it returns". "come closer but lack" links trace-trained models to our position. The two precedent clauses are joined into one sentence, and the choice-frontier gloss is removed because the Introduction defines the contract first. All 13 keys are kept. No numbers.

### Related Work ¶2: "Our model issues every exploration-determining operation..."
Point: Our model issues every operation that determines exploration, and a runtime that never repairs checks each one against the algorithm's invariants. Model-in-the-loop search, step supervision, visual reasoning, repair loops, and constrained decoding give one or both of these to something else.
Diagnosis: The ownership contrast came first, but the no-repair contrast came last and was folded into the repair-loop list. The paragraph read as three unrelated lists.
Action: The paragraph now opens with a topic sentence that states both differences. The following sentences name who owns exploration (Tree of Thoughts, RAP), who leaves steps unchecked (scratchpads, Visual Sketchpad, MVoT), process supervision, and repair loops and constrained decoding. The process-supervision sentence moved here from ¶3 because it concerns whether choices are identifiable. The duplicate `lightman2023lets` citation in the old list is merged into that sentence, so the key is cited once. "(MVoT)" is dropped because the acronym is never used again. "(RAP)" is kept because the survey table in the appendix uses it. All keys are kept. No numbers.

### Related Work ¶3: "Evaluation-validity and shortcut studies locate..."
Point: Evaluation-validity and shortcut studies place the confound in the model or the data. Ours is in the runtime, and our label permutation is the standard mitigation, not a contribution.
Diagnosis: This was a citation ledger of four sentences, each "X documents Y". An unrelated process-supervision sentence was attached at the end.
Action: The three shortcut findings (language priors, answer and label position, and cues missing from the reasoning trace) are merged into one sentence with parallel clauses, each keeping its own citation. "(VQA)" and "(LVLM)" are dropped because they are never used again. The label permutation is stated in one sentence as the standard mitigation. The process-supervision sentence moved to ¶2. All keys are kept. No numbers.

### Related Work ¶4: "Jericho and the Contextual Action Language..."
Point: The valid-action handicap is already known. Our contribution is a per-decision identity audit on a search runtime, and ScienceWorld serves as its positive control.
Diagnosis: The old ¶4 mixed three lines of work (NAS baselines, valid-action interfaces, metric meta-evaluation), so it had no single point.
Action: The old paragraph is split in two. This half covers valid-action interfaces. "No per-decision test checks" is scoped to "neither tests", which is a narrower claim. The ScienceWorld sentence is shortened. "(CALM)" is dropped because it is never used again. No numbers.

### Related Work ¶5: "Our budget check and ladder adapt..."
Point: The budget check applies the matched-budget baseline principle and adds no new one. The ladder follows perturbation-based metric meta-evaluation, and because its rungs are privileged it validates the measurement, not a policy.
Diagnosis: This came from the second half of the old ¶4. The ladder sentence joined its privileged-rung caveat with "and because …", which made one long sentence.
Action: New topic sentence. Li & Talwalkar and Yang et al. are credited together, the budget-principle disclaimer is kept, and the ladder sentence and its caveat are now two sentences. The caveat appears here as a short clause (the full statements are in the abstract, Section 5.3, and Limitations). No numbers.

### Section 3 (Search Process Policy)

### Section 3 ¶1: "A Search Process Policy executes a..."
Point: A Search Process Policy executes a declared algorithm one typed operation at a time under a runtime that checks each decision. An episode fixes (x, A, m, B), the observation exposes every fact the reference uses, and the scenes come from an external renderer.
Diagnosis: The episode tuple ran its appositives together with commas, including the nested "m, distinct from …," clause. The sentence on textual scope under the enumeration contract referred forward to "Search Memory (defined below)" and belonged with the contracts.
Action: The tuple is now introduced by a colon after a complete clause, with semicolon-separated items (allowed because the items contain commas). "given as input" is cut. The enumeration-only textual sentence moved to the contracts paragraph. The logged clause "the observation adapter m, distinct from the trained adapter scored in Section~\ref{sec:results}" is kept verbatim. The Planimation credit and footnote are unchanged, except that the semicolon became a period (house style: no prose semicolons). No numbers.

### Figure~\ref{fig:contracts} caption: "The policy emits typed decisions, and..."
Point: The policy emits typed decisions, and the runtime owns the checks and Search Memory. The two panels differ in what determines the expansion.
Diagnosis: The takeaway already came first, but a 29-word middle sentence described the top row box by box.
Action: The bold takeaway is unchanged. The top row is one clause (validate, apply, or reject, without repair). Panel (a) is "submitted candidates enter a priority heap that sorts ties", and panel (b) is "the policy's choice of an opaque label determines the expanded state", which matches the figure text. About 71 words became 52. There are no rendering specs, and both evidence comments are unchanged.

### Section 3 old ¶2: "Figure~\ref{fig:contracts} separates the observation adapter..."
Point: A pointer to the figure.
Diagnosis: A one-sentence paragraph that only points to the figure and makes no claim.
Action: Deleted as a paragraph. The pointer is now the parenthetical `(Figure~\ref{fig:contracts})` on the ownership sentence below, and its `% Evidence` comment stays next to it. The old paragraph-purpose comment is replaced by the merged paragraph's comment.

### Section 3 ¶2: "The policy owns only the operations..."
Point: The policy owns the operations it emits, which are Typed Search Operations. The runtime owns the search state in Search Memory, so the observation is the policy's only view of history.
Diagnosis: Run-in bold heads ("Typed Search Operation." and "Search Memory. This is …") broke the paragraph into glossary entries, and the "only channel" logic was implied rather than stated.
Action: Both bold terms are defined inside running sentences. "not in the model, so $o_t$ is the policy's only channel to history" states the reasoning. The Search Memory capacity TODO comment is kept. No numbers.

### Section 3 ¶3: "On every operation, the runtime checks..."
Point: The runtime checks every operation against the declared algorithm's invariant and never decides for the policy. Compliance is not success.
Diagnosis: The old version was two run-in-head paragraphs (Algorithm Invariant and Trusted Search Runtime). The compliance caveat sat in the middle of the definitions. The runtime sentence stacked three appendix pointers by prose name, and two of them had no \ref.
Action: The two are merged into one paragraph around a single point. The per-family invariant sentences are kept, including FIFO and the two additive variants. "reorders candidates on the policy's behalf" uses the CONTEXT.md wording, so the sentence does not contradict the heap ordering under enumeration. The pointer is now `Appendices~\ref{appendix}--\ref{app:runtime}` (Operation Schemas, Algorithm Invariant Definitions, Trusted Search Runtime). The full caveat now closes the paragraph. The `% Evidence (executed additive controller)` comment stays next to the tie-break sentence. The visible `g + 3h_add` is unchanged.

### Section 3 ¶4: "The two decision contracts differ in..."
Point: The contracts differ in what the policy chooses. Under enumeration it submits the full candidate set, and Search Memory and the candidates stay textual. Under choice-frontier it picks the frontier state for greedy and weighted-A* best-first search only, within twice the reference's expansions, from scene-only observations, so no modality comparison is made.
Diagnosis: The algorithm-scope and observation sentences were stacked facts. Two pointers had no \ref ("(Choice-Frontier Contract appendix)" and "(Decision Contracts appendix)"). The textual-scope fact sat in ¶1.
Action: The enumeration textual-scope sentence is added here ("even when $o_t$ is visual", supported by the Modality Adapters appendix). The scene-only list is introduced by a colon. The logged "no observation modality is compared under this contract" is kept as its own "therefore" sentence. Pointers now use Appendix~\ref{app:cf-contract} and Appendix~\ref{app:design-contracts}. "twice" is kept, and it also appears in Table~\ref{tab:design-contracts} and Box 1. All `% Evidence` comments are unchanged.

### Section 3 ¶5: "Training uses process supervision, token-level..."
Point: The training objective is token-level cloning of the exact reference on Search-Trace Segments, with optional DAgger.
Diagnosis: OK.
Action: The only change is the verb up front ("Training uses"). No numbers.

### Word counts (non-comment, whitespace tokens)

I counted by hand with the same rule as `sed -E 's/(^|[^\\])%.*$/\1/' FILE | wc -w`, because this slice has no shell tool. Hand-counting the original Section 3 gave exactly the brief's 536, which checks the method.

| File | Before | After | Target |
|---|---|---|---|
| iclr2026_conference_related_work.tex | 415 (brief) | 374 | ≤ 380 |
| iclr2026_conference_search_process_policy.tex | 536 | 486 | ≤ 490 |

### Numbers
No number was added, changed, or removed. The only visible numerals in the slice are Section 3's "twice" and $g + 3h_{\rm add}$, and both are unchanged. Related Work has no numbers.

### Cross-file notes (not fixed)
1. Related Work no longer glosses the choice-frontier contract, and it uses "ladder", "rungs", and "random-valid" without defining them. It relies on the Introduction's definitions (L23 random-valid, L53 choice-frontier contract, L57 and L63 ladder and rungs). If the Introduction cuts these, the gloss must come back. AbstractIntro has been told.
2. Section 3 now says the runtime never "reorders candidates on the policy's behalf" (CONTEXT.md wording). The No-repair property item in the Trusted Search Runtime appendix (appendix L157) still says "reorders candidates" without the qualifier, which reads as conflicting with the priority heap that orders candidates under enumeration.
3. The acronyms MVoT, VQA, LVLM, and CALM left Related Work because nothing else in the manuscript uses them. "RAP" stays because the appendix survey table (Table 24 row) uses it.
4. `lightman2023lets` is now cited once in Related Work instead of twice. All 34 Related Work keys are still cited.

## Prose audit: Design (Section 4, `iclr2026_conference_experimental_design.tex`, including Box 1 `box:procedure`)

### §4 ¶1: "Every learned result is read against"
Point: Two oracle-assisted controls bound every learned result. Random-valid is defined exactly under each contract.
Diagnosis: The topic claim was fine, but the saturation consequence was buried as the third sentence, between the definitions. It also said "defines the imitation target", which Section 3 already establishes.
Action: The paragraph now runs claim (two controls, named in a colon list), then why (they read oracle information, so their scores are bounds and saturation makes a gain unmeasurable), then the definitions. The sampler definition is kept in full because nothing else in the PDF states it. No numbers.

### §4 ¶2: "The identity audit compares random-valid with"
Point: The audit comes first because when random-valid never diverges from the reference, success measures validity. Its role differs by contract.
Diagnosis: Definition with no reason. A semicolon joined the two roles.
Action: Added a "because" clause giving why the audit matters, and replaced the semicolon with a single sentence covering both roles. No numbers.

### §4 ¶3: "The choice-frontier panels grow more independent"
Point: The panels become progressively more independent of the design, and "held-out" names only the most independent one. This is the one place the full held-out definition appears.
Diagnosis: Ledger. Old ¶3 and ¶4 mixed the panel list, the screen rule, and a seed-extension history sentence. The held-out meaning was spread over five one-fact sentences, and the Held-Out Panels appendix was cited by name with no \ref.
Action: New topic sentence (panels ordered by independence), then the reused 9-task panel with its adaptivity caveat, the validation panel, the held-out panel, and the held-out meaning with the 45-task caveat as a short clause. The seed extension shrank to one clause, "their range extended once before any evaluation episode (Appendix~\ref{app:results-panels})", because Results now cites Section 4 for it (confirmed with the Results agent). "12 fresh tasks from 7 domains" is kept: the Results agent reported that the 7-domain count is no longer printed in Results. "8 domains" is kept because it is printed nowhere else.

### §4 ¶4: "The validation and held-out panels pass"
Point: The screen keeps tasks on which near-uniform choice sometimes succeeds, and the unscreened panel removes that selection.
Diagnosis: The screen rule sat inside the panel paragraph, and the reason the unscreened panel exists was never stated.
Action: Separate paragraph: the rule (1 to 9 of 10, kept as the rule's own threshold), what it selects, and then the unscreened panel as the control that removes the selection. Screen evidence comments moved with the sentence.

### Box 1 caption: "Validate before score."
Point: Four steps admit random-valid as a choice control and validate the success measure before any policy is scored.
Diagnosis: The takeaway was fine. The "each step names the Results subsection" sentence repeated what each step's own \ref already shows.
Action: Cut that sentence and the phrase "for a search-execution interface" (the Inputs line names the interface). Takeaway only.

### Box 1 Inputs
Point: What the procedure needs.
Diagnosis: Three fragments.
Action: One list sentence with a parenthetical interface spec. Same content.

### Box 1 step 1: "Identity audit"
Point: Audit decisions; read success as choice only under divergence plus a below-reference control.
Diagnosis: The imperative was split over two sentences.
Action: One imperative ("Compare ... reporting the divergent fraction and first divergence"), then the rule as an imperative ("Read success as choice only where ..."), then the saturation clause.

### Box 1 step 2: "Budget check"
Point: When a zero-token control exists, count the budget in decisions or expansions.
Diagnosis: The condition and the principle came in the wrong order.
Action: Condition, then the credited principle (\citep{li2019random} unchanged), then the count and report instruction, then the failure rule. Thresholds unchanged (reference count, twice it).

### Box 1 step 3: "Ladder"
Point: Pre-register the exact-ε ladder on a fresh frozen panel. It passes only if every adjacent lower bound is positive, and the rungs are privileged.
Diagnosis: The long first sentence started with "Given ..., and on ...".
Action: Imperatives ("freeze", "pre-register", "Score M1"). Every threshold kept verbatim: ε 0.25, 0.50, 0.75; four adjacent paired task-clustered 95% lower bounds; twice the reference's expansion count. The privileged-rung caveat is kept.

### Box 1 step 4: "Report"
Point: What to report for a policy.
Diagnosis: "(margin 0.05 here)" repeated "margin".
Action: "(0.05 here)". Otherwise unchanged.

### Box 1 at-risk row and failure branch
Point: One audited instance per step, and what to do on failure.
Diagnosis: OK.
Action: Unchanged.

### §4 ¶5: "Each choice-frontier verdict follows a rule"
Point: Every choice-frontier verdict follows a rule frozen before its outcome.
Diagnosis: Ledger tail ("...; resampling details appear in the Statistics appendix") joined with a semicolon, plus a bare-name appendix pointer.
Action: Topic sentence kept. The ladder rule is a pointer to Box 1, and the adapter rule keeps its 0.05 and ±0.05 margins. The later protocols are one sentence. The resampling pointer moved to ¶6 as Appendix~\ref{app:statistics}.

### §4 ¶6: "The enumeration-contract study compares process" (merged with the former grid paragraph)
Point: The enumeration-contract study compares process SFT with its arms on the expanded baseline, under decision-counted budgets.
Diagnosis: Two paragraphs served one study. The recipe pointer named the appendices without \ref, and "288 episodes per arm" was a receipt.
Action: Merged into one paragraph: arms, then backbones, then grid, then budget, then termination and analysis. "288 episodes per arm" left the prose; it survives as the "Total (of 288)" row of Table tab:results-identity, and its evidence comment is prefixed "(moved out of prose; kept in ...)". Pointers are now Appendix~\ref{app:data-splits} and Appendix~\ref{app:statistics}. The compute-ledger pointer goes through ¶7's Table~\ref{tab:appendix-receipts}. All four \citep kept.

### §4 ¶7: "Every executed run reconciles with its" (carries `\label{sec:results-gates}`)
Point: Every run has a ledger and a replay, and enumeration-contract cells are single-seed except two replicated cells.
Diagnosis: Stacked pointer "(Gate Receipts appendix, Appendix~\ref{}, Table~\ref{})". The seed IDs "17/29/71" were a receipt, and the 45-task sentence repeated ¶3.
Action: The pointer is now "(Appendix~\ref{app:results-gates}, Table~\ref{tab:appendix-receipts})". The seed IDs became "three training seeds". The IDs remain in the Statistics appendix Seed-variance addendum, the replication paragraph, and the Introduction, with a prefix comment. The "never accessed" sentence was cut from this paragraph: ¶3 states the 45-task evaluation is unexecuted, and Appendix app:data-splits states the manifest was never accessed.

### §4 ¶8 (cut): "Box~\ref{box:procedure} collects these rules..."
Point: Pointer to Box 1.
Diagnosis: The same mapping appears in the Results opener, the Reproducibility Statement, and each step's \ref.
Action: Cut for the page budget. Box 1 is still cited in text (¶5, "Box~\ref{box:procedure}'s pass rule").

### Word counts (non-comment, as defined by `sed -E 's/(^|[^\\])%.*$/\1/' FILE | wc -w`)
- `iclr2026_conference_experimental_design.tex`: before 990 (the brief's figure). After: 878, from a manual whitespace-token count of every non-comment line. I had no shell, so this count was not produced by the sed/wc command itself; the integrator should confirm.

### Cross-file notes (not fixed)
- Results line 95 still uses the bare-name pointer "(Statistics appendix, Table~\ref{tab:appendix-seeds})" and "(Primary-Matrix appendices, Appendices~...)". The integrator should check whether the Results owner converted them.
- Introduction line 58 repeats "12 fresh tasks from 7 domains", and Introduction line 106 still prints "seeds 17/29/71". Both are consistent with Section 4, but Section 4 no longer prints the seed IDs.
- Results comments (lines 127 and 146) say Section 4 keeps the 12/7 counts and the seed-extension clause. Both are still present.
- Box 1's caption no longer says "Each step names the Results subsection". Nothing elsewhere depends on that wording (the Results opener maps the steps itself).
- "8 domains" for the reused 9-task panel is printed only in Section 4. If a later pass cuts it, it has to move to Appendix app:results-cf.

## Prose audit: Results (iclr2026/iclr2026_conference_results.tex, Section 5)

### 5 ¶1 — Section~\ref{sec:results-identity} audits the enumeration
Point: Map each subsection to its Box 1 step, and state once that all results are development-stage and the controls are bounds.
Diagnosis: Roadmap written as a semicolon chain that led with caveats and mentioned "tabulates the expanded baseline", "per-task sign counts", and "illustrative episodes". It left out why step 2 is not applied to our own contract.
Action: Rewritten as one mapping sentence, one sentence on why step 2 holds by design (the budget counts decisions), and one caveat sentence. No numbers removed.

### 5.1 ¶1 — On our runtime, random-valid decides
Point: On our runtime, random-valid decides exactly as the exact reference in the additive cells, so success there measures validity, not choice. The serial rule causes this, and BFS/BFWS register choice.
Diagnosis: Buried claim. The mechanism ("equal-priority ties break in sorted candidate order") was stated but not explained, a stack of appendix pointers cut into the argument, and one "(Algorithm Invariant Definitions appendix)" pointer had no \ref.
Action: Claim first, then the cause stated in one sentence (complete candidate set plus sorted tie-break, so submission order cannot change how the frontier evolves; taken from the evidence comment's structural_basis), then 48/48 with a pointer to Table 1. The scope limit to this controller now points to Appendix~\ref{app:invariants}. The Counterfactual confirmation moved to ¶3's topic sentence and keeps the logged "confirms" wording. No numbers removed.

### 5.1 Table 1 caption (tab:results-identity)
Point: Learned success does not establish learned choice where the runtime fixes exploration.
Diagnosis: Takeaway came first (OK), but a semicolon joined two reading notes.
Action: Semicolon split into two sentences, and "algorithm--observation cell" became "algorithm and observation". Table body unchanged.

### 5.1 former ¶2 — Table~\ref{tab:results-identity} separates process-SFT
Point: A table pointer.
Diagnosis: One-sentence paragraph with no claim.
Action: Merged into ¶1, which now cites the table. The text and purpose comment were replaced by a note, and the evidence comment is kept.

### 5.1 ¶3 — Changing only the tie-break order
Point: Changing only the tie-break order breaks the identity, which confirms the serial rule, not the contract alone, as its cause. The pre-registered prediction failed.
Diagnosis: Receipt stream (19/48, >24/48, the other 29 pairs, 18/18, pointer) with no stated meaning. The 18/18 choice-frontier sentence belonged to 5.2.
Action: Meaning first, then 19/48 with the mechanism for the rest, then the failed prediction. Numbers removed: 29 identical pairs → Table tab:appendix-counterfactual (row "Submission order & 29 & 19"); "more than 24/48" → Counterfactual appendix prose ("threshold of more than 24/48"). 18/18 moved to 5.2 ¶1, where it is still visible, and its evidence comment moved with it.

### 5.1 ¶4 (sec:results-primary / sec:results-boundary) — On the expanded baseline, every learned
Point: Every learned success on the expanded baseline lies where the audit finds no choice. The only positive learned contrast is the earlier BFWS development run.
Diagnosis: Number dump (125/288, 240/288, 0/24, 72 units, 0.933, 0.467, 0.2). Two points shared one paragraph (the learned results, and why saturation cannot find the identity), jargon ("problem-modality units"), stacked pointers ("Primary-Matrix appendices, Appendices …"), and "(Statistics appendix, …)".
Action: Split into ¶4 (learned results) and ¶5 (saturation and the step 1 verdict). ¶4 keeps 125/288 and the BFWS lower bound 0.2, which is printed nowhere else, so it stays. Numbers removed: 240/288 → Table tab:results-identity Total row; 0/24 per BFS/BFWS cell → Table tab:results-identity and tab:results-primary-matrix (plain "never succeeds" in prose); 72 problem-modality units → Appendix app:results-contrasts prose ("zero of the 72 problem-modality units") and Table tab:results-contrasts, with the prose now reading "wins no task under any observation"; 0.933 and 0.467 → Table tab:results-bfws. The secondary-analysis list was shortened to "Other enumeration-contract analyses" with an appendix range.

### 5.1 ¶5 — Success saturation alone could not
Point: Saturation alone could not have exposed the identity, so step 1 must run on executed code.
Diagnosis: Previously buried mid-paragraph in ¶4.
Action: New standalone verdict paragraph. Its evidence comment is copied from ¶4 (the BFS saturation key). No numbers.

### 5.2 ¶1 — On the choice-frontier contract, M1
Point: M1 passes its pre-registered validity test. The contract passes the identity audit, and the ladder orders as pre-registered on the validation panel.
Diagnosis: Ledger ("12 tasks from 7 domains", 9/9 tasks, 0.875, 0.021, "+0.082 [+0.051, +0.111]") with the claim second, plus a long appendix name.
Action: Claim first, then the identity pass (18/18 on the reused 9-task panel), then the ordering with "every adjacent lower bound positive", then the logged 0.875 construction gloss. The one-sentence budget-curve paragraph was folded into this one as a Figure~\ref{fig:budget-curves} citation. Numbers removed: 12 tasks, 7 domains → Section 4 ("12 fresh tasks from 7 domains"; Design confirmed it is kept) and Table tab:appendix-ladder-panel; 0.021 → fig:ladder and Table tab:appendix-ladder-arms / tab:appendix-panel-arms; +0.082 [+0.051, +0.111] → Choice-Frontier Validation appendix replay paragraph. "9/9 tasks" does not appear verbatim anywhere else. The same fact is carried by "18/18 pairs of the reused 9-task panel" (9 tasks × 2 algorithms) and by the survey table's 18/18.

### 5.2 ¶2 — The ladder also passes on
Point: The ladder also passes on the held-out panel, which was frozen before any evaluation, so M1's ordering holds on seeds no adapter had been evaluated on. The unscreened pass is descriptive.
Diagnosis: Process history (the first freeze admitted 6 of 8 tasks, then an amendment added seeds) with no claim about what the pass means.
Action: Rewritten as claim plus meaning. The process history is reduced to one defending clause ("frozen before any evaluation episode"). Numbers removed: 11 tasks, 8 domains → Held-Out Panels appendix construction paragraph and the Tasks column of Table tab:results-panels (11); 6 of 8 → Held-Out Panels appendix amendment paragraph ("admitted 6 tasks", "minimum of 8 tasks"). Section 4 states that the seed extension preceded every evaluation episode.

### 5.2 ¶3 — A pass licenses one reading
Point: A ladder pass licenses reading M1 only along the ε axis. The rungs are privileged, so the ladder validates the measurement, not a policy.
Diagnosis: Opened with a bare statistic ("The smallest held-out adjacent gap is +0.130 [+0.070, +0.190]"), and the license, the limit, and the budget facts followed as a list.
Action: Opens on the license. The off-axis limit and the privileged-rung verdict are kept verbatim in meaning, and the logged budget clause is shortened to one sentence. Number removed: +0.130 [+0.070, +0.190] → Held-Out Panels appendix arms paragraph (first of the four held-out gaps).

### 5.2 Figure caption (fig:ladder)
Point: M1 orders the privileged rungs on all three panels.
Diagnosis: Takeaway came first (OK). Slightly wordy.
Action: Tightened by 6 words. The P2 separation reading and the privileged and descriptive labels are kept.

### 5.2 former ¶4 — A point estimate alone would
Point: Pointer to the budget curves.
Diagnosis: One-sentence pointer paragraph.
Action: Folded into 5.2 ¶1 as a figure citation. The purpose comment was replaced by a note, and the evidence comment is kept.

### 5.3 ¶1 — The validated measurement scores one
Point: The validated measurement scores the trained adapter above random-valid on both pre-registered panels.
Diagnosis: No headline number. The main result was stated only as "positive", and process history ("Seeds 29 and 71 were trained later with the byte-identical recipe under a pre-registered protocol") took up a full sentence.
Action: The headline point estimates D3 = +0.285 and +0.416 were added, copied verbatim from Table tab:results-panels with a new evidence comment. D3 is glossed in words, and "every seed positive" is kept. The process-history sentence was removed; it survives in the Scaled Adapter appendix "Four choices" paragraph and does not defend any claim here.

### 5.3 ¶2 — The adapter's ladder position depends
Point: The adapter's ladder position depends on the panel. It clears the 0.75 rung only on the held-out panel, and that separation is fragile.
Diagnosis: Bare interval "+0.227 [+0.053, +0.403]" as the second sentence, followed by a stack of limits.
Action: The interval was replaced by its meaning ("separated above … only on the held-out panel"). Non-equivalence, the below-0.50 descriptive result (now with a Table tab:appendix-seed-d pointer), and the small-cluster caveat are kept. Numbers removed: +0.227 [+0.053, +0.403] → Table tab:results-panels and tab:appendix-seed-d; "35 tasks" → Table tab:results-panels Pooled row; "positive on 8" → Held-Out Panels appendix seed-and-rung paragraph ("8 positive and 3 negative"). Kept in prose: 11 clusters and 3 negative.

### 5.3 Table caption (tab:results-panels)
Point: The adapter beats random-valid on every panel but clears the 0.75 rung only on the held-out panel.
Diagnosis: The title was a label ("Development-stage choice-frontier contrasts"), not a takeaway.
Action: Takeaway title. "Development-stage" moved into the reading sentence, and the last-column sentence was tightened. Table body unchanged.

### 5.3 ¶3 — Two other policies score at
Point: Two other policies score at the random-valid level: the zero-shot base and the first adapter.
Diagnosis: Number dump ("D3 = +0.005 [-0.025, +0.044]", "M1 0.026 [0.010, 0.042]"), and the list of how the first adapter differs was a receipt.
Action: The claim is kept with its stage labels (development, one realisation, confirmatory) and the ±0.05 margin. One grounded meaning clause was added: "although every choice it makes is valid" (Zero-Shot appendix: all 1,592 calls valid; evidence comment added). Numbers removed: +0.005 [-0.025, +0.044] → Table tab:appendix-zeroshot; 0.026 [0.010, 0.042] → Table tab:appendix-ladder-arms and fig:ladder. The corpus/augmentation/order/seed difference list → Scaled Adapter appendix recipe paragraph.

### 5.3 ¶4 — Without the screen, which admits
Point: Without the screen the gain survives but rests on 4 of 12 tasks (descriptive).
Diagnosis: Receipts (0/10) and a repeated statement of the freeze process (already in Section 4). It also repeated the ladder pass from 5.2.
Action: The screen's definition is folded into the topic sentence as the reason the check matters. The logged "not evidence about where choice discriminates" line is kept. Numbers removed: 0/10 → Held-Out Panels appendix unscreened-construction paragraph (prose says "no random-valid screening goals"). The freeze clause was removed because Section 4 states it.

### 5.3 ¶5 — The gain is not carried
Point: The gain is not carried by a single domain (descriptive).
Diagnosis: The old paragraph packed concentration, a figure pointer, leave-one-domain-out, DAgger, and the claim frame into one paragraph, with stacked parentheticals.
Action: Split in two. This paragraph keeps 22 of 35 and "one negative". Number removed: 12 zero → Table tab:results-panels (22/12/1) and the Held-Out Panels appendix concentration paragraph. Leave-one-domain-out now points to Table tab:appendix-concentration.

### 5.3 ¶6 — One on-policy DAgger round, run
Point: One DAgger round does not move the adapter off the 0.75 rung, and the subsection closes on the full claim frame.
Diagnosis: A bare interval "+0.115 [-0.026, +0.258]".
Action: The interval was replaced by its verdict ("does not separate"). The full claim-frame caveat is kept as the subsection verdict (its single full statement at the result). Number removed: +0.115 [-0.026, +0.258] → DAgger Ablation appendix prose.

### 5.4 (Qualitative) ¶1 — Two rule-selected episodes illustrate a
Point: Two rule-selected episodes illustrate one success and one failure. They are illustrations only.
Diagnosis: No purpose comment. Opened directly on detail.
Action: Topic sentence added and the two cases merged into one sentence. The "illustrations, not efficacy or failure mechanism" and "heuristics only for analysis" caveats are kept, and 7/9 is kept (also in the qualitative caption). A purpose comment was added. The figure refs now read "Figures~\ref{..}", with the appendix located via Appendix~\ref{app:qualitative}.

### 5.5 ¶1 — The identity audit passes on
Point: ScienceWorld passes the identity audit, so it is a positive control for step 1, and the 48/48 failure is shown only on our runtime.
Diagnosis: Receipt chain (5 seeds, 200 tasks, 100-step budget, 1000/1000, 0.915, 6 of 30), and the appendix pointer was stacked with a long appendix name.
Action: Claim first, then the two step-1 conditions (divergence at the first decision; 0 against 0.915), then scope (6 of 30), then the only-our-runtime caveat stated in full. Numbers removed: five seeds, 200 tasks, 100-step limit → External Identity Audit appendix protocol paragraph; 1000/1000 → Table tab:appendix-survey ("1,000/1,000").

### 5.5 ¶2 — LLM-First Search illustrates by construction
Point: LLM-First Search shows by construction why step 2 must count the budget in decisions.
Diagnosis: Receipt stream (400 pairs, 80 tasks, 0.768, 1.0, 0.825, 102,606 vs 1,300). The claim came at the end.
Action: Claim first, then the model substitution (required caveat), the saturation, the mechanism, and the decision-counted result. Kept: 0.0775 and 0.19 (0.19 is printed nowhere else and Box 1 step 2 asks for it). Numbers removed: 400 pairs → Table tab:appendix-survey ("400/400") and LLM-First Search appendix prose; 80 tasks from four configurations → LLM-First Search appendix setup paragraph ("80 tasks in all") and Table tab:appendix-lfs "All (80)"; 0.768 → LLM-First Search appendix prose ("Published GPT-4o success … is 0.768"); 1.0 and 0.825 → Table tab:appendix-lfs (prose says "solves every task"); 102,606 and 1,300 → LLM-First Search appendix prose.

### Word counts (non-comment)
- iclr2026/iclr2026_conference_results.tex: before 1953 (from the brief); after ≈ 1666 by a manual whitespace-token count of every non-comment line (prose ≈ 1238, tables/captions/structure ≈ 428). I could not run `sed | wc -w` because this session has no shell tool, so the integrator should confirm the number. The target is ≤ 1700.

### Cross-file notes (not fixed)
- Introduction still gives D3 intervals (+0.285 [+0.140, +0.433], +0.416 [+0.250, +0.591]). Results now gives only the point estimates, and Table 2 carries the intervals. This is consistent but duplicated.
- Section 4 must keep "12 fresh tasks from 7 domains" (the validation panel's 7-domain count is printed nowhere else). Design confirmed it is kept.
- Appendix line ~643 ("the qualification gates that Section~\ref{sec:results-gates} summarizes"): the label now sits in Section 4, not Results. The ref resolves, but the wording is stale.
- Discussion ¶ on external audits repeats the "none of the seven … only on our runtime" caveat in full. Caveat placement allows a short clause there.
- "9/9 tasks" is no longer printed verbatim anywhere (see 5.2 ¶1). If the integrator wants the literal count, the Choice-Frontier Receipts appendix owner could add it.

## Prose audit: DiscussionEtc

Files: `iclr2026/iclr2026_conference_discussion.tex`, `iclr2026/iclr2026_conference_reproducibility.tex`, `iclr2026/qualitative_figures.tex` (three captions), `iclr2026/iclr2026_conference.tex` (hub, checked only).

### Discussion ¶1: "A search-choice measurement must be validated..."
Point: success on a search-execution interface can measure validity rather than choice, so a measurement must be validated before it scores policies. Ours passes the audit, the decision-counted budget, and the ladder, and the privileged rungs validate the measurement, not a policy.
Diagnosis: the claim led the paragraph but was followed by a Results receipt (48/48 under sorted ties, 19/48 under submission order) with stacked pointers. The ε-axis license repeated Results 5.2 and Box 1 step 3. It restated results instead of saying what they mean.
Action: opens with the takeaway (success alone cannot separate validity from choice), then the tie-break flip as the reason, stated without numbers, then the inference, then the three checks in one sentence, then the privileged-rung caveat in full. 48/48 and 19/48 left this paragraph. They remain in Results 5.1 (sec:results-identity), Table tab:results-identity, and the Counterfactual appendix, and 48/48 is still stated in ¶4. The evidence comment is kept with a "(moved out of prose; kept in ...)" prefix. The ε-axis license sentence is gone here because the Limitations "Ladder axis" bullet, Results 5.2, and Box 1 step 3 state it.

### Discussion ¶2: "The development-stage answer to the title..."
Point: the development-stage answer is narrow. A trained scene-only adapter chooses frontier states better than random-valid in greedy best-first search and weighted A* on all three panels, stays well below the reference, and nothing is learned under the enumeration contract.
Diagnosis: the topic sentence was 40+ words. The M1 range 0.151 to 0.432 against 0.875 was a number dump. "The adapter is trained only by imitating the exact reference." was left as a disconnected last line.
Action: short topic sentence ("is narrow"), then the scoped answer. The imitation clause now connects to the gap with "yet". 0.151, 0.432, and 0.875 moved to a pointer to Table tab:appendix-panel-arms, which holds all three. 0.875 "by construction" is also in Results 5.2 and the Choice-Frontier Contract appendix. The evidence comment is kept with a moved-out prefix. "(VLM)" is dropped because no later text uses it. The BFS/BFWS negative is kept.

### Discussion ¶3: "Box 1 states three practices..."
Point: Box 1 yields three practices, and each one answers a failure we observed.
Diagnosis: a list of imperatives with no reasons given ("First, ... Second, ... Third, ..."), plus a self-referential Box pointer repeated in the middle.
Action: each practice now carries its reason with "because"/"since": the specification hid the identity failure, and a zero-token control spends nothing under a token budget. The trainer practice keeps both "not choice" and "not near-reference choice" statements. No numbers. The seed-replication evidence comment is kept.

### Discussion ¶4: "ScienceWorld is a positive control..."
Point: the external audits matter because steps 1 and 2 run on published interfaces, and because they bound the 48/48 identity failure to our runtime.
Diagnosis: no topic sentence. The paragraph named the audits' roles without saying why they matter.
Action: new topic sentence ("show that steps 1 and 2 run on published interfaces"), then the two roles as fixed in CONTEXT ("positive control", "by-construction illustration"), then the runtime bound. "Seven" and "48/48" are kept as headline numbers. A copied 48/48 evidence comment is added from Box 1. The paragraph stays two sentences.

### Limitations: list
Point: state each limitation once, in full, with its consequence. This is the designated full-statement location.
Diagnosis: mostly fine, but some items stated a fact without its consequence (Final evaluation, External audit) and some were wordy (Ladder axis, Menu surface).
Action: all 11 items kept, and no caveat was dropped. Changes:
- Final evaluation: adds "so every result is development-stage".
- External audit: adds "so it does not test the published results" (CONTEXT: no claim about the published GPT-4o results).
- Ladder axis: rewritten as "validated only along the ladder's ε axis".
- Menu surface: compressed.
- Seeds: now "Only three ... were run".
- Second policy: drops the parenthetical on the reduced-scope enumeration run. The appendix "Second backbone" paragraph and the Gate Receipts appendix keep it.
Numbers 0.75, 4 of 12, 29, 45, 80, and four are all kept.

### Conclusion ¶1: "We validate a search-choice measurement..."
Point: lead with the validate-before-score contribution, answer the title at development stage for the two additive best-first variants only, and close with the claim frame.
Diagnosis: 5 sentences. It carried $D_3$ with its interval, a separate rung sentence, and a long claim-frame sentence.
Action: now 4 sentences: contribution, scoped answer, the BFS/BFWS negative, and the scoped conclusion with "no planning-ability or generality claim". Moved out:
- $D_3 = +0.285$ $[+0.140, +0.433]$: kept in Table tab:results-panels, the abstract, the Introduction, and Table tab:appendix-seed-d.
- The 0.75-rung sentence: kept in the Limitations "Ladder position" item and Table tab:results-panels.
The evidence comment is kept with a moved-out prefix.

### Reproducibility ¶1: "Box 1 states the validate-before-score..."
Point: Box 1 is the procedure, and four appendices plus the choice-frontier contract appendix hold the reproduction detail.
Diagnosis: a chain of long appendix names, each followed by a ref ("Trusted Search Runtime (Appendix~\ref{}) ... appendices").
Action: replaced with "Appendices~\ref{..}, \ref{..}, \ref{..}, and~\ref{..} give the runtime, data splits, run receipts, and statistics". Every ref is kept.

### Reproducibility ¶2: "The Counterfactual (...), Choice-Frontier Validation..."
Point: the follow-up appendices and the ledger and artifact tables, plus the anonymous-release boundary.
Diagnosis: the appendix-name chain plus a sentence on nesting ("sit under the Scaled Adapter appendix").
Action: one sentence lists the four follow-up appendices by ref, with the subsections introduced by "including". The nesting sentence is removed, since the refs show it. All 8 refs, both table refs, and the supplementary-material sentence are kept. No numbers.

### Caption fig:qualitative-success
Point: on a solved validation task the adapter follows the reference to the goal while random-valid runs out.
Diagnosis: the title "Illustrative success on a validation task" gave the category but no takeaway. It used "weighted best-first" instead of the prose name "weighted A*", and a semicolon.
Action: the takeaway is now the bold title. Kept: 7/9, 10, 18, and the rule-selected clause. Added a one-line guide to reading the figure (rows, $h_{\mathrm{add}}$ trace after the first expansion) and the illustrative-not-efficacy clause. No pixel specs.

### Caption fig:qualitative-decision
Point: the adapter picks the reference's state at the largest menu, and across validation decisions it favours low-$h_{\mathrm{add}}$ states over uniform choice (descriptive).
Diagnosis: the title "A choice at the largest frontier menu ..." gave no takeaway, and the caption used a semicolon.
Action: the takeaway is now the bold title. Kept: 10, $c_{11}$, 12, and the privileged-information clause. Added a cross-ref to fig:qualitative-success for "the episode". The histogram sentence ends with "is not an efficacy estimate".

### Caption fig:qualitative-failure
Point: on a held-out puzzle the adapter stalls where the reference solves.
Diagnosis: the title gave only the category, and the caption used a semicolon.
Action: the takeaway is now the bold title. Kept: 47, 92, 9, 40, the tile-glyph discrepancy (CONTEXT requires it to be described), and the no-causal-claim clause. The provenance and selection-rule comments are unchanged.

### Hub iclr2026_conference.tex
No visible prose apart from the template author block, which is unchanged.

### Word counts (non-comment)
Counted by hand with the `sed ... | wc -w` tokenization (whitespace tokens, comments stripped), because this slice had no shell. The integrator should rerun the command.
- `iclr2026_conference_discussion.tex`: 692 (brief) → about 592
- `iclr2026_conference_reproducibility.tex`: 121 (brief) → about 85
- `qualitative_figures.tex` caption text: about 173 → about 206. It sits in the appendix and grew slightly because each caption now has a takeaway title and a reading guide.

### Cross-file issues noticed (not fixed)
1. Discussion ¶3 cites the seed-replication cell through `Section~\ref{sec:introduction}` (the ref is unchanged per the slice rules). The receipt itself is in Results 5.1 (sec:results-primary, Table tab:appendix-seeds). A more accurate target would be `Table~\ref{tab:appendix-seeds}`.
2. Changelog line 22 says the 0.75-rung position is retained "in the figure, Results, and Discussion". After this pass, the Discussion states it only in the Limitations "Ladder position" item. The Conclusion no longer carries it.
3. The Introduction (line 63) and Results 5.2 (line 136) both state the privileged-rung caveat in full. The Discussion states it in full once more. Per CONTEXT "Caveat placement", one of the Introduction or Results statements could become a short clause. That is left to their owners.
4. The Results qualitative paragraph (line 245) says random-valid "exhausts its budget". The caption says "decision cap". They are consistent in meaning, but the wording differs.

## Prose audit: AppendixA
Scope: `iclr2026/iclr2026_conference_appendix.tex`, from the file start (roadmap) through `\section{Retained-Infrastructure Feasibility Notes}`. No number was added, changed, or recomputed. Table bodies are unchanged. The only exact within-range duplicate removed from prose is 68.52/336 in Follow-up windows, which is still in the addenda paragraph and in `tab:appendix-receipts`. A `% (moved out of prose; kept in …)` comment was added for it. One STATUS line was added at the top, and AppendixB and AppendixC were told not to add a second.

### Roadmap ¶1: "The appendices follow the order in"
Point: says which appendix answers which reader question.
Diagnosis: no topic sentence. Nine stacked "The X appendix (Appendix~\ref{})" name-plus-ref pointers.
Action: added an ordering topic sentence (interface → data/accounting → statistics → results). Replaced the appendix names with bare `Appendix~\ref{}` pointers and kept every ref.

### Operation Schemas ¶1: "This appendix gives the operation vocabulary"
Point / Diagnosis: section opener, OK. Action: none.

### Operation Schemas ¶2: "The schemas enforce one rule: every"
Point: every operand that determines exploration comes from the policy.
Diagnosis: the governing rule was buried in the last sentence.
Action: moved the rule to the topic sentence. Added the consequence clause "so it never supplies a missing operand itself", which restates the no-repair guarantee.

### BFS / BFWS / Additive schema ¶¶
Point: the operands and checks for each algorithm.
Diagnosis: the corpus-exposure sentence at the end was disconnected.
Action: linked it to the checks ("exposes the facts these checks use, namely …"). The additive paragraph is unchanged.

### Validity preconditions ¶: "Every emission passes through the same"
Point: the checks are ordered, and the first one failed defines the rejection kind.
Diagnosis: three one-fact sentences.
Action: merged them. Added why the order matters: each kind names the earliest failed check.

### Rejection categories ¶: "The rejection kinds fall into two"
Point: format failures and search failures are separated, and random-valid has only a budget failure.
Diagnosis: definitional, with no stated point.
Action: added a topic sentence and turned the random-valid clause into a causal "so". Updated the purpose comment.

### Rejection counts ¶ + `tab:appendix-rejection` caption
Point: the base fails on format, and learned policies fail after parsing, on invariants.
Diagnosis: the paragraph pointed at the table without saying what it shows.
Action: added a takeaway topic sentence read from the existing table rows (379/447 malformed, 229/407 other-invariant). The caption now leads with the same takeaway. The 905 and 2,910 counts stay.

### Invariants ¶1 (opener)
OK. Action: none.

### Invariants ¶2: "The Trusted Search Runtime checks the"
Point: invariants are per-step checks, so they say nothing about episode outcomes.
Diagnosis: two sentences with no logical link.
Action: added "Because each invariant constrains a single step". The caveat is kept in full.

### BFS invariant ¶
Diagnosis: a ledger of four one-fact sentences.
Action: joined them with "so". The completeness sentence is kept verbatim.

### BFWS / weighted / greedy invariant ¶¶
OK. Action: none.

### Serial-assignment ¶: "The executed controller's serial assignment is"
Point: the controller's serial rule is what produces the enumeration-contract identity, so the identity is runtime-specific.
Diagnosis: opened on code identifiers, with the claim buried at the end.
Action: added a claim topic sentence and "therefore". Closed with a pointer to Appendix~\ref{app:results-counterfactual}, which confirms the identity.

### Runtime ¶1 (opener), guarantees list
OK. Action: none.

### Pseudocode ¶: "The two procedures below make the"
Point: how Step and Episode map onto the ordered checks and the budget loop.
Diagnosis: LaTeX trivia ("No algorithm package is loaded. The listing uses tabbing.").
Action: replaced it with what the procedures do. The package note survives in the file-header STATUS comment.

### Budget ¶
Diagnosis: two sentences where one causal sentence works. Action: merged them with "so".

### Data ¶1 (opener)
OK. Action: none.

### Split-rule ¶
Diagnosis: consequence stated as a separate fact. Action: joined with "so".

### BFS pilot corpus ¶
Point: the v8 panel draws only from the dev side of a task-level split, so no panel task trains.
Diagnosis: receipt dump, with the leakage claim fourth.
Action: the leakage claim now leads, and the redundant "consistent with the whole-instance rule" sentence is gone. All numbers stay (25,109; 12,994; 12,115; 90; 15; 8,192; 384).

### BFWS corpus ¶
Point: the corpus covers the development panel and passed its audits.
Diagnosis: sizes came first and the audit result last.
Action: the audit result now leads. All numbers stay.

### Enumeration training recipe ¶
Point: recipes differ in size, so they are not a matched comparison.
Diagnosis: the caveat came last. There was no purpose comment and a semicolon.
Action: the caveat now leads. Added "whereas" and a purpose comment, and removed the semicolon. All numbers stay.

### Evaluation manifests ¶
Point: every evaluation is development-stage, and the frozen 45-task final evaluation manifest was never accessed.
Diagnosis: no topic sentence, and a list of manifests.
Action: added a topic sentence and folded the never-accessed clause into the 45-task sentence. All numbers stay.

### Receipts ¶1 (opener)
OK. Action: none.

### Branch receipts ¶ + `tab:appendix-receipts` caption
Point: every branch reconciles with zero missing evidence.
Diagnosis: the table description came first and the claim third.
Action: the claim now leads. Merged the v1/v2 sentences. The caption leads with the takeaway, and its semicolon became a period.

### Gate-code ¶
Point: one code per outcome kind, because the branches ended differently.
Diagnosis: a mid-list colon, list semicolons, and a trailing semicolon. "LFS" and "P2" appeared in prose.
Action: added a reason clause, used commas in the list, and turned the caveat semicolon into a sentence. P2 → "the held-out panel", LFS → "LLM-First Search", "on validation" → "on the validation panel". 12.11 is kept.

### Attempts ¶
Point: the ledger charges failed attempts.
Diagnosis: three one-fact sentences with no point.
Action: added a topic sentence and merged the rest. 135/96/36/3 and the cutoff timestamp are kept.

### Addenda ¶
Point: two addenda brought the total to 68.52/336.
Diagnosis: the conclusion came third, and "The Statistics appendix" had no ref.
Action: the total now leads. The pointer became Appendix~\ref{app:statistics}. 2.22, 12.79, and 534 are kept.

### Follow-up windows ¶
Point: each window stayed under its own cap on a separate ledger.
Diagnosis: a long run of one-fact receipts, with the "failed attempts" point last.
Action: new topic sentence ("every window finished under its cap", checked against each spend/cap pair in the table). Moved the failed-attempts sentence up and merged the replay sentences into their window sentences. Removed the duplicate 68.52/336 (kept in the addenda ¶ and the table, with a moved-out comment). Every other number stays.

### Artifact index ¶ + `tab:appendix-artifacts` caption
Point: each follow-up claim class traces to a pinned file.
Diagnosis: the caption had no takeaway.
Action: the takeaway now leads in both the paragraph and the caption, and the caption semicolon became ", and".

### Statistics ¶1 (opener)
OK. Action: none.

### Default contrast ¶
Point: main-program intervals are descriptive bounds.
Diagnosis: the licence statement came last.
Action: it now leads, with the reason given as a "because" clause. 10,000, 1729, and 95% are kept.

### BFWS gate ¶
Point: the gate bound is the lower end of a two-sided 95% interval.
Diagnosis: the point came second.
Action: reordered so the point comes first. The same parameters are kept.

### Tiny-strata ¶
Diagnosis: three one-fact sentences. Action: two sentences with "so".

### Transfer tests ¶
Point: no transfer comparison survives correction.
Diagnosis: the conclusion came last. The non-equivalence sentence that the paper's own materiality rule requires was missing.
Action: the conclusion now leads, followed by a one-clause non-equivalence statement. 36 and 0.8156 are kept.

### Follow-up bootstrap ¶
Diagnosis: a ledger of short sentences. Action: merged them into three sentences. All seeds and draws are kept.

### Materiality ¶
Point: materiality means the interval excludes zero, and equivalence needs a pre-registered margin.
Diagnosis: $D$ and $S$ were used before their definitions. The sign-flip sentence was unattached.
Action: glossed $D$ ("adapter minus random-valid M1") and $S$ ("from an exact-ε rung"). The sign-flip sentence now opens "likewise descriptive".

### Tiny strata in follow-ups ¶, Zoo dominance ¶
The first is OK. In the second, the rule now reads as a licence condition ("must survive Holm … over fifteen tests"). Numbers are unchanged.

### Seed-variance ¶
Point: two cells, with descriptive aggregation.
Action: the descriptive status now leads, and the ledger sentences were merged.

### Cell A ¶ + `tab:appendix-seeds` caption
Point: process SFT beats the base and trails random-valid at every seed, and in an additive cell that reads as validity.
Diagnosis: the paragraph defined the cell and pointed at the table without saying what it shows.
Action: added a takeaway topic sentence (no numbers, from the table rows) and a one-clause identity-audit caveat, consistent with Results ¶95. The caption leads with the takeaway and keeps "descriptive".

### Cell B ¶
Point: the null replicates at every seed.
Diagnosis: the claim came second.
Action: the claim now leads. Added a non-equivalence clause, as the materiality rule requires. 0/72 and +0.000 [0.000, 0.000] are kept.

### Seed boundary ¶
OK. Action: none.

### Modality ¶1 (opener)
OK. Action: none.

### Adapter-contract ¶
Point: every adapter must be decision-sufficient.
Diagnosis: the requirement came last.
Action: it now leads.

### text-state, multimodal-state, native-arms ¶¶
OK. Action: none.

### visual-state ¶ (split in two)
Point of the new second paragraph: the figures show the policy's own scenes, never retouched.
Diagnosis: figure provenance was run on inside the adapter definition. It had a mid-sentence colon, and "validation filmstrips" had no pointer.
Action: split it into its own paragraph with a purpose comment and topic sentence. Added Appendix~\ref{app:qualitative} and replaced the colon with "because". 128 and 256 are kept.

### Text-scaffold caveat ¶
Point: search bookkeeping always travels as text.
Action: tightened the topic sentence and added Table~\ref{tab:results-corruption}. −0.944, −0.722, and −0.111 are kept.

### Native-arms caveat ¶
Point: the native arms narrow the caveat to the menu but do not remove it.
Action: added "without removing it" and pointers to Appendix~\ref{app:results-native} and Appendix~\ref{app:results-menu}. The numbers stay.

### Information-loss ¶
Point: adapters match in format, not information, so no intrinsic modality effect is established.
Diagnosis: the conclusion was the last of six one-fact sentences.
Action: the conclusion now leads, followed by the grouped evidence. 24/24, 18/24, and 0/24 are kept.

### Retained-infrastructure opener, plan/rendering/certification ¶¶, Historical terms ¶
Diagnosis: the opener's three one-fact sentences said "The terms below". The historical ¶ had a ledger split.
Action: the opener is now two sentences, and the historical ¶ merges "describe retained infrastructure internals" into the first sentence. The glossary definitions are unchanged.

### Word counts (non-comment, `sed -E 's/(^|[^\\])%.*$/\1/' FILE | wc -w`)
Not measured. This session had no shell tool, and the owners did not run the command. The integrator should run it on the whole shared file. By a per-paragraph tally, the owned range grew by roughly +230 words (about +4%). The growth comes from the topic and consequence sentences added to formerly bare receipt paragraphs, and from three takeaway-first captions.

### Cross-file issues noticed (not fixed)
- `iclr2026_conference_search_process_policy.tex` L48 has a stacked name-plus-ref pointer "(Operation Schemas appendix, Appendix~\ref{appendix}, and Algorithm Invariant Definitions appendix)". The second appendix has no `\ref`, and should use `Appendix~\ref{app:invariants}`.
- `iclr2026_conference_experimental_design.tex` L120 says "Data and Split Procedures and Receipt Tables appendices" with no refs (`app:data-splits`, `app:receipts`). L133 uses the stacked "(Gate Receipts appendix, Appendix~\ref{app:results-gates}, Table~…)". L109 and L127 say "Statistics appendix" / "(Statistics …" with no `\ref{app:statistics}`.
- `iclr2026_conference_results.tex` L95 has "(Statistics appendix, Table~\ref{tab:appendix-seeds})" and "(Primary-Matrix appendices, Appendices~…)", both stacked name-plus-ref pointers.
- The Modality Adapters and Retained-Infrastructure sections have no `\label`, so the roadmap cannot reference them and they are not mentioned in it. Adding labels would change section structure outside the prose remit.
- Materiality ¶ glosses $D$ as "adapter minus random-valid M1". The Scaled Adapter appendix (AppendixB/C range, L~1314) defines $D$ as the mean over training seeds of that difference, which is consistent. Owners of that section may want to check the gloss.

## Prose audit — AppendixB slice

File: `iclr2026/iclr2026_conference_appendix.tex`. Scope runs from `\section{Choice-Frontier Contract and Comparator Selectors}` through the end of `\section{Results Detail: Image-Only Native Arms}`. Table bodies, labels, refs, and citations are unchanged. No number was added, changed, or recomputed. The STATUS line was already added by AppendixA at the file top, per their message, so I did not add a second copy.

### Choice-Frontier Contract and Comparator Selectors

### ¶0 — This appendix specifies the choice-frontier
Point: Roadmap for the section.
Diagnosis: OK.
Action: None.

### ¶1 — Menu and observation. At each
Point: The observation withholds scores, positions, and search counters, so a choice can rest only on the scenes and task pages.
Diagnosis: The paragraph was a specification list with no topic sentence. Its point (no leak channel) was implicit.
Action: Added a topic sentence and merged the leak-check sentence into the payload sentence. Numbers kept (51131, 128px).

### ¶2 — Output and validation. The policy
Point: The contract admits exactly one offered label per decision, and the first invalid emission ends the episode.
Diagnosis: This was a ledger of rejection kinds with no lead claim.
Action: Added a topic sentence and folded the termination label into the rejection sentence.

### ¶3 — Expansion and budget. On acceptance
Point: The policy only chooses and the runtime does the rest, so one choice is one decision. The goal-at-selection rule fixes the reference's decision count.
Diagnosis: The claim was buried in sentence 3.
Action: Moved the claim to the front and split the "so" chain.

### ¶4 — Corpus derivation. The training corpus
Point: Each record teaches the exact reference's own choice (the heap-head label).
Diagnosis: The imitation target, which is the point of the paragraph, came last.
Action: The target now leads.

### ¶5 — Five fail-closed gates run before
Point: Training ran only after five fail-closed gates passed.
Diagnosis: Close to OK. The PASS outcome sat at the end of the list.
Action: Light reorder. PASS now comes first, and all counts are kept.

### ¶6 — Training and replay. Each of
Point: Both adapters trained to completion, and their episodes are replayed. Only report construction failed, and those reports were recovered without retraining.
Diagnosis: This was a process ledger ("completed…, then failed…, recovered…") with no claim.
Action: Added a topic sentence and put the failure into one causal clause.

### ¶7 — Comparator selectors. Each selector's choice
Point: The selectors replace only the choice, so every other search step stays additive. Their replay omits image bindings.
Diagnosis: The claim was implicit.
Action: Added a topic sentence, merged the "therefore" sentence, and scoped the replay-coverage sentence explicitly.

### ¶8 — Metric computation. Under M1 an
Point: The protocol fixes metric edge cases so that every arm is scored by one rule. Goal-at-selection fixes the reference's M1 at 0.875, and privileged arms can exceed it.
Diagnosis: A definition list plus a trailing clause with an unlabeled triple of numbers.
Action: Added a topic sentence. The second line now leads with its own claim. The triple 0.882/0.928/0.906 is now labelled validation/held-out/unscreened panels (mapping p135/p2/p2u taken from the evidence comment). "Privileged" is kept.

### Results Detail: Gate Receipts and Qualification Gates

### ¶0 — This appendix gives the program's
Point: Roadmap.
Diagnosis: OK.
Action: None.

### ¶1 — The expanded study program ran
Point: The program stayed well inside its compute cap, and every executed branch reconciles with zero missing evidence.
Diagnosis: A ledger (hardware, then spend, then branches, then table, then replay). The reconciliation claim came last.
Action: The claim now leads. Spend is stated as a total with the snapshot split in one clause. Replay counts are one sentence and the table pointer comes last. Numbers kept: 336, 68.5244, 53.52, 15.9%, 1,152, 405, 90.

### ¶2 — Follow-up windows executed after the
Point: The follow-up windows ran on their own ledgers, were never summed with the program, and each stayed within its cap.
Diagnosis: A ledger with no claim. It also duplicates the Receipt Tables "Follow-up windows" paragraph, which is outside my slice.
Action: Added a topic sentence and turned the cap resize into a one-clause justification. Numbers kept (3.2086/12, 7.7998/36, 1.069/12, 20→36, 27.04, 29%).

### ¶3 — Of three earlier gates that
Point: Three earlier gates fixed the active algorithm matrix. The BFS pilot showed zero gain over random-valid and was gated off, the BFWS gate passed, and the 45-task manifest was never accessed.
Diagnosis: The lead sentence was a subordinate clause, and the "zero gain" reason was buried in the middle.
Action: The claim now leads, and the gate is stated as caused by the zero gain. The overlap-not-pinned sentence becomes a clause. All numbers are kept.

### ¶4 — The optimal A* arm over
Point: The third gate retired optimal A*, and the five-seed pilot predates the one-seed budget rule.
Diagnosis: The paragraph was disconnected from ¶3's "three gates".
Action: Now framed as "the third gate". Otherwise unchanged.

### Results Detail: Primary-Matrix Tables

### ¶1 — Table~\ref{tab:results-bfws} gives the BFWS
Point: The two tables keep what the model learned apart from what the controls achieve.
Diagnosis: The paragraph led with pointers, and the point came last.
Action: The point now leads, followed by the pointers.

### Caption tab:results-bfws
Point: Process SFT beats oracle-assisted random-valid on the BFWS development panel.
Diagnosis: The caption had no takeaway.
Action: The takeaway now leads. The development-stage and single-seed scope and "no final evaluation" are kept. Semicolon removed.

### Caption tab:results-primary-matrix
Point: Learned success appears only in the additive cells and never exceeds random-valid.
Diagnosis: The caption described the columns only.
Action: The takeaway now leads. "Descriptive" and "controls, not model abilities" are kept. RV abbreviation glossed. Semicolon removed.

### Results Detail: Primary-Matrix Paired Contrasts

### ¶0 — This appendix gives the paired
Point: Roadmap.
Diagnosis: OK.
Action: None.

### ¶1 — Paired whole-problem contrasts supply the
Point: SFT gains over the base only in additive cells and never beats random-valid, whose tie with the reference there means those cells cannot register choice.
Diagnosis: The lead sentence was procedural ("supply the gain"), and the claims came in sentences 2 and 3.
Action: The claim now leads, and "cannot measure beyond bookkeeping" is stated as the reason. The scope caveat is merged into one sentence. "Unexecuted final evaluation" now uses the prose name "frozen 45-task final evaluation". Numbers kept (+0.833, +0.903, 72).

### Caption tab:results-contrasts
Point: Same takeaway, stated for the table.
Diagnosis: The caption had no takeaway.
Action: The takeaway now leads, followed by how to read the cells.

### Results Detail: Secondary Panels

### ¶0 — This appendix reports the secondary
Point: Roadmap.
Diagnosis: OK.
Action: None.

### ¶1 — Modality. The per-modality rows of
Point: No executed enumeration-contract panel shows a modality effect, and parity limits would bound one if it appeared.
Diagnosis: The claim ("does not support an intrinsic modality effect") was in sentence 4. "Two caveats bound any such claim" was a stacked lead-in.
Action: The claim now leads. The caveat is restated as one causal sentence ("could not be read as … because parity is not established") plus its two reasons. All v5 counts are kept.

### ¶2 — Generalization and robustness v2. The
Point: The learned additive adapters succeed on most semantics-preserving perturbations, and shifted initial states hurt most.
Diagnosis: A number dump with no lead claim (one-sentence-per-split ledger).
Action: Added a topic sentence. The modality and algorithm splits are merged into one sentence. The saturation caveat is phrased as a reason. All counts are kept, because this is their appendix home.

### ¶3 — DAgger. Two DAgger iterations on
Point: DAgger does not improve BFS over exposure-matched continued SFT, and both stay far below random-valid.
Diagnosis: The claim ("The result is null.") was in sentence 4.
Action: The claim now leads. The win/loss/ties parenthetical is folded into the sentence. Counts are kept.

### Caption tab:results-dagger
Point: DAgger does not improve BFS over continued SFT.
Diagnosis: The caption had no takeaway.
Action: The takeaway now leads, followed by the column description.

### ¶4 — Model-generated successors. Replacing trusted successors
Point: The policy depends on trusted successors. Generated successors fail mostly on content (state identity and effects) rather than format.
Diagnosis: The claim was implicit, and the second point was buried in a long sentence.
Action: Added two short topic sentences. All counts are kept (45/45, 1/45, 65/109, 93, 66, 27/16/1, 119/1,536, 147.66, 64).

### ¶5 — Curriculum by modality. Nine training
Point: Training order shows no material ordering-by-modality interaction, and ceiling and floor effects bound what could appear.
Diagnosis: The claim ("No material … interaction emerged") came after the numbers.
Action: The claim and its limit now lead. The saturation facts move next to the ceiling/floor conclusion. The four intervals are kept in prose because this is their only home.

### ¶6 — Transfer. All 12 verified planning
Point: No planning adapter changes zero-shot accuracy detectably. The null is not equivalence, and the leakage screen finds no content overlap.
Diagnosis: The null was stated last ("The transfer result is a null.").
Action: The claim now leads. The McNemar/Holm procedure is merged into one sentence. Added "This null does not establish equivalence", which the Statistics appendix's materiality rule requires and which was missing here. Numbers kept (0.8156, 0.0227, +12, 7/564).

### Caption tab:results-transfer
Point: No adapter differs detectably from the base.
Diagnosis: The takeaway came at the end of the caption.
Action: The takeaway now leads. Semicolon removed.

### ¶7 — Second backbone. Two reduced-scope cells
Point: A second backbone reproduces the enumeration-contract pattern. Under BFS neither arm reaches a goal.
Diagnosis: A process lead ("Two reduced-scope cells trained and evaluated").
Action: Added a topic sentence. The numbers are unchanged.

### ¶8 — The replication cell (protocol v3,
Point: Under greedy best-first the same backbone gives high learned success that still trails random-valid.
Diagnosis: No lead claim.
Action: Added a topic sentence. All rates, usage, and intervals are kept (appendix home).

### ¶9 — Learned success under the enumeration
Point: Read with the identity audit, the InternVL cells fit the Qwen enumeration-contract pattern. The greedy cell shows contract fluency, not choice, and the BFS null is consistent with an algorithm difference.
Diagnosis: Close to OK, but there was no paragraph-purpose comment and no framing lead.
Action: Added a Paragraph-purpose comment and a framing topic sentence ("fit the pattern", hedged, not "track the algorithm"). "Therefore" links the null reading. Intervals are kept.

### Results Detail: Failure-Mechanism Calibration

### ¶0 — This appendix localizes where each
Point: Roadmap.
Diagnosis: OK.
Action: None.

### ¶1 — A frozen CPU-only calibration mined 2,910
Point: Each arm class fails in its own way. The base mostly cannot emit the format, learned arms mostly break the invariant early, and the oracle control runs out of budget late.
Diagnosis: A method lead with the profiles buried ("Three arm-level profiles emerge.").
Action: The profile claim now leads, followed by the method and then the counts. All counts are kept.

### ¶2 — Every baseline process-SFT episode under
Point: Failures concentrate where the primary matrix shows no learned success, and supervision leaves an invariant problem rather than a format problem.
Diagnosis: It opened on a bare statistic and repeated 229/407 and 72/407 from ¶1.
Action: The claim now leads. The repeated counts are removed from prose and remain in ¶1 and in Table tab:appendix-rejection (verified: rows 229 and 72). A `% (moved out of prose; …)` comment is added and the evidence comment is kept.

### Results Detail: Observation-Corruption Channel Tests

### ¶0 — This appendix reports the observation-corruption
Point: Roadmap.
Diagnosis: OK.
Action: None.

### ¶1 — The observation-corruption suite evaluated frozen
Point: Corrupting the text collapses the controller's success, while corrupting the images barely moves it.
Diagnosis: A method lead and a number dump with duplicated intervals.
Action: The claim now leads. Two intervals that duplicate table cells, $[-1.000,-0.833]$ and $[-0.278,+0.000]$, are removed from prose. They remain in Table tab:results-corruption, and a moved-out comment is added. The channel-isolation numbers are kept because they have no other home.

### Caption tab:results-corruption
Point: Text corruption collapses success and visual corruption does not.
Diagnosis: The caption had no takeaway.
Action: The takeaway now leads. Semicolon removed.

### ¶2 — A decomposition of the 72 published
Point: Masking and shuffling fail for different reasons. Masking destroys the output contract, while shuffling removes information as valid operations keep flowing.
Diagnosis: The claim sat inside the lead sentence's subordinate clause.
Action: The claim now leads, and the cross-cell sentence gets its own lead. Counts are kept.

### ¶3 — The language-channel claim survives only
Point: The text channel carries decision-relevant information only in the shuffled sense. This is a channel finding, not a modality claim.
Diagnosis: OK. "Sections~\ref{sec:results-menu} and~\ref{sec:results-native}" pointed to appendices.
Action: Changed to "Appendices~\ref{app:results-menu} and~\ref{app:results-native}". Purpose comment updated.

### Results Detail: Menu-Manipulation Receipts

### ¶0 — This appendix reports the menu-manipulation
Point: Roadmap.
Diagnosis: OK.
Action: None.

### ¶1 — Menu manipulation (stress test R1) probes
Point: Menu manipulation asks whether the policy responds to its menu's content.
Diagnosis: A stacked pointer "(the Image-Only Native Arms appendix, Appendix~\ref{…})" and a short-sentence ledger.
Action: The pointer is now "(Appendix~\ref{app:results-native})". Sentences are merged and the counts kept.

### Caption tab:results-menu
Point: Reordering changes nothing, while injected inapplicable actions end every episode.
Diagnosis: The caption had no takeaway.
Action: The takeaway now leads, followed by the column definitions.

### ¶2 — On the frozen native adapters (stress
Point: The distractor receipt shows the policy does not reject schema-valid inapplicable entries, but it cannot separate content reading from position habits.
Diagnosis: The permutation null led, and the claim was buried in sentence 4.
Action: The claim now leads. The logged wording is held verbatim ("does not reject schema-valid inapplicable menu entries", "Every episode ends on a distractor pick, 20/36 on the first decision", the 0.592–0.625 chance band, and "fixed-versus-random-position test remains unrun"). The permutation sentence moves to the end.

### Results Detail: Image-Only Native Arms

### ¶0 — This appendix reports the image-only
Point: Roadmap.
Diagnosis: OK.
Action: None.

### ¶1 — The native-arms follow-up (contract v2)
Point: The native arms remove every textual search aid except the grounded candidate menu, and both passed the pre-registered smoke gate with full replay.
Diagnosis: A ledger. The gate history ("v1 … retained as history. The v2 amendment …") sat ahead of the result.
Action: The claim now leads. The gate result comes before its provenance, and the history becomes one clause. Numbers are kept (K=8, 62/62, 0.5, 512, 16, 17, 216/216, 72/72, 3.2086/12).

### ¶2 — On the clean panel, both arms
Point: Both arms still solve every clean task, but the saturated control leaves no room to call this an advantage.
Diagnosis: No lead claim.
Action: Added a topic sentence. Added "neither establishes equivalence" next to the non-material contrasts, as the Statistics materiality rule requires. Intervals are kept (appendix home).

### ¶3 — The pre-registered corruption payoff is
Point: The images-only hypothesis fails because corrupting every seq image changes nothing. The post-hoc menu reading is bounded by the identity audit.
Diagnosis: Close to OK.
Action: Merged "answered in the negative" into the lead and added a short bridge ("That reading has a limit.") before the identity-audit bound.

### ¶4 — The degraded-strain test (stress test
Point: The native arms reach ceiling on the two strains where the full scaffold degraded. The comparison is post-hoc and unpaired and cannot show that the removed text carried signal.
Diagnosis: A process lead, a stacked pointer "(Secondary Panels appendix, Appendix~\ref{…})", and the unpaired caveat stated twice.
Action: The claim and caveat now lead. The pointer is now "(Appendix~\ref{app:results-secondary})". The two caveat sentences are merged into one. Counts are kept.

### Word counts (non-comment)

I could not compute these. This slice has no shell tool, so I could not run `sed -E 's/(^|[^\\])%.*$/\1/' FILE | wc -w`, and the file is shared with two other appendix writers, so a whole-file count would mix our slices. [INFERENCE] My estimate for the owned range is +150 to +250 words net (+4 to +6%). Topic sentences added about 400 words. Removing duplicate intervals, repeated counts, stacked pointers, and duplicated caveats saved about 200. The integrator should run the command once all three appendix slices have landed.

### Cross-file / cross-section issues noticed (not fixed)

1. The Gate Receipts ¶2 (follow-up window spend: 3.2086, 7.7998, 1.069, 27.04, 29%) duplicates the Receipt Tables "Follow-up windows" paragraph (`\paragraph{Follow-up windows.}`, another owner's section). One copy could become a pointer. Numbers would survive in either.
2. The Modality Adapters appendix ("Text-scaffold caveat" and the paragraph after it) restates the corruption and native-arm numbers (−0.944, −0.722, −0.111, 18/18, 0.000 [0.000, 0.000]) that also live in my slice. Another owner's section.
3. The Modality Adapters and Observation Contract section has no `\label`, so the parity caveat in my Modality paragraph cannot point to it. I stated the caveat in full instead.
4. The Statistics materiality rule says every non-material contrast needs an adjacent non-equivalence sentence. I added it in Transfer and Native ¶2. The Curriculum paragraph's intervals ("include zero") and the Second-backbone cross-backbone contrasts still lack one. I left them unchanged to avoid adding caveat text beyond these two fixes; the integrator may want it.
5. It is kept per the no-comment-deletion rule.

## Prose audit: AppendixC slice

File: `iclr2026/iclr2026_conference_appendix.tex`, from `\section{Results Detail: Choice-Frontier and Comparator-Zoo Receipts}` to end of file. Table bodies and labels are unchanged. No number was added, altered, or recomputed. Two numbers moved out of a paragraph but stay in the PDF: the duplicate M4 17.4% / 26.9% / 54.5% sentence (still in the M4 paragraph and Table tab:appendix-m4) and the closing protocol paragraph (merged, see below). Nothing else was deleted from visible text. No STATUS line was added, because AppendixA already added the single shared line at the top of the file.

### Choice-Frontier and Comparator-Zoo Receipts (app:results-cf)

### app:results-cf ¶1 — This appendix documents the first measurement
Point: The first measurement and the zoo show that the contract separates random-valid from the exact reference, but they cannot calibrate choice quality.
Diagnosis: Signpost only ("holds the receipts ... for readers checking"). It made no claim.
Action: Rewritten as a claim with its limit. No numbers.

### app:results-cf ¶2 — The first adapter ("Learned adapter" in
Point: The first adapter's corpus reproduces the exact reference and contains real choices.
Diagnosis: Ledger. It ran six receipts with no topic sentence, and "(58 episodes bit-exact)" was a parenthetical receipt.
Action: Added a topic sentence and a one-time gloss (first adapter = "Learned adapter" in the tables), then split the receipts into readable sentences. The CHOICE_SENSITIVE final-audit fact from the orphaned closing paragraph moved in here, with an evidence comment. All numbers kept.

### Caption tab:results-cf
Point: Random-valid falls well below the exact reference, and the learned adapter emits no invalid operation.
Diagnosis: Definitions came first and there was no takeaway. It had a semicolon.
Action: Takeaway first, the semicolon split into two sentences, and the non-comparability caveat kept.

### app:results-cf ¶3 — The first measurement shows that the
Point: The contract registers choice (the controls separate), but the first adapter does not separate from random-valid.
Diagnosis: Number dump that opened with bootstrap settings. The claim was buried after three intervals.
Action: Claim first. The bootstrap settings (seed 61813, 10,000) moved to the last sentence. The storage seed frequency 0.2 and "percentile" intervals were merged in from the orphaned closing paragraph, with a copied evidence comment. Every interval kept. The descriptive, no-learning-to-plan, and no-equivalence caveats are kept in full.

### app:results-cf ¶4 — Clustering by task leaves both readings
Point: Task-clustered intervals, which respect the repeated measures, leave both readings unchanged.
Diagnosis: Two disconnected facts with no claim.
Action: Added a topic sentence and a "because" link, and stated what each interval means (it still reaches zero / still excludes zero). Intervals kept.

### Comparator zoo ¶1 — The comparator zoo is an exploratory
Point: The zoo's three rule selectors give an exploratory comparison that is not information-matched.
Diagnosis: Selector definitions sat in a separate one-sentence paragraph two paragraphs later. "Exploratory" was not motivated.
Action: Merged the selector definitions here. Two explicit reasons now back "exploratory" and "not information-matched".

### Caption tab:results-zoo
Point: No rule selector exceeds random-valid on M1, so no comparator lies between random-valid and the exact reference.
Diagnosis: Reading instructions only, with a semicolon.
Action: Takeaway first (checked against the table: .1250, .0694, and .0556 are all < .1389). The semicolon was removed.

### Comparator zoo ¶2 — The zoo bounds the first adapter
Point: The zoo cannot calibrate choice quality, because no comparator lies between random-valid and the exact reference.
Diagnosis: Buried claim. It repeated the M4 numbers and the Counterfactual pointer that the M4 paragraph states in full.
Action: Claim first. The duplicate M4 sentence was removed, with a "(moved out of prose; kept in the M4 paragraph below and Table tab:appendix-m4)" comment, and the M4 evidence comments were kept. The Holm/Pareto result and the non-equivalence caveat are kept.

### Zoo receipts ¶1 — The zoo reuses the model's
Point: Selectors and model face the same menus and budgets. The paragraph then gives coverage, replay, and C* receipts.
Diagnosis: Ledger with no topic sentence.
Action: Added a topic sentence and kept every receipt. The C* list keeps its semicolons because its items contain commas.

### Zoo receipts (former selector paragraph)
Action: Merged into Comparator zoo ¶1. Nothing was lost.

### Zoo receipts ¶2 — Post-hoc diagnostics on the stored episodes
Point: There is no heap-head agreement beyond chance, and the last-label excess does not establish a position habit.
Diagnosis: Diagnostics chained with the M5 result in one paragraph (two points). "Teacher's heap-head" used a retired name.
Action: Claim first, "teacher's" changed to "reference's", and a stacked pointer ("Counterfactual appendix (Appendix~\ref{})") reduced to Appendix~\ref{}. M5 was split out.

### Zoo receipts ¶3 — M5 is too small to
Point: The M5 subset is one task and therefore descriptive only.
Diagnosis: Previously buried at the end of the M4 paragraph.
Action: New paragraph with the same sentences, and the M5 evidence comment copied beside it. .3125, .075, and .625 kept.

### Caption fig:zoo-m1
Point: Only the exact reference stands apart on M1, and all non-exact intervals overlap.
Diagnosis: Values listed before the takeaway.
Action: Reordered so the takeaway comes first. Every value and clause is kept. The logged "caption fixed by wave2-contract" comment is kept, with a note that the brief's caption rule caused the reorder.

### app:results-cf closing paragraph (former) — The choice-frontier contrasts use percentile
Point: Protocol leftovers for the contrasts.
Diagnosis: Orphaned receipts after the figure, with no claim.
Action: Merged. "Percentile" and the storage 0.2 went into ¶3, and CHOICE_SENSITIVE/144 went into ¶2. The source-conflict and evidence comments stay in place with a merge note and are copied at their new homes.

### Submission-Order Counterfactual (app:results-counterfactual)

### ¶1 — This appendix shows that the enumeration
Point: The 48/48 identity comes from the executed heap-serial rule.
Diagnosis: Signpost only.
Action: Rewritten as a claim.

### ¶2 — The counterfactual changes only the rule
Point: The counterfactual changes one thing, the heap-serial rule.
Diagnosis: It opened with process history ("A CPU-only follow-up with a protocol committed before its outputs").
Action: The single-variable design comes first, and the protocol timing sits in one clause at the end. Numbers kept.

### Caption tab:appendix-counterfactual
Point: Random-valid matches the reference on every pair only under the executed rule.
Diagnosis: Reading instructions only.
Action: Added the takeaway first.

### ¶3 — The 48/48 identity is a property
Point: The identity is a property of the executed serial rule.
Diagnosis: The conclusion came last, after the verdict string.
Action: Conclusion first, then 19/48, the failed prediction and verdict string, and the divergence location. Wording uses "confirms", not "predicted", as the CONTEXT framing requires.

### ¶4 — Clustering by task keeps the first
Point: Task clustering keeps the last-label excess but not the agreement gap.
Diagnosis: Receipts came first and the claim was buried.
Action: Claim first. Numbers kept.

### Caption tab:appendix-m4
Point: Only the last-label excess has an interval that excludes zero.
Diagnosis: The caption was vague ("differences with uncertainty concern").
Action: Takeaway first, then how to read the columns.

### Choice-Frontier Validation Panel and Ladder (app:results-ladder)

### ¶1 — This appendix shows how the validation
Point: The panel was frozen in advance, and the ladder passes on it.
Diagnosis: Signpost.
Action: Rewritten as a claim.

### ¶2 — The validation panel was fixed by
Point: The panel was fixed by rules committed in advance.
Diagnosis: Acceptable, but it opened with process history as a bare fact.
Action: Turned into a topic sentence. Numbers kept.

### Caption tab:appendix-ladder-panel
Point: Random-valid reached the goal in some but not all screening episodes on every task.
Diagnosis: Definitions only, with a semicolon.
Action: Takeaway first (Screen values are 1 to 4 of 10). The semicolon was removed.

### Caption tab:appendix-ladder-arms
Point: M1 falls in order from the reference down the rungs to random-valid.
Diagnosis: Definitions only, with a semicolon.
Action: Takeaway first (0.875 > 0.793 > 0.603 > 0.347 > 0.021). The semicolon was removed.

### Caption fig:budget-curves
Point: The rungs order correctly on all three panels, and the adapter's area exceeds random-valid's.
Diagnosis: The title was descriptive ("How solved fraction changes"), and the caption had a semicolon.
Action: Takeaway first (the areas are the M1 values in tab:appendix-panel-arms). Privileged-rung and three-seed-band caveats kept.

### ¶3 — The ladder test passes on the
Point: The ladder passes because every adjacent gap has a positive lower bound.
Diagnosis: It opened with a replay receipt, and the claim was implicit.
Action: Claim first. The four gaps are labelled inline, with the observation that they widen toward the random end (0.082 < 0.190 < 0.256 < 0.326). The replay receipt moved last.

### ¶4 — Three documented deviations affect how the
Point: The deviations affect generation and rendering, not panel membership.
Diagnosis: "Three deviations are documented." was a list header with no claim.
Action: Claim first, with the items marked First/Second/Third.

### Scaled Adapter and Seed Replication (app:results-adapter)

### ¶1 — This appendix documents the adapter behind
Point: This section is the adapter's documentation, and the gain holds at every seed.
Diagnosis: Signpost.
Action: A one-sentence claim-bearing opener.

### ¶2 — Each part of the adapter protocol
Point: Each part of the protocol was frozen before the step it governs.
Diagnosis: A bare process list.
Action: Topic sentence with a colon introducing the list. The estimand and rule are kept.

### ¶3 — The training corpus shares no task
Point: No task overlaps an evaluation panel, and the target is not placed last more often than chance.
Diagnosis: A bare count chain.
Action: Topic sentence added. Numbers kept.

### ¶4 — The adapter changes the first adapter's
Point: Data changed, recipe unchanged, and every execution check passed.
Diagnosis: Receipt chain.
Action: Only a topic sentence was prepended.

### Caption tab:appendix-adapter-tasks
Point: The seed-17 gain is uneven across tasks.
Diagnosis: The caption had no takeaway.
Action: Added the takeaway: large on both storage and both elevators tasks, and zero on both blocksworld tasks (checked against the table cells).

### ¶5 — Four documented choices shaped this run,
Point: Only the single-seed scope limits what the run shows, and the replication closed that gap.
Diagnosis: A list header followed by an unranked fact chain.
Action: Claim first, with the items enumerated. Replay facts kept.

### ¶6 — On the validation panel the adapter
Point: The adapter beats random-valid at every seed but sits near or below the 0.75 rung.
Diagnosis: Number dump with no claim that mixed two points (D/S and last-label).
Action: Claim first, with each interval given its meaning ("every lower bound is positive", "below the rung"). The last-label rates were split into their own paragraph, and the evidence comments were split to match. All values kept.

### ¶7 — The adapter also picks the last
Point: The adapter picks the last label less often than the first adapter did (descriptive).
Diagnosis: Previously buried in ¶6.
Action: New paragraph with the same numbers and its evidence comments.

### Held-Out Panels (app:results-panels)

### ¶1 — This subsection shows that both fresh
Point: Both panels were frozen before evaluation.
Diagnosis: Signpost ("for readers checking").
Action: Claim, and the P2/P2u symbols defined once.

### ¶2 — The held-out panel repeats the validation
Point: The panel repeats the validation construction on fresh seeds, so its tests are confirmatory.
Diagnosis: A count ledger with no topic sentence.
Action: Topic sentence added, the exclusion counts regrouped in parentheses, and the conclusion stated last.

### ¶3 — The unscreened panel drops the random-valid
Point: Dropping the screen shows, descriptively, whether the gain survives without it.
Diagnosis: Receipts only, with no purpose stated.
Action: Purpose-bearing topic sentence (CONTEXT wording). Numbers kept.

### ¶4 — The seed range was extended once,
Point: One pre-evaluation extension, with all other rules fixed.
Diagnosis: It narrated process history chronologically, and "before any evaluation episode" appeared twice.
Action: Conclusion first, and one duplicate clause removed. Every amendment fact is kept, because this is the amendment's full disclosure.

### ¶5 — The ladder test passes on the
Point: The ladder passes on the held-out panel and, descriptively, on the unscreened panel.
Diagnosis: It opened with a table pointer, and the claim came after four intervals.
Action: Claim first, with direction glossed ("from the exact reference down to random-valid"). All eight intervals kept. This is now the appendix home of the +0.130 [+0.070, +0.190] gap.

### Caption tab:appendix-panel-arms
Point: On every panel the adapter's mean sits between random-valid and the exact reference.
Diagnosis: No takeaway, and a semicolon.
Action: Takeaway first (0.306 / 0.432 / 0.151 against 0.021 / 0.016 / 0.002 and 0.875).

### ¶6 — Every seed's gain over random-valid has
Point: Every per-seed D lower bound is positive, but the rung separations need care.
Diagnosis: It opened with a table pointer.
Action: Claim first (checked: every per-seed lower bound in tab:appendix-seed-d is positive). The non-equivalence and small-sample caveats are kept.

### Caption tab:appendix-seed-d
Point: The adapter separates above random-valid everywhere, and above the 0.75 rung only on the held-out panel.
Diagnosis: No takeaway, and a semicolon.
Action: Takeaway first (verdict column: D3 ✓ ×4; S vs 0.75 is ✓ only for P2).

### ¶7 — Over the validation and held-out panels
Point: No single domain carries the gain, while on the unscreened panel it rests on four of twelve tasks.
Diagnosis: It opened with a table pointer.
Action: Claim first. "Four of twelve" is copied from the table's P2u row (4/8/0). Numbers kept, and the descriptive label kept.

### Caption tab:appendix-concentration
Point: Removing any one domain keeps D3 positive with a positive lower bound.
Diagnosis: No takeaway, and a semicolon.
Action: Takeaway first.

### Caption fig:task-gains
Point: Most tasks gain, and the unscreened panel's improvement is concentrated on four tasks.
Diagnosis: The takeaway was in the middle, and a semicolon.
Action: Reordered so the takeaway comes first.

### Illustrative Search Episodes (app:qualitative)

### ¶1 — These rule-selected traces illustrate what the
Point: The traces are illustrations, not effect estimates.
Diagnosis: OK.
Action: Unchanged. `qualitative_figures.tex` was not touched.

### DAgger Ablation (app:results-cf-dagger)

### ¶1 — This subsection reports the pre-registered DAgger
Point: One round at one seed produces no detectable change.
Diagnosis: Signpost.
Action: States the result.

### ¶2 — The ablation asks whether one round
Point: It states the question the ablation tests.
Diagnosis: A procedure list with no question.
Action: The question comes first. Endpoints kept.

### ¶3 — A deadline cut the ablation to
Point: The cut to one seed and half the corpus was made before any outcome.
Diagnosis: It opened with a timestamp (process history).
Action: Conclusion first, and the timestamp kept in the second sentence. "Half the planned corpus" is copied from the Follow-Up Limits paragraph (comment added).

### ¶4 — One DAgger round at one seed
Point: The ablation is inconclusive.
Diagnosis: It opened with a replay receipt, and the conclusion came last.
Action: Conclusion first, the replay moved last, and all intervals kept.

### Zero-Shot Policy (app:results-cf-zeroshot)

### ¶1 — This subsection shows that the untrained
Point: The untrained base scores at the random-valid level.
Diagnosis: Signpost.
Action: Rewritten as a claim.

### ¶2 — The zero-shot policy is the pretrained
Point: This is the policy's definition.
Diagnosis: OK, apart from a long opening sentence.
Action: The opening sentence was split. Content unchanged.

### ¶3 — A trained second backbone was ruled
Point: The trained second backbone did not fit the compute cap.
Diagnosis: The reason came after the arm name.
Action: Claim first. Numbers kept.

### ¶4 — The zero-shot base scores at the
Point: At the random-valid level and below both the rung and the adapter, as pre-registered.
Diagnosis: One nine-sentence paragraph mixed endpoints, behaviour, prediction, and replay, and it opened with a table pointer.
Action: Split into ¶4 (endpoints, stage labels, margin detail, M1, prediction) and ¶5 (behaviour, replay). The evidence comments were split to match, with a "continued" marker and the prediction line copied. All numbers kept.

### ¶5 — The base always emits a valid
Point: Its choices are valid, and they agree with the reference's heap head at about the chance rate.
Diagnosis: Previously buried inside ¶4.
Action: New paragraph that labels which panel each value belongs to.

### Caption tab:appendix-zeroshot
Point: The base is not separated from random-valid and is below both the rung and the adapter.
Diagnosis: No takeaway, and a semicolon.
Action: Takeaway first (checked: every D3 interval includes zero, and every S and A row is ▼).

### External Identity Audit (app:results-external)

### ¶1 — This appendix shows how ScienceWorld was
Point: ScienceWorld was chosen from a survey, and it serves as a positive control.
Diagnosis: Signpost.
Action: Claim, using the CONTEXT term "positive control".

### ¶2 — The survey found no published evaluation
Point: No published interface uses the enumeration type, and ScienceWorld was the most cited feasible candidate.
Diagnosis: One LaTeX paragraph carried three points (survey, budget units, LFG) and a stacked pointer ("the later audit in the LLM-First Search Audit appendix (Appendix~\ref{})").
Action: Claim first. The LFG sentence moved beside the type-A finding. The pointer was reduced to Appendix~\ref{}. "The only saturated prediction" became "the only candidate predicted to saturate" (Results wording).

### ¶3 — The surveyed interfaces differ in how
Point: Only LLM-First Search counts tokens, which a zero-token chooser never exhausts.
Diagnosis: Previously a trailing fact inside ¶2.
Action: New paragraph with a topic sentence and a pointer. A new evidence comment points to the table's budget-unit comments.

### Caption tab:appendix-survey
Point: Both audited external interfaces diverge, and only our enumeration contract is identical.
Diagnosis: A legend only.
Action: Takeaway first (Audit column: ScienceWorld ✓, LFS ✓, ours = 48/48). The semicolon was removed. The table footnote is unchanged (table content).

### ¶4 — On ScienceWorld success measures choice, because
Point: Success measures choice there.
Diagnosis: A protocol-first ledger.
Action: Claim first, and the long sentence split. Numbers kept.

### ¶5 — The audit covers a narrow slice
Point: The audit's scope and version are narrow.
Diagnosis: No topic sentence.
Action: Topic sentence added. Caveats kept.

### LLM-First Search Audit (app:results-external-lfs)

### ¶1 — This subsection shows why a token
Point: A token budget cannot bind a zero-token chooser.
Diagnosis: Signpost ("for readers asking").
Action: Claim.

### ¶2 — LLM-First Search keeps every unexpanded alternative,
Point: The frontier keeps every alternative, so a zero-token chooser becomes a complete search.
Diagnosis: One paragraph mixed the interface mechanics with tasks, budgets, and deviations.
Action: Split. This paragraph carries the mechanism, with a copied evidence line.

### ¶3 — The audit runs the upstream code
Point: The upstream code runs unchanged under the paper's budgets, with four declared deviations.
Diagnosis: The deviations were run together in one sentence.
Action: Topic sentence added, and one sentence per deviation. The original evidence block stays after this paragraph.

### ¶4 — Random-valid diverges from the reference in
Point: Random-valid diverges early in every pair.
Diagnosis: Previously one sentence inside a 13-sentence paragraph.
Action: Split out, with the matching evidence lines.

### ¶5 — Under the paper's token budget random-valid
Point: Saturation follows by construction.
Diagnosis: Buried mid-paragraph.
Action: Claim first, followed by the mechanism and the expansion counts. The evidence lines were split verbatim to match.

### ¶6 — A budget counted in decisions lets
Point: A decision-counted budget lets success register choice.
Diagnosis: Buried at the end.
Action: Claim first. The predictions, 0.768, and the ledger are kept. The "budget curve in Table~\ref{tab:appendix-lfs}" wording is kept (see open issues).

### Caption tab:appendix-lfs
Point: Saturated under the token budget, far below the reference under the matched budget.
Diagnosis: No takeaway, and a semicolon.
Action: Takeaway first.

### Seed Replication and Follow-Up Limits (app:results-boundary)

### ¶1 — This appendix shows that the enumeration-contract
Point: The replication reproduces the seed-17 verdicts.
Diagnosis: Signpost.
Action: Claim.

### ¶2 — Both replicated enumeration-contract cells give the
Point: Same verdict at all three seeds.
Diagnosis: A 12-sentence ledger that mixed results with scope.
Action: Claim first, then the results. The scope sentences were split into ¶3. Values kept, including "no sign flip" (the Introduction uses these numbers).

### ¶3 — The replication covers only part of
Point: Coverage is partial, so aggregation is descriptive.
Diagnosis: Previously buried at the tail of ¶2.
Action: New paragraph. The "Cell A" sentence is kept verbatim. A stacked pointer ("the Image-Only Native Arms appendix, Appendix~\ref{}") was reduced to Appendix~\ref{}.

### ¶4 — Every follow-up window is development-stage, and
Point: All windows are development-stage, and none touched the frozen 45-task final evaluation.
Diagnosis: The claim ("none accessed") was buried near the end.
Action: The claim was moved to the topic sentence. The list is kept.

### Final primary evaluation prerequisites — No authorized protocol yet exists
Point: No final protocol exists until four decision groups are recorded.
Diagnosis: OK (topic sentence first). The comment marks it as migrated verbatim.
Action: Unchanged.

### Decision Contracts (app:design-contracts)

### ¶1 — The two decision contracts differ in
Point: The contracts differ in what the policy emits and what the runtime owns, so their results are not comparable.
Diagnosis: A bare table pointer.
Action: Claim plus pointers. The old purpose comment is kept as "Former purpose".

### Caption tab:design-contracts
Diagnosis: OK (the takeaway is already first).
Action: Unchanged.

### Use of LLM Statement (app:llm-usage)
Diagnosis: Author-dictated wording.
Action: Unchanged.

### Word counts
`sed -E 's/(^|[^\\])%.*$/\1/' FILE | wc -w` was **not run**: this session has no shell tool, so I could not measure it. [INFERENCE] The net change in my range is modest growth, roughly +400 to +600 words. Added topic sentences (about 45 paragraphs) and caption takeaways (16 captions) account for the growth. The removed duplicate M4 sentence (about 50 words), the merged closing protocol paragraph, and a few removed repeated clauses offset part of it. The integrator should run the command on the whole file before and after (git) to get exact figures.

### Cross-file notes (not fixed)
1. `results.tex` L136 still reads "The smallest held-out adjacent gap is $+0.130$ $[+0.070, +0.190]$". The value stays in Held-Out Panels ¶5, so the Results slice can drop it safely.
2. `results.tex` L118 says the reused-panel identity audit diverged on "9/9 tasks" and points to app:results-cf. The app:results-cf prose never states 9/9. The number lives in the comparator/identity comments (18 divergent pairs = 9 tasks × 2). Consider pointing to Table tab:appendix-survey (18/18) instead.
3. The LLM-First Search results paragraph says "the budget curve in Table~\ref{tab:appendix-lfs}". The table shows matched-budget rows, not a curve. The curve values (0.0775 to 0.19, AUC 0.135) exist only in a `% Caption curve:` comment and do not appear in the visible caption. I kept the wording because the claim belongs to the source. The integrator or the Results owner should either add the curve values to the tab:appendix-lfs caption or say "the matched-budget rows".
4. Source conflict retained: `issue-132-closeout.md` gives "max menu 315" and describes the corpus as independent, while `report.json` gives a 222 maximum and a replay-derived corpus. The artifact wording is used, as before.
5. The appendix still names "the first adapter" inside app:results-cf (with a table gloss). CONTEXT says the first adapter is "named once in Results", so this is consistent as long as Results keeps that naming.
