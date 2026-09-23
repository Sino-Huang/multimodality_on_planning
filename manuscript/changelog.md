# Manuscript Changelog

The record of what changed in the ICLR 2026 manuscript and why. Newest first. Each entry names the commit, the scope of the change, and the review or ticket it answered. Review findings and their status live in `review-log.md`; claim vocabulary and boundaries live in `CONTEXT.md`.

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

Last verified build (`e5c4c09`): 29 pages, 0 errors, 0 undefined references or citations, 0 overfull boxes, 0 bibtex warnings; main text through the Conclusion is 9 pages. Headline numbers were re-checked in the rendered PDF text against the pinned artifacts listed in `review-log.md`.

## Open items

- The active fixlist is the last `OPEN` entry in `review-log.md`.
- Release URLs (#122) and the BFWS-to-BFS panel overlap (post-#126 retention manifest) are stated as prose in the section files, with their ticket references in `%` comments.
