# Manuscript Changelog

The record of what changed in the ICLR 2026 manuscript and why. Newest first. Each entry names the commit, the scope of the change, and the ticket or request it answered. Claim vocabulary and boundaries live in `CONTEXT.md`.

## 2026-09-26 · Teaser caption rewritten as a claim chain, panels retitled (fig_teaser.py, abstract.tex)

- Changed: the Figure 1 caption leads with the through-line "We supervise search traces, not plans: all four algorithms are learnable, at data costs an order of magnitude apart, and the learned control is textual" --- one clause per panel --- and the panel sentences are reading guides only. Removed from (b) the methods detail ("each line joins a 512-record cell to a larger development run on its own task panel", "not a matched comparison or a learning curve"), and from (c) the scope/statistic wording; those caveats stay in `results.tex` (caption line 41: "not a matched-size comparison"; prose line 22: no corpus tested between 512 and about 11,900) and `discussion.tex` (Data cost limitation). Caption 52 → 54 whitespace tokens.
- Changed: `fig_teaser.py` panel titles are claims in reading order: "a  The trace, not the plan", "b  An order of magnitude apart", "c  Channel: text" (were "Trace, not plan", "Data cost", "Which channel?"). Widths re-measured at 7.5 pt bold; panel (a) uses the shorter form because "What we supervise: the trace" left only 0.04 in before panel (b)'s title.
- Verified against the evidence repository, not against manuscript prose: ferry episode 11 decisions / 4 expansions and the 4-action plan (`…/ferry-compact-915000/…best_first_add_greedy-exact_reference.json.gz` + `scenes/catalog.json.gz`); 512-record grid 125/144 additive vs 0/24 BFS and BFWS + 512-record receipts; endpoints 11,911 / 12,994 / 14,225 / 47,780 and their controls; corruption −0.722 [−0.889, −0.500] and −0.111 [−0.278, 0]. A sweep of `data/**/manifest.json` plus the training receipts under `outputs/` (484 manifests, 121 reports) found no BFS/BFWS corpus between 512 and 11,911 records; the only in-window values are additive 8,342 / 9,398 and the 4 × 512 = 2,048 grid total, so the Results data-gap sentence stands.
- Rebuilt: `fig_teaser.{pdf,svg,png}` re-rendered with every evidence assertion passing, PNG inspected at final size (no overlap or overflow); `manuscript.pdf` and `iclr2026/iclr2026_conference.pdf` rebuilt, 53 pages, main text still ends on page 9, 0 undefined references.
  Why: author feedback 2026-09-26 --- the teaser read as three unrelated result panes with no through-line, and its (b) sentence carried methods detail a teaser should not.

## 2026-09-26 · Abstract back-reference fix (abstract.tex)

- Changed: one phrase in the abstract's data-cost sentence, "than the $A^*$ variants" → "than the additive variants". The pair it names is greedy best-first search plus weighted A* ($w{=}3$), and greedy best-first search is not an A*-family algorithm (priority $h_{\rm add}$, no path-cost term), so the old back-reference contradicted Section 3's split citation (Bonet \& Geffner for greedy, Hart/Pohl for weighted A*). The new wording matches the body's own label for the pair, "the two additive variants" (`results.tex` L11, `search_process_policy.tex` L42, `introduction.tex` L25/L63, `discussion.tex` L38).
- Unchanged: the algorithm list itself, "greedy and weighted-$A^*$ best-first search with the additive heuristic", which is correct and stays aligned with `introduction.tex` L12. Word count unchanged by the swap.
- Rebuilt: `manuscript.pdf` and `iclr2026/iclr2026_conference.pdf` (53 pages); page 1 text checked.
  Why: author request 2026-09-26 after the algorithm-naming review; this was the only defect found in the sentence.

## 2026-09-26 · Figure 1 teaser revision (fig_teaser.py, abstract.tex teaser block)

