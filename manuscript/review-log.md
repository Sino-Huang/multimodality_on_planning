# Manuscript Review Log

Single record of every review the manuscript has received: what draft state it reviewed, what it found, and how it was disposed. Per-review detail files were folded into this log on 2026-09-23 so that only one review artifact is authoritative; the original files (`manuscript/critics/`) remain in git history at commit `5357a65`.

## Conventions

- One entry per review: date, reviewer, scope and draft state where known, verdict with finding counts, and disposition.
- `status` is `OPEN` (findings not yet addressed on the current draft), `CLOSED` (addressed in the named commit), or `SUPERSEDED` (reviewed an earlier draft state; findings resolved or made moot by later revisions).
- The active fixlist is the last `OPEN` entry. Current draft state: branch `manuscript`.

## Index

| # | date | reviewer | scope / draft state | verdict | status |
|---|---|---|---|---|---|
| 1 | 2026-08-19 | paper-reviewer | Confirmed manuscript design artifacts: `content_brief.md`, `CONTEXT.md`, and the writing design tree. | not recorded in header | SUPERSEDED |
| 2 | 2026-08-19 | paper-reviewer | Re-review of the corrected design artifacts. | not recorded in header | SUPERSEDED |
| 3 | 2026-08-25 | paper-reviewer | Design artifacts against the fetched-main evidence boundary and the Oracle gates. | not recorded in header | SUPERSEDED |
| 4 | 2026-08-26 | paper-reviewer | `writing_design_tree.md` and `content_brief.md`; the `.tex` file was still an unreviewed template shell. | not recorded in header | SUPERSEDED |
| 5 | 2026-08-31 | paper-reviewer | Title and abstract only, under the bounded BFS-only text-state v6 boundary. | not recorded in header | SUPERSEDED |
| 6 | 2026-08-31 | paper-reviewer | Title, abstract, and introduction under the retained BFS-only evidence boundary. | not recorded in header | SUPERSEDED |
| 7 | 2026-08-31 | paper-reviewer | Title, abstract, and introduction against the audited BFS/BFWS boundary. | not recorded in header | SUPERSEDED |
| 8 | 2026-09-04 | paper-reviewer | Motivation and continuity review of title, abstract, and introduction. | not recorded in header | SUPERSEDED |
| 9 | 2026-09-04 | paper-reviewer | Citation and attribution review of the introduction's first paragraphs. | not recorded in header | SUPERSEDED |
| 10 | 2026-09-04 | paper-reviewer | Background-source-chain review of the revised citation chain. | not recorded in header | SUPERSEDED |
| 11 | 2026-09-04 | paper-reviewer | Full introduction review. | not recorded in header | SUPERSEDED |
| 12 | 2026-09-19 | paper-reviewer | Deadline abstract review against `content_brief.md` and `CONTEXT.md`. | not recorded in header | SUPERSEDED |
| 13 | 2026-09-19 | paper-reviewer | Concise abstract review (164 words). | not recorded in header | SUPERSEDED |
| 14 | 2026-09-21 | paper-reviewer | Alignment audit of abstract and introduction against issues #115--#128. | not recorded in header | SUPERSEDED |
| 15 | 2026-09-22 | paper-reviewer | Full-draft audit of the assembled 25-page draft; verdict FIXLIST (1 CRITICAL, 9 MAJOR, 16 MINOR), gating the last revision round. | FIXLIST (1 CRITICAL, 9 MAJOR, 16 MINOR) | CLOSED (`4d5842e`) |
| 16 | 2026-09-23 | paper-reviewer (area-chair tier) | Full manuscript: 9 sections, hub, 6 bibs, build log, rendered 37-page PDF at commits `2569773`, `1b49ecb`, `059028f` | REJECT (6 CRITICAL, 14 MAJOR, 16 MINOR) | SUPERSEDED by 17 (34 verified, findings 9 and 11 partial and carried into 17, remainders CLOSED in `e5c4c09`) |
| A | 2026-09-23 | related-work-scout | Citation pass over all sections and the six bibs at commit `1b49ecb` | 0 placeholders, 8 entries added, 42 cited keys resolving, 2 entries restored after an audit error | CLOSED (`059028f`) |
| 17 | 2026-09-23 | paper-reviewer (area-chair tier) | Round-2 re-review at `c42277c`: nine section files, hub, six bibs, log/blg, rendered 30-page PDF, both figures, re-check of headline numbers against the pinned JSONs and episode stores | WEAK REJECT (0 CRITICAL, 4 MAJOR, 10 MINOR, counting the 2 carried partials) | CLOSED (`e5c4c09`; finding 40 WONTFIX by author decision) |

## Live fixlist — review 17 (2026-09-23)

**Verdict:** WEAK REJECT. 0 CRITICAL, 4 MAJOR (findings 37-40), 10 MINOR (the partial remainders of findings 9 and 11, plus findings 41-48). Most damaging issue: **finding 37**. The comparator zoo has no comparator between random-valid and exact, so it cannot calibrate choice quality, and the paper hides this by labelling random-valid a "floor".

Genre: BENCHMARK (+ FINDINGS)
Δbelief: On additive best-first search, a grounded-menu (enumeration) evaluation cannot measure choice at all, because random-valid is decision-identical to exact on 48/48 pairs. A per-decision identity check plus menu manipulation exposes this cheaply.
Ledger: Verified: 1-8, 10, 12-36 · Partial (carried, MINOR remainder): 9, 11 · Regressed: none · Not addressed: none · New: 37-48

**Reviewer summary:**

> Round-2 adversarial verification of the Wave 1-3 revision at HEAD `c42277c` (clean working tree). I read the rendered PDF text in full (30 pages), every section file, the hub, the log/blg, and both figure assets and scripts. I re-checked the headline numbers directly against the pinned JSONs and episode stores, not the section text. Every number checked matches its artifact: 48/48 (identity-audit.json); 36/36, 0/512, 36/60 = 0.6, cross cell 0/18, variant cells (stress-evaluation.json); a chance band of 0.5919-0.6252 over 60 injected decisions, recomputed from the 36 distractor episode records; 20/36 first-decision endings, with 36/36 rejections being injected distractors; R2 16+15 partial-valid, 3 goal, 2 all-invalid (r2-decomposition.json); 18/18 divergent, CHOICE_SENSITIVE, 144 replayed (choice-frontier identity-audit/final-audit/evaluation); −0.644 [−0.856, −0.422], +0.389 [+0.167, +0.611], +0.033 [−0.033, +0.133], and 7/18 and 32/90 recomputed from per-cell rows (analysis.json); every M1 value and CI, 3×/4× counts, M2 ρ, M3 κ, M4 23/132 vs 0.269, 72/132 last-label, M5 .3125/.075/.625 (o4/metrics/analysis.json); 11/10/10 of 12, 0/36, 24/24, invalid rates, decision usage, and all six contrasts plus three cross-backbone intervals (second-backbone-v3 analysis.json); expanded-baseline SFT 125/288, RV 240/288, BFS RV 45/72, BFWS RV 51/72 (tallied from the 1,152 baseline episode files). Transcription is clean. Of the 36 review-16 findings, 34 are fixed and hold up under adversarial reading. Two are only partly fixed: the abstract still omits the task-clustered interval (9), and Appendix O still pools the masked regime into the −0.694 isolation contrast (11). None regressed. The revision's real gains are the scoped headline, the chance-band menu ruling, and the 9-page body. Compression, however, pushed out of the body the two facts that most constrain the choice-frontier reading. On M1 the adapter sits below random-valid (.1042 vs .1389, paired −0.035 [−0.150, +0.061]). Its heap-head agreement is below chance (17.4% vs 26.9%), with 54.5% last-label picks; this was in Results at `5357a65` and is now Appendix R only. The new Figure 1 then labels random-valid a "floor" that 5 of 7 arms sit below. The zoo therefore brackets nothing between uniform choice and exact, and its role as a calibration instrument is unargued. The headline mechanism (heap serial order) is never pinned in Appendices A/B, and the source comments admit the tie-break is unpinned. The author-dictated LLM statement ("only for polishing language") conflicts with the repository's agent-driven drafting record.

### Build, page count, figures

