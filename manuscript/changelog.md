# Manuscript Changelog

The record of what changed in the ICLR 2026 manuscript and why. Newest first. Each entry names the commit, the scope of the change, and the review or ticket it answered. Review findings and their status live in `review-log.md`; claim vocabulary and boundaries live in `CONTEXT.md`.

## 2026-09-24 — round 4 wave 1, evidence integration and reframe (`59e8714`)

- Findings 49 and 60 (review 19) CLOSED with #134. 5.2 reports both verdicts of the identity check on one runtime (48/48 identical under the executed sorted-order serial rule, 19/48 divergent under submission-order serials, first divergence at decisions 2-50, median 6) and states that the pre-registered majority prediction (>24/48) did not hold. 5.4 and App S give the M4 task-cluster intervals and drop the below-chance agreement reading.
- Results reordered: 5.2 identity audit, 5.3 choice-frontier contract and instrument validation (#135 ladder, body Table 1), 5.4 scaled adapter (#136, D = +0.328 [+0.155, +0.508], at the exact-ε 0.75 rung, single seed, placeholders P1-P3), 5.5 external identity audit (#137 ScienceWorld, survey, exclusions), 5.6 enumeration-contract learned results and boundaries. The zoo (tab:results-zoo, sec:results-calibration) and the #132 table (tab:results-cf) moved to App R; secondary, failure, corruption, menu, and native-arm subsections collapsed to one pointer paragraph with their labels kept on the appendix headings.
- Appendix gains app:results-counterfactual, app:results-ladder, app:results-adapter, app:results-external, and #134-#137 ledger rows (#135 1.19/4 GPU-h, #136 4.84/30 GPU-h, #134 and #137 CPU-only, never summed).
- Abstract, Introduction, Discussion, and Conclusion rebuilt around the shared vocabulary sentences from the round contract. Contributions are the two-verdict identity audit, the ladder-validated measurement, the first learned result above uniform choice with its boundaries, and the external anchor. The Discussion states that the identity failure is shown only on this runtime, so the contribution is the measurement.
- New keys `wang2022scienceworld`, `herr2025llmfirst` (results_refs.bib).
- Build: 32 pages, 0 errors, 0 undefined, 0 overfull, 0 bibtex warnings. The Conclusion ends on p.8. All headline strings present in the rendered text.

## 2026-09-24 — round 4 opening, Phase 0 decisions (issue #131; evidence tickets #134-#137)

- Evidence sheet frozen for the round from the #134-#137 artifacts (Main spot-checked 15 rows against the JSONs). Writers copy new numbers only from it.
- Author decisions (Phase 0):
  - Title: "Separating Choice from Validity: A Validated Search-Choice Measurement for Vision-Language Search Policies" (hub). The complete-set identity failure is scoped to this runtime's complete-set submission contract, and the #137 survey found it in none of seven published interfaces.
  - `CONTEXT.md`: the rule "no choice-quality claim for the redesigned arm" is replaced by a development-stage, single-seed choice-quality claim on the #135 validation panel, relative to uniform choice and the exact-ε ladder, with no planning-ability, generality, or held-out claim.
  - #136 single seed: POSITIVE reported as the pre-registered rule applied to one seed, deviation stated, no seed-robustness claim. Visible placeholders P1 (seeds 29 and 71), P2 (second fresh panel or held-out evaluation), P3 (paired learned minus exact-ε 0.75 interval) mark the author's pending follow-up experiments in Results, the appendix, and Discussion only.
  - #137: ScienceWorld CHOICE_REGISTERED over 6 of 30 task types; WebShop and LLM-First Search exclusions named; no claim about agent benchmarks in general.
  - Findings 49 and 60 close with #134 (verdict "PREDICTION_FAILED: see preregistered_prediction": 48/48 identical under the executed rule, 19/48 divergent under submission-order serials, pre-registered >24/48 not met; M4 task-cluster intervals).
  - Main text stays within 9 pages. Secondary nulls, the #133 zoo table and figure, and the #132 table move to the appendix. One body ladder figure is added.
  - Meaning-level rules: the scaled adapter is "at the exact-ε 0.75 rung" on point estimates; the ladder rungs are privileged selectors; the panel is screened and the effect concentrated; the screened count is 34 (JSON) against the closeout's 38; hadd-greedy stays in the appendix.
  - Finding 40 stays WONTFIX. Review 20 is held until the author reports the follow-up results.
- ScienceWorld (ACL Anthology bib, 2022.emnlp-main.775, pp. 11279-11298) and LLM-First Search (arXiv:2506.05213) verified by Main against primary sources.

## 2026-09-23 — review 19 and consolidation (`c08ef50`)

- Review 19 (paper-reviewer, re-review at `1281c1b`) returned WEAK REJECT, with 0 CRITICAL, 1 MAJOR (finding 49, blocked on #134), and 8 MINOR findings. Every number in the rendered PDF matches its pinned artifact, and the 16 sampled `% Evidence` comments resolve. zheng2024robust matches its primary sources. The main text is 9 pages. Full text is in `review-log.md`.
- Consolidation closed the WORDING items:
  - Review-16 finding 15 regression: the Related Work positioning sentence ("This paper operationalizes the known admissible-action handicap ...") is restored.
  - 51 remainder: the Related Work menu-probe sentence now says only the unrun position variant would separate surface-following from state grounding.
  - 53 remainder: four more `% Evidence` lines were added, and two wrong pointers were corrected by Main (the BFWS gate bootstrap now cites `configs/experiments/bfws_phase_threshold_v1.json`, and the backbone revision cites `goal10-completion-audit.json` L7).
  - 56 remainder: Section 3 now points invariants to the Algorithm Invariant Definitions appendix.
  - 66: Figure 1 uses "pairs" in both panels with task counts, adds the enumeration-contract random-valid minus exact +0.000 (read from `synthesis-v1/baseline-contrasts.csv`), relabels the node "Submission-order-invariant frontier", and the caption states the panels differ.
  - 67: the abstract's closing sentences are rewritten.
  - 68: the Related Work comma splice is fixed.
  - 49 (wording part): Contribution 1 hedges the 18/18 divergence as holding by construction over 9 tasks. The Introduction's closing sentence states that portability beyond this runtime is untested.
  - 60 (interim): 5.10 and App R note that no M4 interval is computed and that decisions cluster within 9 tasks.
- Still open: findings 49 and 60 wait on evidence ticket #134 (the same-runtime submission-order-serial counterfactual and the M4 task-cluster intervals). Finding 40 remains WONTFIX.
- Build: 29 pages, 0 errors, 0 undefined, 0 overfull, 0 bibtex warnings. The Conclusion ends on p.9.

## 2026-09-23 — review 18 wave 3, compliance and hygiene (`640467b`)

- Findings 53, 56, 57, 61, 63, 64, 65 and the finding 44 and 45 remainders are CLOSED.
- Finding 53: every numeric paragraph and table the finding listed now has an adjacent `% Evidence` line naming its pinned file and key. `content_brief.md` sources are replaced by the pinned JSON or README they summarized. The `descriptive_only=false` artifact flag against the one-task descriptive rule gets a source-conflict comment in the Abstract, Results, and App R.
- Finding 56: the 5.2 mechanism pointer names the Algorithm Invariant Definitions appendix, and the Reproducibility Statement uses prose appendix names.
- Finding 57: the second-backbone control denominator is explained in the text ("24/24 control entries per modality, two per task").
- Finding 63: the ledger wording names three GPU windows plus the CPU-only zoo.
- Finding 64: the Design freeze-timing sentence says each follow-up was frozen before its own outcome but after earlier outcomes on the same nine tasks.
- Finding 65: mid-clause colons are removed across Results and the Appendix. The design run-on sentences are split, artifact-speak is removed, and the Imitation-target item and Cell A wording follow the prescribed fixes (44, 45 remainders).
- Finding 61: Related Work cites Zheng et al. (ICLR 2024) on label-position selection bias (`zheng2024robust`). The entry is verified against arXiv:2309.03882 and the ICLR 2024 proceedings, with DBLP as a cross-check, and the fixed-versus-random-position distractor test is named as the unrun diagnostic.
- The one remaining prose semicolon is in the author-dictated LLM-usage sentence (finding 40, WONTFIX).
- Build: 29 pages, 0 errors, 0 undefined, 0 overfull, 0 bibtex warnings; the Conclusion ends on p.9.

## 2026-09-23 — review 18 wave 2, title, figures, and the two-contract audit (`83e30c2`)

- Finding 50 CLOSED. The hub title is now "When Random-Valid Equals the Reference: A Per-Decision Identity Audit for Search-Execution Evaluation of Vision-Language Models" (author decision). fig:contracts is regenerated in a wide side-by-side layout, with numbers read by the script from identity-audit.json (both contracts) and analysis.json, and placed as Figure 1 in Results 5.2. fig:zoo-m1 moved to App R, and Table 2 stays in 5.10. The Design reference drops "(Appendix)".
- Finding 49, text part: the author asked for existing evidence first. An evidence search found that the identity check already returns opposite verdicts on the two contracts (48/48 identical, 18/18 divergent), and 5.2 and Contribution 1 now say so. 5.2 states that the choice-frontier divergence holds by construction and that the same-runtime submission-order-serial counterfactual has not been run. That counterfactual and the M4 intervals (finding 60) are filed as evidence ticket #134. Both findings stay OPEN until it closes.
- Build: 29 pages, 0 errors, 0 undefined, 0 overfull, 0 bibtex warnings. The Conclusion ends on p.9, and Figure 1 is on p.6.

## 2026-09-23 — review 18 wave 1, claim scoping (`9de44ad`)

- Findings 51, 52, 54, 55, 58, 59, 62 CLOSED, each per the author's Phase 0 decision (reviewer's prescribed fix). Menu manipulation is demoted in Abstract, Contribution 1, and Conclusion to a probe whose discriminating fixed-versus-random-position variant remains unrun; the Conclusion keeps only the identity audit (51). The Conclusion's last-label sentence is replaced by "without demonstrated choice quality", the below-random M1 contrast with "which is not equivalence", and a post-hoc label audit; 5.10 and App R label M4 post-hoc with no last-label comparator (52). 5.4 matched modality "does not support" an intrinsic modality effect, "non-significance is not equivalence" (54). 5.4 and App M recast the second backbone as an unpaired architecture-difference limitation per analysis.json architecture_note (55). 5.5, App N, and Discussion give the descriptive failure calibration (229/407 invariant rejections, 72/407 malformed) and drop "teaches" and "frontier intent" (58). App Q gives the operand-removal reading (59). Discussion scopes learnability to the additive-cell output contract (BFS/BFWS 0/24) and the language-channel dependence to the shuffled condition (62).
- Held: 49 and 60, pending an evidence search the author requested (see wave 2). Length offsets trimmed connectives in Abstract, Introduction, Discussion, and 5.10 to hold the 9-page main text.
- Build: 29 pages, 0 errors, 0 undefined, 0 overfull, 0 bibtex warnings; Conclusion ends p.9.

## 2026-09-23 — round 3 opening, review 17 bookkeeping

- `review-log.md`: finding 48 flipped to CLOSED (`e5c4c09`, fix verified in fig_contracts.png), review 17 index row to CLOSED, review 16 index row to SUPERSEDED. No manuscript text changed.
- Round 3 Phase 0 decisions (author, 2026-09-23): commission review 18 and resolve its fixlist; main text through the Conclusion stays within 9 pages; finding 40 LLM-usage wording stays WONTFIX, and any new finding contesting it gets the same disposition; figure work, if requested, is drawn by a paper-writer from the pinned JSONs; the ICLR 2026 style file stays.

## 2026-09-23 — review 17 and consolidation (`e5c4c09`)

- Review 17 (paper-reviewer, adversarial verification at `c42277c`): WEAK REJECT, 0 CRITICAL, 4 MAJOR, 10 MINOR. It re-checked every headline number against the pinned JSONs and episode stores (all match), confirmed the 9-page main text and the clean build, and verified 34 of 36 review-16 findings with 2 partial (9, 11) and 0 regressed. Full text in `review-log.md`.
- Consolidation: the remainders of findings 9 and 11 and new findings 37-39, 41-48 are closed. Main changes: random-valid relabelled "uniform-choice reference" with the zoo's calibration limit stated (no comparator between random-valid and exact on this panel); the abstract and conclusion now carry the adapter's below-random M1 position (paired -0.035 [-0.150, +0.061]) and the post-hoc M4 last-label habit; the additive equal-f tie-break and serial-assignment rule is pinned from the executed controller in Appendix B with the submission-order counterfactual; duplicate seed-variance and receipts tables merged; visible TODO markers converted to prose; the Reproducibility Statement is one pointer paragraph.
- Finding 40 (LLM-usage wording) is DECLINED by the author: the dictated sentence "An LLM was used only for polishing language; the scientific content is entirely original." stays as App U. The reviewer's note that the repository record shows agent-drafted text, and that under-disclosure risks desk rejection under the ICLR 2026 guide, is recorded here per the finding's fix.
- Build: 29 pages, 0 errors, 0 undefined, 0 overfull, 0 bibtex warnings; main text (through the Conclusion) is 9 pages.

## 2026-09-23 — review 16 wave 3, compliance and hygiene (`afec954`)

- Findings 12, 15, 18, 19, 21-25, 27, 30, 32 CLOSED. The withdrawn v1 scopes (#96/#98/#102/#103, closed 2026-09-21) replace every "remain open" sentence and marker; the panel-overlap (#126 manifest) and release-URL (#122) TODOs stay as the only visible markers, each tied to its ticket.
- Anonymity: comment IDs, internal release and branch names, and "reviewer window" naming scrubbed from reader-facing prose and tables (kept in % Evidence comments); the R1-R4 window ledgers row in the artifact index uses a neutral name. The appendix receipt tables retain their ticket-index columns as the sanctioned internal index.
- Appendix "Use of LLM Statement" section added with author-dictated wording. Related Work anchors the audit in the admissible-action literature with verified Jericho (hausknecht2020interactive) and CALM (yao2020keep) entries; orseau2021policyguided bibtex warning fixed. Paragraph-purpose census completed; prose semicolons, rule-of-three remnants, "preregistered" spellings, hard-coded "Section F", and the pooled -0.944 "confirms" caveat in the appendix fixed. Build: 30 pages, 0 errors, 0 undefined, 0 overfull, 0 bibtex warnings; main text ends p.9.

## 2026-09-23 — review 16 wave 2, 9-page restructure and figures (`3c558bf`)

- Findings 6 and 14 CLOSED. Main text compressed from about 25 pages to 9: the Conclusion ends on page 9, with References and the Reproducibility Statement after. Seven operational tables (gates, contrasts, DAgger, transfer, corruption, menu, seed-variance) and the design-contracts table migrated to the appendix with labels intact, along with the secondary-panel, failure-calibration, corruption, and native-arm detail; the body keeps the identity audit, the primary-matrix prose, menu manipulation, the choice-frontier contract with its table, and the comparator-zoo table.
- Two figures added, drawn from the pinned JSONs by a paper-writer with reproducible scripts under `iclr2026/figures/`: `fig:zoo-m1` (comparator-zoo M1 positions with task-clustered intervals, in Results 5.10) and `fig:contracts` (enumeration versus choice-frontier contract contrast, in Appendix "Decision Contracts" per the reviewer's one-body-figure keep list).
- Hub: graphicx loaded, float and caption spacing tightened. The `tab:axis` related-work table was compressed to prose. The final-evaluation prerequisites list migrated from Design to the appendix.
- Build: 31 pages total, 0 errors, 0 undefined, 0 overfull. Headline numbers re-checked in the rendered PDF text (48/48, -0.644 [-0.856, -0.422], 0.592-0.625 chance band, .1042 zoo position, 0.933 BFWS contrast, 20/36 first-decision distractors).

## 2026-09-23 — review 16 wave 1, claim scoping (`1c559e7`)

- Findings 1-5, 7-11, 13, 16-17, 20, 26, 28-29, 31, 33-36 CLOSED. Headline sentences in Abstract, Introduction, Discussion, and Conclusion are scoped to the additive best-first cells, with submission-order invariance named as the cause and the choice-registering BFS/BFWS cells (random-valid 15/24 and 17/24, learned 0/24) stated alongside.
- The "rules out order-riding" and "reads menu content / cannot ground actions in state" rulings are replaced by the scoped behavioral statement (does not reject schema-valid inapplicable menu entries, pick-rate 0.6 at the 0.592-0.625 chance band), per the user's Phase 0 decision. The distractor receipt is corrected to "every episode ends on a distractor pick, 20/36 on the first decision" with a source-conflict comment.
- Results reordered: the identity audit now follows the gate receipts as Section 5.2, ahead of the primary matrix, which references it directly. Comparator-zoo claims report point estimates with overlapping intervals and no Pareto dominance. The choice-frontier corpus provenance sentence is now identical in Results, Design, and Appendix, and the enumeration-contract random-valid sampler is pinned from the executed code.
- Build: 39 pages, 0 errors, 0 undefined, 0 overfull.

## 2026-09-23 — documentation consolidation (this commit)

- `changelog.md` moved from `iclr2026/` to the manuscript root (the LaTeX directory holds build inputs only).
- `review-log.md` created as the single authoritative review record. The 16 per-review files under `manuscript/critics/` were folded into it and the folder was removed; the originals remain in git history at `5357a65`.
- Removed the stale "result-ready empirical skeleton" sentence from `iclr2026_conference_experimental_design.tex` (review 16, finding 27).
- `content_brief.md` marked superseded: it is the pre-#129 evidence snapshot and its progress list no longer describes the draft.

## 2026-09-23 — full-draft review, review 16 (`5357a65`)

- Area-chair-tier review of the assembled 37-page draft: all nine sections, the hub, the six bibs, the build log, and the rendered PDF text. Verdict REJECT with 6 CRITICAL, 14 MAJOR, and 16 MINOR findings.
- Findings are the live fixlist in `review-log.md`. The review confirmed the number transcription against the pinned artifacts and located the problems in what those numbers license, not in their transcription.

## 2026-09-23 — citation pass (`059028f`)

- Related Work gained a scoped paragraph positioning the audit against evaluation-validity work, multimodal shortcut and position-bias findings, and search-selector calibration; eight entries added, each verified against its primary source (`manuscript/critics/2026-09-23-scout-citations.md` before the consolidation).
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

- Multi-file layout: prose-free hub plus nine per-section files and per-section bibliography namespaces; all sections written; review 15's fixlist applied; prose pass.

## Earlier (2026-08-19 to 2026-09-21)

- `112061d` condense deadline abstract; `35e205d` update abstract with expanded evidence; `ae52649` rewrite introduction narrative; `8dd985b`, `45fa9f1` citation work in the introduction; `55f0635` clarify search-training motivation; `f0bc656`, `4f79241`, `84af891`, `b50a82e`, `accc068` skeleton, corpus alignment, and manuscript initialization.

## Build and verification

```bash
bash manuscript/build_pdf.sh          # writes manuscript/manuscript.pdf
```

Last verified build (`c08ef50`): 29 pages, 0 errors, 0 undefined references or citations, 0 overfull boxes, 0 bibtex warnings; main text through the Conclusion is 9 pages. Headline numbers were re-checked in the rendered PDF text against the pinned artifacts listed in `review-log.md`.

## Open items

- The active fixlist is the last `OPEN` entry in `review-log.md`.
- Release URLs (#122) and the BFWS-to-BFS panel overlap (post-#126 retention manifest) are stated as prose in the section files, with their ticket references in `%` comments.