- Changed: (a) legend shortened to "bold: actual plan · numbered: reasoning trace"; panel narrowed to 1.9 in so (b) gets 2.5 in; goal label moved under the scene; two-digit step circles enlarged.
- Changed: (b) broken-axis dot plot replaced by a log-x line plot. Each line goes from the 512-record main-grid cell to its large-corpus development endpoint; colour marks the algorithm, solid lines are text and dashed lines are visual. Endpoints: BFS text 12,994 and visual 11,911; BFWS text 47,780 and visual 14,225; WA* 9,398 and GBF 8,342 (text #65/#66, visual #75). Random-valid rings and the multimodal arm, which has no large-corpus endpoint, removed. The caption keeps the "not a matched comparison" warning.
- Changed: (c) now shows only the multimodal adapters: shuffled text −0.72 vs blank images −0.11, as vertical 95% CIs.
  Why: author feedback 2026-09-26 (legend too long, (a) crowding (b), dot plot unreadable without lines, (c) should show only the multimodal arm under the two corruptions).

## 2026-09-26 · Storyline v2: main text rewritten around trace learning (all main-text .tex, appendix, figures)

Author-frozen abstract fixes the storyline: the contribution is an empirical study of a VLM fine-tuned on search traces (not plans) of four algorithms across 12 PDDL domains and text / visual / multimodal observations. Validate-before-score material (Box 1, identity audit, ladder, choice-frontier scoring, external audits) moves to the appendix. Old main text snapshotted at `drafts/pre_storyline_v2/`.

- Abstract: author's v4 text entered by the author; orchestrator fixed typos only ("are learnable", "costs at most 0.11", double space). Abstract text otherwise untouched.
- Introduction (`introduction.tex`, ~835 words): full rewrite. Plans-vs-traces gap, what we do in plain words, findings F1-F4 with honest qualifiers (unmatched development panels; robustness tested on the additive adapters and juxtaposed, not compared, with belcamino2026generalization; FOLIO gain consistent but not significant after Holm; candidates stay textual in every observation type), three contribution bullets, one evidence-boundary sentence. Runtime supplies visited flags and BFWS novelty values; the model reads them and names each step.
- Related Work (`related_work.tex`, light edits): paragraph 1 adds Belcamino's finding that symbol anonymization and compact plan serialization cause significant drops despite preserving plan semantics (backs the abstract's robustness contrast); paragraph 4 forward-reference retargeted to sec:results-modality; paragraph 5 condensed to credit the controls the main text still uses, with the audits in the appendix.
- Section 3 (`search_process_policy.tex`, retitled "Learning to Execute Search from Traces", ~550 words): task formulation, per-algorithm valid-step content verified in code (BFS: FIFO position and head-removal flag derived; BFWS: priority-implied frontier position copied; additive: source and one candidate only, runtime owns values and heap), observation types (only state facts become images), trace training target vs plan target. DAgger and contract-comparison machinery dropped.
- Section 4 (`experimental_design.tex`, ~475 words): models, main grid, 512/1/16/seed-17 recipe, large-corpus runs as a data-cost probe explicitly not a matched-size comparison, random-valid as an oracle-assisted validity bound that necessarily matches exact in the additive cells, success metric, analysis list, evidence boundary. Box 1 and the validation-protocol paragraphs removed (re-homed in the appendix).
- Results (`results.tex`, ~1,375 words, one new main table `tab:results-main` with main grid + large-corpus runs): sec:results-data-cost (125/144 at 512 records; BFS 12,994 x3 and BFWS 47,780 x2 development runs; visual #75 per-algorithm counts 11,911/14,225 from attempt-001/training.json; BFS failures 68/72 wrong queue fields and 4/72 premature retires, BFWS 72/72 malformed first operations; no corpus size between 512 and ~11.9k tested), sec:results-modality (text carries the learned execution; masking destroys format so the claim rests on shuffling), sec:results-robustness (128/150 vs 0/150 with per-family counts; Belcamino juxtaposition with no plan-only baseline), sec:results-transfer (BFWS FOLIO 0.600 -> 0.645-0.660 under all three observations; 0/36 survive Holm, min adjusted p 0.82; these are the 512-record adapters, so the BFWS adapter that gains on FOLIO solves 0/24 planning tasks). InternVL3.5-8B replication (greedy 31/36, BFS 0/36) and seed replication in sec:results-data-cost. 12,994 evidence path corrected to `data/bfs_pilot_v6/ms-swift-process/manifest.json` counts.train.
- Discussion and Conclusion (`discussion.tex`, ~590 words): traces as a practical supervision target; BFS queue-bookkeeping vs BFWS operation-format split as an untested explanation; observation-channel result and the appendix frontier-choice study as the two open problems; limitations (development stage, main-grid single-seed scoping since the BFS large-corpus run used five seeds, untested 512-11,911 corpus gap, no plan-only baseline, non-significant transfer); conclusion ends on the research direction.
- Appendix (`appendix.tex`): restructured to trace-learning-first order; demoted main-text material re-homed with labels kept (`sec:results-identity`, `sec:results-primary`, `sec:results-boundary`, `sec:results-ladder`, `sec:results-choice-frontier`, `sec:results-adapter`, `sec:results-external`, `box:procedure`, `fig:ladder`, `tab:results-panels`); `tab:results-identity` superseded by `tab:results-main`; captions reframed to the new storyline without changing numbers; new `Illustrative Search Episodes` section (`app:qualitative`); BFS/BFWS 512-record failure split added to `app:results-failures` and `tab:appendix-rejection` caption annotated; transfer caption and paragraph now lead with the BFWS FOLIO gain and keep the Holm null; robustness v2 paragraph carries per-family counts.
- Figures: teaser (`fig:teaser`, 5.5x1.85 in) redrawn as (a) ferry plan-vs-trace spine (4 plan actions inside 11 greedy best-first operations), (b) success vs training records, filled 512-record grid vs hollow development runs with random-valid rings, no connecting lines (broken axis; not a learning curve), (c) corruption forest plot (shuffled text vs blank/degraded images; blank and degraded merged after asserting 36/36 identical paired outcomes). `fig:contracts` (5.5x2.35 in) rebuilt as the runtime loop plus per-algorithm "one valid step" columns with grey copied vs orange derived fields. Three new appendix trace figures (`fig:qual-trace-solved`, `fig:qual-trace-failures`, `fig:qual-trace-corruption`) on blocksworld-expanded-911101; old choice-frontier qualitative figures moved to `qualitative_figures_choice_frontier.tex`; `fig_enumeration_example.*` deleted. All five generators assert their evidence and were visually inspected. The new trace figures are labelled illustrative, with selection not pre-registered (exception to the frozen-selection rule, disclosed in captions and appendix lead).
- Reproducibility statement retargeted to the new appendix structure.
- Build: clean rebuild from scratch; 0 undefined references or citations, 0 multiply-defined labels; the Conclusion and Reproducibility Statement end on page 9; 53 PDF pages total. Pages 1, 4, 28, and 29 rendered and inspected.
  Why: user direction of 2026-09-26 (abstract frozen; main body, appendix, and figures to follow it).

## 2026-09-26 · Section 2 Related Work (related_work.tex, related_refs.bib)

- Changed: Section 2 rewritten as five one-point paragraphs: (1) LLM training for classical planning supervises plans or reasoning along a plan (Plansformer, Pallagani 2023, PlanGPT, Bohnet, Li, Belcamino, PDDL-Instruct, Emami; benchmarks as evaluation context); (2) search-trace learning (Procedure Cloning, Searchformer, Dualformer, Stream of Search, Moon, Opedal) with System-1.x as the closest work, explicit differences, and the hedged gap sentence; (3) LLMs inside search they do not run, ending on the model-owns-exploration / no-repair point; (4) visual and multimodal planning (ViPlan, Visualizing Thought, VPRL, VLMFP) plus language-prior findings, linked to the text-channel result; (5) condensed evaluation-control credits. Each paragraph carries `% Paragraph purpose:` and `% Sources:` comments. Prose about 375 to about 653 words.
  Why: author reframe 2026-09-26 (primary contribution is what a pretrained VLM learns from declared search-algorithm traces; gap per research_notes/trace_training_gap.md).
- Changed: 20 bib entries appended to iclr2026_conference_related_refs.bib under the 2026-09-26 separator, each with a `% source:` line; keys use the first public (arXiv) year.
  Why: same brief (bib contract).
- Changed: dropped from this section only (entries kept): hart1968formal, lipovetzky2017bestfirst (Section 3 cites them), velickovic2020neural, nye2021show, hu2024visual, li2025imagine, li2024behavior1k.
  Why: 650-word cap; each served a point no longer made in Section 2.
- Deferred: the text-channel sentence in Section 2 points to Section~\ref{sec:results}; Results must state that finding when it is rewritten (currently only in the observation-corruption appendix).
- Rejected: "first"/"no prior work" phrasing (brief forbids it); numeric receipts from our results (brief); re-adding the choice-frontier contract gloss (logged 2026-09-25, Introduction defines it).

## 2026-09-25 — paragraph-level prose revision (all .tex files)

- Changed: every paragraph and caption in the abstract, Sections 1–7, the Reproducibility Statement, `qualitative_figures.tex`, and the appendix was rewritten so that it makes one point: a claim, then its explanation, then an evidence pointer. Main-text prose keeps headline numbers only. Intervals, per-seed values, panel construction counts, and protocol history now appear in tables and appendix paragraphs. Stacked appendix-name pointers became `Appendix~\ref{}`. Per-paragraph Point/Diagnosis/Action records are in `prose_audit.md`.
  Why: user request. Main-text prose read like an experiment log; for example, Results said "The smallest held-out adjacent gap is +0.130 [+0.070, +0.190]." without stating what the number means.
- Number accounting: no visible number was added or recomputed. A script compared the pre-revision and post-revision sources and found that every number visible before the revision is still visible somewhere in the PDF. Every number removed from a paragraph has a `% (moved out of prose; kept in …)` comment beside its evidence comment. LLM-First Search's 0.19 at twice the reference's expansions was previously printed only in Results; it is now stated in the LLM-First Search appendix (copied from the curve evidence key), and Results points there instead of to Table tab:appendix-lfs, which does not print it.
- Reversed logged decisions: (1) the Introduction's seed-replication receipts (+0.875/−0.125) are now kept only in Table tab:appendix-seeds; (2) the earlier one-sentence external-audit Discussion paragraph now has two sentences; (3) the Related Work gloss of the choice-frontier contract was removed because the Introduction defines it first; (4) the "problem-modality units" gloss is replaced by "wins no task under any observation". Cause: this revision's readability brief.
- Claim-boundary corrections from the acceptance check: the abstract scopes the BFS/BFWS negative to the expanded baseline; Section 4 restores "counts only after independent replay"; the zero-shot appendix subsection says the base model is "not separated from" random-valid rather than "at the random-valid level" (its held-out verdict is INCONCLUSIVE); the survey caption now attributes the 48/48 identity to our runtime's serial tie-break rule, not to the enumeration contract; the follow-up ledger now names the held-out and unscreened panels instead of saying "held-out panels"; Related Work says "language models" when citing huang2026twodistinct.
- Verified: rebuilt the 47-page PDF. The log shows no undefined-reference, citation, or overfull-box diagnostics. The main text ends on page 9 with the Conclusion, and the Reproducibility Statement opens page 10. Pages 1 and 6–10 were rendered and inspected. Main-text word counts, excluding comments: abstract file 236→212, Introduction 885→784, Related Work 415→375, Section 3 536→490, Section 4 990→893, Results 1953→1680, Discussion 692→611, Reproducibility 121→85. The appendix grew from 17,020 to about 18,780 words because receipt paragraphs gained topic sentences.

## 2026-09-25 — reader-facing integration and rendered QA

- Fixed title retained. The primary story is that learned search choice requires a choice-sensitive success measure: the two-lane teaser contrasts runtime-determined exploration with model-selected frontier expansion; Planimation is credited as an external scene renderer in Section 3, not as a contribution.
- Abstract tightened to 163 whitespace-delimited words. Teaser and qualitative captions contain no rendering-size specifications; exact image provenance lives in the Modality Adapters appendix and figure scripts. Figure 1 uses unchanged cached policy scenes; its Python assertions ran and its SVG, PDF, and PNG exports were generated and visually inspected.
- The identity heatmap became a native Results table. A sparse enumeration illustration duplicated the teaser and was removed from the PDF; two tall quantitative plots and all three rule-selected qualitative plots moved to the appendix. Results retains the findings and cross-references; figure evidence remains in the appendix and scripts.
- Main Methods now keeps evaluation logic and scope, while the training record counts, epoch schedule, backbone revision and program cap are in the appendix; the identity-audit seed and held-out seed-window construction remain in the corresponding appendix receipts. The final 46-page PDF rebuilt without undefined-reference or overfull-box diagnostics.

## 2026-09-25 · Figure 1 teaser (fig_teaser.py and abstract.tex teaser block)
- Changed: `fig_teaser.py` redrawn as two lanes. (a) enumeration contract, 48/48 additive pairs random-valid ≡ reference, "success measures validity, not choice". (b) choice-frontier contract, 18/18 divergent pairs, the pinned blocksworld decision (three unchanged cached 128 px policy scenes, same #145 selection rule), and one unnumbered strip placing random-valid < trained adapter < reference at validation-panel M1 positions. Removed the 12-domain tile grid, the 320 px VFG re-renders and the Planimation renderer import, and the numeric ladder panel (fig:ladder carries it). Asserts on both identity audits, the episode, the scene recipe and paths, and the three plotted M1 values (3 dp) are kept.
  Why: #145 brief (Main): teaser must state the choice-versus-validity insight and the bounded learned result in seconds, with no Planimation credit confusion and no pixel/VFG specs; user follow-up asked for two lanes and no miniature ladder.
- Changed: teaser caption rewritten as a standalone plain-language caption without numbers; evidence comments rewritten per panel.
  Why: same brief (short caption, no method jargon or numerical ledger).
- Resolved at integration: `fig_teaser.{pdf,svg,png}` regenerated with the pinned episode and audit assertions passing, and the PNG/PDF visually inspected; Introduction and Results cite the final two-lane figure without panel letters.
- Rejected: 320 px enlarged re-renders (needless image provenance complexity); grid-domain frames from the qualitative figure (new selection after viewing, and duplicates that figure).

## 2026-09-25 · #145 prose pass: abstract body, Introduction, Experimental Design, Discussion

- Changed at prose pass: abstract body rewritten as question, blind spot, validate-before-score, bounded result, boundary (about 200 to 180 words); integration subsequently cut it to 163 words, moving the 18/18 count and 0.75-rung position out of the abstract while retaining them in the figure, Results, and Discussion.
  Why: #145 brief names the abstract (140-165-word target, restrained style).
- Changed: the abstract drops 19/48 with the failed prediction, unscreened +0.149 (4 of 12), ScienceWorld 0.915 versus 0, and LLM-First Search 0.0775. A comment records where each survives (Introduction, Results, Limitations, Table 1).
  Why: #145 word budget.
- Changed: Introduction. `fig:teaser}c` becomes `fig:teaser` (twice). The 125/288 pointer goes to `tab:results-identity`. Additive best-first is glossed "in greedy and weighted-A* variants". The seeds sentence is folded into the replication sentence, with the descriptive gloss kept. The prediction sentence is merged into the 19/48 sentence.
  Why: #145 brief and Main/ResultsLayout messages (teaser panels may lose letters, new Results table).
- Changed: the Introduction drops these local receipts, each of which stays in Results or the appendix: "twice the reference's expansion count", smallest ladder gaps +0.082 and +0.130, unscreened +0.149 interval, and "1000/1000 over 200 tasks".
  Why: #145 asks to remove overloaded ledgers already held in Results.
- Changed: Design ¶ on frozen rules now points to Box 1 step 3 for the ladder pass rule instead of restating it. Discussion ¶2 names greedy best-first search and weighted A*.
  Why: #145 brief (overtechnical duplication; abstract naming consistency).
- Resolved at integration: the abstract is 163 whitespace-delimited words. Reproducibility-critical Design recipe details remain in Methods; no unsupported move was made.
- Rejected: rewriting contributions C1-C3, the Li & Talwalkar double credit (logged), Box 1, or the Conclusion (not assigned).

## 2026-09-25 — issue #145, Results layout pass (Results 5.2–5.3, Section 3 figure placement)

- Changed: `fig:identity-heatmap` replaced by native `tab:results-identity` (base, SFT per observation, random-valid, exact, 48/48 audit column), each cell checked against `baseline-summary.csv` and `identity-audit.json`. Why: Main's layout brief names table-like figures for replacement; the heatmap duplicated the success columns of appendix `tab:results-primary-matrix`, so the visual-overhaul entry below is reversed on new instruction.
- Changed: `fig:budget-curves` and `fig:task-gains` floats left the body; Main placed them in the Choice-Frontier Validation and Held-Out Panels appendices under the same labels, and the body keeps one pointer sentence each. Per-panel task sign counts (9/2/1, 9/2/0, 4/8/0, 22/12/1 from `concentration.per_panel` and `all_36_counts`) became a `tab:results-panels` column. Why: brief (reduce vertical load); task gains ran about 6.9 in tall, and stacking the budget curves with the ladder ran about 4.5 in, over Main's height rule.
- Integration correction: `fig:ladder` and `fig:enumeration-example` captions shortened; image resolutions were moved from the enumeration caption and figure to the Modality Adapters appendix, with the figure regenerated. `fig:teaser` refs are panel-free; natural qualitative float placement replaces the prior forced page break; `fig:contracts` uses `[t]`.
- Deferred: none. Figure assets kept on disk (Main's instruction).
- Rejected: shrinking the budget-curve, task-gain, and enumeration figures by `width` alone (their small labels would become unreadable); the enumeration source was subsequently regenerated only to remove its visible image-resolution ledger.

## 2026-09-25 — issue #145, manuscript visual overhaul

- Moved a Planimation-scene teaser above the abstract, separated the method diagram from the identity comparison, and integrated solve-versus-budget curves, per-task differences, an enumeration heatmap, and illustrative episode panels into their corresponding sections. Added figure evidence comments, image-integrity and selection-rule conventions to `CONTEXT.md`, and preserved development-stage, descriptive, and privileged-reference claim boundaries.
- Shared figure styling now reads pinned evidence and checks displayed numbers with three-decimal Decimal half-up rounding. The appendix and main results tables use booktabs rules, gray headers, and symbol verdicts; Box 1 keeps its dedicated float and gains a tcolorbox body.
- An independent visual check found two provenance/precision defects: qualitative re-renders now prove pixel identity with cached 128 px policy scenes before enlarging; the held-out puzzle uses its exact cached PNGs where the VFG exposes tile glyphs absent in the initial policy frame. The appendix comparator-zoo figure and caption now report three-decimal, half-up-asserted values.
- Added manifest-checked vector goal facts next to the unchanged tiny rendered goal pages, balanced the registered title over two natural lines, and grouped the qualitative panels on adjacent pages with exact-placement `float` support (installed into the gitignored TeX tree). Their captions distinguish cached scenes with and without embedded tile glyphs; no visual failure mechanism is inferred.

## 2026-09-25 — issue #145, manuscript TeX toolchain and Box 1 styling

- Installed `booktabs`, `xcolor`, `colortbl`, `multirow`, `tcolorbox`, `pgf`, `caption`, and `wrapfig` into the gitignored local TeX Live 2026 tree via `tlmgr` (plus resolved dependencies `environ`, `fp`, `trimspaces`).
- The hub preamble now loads the table, math-symbol (`amssymb`), color, box, caption, TikZ, and wrapfig packages and defines `mygray`, `\legendbg`, `\cmark`, `\xmark`, and `\notseparated` for consistent table verdicts. Box 1 retains its dedicated `protocolbox` float and numbering, with a dark-title/light-background `tcolorbox` body in place of the framed parbox; its scientific wording is unchanged.

## 2026-09-23 — citation pass (`059028f`)

- Related Work gained a scoped paragraph positioning the audit against evaluation-validity work, multimodal shortcut and position-bias findings, and search-selector calibration; eight entries added, each verified against its primary source.
- Bibliography audited: 42 cited keys over 45 entries, every key resolving exactly once, no duplicate works. Two entries (`bai2025qwen3vl`, `yang2025qwen3`) were restored after the audit had removed them while they were still cited.
- Removed an inaccurate parenthetical in Results ("confirmed by the expanded baseline below").

## 2026-09-23 — writing round 2 (`1b49ecb`)

- Abstract rewritten around the measurement-methodology arc; Introduction headline and results map restructured with the BFWS development-panel positive demoted to one positive contrast.
- Experimental Design extended with the native-arms v2 observation contract, the menu-manipulation protocol, the two-contract table, the identity audit, the choice-frontier panel, and the #133 metric and test-family definitions; staged sequence extended through #128–#133.
- Appendix extended with follow-up receipt rows on separate ledgers, an artifact index, follow-up bootstrap conventions, and a choice-frontier operations section. Reproducibility Statement extended with per-window compute and the new replay receipts.

## 2026-09-23 — writing round 1 (`2569773`)

- Results integrated the closed tickets #129 (native-arms v2), #130 (R1–R4 and the identity audit), #132 (choice-frontier redesign), and #133 (comparator zoo and metric set), under the measurement-methodology reframe the ticket records as user-approved.
- Discussion restructured around the same arc, with the menu-leak reading, the choice-quality boundaries, five new threat items, and a declarative conclusion.
- Hub: the unused `\fix` and `\new` annotation macros were removed.

## 2026-09-22 — full draft (`4d5842e`)

- Multi-file layout: prose-free hub plus nine per-section files and per-section bibliography namespaces; all sections written; prose pass.

## Earlier (2026-08-19 to 2026-09-21)

- `112061d` condense deadline abstract; `35e205d` update abstract with expanded evidence; `ae52649` rewrite introduction narrative; `8dd985b`, `45fa9f1` citation work in the introduction; `55f0635` clarify search-training motivation; `f0bc656`, `4f79241`, `84af891`, `b50a82e`, `accc068` skeleton, corpus alignment, and manuscript initialization.

## Build and verification

```bash
bash manuscript/build_pdf.sh          # writes manuscript/manuscript.pdf
```

Last verified build (2026-09-25): 47 pages, 0 errors, 0 undefined references or citations, 0 overfull boxes; main text through the Conclusion is 9 pages.

## Open items

- Release URLs (#122) and the BFWS-to-BFS panel overlap (post-#126 retention manifest) are stated as prose in the section files, with their ticket references in `%` comments.