- **Build (iclr2026_conference.log / .blg, both newer than every .tex/.bib):** 0 errors (`^!` count 0), 0 LaTeX warnings, 0 undefined references or citations, 0 overfull boxes (underfull only), 0 BibTeX `Warning--` lines, 40 bib entries used; "Output written on iclr2026_conference.pdf (30 pages)". **PASS.**
- **Page count:** Title/abstract p.1 through the end of the Conclusion on **p.9**: main text = **9 pages**, within the ICLR 2026 limit (Author Guide https://iclr.cc/Conferences/2026/AuthorGuide, fetched 2026-09-23: "main text should be 9 pages or fewer"; references and the Reproducibility Statement do not count). **PASS.** Note: the same guide dates the ICLR 2026 full-paper deadline to 2025-09-24; the target cycle is taken as the one stated in the brief.
- **fig:zoo-m1 (Figure 1, p.8):** plotted values and CIs match o4/metrics/analysis.json exactly (.8472 [.7917, .8750], .1389 [.0250, .2722], .1042 [.0278, .2014], .1250 [0, .2778], .0694 [0, .1528], .0556 [0, .1389], 0). The caption numbers match. Defects are in findings 37 and 44.
- **fig:contracts (Figure 2, p.30):** 48/48 and −0.644 [−0.856, −0.422] match identity-audit.json and analysis.json. The caption matches the panels. A rendering defect is in finding 48.

### Verification of review-16 findings 1-36

| # | sev (r16) | r17 result | evidence at `c42277c` |
|---|---|---|---|
| 1 | CRITICAL | VERIFIED | Abstract p.1 L13-17, Intro p.2 L58-62, Contribution 1, Discussion p.8 L415-418, and 5.2 all scope to "the additive best-first cells", with submission-order invariance as cause. BFS/BFWS 15/24 and 17/24 vs 24/24 stated, learned 0/24; "any grounded-menu evaluation" deleted. Conclusion hedges with "can leave". |
| 2 | CRITICAL | VERIFIED | 5.7 p.6 L308-316: "uninformative about order", "pick-rate of 0.6 against a uniform-picking expectation of 0.592 to 0.625", "does not reject schema-valid inapplicable menu entries"; fixed-vs-random-position test named as not run. Chance band recomputed from the 36 episode files: 0.5919 (all rows) / 0.6252 (unpruned rows), n=60. |
| 3 | CRITICAL | VERIFIED | 5.7 L311 "every episode ends on a distractor pick, 20/36 on the first decision". Episode files: 20 one-decision, 8 two-decision, and 8 three-decision episodes; all 36 rejected emissions ∈ injected_distractors. Source-conflict comments are at results.tex L86-87 and appendix.tex L807-810. |
| 4 | CRITICAL | VERIFIED | Abstract p.1 L33-34 "(.1042) lies between bfs-order (.0694) and novelty-first selection (.1250) (point estimates, intervals overlap)"; Contribution 3 no longer ranks. The new omission of random-valid is finding 38. |
| 5 | CRITICAL | VERIFIED | Discussion no longer carries 34/36 or "0/18 all-invalid". Appendix O p.26-27 gives 16/18 and 15/18 partial-valid, 3/18 goal, cross cell "0/18 with every episode all-invalid", all matching r2-decomposition.json and stress-evaluation.json. |
| 6 | CRITICAL | VERIFIED | Main text 9 pages (see above). Seven tables and operational detail moved to the appendix. |
| 7 | MAJOR | VERIFIED | "algorithm confound" and "not modality-specific" absent from PDF. App M p.26 L1350-1354 uses the prescribed wording: "consistent with an algorithm (choice-requirement) difference rather than a backbone null". |
| 8 | MAJOR | VERIFIED | "only panel where random-valid falls below saturation" absent. 5.3 p.6 L273-275 states the unsaturated BFS/BFWS cells with SFT 0/24. |
| 9 | MAJOR | **PARTIAL** | Fixed: "9/9 tasks (18 cells, control sequences coincide across the two algorithms)", "sanity check that holds by construction", "rests on a single task". The Intro carries the task-clustered [−0.889, −0.333]. **Remaining:** the Abstract (p.1 L28) gives only the frozen cell-bootstrap CI [−0.856, −0.422], although identity-audit.json shows identical exact and random decision/expansion counts for greedy and w3 on every task (18 cells = 9 independent units). Fix as prescribed: add "task-clustered [−0.889, −0.333]" to the abstract. Remainder severity MINOR. |
| 10 | MAJOR | VERIFIED | One sentence, identical in Design p.4 L210-212, App I p.21 L1095-1096, and App R p.28 L1488-1489. Checked against code: `choice_frontier_corpus.derive_task_episode` runs the new contract's exact_reference session from PDDL and gates it expansion-for-expansion against the stored trace (L245-261). The module docstring's word is "Replays", so the wording is defensible. |
| 11 | MAJOR | **PARTIAL** | Fixed: Intro, Contribution 3, and App G p.19 L1022-1023 cite shuffled only, with "is consistent with". **Remaining:** App O p.26 L1391-1397 still reads "Masking or shuffling the text channel lowers success by up to −0.944". It reports "text minus visual −0.694 … which is material under the frozen rule" with no flag that its −0.806 text term averages masked (−0.889) and shuffled (−0.722). Fix: cite shuffled only, and append "this contrast pools the output-contract-destruction (masked) regime". Remainder severity MINOR. |
| 12 | MAJOR | VERIFIED | No marker or "remain open" sentence tied to #96/#98/#102/#103. The withdrawal sentence is present in Intro, Design, 5.1, 5.11, Discussion, and App J/M. `gh issue view -R Sino-Huang/multimodality_on_planning` confirms all four CLOSED 2026-09-21. The remaining visible markers (#122 OPEN, #131 OPEN) are finding 46. |
| 13 | MAJOR | VERIFIED | Identity audit is 5.2, directly after 5.1; 5.3 references it ("which the identity audit reads as operation validity"). |
| 14 | MAJOR | VERIFIED | fig:zoo-m1 is in the body (p.8) and fig:contracts in App T. Placement follows review 16's one-body-figure keep list. Content defects are findings 37 and 44. |
| 15 | MAJOR | VERIFIED | Related Work p.3 L130-138 cites Jericho and CALM. Both claims check against sources: CALM abstract, https://arxiv.org/abs/2010.02903 ("on half of these games, CALM is competitive with or better than other models that have access to ground truth admissible actions"); Jericho, https://arxiv.org/pdf/1909.05398 ("Jericho's world-change-detection handicap to identify valid actions"). |
| 16 | MAJOR | VERIFIED | Design p.4 L178-187 pins both samplers per contract. Checked against code: additive `best_first_development.random_valid_best_first_output` (uniform `randrange(len(rows))`, L519-521); BFWS `bfws_issue59.random_valid_bfws_model_output` (non-duplicate, admissible-position filter, retire fallback, L1054-1084). |
| 17 | MAJOR | VERIFIED | 5.11 p.8 L406-410 names panel reuse, the adaptive design sequence, and a fresh frozen panel with non-trivial tasks as the required confirmation. Design p.4 L206-210 repeats it. |
| 18 | MAJOR | VERIFIED | PDF text has no comment ID, "issuecomment", "deadline-study", "reviewer" naming, GitHub URL, or institution. PDF Author/Title metadata empty. Author block renders "Anonymous authors". The self-citation (Huang et al., 2026) is in third person, which the guide allows. |
| 19 | MAJOR | VERIFIED (form) | App U exists. Its content is contested in finding 40. |
| 20 | MAJOR | VERIFIED | App Q p.28 L1477-1479 "0/20 on each strain (0/40 in total)". Episode store: 40 learned files (all goal true) and 40 base files. |
| 21 | MINOR | VERIFIED | Abstract L5 is declarative. |
| 22 | MINOR | VERIFIED | All six named paragraphs now carry "% Paragraph purpose:" comments (appendix.tex L64/L375/L397, related_work.tex L8/L11/L14). A scan found no uncommented paragraph after a blank line in the main-text files. |
| 23 | MINOR | VERIFIED | Main-text PDF has 0 prose semicolons. The remaining ones are the App R C* list separator and the author-dictated App U sentence. |
| 24 | MINOR | VERIFIED | Renders as "Statistics appendix" and "Data and Split Procedures appendix"; no mis-resolving "Appendix A". |
| 25 | MINOR | VERIFIED | blg has 0 warnings. |
| 26 | MINOR | VERIFIED | App R L1491-1492 "(up to 315 such decisions in one episode, menus of up to 222 states)". report.json menu_size_range.max = 222. |
| 27 | MINOR | VERIFIED | "skeleton" absent. App S ends "Until these choices are recorded, the held-out evaluation cannot be frozen". "preregistered" absent from PDF. |
| 28 | MINOR | VERIFIED | App G p.20 L1034-1036 "Family-wide (24 eligible P3 variants)". |
| 29 | MINOR | VERIFIED | App M p.25 L1344-1347 explains the two entries per task. Residual: the Intro and 5.4 still print "random-valid 24/24 per modality" without the basis (appendix.tex L727 admits a double count of 12 unique episodes). Not reopened. |
| 30 | MINOR | VERIFIED | "the closeout" absent from reader prose. Ticket numbers are confined to the sanctioned appendix index columns, except the TODO markers (finding 46). |
| 31 | MINOR | VERIFIED | "Learned arms fail later" absent. App N "First failures cluster early". |
| 32 | MINOR | VERIFIED | Intro L7 triple removed. Discussion: "unassisted internal search or general planning autonomy". |
| 33 | MINOR | VERIFIED | 5.1 p.5 L239 gives 68.5244/336. App J gives 53.52 and 68.5244. |
| 34 | MINOR | VERIFIED | App Q L1481-1484 "A post-hoc, unpaired reading, with 10 visual-only episodes per arm against 30 full-scaffold episodes". |
| 35 | MINOR | VERIFIED | results.tex L30/L181, design.tex L62, and intro.tex L37 comments record the 2026-09-21 withdrawal. |
| 36 | MINOR | VERIFIED | No "confirms" in reader prose (the only hit is App H "Render Validation confirms", an infrastructure definition). |

**Tally:** 34 verified, 2 partial (9, 11), 0 not addressed, 0 regressed.

**Disposition of remainders and new findings (2026-09-23, `e5c4c09`):** the partial remainders of findings 9 and 11 are closed (abstract carries the post-hoc task-clustered interval; Appendix O cites shuffled only and flags the pooled contrast). Findings 37-39 and 41-48 are closed per the fixes above. Finding 40 is WONTFIX by author decision: the dictated LLM-usage sentence stays, with the reviewer's desk-rejection risk recorded in `changelog.md`.

### New findings

#### 37 · MAJOR · BENCHMARK checklist (metric argued against near-miss alternatives) / Axis 3 · `iclr2026_conference_results.tex (5.10, fig:zoo-m1); iclr2026_conference_introduction.tex; iclr2026_conference_appendix.tex (App R)`

- **Location:** Figure 1 dashed line labelled "random_valid floor" and caption p.8 L399-401 "random-valid floor .1389 … Random-valid is the floor, not a selector"; Intro p.2 L82-83 "random-valid (.1389) is the floor reference rather than a selector"; App R p.28 L1500 "Random-valid is the zoo floor"
- **Issue:** The "floor" sits above five of the seven plotted arms: learned .1042, novelty-first .1250, bfs-order .0694, worst-first .0556, base 0. No privileged-information selector beats uniform menu choice on M1 (o4/metrics/analysis.json). The zoo therefore has no comparator in the interval (random-valid, exact). It cannot say whether any choice rule registers "choice quality beyond random" on this panel, which is the job the paper gives it in 5.10 ("calibrates this measurement"). Calling random-valid a "floor" and excluding it from the ranking relabels the calibration failure as a definitional choice. The paper never says why goal-agnostic selectors (min-g, novelty) fall below uniform choice at budgets of 6-12 decisions (C* 3-6). Nor does it say whether M1 on these nine tasks can separate any selector from random at all.
- **Fix:** Drop "floor" (e.g., "uniform-choice reference"). In 5.10, state that no comparator between random-valid and exact exists on this panel, so the zoo bounds the adapter only against weaker-than-random rules and cannot calibrate choice quality. **Experiment that would change the verdict:** run the zoo, including one goal-directed privileged selector (e.g., h_add-greedy with random tie-breaks, or exact with ε-random choices at graded ε), on the fresh larger-C* panel that 5.11 already requires. A graded-ε dose ladder that orders exact > ε-exact > random on M1 would show that M1 discriminates, and the adapter's position would then mean something. If informed selectors still fall at or below random, the metric, not the policy, is the bottleneck.
- **Status:** CLOSED (`e5c4c09`)

#### 38 · MAJOR · Axis 4 (limitation omitted from abstract/intro; boundary dropped by compression) · `iclr2026_conference_abstract.tex; iclr2026_conference_introduction.tex; iclr2026_conference_results.tex (5.10); iclr2026_conference_discussion.tex (Conclusion)`

- **Location:** Abstract p.1 L29-34 reports "+0.033 [−0.033, +0.133]" and "(.1042) lies between bfs-order (.0694) and novelty-first selection (.1250)"; Conclusion p.9 L454-455 "the adapter learns to emit valid choices without demonstrating choice quality beyond the named references"; App R p.29 L1522-1527 "selecting the teacher's heap-head state on 23/132 … (17.4%) against an on-policy chance rate of 26.9%, and emitting the last menu label on 72/132 (54.5%)"
- **Issue:** The abstract reports only the favorable-sign contrast, the 2× cap +0.033. It omits that on the paper's pre-registered primary zoo metric the adapter is below random-valid: M1 .1042 vs .1389, paired −0.035 [−0.150, +0.061] (analysis.json m1_m2_m3_dominance_holm.comparisons.random_valid). Compression moved the M4 evidence out of the body; at `5357a65` it sat in Results L420. That evidence shows teacher agreement below chance and a majority last-label habit, which App R itself calls "operationally … a random picker". Stated in the body, these facts turn "choice quality not established" into "choice behaviour indistinguishable from, or worse than, a position habit". A skim of the abstract, Table 2, or Fig. 1 cannot recover that without the appendix.
- **Fix:** Abstract: after the zoo sentence, add "and below random-valid (.1389; paired −0.035 [−0.150, +0.061])". 5.10: one sentence with M4 (17.4% vs 26.9% chance, 54.5% last label under per-decision permutation). Conclusion: "…without choice behaviour distinguishable from a last-label position habit".
- **Status:** CLOSED (`e5c4c09`)

#### 39 · MAJOR · Axis 4 (headline mechanism unpinned) · `iclr2026_conference_appendix.tex (App A/B, App R); iclr2026_conference_search_process_policy.tex`

- **Location:** App A p.13 L691-693 "the expanded state has the minimum f in the frontier under the declared tie-breaking rule"; App B p.14-15 L755-762, where the weighted/greedy invariants state no tie-break; App R p.29 L1530-1533 "heap serials follow the deterministic sorted candidate order at start expansion, so frontier evolution is invariant to submission order"; source comments appendix.tex L46-47, L119-120, L125 and policy.tex L20-21: "Tie-breaking among equal-f states is not pinned in any audited source"
- **Issue:** The paper's named cause for its headline result is submission-order invariance, which is a property of the serial/tie-break rule: serials come from sorted candidate order, not submission order. That rule is never stated in the invariant definitions. The only statement of the mechanism is a one-sentence artifact quote at the end of App R, and the authors' own comments record the rule as unpinned. A reader cannot check whether the 48/48 identity is a property of additive best-first search in general, or an artifact of this implementation's serial assignment. The distinction decides how far the "measurability audit" contribution ports to other runtimes.
- **Fix:** Pin the equal-f tie-break and serial-assignment rule from the executed controller (file and function) in App B, and move the structural-basis sentence into 5.2 or App B. State explicitly that a runtime assigning serials in submission order would not be submission-order invariant, and therefore would not show the identity.
- **Status:** CLOSED (`e5c4c09`)

#### 40 · MAJOR · Submission compliance (LLM disclosure) · `iclr2026_conference_appendix.tex (App U)`

- **Location:** App U p.30 L1617 "An LLM was used only for polishing language; the scientific content is entirely original."
- **Issue:** [INFERENCE] The repository record describes LLM agents drafting and restructuring manuscript text, not only polishing it. changelog.md L14: figures "drawn from the pinned JSONs by a paper-writer with reproducible scripts". Hub L60-63: "one owner per section file … Section agents never edit this file". The citation pass was run by a "related-work-scout" (index row A). Review rounds were run by "paper-reviewer" agents. The ICLR 2026 guide (URL above) requires describing "the precise role of the LLM" when LLMs "played a significant role in research ideation and/or writing", and warns that non-disclosure "can lead to desk rejection". The wording is author-dictated, so this is flagged as a risk, not adjudicated.
- **Fix:** If agents drafted section text, replace App U with a precise description: agent-drafted section text and figure scripts, an agent citation pass with human-verified sources, agent review rounds, and the author verification applied to every number. Otherwise record the decision as declined in changelog.md, so this finding can be marked WONTFIX.
- **Status:** WONTFIX (`e5c4c09`; author decision 2026-09-23, recorded in changelog.md)

#### 41 · MINOR · Axis 3 · `iclr2026_conference_introduction.tex`

- **Location:** Intro p.2 L63-65 "process SFT solved 125 of 288 versus 240 for random-valid, 0 for the base, and 288 for exact, all in additive cells with no decision to make"
- **Issue:** "all" attaches to all four counts. Random-valid's 240 includes 96 BFS/BFWS successes (45+51, tallied from the baseline episode files), and exact's 288 includes 144. The sentence contradicts the "BFS and width-based cells register choice" claim three lines above.
- **Fix:** "process SFT solved 125 of 288, all of them in the additive cells, against 240 for random-valid (96 of them in the choice-registering BFS/BFWS cells), 0 for the base, and 288 for exact".
- **Status:** CLOSED (`e5c4c09`)

#### 42 · MINOR · Axis 4 · `iclr2026_conference_introduction.tex`

- **Location:** Intro p.2 L65-66 "Over 2,910 replayed episodes learned failures are early invariant rejections of applicable operations"; Contribution 3 "Failures localize to invariant rejections"
- **Issue:** Table 3 shows other invariant violations are 229/407 (56.3%) of learned failures. The other 178 are malformed output (72), inapplicable grounded actions (56), effect (27), schema (16), and others, so the bare generalization overstates.
- **Fix:** "the dominant learned failure (229/407) is an invariant rejection of a parsed, applicable operation".
- **Status:** CLOSED (`e5c4c09`)

#### 43 · MINOR · Axis 3 · `iclr2026_conference_discussion.tex`

- **Location:** Discussion p.8-9 L431-433 "As a post-hoc interpretation the candidate menu, the input every arm retains, carries the decision-relevant signal on this panel."
- **Issue:** On these additive cells the identity audit says there is no decision to make (5.2), and App Q L1474-1475 says the null "is equally consistent with a policy that uses no state information". A "decision-relevant signal" on cells with zero decision headroom contradicts both.
- **Fix:** "the menu is the only retained input that could carry the operation-validity signal on this panel".
- **Status:** CLOSED (`e5c4c09`)

#### 44 · MINOR · Axis 3 / Axis 5 · `iclr2026_conference_results.tex (fig:zoo-m1 caption); figures/fig_zoo_m1.py; iclr2026_conference_discussion.tex`

- **Location:** Fig. 1 caption p.8 L400-401 "Intervals overlap and the Holm family licenses no ordering"; Fig. 1 tick labels `exact_reference`, `random_valid`, `learned_adapter`, `pretrained_base`; the in-plot box "Enumeration-contract BFS/BFWS random-valid already registered choice (15/24, 17/24 vs exact 24/24)"; Discussion p.8 L420-422 `\texttt{random\_valid}`/`\texttt{exact\_reference}` and threat item "exact reference solves by construction"
- **Issue:** (a) The exact-reference interval [.7917, .8750] overlaps no other arm, so "Intervals overlap" is false as written. (b) Code identifiers in the figure and Discussion clash with the prose names ("random-valid", "Learned adapter") and yield a lowercase item start. (c) The annotation box puts success counts from another contract and panel on an M1-AUC axis, although Table 1's caption and 5.2 declare the two contracts not comparable.
- **Fix:** Caption: "Intervals of all non-exact arms overlap". Use the prose arm names in the figure and Discussion. Move the enumeration-contract note from the plot area into the caption.
- **Status:** CLOSED (`e5c4c09`)

#### 45 · MINOR · Axis 5 · `iclr2026_conference_appendix.tex`

- **Location:** Table 6 (App F, p.19) and Table 15 (App R/S, p.29) print identical seed-variance rows (21/24, 21/24, 22/24; +0.875/+0.875/+0.917; −0.125/−0.125/−0.083). Table 4 (App E) and Table 7 (App I/J) both list per-branch receipts with ticket columns. Captions and App F/S call Cell A "the headline process-SFT cell".
- **Issue:** The duplicate tables were left over from compression. "Headline process-SFT cell" is legacy framing that contradicts the paper's stated headline (the measurement finding), and the cell's SFT−random-valid is negative at every seed.
- **Fix:** Delete Table 15 and cite Table 6 from App S. Merge Tables 4 and 7. Rename Cell A "the greedy × multimodal replication cell".
- **Status:** CLOSED (`e5c4c09`)

#### 46 · MINOR · Submission hygiene · `iclr2026_conference_experimental_design.tex; iclr2026_conference_results.tex; iclr2026_conference_discussion.tex; iclr2026_conference_reproducibility.tex`

- **Location:** Visible markers in the PDF. Design p.5 L223-224 "[TODO: panel overlap, needs the post-#126 retention manifest, issue #131]"; 5.11 p.8 L404, Discussion p.9 L447, and Reproducibility p.10 L497-498 "[TODO: release URLs, issue #122]".
- **Issue:** The markers are tied to open tickets (#122 and #131 OPEN per `gh`), so the brief's rule is met. They are still the only internal ticket numbers left in the main text, and a PDF uploaded with "[TODO: …]" reads as unfinished. The panel-overlap marker points at the manuscript ticket itself, not an evidence ticket.
- **Fix:** Before upload, replace each marker with prose: "the BFWS-to-BFS panel overlap is not pinned in the retained manifests"; "code and evidence bundles will be provided as anonymous supplementary material". Keep the ticket references in % comments.
- **Status:** CLOSED (`e5c4c09`)

#### 47 · MINOR · Submission compliance · `iclr2026_conference_reproducibility.tex`

- **Location:** Reproducibility Statement p.9 L460 to p.10 L499 (≈1.2 pages: per-window GPU ledgers, corpus sizes, replay counts, bootstrap settings)
- **Issue:** The ICLR 2026 guide asks for a "paragraph-long" statement that "should not itself describe details needed for reproducing the results, but rather reference the parts of the main paper, appendix, and supplemental materials". A results-dense page after the Conclusion invites a page-limit-circumvention reading.
- **Fix:** Compress it to one paragraph of pointers (App C runtime, App D splits, App E ledgers, App F statistics, App I/R choice-frontier, artifact index Table 5).
- **Status:** CLOSED (`e5c4c09`)

#### 48 · MINOR · Figure rendering · `figures/fig_contracts.{py,pdf,png}`

- **Location:** Figure 2 (App T, p.30): the left and right node boxes of both panels are clipped at the canvas edge (visible in fig_contracts.png).
- **Issue:** Cosmetic, but it is one of only two figures.
- **Fix:** Widen the axes limits or add padding in fig_contracts.py and regenerate.
- **Status:** CLOSED (`e5c4c09`; axes padded in fig_contracts.py and the figure regenerated, verified in fig_contracts.png)

## Live fixlist — review 16 (2026-09-23)

**Verdict:** REJECT — 6 CRITICAL, 14 MAJOR, 16 MINOR.

**Reviewer summary (verbatim):**

> Round-1 area-chair review of the assembled #131 draft (37 pages, 0 figures, 17 tables). All nine section files, the hub, the six bibs, the log/blg, and the rendered PDF text were read. Headline numbers were re-read from the pinned artifacts, and the 36 distractor-injection episode records were opened directly. The number transcription is careful: every Results table matches its pinned JSON. The failures are in what those numbers license. (1) The headline says the enumeration contract makes choice quality unmeasurable. The identity audit covers only the 48 additive pairs, and the same contract's BFS/BFWS rows (random 15/24 and 17/24 vs exact 24/24) plus the abstract's own BFWS positive show that choice is measurable there. (2) The menu-manipulation receipt pair cannot discriminate. Under the recorded submission-order invariance, permutation succeeds for any policy that emits any remaining candidate. The 0.6 distractor pick-rate equals uniform chance over the displayed menu (0.56 to 0.63 recomputed from the episode views). The repeated claim that every episode's first emitted operation is a distractor is false: 16/36 episodes open with an accepted operation. (3) Contribution 3 says the zoo places the adapter below named selectors, while its M1 exceeds bfs-order and worst-first. (4) The Discussion misstates the R2 decomposition that Results resolved from JSON. (5) The main text runs about 24 pages against ICLR's strictly enforced 9-page desk-reject limit. MAJOR issues cover the unexamined link between the identity finding and the algorithm-specific success map (learned success appears only where the audit shows no decision to make), a choice-frontier gate that passes by construction with 9 independent tasks and one discriminative task, pooled masked-text channel claims the paper itself retracts, seven TODO markers tied to tickets closed on 2026-09-21, the missing text-game admissible-action literature, an anonymity-breaking GitHub comment ID, and no LLM-usage disclosure. Claim discipline on seeds, saturation, equivalence, expansion parity, and post-hoc labelling is otherwise clean.

### Findings

#### 1 · CRITICAL · `iclr2026_conference_abstract.tex; iclr2026_conference_introduction.tex; iclr2026_conference_discussion.tex`

- **Location:** Abstract L6 'Under the original enumeration contract, where the policy picks each operation from a grounded candidate menu, the answer is that it cannot be measured.'; Abstract L18 'Under the enumeration contract one positive contrast exists, a 15-task width-based best-first development panel (0.933 versus 0.467 for random-valid).'; Intro L42 'under the enumeration contract a grounded action menu makes search-choice quality unmeasurable'; Discussion L24 and Conclusion L132 'Under the enumeration contract, the grounded action menu makes choice quality unmeasurable by construction'
- **Issue:** Axis 1 / Axis 3 / Axis 4. The headline belief update overgeneralizes an additive-only audit, and the abstract contradicts itself. The artifact covers only additive cells: outputs/native-arms/v1/identity-audit.json has pairs_checked 48, with the verdict scoped to 'every additive pair'. Its structural_basis ('finish_expansion() requires the complete candidate set; heap serials are assigned from the deterministic sorted candidate order ... frontier evolution is submission-order invariant') is a property of the additive heap implementation, not of grounded menus. Under the same enumeration contract, Table 5 shows random-valid 15/24 (BFS) and 17/24 (BFWS) against exact 24/24. Table 6 gives random-valid minus exact -0.375 and -0.292 (docs/experiments/expanded-study/synthesis-v1/README.md L48), so decisions change outcomes there. The abstract's own L18 BFWS positive (0.933 vs 0.467) is an enumeration-contract measurement of learned advantage over random-valid, which L6 says cannot exist. The portability claim ('two cheap benchmark-hygiene checks that any grounded-menu evaluation can run', Abstract L21, Discussion L132) is likewise unsupported beyond submission-order-invariant priority queues.
- **Fix:** Scope every headline sentence to the additive best-first cells, e.g. 'On the additive best-first cells of the enumeration contract, where an expansion must submit its complete candidate set and heap order ignores submission order, random-valid is decision-identical to the reference on 48/48 pairs.' Name the cause as submission-order invariance, not the menu. State that BFS/BFWS cells under the same contract do register choice (random-valid 15/24 and 17/24 vs 24/24) and that the learned policy scores 0/24 there. Either run the identity audit on the 48 BFS/BFWS control pairs and report the divergence count, or delete 'any grounded-menu evaluation'.
- **Status:** CLOSED (`1c559e7`)

#### 2 · CRITICAL · `iclr2026_conference_results.tex; iclr2026_conference_abstract.tex; iclr2026_conference_discussion.tex; iclr2026_conference_introduction.tex`

- **Location:** Results L332 'Permutation leaves behavior intact, with 36/36 successes and 0/512 invalid operations, which rules out order-riding ... so the collapse rules out state grounding. The policy reads menu content without verifying applicability against the scene.'; Abstract L8 'Menu manipulation shows what trained policies read instead'; Intro L23 'The policy reads menu content without grounding applicability in the scene.'; Discussion L24 'the trained policy reads menu content and cannot ground actions in state'; Conclusion L132 'it cannot ground actions in state'
- **Issue:** Axis 2 falsifiability: the receipt pair could not have lost, and the pick-rate sits at chance. (a) Per the paper's own structural basis (Results L339, identity-audit.json), additive frontier evolution is submission-order invariant and each decision submits one remaining candidate. Any policy that emits any listed candidate therefore succeeds, including a pure order-rider that always copies the first entry. Permutation 36/36 is guaranteed and cannot rule out order-riding. (b) The pick-rate is not compared with chance. Recomputed from the 36 episode records under outputs/native-arms/v1/evaluation/episodes/menu/*/*/*distractor-injection-learned_adapter.json.gz (events[].view.injected_distractors against events[].input.successor_candidates.rows), uniform picking over the displayed menu gives an expected distractor pick-rate of 0.592 (all listed rows) to 0.625 (unpruned rows) over the 60 injected decisions. The observed 36/60 = 0.6 is at chance. Content-reading and position-picking both predict about 0.6, so neither 'reads menu content' nor 'cannot ground actions in state' is identified. The distractors are also out-of-distribution (training menus contained only applicable actions), so the collapse shows the policy does not reject inapplicable entries it never saw, not an inability to ground. The #132 post-hoc finding (last label 54.5%, Results L1093) points to position habits, the hypothesis permutation was supposed to exclude.
- **Fix:** Report the chance pick-rate next to 0.6 and state that the observed rate is at chance. Replace 'rules out order-riding' with 'is uninformative about order under submission-order invariance'. Replace 'reads menu content' and 'cannot ground actions in state' with 'does not reject schema-valid inapplicable menu entries (pick-rate at chance)'. A discriminating test would inject distractors at a fixed position (first or last) versus random positions and compare pick-rates by position. That experiment separates position-riding from content-reading and would change the verdict on the receipt pair.
- **Status:** CLOSED (`1c559e7`)

#### 3 · CRITICAL · `iclr2026_conference_results.tex; iclr2026_conference_discussion.tex`

- **Location:** Results L332 'and the first emitted operation of every episode is a distractor'; Discussion L24 'collapses under distractor injection (0/36), where the first emitted operation of every episode is an injected inapplicable action'
- **Issue:** Number contradicting the pinned source. outputs/native-arms/v1/stress-evaluation.json gives each distractor-injection cell 9 episodes and 15 decisions (60 decisions over 36 episodes), and episodes terminate on the first invalid operation. The episode records show 20/36 episodes ending on their first decision and 16/36 (8 with two decisions, 8 with three) opening with one or two accepted operations before the distractor pick. Example: visual-nomem-state/expanded-final__ferry-compact-915000/best_first_add_greedy-distractor-injection-learned_adapter.json.gz. There, events 0 and 1 are accepted (sail l1 l0, sail l1 l2) with three injected distractors each, and event 2 (debark c0 l1) is rejected. The closeout (docs/experiments/native-arms/issue-130-closeout.md L13) carries the same error. The pinned JSON and episode records take precedence.
- **Fix:** Replace with 'every episode ends on a distractor pick, 20/36 of them on the first decision'. Add a % Source-conflict comment recording the closeout's wording against stress-evaluation.json and the episode records.
- **Status:** CLOSED (`1c559e7`)

#### 4 · CRITICAL · `iclr2026_conference_introduction.tex; iclr2026_conference_abstract.tex`

- **Location:** Intro L44 contribution 3 'and a comparator zoo places the adapter below named selectors'; Abstract L16 'places the adapter's solve-versus-budget score (.1042) below novelty-first selection (.1250)'
- **Issue:** Claim contradicted by the paper's own Table 12. outputs/choice-frontier/o4/metrics/analysis.json gives M1 learned 0.1042 [0.0278, 0.2014], bfs-order 0.0694 [0.0, 0.1528], worst-first 0.0556 [0.0, 0.1389], novelty-first 0.125 [0.0, 0.2778]. The adapter is above two of the three named selectors and below only novelty-first. Random-valid is the floor, not a selector. Every interval overlaps, and the fifteen-test Holm family licenses no ordering in either direction. The contribution bullet turns a point-estimate ordering against one selector into a general ranking.
- **Fix:** Contribution 3: 'a comparator zoo finds no positive learned Pareto dominance, and on M1 the adapter's point estimate (.1042) lies between bfs-order (.0694) and novelty-first selection (.1250), with overlapping intervals'. Abstract: add 'point estimates, intervals overlap' after the .1250 comparison.
- **Status:** CLOSED (`1c559e7`)

#### 5 · CRITICAL · `iclr2026_conference_discussion.tex`

- **Location:** Discussion L52 'Copyability-preserving shuffling is the information-loss regime, with 34/36 episodes still emitting valid operations while the search fails. Masking is output-contract destruction, with 36/36 episodes all-invalid and 0/18 all-invalid in the new text-masked visual-state cross cell.'
- **Issue:** Two numbers contradict the pinned JSON and the Results text for the same cells. outputs/native-arms/v1/r2-decomposition.json records text-shuffled partial_valid 16 (text) + 15 (multimodal) = 31 and goal_reached 3 (multimodal), so 'the search fails' is false for 3 of the 34. Results L278 records this exact source conflict and resolves it per the JSON, and the Discussion reverts to the closeout's '34/36 partial_valid'. The cross cell in stress-evaluation.json (textmask|text-masked|visual-state, 9+9 episodes, 0 successes, 18 invalid over 18 decisions) is 0/18 success with every episode all-invalid (Results L926-928). 'with ... 0/18 all-invalid' says that no episode was all-invalid.
- **Fix:** 'Copyability-preserving shuffling is the information-loss regime: 31/36 episodes are partial-valid without reaching the goal and 3/36 reach it. Masking is output-contract destruction: 36/36 all-invalid, and the new text-masked visual-state cross cell scores 0/18 with every episode all-invalid.'
- **Status:** CLOSED (`1c559e7`)

#### 6 · CRITICAL · `iclr2026_conference.tex (assembled PDF)`

- **Location:** Rendered PDF: Introduction starts p.1 and the Conclusion ends p.25 (manuscript.pdf, 37 pages); hub L3 '\usepackage{iclr2026_conference,times}'
- **Issue:** Submission blocker. The main text runs about 24 pages. The ICLR 2026 Author Guide (https://iclr.cc/Conferences/2026/AuthorGuide, fetched 2026-09-23) states 'At the time of submission, the main text should be 9 pages or fewer ... This limit will be strictly enforced. Papers with main text beyond the page limit will be desk-rejected.' Graded CRITICAL because desk rejection precedes any review. Venue-year mismatch in addition: the draft uses the ICLR 2026 template ('Under review as a conference paper at ICLR 2026') while citing ICLR 2026 proceedings (Kokel et al., 2026, 'The Fourteenth International Conference on Learning Representations (ICLR 2026)'). The ICLR 2026 submission cycle closed in September 2025.
- **Fix:** Confirm the target venue and cycle and swap in its style file. Cut the main text to the limit. Move Tables 3, 7, 8, 13, most of Sections 5.3-5.4, and Section 4's staged list to the appendix, and keep the identity finding, the choice-frontier contract, Table 11, Table 12, and one figure (I14) in the body.
- **Status:** CLOSED (`3c558bf`)

#### 7 · MAJOR · `iclr2026_conference_introduction.tex; iclr2026_conference_results.tex; iclr2026_conference_discussion.tex`

- **Location:** Intro L35 'so the additive-family result replicates across backbones, and the earlier BFS null on that backbone is an algorithm confound'; Results L233 'The earlier total null is therefore an algorithm confound. Under the same backbone, recipe, and panel shape, the additive-family result replicates on a second backbone.'; Discussion L37 'The additive best-first result replicates on a second backbone'; Discussion L41 'The pattern is algorithm-specific, not modality-specific.'; Conclusion L132 'that family replicates on a second backbone'
- **Issue:** Axis 3 / Axis 4. The paper never connects its identity finding to its own success map. By Results L339, additive cells of the enumeration contract carry no decision, so learned success there measures operation validity. Learned success appears only in those cells. On the choice-sensitive BFS/BFWS cells every baseline SFT episode fails (144/144) and DAgger BFS arms fail 155/162, and these account for most of the 229 other_invariant_violation failures (docs/experiments/expanded-study/failure-mechanism-analysis.md L185-191). Random-valid solves 15/24 and 17/24 there. What 'replicates across backbones' is contract fluency (R3 random-valid 24/24 per modality, SFT below it, second-backbone-v3/evaluation/analysis.json). The 'algorithm confound' is at least equally a choice-requirement confound, and 'algorithm-specific, not modality-specific' is a non-significance reading. 'Therefore an algorithm confound' is a causal verdict from a v2-versus-v3 comparison with fresh qualification and probe under a new protocol version.
- **Fix:** Say what the evidence shows: 'Learned success under the enumeration contract appears only in the additive cells, where the identity audit shows no decision to make, and the InternVL v3 cell replicates that contract fluency (31/36 vs 0/36 base, below random-valid 24/24 per modality).' Replace 'therefore an algorithm confound' with 'is consistent with an algorithm (choice-requirement) difference rather than a backbone null'. Drop 'not modality-specific'.
- **Status:** CLOSED (`1c559e7`)

#### 8 · MAJOR · `iclr2026_conference_discussion.tex`

- **Location:** Discussion L37 'and it is the only panel where random-valid falls below saturation'; Discussion L85 'The BFWS development panel is the only enumeration-contract panel where random-valid falls below 1.0'
- **Issue:** Axis 3. Contradicted by the paper's own tables. Random-valid is below saturation on expanded-baseline BFS 15/24 and BFWS 17/24 (Table 5, enumeration contract), on the DAgger unseen panel 45/72 (Table 7), on second-backbone v2 54/72 (Results L851), and under the choice-frontier contract 32/90 (Table 11).
- **Fix:** 'the only development panel on which random-valid falls below saturation and a positive learned contrast is reported'. State that the expanded-baseline BFS/BFWS cells are unsaturated and the learned policy scores 0/24 on them.
- **Status:** CLOSED (`1c559e7`)

#### 9 · MAJOR · `iclr2026_conference_abstract.tex; iclr2026_conference_introduction.tex; iclr2026_conference_results.tex`

- **Location:** Abstract L11 'Its own identity audit was a pre-registered pass condition and passes with 18/18 control pairs divergent, and headroom becomes measurable (... $-0.644$, 95\% CI $[-0.856, -0.422]$)'; Intro L43 'Its identity audit was a pre-registered pass condition, and it passes, so choice headroom becomes measurable.'; Results L375 'The frozen bootstrap resamples cells. Post-hoc task-clustered intervals ... [-0.889, -0.333]'
- **Issue:** Axis 2 falsifiability plus BENCHMARK operationalization. (a) The gate passes by construction. outputs/choice-frontier/v1/evaluation/identity-audit.json basis: 'random_valid (uniform menu choice) and exact_reference (heap head) diverge whenever a decision sees a frontier of size >= 2'. The preparation audit (preparation/visual-choice-frontier/audit.json, headroom_present true, 58 episodes) had already guaranteed such decisions. Exact solves 18/18 by budget construction (Discussion L1251). The advertised contribution is a sanity check that could not realistically fail. (b) 18/18 is 9 independent divergences: in identity-audit.json each task's greedy and w3 pairs have identical exact and random decision/expansion counts (e.g. 15puzzle-compact 5/4 vs 8/8 in both), per closeout Erratum item 2. The abstract and intro quote only the cell-level interval, whose post-hoc task-clustered counterpart is wider ([-0.889, -0.333]). (c) The instrument's resolution between non-oracle policies is one task. M5 holds only storage (o4/metrics/analysis.json m5_informative_tasks_D), and random-valid is 0 or 1 on the other 8. The panel tasks have C* 3-6 (optimal-costs.json) and exact expansions 3-6. The identity check and M1 are not argued against near-miss alternatives (e.g. a static count of decisions with two or more admissible options, or chance-corrected teacher agreement as the primary endpoint).
- **Fix:** Abstract and intro: 'passes on 9/9 tasks (18 cells, control sequences coincide across the two algorithms)', and give the task-clustered interval next to the frozen one. Describe the gate as a sanity check that holds by construction whenever a menu offers two or more states. Replace 'headroom becomes measurable' with 'random-valid and exact separate. Policy-level resolution currently rests on one discriminative task.' A frozen panel with at least eight discriminative tasks (the #133 boundary) is the experiment that would make the instrument claim stand.
- **Status:** CLOSED (`1c559e7`)

#### 10 · MAJOR · `iclr2026_conference_results.tex; iclr2026_conference_experimental_design.tex; iclr2026_conference_appendix.tex`

- **Location:** Results L348 'The training corpus was derived on CPU from 29 training tasks, independently of the stored exact traces'; Design L104 'train on a corpus re-derived through the new contract on CPU from the stored exact traces'; Appendix I 'The corpus replays the frozen paired-phase exact traces through the new contract on CPU'
- **Issue:** Axis 3. Three sections give opposite provenance for the same corpus. The closeout (issue-132-closeout.md L66) says 'derived independently of the stored exact traces'. The preparation report says 'every derived episode matched its stored exact trace expansion for expansion' (report.json expansion_gate). A reader cannot tell whether the corpus is a replay of stored traces or an independent re-derivation checked against them.
- **Fix:** One sentence used in all three places: 'derived on CPU by replaying the frozen exact traces through the new contract and verified expansion-for-expansion against them (58 episodes bit-exact)'. If 'independently' means an independent re-derivation, say 'independently re-derived and checked against the stored exact traces'.
- **Status:** CLOSED (`1c559e7`)

#### 11 · MAJOR · `iclr2026_conference_introduction.tex; iclr2026_conference_appendix.tex; iclr2026_conference_discussion.tex`

- **Location:** Intro L35 'Observation corruption localizes the learned controller in the language channel. Masking or shuffling it drops success by up to 0.944'; Intro L44 'the learned controller runs on the textual scaffold rather than the rendered state'; Appendix L419 'The observation-corruption suite (#126) confirms this empirically: corrupting the text channel drops success by up to $-0.944$'; Discussion L52 'the multimodal text-minus-visual isolation contrast is $-0.694$ $[-0.889, -0.472]$'
- **Issue:** Axis 4. Results L930 states 'The language-channel claim survives only in its shuffled form', and #131 comment 1 is binding on this. Yet the intro, contributions, and appendix still pool the masked regime, which R2 shows is output-contract destruction (r2-decomposition.json: 36/36 all_invalid). The isolation contrast -0.694 uses a text-channel term of -0.806, which averages masked (-0.889) and shuffled (-0.722) (issue-126-closeout.md L63-65), so it is contaminated by the destroyed-contract regime. 'Confirms' is the wrong register.
- **Fix:** Cite shuffled only: 'copyability-preserving text shuffling lowers success by -0.944 (text) and -0.722 (multimodal), while visual corruption costs at most -0.111'. Flag the -0.694 isolation contrast as pooling a contract-destruction regime. Replace 'confirms' with 'is consistent with'.
- **Status:** CLOSED (`1c559e7`)

#### 12 · MAJOR · `iclr2026_conference_introduction.tex; iclr2026_conference_experimental_design.tex; iclr2026_conference_results.tex; iclr2026_conference_discussion.tex`

- **Location:** Intro L48 '[TODO: issues \#96/\#98/\#102/\#103]'; Design L133 'remain unexecuted (issues #96 and #98 open)' with '[TODO: full-scope v1, issues \#96/\#98]'; Results L36 'the corresponding issues remain open [TODO: ...]'; Results L171, L233 'with its issues still open [TODO: ...]'; Results L449; Discussion L123
- **Issue:** TODO hygiene and a false factual statement. `gh issue view` (2026-09-23) returns #96, #98, #102, #103 all CLOSED on 2026-09-21 (stateReason COMPLETED), each with a closing comment 'Supervisor decision: v1 scope withdrawn — closing'. Seven visible markers and at least six prose sentences tie the manuscript to tickets that no longer exist as open work. The brief's rule requires every visible TODO to be tied to an open ticket, and the round-2 rule drops markers that the prose already states (Design L133 and Results L171 do both).
- **Fix:** Delete all seven markers and the stale % TODO comments (Results L172, L236, L450, Design L135, Intro L49). Rewrite the prose as 'the full-scope v1 branches were withdrawn after their terminal VALID_STOP receipts (issues #96/#98/#102/#103, closed 2026-09-21) and will not be executed'.
- **Status:** CLOSED (`afec954`)

#### 13 · MAJOR · `iclr2026_conference_results.tex`

- **Location:** Results L30 section roadmap 'Sections 5.5 to 5.9 report the follow-up audits in argument order, from channel tests and image-only arms to menu manipulation, the enumeration-contract identity finding'; Results L299 (5.6) 'The decision-relevant signal these policies use is the grounded unscored candidate menu itself'; identity finding first appears at 5.8 (PDF p.19)
- **Issue:** Axis 5 and the argument-order rule. The abstract and intro lead with the identity finding, but Results reaches it only at 5.8 after 18 pages. The native-arms 'leak' interpretation (5.6) and the menu-manipulation verdict (5.7) come before the structural basis that explains both (submission-order invariance, 5.8). Sections 5.2-5.4 interpret the additive old-contract rows as learned success before the audit that reclassifies them as operation validity. Interpretation precedes its receipt.
- **Fix:** Put the identity audit immediately after 5.1 as the first follow-up receipt. Then give menu manipulation (reinterpreted per I2), native arms, the choice-frontier redesign, and the zoo, and add a forward note in 5.2 that the additive rows are reinterpreted by that audit.
- **Status:** CLOSED (`1c559e7`)

#### 14 · MAJOR · `all section files`

- **Location:** 0 figure environments, 0 \includegraphics across the nine section files and the hub, versus 17 table environments. The first table is the related-work axis table (Table 1)
- **Issue:** Axis 1 / Axis 5. The tension (random-valid identical to exact under one contract, separated under the other) exists only in prose and in Tables 5, 11, and 12. A skimming reviewer's 10-minute test lands on a related-work design-axis table.
- **Fix:** Add a Fig. 1 with two panels. (a) The enumeration versus choice-frontier contract on one additive task. (b) Solve fraction versus budget multiplier (M1 curves) for exact, random-valid, learned, and the three selectors, with the BFS/BFWS enumeration-contract random-valid points marked to show where choice was already measurable (I1).
- **Status:** CLOSED (`3c558bf`)

#### 15 · MAJOR · `iclr2026_conference_related_work.tex`

- **Location:** Related Work 'Evaluation-validity work in planning and reasoning ...' paragraph (L70ff), which cites PlanBench, BEHAVIOR-1K, VQA priors, and video MCQ position bias but no action-candidate literature
- **Issue:** Citation failure on the headline claim's anchor. That grounded admissible-action lists are privileged information which changes what an agent's success measures is published practice in text-based game RL: Jericho's valid-action handicap (Hausknecht et al., 2020, arXiv:1909.05398). CALM (Yao et al., EMNLP 2020, arXiv:2010.02903, abstract fetched 2026-09-23) states that its generator 'is competitive with or better than other models that have access to ground truth admissible actions'. Multiple-choice position bias in LLM selectors is also directly relevant to the last-label finding. Without these, the 'measurement finding' reads as a discovery when it is a known handicap in a new setting.
- **Fix:** Add a sentence citing Jericho's valid-action handicap and CALM (verified keys in related_refs.bib) and reframe the contribution as operationalizing a per-decision identity check for that known handicap in search-execution evaluation.
- **Status:** CLOSED (`afec954`)

#### 16 · MAJOR · `iclr2026_conference_experimental_design.tex`

- **Location:** Design L36 'The frozen protocol has not yet pinned the validity-constrained sampling distribution, the candidate access granted to the control, the runtime filtering step, or the explicit absence of retry and repair.'
- **Issue:** Axis 4 / Axis 3. Random-valid is the pivot of the identity audit, Table 5, Table 6, the BFWS 0.467, and every learned-to-control gain, yet its sampling distribution under the enumeration contract is declared unpinned. Under the choice-frontier contract the same name denotes uniform menu choice (identity-audit.json basis), a different distribution. The paper's central comparator is undefined in one contract and redefined in the other.
- **Fix:** Pin the enumeration-contract random-valid sampler from the executed code (distribution, candidate access, filtering, retry) in Section 4 or Appendix C, and give the choice-frontier control a distinct name or an explicit per-contract definition.
- **Status:** CLOSED (`1c559e7`)

#### 17 · MAJOR · `iclr2026_conference_experimental_design.tex; iclr2026_conference_results.tex`

- **Location:** Design L104 'The choice-frontier evaluation reuses the frozen 9-task native-arms membership under both additive algorithms.'; Results 5.9 'the 144 stored #132 episodes enter it post-hoc'
- **Issue:** Axis 2 post-hoc smell and BENCHMARK adoption risk. The same nine tasks (8 domains, 7 compact / 2 expanded) serve #126, #129, #130 R1, #132, and #133. The #132 redesign was frozen after #130 outcomes on those tasks, and the #133 metric set after #132 outcomes on them. No discover-then-confirm step exists: no fresh panel, no held-out tasks for the new contract. The tasks are the cheapest members (C* 3-6, optimal-costs.json).
- **Fix:** State the panel reuse and its adaptive-overfitting risk in the Section 5.10 boundary. Name a fresh frozen choice-frontier panel, drawn outside these nine and including non-trivial tasks, as the required confirmation before any instrument-level claim.
- **Status:** CLOSED (`1c559e7`)

#### 18 · MAJOR · `iclr2026_conference_appendix.tex; iclr2026_conference_reproducibility.tex; iclr2026_conference_experimental_design.tex`

- **Location:** Appendix L315 'Issue \#133 closing comment (comment 5788941573)'; Reproducibility L76 'The existing \texttt{deadline-study-v1} release'; Design L161 'Reviewer stress tests (issue \#130, executed)'
- **Issue:** Double-blind risk. A GitHub comment ID resolves to one public repository and its author (#131 cites it as https://github.com/Sino-Huang/multimodality_on_planning/issues/133#issuecomment-5788941573). Named internal releases and 'reviewer stress tests' / 'reviewer-blocker window' (Results L643, Table 3) also expose the project's prior review history.
- **Fix:** Remove the comment ID and internal release name from the submission (keep them in the % Evidence comments). Rename 'Reviewer stress tests' / 'reviewer-blocker window' to neutral protocol names (e.g. 'stress tests R1-R4').
- **Status:** CLOSED (`afec954`)

#### 19 · MAJOR · `iclr2026_conference.tex (no section)`

- **Location:** No LLM-usage section anywhere in the nine section files or the appendix
- **Issue:** Submission compliance. The ICLR 2026 Author Guide (URL in I6) requires a separate LLM-usage section when LLMs 'played a significant role in research ideation and/or writing' and warns 'Not disclosing significant LLM usage can lead to desk rejection.' [INFERENCE] The #131 briefs and the section STATUS banners record agent-driven writing rounds, which meets that threshold.
- **Fix:** Add an appendix section 'LLM Usage' describing the agent-assisted writing, citation, and review passes and the human verification applied.
- **Status:** CLOSED (`afec954`)

#### 20 · MAJOR · `iclr2026_conference_results.tex`

- **Location:** Results L303 'The learned adapters succeed on 10/10 shifted-init and 10/10 scale-up episodes for both arms, and the pretrained base scores 0/20.'
- **Issue:** Denominator does not close against the pinned source. outputs/native-arms/v1/stress-evaluation.json has 8 variant cells of 10 episodes (5 successes, 5 invalid each), and the episode store holds 40 learned_adapter and 40 pretrained_base variant files (80 total, matching Table 3's '80 variant'). The base total is 0/40. '0/20' holds only per family, and read as written, 40 learned + 20 base = 60 does not match the 80 reported in Table 3.
- **Fix:** '... and the pretrained base scores 0/20 on each strain (0/40 in total)'.
- **Status:** CLOSED (`1c559e7`)

#### 21 · MINOR · `iclr2026_conference_abstract.tex`

- **Location:** Abstract L5-6 '... and ask whether such training can be measured to improve search choice. Under the original enumeration contract, ..., the answer is that it cannot be measured.'
- **Issue:** Style rule: rhetorical question followed by its answer.
- **Fix:** State the finding declaratively (and scoped per I1).
- **Status:** CLOSED (`afec954`)

#### 22 · MINOR · `iclr2026_conference_appendix.tex; iclr2026_conference_related_work.tex`

- **Location:** Paragraphs without a preceding '% Paragraph purpose:' comment: Appendix L62 ('The two broad categories are ...'), L368 ('Cell~A is the headline ...'), L389 ('This addendum supersedes ...'); Related Work L44 ('Step-level and process supervision ...'), L51 ('Recent work uses visual intermediate states ...'), L63 ('Constrained-decoding methods ...')
- **Issue:** Paragraph-purpose convention violated in six paragraphs.
- **Fix:** Add a '% Paragraph purpose:' line before each.
- **Status:** CLOSED (`afec954`)

#### 23 · MINOR · `iclr2026_conference_results.tex`

- **Location:** Results L434 caption 'Seeds 17/29/71 frozen pre-launch; 534 new episodes independently replayed; aggregation descriptive ($n{=}3$).'; Results L171 'visual 41/50; by algorithm, greedy 67/75'
- **Issue:** Prose semicolons outside comma-lists (8 semicolons in Results. The L251 and L388 ones are list separators and acceptable).
- **Fix:** Split into sentences or use commas.
- **Status:** CLOSED (`afec954`)

#### 24 · MINOR · `iclr2026_conference_experimental_design.tex; iclr2026_conference_reproducibility.tex`

- **Location:** Design L52 'never summed with the 336 GPU-hour program ledger (Appendix~\ref{appendix})'; Design L104 'Contrasts use the paired conventions of Appendix~\ref{appendix}'; Reproducibility L65 '(Appendix~\ref{appendix})'
- **Issue:** The frozen label resolves to Appendix A (Operation Schemas), but the ledger is in Appendix E and the bootstrap conventions in Appendix F. Rendered text reads 'Appendix A' in all three places.
- **Fix:** Write 'Appendix~\ref{appendix}, Receipt Tables' / 'Statistics' or add named in-appendix labels owned by the appendix file.
- **Status:** CLOSED (`afec954`)

#### 25 · MINOR · `iclr2026_conference_related_refs.bib`

- **Location:** iclr2026_conference.blg L11 'Warning--can't use both volume and number fields in orseau2021policyguided'
- **Issue:** BibTeX warning, the same class critic-15 fixed for the BFWS entry.
- **Fix:** Drop `number` from orseau2021policyguided.
- **Status:** CLOSED (`afec954`)

#### 26 · MINOR · `iclr2026_conference_results.tex`

- **Location:** Results L348 'every corpus episode carries at least one decision whose menu offers two or more states (maximum 315)'
- **Issue:** Ambiguous number. 315 is the maximum count of multi-option decisions in one episode (preparation/visual-choice-frontier/audit.json headroom_decisions_per_episode, astar-pair-68102553...:best_first_add_w3). The maximum menu size is 222 (report.json menu_size_range.max). The closeout's 'max menu 315' is wrong, and the sentence invites that reading.
- **Fix:** '(up to 315 such decisions in one episode, menus of up to 222 states)'.
- **Status:** CLOSED (`1c559e7`)

#### 27 · MINOR · `iclr2026_conference_experimental_design.tex`

- **Location:** Design L152 'Until these choices are set, the manuscript is a result-ready empirical skeleton rather than a preregistered evaluation protocol.'
- **Issue:** Leftover planning-document sentence. It calls the paper a skeleton and contradicts the pre-registered follow-up protocols reported elsewhere. Spelling alternates 'preregistered' (Design L124, L152, Discussion L139) and 'pre-registered' (everywhere else).
- **Fix:** Replace with 'Until these choices are recorded, the held-out evaluation cannot be frozen.' and normalize to 'pre-registered'.
- **Status:** CLOSED (`afec954`)

#### 28 · MINOR · `iclr2026_conference_appendix.tex; iclr2026_conference_results.tex`

- **Location:** Appendix L428 'information-lossy: 24/24 variants are text-lossy, 18/24 are multimodal-lossy, and 0/24 are visual-lossy'; Results L171 'all 5 admitted variants are text-lossy, 3 multimodal-lossy, and 0 visual-lossy'
- **Issue:** Same stratum with two denominators and no label. 24 is the family-wide eligible P3 set and 5 the admitted subset (issue-124-closeout.md L111-114).
- **Fix:** Appendix: 'family-wide (24 eligible P3 variants)'.
- **Status:** CLOSED (`1c559e7`)

#### 29 · MINOR · `iclr2026_conference_results.tex`

- **Location:** Results L225 'Random-valid and exact reference both score 24/24 per modality.' (12-task key-cell panel)
- **Issue:** Control denominators (24 per modality) exceed the 12 panel tasks per modality with no explanation, while model rows are /12 (second-backbone-v3/evaluation/analysis.json by_modality: episodes 12, random_valid_successes 24).
- **Fix:** State what the 24 control episodes per modality are (e.g. two reused control episodes per task).
- **Status:** CLOSED (`1c559e7`)

#### 30 · MINOR · `iclr2026_conference_introduction.tex; iclr2026_conference_results.tex`

- **Location:** Intro L27 'which the closeout reads as a menu leak'; Results L299 'This null licenses the leak interpretation the closeout records'
- **Issue:** Internal project documents ('the closeout') cited as interpretive authority in reader-facing prose. About 94 internal issue numbers appear in the body.
- **Fix:** State the interpretation as the paper's own and move ticket numbers into % Evidence comments or one appendix index.
- **Status:** CLOSED (`afec954`)

#### 31 · MINOR · `iclr2026_conference_discussion.tex`

- **Location:** Discussion L45 'Learned arms fail later.' followed by 'Learned first failures cluster in steps 0-2 (137/88/46)'
- **Issue:** 137 of 407 learned first failures occur at decision 0, the same index as every base failure, so 'later' contradicts the next sentence.
- **Fix:** 'Learned arms fail early but mostly after parsing: ...'.
- **Status:** CLOSED (`1c559e7`)

#### 32 · MINOR · `iclr2026_conference_introduction.tex; iclr2026_conference_discussion.tex`

- **Location:** Intro L7 'instances to be generated systematically, solutions verified automatically, and difficulty controlled precisely'; Discussion L29 'conducts unassisted internal search, holds unbounded frontier state, or possesses general planning autonomy'
- **Issue:** Rule-of-three constructions.
- **Fix:** Cut to two items or restructure.
- **Status:** CLOSED (`afec954`)

#### 33 · MINOR · `iclr2026_conference_results.tex`

- **Location:** Results L36 'spent 53.52 of those hours (15.9\%) at the #120 synthesis snapshot, before the #126/#127 addenda'
- **Issue:** Results reports only the stale snapshot. The current program total 68.5244/336 appears only in the Reproducibility statement and in Appendix Table 15 (as 68.52), so a Results reader never sees the ledger the rest of the paper uses.
- **Fix:** Add 'and 68.5244 after the #126/#127 addenda' to the same sentence.
- **Status:** CLOSED (`1c559e7`)

#### 34 · MINOR · `iclr2026_conference_results.tex`

- **Location:** Results L303 'which suggests the scaffold's scalar and bookkeeping text carried no useful signal on these variants'
- **Issue:** Unpaired and not matched: native arms 10 episodes per arm (visual only) against full-scaffold 30 episodes pooled over three modalities. The inference is post-hoc and unlabelled.
- **Fix:** Label as post-hoc and unpaired, or drop the 'suggests' clause.
- **Status:** CLOSED (`1c559e7`)

#### 35 · MINOR · `iclr2026_conference_results.tex; iclr2026_conference_experimental_design.tex; iclr2026_conference_introduction.tex`

- **Location:** Results L172 '% TODO: #96/#98 remain open'; Results L236; Results L450; Design L135 '% #102/#103 (second backbone) remain open'; Intro L49
- **Issue:** Stale source comments that restate the false ticket status (see I12). They will mislead the next writer.
- **Fix:** Update with the 2026-09-21 withdrawal.
- **Status:** CLOSED (`1c559e7`)

#### 36 · MINOR · `iclr2026_conference_discussion.tex`

- **Location:** Discussion L52 'Menu manipulation then confirms that the policy reads that menu by content.'; Discussion L29 'The successor-prediction null confirms the runtime dependence'
- **Issue:** Axis 2 wording register ('confirms'). The first instance is also substantively unsupported (I2).
- **Fix:** Replace with 'is consistent with' and scope per I2.
- **Status:** CLOSED (`1c559e7`)

## Closed history

Reviews 1--14 predate the multi-file draft and the #131 round. They audited design artifacts, the title, the abstract, or the introduction at earlier evidence boundaries; each was resolved in the revision that followed it, and none of their findings remain open. Review 15 audited the 2026-09-22 full draft and gated the revision that became commit `4d5842e`. Full text of every folded file is recoverable from git history:

```
git show 5357a65:manuscript/critics/2026-09-22-critic-15.md
git log --diff-filter=D --oneline -- manuscript/critics   # the deletion commit
```