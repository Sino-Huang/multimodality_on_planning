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
| 18 | 2026-09-23 | paper-reviewer (area-chair tier) | Round-3 re-review at `19a641b` (clean tree): nine section files, hub, six bibs, log/blg, rendered 29-page PDF, both figure assets and scripts, headline numbers re-derived from the pinned JSONs, ledgers, and episode stores | WEAK REJECT (0 CRITICAL, 6 MAJOR, 13 MINOR, counting the 2 partial remainders) | SUPERSEDED by 19 (all findings closed except 49 and 60, carried into 19 and blocked on issue #134) |
| 19 | 2026-09-23 | paper-reviewer (area-chair tier) | Round-3 re-review at `1281c1b` (clean tree): nine section files, hub, six bibs, log/blg, rendered 29-page PDF, both figure assets and scripts, numbers re-checked against the pinned JSONs, CSVs, and ledgers, and a sample of the new `%` Evidence comments checked for path and key | WEAK REJECT (0 CRITICAL, 1 MAJOR, 8 MINOR) | CLOSED (`59e8714`; 49 and 60 closed with #134; 40 WONTFIX) |
| 20 | 2026-09-25 | paper-reviewer (area-chair tier) | Round-5 re-review at `0277de7` (clean tree): rendered 35-page PDF, nine section files, hub, six bibs, log/blg, all three figure scripts and PNGs (28/28 fig_ladder asserts re-run), every round-5 number and all cells of Tables 19-21 re-derived from the pinned #138-#140 JSONs and ledgers, 16 `%` Evidence comments checked | WEAK REJECT, rating 4 (S 3 / P 2 / C 2, confidence 4); 0 CRITICAL, 2 MAJOR, 10 MINOR | CLOSED (70-80 `e7346aa`; 69 `e7346aa` + `e2eb87c` after #141/#142; 40 WONTFIX) |
| 21 | 2026-09-25 | paper-reviewer (area-chair tier) | Round-6 re-review at `ba7d4d2` (clean tree): rendered 37-page PDF, word diffs since `0277de7`, figures and scripts (30/30 fig_ladder checks re-run), every round-6 number and all cells of Tables 22 and 24 re-derived from the #141/#142 JSONs and ledgers, 14 `%` Evidence comments checked | WEAK REJECT, rating 4 (S 3 / P 2 / C 2, confidence 4); 0 CRITICAL, 1 MAJOR, 5 MINOR | CLOSED (`58e661e`; 40 WONTFIX; experiments filed as #143/#144) |
| 22 | 2026-09-25 | paper-reviewer (area-chair tier) | Round-7 re-review at 3c9b434 (clean tree): readability rewrite since 7bf48aa, rendered 38-page PDF, numeric-token diff of all 11 .tex files against 7bf48aa, 31 rendered numbers re-derived, both figure scripts re-run (12 + 30 checks), 18 % Evidence comments resolved, log/blg | WEAK REJECT, rating 4 (S 3 / P 3 / C 2, confidence 4); 0 CRITICAL, 2 MAJOR, 12 MINOR | OPEN |
| B | 2026-09-25 | paper-reviewer (cold read) | Round-7 10-minute skim test at `3c9b434`: title, abstract, Figure 1, first sentence of every body paragraph, contributions, Conclusion | no rating; takeaway, skim losses, undefined terms, three changes | OPEN |

## Live fixlist — review 22 (2026-09-25)


**Verdict:** WEAK REJECT. 0 CRITICAL, 2 MAJOR, 12 MINOR.
- MAJOR: findings 85 and 86.
- MINOR: new findings 87-96, the regressed part of review-21 finding 82, and the remainder of finding 80.
- Fix class: MEANING for 88 only. Everything else is WORDING: the fix puts back a scope or caveat that round 7 dropped, and no approved claim changes.
- Finding 40 was replaced in round 7 by author decision. Its compliance risk is assessed separately below, outside the rating and the count.

The number set is unchanged. Round 7 added no token and dropped none. All 31 rendered numbers I re-derived match their pinned artifacts. Both figure scripts pass. The build is clean, and the main text is 8 pages.

Most damaging issue: **finding 85** (Axis 1 with Axis 4). The redrawn Figure 1 teaser says "success measures validity" for the whole enumeration contract. The paper's own evidence limits that to the additive cells under sorted tie-breaking. The same box of the figure prints the counterexample ("submission-order serials: 19/48 divergent"), and Section 5.2 says the BFS and BFWS cells of that contract register choice.

Genre: BENCHMARK (+ FINDINGS)

Δbelief: The findings, unchanged from review 21:
- On the authors' additive best-first runtime, the identity audit returns both verdicts: 48/48 pairs identical under sorted tie-breaking, 19/48 divergent under submission order.
- A choice-frontier M1 passes a pre-registered exact-ε ladder on a validation panel and a screened held-out panel.
- An imitation-trained, scene-only VLM adapter beats uniform frontier choice (D3 +0.285, held-out +0.416, unscreened +0.149). It is interval-separated above the ε-0.75 rung only on the 11-task held-out panel.
- A zero-shot base model scores as uniform choice on the validation panel.
- On LLM-First Search (LFS), a zero-token chooser solves every task by construction.

The skimmer's update is "check that decisions diverge and that the budget binds decisions before reading random-valid success as choice". It is the same as review 21's. Round 7 promoted it to the thesis, but its second half is the compute-matched-baseline principle.

Ledger: Closed: 81, 83, 84, 75 remainder, 80 (i) and (ii) · Regressed: 82* (part e reverted; part d fixed in the appendix only) · Still open: 80 (iii)*, plus new instances of the same pattern · Wontfix: none (40 replaced by author decision, assessed below) · Withdrawn: none · Not rechecked: none · New: 85-96

**Reviewer summary:**

> This round-7 re-review covers HEAD `3c9b434` on a clean tree: the readability and expert-style rewrite `c00ea8b..3c9b434`. I read:
> - all 38 pages of the rendered PDF (`pdftotext -layout`), and the word-level diff of every section file against `7bf48aa`;
> - the redrawn `fig_contracts.py` and its PNG, and the `CONTEXT.md` prose-name table;
> - the round-7 changelog entry and `local://style-sheet.md`.
>
> Round 7 made no number change: 0 numeric tokens appear in HEAD that are absent from `7bf48aa`, and 0 were lost. I re-derived 31 rendered numbers from the pinned artifacts, all of which are md5-identical to review 21's, and all 31 match. Both figure scripts pass their checks, run read-only from temporary copies. The build is clean, and the Conclusion now ends on p.8, which leaves a page of slack.
>
> The rewrite achieves most of its readability targets:
> - mean sentence length 17.2 words, down from 25.0;
> - one sentence over 40 words, down from 25;
> - no paragraph over 6 sentences;
> - an abstract of about 205 words, down from 327.
>
> The compression moved meaning in five places, all new in round 7:
> - Figure 1's takeaway "success measures validity" drops its scope (85).
> - The Intro and Discussion topic sentences say the external audits show both checks are needed, when both external interfaces passed the identity audit at once (86).
> - Contribution 4 claims "the budget check" as a contribution (88).
> - The abstract drops the caveats that `CONTEXT.md` requires there (89).
> - The zero-shot topic sentence reverts review 21's 82(e) fix.
>
> The rating does not move. The two MAJOR items are cheap wording fixes. The contribution-side reasons of review 21 (one non-trivial realisable policy, one backbone, no modality contrast under the choice-frontier contract) are untouched, because round 7 ran no experiment.

### Rating

**Rating: 4** (ICLR 2026 scale {0, 2, 4, 6, 8, 10}; 4 = marginally below the acceptance threshold)

- **Soundness: 3** (good). Nothing changed in the evidence:
  - The endpoints are pre-registered, the intervals are paired and task-clustered, and all episodes are replayed.
  - Failures are reported: #134 PREDICTION_FAILED, DAgger NOT_SEPARATED, the zero-shot held-out verdict INCONCLUSIVE, and InternVL not run.
  - The LFS result is now honestly framed as by construction.
  - The one separated ladder position still rests on 11 task clusters.
  - 85 and 86 are overclaims in prose, not evidence defects.
- **Presentation: 3** (good; up from 2). The measured targets are mostly met: mean sentence 17.2 words, 1 sentence over 40, no paragraph over 6 sentences, and the teaser figure is in the Introduction. The claim-first topic sentences make the paper skimmable. Two things keep it from 4:
  - The compression slipped in five places (85, 86, 88, 89, and the 82 regression). "Saturates the token caps" states the opposite of the mechanism (87).
  - The main text has no table, so the three-interval ladder-position sentence is printed three times (96).
- **Contribution: 2** (fair). The same as review 21:
  - The identity audit is a clean, cheap check.
  - The ladder-validated measurement is careful.
  - The only non-trivial policy it ranks is the authors' own imitation adapter.
  - The "vision-language" framing has no modality contrast under the choice-frontier contract.
  - The budget half of the thesis is a known principle, which the paper itself cites.
- **Confidence: 4.** I re-derived the numbers and re-ran both figure scripts myself. Published-practice anchors: the ICLR 2026 LLM policy (https://blog.iclr.cc/2025/08/26/policies-on-large-language-model-usage-at-iclr-2026/, fetched 2026-09-25), and Li & Talwalkar (Semantic Scholar 35a59bd09974c7fc78cf681f77f7301e180fd23c; https://arxiv.org/abs/1902.07638).

**Strongest reasons for acceptance:**
- The evaluation discipline is rare for the area:
  - protocols were frozen before outcomes, and amendments are disclosed;
  - every episode was independently replayed;
  - failed predictions are reported where they occur (abstract p.1 L016-017, 5.2 p.5 L253-254, Limitations p.8 L404).
- The identity audit returns both verdicts on one runtime. The instrument does not credit an untrained realisable policy: zero-shot D3 is +0.005 [−0.025, +0.044].
- The paper is now readable by a first-time reviewer: claim-first paragraphs, a thesis teaser in the Introduction, and a short abstract.

**Strongest reasons against acceptance:**
- (i) The instrument has ordered exactly one non-trivial realisable policy, the authors' imitation adapter. The second policy is at chance (5.4 p.6 L316-321).
- (ii) The learned result is small and fragile. It is separated above the ε-0.75 rung only on the 11-task held-out panel, with 8 positive and 3 negative per-task differences. The unscreened gain rests on 4 of 12 tasks.
- (iii) The title's "Vision-Language" has no choice-frontier modality evidence, and the body never names the observation the adapter sees (94).
- (iv) The thesis's second check is the compute-matched-baseline principle. Its only instance here holds by construction (88).

**What would move the rating up one step (4 → 6):**
1. Fix 85 and 86 (zero experiments, space-neutral).
2. Run #143: one trained second policy (a one-seed InternVL3.5 cell on the validation and held-out panels). This would show that M1 plus the ladder orders two trained choosers.
3. Run #144, the most value-changing: a modality contrast under the choice-frontier contract, for example a text-rendered menu against the scene-only observation with the same recipe.

The page of slack now available holds either result without cuts.

**Finding 40 (compliance, outside the rating and the count):** App Y p.37 L1985-1988 (appendix.tex, the Use of LLM Statement) now reads: "Large language model agents drafted and revised the manuscript text and wrote the figure scripts under the authors' direction. An agent pass searched for citations, and a human verified every cited source. Agent reviewers ran repeated review rounds on the drafts. The authors verified every reported number against its pinned artifact and take full responsibility for the content."
- **What it resolves.** ICLR 2026 Policy 1 requires that "Any use of an LLM must be disclosed", and the paper-writing case asks authors to "explicitly state how they used LLMs". The statement now truthfully covers drafting, figure code, citation search, and agent reviewing. It closes the understatement that review 21 recorded ("only for polishing language").
- **What remains.** The policy's research-assistant case ("generating experiment code, and analyzing results") also requires disclosure. The evidence record shows agent involvement beyond the manuscript:
  - #139 and #140 Amendment A1 were made by the "orchestrator, on the author's behalf" (`docs/experiments/choice-frontier/issue-139-protocol.md` L120; `issue-140-closeout.md` L80).
  - #141 ran "via orchestrator" (`schedule-v6.json` L6).
  - The round-5 changelog records that "Main ran the final replay after the executing agent's allowance ran out".
  - The number checks are attributed to Main ("Main spot-checked 20 rows", "Main re-read both JSONs").
- **Assessment.** If Main and the orchestrator are LLM agents, the statement still omits experiment execution, protocol amendments, analysis, and evidence compilation. Its sentence "The authors verified every reported number" is then true only if a human also did so.
- **Fix (one sentence):** "LLM agents also wrote and ran experiment and analysis code, drafted protocols and two pre-evaluation protocol amendments on the authors' behalf, and compiled evidence sheets; the authors approved each protocol before its outcome."
- The risk falls from desk-reject-grade to minor.

### Build, page count, figures

- **Build:** `iclr2026_conference.log` (16:50:51) is newer than every `.tex`; the newest is appendix.tex at 16:49:28. `.bbl` and `.blg` (16:50:50) are newer than every `.bib`; the newest is related_refs.bib at 12:39:03. Counts:
  - `^!` errors: 0
  - LaTeX and package warnings: 0
  - "undefined": 0
  - Overfull: 0 (61 underfull)
  - BibTeX `warning$`: 0
  - 46 unique `\citation` keys = 46 `\bibitem`s
  - "Output written on iclr2026_conference.pdf (38 pages, 457401 bytes)"

  `manuscript/manuscript.pdf` (38 pages, a cairo-processed copy) has the same text as the build after whitespace squeezing. **PASS.**
- **Page count:** the Conclusion ends on **p.8 L423**. The Reproducibility Statement spans p.8 L425 to p.9 L433, and the References start on p.9 L436. The main text is **8 pages** against the 9-page limit. **PASS**, with one page of slack; review 21 had zero.
- **Visible TODO:** 0 in the rendered text. The source TODOs are all in `%` comments. **PASS.**
- **fig:contracts (Figure 1, p.2 L054-073):** I re-ran `fig_contracts.py` from a temp copy with the evidence-repo root. It holds 7 `assert` statements covering 12 value checks:
  - 48/48 from `native-arms/v1/identity-audit.json`;
  - 19/48 from `…-submission-order.json rules.submission_order`;
  - 24 additive tasks from `baseline-contrasts.csv`, and pairs = 2 × tasks;
  - 18/18 and 9 tasks from `choice-frontier/v1/evaluation/identity-audit.json`;
  - six validation-panel M1 values from `v4/panels arms.p135.*.m1`, half-up.

  **All pass.** The regenerated PNG is pixel-identical to the committed one (1650×645, 0.0 pixels differ). The labels are legible and do not overlap. The "exact ref." label sits above the exact-ε 0.25 dot, which is a minor ambiguity. Content: finding 85.
- **fig:ladder (Figure 2, p.6 L270-289):** the script and PNG are unchanged since review 21. I re-ran it: **30/30 checks pass**, and the regenerated PNG is pixel-identical (1791×698).

### Numbers re-check

**Number set (item 1).** A throwaway script tokenised every numeric literal outside `%` comments in all 11 `manuscript/iclr2026/*.tex` files at `7bf48aa` and at HEAD. **Tokens present in HEAD but absent from 7bf48aa anywhere: none. Tokens lost: none.**

Per-file new tokens are all moves:
- 0.306 in introduction.tex: the Figure 1 caption, taken from the appendix three-seed row (`7bf48aa` appendix.tex L1266).
- 18 in introduction.tex, from results.tex.
- 0.144 and 0.300 in appendix.tex: the first-adapter last-label contrast, from results.tex L125.
- 10, 40, and 7 in experimental_design.tex: the screen and panel definitions, from results.tex.
- 48 in discussion.tex: "48/48 identity failure", a prose-name change.

The figure text values were all present at `7bf48aa`. Limitation: distinct-token comparison cannot detect a number restated in a new context. The rendered re-derivation below covers that.

**Artifacts:** md5-identical to review 21: v4/seeds d5c3828cba0f, v4/panels fa5399d9a0f6, v5 29d08e8bcbea, v6 c2073fc9e4f3, LFS d94f54e35f55, v2 c609286a7e3f, submission-order 6f523484d3d0. Evidence HEAD is `53751f0`, clean. All values are half-up to 3 dp.

| rendered claim | PDF location | artifact : key | match |
|---|---|---|---|
| 48/48 identical | p.1 L015, p.2 L045, p.5 L248, Fig. 1 | native-arms/v1/identity-audit.json pairs_identical 48, pairs_checked 48 | yes |
| 19/48 divergent; 29 identical; decisions 2-50, median 6 | p.1 L016, p.2 L045, p.5 L252-256 | submission-order rules.submission_order {pairs_divergent 19, pairs_identical 29}; first_divergence_decision_index over 19 pairs min 2, max 50, median 6; preregistered_prediction.held false | yes |
| +0.082 [+0.051, +0.111] | p.2 L077, p.5 L268 | v2 instrument_validity.pairs[0] {0.0823, [0.0510, 0.1115]}, verdict PASS, tasks 12 | yes |
| 0.875, 0.793, 0.603, 0.347, 0.021; adapter 0.306 | p.5 L266-267, Fig. 1-2 | v4/seeds ladder_position.ladder_m1_135; learned_3seed_mean 0.30556 | yes |
| D3 +0.285 [+0.140, +0.433], every seed positive | p.1 L021, p.2 L082, p.6 L302-303, p.8 L417 | v4/seeds primary {D3 0.28472, ci95 [0.1403, 0.4326], POSITIVE, per_seed 0.328/0.229/0.297} | yes |
| +0.416 [+0.250, +0.591] | p.1 L022, p.2 L084, p.6 L304, p.8 L418 | v4/panels heldout_p2.primary {0.41591, [0.2504, 0.5909]} | yes |
| +0.149 [+0.030, +0.283]; 4 of 12 | p.1 L024, p.2 L087, p.7 L325 | unscreened_p2u.primary {0.14896, [0.0295, 0.2830]}; concentration.per_panel.p2u.counts {positive 4, zero 8} | yes |
| −0.041 [−0.187, +0.102] | p.2 L085, p.6 L309, p.8 L420 | v4/seeds separation.vs_eps_0.75 {−0.04132, [−0.1868, 0.1017], NOT_SEPARATED} | yes |
| +0.227 [+0.053, +0.403]; 8 positive, 3 negative | p.1 L023, p.6 L309-314 | heldout_p2.separation.vs_eps_0.75 {0.22727, [0.0527, 0.4027], SEPARATED_ABOVE}; per_task_difference 8 > 0, 3 < 0 | yes |
| +0.058 [−0.040, +0.156], 35 tasks | p.2 L086, p.6 L311, p.8 L421 | pooled.separation_vs_eps_0.75 {0.05798, [−0.0395, 0.1564]}, primary.tasks 35 | yes |
| +0.002 [−0.145, +0.157]; −0.298 [−0.468, −0.129] | p.6 L310, L313 | unscreened_p2u…vs_eps_0.75.S 0.00208; v4/seeds separation.vs_eps_0.50 {−0.29757, [−0.4684, −0.1288]} | yes |
| +0.130 [+0.070, +0.190] | p.6 L295 | ladder_p2.pairs[0] {0.12955, [0.0705, 0.1898]} | yes |
| 22 of 35 positive, 12 zero, 1 negative | p.7 L330-331 | concentration.all_36_counts {22, 12, 1} | yes |
| LODO +0.305 to +0.395, lower bound ≥ +0.185 | p.7 L332 | leave_one_domain_out_p2_union_p135 min D3 0.30479 (elevators), max 0.39539 (blocksworld), min lo 0.18542 | yes |
| first adapter 0.026 [0.010, 0.042] | p.6 L307 | v2 adapter_reevaluation.learned_adapter {m1_auc, m1_task_cluster_95pct_ci_10000_seed133} | yes |
| zero-shot +0.005 [−0.025, +0.044] EQUIVALENT (development); +0.001 [−0.048, +0.051] INCONCLUSIVE (confirmatory) | p.6 L318-320 | v6 primary.v2 {0.00521, [−0.025, 0.04375], EQUIVALENT, stage "development"}; primary.p2 {0.00114, [−0.0477, 0.0511], INCONCLUSIVE, "held-out confirmatory"} | yes |
| −0.280 [−0.425, −0.142]; −0.415 [−0.589, −0.248] | p.6 L320-321 | v6 co_primary.{v2,p2}.A | yes |
| DAgger +0.115 [−0.026, +0.258] | p.7 L334 | v5 primary {NOT_SEPARATED, S_pool 0.11522, [−0.0255, 0.2576], tasks 23, seeds [17]} | yes |
| 0.915 versus 0; 1000/1000; 200 tasks | p.1 L025, p.2 L090-091, p.7 L343-344 | scienceworld/identity-audit.json success {reference 0.915, random_valid_mean 0.0}; pairs 1000/1000; first_divergence max 0; tasks 200 | yes |
| LFS 1.0 against 0.825; 400 pairs; by the third decision | p.7 L350-354 | LFS paper_budget.success {1.0, 0.825} SATURATED; pairs_checked 400, identical 0, first_divergence max 2 | yes |
| 0.0775 at 1×, 0.19 at 2×; 102,606 against 1,300; 0.768 | p.1 L027, p.7 L352-357 | matched_decision_budget random_valid_success [0.0775 … 0.19]; supplementary.expansions_max {102606, 1300}; published_model_success 0.768425 | yes |
| −0.644 [−0.856, −0.422]; 9/9; 18/18 | p.5 L257, L263-264 | cf v1 analysis contrasts.random_valid_minus_exact_reference {−0.64444, [−0.8556, −0.4222]}; identity-audit 18/18 | yes |
| 125/288 against 240/288; 15/24, 17/24 | p.2 L048, p.5 L251, p.7 L366-367 | synthesis-v1/README.md L176-177 | yes |
| 0.933 against 0.467; lower bound 0.2 | p.7 L364-365 | docs/issue-59-bfws-structural-gate.md L250-253 | yes |
| 68.5244 of 336 | p.5 L237-238 | issue-127-closeout.md L54 | yes |
| M1 0.151 to 0.432 | p.8 L381-382 | v4/panels arms.{p2u,p2}.learned_adapter_seed_mean.m1 0.15104, 0.43182 | yes |

That is 31 rendered numbers across 26 rows, all matching.

### Evidence-comment spot-check

I checked 18 comments. For each, the path exists and the key and value (or the line reference) resolve.

1. results.tex L39-41 (ledgers): v6 Σ attempts[].gpu_hours 2.2452 ✓; `schedule.authorization.window_gpu_hours_cap` 30.0 ✓ (review-21 80(ii) fixed); external total_gpu_hours 2.8910 ✓; schema.gpu_hours_cap 12.0 ✓; schema.independent "never summed with any other ledger" ✓; issue-141-closeout L77 "2.245 / 30" ✓; issue-142-closeout L108 ✓.
2. results.tex L42: issue-127-closeout L54 "Program total 68.5244 / 336 GPU-h" ✓.
3. results.tex L70-73: submission_order.pairs_divergent 19 and pairs_identical 29 ✓; sorted_candidate_order.pairs_identical 48 ✓; preregistered_prediction.held false ✓; verdict "PREDICTION_FAILED: see preregistered_prediction" ✓; first divergence 2 / 50 / median 6 ✓.
4. results.tex L82-83: cf v1 pairs_checked 18, pairs_divergent 18, pre_registered true ✓; contrasts.random_valid_minus_exact_reference ✓.
5. results.tex L88-91: instrument_validity PASS, tasks 12 ✓, pairs[0] 0.0823 [0.0510, 0.1115] ✓; membership.json 12 task_ids, 7 domains ✓.
6. results.tex L96-98: pooled.panels.p2 11 ✓; 8 P2 domains ✓; ladder_p2 PASS, pairs[0] ✓; issue-139-protocol.md L122 seeds 955040-955199 ✓; closeout L58 "P2 = 6 / 5" ✓.
7. results.tex L135-140: all S values, intervals, roles, and verdicts ✓; P2 per-task signs 8 / 3 / 0 ✓.
8. results.tex L144-148: v6 stage labels "development" and "held-out confirmatory" ✓; D3 and A values ✓.
9. results.tex L152-154: P2u primary ✓; closeout L73 (4 positive / 8 zero) ✓; closeout L56 "All 12 happen to have 0/10 random goals." ✓; protocol L48 screen rule "1–9 of its 10" ✓.
10. results.tex L161-164: LODO values ✓, with every other lower bound ≥ 0.204 (grid 0.2040) ✓; v5 keys ✓.
11. results.tex L172-174: ScienceWorld verdict CHOICE_REGISTERED and seeds 17/5077/6131/7409/8527 ✓.
12. results.tex L181-186: LFS supplementary and budget-curve keys ✓; protocol L191-194 (the Qwen3-30B-A3B-Instruct-2507 @ 0d7cf239 substitution) ✓; closeout L11-15 mechanism ✓.
13. results.tex L194: issue-59 L250-255 ✓.
[…85ln elided…]
    - "Success therefore measures validity in (a) and choice in (b)" (Fig. 1 caption, p.2 L072-073)

    The other three: "The gain is spread across tasks and domains and comes from imitating the exact reference." (p.7 L329), "so success budgets must bind decisions" (p.7 L357-358), and "A budget that a zero-token chooser never exhausts turns uniform choice into exhaustive randomized search." (p.8 L393-394).
- **Axis 3:** findings 87, 90, 91, 92, and 95, and the 82 regression.
- **Axis 4:** findings 85, 86, 88, 89, and 94.
- **Axis 5:** findings 93 and 96.
  - The experiment order still runs an elimination tournament. Each block kills a named alternative:
    - 5.2: the idea that success always measures choice;
    - 5.3: the idea that M1 does not order choice quality;
    - 5.4: chance-level and screen artifacts;
    - 5.5: the objection that the result is interface-specific.
  - 5.6 is the enumeration-contract residue. It kills "learned success where choice registers".
- **BENCHMARK checklist:**
  - Two bottlenecks: pass (contract; M1 plus ladder).
  - Near-miss definitions: pass (token-denominated against expansion-denominated budgets).
  - Headline findings stated as claims: pass, but Contribution 4 now claims a known principle (88).
  - Adoption risks: screening pass (with 91 as a caveat); contamination n/a (procedurally generated tasks).

#### 85 · MAJOR · Axis 1 + Axis 4 (the Figure 1 teaser's takeaway generalises an additive-cell, sorted-tie result to the whole enumeration contract) · `iclr2026_conference_introduction.tex; figures/fig_contracts.py`

- **Location:**
  - Figure 1 art p.2 L065, panel (a) boxed takeaway "success measures validity" (fig_contracts.py L122), printed directly under "submission-order serials: 19/48 divergent" (p.2 L063).
  - Caption p.2 L072-073 (introduction.tex L22): "Success therefore measures validity in (a) and choice in (b)".
  - Caption L070: "18/18 pairs on the first panel diverge".
- **Issue:**
  - (i) **The takeaway overgeneralises.** It labels the whole enumeration contract. The paper's own evidence restricts "success measures validity" to the additive best-first cells under sorted tie-breaking:
    - 5.2 p.5 L249-251: "This is a property of this controller, not of additive best-first search in general … The BFS and BFWS cells instead register choice, with random-valid at 15/24 and 17/24."
    - The figure's own second line (19/48 divergent under submission-order ties) is a counterexample inside the same box.
  - (ii) **The takeaway is new in round 7.** The `7bf48aa` caption had no takeaway and said "on a separate 9-task panel".
  - (iii) **Why it matters.** Figure 1 is the 10-minute-test asset. A skimming AC now leaves believing "enumeration contract ⇒ validity", which the paper contradicts on p.5.
  - (iv) **The caption is not standalone.** "First panel" is undefined in it. The mini-ladder plots point estimates only: the adapter's 0.306 is drawn left of the ε-0.75 rung's 0.347, so it visually reads "below the rung", while the pre-registered verdict is NOT_SEPARATED (−0.041 [−0.187, +0.102]).
- **Fix:**
  - Figure: change the panel (a) takeaway to "additive cells, sorted ties: success measures validity" (fig_contracts.py L122). No number changes, and the asserts are unaffected.
  - Caption: "Success therefore measures validity in the additive cells of (a) under sorted tie-breaking (its BFS and BFWS cells and submission-order ties register choice, Section 5.2) and choice in (b)."
  - Replace "the first panel" with "the reused 9-task panel". Add "(point estimates; intervals in Figure 2)".
  - About +25 words, covered by the page of slack.
- **Why it changes the verdict:** the teaser is the one place every reviewer reads. Its headline must not claim more than Section 5.2 does.
- **Fix class:** WORDING (restores the body's scope)

#### 86 · MAJOR · Axis 4 + Axis 3 (topic sentences say the published interfaces show that both checks are needed; both interfaces passed the identity audit immediately) · `iclr2026_conference_introduction.tex; iclr2026_conference_discussion.tex`

- **Location:**
  - Intro p.2 L089 (introduction.tex L68): "Both checks matter on published interfaces."
  - Discussion p.8 L385 (discussion.tex L24): "The external audit shows that both checks are needed."
- **Issue:**
  - (i) **The identity audit passed at once on both external interfaces.**
    - ScienceWorld diverges at the first decision in 1000/1000 pairs (`first_divergence_index.max` 0).
    - On LFS, 0/400 pairs are identical, all diverging by the third decision (max 2).
    - So neither published interface shows the identity audit to matter. The only external case where a check decides anything is the budget check on LFS, and there the outcome holds by construction.
  - (ii) **Each paragraph contradicts its own topic sentence two sentences later:** "so the 48/48 failure is shown only on our runtime" (p.2 L092-093; p.8 L386-387).
  - (iii) **The claim is new in round 7.** At `7bf48aa` the Discussion read "ScienceWorld anchors the check on a published interface where it registers choice", and the Intro had no topic claim.
  - (iv) **It breaks the CONTEXT boundary.** `CONTEXT.md`'s External audit claim says the identity failure is "shown only on this project's runtime" and "may not generalise". Under style principle 5, topic sentences are what skimmers read, so this sentence is the external-value claim a reader takes away.
- **Fix:**
  - Intro L068: "The external audits test each check on a published interface."
  - Discussion L24: "The external audits exercise each check on a published interface. The identity audit passes on both, and on LLM-First Search the budget check fails by construction."
  - Both are space-neutral.
- **Why it changes the verdict:** this is the paper's external-evidence claim for its first contribution. As written, it credits published interfaces with evidence they do not supply.
- **Fix class:** WORDING (restores the approved external-audit claim)

#### 87 · MINOR · Axis 3 ("saturates the token caps/budget" states the mechanism backwards) · `abstract; introduction; results; discussion`

- **Location:**
  - Abstract p.1 L026 (abstract.tex L30): "a zero-token chooser saturates token caps by construction".
  - Intro p.2 L093-094 (L74): "saturates the token caps".
  - 5.5 p.7 L349-350 (results.tex L180): "random-valid success saturates the paper's token budget by construction".
  - Discussion p.8 L387-388: "random-valid success saturates the token budget".
  - Conclusion p.8 L415-416: "saturates LLM-First Search's token budget".
- **Issue:**
  - A chooser that saturates a budget uses it up. Random-valid spends no tokens (`supplementary.tokens_median.random_valid` 0.0 against the reference's 70,403.5), and 5.5's next sentence says so: "A token cap never binds a chooser that spends no tokens".
  - What saturates is success (1.0) under the caps.
  - The abstract had this wording at `7bf48aa`. Round 7 spread it to the 5.5 topic sentence and the Discussion.
- **Fix:**
  - Abstract: "a zero-token chooser solves every task under the token caps by construction but only 0.0775 at the reference's expansion count".
  - Elsewhere: "random-valid success saturates (1.0) under the paper's token caps, which a zero-token chooser never reaches".
- **Fix class:** WORDING

#### 88 · MINOR · Axis 4 + Axis 1 (Contribution 4 claims the compute-matched-baseline principle as "the budget check"; the thesis asserts it with "therefore") · `iclr2026_conference_introduction.tex; iclr2026_conference_discussion.tex`

- **Location:**
  - Contribution 4, p.2 L102-103 (introduction.tex L84): "The budget check, with an audit of two published interfaces…".
  - Thesis p.1 L050-051 (L46): "Random-valid success therefore measures choice only if the identity audit finds divergent decisions and the budget check … finds that it does."
  - Portable rule p.8 L393-394: "A budget that a zero-token chooser never exhausts turns uniform choice into exhaustive randomized search."
- **Issue:**
  - (i) **It claims a known principle.** The paper itself calls this check "the compute-matched-baseline principle (Li & Talwalkar, 2020)" (p.8 L392-393) and "the standard architecture-search baseline" (p.3 L137-138). `CONTEXT.md` allows it only as "a by-construction demonstration of why a success budget must bind decisions". Listing the check as a contribution claims the principle. The `7bf48aa` bullet claimed the audit ("An external audit of two published interfaces…").
  - (ii) **"Therefore" has nothing to follow from.** It follows a paragraph that establishes only the identity result; the budget condition enters with no premise.
  - (iii) **The portable rule drops its condition.** 5.5 states the condition ("because the frontier keeps every alternative"). Without it, the rule is false for a bounded or beam frontier.
- **Fix:**
  - Contribution bullet: "An audit of two published interfaces that applies the compute-matched-baseline principle as a budget check: random-valid registers choice on one and saturates by construction on the other."
  - Thesis: "We argue that random-valid success measures choice only if …".
  - Portable rule: "…never exhausts, on a frontier that keeps every alternative, turns …".
- **Fix class:** MEANING (it changes what is claimed as a contribution)

#### 89 · MINOR · Axis 4 + Axis 3 (abstract compression dropped caveats that CONTEXT requires in the abstract) · `iclr2026_conference_abstract.tex`

- **Location:**
  - p.1 L022-023 (abstract.tex L24): "It is separated above the 0.75 rung only on the held-out panel (+0.227 [+0.053, +0.403]), not pooled."
  - L028-029 (L32): "The choice-quality claim is development-stage (development panels only)…".
  - L026-027 (L30).
- **Issue:**
  - (a) **Ladder position.** `CONTEXT.md` says it "is always reported for all three results together …, never for P2 alone". The pre-registered co-primary validation-panel result (NOT_SEPARATED, −0.041 [−0.187, +0.102]) is no longer named.
    - "Pooled" appears before the unscreened panel is introduced (L023-024).
    - Neither ε nor "the 0.75 rung" is defined in the abstract.
    - `7bf48aa` read "…on the held-out panel (+0.227 …) but not on the validation panel, the unscreened panel, or pooled."
  - (b) **Missing caveats.** `CONTEXT.md` L99 requires the held-out definition and "45-task final evaluation unexecuted" to be stated in full once in the abstract. Neither appears.
  - (c) **The gloss collides with the held-out panel's label.** "Development panels only" glosses the term with itself, and it collides with the held-out panel's "confirmatory" label (5.4 p.6 L319; the Table 22 header "P2 (11, confirmatory)"; artifact `heldout_p2.status` "confirmatory"). A reader cannot tell whether the held-out panel is a development panel.
  - (d) **Substitution caveat.** The "substituted reference" note that `7bf48aa` carried for LFS is gone. The body keeps it, so this is noted, not required.
- **Fix:**
  - Move the ladder sentence after the unscreened sentence: "It is separated above the ε-0.75 rung only on the held-out panel (+0.227 […]), not on the validation panel, the unscreened panel, or pooled."
  - Define ε in the ladder clause: "selectors that randomize a fraction ε of reference decisions".
  - Close with: "All claims are development-stage: the held-out panel is a fresh 11-task panel, and the frozen 45-task final evaluation is unexecuted. We make no planning-ability or generality claim."
  - Pay for about 25 words by writing "Under our choice-frontier contract, M1 passes…" for L017-018.
- **Fix class:** WORDING

#### 90 · MINOR · Axis 3 + Axis 5 (the Introduction's held-out definition has a dangling referent) · `iclr2026_conference_introduction.tex`

- **Location:** p.2 L105-107 (L88-89): "…not on the frozen 45-task final evaluation, which is unexecuted. Held-out means only that panel, drawn from seeds no adapter had been evaluated on (Section 4)."
- **Issue:** the nearest singular antecedent of "that panel" is the frozen 45-task final evaluation. The sentence can therefore be read as defining held-out as exactly what `CONTEXT.md` forbids. At `7bf48aa` it read "Held-out here means the fresh panel P2, frozen before any evaluation episode…".
- **Fix:** "Held-out means only the fresh 11-task held-out panel, drawn from seeds…".
- **Fix class:** WORDING

#### 91 · MINOR · Axis 3 (Design topic sentence: "frozen before any evaluation and screened against trivial tasks") · `iclr2026_conference_experimental_design.tex`

- **Location:** p.4 L191 (L35): "The choice-frontier panels are frozen before any evaluation and screened against trivial tasks."
- **Issue:**
  - (i) The unscreened panel "skips the screen" (L203).
  - (ii) The first 9-task panel was reused, "so each design step could adapt to earlier results" (L192-194). It was not frozen before any evaluation.
  - (iii) The screen rejects both 10/10 and 0/10 tasks ("admit iff … random-valid reaches the goal in 1–9 of its 10", issue-139-protocol.md L48). "Against trivial tasks" names only half of that. It reads as the enrichment interpretation that finding 70 removed (the screen admits "tasks easy enough for weak choosers").
  - (iv) The sentence is new in round 7; `7bf48aa` had "Panels are frozen and outcome-blind".
- **Fix:** "The validation and held-out panels are frozen before any evaluation and admit only tasks on which random-valid reaches the goal in 1 to 9 of 10 screening episodes; the unscreened panel skips that screen." Then delete the duplicate at L197-198.
- **Fix class:** WORDING

#### 92 · MINOR · Axis 3 (the Limitations say the trained second backbone was not run; Design says it ran at reduced scope) · `iclr2026_conference_discussion.tex`

- **Location:**
  - Limitations p.8 L409-410 (discussion.tex L42): "the trained second backbone was not run."
  - Against it: Design p.4 L215 "with InternVL3.5-8B (Wang et al., 2025) second", and p.5 L225 "Generalization and second backbone ran at reduced scope only"; 5.1 p.5 L239-240.
- **Issue:** the limitation holds only under the choice-frontier contract (the #141 InternVL arm was ruled out). It predates round 7 but has not been flagged before.
- **Fix:** "…and the trained second backbone was not run under the choice-frontier contract (it ran at reduced scope under the enumeration contract)."
- **Fix class:** WORDING

#### 93 · MINOR · Axis 5 (stale cross-reference after the round-7 move) · `iclr2026_conference_appendix.tex`

- **Location:** App X p.37 L1981 (appendix.tex L1604): "Table 25 compares the enumeration and choice-frontier contracts defined in Section 4."
- **Issue:** round 7 moved the contract definitions to Section 3 (p.4 L167-171; search_process_policy.tex STATUS "decision-contracts paragraph moved from Section 4").
- **Fix:** replace `\ref{sec:design}` with `\ref{sec:policy}`.
- **Fix class:** WORDING

#### 94 · MINOR · Axis 4 + Axis 5 (the body never says what the choice-frontier adapter observes, under a "Vision-Language" title) · `iclr2026_conference_search_process_policy.tex; iclr2026_conference_discussion.tex`

- **Location:**
  - `grep scene` over the main text returns 0 hits.
  - Section 3 p.3 L152-155: o_t is "a text, visual, or multimodal rendering", and "Search Memory … and the candidates stay textual."
  - The actual observation is in App I p.21 L1085-1092 ("the unlabelled 128px initial-state scene, one unlabelled 128px scene per frontier state … Its text payload carries only the algorithm name, the label list…") and App U.3 p.34 L1834 ("the frozen scene-only choice-frontier observation").
- **Issue:**
  - (i) "The candidates stay textual" is false for the contract behind every positive learned result.
  - (ii) The title's modality claim rests on an observation the body never names.
  - (iii) The Limitations do not mention that no modality comparison exists under the choice-frontier contract (review 21 reason (iv); #144 filed).
- **Fix:**
  - Add to Section 3's contract paragraph: "Under the choice-frontier contract the observation is scene-only: rendered scenes of the initial and each frontier state plus goal pages, with opaque labels as the only candidate text (Choice-Frontier Contract appendix)." Scope "candidates stay textual" to the enumeration contract.
  - Add a Limitations bullet: "Modality. The choice-frontier results use one scene-only observation, so no modality is compared under that contract."
- **Fix class:** WORDING (adds a limitation; no claim changes)

#### 95 · MINOR · Axis 3 (the new "privileged" gloss contradicts decision sufficiency) · `iclr2026_conference_introduction.tex; iclr2026_conference_results.tex`

- **Location:**
  - Intro p.2 L078 (L53) and 5.3 p.6 L296-297 (results.tex L95): "The rungs read the reference's own priority order, which no policy sees".
  - Against it: Section 3 p.3 L154 "The observation must expose every fact the exact reference uses at step t."
- **Issue:** the priority order is a deterministic function of states that a sufficiency-respecting observation exposes. What no policy receives is the computed score or order (App R p.29 L1546: selectors "read privileged scalars or PDDL atoms while the model sees only scenes"). This is a round-7 gloss; the old text said "read the privileged heap head".
- **Fix:** "…read the reference's computed priority order, which is never shown to a policy…".
- **Fix class:** WORDING

#### 96 · MINOR · Axis 5 (residual presentation targets and no main-text table) · `section files`

- **Location and evidence:** see the Presentation axis tables above.
  - The 46-word sentence at p.3 L160-p.4 L162.
  - An abstract of about 205 words with 13 point numbers.
  - 6 body sentences with 3 or more numbers.
  - The three-interval ladder-position sentence printed three times, while the main text has **zero tables** and one free page.
  - No enumerated multi-result paragraphs.
  - "Uniform choice" as an 11-use synonym for random-valid.
  - Four names for the reused 9-task panel.
  - Undefined LVLM, RAP, MVoT, UCT, VQA, CALM, and FIFO.
- **Fix:**
  - Split the Section 3 invariant sentence into one sentence per algorithm family.
  - Add one 3 × 3 main-text table in 5.4 (validation / held-out / unscreened × D3, adapter minus ε-0.75 rung, smallest ladder gap, each with its interval and verdict). Replace the 5.4 ladder-position sentence with a pointer to it, and keep the Intro and Conclusion versions for the three-part rule. This uses about a third of the free page.
  - Move "22 of 35 … 12" and "0.151 to 0.432 … 0.875" into that table.
  - Use "random-valid" throughout. Name the 9-task panel "the reused 9-task panel" everywhere. Expand the acronyms at first use.
- **Fix class:** WORDING

### What would change the verdict

Round 7 did what it set out to do. The numbers are untouched, the build is clean, the page limit now has slack, and the body reads at a mean of 17 words per sentence with a teaser figure that finally carries the thesis. The price of the compression is five meaning slips, two of them MAJOR:
- The teaser's takeaway says the whole enumeration contract measures validity (85).
- The Introduction and Discussion topic sentences credit the published interfaces with showing that both checks are needed (86).

Both are one-line fixes. The rest (87-96, the 82 regression, and the 80 remainder) are space-neutral wording.

The rating stays at 4 for the reasons review 21 gave, which round 7 was not meant to address:
- The instrument has ordered one non-trivial realisable policy.
- The title's modality claim has no choice-frontier contrast behind it.
- The budget half of the thesis is the compute-matched-baseline principle, demonstrated by construction.

What would move it to BORDERLINE (rating 6):
- **85 and 86, zero experiments:** restore the scopes as prescribed.
- **#143:** one trained second policy (a one-seed InternVL3.5 cell on the validation and held-out panels, about 7-9 GPU-h per cell by the #141 estimate). This would show that M1 plus the ladder orders two trained choosers.
- **#144, the most value-changing:** a modality contrast under the choice-frontier contract (text-rendered menu against the scene-only observation, same recipe). It is the only experiment that can make the title's "Vision-Language" a finding rather than a setting. The page of slack now holds it.


[Showing lines 1-191 and 277-483 of 483; 85 middle lines (13.9KB) elided. Read artifact://118 for full output]

## Cold read B — round-7 skim test (2026-09-25)

Cold-read skim test of pages 1-8 of manuscript/manuscript.pdf (pdftotext) plus fig_contracts.png. The pdftotext dump printed the full body text; only the parts the brief allowed were used, and anything else noticed is marked incidental. No rating.

## 1. Takeaway after the first skim
"A random-valid control can make exactly the reference algorithm's decisions: 48/48 on some cells. When it does, success measures validity, not choice. In a different setup (the 'choice-frontier contract') a metric checked against a ladder, M1, shows a trained adapter beating random."

The rule the paper actually argues for did not reach me on the first pass. That rule is that two checks, an identity audit and a budget check, must both pass. The abstract states it as "...and the budget binds them" (p.1 l.17), and I did not parse that. The LLM-First Search sentence (l.26-27) read as a separate fact.

## 2. Do the five places agree?
Only partly. Each one leads with something different:
- Title: "Separating choice from validity" plus "a validated ... measurement for vision-language search policies".
- Abstract: the 48/48 failure (sentence 2). The two-condition rule comes at sentence 4, and the budget half is only implied.
- Figure 1: validity in (a) against choice in (b), with the M1 ladder. The budget check does not appear.
- Contributions: four equal bullets (audit, measurement, adapter, budget check). None is marked primary.
- Conclusion: sentence 1 is the two-check rule. More than half the paragraph is adapter numbers (5 bracketed intervals).

Where they disagree:
- "Vision-language" appears only in the title. The abstract, Figure 1, the contributions and the Conclusion never mention modality, vision or language.
- Flaw or measurement? The Discussion says "The contribution is therefore the measurement and its two checks, not the exposure of one flaw" (p.8 l.388-389). But the abstract and Figure 1 lead with the flaw (48/48).
- The budget check is a contribution bullet and half of the Conclusion's rule. It is absent from Figure 1 and only implied in the abstract.
- ScienceWorld (random-valid measuring choice on a published interface) is in the abstract but not the Conclusion.

## 3. Where the first-sentence skim lost me
- §1 ¶2 l.042 "On part of our own runtime, random-valid makes exactly the decisions of the exact reference...": "part of" is vague; the answer (additive cells) comes a sentence later.
- §1 ¶3 l.050 "Random-valid success therefore measures choice only if the identity audit finds divergent decisions and the budget check ... finds that it does.": depends on the previous paragraph ("therefore"). It also jumps topic: nothing before it motivates budgets. "Binds decisions" is never defined.
- §1 ¶5 l.080 "Scored this way, a trained adapter beats uniform choice on all three panels, but its ladder position depends on the panel.": depends on the previous paragraph. "Adapter", "three panels" and "ladder position" are undefined here.
- §1 l.095 "This paper makes four contributions.": makes no claim.
- §3 ¶2 l.156 "Four definitions fix what the policy owns and what the runtime owns.": makes no claim. Four definitions are packed into one paragraph as run-in headings.
- §4 ¶1 l.180 "Every learned result is read against two oracle-assisted controls...": "oracle-assisted" is unexplained. A skimmer can't see why a uniform-random control counts as oracle-assisted.
- §4 ¶3 l.191 "The choice-frontier panels are frozen before any evaluation and screened against trivial tasks.": the same paragraph says the first panel was reused "so each design step could adapt to earlier results". "Trivial" doesn't fit the screen actually used: a task is admitted only if random-valid reaches the goal in 1-9 of 10 runs.
- §4 ¶7 l.216 "The modality matrix evaluates 24 tasks from 12 domains.": jumps topic, and "modality matrix" is undefined. This is the first time modality shows up in the skim path.
- §5 intro l.231 "Results follow the thesis, with the two checks first, then the validated measurement, then the policies it scores.": makes no claim, and "the thesis" is never stated. The roadmap is also wrong: §5.1 (gate receipts) comes before the checks.
- §5.1 l.237 "Every executed run reconciles with its ledger and independent replay, and the program spent 68.5244 of its 336 GPU-hour cap.": unrelated to the takeaway. "Ledger" is undefined, and the number has four decimals.
- §5.3 ¶2 l.291 "The same test passes on the held-out panel and, descriptively, on the unscreened panel.": depends on the previous paragraph ("same test" is the ladder test). "Descriptively" is a convention that is never explained.
- §5.4 ¶3 l.316 "A zero-shot policy scores as uniform choice, so the measurement separates the two realisable policies.": reads as self-contradictory (it scores the same as uniform, yet the measurement separates something). "Realisable" is undefined, and so is which two policies are meant.
- §5.4 ¶5 l.329 "The gain is spread across tasks and domains...": sits right after "the gain ... rests on 4 of 12 tasks" (l.323). At skim level the two first sentences contradict each other.
- §5.6 l.362 "...the only positive learned contrast comes from one development panel, and the expanded matrix shows no gain where choice registers.": two claims in one sentence. "Expanded matrix" is undefined (elsewhere it is "expanded baseline"). "Registers choice" is jargon.
- §6 ¶1 vs ¶4 (l.376 / l.391): "Random-valid success separates choice from validity only after the identity audit has run..." against "Before random-valid success is read as choice, an interface must pass two checks.": ¶1 names one check and ¶4 names two. They are near-duplicate openers that don't match.
- Limitations "Runtime" bullet l.405 "The runtime never chooses or repairs operands, so no result shows unassisted internal search.": "unassisted internal search" is undefined.
- Figure 1 caption: "18/18 pairs on the first panel diverge". "First panel" is undefined in the caption.
- Figure 1 image: the "exact ref. 0.875" label sits over the 0.793 dot, so the two rightmost points are easy to swap.
- Incidental, outside the skim scope: §4 l.225 says "Generalization and second backbone ran at reduced scope only". The Limitations bullet at l.409-410 says "the trained second backbone was not run". These read as inconsistent.

## 4. Terms met without a definition
- Title: "search-choice measurement"; "vision-language search policies" (no model or modality in the skim path until §4).
- Abstract: "additive best-first cells" (neither "cells" nor "additive" is defined); "enumeration contract"; "exact reference"; "pairs" (pairs of what?); "submission-order tie-breaking"; "pre-registered majority prediction" (majority of what?); "the budget binds them"; "exact-ϵ ladder" (ϵ is never glossed); "privileged rungs"; "0.75 rung"; "pooled"; "adapter" (adapter of what?); D3 (symbol used with no definition; the 3 is unexplained); "unscreened panel"; "(descriptive)"; "ScienceWorld (0.915 versus 0)" (which quantity?); "zero-token chooser"; "token caps"; "choice-quality claim"; "development-stage".
- Figure 1: "Grounded candidate menu"; "Sorted-serial frontier (order-invariant)"; "one op"; "additive pairs"; "submission-order serials"; "(24 tasks)" next to 48 pairs (why 2 per task?); "exact-ε 0.25"; "rungs read privileged information".
- §1: "Search Process Policy", "Typed Search Operations" and "Trusted Search Runtime" are named at l.036-037 but only defined in §3; "operational reasoning" vs "structural enumeration" (l.035-036); "baseline entries" (l.048); "cells"; "panels"; "ladder position"; "screening"; "published interfaces"; "gold trajectory". "Adapter" collides with "observation adapter m" in §3 (l.152).
- §2: UCT, RAP, MVoT, LVLM, VQA; "menu manipulations"; "fixed-versus-random-position variant".
- §3: FIFO; "g+3h_add ... weighted A*". Weighted A* is not among the declared algorithms listed in §1.
- §4: "oracle-assisted"; P2 (with no P1); P2u; "corruption suite, native arms, menu manipulation, comparator zoo"; "modality matrix"; "BFWS gate checkpoint"; "exposure-matched".
- §5: "ledger"; "v1 cost gates"; VALID STOP; "BFS pilot"; "BFWS structural gate"; "realisable policies"; "registers choice"; "expanded matrix/baseline"; "problem-modality units"; "first adapter".
- §6: "compute-matched-baseline principle"; "unassisted internal search".

## 5. Three changes that would most improve the skim (no number or claim changes)
1. Pick one headline and use it in all five places. Use the Discussion's own framing: random-valid success measures choice only when the identity audit and the budget check both pass. Put that rule in abstract sentences 1-2, ahead of the 48/48 detail. Retitle to name the rule. Also resolve "vision-language": either drop it from the title or surface the modality setup in the abstract. Add a small third strip to Figure 1 for the budget check: the LLM-First Search saturation under tokens against 0.0775 under expansions. That makes Figure 1, the contributions and the Conclusion carry the same two checks. Mark one contribution as primary.
2. Define terms where they are first used, and make every paragraph open with a claim. Add a one-clause gloss at first use for: exact reference, pair, cell, panel, rung/ladder, D3, "registers choice", "binds decisions" and "descriptive". Rename one of the two "adapter" senses. Rewrite the openers that depend on the previous paragraph or make no claim: §1 ¶3 and ¶5, "This paper makes four contributions", §3 ¶2, the §5 intro, §5.3 ¶2 and §5.4 ¶3. Each should state its claim with no "therefore", "same" or "this way" back-reference. Fix §5.4 ¶5 so "spread across tasks" doesn't directly contradict "rests on 4 of 12 tasks".
3. Cut number density and non-thesis material from the skim path. Move §5.1 (gate receipts) to the end of §5 or to the appendix, so §5 opens with the checks as its roadmap promises. Keep the abstract and Conclusion to the headline numbers: the Conclusion currently has one sentence with three bracketed intervals, and the abstract has about 20 numbers. Leave the full ladder-position detail to §5.4. Fix the "exact ref." label placement in Figure 1(b).

## Live fixlist — review 21 (2026-09-25)

**Verdict:** WEAK REJECT. 0 CRITICAL, 1 MAJOR, 5 MINOR.
- MAJOR: finding 81.
- MINOR: new findings 82-84, and the partial remainders of review-20 findings 75 and 80.
- Fix class: MEANING for 81. WORDING for 82-84 and for both remainders.
- Finding 40 (LLM-usage statement) is WONTFIX by author decision. It is reported below as a compliance risk and is outside the rating and the finding count.

Most damaging issue: **finding 81** (Axis 2 with Axis 1). The new external result and the second check of the portable rule both rest on the LLM-First Search (LFS) SATURATED verdict, and that verdict could not have lost.
- The paper's own V.1 says the frontier keeps every alternative, and random-valid spends zero tokens under a token-only cap. It is therefore a complete randomized search on finite, solvable puzzles.
- The #142 protocol states this before the audit ("random_valid is a complete randomized search. The probe won 100/100 non-audited episodes within the guard").
- The paper nonetheless presents it as "Both pre-registered predictions held" (V.1) and as "a failure the per-decision audit does not detect" (Discussion). The Introduction generalises it to "success saturates unless the budget binds decisions".
- The matched-budget reading compares random-valid against a reference whose success at its own expansion count equals its token-budget success by construction.

Genre: BENCHMARK (+ FINDINGS)

Δbelief: On the authors' additive best-first runtime, the per-decision identity check returns both verdicts (48/48 identical under sorted serials, 19/48 divergent under submission-order serials). A choice-frontier contract passes a pre-registered exact-ε ladder on a validation panel and a screened held-out panel. An imitation-trained VLM adapter beats uniform frontier choice (D3 +0.285, held-out +0.416, unscreened +0.149) but is interval-separated above the ε-0.75 rung only on the 11-task held-out panel. A zero-shot base model scores as uniform choice. On LFS, a zero-token uniform chooser solves every task under the paper's token caps. The update a skimming reviewer takes away is "before reading random-valid success as choice, check that decisions diverge and that the budget binds decisions". The second half is the established compute-matched-baseline principle, and here it is shown on a case whose outcome was guaranteed.

Ledger: Verified: 69, 70, 71, 72, 73, 74, 76, 77 (wording; p-value part declined by author), 78, 79; round-4 closures 49, 60, #137 reframe, review-16 finding 15, 51, 52 · Partial: 75, 80 · Regressed: none · Not addressed: none · Wontfix: 40 (unchanged, App Y p.37 L1985) · New: 81-84

**Reviewer summary:**

> This round-6 re-review covers HEAD `ba7d4d2` on a clean tree: the review-20 consolidation `e7346aa` and round 6 (`e2eb87c`, `865545a`, `bded653`), which integrates #141 (zero-shot second policy) and #142 (LLM-First Search audit). I read all 37 pages of the rendered PDF text, the word-level diffs of every section file since `0277de7`, both figure PNGs, `fig_ladder.py`, the log, blg, and bbl, the new `CONTEXT.md` "External audit claim" entry, the round-6 changelog entries, and the #141/#142 protocols, feasibility note, and closeouts.
>
> The build is clean. The Conclusion ends on **p.9 L477**, so the main text is exactly 9 pages against the 9-page limit, with no slack left.
>
> Every number checked in the rendered PDF matches its pinned artifact. The artifacts behind review 20 are md5-identical, so its re-derivations stand. I re-derived every new number from `v6/metrics/analysis.json`, `external-audit/v2/lfs/identity-audit.json`, both new ledgers, and `protocol.json`, including every cell of Tables 22 and 24 and the Figure 2 zero-shot row. Re-running the 30 `fig_ladder.py` value checks read-only against the JSONs, with the script's half-up `Decimal` rule, gives 30/30 pass. The rounding in one Table 24 cell is noted below; it is not a mismatch.
>
> I checked 14 evidence comments, 10 of them from round 6. Twelve resolve fully. One names a non-existent key path, and two lean on a non-repository "local evidence sheet §9" (80 remainder).
>
> Every review-20 fix landed. 75 is missing one chance rate, and 80 has new instances of the same pattern.
>
> The paper's remaining problem is what the two new experiments can bear:
> - The LFS saturation is a construction, not a test (81).
> - The zero-shot policy's equivalence verdict is the development-stage one, while the confirmatory held-out verdict is INCONCLUSIVE. Its prompt carries an undisclosed goal-similarity instruction (82).
> - Table 22 pairs "EQUIVALENT" with large sign-flip p values (83).
> - The abstract has grown to 327 words carrying 31 decimal numbers (84).

### Rating

**Rating: 4** (ICLR 2026 scale {0, 2, 4, 6, 8, 10}; 4 = marginally below the acceptance threshold)

- **Soundness: 3** (good). Every endpoint is pre-registered with a frozen verdict rule, every episode is independently replayed, the paper uses paired task-clustered intervals and three training seeds, and it reports its own failures (the #134 prediction, DAgger, P2u, and the InternVL arm not run). Two things cap soundness. The LFS SATURATED verdict could not have lost, and its matched-budget contrast is reference-conditioned (81). The one interval-separated ladder position rests on 11 task clusters.
- **Presentation: 2** (fair). The paper is honest and exact, but a first-time reader struggles:
  - The abstract has 327 words and 31 decimal numbers, and two of its sentences need re-reading (84).
  - The main text fills exactly 9 pages with contract, panel, and ledger jargon.
  - The appendix runs to 26 lettered sections, 25 tables, and 37 pages.
- **Contribution: 2** (fair). The per-decision identity audit is a clean, cheap check, and the ladder-validated choice measurement is careful. Both new experiments land where they had to:
  - The zero-shot policy scores as uniform choice, so it re-confirms that the instrument separates the trained adapter from chance, which D3 already showed.
  - The LFS saturation follows from completeness plus a zero-cost chooser.

  The failure the audit exposes is still shown only on the authors' runtime, the learned result is modest, and there is one backbone.
- **Confidence: 4.** I verified all numbers against the artifacts myself. The published-practice anchors were checked against the ICLR 2026 LLM policy, the LFS abstract, and Semantic Scholar records (URLs below).

**Strongest reasons for acceptance:**
- The evaluation discipline is rare for the area. Protocols were frozen before outcomes, amendments were disclosed as made before evaluation, all episodes were independently replayed, and failed predictions are reported (#134 PREDICTION_FAILED, #140 NOT_SEPARATED and INCONCLUSIVE, InternVL not run).
- The per-decision identity check returns both verdicts on one runtime, and there are now two published-interface audits: ScienceWorld registers choice (0.915 against 0), and LFS saturates under token caps (1.0 against 0.825).
- The choice-frontier instrument is validated by a pre-registered monotone ladder that replicates on a held-out panel (smallest gap +0.130 [+0.070, +0.190]). It does not credit an untrained realisable policy: the zero-shot D3 is +0.005 [−0.025, +0.044].
- The portable rule (Discussion p.9 L442-448) is now stated, and it is falsifiable.

**Strongest reasons against acceptance:**
- (i) The new external-audit contribution is a construction, not an empirical finding (81).
  - LFS's own evaluation never runs a random-valid control, so no published result changes. The CONTEXT entry itself forbids claiming otherwise.
  - The rule the audit supports ("the success budget must bind decisions") is the standard compute-matched-baseline principle; random search under a matched evaluation budget is the classic NAS baseline, Li & Talwalkar, UAI 2019 (https://arxiv.org/abs/1902.07638; Semantic Scholar 35a59bd09974c7fc78cf681f77f7301e180fd23c; fetched 2026-09-25).
- (ii) The instrument has still ranked exactly one non-trivial realisable policy, the authors' imitation adapter. The second policy is at chance.
- (iii) The learned result is small and fragile:
  - It is separated above the ε-0.75 rung only on the 11-task P2, with 8 positive and 3 negative per-task differences.
  - It is not separated from that rung on the validation panel, the unscreened panel, or pooled.
  - The unscreened gain rests on 4 of 12 tasks.
- (iv) The "vision-language" framing rests on one visual-only choice-frontier adapter and one backbone. There is no modality comparison under the choice-frontier contract, and every enumeration-contract learned result is null or below random-valid.

**What would move the rating up one step (4 → 6):**
1. **(81)** Rewrite the LFS result as what it is:
   - State in 5.5 and V.1 that saturation follows by construction from a complete frontier and a zero-cost chooser. Disclose the 500,000-expansion guard, random-valid's median 201 and maximum 102,606 expansions against the reference's median 29.5 and maximum 1,300, and the pre-audit probe's 100/100.
   - Report the stored random-valid decision-budget curve (0.0775 at 1×, 0.19 at 2×, normalised AUC 0.135) instead of the single reference-conditioned point.
   - Drop the "failure the audit does not detect" framing, and cite the compute-matched-baseline precedent.

   This costs no new experiment, and the space is covered by the 84 cuts.
2. Put one non-trivial second policy through the instrument. The InternVL arm was ruled out against a self-imposed 30 GPU-h ticket cap, while the main program spent 68.5 of its 336 GPU-h. A one-seed InternVL cell (about 7-9 GPU-h per cell by the protocol's own estimate; two algorithms, descriptive) would test whether M1 plus the ladder orders two trained policies. That is what "a validated search-choice measurement" promises.
3. Optionally, and the most value-changing: one modality contrast under the choice-frontier contract, for example the same adapter recipe with a text-rendered frontier menu against the scene-only observation, on the validation panel and P2. The title's "vision-language" claim currently has no choice-frontier evidence behind it.

**Finding 40 (compliance risk, outside the rating and the count):** App Y p.37 L1985 (appendix.tex L1558) reads "An LLM was used only for polishing language; the scientific content is entirely original."
- ICLR 2026 policy says "Any use of an LLM must be disclosed" and asks authors to "explicitly state how they used LLMs in their submission". It names drafting sections and research-assistant use (analysis, code) as uses to disclose, and names desk rejection as a possible consequence (https://blog.iclr.cc/2025/08/26/policies-on-large-language-model-usage-at-iclr-2026/, fetched 2026-09-25).
- `manuscript/changelog.md` round 6 again records agent-drafted sections, figures, and evidence sheets ("two scouts", "figure-only paper-writer", "front and back writers steered").
- If those agents are LLMs, the statement understates the use. Not re-argued: WONTFIX per the round-5 Phase 0 decision, item 8.

### Build, page count, figures

- **Build:** `iclr2026_conference.log` (2026-09-25 12:14:47.955) is newer than every `.tex`; the newest is appendix.tex at 12:14:47.151. `.blg`/`.bbl` (12:10:41) are newer than every `.bib`; the newest is related_refs.bib at 02:16:12. Counts:
  - `^!` errors: 0
  - LaTeX and package warnings: 0
  - "undefined" (references or citations): 0
  - Overfull: 0 (63 underfull)
  - BibTeX `warning$`: 0 across six databases
  - 45 unique `\citation` keys and 45 `\bibitem`s, including `asai2016tiebreaking` and `orseau2021policyguided`
  - "Output written on iclr2026_conference.pdf (37 pages, 456277 bytes)"

  `manuscript/manuscript.pdf` has 37 pages. Its `pdftotext -layout` text differs from `iclr2026/iclr2026_conference.pdf` only in column whitespace in Tables 6 and 17 (24 lines, all spacing). **PASS.**
- **Page count:** The Conclusion ends on **PDF p.9, L477**. The Reproducibility Statement (L479) and References (L490) begin on p.9. Main text, title through Conclusion, is **9 pages** against the 9-page limit. **PASS**, with zero slack, so every fix below must be space-neutral. 84's cuts pay for 81's disclosures.
- **Visible TODO:** a `grep -c TODO` of the rendered text returns 0. **PASS.**
- **fig:ladder (Figure 2, p.6 L290-307; `figures/fig_ladder.png`, 1791×698):**
  - Three panels as before, plus a new "zero-shot base" row (open diamond) on the validation panel (0.026) and P2 (0.017), placed between the adapter mean and the first adapter.
  - The labels are legible, with no clipping or overlap. The zero-shot interval whiskers ([0.000, 0.063] and [0.000, 0.051]) are barely visible at print size; this is noted, not ranked.
  - The caption now says "The P2u ladder is descriptive, and the first adapter appears on the validation panel only. The zero-shot base model appears on the validation and P2 panels." Review-20 78(c) is closed.
  - `fig_ladder.py` now rounds half-up with `Decimal(repr(v))` (L72-74) and holds 4 `assert` statements. Their loops cover **30 value checks**: 28 (m, lo, hi) triples and per-seed values from `v4/panels arms.{p135,p2,p2u}.*` plus the first adapter from `v2 adapter_reevaluation.learned_adapter.*`, and 2 zero-shot triples from `v6 per_panel.{v2,p2}.{m1_arm, m1_arm_ci95}`.
  - I re-executed exactly these comparisons in a throwaway script against the pinned JSONs, without writing any figure: **30/30 pass.**
- **fig:contracts (Figure 1, p.6 L270-286):** the script, PNG, and values are unchanged since review 20 (`git diff 0277de7..HEAD` is empty for `fig_contracts.*`).

### Numbers re-check

**Artifact state.** The review-20 artifacts are md5-identical:

| artifact | md5 prefix |
|---|---|
| v4/seeds/metrics/analysis.json | d5c3828cba0f |
| v4/panels/metrics/analysis.json | fa5399d9a0f6 |
| v5/metrics/analysis.json | 29d08e8bcbea |
| v4/budget.json | c58180f1c1c7 |
| v5/budget.json | 178f3023fc53 |
| v2/metrics/analysis.json | c609286a7e3f |
| native-arms submission-order audit | 6f523484d3d0 |
| ScienceWorld audit | 83d4265671a7 |

So every review-20 re-derivation stands. I confirmed that the headline strings still render unchanged: 0.875 / 0.793 / 0.603 / 0.347 / 0.021, +0.082 [+0.051, +0.111], +0.285 [+0.140, +0.433], +0.416 [+0.250, +0.591], +0.149 [+0.030, +0.283], −0.041, −0.298, +0.227, +0.002, and +0.058 with their intervals, 22 of 35, +0.305 to +0.395, +0.130 [+0.070, +0.190], +0.115, −0.030, 0.205 → 0.137, 15.22/24, 9.06/40, 48/48, 19/48, 0.915, and 1000/1000. Tables 19-21 are cell-for-cell unchanged; the appendix diff touches only comments.

**New artifacts:**

| artifact | mtime | md5 prefix |
|---|---|---|
| `outputs/choice-frontier/v6/metrics/analysis.json` | 05:02 | c2073fc9e4f3 |
| `outputs/choice-frontier/v6/budget.json` | — | 67f97c42d4b3 |
| `outputs/external-audit/v2/lfs/identity-audit.json` | 05:43 | d94f54e35f55 |
| `outputs/external-audit/v2/budget.json` | — | ea23ac570b5c |

The last evidence commit is `53751f0`, and the evidence tree is clean. In the table below, V6 = `outputs/choice-frontier/v6/metrics/analysis.json`, LFS = `outputs/external-audit/v2/lfs/identity-audit.json`, and P6 = `configs/experiments/choice-frontier-v6/protocol.json`.

| claim (rendered) | PDF location | artifact : key | match |
|---|---|---|---|
| zero-shot D3 +0.005 [−0.025, +0.044] EQUIVALENT (validation); +0.001 [−0.048, +0.051] INCONCLUSIVE (P2) | p.7 L345-346, Table 22 p.35 L1840 | V6 primary.v2 {D3 0.005208, ci95 [−0.025, 0.04375], verdict EQUIVALENT, stage "development"}; primary.p2 {D3 0.001136, ci95 [−0.04773, 0.05114], INCONCLUSIVE, stage "held-out confirmatory"} | yes (stage labels: finding 82) |
| adapter contrast −0.280 [−0.425, −0.142] and −0.415 [−0.589, −0.248] | p.7 L347-348, Table 22 L1843 | V6 co_primary.v2.A {value −0.27951, ci95 [−0.42535, −0.14236]}; co_primary.p2.A {−0.41477, [−0.58902, −0.24811]}; both SEPARATED_BELOW | yes |
| **Table 22** (tab:appendix-zeroshot), all 27 cells | p.35 L1839-1843 | D3 row: primary.* and pooled.D3 {0.003261, [−0.02391, 0.03315], EQUIVALENT}. p row: sign_flip_p 0.90625 / 1.0 / 0.896484. S row: co_primary.{v2,p2}.S {−0.32083 [−0.421875, −0.22604]; −0.1875 [−0.23864, −0.13977]}; pooled.S {−0.25707 [−0.32446, −0.19728]}; p 4.8828e-4 / 9.7656e-4 / 2.3842e-7. A row: pooled.A {−0.34420 [−0.45924, −0.23188]}; p 0.0039063 / 0.0039063 / 7.6294e-6. All verdicts match | yes, all 27 (half-up: −0.1875 → −0.188, 0.04375 → 0.044) |
| zero-shot M1 0.026 [0.000, 0.063], 0.017 [0.000, 0.051], 0.022 [0.003, 0.046] pooled | p.35 L1866-1867; Fig. 2 | V6 per_panel.v2 {m1_arm 0.026042, ci95 [0.0, 0.0625]}; per_panel.p2 {0.017045, [0.0, 0.051136]}; pooled {0.021739, [0.002717, 0.046196]} | yes (0.0625 → 0.063 half-up) |
| 1,592 calls, all valid via first extractor rule; heap-head − chance +0.003 / +0.001; last-label 0.328 / 0.285 (chance about 0.13-0.14); 4 of 46 solve | p.35 L1867-1870 | V6 per_panel.{v2,p2}.behaviour: model_calls 836 + 756; extraction_rules.json_object 836 / 756; valid_output_rate 1.0; teacher_agreement_minus_chance 0.00339 / 0.00117; last_label_rate 0.32828 / 0.28472; teacher_agreement_chance 0.1418 / 0.1322; terminations.goal_reached 3 + 1 | yes |
| 46/46 replayed; no amendment | p.35 L1859, L1863, L1871-1872 | V6 episode_accounting.{v2,p2}.episodes_replayed 24 / 22; issue-141-closeout.md L3 (`0fa497c` before launch) and L66 | yes |
| InternVL 11,748 against 3,111 tokens; 43-55 GPU-h against 30 | p.35 L1860-1862 | P6 arm_choice.feasibility_evidence.{internvl_mean_tokens 11747.999, qwen_mean_tokens 3110.520}; arm_choice.reason "6 cells = 43-55 GPU-h training alone" | yes |
| zero-shot prompt: "one appended system sentence asking for a single JSON choice" | p.35 L1857-1858 | P6 arm.system_message_suffix holds **two** sentences, the JSON format and "Choose the frontier state whose scene appears closest to satisfying the goal pages." | **incomplete description** (finding 82) |
| ledgers 2.25/30 (v6) and 2.89/12 (external v2) | p.5 L245-246, Table 2 p.17 L890-893, p.18 L965-967 | Σ attempts[].gpu_hours for v6/budget.json = 2.245242 (5 attempts, all succeeded; schedule.authorization.window_gpu_hours_cap 30.0); external-audit/v2/budget.json total_gpu_hours 2.891025 = Σ attempts 0.008972 + 2.882053, schema.gpu_hours_cap 12.0, paid_api_usd 0.0 | yes |
| LFS: all 400 pairs diverge, by the third decision; first-divergence median 0, max 2 | p.1 L033-034, p.2 L078, p.8 L379, p.36 L1921 | LFS pairs_checked 400, pairs_identical 0, first_divergence_index {min 0, median 0, max 2, pairs_diverging_at_0 380} | yes |
| LFS 1.0 against 0.825 under the paper budget; 0.0775 matched; per seed 0.0625 / 0.075 / 0.075 / 0.0875 / 0.0875 | p.1 L034-036, p.2 L079, p.8 L380-382, p.36 L1922-1925 | LFS paper_budget.success {reference 0.825, random_valid_mean 1.0, every seed 1.0}, verdict SATURATED; matched_decision_budget.success {random_valid_mean 0.0775, per_seed as printed, reference 0.825}, verdict CHOICE_REGISTERED; prediction {SATURATED, CHOICE_REGISTERED} | yes |
| every reference loss ends at the token cap | p.36 L1923 | LFS supplementary.terminated.reference {success 66, token_limit 14} | yes |
| GPT-4o published 0.768 | p.8 L384, p.36 L1926 | LFS published_model_success.value 0.768425 = mean of {cd3 100.0, cd5 63.16, cd7 47.37, su4 96.84}; issue-142-protocol.md L29-34 table | yes |
| token caps 1,000,000 and 100,000; Sudoku 6×6 excluded; games 0-19; 80 tasks; upstream `3025bdaa`; 57/57 byte-identical probe | p.36 L1912-1919 | issue-142-protocol.md L22-37 (Sudoku 6×6 win rate 2.22%); LFS upstream.commit 3025bdaa3add…, license Apache-2.0, tasks 80; `outputs/external-audit/v2/lfs-probe/fast-equivalence.json` {checked 57, identical 57} | yes |
| 80/80 and 400/400 replayed | p.36 L1920, Table 2 L892-893 | LFS replay.reference {80, match 80}, replay.random_valid {400, match 400}, mismatch 0 | yes |
| **Table 24** (tab:appendix-lfs), all 30 cells | p.36 L1894-1899 | LFS per_config.{cd3,cd5,cd7,su4}.{paper_budget,matched_decision_budget}.{success.reference, success.random_valid_mean, contrast.mean_difference_reference_minus_random, contrast.bootstrap_95ci, verdict}. cd3 1.0 / 1.0 / 0.0 [0, 0] / 0.12 / 0.88 [0.77, 0.97]; cd5 0.75 / 1.0 / −0.25 [−0.45, −0.10] / 0.11 / 0.64 [0.37, 0.87]; cd7 0.65 / 1.0 / −0.35 [−0.55, −0.15] / 0.02 / 0.63 [0.41, 0.84]; su4 0.9 / 1.0 / −0.10 [−0.25, 0.0] / 0.06 / 0.84 [0.70, 0.95]; All 0.825 / 1.0 / −0.175 [−0.2625, −0.10] / 0.0775 / 0.7474999999999999 [0.6475, 0.8375] | yes, all 30. Note: the "All" matched difference prints +0.747 from the stored float, while its exact value 0.825 − 0.0775 = 0.7475 would print 0.748 under the paper's stated half-up rule, and the same cell's endpoints 0.6475 and 0.8375 are rounded up. Immaterial (0.001) and disclosed in the source comment; noted, not ranked |
| last-label 0.300 (chance 0.144) for the first adapter | p.7 L333 | v2 adapter_reevaluation.learned_adapter.m4_teacher_agreement.{selected_last_rate 0.29975, chance 0.14436} | yes (scaled adapter's chance missing: 75 remainder) |
| metric note: exact reference 0.875 by construction; hadd-greedy 0.882 / 0.928 / 0.906 | App I p.22 L1173-1174 | v4/panels arms.{p135,p2,p2u}.exact_reference.m1 0.875; hadd-greedy.m1 0.88229 / 0.92841 / 0.90625 | yes |
| P2 small-cluster disclosure: 11 clusters, 8 positive and 3 negative | p.7 L341-343, App U.1 p.33 | v4/panels heldout_p2.separation.vs_eps_0.75.per_task_difference: negative on 15puzzle-955075, blocksworld-955022, blocksworld-955127; positive on the other 8 | yes |
| Orseau & Lelis 2021; Asai & Fukunaga 2016 | p.2 L105-107; References p.9 (Asai) and p.12 (Orseau) | bbl `orseau2021policyguided` DOI 10.1609/aaai.v35i14.17469; `asai2016tiebreaking` DOI 10.1609/aaai.v30i1.10071. Both match the Semantic Scholar records 53ae4b740f4a870004f9f840a731a0e051eb2b95 and 47be28eee56a6171ae0b1a26c3692221f2d6cc15 (review 20) | yes |

**Stored LFS values the paper does not report** (used in finding 81): supplementary.expansions_median {random_valid 201.0, reference 29.5}; expansions_max {random_valid 102,606, reference 1,300}; tokens_median.random_valid 0.0; matched_decision_budget.random_valid_decision_budget_curve.random_valid_success at 1× / 1.25× / 1.5× / 1.75× / 2× = 0.0775 / 0.0975 / 0.14 / 0.17 / 0.19, auc_normalized 0.1353; reference_success_at_own_budget 0.825 (the same as its token-budget success); matched_decision_budget.contrast.tasks_random_better 4. The protocol and closeout add the 500,000-expansion safety guard, which "never bound" (issue-142-closeout.md), and the pre-audit probe "won 100/100 non-audited episodes within the guard" (issue-142-protocol.md, Pre-registered prediction).

### Evidence-comment spot-check

I checked 14 comments, 10 of them from round 6. For each I checked that the path exists and that the key and value, or the line reference, match.

1. **[r6]** results.tex, 5.5 LFS paragraph comment: LFS pairs_checked 400 ✓, pairs_identical 0 ✓, first_divergence_index.max 2 ✓, tasks 80 ✓, paper_budget.* 1.0 / 0.825 / SATURATED ✓, matched 0.0775 / CHOICE_REGISTERED ✓, published_model_success.value 0.768425 ✓. `issue-142-protocol.md` L191-194 is deviation 1, the Qwen3-30B-A3B-Instruct-2507 @ `0d7cf239` substitution ✓. `issue-142-closeout.md` L11-15 is the token-cap mechanism ✓. `issue-137-survey.md` row 6 at L38 is LFS ✓. Closeout L3-5 "Both predictions held" ✓.
2. **[r6]** results.tex, 5.4 zero-shot comment: V6 primary.v2.* and primary.p2.* values and verdicts ✓. The margin at "P141 L57" is the D3 rule ✓, and S and A at L58-59 ✓. co_primary.*.A values ✓.
3. **[r6]** results.tex, 5.1 ledger comment: `issue-141-closeout.md` L77 "2.245 / 30" ✓; v6 budget.json attempts[0..4].gpu_hours sum 2.2452 ✓. **"cap schedule.window_gpu_hours_cap 30.0" names a key that does not exist**: the cap is at `schedule.authorization.window_gpu_hours_cap`, and `schedule.window_gpu_hours_cap` returns null (80 remainder). External v2 total_gpu_hours 2.8910 ✓, schema.gpu_hours_cap 12.0 ✓, schema.independent ✓, closeout L108 "Total 2.89 GPU-h of the 12 GPU-h cap" ✓.
4. **[r6]** results.tex, fig:ladder zero-shot-row comment: V6 per_panel.{v2,p2}.arms.zero_shot_base.{m1,ci95} exist and match ✓. P6 evaluation.p2u = "not evaluated" ✓.
5. **[r6]** appendix.tex, U.3 arm comment: P6 arm.condition zero_shot_base ✓, arm.adapter null ✓, arm.system_message_suffix ✓ (two sentences; see 82), arm.extraction has 3 rules ✓, inference.do_sample false ✓. The comment writes "inference_seed 17", but the key is top-level `inference_seed`, not under `inference` (resolves as a top-level key). evaluation.model_episodes 46 ✓. InternVL tokens 11747.9985 / 3110.5199 ✓; "P141 L13-14" is the feasibility bullets ✓.
6. **[r6]** appendix.tex, U.3 results comment: primary.p2.ci95[1] 0.05114 against margin 0.05, closeout L32 ✓; per_panel.* m1_arm and ci95 ✓; model_calls 836 + 756 ✓; teacher_agreement_minus_chance ✓; last_label_rate ✓; closeout L46 chance ≈ 0.13-0.14 ✓; L48-49 3/24 and 1/22 ✓; prediction at P141 L72 ✓; closeout L66 replay ✓.
7. **[r6]** appendix.tex, Table 22 comment: primary.{v2,p2}.{D3, ci95, verdict, sign_flip_p} ✓; co_primary.{v2,p2}.{S,A}.{value, ci95, verdict, sign_flip_p} ✓; pooled.{D3,S,A}.{…, sign_flip.p_two_sided} ✓; raw p values 0.00048828125, 0.0009765625, 2.384e-07, 7.629e-06 ✓; P141 L65-67 pooled and sign-flip descriptive ✓.
8. **[r6]** appendix.tex, V.1 design comment: `issue-142-protocol.md` L57-62 random-valid, zero tokens, seeds ✓; `lfs-probe/fast-equivalence.json` {checked 57, identical 57} ✓; LFS upstream.commit and license ✓; per_config.*.tasks 20 ✓.
9. **[r6]** appendix.tex, V.1 results comment: replay.* ✓; supplementary.terminated.reference {success 66, token_limit 14} ✓; per-seed matched values ✓; A1 at protocol L212 "(2026-09-25 02:50 AEST, commit e89a793, before any audit episode)" ✓.
10. **[r6]** appendix.tex, Table 24 comment: per_config and top-level keys ✓. The raw 0.7474999999999999 [0.6475, 0.8375] is recorded ✓. "rendered 0.747 from the stored raw value per Main, 2026-09-25" gives a person as provenance, not an artifact; noted.
11. **[r6]** introduction.tex / abstract.tex, P2u "never solved in screening" comments: concentration.per_panel.p2u.counts positive 4 ✓. **"P2u 0/10 random-valid goals on all 12 tasks, local evidence sheet §9 (#139)" is the only source named for the 0/10 claim**, and that sheet is in neither repository (80 remainder). The repository source exists (`issue-139-closeout.md` L56, "All 12 happen to have 0/10 random goals.") and is cited in the results.tex comment, but not here.
12. **[r6]** discussion.tex, external-anchor comment: `issue-137-survey.md` "## Candidate table (7 candidates)" at L29 ✓; LFS pairs_identical 0, paper_budget.verdict SATURATED, matched verdict CHOICE_REGISTERED ✓.
13. **[r5-consolidation]** results.tex, last-label comment: v2 selected_last_rate 0.2997 and chance 0.1444 ✓.
14. **[r5-consolidation]** results.tex and appendix.tex V-SMALL comments: 8 positive, 3 negative, 0 zero of 11, with the negatives named correctly ✓. The DAgger pointer is now `issue-140-protocol.md` L123 (A1 item 2) ✓, fixing review-20 finding 80.

**Tally:** 12 of 14 resolve fully. Comment 3 names a non-existent key path. Comment 11 relies on a non-repository sheet. Both are recorded under the 80 remainder.

### Verification of review-20 findings (69-80) and earlier closures

| # | sev (r20) | r21 result | evidence at `ba7d4d2` |
|---|---|---|---|
| 69 | MAJOR | **VERIFIED** (all three prescribed parts landed) | (a) Portable rule: Discussion p.9 L442-448 "The portable rule has two checks before random-valid success is read as choice. The per-decision identity audit must find divergent pairs, and the success budget must bind decisions … a learned policy's difference from random-valid should be reported with its position on a privileged exact-ϵ ladder". (b) Second realisable policy: 5.4 p.7 L344-349 and App U.3 (zero-shot base; the InternVL arm was ruled out before any outcome and is disclosed at p.35 L1860-1863 and in Limitations p.9 L462). (c) LFS audit: 5.5 p.8 L378-385, App V.1. What the new evidence can bear is raised separately as 81 and 82. |
| 70 | MAJOR | **VERIFIED** | 5.4 p.7 L350-355 "The random-control screen admits tasks on which near-uniform choice sometimes succeeds, since random-valid must reach the goal in 1 to 9 of its 10 screening episodes. … all 12 of its tasks had 0/10 random-valid screening goals. Choice still discriminates there, since the ladder passes (descriptive), and … its gain rests on 4 of 12 tasks". Intro p.2 L070-072, Discussion p.9 L433-435, and the abstract p.1 L027-029 match. `grep enriches` returns 0 hits. |
| 71 | MINOR | **VERIFIED** | "not separated from that rung on the validation panel" in the abstract p.1 L030-031, Intro p.2 L069, 5.4 p.7 L336, Discussion p.9 L432, and Conclusion p.9 L472. The non-equivalence sentence is at 5.4 p.7 L340-341 and App U.1. `grep 'sits at\|at that rung'` returns no ladder-position hit. |
| 72 | MINOR | **VERIFIED** | App U.2 p.34 L1834-1835 "therefore produces no detectable change in measured choice quality, since ∆ is inconclusive against the ±0.05 margin, and the ablation is inconclusive." |
| 73 | MINOR | **VERIFIED** | Intro p.2 L093-095 and 5.4 p.7 L355-357 "from seeds on which no adapter had been evaluated (the seed extension followed a controls-only screen of the first 40 seeds)". |
| 74 | MINOR | **VERIFIED** | (a) App J p.22 L1187 "Follow-up windows executed after the program on separate GPU ledgers (Table 2) and on CPU only (the comparator zoo, the counterfactual audit, and the first external audit)". (b) App J p.23 "one training run at seed 17 per enumeration-contract model and cell". (c) Design p.5 L219 "At submission (receipts in Table 2)". (d) Letter ranges dropped; the text now reads "Results Detail appendices" (p.4 L196, p.5 L228, p.8 L405). (e) Table 2 p.17 L887-888 "and 88/88 P2 plus 96/96 P2u learned episodes". |
| 75 | MINOR | **PARTIAL** (remainder MINOR, WORDING) | 5.4 p.7 L332-334 "the scaled adapter's last-label rate per seed is 0.205, 0.192, and 0.171 against 0.300 (chance 0.144) for the first adapter on the same panel". The dangling table pointer is gone and the units are unified, and App U now carries the per-seed rates. **Remaining:** the scaled adapter's own chance rate (about 0.125-0.131, v4/seeds per_seed.*.teacher_agreement_chance 0.1247 / 0.1306 / 0.1267) is still missing, so a reader compares 0.205 against 0.300 with only one baseline. **Fix:** "…0.205, 0.192, and 0.171 (chance about 0.13) against 0.300 (chance 0.144)…". It is space-neutral: 4 words. |
| 76 | MINOR | **VERIFIED** | App I p.22 L1173-1174 "Because goal selection is the (Rt+1)-th decision, the exact reference fails at m = 1 and scores M1 = 0.875 by construction, and arms that reach the goal in fewer decisions can exceed it (privileged hadd-greedy 0.882, 0.928, and 0.906)". Design p.4 L172 "defines the imitation target". The Discussion's "remains far from the reference" is replaced (p.9 L433). |
| 77 | MINOR | **VERIFIED** (wording). The p-value part was declined by author decision (changelog, review-20 entry: "no unpinned p-value"); not re-argued. | 5.4 p.7 L341-343 and App U.1: "The P2 separation rests on 11 task clusters, with 8 positive and 3 negative per-task differences, and percentile intervals can under-cover at this size." Observation only: #141 now pins exact sign-flip p values for the zero-shot contrasts, "answering review 20's small-cluster concern" (P141 L67), but not for the adapter's P2 S that the concern was about. |
| 78 | MINOR | **VERIFIED** | (a) Abstract p.1 L020 "The solve-versus-budget area M1", L026 "D3, adapter minus random-valid M1 averaged over three seeds"; Intro p.2 L060 and L066. (b) The first-adapter M4 paragraph is out of 5.4, leaving a pointer at p.7 L333-334. (c) The Figure 2 caption is fixed. (d) Discussion p.9 L433 "Its M1 of 0.151 to 0.432 remains well below the reference's 0.875." The abstract's new D3 sentence introduces a grammar problem (84). |
| 79 | MINOR | **VERIFIED** | Related Work p.2 L105-107 cites Orseau & Lelis (2021) and Asai & Fukunaga (2016). Both bib entries match their Semantic Scholar records. |
| 80 | MINOR | **PARTIAL** (remainder MINOR, WORDING) | The named locations are fixed: the L124 → L123 pointer, and "local evidence-r5.md" is replaced by "rounded half-up to 3 dp from the named keys". **New instances of the same pattern in round 6:** (i) abstract.tex and introduction.tex comments name "local evidence sheet §9 (#139)" as the only source for the P2u 0/10 claim; (ii) the results.tex 5.1 ledger comment cites the non-existent key `schedule.window_gpu_hours_cap` (the actual key is `schedule.authorization.window_gpu_hours_cap`); (iii) the Table 24 comment cites "per Main" as provenance. **Fix:** replace (i) with `issue-139-closeout.md` L56, correct (ii), and replace (iii) with "rounded half-up from the stored repr". |
| 49, 60 (round 4, #134) | — | **VERIFIED (no regression)** | 5.2 p.5 L258-263 still reports 19/48, "did not hold", and decisions 2-50 (median 6). App S p.31 carries "PREDICTION FAILED" and "a property of the executed serial rule". Table 15 keeps the task-clustered M4 intervals. |
| #137 reframe | — | **VERIFIED**, updated as the author decided | Discussion p.9 L437-441 "The complete-set identity failure is shown only on our runtime, since none of the seven surveyed published interfaces uses that contract. … The contribution is therefore the measurement and its two checks, not the exposure of a single flaw." The CONTEXT "External audit claim" entry is respected: no claim that the published GPT-4o results are invalid. |
| Review-16 finding 15 | — | **VERIFIED (present)** | Related Work p.3 L133-134 "This paper operationalizes the known admissible-action handicap in search-execution evaluation with a per-decision identity audit that returns both verdicts on one runtime…". |
| 51, 52 hedges | — | **VERIFIED** | 51: Related Work p.3 L131-133 and App P p.28 L1470-1471. 52: App R p.30 L1593 "no last-label comparator and no equivalence claim", L1616-1617 "do not establish a position habit". |
| 40 | MAJOR | WONTFIX (unchanged) | App Y p.37 L1985. The compliance risk is reported above. |

### Placeholder and claim-discipline check

- **Visible `[TODO`:** 0. **PASS.**
- **3 seeds; DAgger single seed; held-out = P2 only; P2 screened; three-part ladder position; privileged rungs; #134 failed; A1 disclosures:** all unchanged from review 20 and still present. **PASS.**
- **No equivalence claim without margin:** **PASS for the adapter**, now "not separated" everywhere plus the non-equivalence sentence. **Zero-shot:** the equivalence claim uses the pre-registered ±0.05 margin (P141 L57). But Table 22 also prints "EQUIVALENT" for the **pooled** 23 tasks (descriptive), whereas `CONTEXT.md` says "equivalence to uniform choice is claimed only on the validation panel". And the validation verdict is the protocol's development-stage verdict (finding 82).
- **No planning-ability claim:** **PASS.**
- **External-audit claim (new CONTEXT entry):** "may not generalise to agent benchmarks at large or claim the published GPT-4o results are invalid". Neither is claimed outright. But the Intro p.2 L080 "so success saturates unless the budget binds decisions" and the Conclusion p.9 L476-477 "On a published interface, success saturates under a budget that does not bind decisions, so the audit needs both checks" state a general rule from one interface whose outcome was guaranteed (finding 81).
- **Old and new contract not compared as performance rows:** **PASS** (Table 25 caption).
- **Round-6 amendment disclosure:** #141 "no amendment followed" (p.35 L1863) ✓. #142 A1 "made before any audit episode, only reordered the smoke and audit start" (p.36 L1926-1927) ✓. Design p.5 L216-217 says both protocols were frozen before their outcomes ✓.

### Verification of prior findings (reviewer follow-up detail)

- **82 (d), regressed:** the body defines D3 once (introduction.tex, "adapter minus random-valid M1 averaged over three training seeds") and reuses it for the single-realisation zero-shot arm (results.tex 5.4). Fix: add "(here a single realisation)" after the zero-shot D3 value.
- **82 (e), regressed:** results.tex 5.4 reads "A zero-shot policy scores as uniform choice, so the measurement separates the two realisable policies." Fix: "On the validation panel a zero-shot policy scores as uniform choice, so the measurement separates the trained adapter from it."
- **80 (iii), open:** appendix.tex Table 24 comment still says "per Main, 2026-09-25". Fix: delete it and keep "rounded half-up from the stored repr".
- **80 pattern, new instance:** introduction.tex evidence comment for the ladder gap cites "(#135 E135-63)", which is the membership-freeze label elsewhere. Fix: "(#135 E135-05, E135-06)".
- **Lesser:** experimental_design.tex comments cite "V-SCR2" and "V-HO2 (r5-consolidation.md)", which are session labels. Fix: delete "V-SCR2"; cite issue-139-closeout.md L58 for "first 40 seeds".

### New findings

**Axis and genre coverage** (everything not listed as a finding passes or is n/a):
- **Axis 1:** the 10-minute test delivers the Δbelief above. The new external result's value is finding 81.
- **Axis 2:** falsifiability passes for #141, whose zero-shot arm could have come out POSITIVE. **It fails for #142's primary reading (81).**
  - HARKing scan: 4 new bare-fact generalisations. The three most damaging are "so success saturates unless the budget binds decisions" (Intro p.2 L080), "a failure the per-decision audit does not detect and a decision-matched budget does" (Discussion p.9 L440), and "On a published interface, success saturates under a budget that does not bind decisions, so the audit needs both checks" (Conclusion p.9 L476-477). The fourth is "so the instrument ranks the two realisable policies" (p.7 L348).
  - Wording register passes. Statistical hygiene: finding 83.
- **Axis 3:** findings 82(d) and 83.
- **Axis 4:** findings 81 and 82.
- **Axis 5:** finding 84. The experiment order still runs an elimination tournament. The zero-shot block ends in a local verdict. The LFS block ends in a verdict that its own construction guarantees (81).
- **BENCHMARK checklist:**
  - Two bottlenecks: pass (the contract and M1 with the ladder).
  - Definitions against near-miss alternatives: pass. The new near miss (token-denominated against decision-denominated budgets) is argued in the Discussion.
  - Headline findings as claims: pass.
  - Adoption risks: screening is now answered honestly (70 verified). A budget-denomination risk is added but supported only by a guaranteed case (81).

#### 81 · MAJOR · Axis 2 + Axis 1 (the LLM-First Search saturation could not have lost, yet carries a contribution, the portable rule's second check, and the Conclusion) · `iclr2026_conference_results.tex; iclr2026_conference_appendix.tex; iclr2026_conference_discussion.tex; iclr2026_conference_introduction.tex; iclr2026_conference_abstract.tex`

- **Location:**
  - Abstract p.1 L033-036 (abstract.tex L25): "yet solves every task under the paper's token budget (1.0 versus 0.825 for a substituted reference model), and a decision-matched budget restores the contrast (0.0775)."
  - Intro p.2 L077-080 (introduction.tex L31): "…and only 0.0775 at the reference's decision count, so success saturates unless the budget binds decisions".
  - Contribution 4, p.2 L088-089.
  - 5.5 p.8 L378-383 (results.tex L184): "…yet under the paper's own token budget it solves all 80 tasks (1.0) against 0.825 for the reference, because a token cap never binds a chooser that spends no tokens. Given only the reference's own number of expansions, random-valid solves 0.0775…".
  - App V.1 p.36 L1909-1911 "every unexpanded alternative stays in the frontier. Random-valid … spends zero tokens" and L1922-1926 "Under the paper's budget random-valid wins every episode at every seed, so the verdict is SATURATED … Both pre-registered predictions held."
  - Discussion p.9 L438-441 (discussion.tex L23): "random-valid success instead saturates under the paper's own budget although every decision diverges, a failure the per-decision audit does not detect and a decision-matched budget does."
  - Conclusion p.9 L476-477 (discussion.tex L57): "On a published interface, success saturates under a budget that does not bind decisions, so the audit needs both checks."
- **Issue:**
  - (i) **The SATURATED outcome was guaranteed.** Random-valid spends zero tokens, so the token cap never stops it. The frontier keeps every alternative, and every audited game is solvable, so random-valid is a complete randomized search that must eventually win.
    - The #142 protocol says exactly this before the audit: "random_valid is a complete randomized search. The probe won 100/100 non-audited episodes within the guard." The only way to lose was the 500,000-expansion safety guard, which "never bound" (closeout).
    - The paper does not disclose the guard, the probe, or the expansion counts: random-valid median 201 and maximum 102,606, against the reference's median 29.5 and maximum 1,300 (LFS supplementary.*).
    - "Both pre-registered predictions held" therefore reads as a risky test that passed, when one of the two predictions could not have failed. Under the Axis 2 rule, a result that could not have lost is a demonstration, not evidence.
  - (ii) **The matched-budget reading is reference-conditioned.** Random-valid gets the reference's own expansion count on each task, so the reference's success under this reading equals its token-budget success by construction (`reference_success_at_own_budget` 0.825). The +0.747 difference in Table 24 compares a post-hoc stopping budget against itself.
    - The artifact stores the budget curve, which the paper does not report: random-valid reaches 0.0775 at 1×, 0.14 at 1.5×, and 0.19 at 2× the reference's expansions (normalised AUC 0.135). That curve is the non-conditioned evidence that choices matter.
    - "Restores the contrast (0.0775)" also labels a success rate as a contrast.
  - (iii) **The value anchor.** LFS's published evaluation compares LLM-guided searches (ToT-BFS, BestFS, MCTS) and reports no random-valid control (https://arxiv.org/abs/2506.05213, fetched 2026-09-25). So no published number changes, as the CONTEXT entry itself requires.
    - What remains is the rule "the success budget must bind decisions". That is the established compute-matched-baseline principle, for example random search under a matched evaluation budget as the NAS baseline (Li & Talwalkar, UAI 2019, https://arxiv.org/abs/1902.07638; Semantic Scholar 35a59bd09974c7fc78cf681f77f7301e180fd23c).
    - Its instance here is guaranteed by construction, so the belief update is one a search-literate reader already holds.
  - (iv) **The generalisation.** The Intro's "so success saturates unless the budget binds decisions" and the Conclusion's "so the audit needs both checks" state a general law from one interface whose outcome was fixed in advance. The Discussion's "a failure the per-decision audit does not detect" blames the audit for something outside its scope: the audit correctly returned 0/400 identical.
- **Fix:**
  - 5.5, space-neutral: replace "Given only the reference's own number of expansions, random-valid solves 0.0775, so success there measures choice only under a budget that binds decisions" with "This saturation is guaranteed: the frontier keeps every alternative, so a zero-token chooser is a complete randomized search, which here used up to 102,606 expansions against the reference's 1,300. Counted in expansions, random-valid solves 0.0775 at the reference's own count and 0.19 at twice it."
  - V.1: disclose the 500,000-expansion guard (never bound) and the pre-audit probe (100/100). Change "Both pre-registered predictions held" to "The matched-budget prediction held, and the paper-budget saturation follows by construction." Add a sentence stating that the reference's matched-budget success equals its token-budget success by construction. Report the stored budget curve (1×-2×) in Table 24 or its caption.
  - Discussion L438-441: "On LLM-First Search, whose token cap does not bind a zero-cost chooser, random-valid success saturates by construction, although every decision diverges. Counted in expansions, the reference's choices matter." Cite the compute-matched-baseline precedent in the portable-rule paragraph.
  - Intro L080 and Conclusion L476-477: drop the general "success saturates unless …". Write, for example, "on LLM-First Search a zero-cost chooser saturates under the paper's token caps by construction, so success must be counted against a budget that binds decisions".
  - Abstract: "…and at the reference's own number of expansions random-valid solves only 0.0775."
  - Pay for the space with the 84 cuts.
- **Why it changes the verdict:** Contribution 4, the second check of the portable rule, the Discussion's value sentence, and the Conclusion's last sentence all rest on this result. Framed as a guaranteed demonstration of a known principle, it is honest and still useful. Framed as a pre-registered test of a newly found failure mode, it overstates.
- **Fix class:** MEANING (it changes what the LFS result is claimed to show, from a tested failure mode to a by-construction demonstration)
- **Status:** CLOSED (`58e661e`)

#### 82 · MINOR · Axis 4 + Axis 3 (zero-shot policy: undisclosed prompt instruction, unstated verdict stages, notation reuse) · `iclr2026_conference_results.tex; iclr2026_conference_appendix.tex`

- **Location:**
  - App U.3 p.35 L1856-1858 (appendix.tex L1376): "given the frozen scene-only choice-frontier observation, one appended system sentence asking for a single JSON choice".
  - 5.4 p.7 L344-349 (results.tex L149): "is equivalent to uniform choice on the validation panel, D3 = +0.005 [−0.025, +0.044] within the pre-registered ±0.05 margin, and inconclusive on P2 … so the instrument ranks the two realisable policies".
  - Table 22 p.35 L1836-1843: "Panel endpoints are pre-registered and pooled entries are descriptive" and "Pooled (23, descriptive) … EQUIVALENT, 0.896".
- **Issue:**
  - (a) **Prompt.** The appended suffix (P6 `arm.system_message_suffix`) is two sentences. The second is a zero-shot policy instruction: "Choose the frontier state whose scene appears closest to satisfying the goal pages." The paper describes only the format request, so a reader cannot tell that the zero-shot policy was given a goal-similarity heuristic. That changes what "zero-shot" means here.
  - (b) **Stage.** The #141 protocol states "Verdicts on P2 are held-out confirmatory; verdicts on the #135 panel are development-stage" (P141, the line after the endpoint list; V6 `primary.v2.stage` "development", `primary.p2.stage` "held-out confirmatory"). The body's equivalence claim is the development-stage verdict, and the confirmatory one is INCONCLUSIVE. Neither the body nor Table 22 says so.
  - (c) **Pooled equivalence.** Table 22 prints a pooled EQUIVALENT verdict, while `CONTEXT.md` says "equivalence to uniform choice is claimed only on the validation panel".
  - (d) **Notation.** D3 is defined as "adapter minus random-valid M1 averaged over three seeds" (abstract, Intro). For the zero-shot arm it names a single greedy realisation at one inference seed (P141 "One realisation per (task, algorithm)").
  - (e) **The ranking claim.** "Ranks the two realisable policies" is literally true. But because the zero-shot arm scores as uniform choice, the ranking re-states D3's separation of the adapter from chance; it does not order two non-trivial choosers.
- **Fix:**
  - (a) U.3: "one appended system message stating the JSON format and asking for the frontier state whose scene appears closest to satisfying the goal pages".
  - (b) 5.4: "…is equivalent to uniform choice on the validation panel (development stage), D3 = …, and inconclusive on the held-out P2 (confirmatory)…". Add the stage to the Table 22 column headers.
  - (c) Print the pooled verdict as "(within margin, descriptive)" or drop it.
  - (d) Write D for the zero-shot arm, or define "D3" once as the endpoint name for both arms.
  - (e) "…so the instrument separates the trained adapter from a zero-shot policy that it scores as uniform choice".
- **Fix class:** WORDING
- **Status:** CLOSED (`58e661e`)

#### 83 · MINOR · Axis 2 statistical hygiene (sign-flip p values printed beside EQUIVALENT verdicts; the convention is absent from the Statistics appendix) · `iclr2026_conference_appendix.tex`

- **Location:** Table 22 p.35 L1840 (appendix.tex L1403): "verdict, p | EQUIVALENT, 0.906 | INCONCLUSIVE, 1.000 | EQUIVALENT, 0.896". Statistics appendix p.19-20, which has no sign-flip entry. Its own rule at p.19: "Wherever the text reports a non-material contrast …, an adjacent sentence states that non-significance is not equivalence."
- **Issue:**
  - An exact sign-flip p tests a zero mean difference. Printed in the same cell as "EQUIVALENT", p = 0.906 invites exactly the reading the Statistics appendix forbids: a large p taken as support for equivalence. The equivalence verdict actually comes from the interval inside ±0.05.
  - The Statistics appendix does not define the sign-flip convention (exact, all 2^n vectors, two-sided, descriptive) now used in Table 22.
- **Fix:** Drop the p value from the D3 row, or print it in its own row with the note "p tests a zero difference; EQUIVALENT is the ±0.05 margin rule". Add one sentence to the Statistics appendix defining the exact sign-flip p (V6 `per_panel.*.*.sign_flip.{exact, sign_vectors, statistic}`) as descriptive.
- **Fix class:** WORDING
- **Status:** CLOSED (`58e661e`)

#### 84 · MINOR · Axis 5 (abstract length, number density, and two garbled sentences) · `iclr2026_conference_abstract.tex`

- **Location:**
  - Abstract p.1 L013-038: 327 words and 31 decimal numbers.
  - L026-027 (abstract.tex L20): "A scaled adapter beats uniform choice on D3, adapter minus random-valid M1 averaged over three seeds (+0.285 [+0.140, +0.433]), and on a held-out panel (+0.416 …)".
  - L027-028: "On an unscreened panel whose tasks random-valid never solved in screening, the gain is …".
  - L036: "restores the contrast (0.0775)".
- **Issue:**
  - "Beats uniform choice on D3 … and on a held-out panel" reads D3 as a panel.
  - "Unscreened … in screening" reads as a contradiction until the reader learns that screening ran but did not gate admission.
  - 0.0775 is a success rate, not a contrast (see 81).
  - An abstract of more than 300 words with 31 decimals and six bracketed intervals buries the Δbelief a skimming reviewer should get in 10 seconds. The 164-word abstract of review 13 carried the same claim structure.
- **Fix:**
  - Keep one interval per result and cut the rung values (0.793, 0.603, 0.347) to "and the three exact-ε rungs in order".
  - "A scaled adapter beats uniform choice by D3 = +0.285 [+0.140, +0.433] (adapter minus random-valid M1, three seeds) and by +0.416 on a held-out panel."
  - "On a panel admitted without the random-control screen (all its tasks had 0/10 screening goals), the gain is +0.149 …".
  - Apply the 81 wording.
  - Target 220 words or fewer. The freed lines also give the main text the room 81 needs.
- **Fix class:** WORDING
- **Status:** CLOSED (`58e661e`)

**Disposition (2026-09-25, `58e661e`):** 81 CLOSED by author decision (reviewer reframe: by-construction demonstration, guard, probe, expansion counts, budget curve, compute-matched precedent `li2019random`). 82-84 and the 75/80 remainders CLOSED as prescribed. The reviewer's experiment paths are filed as #143 (one-seed InternVL3.5-8B adapter) and #144 (modality contrast under the choice-frontier contract) and are not written into the paper. Finding 40 WONTFIX unchanged.

### What would change the verdict

The numbers are right, the pre-registration is real, and every review-20 fix landed except two small remainders (75 and 80). The paper stays at WEAK REJECT, rating 4, for a reason that is no longer about honesty of reporting. The two new experiments came out as they had to.

The LFS audit (81) is a guaranteed demonstration. Its SATURATED verdict follows from a complete frontier and a zero-cost chooser, as the #142 protocol and the pre-audit probe (100/100) already showed. Its matched-budget contrast is conditioned on the reference's own stopping point. The zero-shot policy (82) scores as uniform choice, so the instrument has still ordered only one non-trivial realisable policy.

What would move it to BORDERLINE (rating 6):
- **81, zero experiments:** state the LFS saturation as by construction, report the stored budget curve (0.0775 at 1×, 0.19 at 2×), disclose the expansion counts and the guard, and cite the compute-matched-baseline precedent. Paid for by the 84 abstract cuts.
- **One trained second policy through the instrument:** a one-seed InternVL3.5 cell on the validation panel and P2, about 7-9 GPU-h per cell by the #141 protocol's own estimate. That would show M1 plus the ladder orders two trained choosers. The 30 GPU-h ticket cap that ruled it out is self-imposed.

The single most value-changing addition is a modality contrast under the choice-frontier contract, for example a text-rendered menu against the scene-only observation with the same recipe. The title's "vision-language" framing currently has no choice-frontier evidence behind it.

The MINOR items (82-84 and the 75 and 80 remainders) are cheap and space-neutral. None changes the rating on its own.

## Live fixlist — review 20 (2026-09-25)

**Verdict:** WEAK REJECT. 0 CRITICAL, 2 MAJOR, 10 MINOR.
- MAJOR: findings 69 (Axis 1, value cash-out) and 70 (Axis 4, the screen interpretation contradicts the paper's own P2u ladder).
- MINOR: findings 71-80.
- Fix class: MEANING for 69, 70, and 71. WORDING for the other nine.
- Finding 40 (LLM-usage statement) is WONTFIX by author decision. It is reported below as a compliance risk and is outside the rating and the finding count.

Most damaging issue: **finding 69**. The paper states that the identity failure "is shown only on our runtime" and that "The contribution is therefore the measurement" (Discussion p.8 L406-408). On the one published interface audited (ScienceWorld), random-valid already registers choice. The validated instrument ranks exactly one realisable, non-trivial policy, which is the authors' own imitation adapter. Everything else it ranks is a privileged rung, a rule selector at or below random-valid, or the authors' first adapter. The update a reader can take away and reuse (when to run the audit, what to report, what changes in practice) is never stated as a falsifiable rule.

Genre: BENCHMARK (+ FINDINGS)

Δbelief: On the authors' additive best-first runtime, random-valid is decision-identical to the exact reference (48/48) under the executed sorted-serial rule, and 19/48 pairs diverge under submission-order serials, so the per-decision check can return either verdict. A redesigned choice-frontier contract passes a pre-registered exact-ε ladder test on a validation panel and on a screened held-out panel (and descriptively on an unscreened one). An imitation-trained VLM adapter beats uniform frontier choice across three seeds (D3 +0.285, held-out +0.416, unscreened +0.149) but is interval-separated above the ε-0.75 rung only on the held-out panel. A skimming reviewer comes away believing "check random-valid per decision before reading its success as choice", and that belief is anchored only in the authors' own runtime.

Ledger: Verified: 49 and 60 (closed with #134), #137 reframe, review-16 finding 15, 51, 52, 53 (remainder), 56 (remainder), 66, 67, 68 · Partial: none · Regressed: none · Not addressed: none · Wontfix: 40 (unchanged, App Y p.34 L1825) · New: 69-80

**Reviewer summary:**

> This round 5 re-review covers HEAD `0277de7` on a clean tree. It covers rounds 4 and 5 (`59e8714` … `0277de7`), which no reviewer had seen: #134-#137, and then #138-#140. I read all 35 pages of the rendered PDF text, both figure PNGs, both figure scripts, the log and blg, the new appendix subsections and their `%` comments, and the protocols and closeouts for #138-#140.
>
> The build is clean. The Conclusion ends on p.8, so the main text is 8 pages against the 9-page limit.
>
> I re-derived every round-5 number directly from the pinned JSONs and ledgers, not from any evidence sheet. That covers the headline set, all cells of Tables 19-21, both ledger attempt sums, the #134 counterfactual (19/48, divergence at decisions 2-50 with median 6, the ferry goal flip), ScienceWorld (1000/1000, 0.915 against 0), and the 1.79 GPU-h cancelled collection. Every number matches its artifact. Re-running the 28 `fig_ladder.py` asserts read-only against the JSONs gives 28/28 pass.
>
> I checked 16 evidence comments, 13 of them from round 5. All paths exist and every key and value resolves. One protocol line pointer is off by one (finding 80).
>
> The claim discipline from Phase 0 largely holds. Three seeds, single-seed DAgger, held-out meaning P2 only, P2 described as screened, three-part ladder-position statements, the privileged rungs, the failed #134 prediction, and both A1 disclosures are all in place.
>
> The problems are now about interpretation and value, not numbers:
> - The paper reads P2u as showing that "the screen enriches for tasks on which choice discriminates". Its own P2u ladder shows the opposite: choice discriminates at least as strongly on P2u (70).
> - "Sits at that rung" is an equivalence reading that the Statistics appendix itself forbids (71).
> - The DAgger ablation is called inconclusive and, in the same sentence, "does not change measured choice quality" (72).
> - The value anchor no longer rests on a flawed claim, but it still has no portable cash-out (69).

### Rating

**Rating: 4** (ICLR 2026 scale {0, 2, 4, 6, 8, 10}; 4 = marginally below the acceptance threshold)

- **Soundness: 3** (good). Pre-registration is used throughout. Every number is replay-verified and traces to a pinned artifact. The intervals are paired and task-clustered, and the paper uses 3 seeds and a held-out panel. Two things cap soundness: the interpretation of the screen (70), and a headline separation that rests on an 11-cluster percentile bootstrap (77).
- **Presentation: 2** (fair). The paper is honest and precise, but a first-time reader struggles:
  - M1 and D3 appear in the abstract undefined.
  - The appendix apparatus runs to 26 lettered appendices and 35 pages.
  - The main text is dense with contract, panel, and ledger jargon.
  - Several appendix cross-reference ranges are stale.
- **Contribution: 2** (fair). The per-decision identity audit is a clean, cheap methodological check, and the ladder-validated choice measurement is well constructed. The failure the audit exposes is shown only on the authors' own runtime, though, and the learned result is modest: the adapter is at or below the ε-0.75 rung on two of three panels and pooled.
- **Confidence: 4.** I verified the numbers against the artifacts myself. Published-practice anchors were checked against the ICLR 2026 LLM policy and Semantic Scholar entries (URLs below).

**Strongest reasons for acceptance:**
- The evaluation discipline is exemplary for the area. Protocols were frozen before outcomes, amendments were disclosed as made before evaluation, and every episode was independently replayed.
- A cheap diagnostic returns both verdicts on one runtime (48/48 identical against 19/48 divergent). It is paired with an external anchor on ScienceWorld and a seven-interface survey.
- The choice-frontier measurement is validated by a pre-registered monotone exact-ε ladder, and the ladder replicates on a held-out panel (smallest gap +0.130 [+0.070, +0.190]).
- The adapter result holds across three seeds and replicates on held-out P2 (+0.416 [+0.250, +0.591]). The paper reports its own failures prominently: the #134 prediction failed, P2u is weaker, DAgger is inconclusive.

**Strongest reasons against acceptance:**
- (i) The value anchor is internal. The complete-set contract "was not found among the surveyed published interfaces", and on the audited published interface random-valid already measures choice, so in published practice the audit confirms the status quo (69).
- (ii) The learned result is small and fragile:
  - Its advantage over uniform choice shrinks to +0.149 [+0.030, +0.283] without the screen, and 8 of 12 unscreened tasks are unsolved by both arms.
  - It is interval-separated above the ε-0.75 rung only on the 11-task P2. There, 3 of 11 per-task differences are negative and an exact sign-flip test gives p = 0.046 (reviewer computation, 77).
  - It uses one backbone, and every panel has 11-12 tasks.
- (iii) All enumeration-contract learned results are null or below random-valid (125/288 against 240/288; 0/24 in every BFS and BFWS cell). The "vision-language" framing therefore rests on a single visual-only choice-frontier adapter with no modality comparison under that contract.
- (iv) The screening interpretation that answers the obvious reviewer concern is contradicted by the paper's own P2u ladder (70).

**What would move the rating up one step (4 → 6):**
1. **(69)** Push a second realisable policy family through the validated instrument on the validation panel and P2. Cheap options, all feasible on the existing v4 controls and ladder without new panels:
   - the InternVL3.5-8B backbone trained with the frozen #138 recipe (3 seeds);
   - a zero-shot scene-only prompt of the base Qwen3-VL-8B with a relaxed call cap;
   - the h_add-free novelty or width selector re-expressed as a realisable scene-only rule.

   This would show that M1 ranks independent policies, which is what "a validated search-choice measurement" promises. Then state the portable rule: run the audit, and report D with ladder position.
2. **(70)** Replace the "screen enriches for tasks on which choice discriminates" reading with the defensible one: the screen selects tasks where near-uniform choice sometimes succeeds. Back it with one descriptive analysis, either the P2−P2u difference with an interval or D3 regressed on the random-valid screen rate across the 35 tasks.
3. **(77)** Report a small-cluster-robust check (exact sign-flip or cluster-t) for every "interval-separated" statement.
4. Optionally, the single most value-changing experiment: run the per-decision audit on the one surveyed interface predicted to saturate (LLM-First Search, type C). A published interface on which random-valid matches the reference would convert the internal anchor into a published-practice finding and address (i) directly.

**Finding 40 (compliance risk, outside the rating and the count):** App Y p.34 L1825 (appendix.tex L1452) reads "An LLM was used only for polishing language; the scientific content is entirely original."
- ICLR 2026 policy says "Any use of an LLM must be disclosed" and asks authors to "explicitly state how they used LLMs in their submission". It names "drafting entire paper sections" and use "as a research assistant" (analysis, code) as uses to disclose, and names desk rejection as a possible consequence (https://blog.iclr.cc/2025/08/26/policies-on-large-language-model-usage-at-iclr-2026/, fetched 2026-09-25).
- `manuscript/changelog.md` records LLM agents drafting sections, figures, and citation passes (for example "paper-writer", "related-work-scout", "figure-only paper-writer" in round 5 waves 1-3).
- If those agents are LLMs, the statement "only for polishing language" understates the use, and the risk is a Code-of-Ethics misrepresentation finding, not just an incomplete disclosure.
- Not re-argued: WONTFIX per the Phase 0 decision (changelog round 5 Phase 0 item 8).

### Build, page count, figures

- **Build:** `iclr2026_conference.log` (2026-09-25 01:42:58) and `.blg` (01:42:57) are newer than every source. The newest sources are results.tex at 01:41:19 and fig_ladder.png/svg at 01:36:56. Counts:
  - `^!` errors: 0
  - LaTeX and package warnings: 0
  - "undefined" (references or citations): 0
  - Overfull: 0 (51 underfull)
  - BibTeX `warning$`: 0 across six databases
  - `\bibitem`s: 43
  - "Output written on iclr2026_conference.pdf (35 pages, 441637 bytes)"

  `manuscript/manuscript.pdf` (514,897 bytes) is not byte-identical to `iclr2026/iclr2026_conference.pdf`, but both have 35 pages. Their `pdftotext -layout` output differs only in column whitespace in Table 6, so the text reviewed is the same. **PASS.**
- **Page count:** The Conclusion ends on **PDF p.8, L431**. The Reproducibility Statement and References begin on p.9 (L432). Main text, title through Conclusion, is **8 pages** against the 9-page limit. **PASS**, with one page of slack. That slack is room for the fixes to 69, 70, and 76.
- **fig:ladder (Figure 2, p.6 L270-284; `figures/fig_ladder.png`, 1791×623):**
  - Three panels: "Validation (12 tasks)", "Held-out P2 (11 tasks)", and "Unscreened P2u (12 tasks)".
  - Each panel shows the five ladder arms with task-clustered intervals, a dotted line at that panel's own ε-0.75 value (0.347, 0.205, 0.149), and the 3-seed adapter mean (0.306, 0.432, 0.151) with faint per-seed points. The first adapter (0.026) appears on the validation panel only.
  - Labels are legible and there is no clipping or overlap.
  - `fig_ladder.py` L45-92 holds **28 assert statements**: per panel, 6 (m, lo, hi) triples and 3 per-seed M1 values, plus the first adapter. They read `v4/panels/metrics/analysis.json arms.{p135,p2,p2u}.*` and `v2/metrics/analysis.json adapter_reevaluation.learned_adapter.{m1_auc, m1_task_cluster_95pct_ci_10000_seed133}`. I re-executed exactly these comparisons in a throwaway script against the pinned JSONs, without writing the figure: **28/28 pass.**
  - Content defects: the caption omits the "descriptive" status of the P2u ladder, and it does not mention the first-adapter row (finding 78). The P2u panel title reproduces the "Unscreened" label that finding 70 questions.
- **fig:contracts (Figure 1, p.5 L216-232):**
  - `fig_contracts.py` L31-63 reads 48/48 (`native-arms/v1/identity-audit.json`); 19/48 (`identity-audit-submission-order.json rules.submission_order.pairs_divergent`, asserted == (19, 48)); +0.000 over 24 tasks (`synthesis-v1/baseline-contrasts.csv`, 6 additive rows asserted 0.0); 18/18 and 9 tasks (`choice-frontier/v1/evaluation/identity-audit.json`); and −0.644 [−0.856, −0.422] (`v1/evaluation/analysis.json contrasts.random_valid_minus_exact_reference`). All match; I re-read the values from the JSONs and CSV this round.
  - The PNG renders cleanly. "Sorted-serial frontier (order-invariant)" is accurate for the executed rule.
  - The caption states that the panels differ ("on a separate 9-task panel with its own uniform-menu control"). The review-19 finding 66 fix holds.
  - Figure 1 is still a pipeline-plus-numbers schematic. Its (b) panel reports the 9-task first measurement, not the ladder-validated result, so the belief-carrying picture of the adapter result is Figure 2. This is noted, not ranked.
- **fig:zoo-m1 (Figure 3, App R p.29):** unchanged since review 19.

### Numbers re-check

The pinned artifacts are git-ignored (`.gitignore:285 outputs/`), so I identify them by mtime and md5 prefix. The last evidence commit is `3996600` (2026-09-24 23:30, #140 closeout).

| artifact | mtime | md5 prefix |
|---|---|---|
| v4/seeds/metrics/analysis.json | 2026-09-24 15:42 | d5c3828cba0f |
| v4/panels/metrics/analysis.json | 18:47 | fa5399d9a0f6 |
| v5/metrics/analysis.json | 23:29 | 29d08e8bcbea |
| v4/budget.json | — | c58180f1c1c7 |
| v5/budget.json | — | 178f3023fc53 |
| v2/metrics/analysis.json | — | c609286a7e3f |
| native-arms/v1/identity-audit-submission-order.json | — | 6f523484d3d0 |
| external-audit/v1/scienceworld/identity-audit.json | — | 83d4265671a7 |

All paths are under `outputs/choice-frontier/` except the last two. A = `outputs/choice-frontier/`.

| claim (rendered) | PDF location | artifact : key | match |
|---|---|---|---|
| 0.875 / 0.793 / 0.603 / 0.347 / 0.021 | p.1 L020-022, p.2 L057-058, p.6 L292-294, Fig. 2, Tables 17 and 19 | A/v4/panels arms.p135.{exact_reference, exact-eps-0.25, -0.50, -0.75, random_valid}.m1 = 0.875, 0.79271, 0.60313, 0.34688, 0.02083 (same in A/v2 arms, A/v4/seeds controls_135) | yes |
| smallest gap +0.082 [+0.051, +0.111]; other gaps +0.190 [+0.126, +0.252], +0.256 [+0.184, +0.339], +0.326 [+0.233, +0.422] | p.1 L022-023, p.2 L059, p.6 L295, App T p.30 L1598-1600 | A/v2/metrics instrument_validity.pairs[0..3].{difference, ci95} = 0.08229 [0.05104, 0.11146]; 0.18958 [0.12604, 0.25208]; 0.25625 [0.18438, 0.33854]; 0.32604 [0.23333, 0.42187]; verdict PASS | yes |
| D3 +0.285 [+0.140, +0.433]; per seed +0.328 / +0.229 / +0.297 | p.1 L025, p.2 L063, p.6 L309-310, p.8 L426, Tables 18 and 20 | A/v4/seeds primary.D3 0.28472, ci95 [0.14028, 0.43264], per_seed.{17,29,71} 0.32813 / 0.22917 / 0.29688, verdict POSITIVE | yes |
| per-seed D intervals [+0.155, +0.508], [+0.108, +0.354], [+0.134, +0.466]; per-seed M1 0.349 / 0.250 / 0.318; SD 0.051; per-seed S +0.002 / −0.097 / −0.029 | App U p.31 L1656-1659 | A/v4/seeds primary.per_seed_ci95.*; seed_variance.m1_per_seed.*.m1_auc; seed_variance.m1_between_seed_sd 0.05059; separation.vs_eps_0.75.per_seed.* 0.00208 / −0.09687 / −0.02917 | yes |
| P2 D3 +0.416 [+0.250, +0.591]; per seed +0.490 / +0.268 / +0.490 | p.1 L026, p.2 L064-065, p.6 L311-313, p.8 L426-427 | A/v4/panels heldout_p2.primary.D3 0.41591, ci95 [0.25038, 0.59091], per_seed 0.48977 / 0.26818 / 0.48977, verdict POSITIVE, tasks 11 | yes |
| P2u D3 +0.149 [+0.030, +0.283] | p.1 L027, p.2 L068, p.6 L323 | A/v4/panels unscreened_p2u.primary.D3 0.14896, ci95 [0.02951, 0.28299], verdict POSITIVE (status "primary endpoint confirmatory") | yes |
| S vs ε-0.75, validation −0.041 [−0.187, +0.102] | p.1 L029, p.2 L066, p.6 L319, p.8 L428 | A/v4/seeds separation.vs_eps_0.75.S −0.04132, ci95 [−0.18681, 0.10174], NOT_SEPARATED (co-primary) | yes |
| S vs ε-0.50, validation −0.298 [−0.468, −0.129], descriptive | p.6 L319-320, App U p.31 L1660 | A/v4/seeds separation.vs_eps_0.50.S −0.29757, ci95 [−0.46840, −0.12882], role "descriptive only", SEPARATED_BELOW | yes |
| S vs ε-0.75, P2 +0.227 [+0.053, +0.403] | p.1 L028, p.2 L065-066, p.6 L320, p.8 L427 | A/v4/panels heldout_p2.separation.vs_eps_0.75.S 0.22727, ci95 [0.05265, 0.40265], SEPARATED_ABOVE; per_seed.29 0.07955 (+0.080 at p.32 L1713) | yes |
| S vs ε-0.75, P2u +0.002 [−0.145, +0.157] | p.6 L321 | A/v4/panels unscreened_p2u.separation.vs_eps_0.75.S 0.00208, ci95 [−0.14549, 0.15729], NOT_SEPARATED | yes |
| pooled S +0.058 [−0.040, +0.156] over 35 tasks | p.1 L030, p.2 L067, p.6 L321, p.8 L429 | A/v4/panels pooled.separation_vs_eps_0.75.S 0.05798, ci95 [−0.03952, 0.15643], pooled.tasks 35, status descriptive | yes |
| 22 of 35 positive / 12 zero / 1 negative | p.7 L327-328, p.32 L1715-1716, Table 21 | A/v4/panels concentration.all_36_counts {positive 22, zero 12, negative 1}. The key says 36 but the counts sum to 35; the source comment at results.tex L147 records this | yes |
| per-panel 9/2/1, 9/2/0, 4/8/0 | Table 21 p.33 | concentration.per_panel.{p135,p2,p2u}.counts; sign of primary.per_task_difference_seed_mean on p135 (1 negative: 15puzzle −0.0625; zeros: blocksworld-935001, ToH-935002) | yes |
| leave-one-domain-out +0.305 to +0.395, lower bounds ≥ +0.185 | p.7 L328-329, p.32 L1718 | concentration.leave_one_domain_out_p2_union_p135.* D3 min 0.30479 (elevators, lo 0.18542), max 0.39539 (blocksworld) | yes |
| 8 of 12 P2u tasks unsolved by both arms (the two 15-puzzle, blocksworld, depot, and driverlog tasks) | p.6 L323-324, p.32 L1716-1717 | unscreened_p2u.primary.per_task_difference = 0.0 on exactly those 8 tasks; issue-139-closeout.md L73 | yes |
| P2 ladder smallest gap +0.130 [+0.070, +0.190]; others +0.239 [+0.183, +0.290], +0.302 [+0.259, +0.340], +0.189 [+0.136, +0.248] | p.6 L301-302, p.32 L1706-1708 | ladder_p2.pairs[0..3] 0.12955 [0.07045, 0.18977]; 0.23864 [0.18295, 0.28977]; 0.30227 [0.25909, 0.33977]; 0.18864 [0.13636, 0.24773]; verdict PASS, status confirmatory | yes |
| P2u ladder +0.197 [+0.154, +0.243], +0.281 [+0.191, +0.355], +0.248 [+0.209, +0.290], +0.147 [+0.088, +0.226] | p.32 L1708-1710 | unscreened_p2u.ladder.pairs[0..3] 0.19688 [0.15417, 0.24271]; 0.28125 [0.19063, 0.35521]; 0.24792 [0.20938, 0.28958]; 0.14688 [0.08750…01, 0.22604]; PASS | yes (half-up 3 dp) |
| #140 S_pool +0.115 [−0.026, +0.258]; Δ −0.030 [−0.114, +0.057] | p.7 L338, p.33 L1758-1759 | A/v5 primary.S_pool 0.11522, ci95 [−0.02554, 0.25761], NOT_SEPARATED, tasks 23; co_primary.delta_pool −0.02989, ci95 [−0.11413, 0.05707], INCONCLUSIVE, equivalence_margin 0.05 | yes |
| #140 per panel S +0.278 [+0.082, +0.473] (P2), −0.034 [−0.197, +0.135] (validation) | p.33 L1760 | A/v5 per_panel.p2.{S 0.27841, S_ci95 [0.08182, 0.47273]}; per_panel.v2.{S −0.03437, S_ci95 [−0.19687, 0.13542]} | yes |
| last-label 0.205 → 0.137 (validation panel) | p.33 L1761 | A/v5 per_seed.v2.17.pre_dagger.last_label_rate 0.20550 → per_seed.v2.17.dagger.last_label_rate 0.13706 | yes |
| last-label per seed 0.205 / 0.192 / 0.171 against 30.0% | p.6 L314-315 | A/v4/seeds seed_variance.last_label_rate_per_seed 0.20550 / 0.19172 / 0.17118; A/v2 adapter_reevaluation.learned_adapter.m4_teacher_agreement.selected_last_rate 0.29975 (238/794, chance 0.144) | yes (presentation: finding 75) |
| first adapter M1 0.026 [0.010, 0.042] | p.6 L314, Tables 17 and 19, Fig. 2 | A/v2 adapter_reevaluation.learned_adapter.m1_auc 0.02604, CI [0.01042, 0.04167] | yes |
| ledgers 15.22/24 and 9.06/40; 1.79 GPU-h cancelled | p.5 L253, p.16 L833-835 and L852-854 | Σ attempts[].gpu_hours: A/v4/budget.json 15.22252 (14 attempts, allocations 24.0); A/v5/budget.json 9.06403 (11 attempts, allocations 40.0); v5 failed cfv5-collect-*-s29 0.89741 + 0.89728 = 1.79468 | yes |
| 48/48 identical; 19/48 divergent; prediction failed; first divergence at decisions 2-50 (median 6); 29 identical; one ferry task flips under both algorithms | p.1 L016-018, p.1 L052-p.2 L054, p.5 L261-269, App S p.29, Table 14 | native-arms/v1/identity-audit.json pairs_identical 48/48; identity-audit-submission-order.json rules.submission_order {identical 29, divergent 19}, preregistered_prediction.held false, verdict "PREDICTION_FAILED: see preregistered_prediction"; first_divergence_decision_index over the 19 divergent pairs: min 2, max 50, median 6; goal flip only on ferry-expanded-915109 (greedy and w3); validation 288 counts + 96 sequences, mismatches [] | yes |
| 18/18 divergent, 9 tasks; −0.644 [−0.856, −0.422] | Fig. 1, p.5 L269, p.6 L290-291 | A/v1/evaluation/identity-audit.json pairs_divergent 18/18, CHOICE_SENSITIVE; analysis.json contrasts.random_valid_minus_exact_reference −0.64444 [−0.85556, −0.42222] | yes |
| ScienceWorld 1000/1000 first-decision divergence; 0.915 against 0; 200 tasks; 6 of 30 task types | p.1 L031-032, p.2 L070-072, p.7 L343-345, App V p.33 | external-audit/v1/scienceworld/identity-audit.json pairs_divergent 1000/1000, first_divergence_index {min 0, median 0, max 0}, success.reference 0.915, random_valid_mean 0.0 (5 seeds all 0.0), tasks 200, verdict CHOICE_REGISTERED | yes |
| Table 2 v4 row: 48/48 new learned episodes, 638/638 P2 and 696/696 P2u zoo episodes | p.16 L833-834 | A/v4/seeds episode_accounting.v4_replayed 48; issue-139-closeout.md L113-115 (11×58, 12×58, 0 missing) | yes (row omits the P2/P2u learned-episode replays 88/88 and 96/96, closeout L123: finding 74) |
| **Table 19** (tab:appendix-panel-arms), all 99 values: 11 arms × 3 panels × (M1, lo, hi) | p.32 L1677-1684 | A/v4/panels arms.{p135,p2,p2u}.{exact_reference, exact-eps-0.25/0.50/0.75, random_valid, pretrained_base, learned_adapter_s17/s29/s71, learned_adapter_seed_mean, hadd-greedy}.{m1, ci95}, checked cell by cell at 3 dp (for example P2 s29 0.284 [0.119, 0.489]; P2u mean 0.151 [0.030, 0.288]; P2 hadd-greedy 0.928 [0.883, 0.966]) | yes, all 99 |
| **Table 20** (tab:appendix-seed-d), all values and verdicts: D per seed (4 panels × 3 seeds with intervals), D3 (4 panels), S vs 0.75 (4), S vs 0.50 (3), and the pre-reg./descriptive labels | p.32 L1689-1695 | validation: A/v4/seeds primary.* and separation.*; P2: heldout_p2.primary.*, .separation.vs_eps_0.75/0.50.*; P2u: unscreened_p2u.primary.*, .separation.*; pooled: pooled.primary.* (per seed +0.334 [+0.223, +0.450], +0.203 [+0.124, +0.290], +0.301 [+0.200, +0.411]; D3 +0.279 [+0.191, +0.375]), pooled.separation_vs_eps_0.75.*. Labels match the status fields: P2u primary "confirmatory" → "POSITIVE (pre-reg.)", its separation "descriptive", pooled "descriptive" | yes, all |
| **Table 21** (tab:appendix-concentration): 12 counts and 9 domains × (D3, lo, hi, tasks left) | p.33 L1731-1740 | concentration.per_panel.*.counts; leave_one_domain_out_p2_union_p135.{15puzzle … visitall}.{D3, ci95, tasks_left}. For example ferry 0.33095 [0.21151, 0.45456] 21; visitall 0.31780 [0.21117, 0.42197] 22. Depot D3 is 0.3525 exactly and is printed +0.353 (half-up; Python's float round gives 0.352) | yes, all 48 (rounding convention noted) |

**Reviewer-computed checks** (not paper claims; used in findings 70 and 77):
- P2 per-task S vs ε-0.75 (heldout_p2.separation.vs_eps_0.75.per_task_difference): 8 positive and 3 negative of 11. An exact two-sided sign-flip permutation gives p = 0.046 (2^11 flips), and a cluster t-statistic gives 2.36.
- Exact reference minus random-valid M1: P2 0.859 (0.875 − 0.016), P2u 0.873 (0.875 − 0.002).
- ε-0.75 minus random-valid: P2 +0.189, P2u +0.147.
- P2u tasks: all 12 have 0/10 random-valid screening goals (issue-139-closeout.md L56).

### Evidence-comment spot-check

I sampled 16 comments, 13 of them from round 5. For each I checked that the path exists and that the key and value, or the line reference, match. 15 resolve and 1 is off by one.

1. results.tex L41-42 (5.1 ledgers): `issue-139-closeout.md` L144 "Shared v4 ledger total: 15.22 / 24 GPU-h" ✓; `issue-140-closeout.md` L72 "Total 9.06 / 40 GPU-h." ✓; both budget.json sums ✓ (above).
2. results.tex L98-100 (P2 ladder, A1): `pooled.panels.p2` 11 ✓; `ladder_p2.pairs[0]` 0.1295 [0.0705, 0.1898] ✓; `issue-139-protocol.md` L93 is the ladder rule ✓, L96 is the P2u descriptive ladder ✓, and L118-127 is A1 with the seeds at L122 ✓; closeout L58 has the first freeze at 6 tasks from 5 domains ✓.
3. results.tex L122-123 (replication provenance): `issue-138-protocol.md` L11 "the #136 recipe, byte-identical" ✓; `issue-138-closeout.md` L5 `f06c7ac` ✓. The quoted "Only training_seed changes" paraphrases L11-12; the text is not verbatim, but the meaning holds.
4. results.tex L124-125 (D3): primary.* values ✓; rule `issue-138-protocol.md` L31-41 ✓ (POSITIVE rule at L39).
5. results.tex L130-131 (last-label): seed_variance.last_label_rate_per_seed ✓; v2 selected_last_rate 0.2997 ✓.
6. results.tex L135 (P2u construction): `pooled.panels.p2u` 12 ✓; P2u rule at protocol L55-57 ✓ (L56 "Admit iff exact reaches the goal …").
7. results.tex L136-140 (ladder position): the five S values and intervals ✓; P139 L95 SEPARATED_ABOVE rule ✓.
8. results.tex L144-145 (P2u D3, zero 8): unscreened_p2u.primary.* ✓; per_panel.p2u.counts.zero 8 ✓; closeout L73 ✓, L11 ✓.
9. results.tex L146-147 (`all_36_counts` note): key and values ✓; closeout L28 "The union has 35 tasks, not the 36 …" ✓.
10. results.tex L148-149 (leave-one-domain-out): elevators 0.3048 / lo 0.1854 ✓; blocksworld 0.3954 ✓; "every other domain's lower bound ≥ 0.204" ✓ (grid 0.20396 is the next smallest).
11. results.tex L160-161 (DAgger): primary.* ✓. **"half corpus per issue-140-protocol.md L124 (A1 item 2)" is off by one.** L124 is A1 item 3 ("Evaluation: …"), and item 2 (the first 512 + 512) is at L123. See finding 80.
12. appendix.tex (U.1 construction, before L1212): P2 rule at protocol L7, L36, L48-50 ✓; candidate pool at closeout L46-54 (2,400; 1,168 / 205 / 31 / 536; 460) ✓; "All 12 happen to have 0/10 random goals." at closeout L56 ✓; zoo replay at closeout L113-115 ✓.
13. appendix.tex (A1 paragraph): protocol L120 trigger ✓, L122 seeds ✓, L123 unchanged ✓; closeout L5-6 `d567939` ✓.
14. appendix.tex (Table 19 and the gaps): the eight `ladder_p2` and `unscreened_p2u.ladder` pairs ✓; `arms.{p135,p2,p2u}.*` ✓. This comment and the Table 20 comment also cite "3-dp renderings per local evidence-r5.md", a sheet that is not in either repository (finding 80). The primary artifact keys are named and resolve.
15. appendix.tex (Table 20): P138 L44-52 (separation co-primary, 0.50 descriptive at L51-52) ✓; closeout L30 (P2 vs ε-0.50 descriptive) ✓; closeout L171 "Seed 29 is weaker … +0.080" ✓.
16. appendix.tex (DAgger A1, before L1341): protocol L118 heading 11:21 UTC ✓, L120 deadline ✓, L122 s29 cancelled ✓; **L124 cited for "first 512 + 512" is off by one (item 2 is L123)**; closeout L80 "1.79 GPU-h charged" ✓; closeout L53 replay 24/24 and 22/22 ✓.

### Verification of round-4 closures

| item | r20 result | evidence at `0277de7` |
|---|---|---|
| 49 (value anchor / same-runtime counterfactual, closed with #134) | **VERIFIED** | 5.2 p.5 L265-269 (results.tex L64): "On the same runtime with heap serials assigned in submission order, the same check finds 19/48 divergent pairs, so the check can return either verdict. The pre-registered prediction of divergence on most pairs (more than 24/48) did not hold." Contribution 1 p.2 L078 "A per-decision identity audit that returns both verdicts on one runtime." Figure 1(a) shows "submission-order serials: 19/48 divergent". App S p.29 L1565 "The 48/48 identity is therefore a property of the executed serial rule, not of the enumeration contract alone." The numbers match (table above). The remaining value question is a different issue (69). |
| 60 (M4 intervals, closed with #134) | **VERIFIED** | Table 15 p.30 L1567-1569 gives task-clustered intervals: heap-head −0.069 [−0.161, +0.032] and last-label +0.277 [+0.126, +0.402]. App R p.28 L1509-1511 reads "Decisions cluster within 9 tasks, and the task-clustered intervals … show that the agreement gap does not survive that clustering while the last-label excess does". 5.4 p.7 L330-333 labels it post-hoc. |
| #137 reframe (identity failure shown only on our runtime; the contribution is the measurement) | **VERIFIED** | Abstract p.1 L032-034, Intro p.2 L072-074, 5.5 p.7 L345-347, and Discussion p.8 L406-408 (discussion.tex L20): "None of the seven published interfaces we surveyed uses a complete-set submission contract, so the identity failure is shown only on our runtime. The contribution is therefore the measurement, not the exposure of a common flaw." |
| Review-16 finding 15 (admissible-action positioning sentence) | **VERIFIED (present)** | Related Work p.3 L122-124 (related_work.tex L18): "This paper operationalizes the known admissible-action handicap in search-execution evaluation with a per-decision identity audit that returns both verdicts on one runtime and anchors the validated choice measurement of Section 5." |
| 51 hedge (menu probe) | **VERIFIED** | Related Work p.3 L120-122: "The menu manipulations in this paper probe this interface, and only the unrun fixed-versus-random-position variant would separate surface-following from state grounding." App P p.26 L1394-1395: "Content-reading and position habits both predict a pick-rate near 0.6, so this receipt does not separate them, and the discriminating fixed-versus-random-position test remains unrun." |
| 52 hedge (no equivalence, no position habit) | **VERIFIED** | App R p.28 L1490 "with no last-label comparator and no equivalence claim". p.29 L1544-1545 "no last-label comparator was run, so these post-hoc rates do not establish a position habit". The only other "habit" occurrence (p.26 L1394) is hedged. The Conclusion no longer carries the zoo sentence, so the hedge cannot regress there. |
| 53, 56, 66, 67, 68 (review-19 remainders, closed `c08ef50`) | **VERIFIED** | 56: Section 3 p.3 L142-143 "(schemas in the Operation Schemas appendix, Appendix A, invariants in the Algorithm Invariant Definitions appendix)". 66: Figure 1 uses "pairs" with task counts, (a) shows +0.000, and the caption names the separate 9-task panel. 67: the abstract's final sentence is replaced (p.1 L034-036). 68: Related Work p.2 L107-p.3 L108 now reads "…(Zhu et al., 2020), and video-language evaluation reports selection bias toward answer positions (Loginova et al., 2025)". 53: see the spot-check. |
| 40 (LLM-usage statement) | WONTFIX (unchanged) | App Y p.34 L1825, appendix.tex L1452. Compliance risk is reported above, outside the rating. |

### Placeholder and claim-discipline check

- **Visible `[TODO`:** `grep -n 'TODO'` over the rendered text returns 0 hits. **PASS.**
- **3 seeds:** abstract p.1 L025 and L035, Intro p.2 L062 and L085, 5.1 p.5 L238, 5.4 p.6 L309, Conclusion p.8 L426 and L431, Design p.3 L155-156. **PASS.**
- **DAgger single seed stated:** 5.4 p.7 L336-337 "run for one seed on half the planned corpus", App U.2 p.33 L1751-1756, App W p.34 L1806. **PASS.** The DAgger conclusion wording is finding 72.
- **Held-out = P2 only:** Intro p.2 L086-088, 5.4 p.7 L325-327, Design p.4 L205 "held-out refers to P2 only". The frozen 45-task manifest is "unexecuted" at p.5 L239, p.7 L375-376, and p.8 L416. **PASS.** The phrase "no design decision … had seen" is finding 73.
- **P2 described as screened:** 5.3 p.6 L298-299 "P2 applies the validation panel's generation, cost, and screening rules", Limitations p.8 L413 "P2 is screened like the validation panel". **PASS.**
- **P2's ladder position never reported alone:** every separation statement carries all three panels plus pooled. This holds in the abstract (p.1 L027-030), Intro (p.2 L065-068), 5.4 (p.6 L318-321), Discussion (p.8 L398-400), Limitations (p.8 L411-412), and Conclusion (p.8 L427-430). App U.2's +0.278 on P2 is paired with −0.034 on the validation panel. **PASS.**
- **Descriptive or post-hoc labels:**
  - ε-0.50 separation: "descriptive" (p.6 L320). PASS.
  - P2u separation: "descriptive" (p.6 L321). PASS.
  - P2u ladder: "which is descriptive" (p.6 L302). **Missing from the Figure 2 caption** (p.6 L282-284), which plots it without the label (finding 78).
  - Pooled: "descriptive" (p.1 L030, p.6 L321). PASS.
  - Concentration: "(descriptive)" (p.7 L328-329). PASS.
  - The P2u screen interpretation is stated as fact with no label (finding 70).
- **No equivalence claim without margin:** **FAIL, twice.**
  - "sits at that rung" (p.1 L028, p.2 L066, p.8 L399 and L428) and "at the 0.75 rung on the validation panel" (p.6 L318-319) apply to S, which has no pre-registered equivalence margin. This contradicts the paper's own Statistics appendix, p.18 L933 "a non-separated S is not equivalence to the rung" (finding 71).
  - "does not change measured choice quality" (p.33 L1762) describes a co-primary that is INCONCLUSIVE against a ±0.05 margin (finding 72).
- **No planning-ability claim:** every claim frame ends "carries no planning-ability or generality claim" (p.1 L036, p.2 L085-086, p.7 L336, p.8 L404 and L431). App R p.28 L1473 reads "no learning-to-plan claim". **PASS.**
- **No expansion parity:** there is no parity claim. **PASS.**
- **Old and new contract not compared as performance rows:** Table 23 caption "Results under the two contracts are not comparable as performance rows". Table 12 caption "Not comparable with enumeration-contract rows". Figure 1 juxtaposes identity counts and each contract's own random-valid − exact contrast, with the separate panel stated. **PASS.**
- **Ladder rungs privileged:** abstract p.1 L023-024, Intro p.2 L060-061, 5.3 p.6 L304-305, Figure 2 caption, Table 19 caption, Discussion p.8 L393-394. **PASS.**
- **#134 prediction reported as failed:** abstract p.1 L018 "the pre-registered majority prediction failed", Intro p.2 L054, 5.2 p.5 L266-267, App S p.29 L1562-1563, Limitations p.8 L417. **PASS.**
- **Amendments disclosed as made before evaluation:** #139 A1 in 5.3 p.6 L299-301 ("an amendment made before any evaluation episode") and App U.1 p.32 L1699-1705. #140 A1 in App U.2 p.33 L1751 ("decided before any DAgger training or evaluation outcome"). **PASS.**

### New findings

**Axis and genre coverage** (everything not listed as a finding passes or is n/a):
- **Axis 1:** the 10-minute test delivers an update (Δbelief above), and Figure 2 carries the three-panel tension. The value cash-out is finding 69.
- **Axis 2:** falsifiability passes. Each follow-up has a pre-registered verdict rule, and two could have lost and one did (#134 PREDICTION_FAILED; DAgger NOT_SEPARATED and INCONCLUSIVE).
  - HARKing scan: 9 bare-fact interpretive claims between the Intro promise and an earned verdict. The three most damaging are "so the random-control screen enriches for tasks on which choice discriminates" (p.2 L068-069), the same claim in 5.4 (p.7 L324), and "The smaller effect on P2u indicates that the random-control screen enriches…" (p.8 L400-401). The other six are the five "sits at / at that rung" statements and the DAgger "does not change" sentence.
  - Wording register passes: no "prove" or "confirm". Statistical hygiene passes except the small-cluster fragility (77).
- **Axis 3:** findings 71 and 74.
- **Axis 4:** findings 70, 72, 73, 76, and 79. Framing-only delta, recorded as an explicit pass: the abstract's "beats uniform choice across three seeds (D3 = +0.285 [+0.140, +0.433])" matches Table 20's "POSITIVE (pre-reg.)" in wording only.
- **Axis 5:** findings 75 and 78. The experiment order runs an elimination tournament, and each block now ends in a local verdict. The exception is the first-adapter M4 paragraph in 5.4 (78).
- **BENCHMARK checklist:**
  - Two bottlenecks: the instrument (the choice-frontier contract) and the operationalization (M1 with a ladder check). **Pass.**
  - Definitions argued against near-miss alternatives: enumeration against choice-frontier (Table 23), and exact-ε rungs as the ladder. **Pass.**
  - Headline findings stated as claims. **Pass.**
  - Adoption risks: overfitting to screened panels is addressed via P2u but misread (70). Contamination is addressed by the exclusion sources (App U.1). **Partial.**
  - The Related Work positioning gap against policy-guided node selection is finding 79.

#### 69 · MAJOR · Axis 1 (value cash-out: the portable rule and a second realisable policy are missing) · `iclr2026_conference_discussion.tex; iclr2026_conference_introduction.tex; iclr2026_conference_results.tex`

- **Location:** Discussion p.8 L405-408 (discussion.tex L20): "None of the seven published interfaces we surveyed uses a complete-set submission contract, so the identity failure is shown only on our runtime. The contribution is therefore the measurement, not the exposure of a common flaw." Contributions p.2 L078-081. Conclusion p.8 L424-431, which ends on the claim frame with no practice cash-out. Tables 17 and 19, where the only realisable arms are random-valid, bfs-order, novelty-first, worst-first, the first adapter, and the authors' scaled adapter.
- **Issue:**
  - Once the reframe lands, the paper's value is "the measurement". The measurement is validated only on privileged exact-ε selectors, which are not realisable policies, and the paper says so (p.6 L304-305).
  - Among realisable choosers, the validated instrument separates one non-trivial policy: the authors' imitation adapter (0.306 / 0.432 / 0.151). The rule selectors score 0.000-0.028 on every panel (`arms.{p135,p2,p2u}.{bfs-order,novelty-first,worst-first}.m1`), at or below random-valid.
  - The audit's diagnostic value in published practice is therefore unshown. On the one published interface audited, random-valid already registers choice (0.915 against 0), so the check returns "fine", and the failing contract appears in 0/7 published interfaces.
  - Nowhere does the paper state the reusable takeaway: when to run the audit, what to report (D with ladder position), and what would change in an existing evaluation.
  - Under the Axis 1 anchor rule, the surprise must contradict published practice, and here it contradicts only the authors' earlier contract. A combined paper like this earns its place through *why and when*, and the paper stops at *whether*.
- **Fix:**
  - (a) Add a closing Discussion paragraph with the portable, falsifiable rule. For example: "Before reading random-valid success as choice, run the per-decision identity audit, and if every pair is identical, report success as operation validity. Under a choice-bearing contract, report D together with its ladder position, because D alone does not locate choice quality". Name one concrete evaluation practice it changes.
  - (b) Run one independent realisable policy through the validated instrument on the validation panel and P2, reusing the frozen v4 controls and ladder. Options: the InternVL3.5-8B backbone under the frozen #138 recipe (3 seeds), or a zero-shot scene-only prompt of the base model with a relaxed call cap. This shows M1 plus the ladder ranks policies other than the authors' own. If the instrument cannot separate a second policy from random-valid or from the adapter, that is itself the cash-out.
  - (c) Optionally, and with the largest effect on value: audit the one surveyed interface predicted to saturate (LLM-First Search, Table 22). That would turn the internal anchor into a published-practice finding.
- **Why it changes the verdict:** (b) changes Contribution from "a measurement shown on one policy" to "a measurement that ranks policies", and (c) supplies the missing anchor in published practice.
- **Fix class:** MEANING (it adds a contribution claim and an experiment)
- **Status:** CLOSED (`e7346aa` part (a) portable rule; `e2eb87c` parts (b) and (c): #141 zero-shot second policy ranked below the adapter and equivalent to uniform choice on the validation panel, #142 LLM-First Search audit reported in 5.5 as budget saturation on a published interface)

#### 70 · MAJOR · Axis 4 (the screening interpretation is contradicted by the paper's own P2u ladder) · `iclr2026_conference_introduction.tex; iclr2026_conference_results.tex; iclr2026_conference_discussion.tex; iclr2026_conference_abstract.tex`

- **Location:**
  - Intro p.2 L068-069 (introduction.tex L27): "On the unscreened panel P2u, D3 = +0.149 [+0.030, +0.283], so the random-control screen enriches for tasks on which choice discriminates."
  - 5.4 p.6 L323-p.7 L324 (results.tex L143): "…where 8 of 12 tasks are unsolved by both the adapter and random-valid, so the screen enriches for tasks on which choice discriminates."
  - Discussion p.8 L400-401 (discussion.tex L17): "The smaller effect on P2u indicates that the random-control screen enriches for tasks on which choice discriminates."
  - Abstract p.1 L027: "Without the random-control screen that admits panel tasks, the gain is +0.149".
  - App U.1 p.31 L1672-p.32 L1697 (appendix.tex L1212-1215): "All 12 P2u tasks happen to have 0/10 random-valid goals in screening."
- **Issue:**
  - (i) The paper's own P2u ladder shows that choice discriminates *at least as strongly* on P2u as on P2. Exact reference minus random-valid is 0.873 on P2u against 0.859 on P2. The P2u ladder passes with every lower bound positive (p.32 L1708-1710). The ε-0.75 − random-valid gap is +0.147 [+0.088, +0.226] (`unscreened_p2u.ladder.pairs[3]`).
  - What the screen admits is tasks on which *near-uniform choice sometimes succeeds*: random-valid reaches the goal in 1-9 of 10 screening episodes (App U.1 p.31 L1668). On P2u, where random-valid is at 0.002, the adapter's partial choice skill (near the ε-0.75 rung, which itself falls to 0.149) converts into solves on only 4 of 12 tasks.
  - The stated mechanism is therefore the wrong one. The screen selects tasks easy enough for weak choosers, not tasks where choice matters.
  - (ii) The comparison is cross-panel and untested. No P2−P2u contrast or interval is reported, and the panels differ in membership as well as screening.
  - (iii) P2u is by construction drawn from "kept candidates outside P2", so it is not a random draw of unscreened tasks. All 12 have 0/10 screening goals, which the body never states. The abstract's "Without the random-control screen … the gain is +0.149" invites a reading of P2u as the unscreened-population effect, which the construction does not license.
  - (iv) The claim is asserted as a bare fact three times, with no descriptive label, and it answers the most obvious reviewer concern (the HARKing scan's top three).
- **Fix:**
  - Replace all three sentences with a version that fits the P2u ladder. For example: "…so the random-control screen enriches for tasks on which near-uniform choice sometimes succeeds (random-valid reaches the goal in 1-9 of 10 screening episodes). On P2u, whose 12 tasks all had 0/10 screening goals, choice still discriminates (the ladder passes, descriptive), but the adapter solves only 4 tasks (descriptive)."
  - In 5.4, add one sentence stating that all 12 P2u tasks had 0/10 random-valid screening goals, and that P2u is drawn from kept candidates outside P2.
  - Back the reading with one descriptive analysis on the 35 tasks: D3 against the random-valid screen rate, or the P2−P2u difference with a task-cluster interval.
  - Label the whole statement "(descriptive)".
- **Why it changes the verdict:** the P2u result is the paper's answer to the screening objection. As written, it misstates what P2u shows, and a reviewer who reads Table 19 will notice.
- **Fix class:** MEANING (it changes what the P2u result is claimed to show)
- **Status:** CLOSED (`e7346aa`; author decision: reviewer rewrite without a new P2−P2u analysis)

#### 71 · MINOR · Axis 3 ("sits at that rung" reads as equivalence, which the Statistics appendix forbids) · `iclr2026_conference_abstract.tex; iclr2026_conference_introduction.tex; iclr2026_conference_results.tex; iclr2026_conference_discussion.tex`

- **Location:**
  - Abstract p.1 L028-029 (abstract.tex L21): "but sits at that rung on the validation panel (−0.041 [−0.187, +0.102])".
  - Intro p.2 L066 (introduction.tex L25).
  - 5.4 p.6 L318-319 (results.tex L134): "at the 0.75 rung on the validation panel (S = −0.041 [−0.187, +0.102])".
  - Discussion p.8 L399 (discussion.tex L17) "sits at that rung on the validation panel".
  - Conclusion p.8 L428 (discussion.tex L45).
  - Against these: Statistics appendix p.18 L932-935: "…and none for the separation S, so a non-separated S is not equivalence to the rung. Wherever the text reports a non-material contrast …, an adjacent sentence states that non-significance is not equivalence."
- **Issue:**
  - S has no pre-registered equivalence margin, and its validation-panel interval spans −0.187 to +0.102. "Sits at that rung" asserts a location, and that is the equivalence reading the paper's own Statistics appendix rules out.
  - None of the four NOT_SEPARATED S results in the body (validation, P2u, pooled, DAgger) carries the "non-significance is not equivalence" sentence that the Statistics appendix promises.
  - The wording follows `CONTEXT.md` ("at the exact-ε 0.75 rung on #135"), so the conflict is between the vocabulary entry and the stated statistical rule.
- **Fix:**
  - Replace "sits at that rung" / "at the 0.75 rung" with "is not separated from that rung", keeping the interval.
  - Add once in 5.4, after the ladder-position sentence: "No equivalence margin was pre-registered for S, so a non-separated S is not equivalence to the rung."
  - Amend the `CONTEXT.md` choice-quality entry accordingly.
- **Fix class:** MEANING (it changes the approved position claim from "at the rung" to "not separated from the rung", which needs an author decision)
- **Status:** CLOSED (`e7346aa`; author decision: "not separated from the 0.75 rung" plus the non-equivalence sentence, CONTEXT.md amended)

#### 72 · MINOR · Axis 4 (the DAgger conclusion asserts no change while the co-primary is inconclusive) · `iclr2026_conference_appendix.tex`

- **Location:** App U.2 p.33 L1758-1762 (appendix.tex L1346): "the co-primary is INCONCLUSIVE, ∆ = −0.030 [−0.114, +0.057] … One small round at one seed therefore does not change measured choice quality, and the ablation is inconclusive."
- **Issue:**
  - "Does not change" is an equivalence claim. The co-primary's pre-registered equivalence margin is ±0.05 (`co_primary.equivalence_margin` 0.05), and its interval reaches −0.114, so EQUIVALENT was not reached.
  - The sentence contradicts its own second clause.
  - The closeout says "does not measurably change" (`issue-140-closeout.md` L20), and the paper dropped the hedge.
- **Fix:** "One small round at one seed therefore produces no detectable change in measured choice quality (Δ is inconclusive against the ±0.05 margin), and the ablation is inconclusive."
- **Fix class:** WORDING (it restores the approved "single-seed and inconclusive" claim)
- **Status:** CLOSED (`e7346aa`)

#### 73 · MINOR · Axis 4 ("seeds that no design decision had seen" overstates P2's freshness) · `iclr2026_conference_introduction.tex; iclr2026_conference_results.tex`

- **Location:** Intro p.2 L086-087 (introduction.tex L48) and 5.4 p.7 L325-326 (results.tex L143): "Held-out here means the fresh panel P2, frozen before any evaluation episode from seeds that no design decision or adapter had seen".
- **Issue:**
  - Amendment A1 is itself a design decision. It was made after the controls-only screen of seeds 955000-955039 had admitted 6 tasks (App U.1 p.32 L1699-1701).
  - Those 6 tasks are in P2: elevators-955007, ferry-955007, grid-955007, grid-955021, blocksworld-955022, and towers_of_hanoi-955031, according to `concentration.per_panel.p2.domains`. That is 6 of P2's 11 tasks.
  - No adapter or evaluation outcome was seen, and the disclosure in 5.3 is accurate. The "no design decision" clause is still literally false.
- **Fix:** "…frozen before any evaluation episode, from seeds on which no adapter had been evaluated (the A1 seed extension followed a controls-only screen of the first 40 seeds, Section 5.3)".
- **Fix class:** WORDING
- **Status:** CLOSED (`e7346aa`)

#### 74 · MINOR · Axis 3 (stale scope statements and inconsistent appendix ranges left by the round-5 sweep) · `iclr2026_conference_appendix.tex; iclr2026_conference_experimental_design.tex; iclr2026_conference_results.tex`

- **Location:**
  - (a) App J p.21 L1117-1119 (appendix.tex L572): "Four follow-up windows executed after the program, three on their own GPU ledgers and the CPU-only comparator zoo." Table 2 p.16 L825-836 lists seven GPU follow-up windows (native arms, R1-R4, choice frontier, #135, #136, v4, v5) plus CPU-only #133, #134, and #137.
  - (b) App J p.21 L1133 (appendix.tex L589): "…the current budget rule, which authorizes one training run at seed 17 per model and cell (Section 4)." Section 4 p.3 L154-156 now says the choice-frontier adapter "has three training seeds (17, 29, 71)".
  - (c) Design p.4 L206-208 (experimental_design.tex L78): "At the 2026-09-23 snapshot …, and all follow-ups executed". #138-#140 executed on 2026-09-24 (the #140 A1 is timestamped "11:21 UTC on 2026-09-24", p.33 L1751).
  - (d) "Results Detail appendices (Appendices J to W)" at p.5 L234 (results.tex L26), "(Appendices M to Q)" at p.7 L372 (results.tex L189), and "Appendices P–R" at p.4 L186 (experimental_design.tex L50): one named group with three different ranges.
  - (e) Table 2 v4 row p.16 L833-834: "48/48 new learned episodes, 638/638 P2 and 696/696 P2u zoo episodes replayed". This omits the P2/P2u learned-episode replays, "P2 88/88 and P2u 96/96" (`issue-139-closeout.md` L123).
- **Issue:** Each is a later claim contradicting an earlier one, or an incomplete receipt. Changelog round 5 wave 3 reports the stale-claim sweep as complete.
- **Fix:**
  - (a) "Follow-up windows executed after the program on separate GPU ledgers (Table 2) and on CPU only (the comparator zoo, the counterfactual audit, and the external audit)".
  - (b) "…predates the budget rule, which authorizes one training run at seed 17 per enumeration-contract model and cell (Section 4)".
  - (c) Replace the date with "At the 2026-09-24 snapshot" or "At submission".
  - (d) Use one range, or drop the letter ranges in favour of named appendices.
  - (e) Append "and 88/88 P2 plus 96/96 P2u learned episodes".
- **Fix class:** WORDING
- **Status:** CLOSED (`e7346aa`)

#### 75 · MINOR · Axis 5 (last-label sentence: dangling table pointer, mixed units, missing chance rates) · `iclr2026_conference_results.tex`

- **Location:** 5.4 p.6 L314-315 (results.tex L121): "and the scaled adapter's last-label rate per seed is 0.205, 0.192, and 0.171 against 30.0% for the first adapter (per-seed tables in the Held-Out Panels appendix, Appendix U.1)."
- **Issue:**
  - No table in App U.1 (Tables 19-21) carries a last-label rate. The seed-29 and seed-71 values (0.192, 0.171) appear only in this body sentence. App U p.31 L1646 gives only seed 17's 0.205.
  - The units are mixed (proportions against a percentage).
  - The chance rates differ and are not given: 0.125 for the scaled adapter against 0.144 for the first adapter (`v2 … m4_teacher_agreement.chance`).
  - Two paragraphs later, 5.4 quotes a different first-adapter last-label excess on a different panel (+0.277 over the earlier 9-task panel, where the raw rate is 0.545), without saying the panels differ.
- **Fix:** "…last-label rate per seed is 0.205, 0.192, and 0.171 (chance about 0.13) against 0.300 (chance 0.144) for the first adapter on the same panel (Scaled Adapter appendix)". Add the three per-seed rates to Table 17 or 19, or drop the table pointer.
- **Fix class:** WORDING
- **Status:** CLOSED (`e7346aa`)

#### 76 · MINOR · Axis 4 (the exact reference's M1 of 0.875 is a construction constant, and M1 can exceed it) · `iclr2026_conference_results.tex; iclr2026_conference_experimental_design.tex; iclr2026_conference_appendix.tex`

- **Location:**
  - Abstract p.1 L020 and 5.3 p.6 L292-293: "M1 orders the exact reference (0.875) above …". Design p.4 L162 (experimental_design.tex L27): "Exact-classical runs the declared algorithm and bounds perfect decisions".
  - App I p.20 L1058-1060: "…so the exact episode takes its reference expansion count plus one decisions". p.21 L1093-1094: "an episode solves at multiplier m when its first goal selection occurs within ⌊mR_t⌋ decisions".
  - Table 19 p.32 L1678, where the exact reference is 0.875 [0.875, 0.875] on all three panels. Discussion p.8 L400 "so it remains far from the reference".
- **Issue:**
  - [INFERENCE, supported by the definitions and the constant, zero-width interval on 35 tasks] The exact reference needs R_t+1 decisions, so it always fails at m = 1 and solves at every m ≥ 1.25. M1 = 0.875 is therefore a constant of the metric, not a measurement.
  - M1 is not bounded by the reference. hadd-greedy scores 0.882, 0.928, and 0.906 (`arms.*.hadd-greedy.m1`). On P2 visitall the adapter's M1 is 1.0 (`arms.p2.learned_adapter_seed_mean.per_task…visitall-expanded-955170` = 1.0), above the reference.
  - The top ladder gap (+0.082) is therefore partly a metric-construction difference, and the reference is an imitation target rather than a ceiling. None of this is disclosed.
- **Fix:**
  - Add to 5.3 or App I: "Because goal selection is the (R_t+1)-th decision, the exact reference fails at m = 1 and scores M1 = 0.875 by construction. Arms that reach the goal in fewer decisions can exceed it (hadd-greedy 0.88-0.93)."
  - Change "bounds perfect decisions" to "defines the imitation target", and drop "so it remains far from the reference" (see 78).
- **Fix class:** WORDING
- **Status:** CLOSED (`e7346aa`)

#### 77 · MINOR · Axis 2 (the headline separation rests on an 11-cluster percentile bootstrap and is fragile) · `iclr2026_conference_results.tex; iclr2026_conference_appendix.tex`

- **Location:** Abstract p.1 L027-028, Intro p.2 L065-066, 5.4 p.6 L320, and Conclusion p.8 L427: "interval-separated above the exact-ϵ 0.75 rung on the held-out panel (+0.227 [+0.053, +0.403])". Table 20 p.32 L1693 "SEPARATED ABOVE (pre-reg.)".
- **Issue:**
  - The only interval-separated ladder-position result is a 95% percentile bootstrap over 11 task clusters, and percentile intervals are known to under-cover at this cluster count.
  - The per-task differences are 8 positive and 3 negative (`heldout_p2.separation.vs_eps_0.75.per_task_difference`). An exact two-sided sign-flip permutation over all 2^11 flips gives p = 0.046 (reviewer computation).
  - The pre-registered rule is met, so this is not a defect of the verdict. It is a robustness fact a reader needs, because the separation claim is repeated in four headline places.
- **Fix:** Add one sentence to App U.1, and a parenthetical in 5.4: "An exact sign-flip test on the 11 per-task differences gives p = 0.046 (8 positive, 3 negative, descriptive)." Apply the same small-cluster check to D3 on P2u.
- **Fix class:** WORDING (it adds a robustness number and leaves the pre-registered verdict unchanged)
- **Status:** CLOSED (`e7346aa`; author decision: wording-only disclosure of 11 clusters and 8/3 per-task signs, no unpinned p-value)

#### 78 · MINOR · Axis 5 (undefined headline symbols, a misplaced paragraph, and a non-sequitur) · `iclr2026_conference_abstract.tex; iclr2026_conference_introduction.tex; iclr2026_conference_results.tex; iclr2026_conference_discussion.tex`

- **Location:**
  - (a) Abstract p.1 L020 "M1 orders…" (abstract.tex L14) and p.1 L025 "D3 = +0.285" (abstract.tex L19). Intro p.2 L057 and L063 (introduction.tex L18, L23). M1 is first defined at Design p.4 L196-197, and D at p.4 L202. D3 is never defined in the body; it appears only in the Table 20 caption.
  - (b) 5.4 p.7 L330-333 (results.tex L152): the post-hoc M4 analysis of the *first* adapter on the *earlier 9-task* panel sits inside the replication section. It eliminates no alternative explanation for the scaled-adapter result.
  - (c) Figure 2 caption p.6 L282-284 (results.tex L105): no "descriptive" status for the P2u ladder, and no mention of the first-adapter row.
  - (d) Discussion p.8 L399-400 (discussion.tex L17): "…and is not separated from it on the unscreened panel P2u or pooled (descriptive), so it remains far from the reference." The conclusion does not follow from rung positions.
- **Issue:** A tired reviewer re-reads the abstract to decode M1 and D3. 5.4's paragraph has no local verdict tied to its section. The figure caption breaks the claim-discipline rule, and the "so" is a non-sequitur.
- **Fix:**
  - (a) Abstract: "the solve-versus-budget area M1" at first use, and "(D3, adapter minus random-valid M1 averaged over three seeds)". Mirror this in the Intro.
  - (b) Move the first-adapter M4 sentence to App S, keeping a pointer.
  - (c) Caption: append "The P2u ladder is descriptive. The first adapter appears on the validation panel only."
  - (d) Replace "so it remains far from the reference" with a separate sentence: "Its M1 (0.151-0.432) remains well below the reference's 0.875."
- **Fix class:** WORDING
- **Status:** CLOSED (`e7346aa`)

#### 79 · MINOR · Axis 4 (positioning: policy-guided node selection and tie-breaking literature uncited) · `iclr2026_conference_related_work.tex; iclr2026_conference_related_refs.bib`

- **Location:** Related Work p.2 L093-p.3 L124. `related_refs.bib` contains `orseau2018singleagent` and `orseau2021policyguided`, and neither is cited in the rendered References (p.9-12).
- **Issue:**
  - The choice-frontier contract has a policy select which frontier state a best-first search expands next. That is exactly policy-guided best-first search: Orseau & Lelis, "Policy-Guided Heuristic Search with Guarantees", AAAI 2021 (https://arxiv.org/abs/2103.11505, Semantic Scholar 53ae4b740f4a870004f9f840a731a0e051eb2b95, fetched 2026-09-25).
  - The #134 result is a tie-breaking effect ("on the other 29 pairs every equal-priority tie breaks the same way under both orders", p.5 L268). Tie-breaking order in best-first heaps is a known driver of search behaviour: Asai & Fukunaga, "Tiebreaking Strategies for A* Search: How to Explore the Final Frontier", AAAI 2016 (DOI 10.1609/aaai.v30i1.10071, Semantic Scholar 47be28eee56a6171ae0b1a26c3692221f2d6cc15, fetched 2026-09-25).
  - A planning-literate reviewer will see both omissions. They also weaken the novelty framing of the contract.
- **Fix:** Add one sentence to Related Work: "The choice-frontier contract is a learned node-selection policy in the sense of policy-guided heuristic search (Orseau & Lelis, 2021), and the submission-order counterfactual isolates a heap tie-breaking effect of the kind studied by Asai & Fukunaga (2016)". Add the Asai & Fukunaga entry.
- **Fix class:** WORDING
- **Status:** CLOSED (`e7346aa`)

#### 80 · MINOR · Evidence hygiene (off-by-one protocol pointer, non-repository rendering source) · `iclr2026_conference_results.tex; iclr2026_conference_appendix.tex`

- **Location:**
  - results.tex L161: "half corpus per issue-140-protocol.md L124 (A1 item 2)".
  - The appendix.tex comment before L1341: "L124 (first 512 + 512, 2048 samples, 64 steps)".
  - The appendix.tex comments for Tables 19 and 20: "3-dp renderings per local evidence-r5.md section 3" and "sections 1-2".
- **Issue:**
  - `issue-140-protocol.md` L124 is A1 item 3 ("Evaluation: DAgger s17 on the #135 panel first…"). Item 2, the 512 + 512 aggregate, is L123.
  - `local://evidence-r5.md` is a session artifact and is not in either repository, so a reproducer cannot resolve it. The artifact keys named alongside it do resolve.
- **Fix:** Change both L124 pointers to L123. Replace "3-dp renderings per local evidence-r5.md" with "rounded half-up to 3 dp from the named keys".
- **Fix class:** WORDING
- **Status:** CLOSED (`e7346aa`)

**Disposition (2026-09-25, `e7346aa`):** 70-80 CLOSED (70, 71, and 77 by author decision on the reviewer's fix; the others as prescribed). 69 PARTIAL: the portable rule is added; the second-policy experiment and the LLM-First Search audit are filed as #141 and #142 and are not written into the paper. Finding 40 WONTFIX unchanged.

### What would change the verdict

The numbers are right, the pre-registration is real, and the claim discipline mostly holds. The paper sits at WEAK REJECT for two reasons, neither of which is a hygiene problem.

First, value (69). With the identity failure confined to the authors' runtime, the paper's contribution is "the measurement", and that measurement has so far ranked exactly one realisable policy of interest. Two changes would move it to BORDERLINE:
- run a second, independent realisable policy (the InternVL3.5 adapter under the frozen #138 recipe, or a zero-shot scene-only base prompt) through the validation and P2 panels with the existing v4 controls;
- state the portable rule of the audit.

Auditing the surveyed interface predicted to saturate (LLM-First Search) would do more for value than any other single experiment. A published interface on which random-valid matches the reference would convert the anchor from internal to published practice.

Second, the screening answer (70). The P2u sentence must be rewritten to match the P2u ladder and backed by one descriptive P2−P2u or screen-rate analysis. As written, it misstates what the paper's own table shows, and it is the paper's reply to the most predictable objection.

The MINOR items (71-80) are cheap. The main text has a page of slack, so 70, 71, 76, and 77 fit without cuts. None of them changes the rating on its own. Together with 69 and 70 they are what a 6 would require: an instrument shown to rank policies, an honest reading of the screen, and small-sample robustness on the one separated result.

## Live fixlist — review 19 (2026-09-23)

**Verdict:** WEAK REJECT. 0 CRITICAL, 1 MAJOR, 8 MINOR.
- MAJOR: finding 49, carried and blocked on #134.
- MINOR: the remainders of 51, 53, and 56; finding 60, which is open and blocked on #134; the regressed review-16 finding 15; and new findings 66-68.

Most damaging issue: **finding 49**. The value anchor is still unestablished. The two-contract text is accurate in 5.2, but Contribution 1 and Figure 1 present "48/48 identical versus 18/18 divergent" as a discriminating verdict of one check. Nothing on the page shows the check can return "identical" on a runtime where choice matters, or "divergent" where it does not. That submission-order-serial counterfactual is ticketed as #134 and has not been run.

Genre: BENCHMARK (+ FINDINGS)
Δbelief: The update comes from the authors' own additive best-first runtime. There, the grounded-menu enumeration contract makes random-valid decision-identical to exact (48/48), so its success rows measure operation validity. A choice-frontier redesign separates the controls (−0.644), and the first adapter does not beat uniform frontier choice. The new title and Figure 1 now surface this update on p.1 and p.6.
Ledger: Verified: 44 (remainder), 45 (remainder), 50, 52, 54, 55, 57, 58, 59, 61, 62, 63, 64, 65 · Partial: 49 (text part), 51, 53, 56 · Open-blocked (#134): 49, 60 · Regressed: 15 (review 16, Related Work positioning sentence) · Not addressed: none · Wontfix: 40 (unchanged, App U p.28 L1550) · New: 66-68

**Reviewer summary:**

> Round-3 re-review of HEAD `1281c1b`, covering the three review-18 waves (`9de44ad`, `83e30c2`, `640467b`) and their bookkeeping. I read the rendered PDF text in full (29 pages), all diffs since `19a641b`, both figure PNGs, and both scripts. The build is clean. The Conclusion ends on p.9, so the main text is 9 pages.
>
> The pinned artifacts have not changed since review 18: the evidence tree is clean, and the last `outputs/` commit is `bd57324`. Every number in the rendered PDF, including every number touched this round, matches its artifact. That covers 5.2, Contribution 1, Figure 1, 5.4, 5.5, App M/N/O/Q/R, and the Conclusion. This round also confirmed the synthesis CSVs directly: DAgger, successors (65/109, 93, 66 recomputed from the per-cell rows), curriculum, transfer, and baseline contrasts. It confirmed modality-stress/analysis.json for Table 12 and the −0.694 channel contrast, and seed-replication/analysis.json for Table 6 and Cell B.
>
> I sampled 16 of the new `%` Evidence comments. All paths exist and all named keys resolve. The claim wording was fixed as prescribed in 52, 54, 55, 58, 59, 62, 63, and 64. The zheng2024robust entry matches arXiv and the ICLR 2024 proceedings.
>
> What remains:
> - The finding-49 text overstates what the two opposite verdicts show. Contribution 1 and Figure 1 drop the "by construction" hedge and re-inflate 9 tasks to "18/18" (see 49).
> - One Related Work sentence still credits the menu probe with testing surface-following against grounding (51).
> - Four numeric blocks still lack artifact comments (53).
> - Section 3 still points invariants to Appendix A (56).
> - The wave-3 rewrite of Related Work deleted the "this paper operationalizes the known admissible-action handicap" positioning sentence, which regresses review-16 finding 15.
> - The new Figure 1 mixes units and panels (66).
> - The abstract's last sentence is garbled (67).
> - The finding-61 insertion left a comma splice (68).

### Build, page count, figures

- **Build:** iclr2026_conference.log (23:01:36) and .blg (23:01:35) are newer than every .tex and .bib file. The newest source is related_refs.bib at 22:59:44. Counts:
  - 0 errors (`^!` count 0)
  - 0 LaTeX warnings and 0 package warnings
  - 0 undefined references or citations
  - 0 overfull boxes (46 underfull)
  - 0 BibTeX `Warning--` lines
  - 41 entries used (40 + zheng2024robust) and 41 `\bibitem`s
  - "Output written on iclr2026_conference.pdf (29 pages, 377980 bytes)"

  PDF Title/Author metadata is empty. **PASS.**
- **Page count:** The Conclusion ends on **PDF p.9** (L452), and the Reproducibility Statement and References begin on p.9. Main text = **9 pages** against the 9-page limit. **PASS**, with zero slack.
- **fig:contracts (now Figure 1, p.6, in 5.3's float slot, first cited in Intro p.2 L076 and 5.2 L262):** `fig_contracts.py` L27-43 now reads its numbers from the JSONs rather than hard-coding them. It renders 48/48 from native-arms/v1/identity-audit.json pairs_identical/pairs_checked, 18/18 from choice-frontier/v1/evaluation/identity-audit.json pairs_divergent/pairs_checked, and −0.644 [−0.856, −0.422] from analysis.json contrasts.random_valid_minus_exact_reference (f3 rounding). All three match. The PNG has no clipping. Content defects are in finding 66.
- **fig:zoo-m1 (now Figure 2, App R p.28, cited from 5.10 p.7 L376):** the script and values are unchanged and match o4/metrics/analysis.json (see review 18). The body-to-appendix figure reference resolves.

### Numbers re-check

The artifacts are byte-unchanged since review 18: the evidence repo's `git status` is clean, the last commit touching `outputs/` is `bd57324` (14:15), and the md5 of identity-audit.json, v1 analysis.json, and o4 analysis.json is stable. Review 18's re-derivations therefore still hold: the chance band 0.5919/0.6252 from the 36 distractor episodes, the episode-length histogram {1: 20, 2: 8, 3: 8}, the 1,152-file baseline tally, and the four ledger sums. The table below re-checks the rendered PDF text against those artifacts and adds the sources touched this round.

| claim | PDF location | artifact : key | match |
|---|---|---|---|
| 48/48 identical (additive enumeration) | p.1 L019, p.2 L061/L093, p.5 L257, Fig. 1(a) | `outputs/native-arms/v1/identity-audit.json` : pairs_checked 48, pairs_identical 48 | yes |
| 18/18 divergent (choice frontier), 9/9 tasks | p.1 L027-028, p.2 L078-079/L093, p.5 L261, Fig. 1(b) | `outputs/choice-frontier/v1/evaluation/identity-audit.json` : pairs_checked 18, pairs_divergent 18, verdict CHOICE_SENSITIVE; pairs[] exact/random_valid_seed17 identical across greedy/w3 for each task | yes (units: finding 49/66) |
| −0.644 frozen [−0.856, −0.422]; task-clustered [−0.889, −0.333] | p.1 L029-030, p.2 L080, p.7 L358-359, Fig. 1(b) | `choice-frontier/v1/evaluation/analysis.json` : contrasts.random_valid_minus_exact_reference.{mean, ci95}; issue-132-closeout.md Erratum item 2 | yes |
| +0.389 [+0.167, +0.611]; +0.033 [−0.033, +0.133] | p.1 L032-034, p.2 L081-082, p.7 L360-361 | same file : contrasts.learned_minus_pretrained_base, contrasts.learned_minus_random_valid (descriptive_only false; source-conflict comment now present at results.tex and appendix.tex) | yes |
| Table 1: 18/18, 7/18, 0/18, 32/90 | p.7 | `choice-frontier/o4/metrics/all-episode-metrics.json` : records[multiplier=2].solves["2"] | yes |
| permutation 36/36, 0/512; distractor 0/36, 36/60, 0.6; chance 0.592-0.625; 20/36 | p.1 L022-025, p.7 L334-338 | `native-arms/v1/stress-evaluation.json` : cells["menu\|*"], distractor.*; distractor episode records (review-18 recomputation) | yes |
| BFS/BFWS RV 15/24, 17/24; SFT 125/288, RV 240 (96), base 0, exact 288 | p.1 L020-022, p.2 L066-068, p.6 L289-292 | `expanded-study/v1/baseline/episodes/*/*/*.json.gz` : result.goal_reached (review-18 tally); `synthesis-v1/baseline-summary.csv` | yes |
| App L +0.833 (w3), +0.903 (greedy) SFT − base | p.22 | `synthesis-v1/baseline-contrasts.csv` : process_sft_minus_pretrained_base rows (w3 0.833/0.750/0.917, greedy 0.917/0.917/0.875; modality means 0.833, 0.903) | yes |
| 5.4 matched modality 5/12, 6/12, 6/12 vs 10/12 | p.6 L300 | `synthesis-v1/README.md` L52 "Historical v5, kept separate" | yes |
| 5.4 generalization 128/150 vs 0/150; families 29/27/27/26/19 of 30; RV 750/750 | p.6 L302, App M p.23 | `synthesis-v1/README.md` L113-124 generalization table | yes |
| 5.4 / App M DAgger 1/72 each; Table 10 3/9, 2/9, 1/9, 6/9, 9/9; 45/72; rates .316/.175/.364 | p.6 L302, p.23 Table 10 | `synthesis-v1/dagger-summary.csv` : development/unseen rows (0.31556, 0.17488, 0.36364) | yes |
| successors 45/45 → 1/45; 65/109; 93 schema-valid; 66 effect-valid | p.6 L303, App M p.23-24 | `synthesis-v1/successor-summary.csv` : Σ downstream_successes (model-generated 1, trusted 45), Σ predictions_accepted 65, Σ validity_schema_valid 93, Σ(schema valid + invalid) 109, Σ validity_effect_valid 66 | yes |
| curriculum 24/24/25, 24/27/26, 25/27/27; sequential 24/25/24; intervals −0.111 [−0.259, +0.037] … −0.037 [−0.185, +0.111] | App M p.24 | `synthesis-v1/curriculum-summary.csv`; `synthesis-v1/README.md` L102-105; `synthesis-v1/analysis.json` (values present) | yes |
| transfer 0/36, min Holm p 0.8156, min raw p 0.0227 | p.6 L304, App F/M | `outputs/expanded-study/v1/transfer-paired-analysis.json` : min_holm_p 0.81561, min_raw_p 0.02266, len(comparisons) 36 | yes |
| R3 31/36, base 0/36, "24/24 control entries per modality, two per task" | p.2 L071-072, p.6 L304-306 | `second-backbone-v3/evaluation/analysis.json` : by_modality.*.internvl (process_sft_successes 11/10/10, random_valid_successes 24, episodes 12); architecture_note "…architecture-difference limitation" | yes |
| 5.5 / App N 905, 447/447, 229/407, 72/407; 137/88/46; 9/9/3/30; 144/144; 155/162; 56/546 | p.6 L312-315, p.25 L1305-1321 | `docs/experiments/expanded-study/failure-mechanism-analysis.md` L180-190, L203-204, L240-255 | yes |
| Table 12 and channel isolation −0.806 / −0.111 / −0.694 [−0.889, −0.472] | p.25-26 | `outputs/expanded-study/v1/modality-stress/analysis.json` : contrasts.degradation_by_family_modality[] (learned_corrupted_success, learned_clean_success, mean_degradation, degradation_interval_95), contrasts.multimodal_channel_isolation.* | yes |
| Table 6 and Cell B (21/21/22; +0.875/+0.875/+0.917; −0.125/−0.125/−0.083; 0/72, +0.000 [0, 0]) | p.18 | `outputs/expanded-study/v1/seed-replication/analysis.json` : baseline_process_sft.per_seed.{17,29,71}.{successes, contrasts.*.difference}; dagger_iteration_1.per_seed.*.contrasts.dagger_minus_continued_sft_unseen | yes |
| App Q native arms 18/18, +0.111 [0, +0.278], 0.000 [0, 0]; R4 10/10, 0/40 | p.26-27 | `native-arms/v1/evaluation/analysis.json` : contrasts.*; stress-evaluation.json : cells["variants\|*"] | yes |
| App R M4 23/132 (17.4%), 26.9%, 72/132 (54.5%); M5 .3125/.075/.625 | p.27-28 | `o4/metrics/analysis.json` : arms.learned_adapter.m4_teacher_agreement.*, m5_D_descriptive.* | yes |
| zoo M1 / Table 2 / Figure 2 | p.1 L036-038, p.8, p.28 | `o4/metrics/analysis.json` : arms.*.m1_auc, m1_task_cluster_95pct_ci_10000_seed133, m2/m3 keys | yes |
| Conclusion −0.035 [−0.150, +0.061]; 54.5% | p.9 L450-451 | `o4/metrics/analysis.json` : m1_m2_m3_dominance_holm.comparisons.random_valid.m1_auc.{difference_favoring_learned −0.03472, cluster_bootstrap_95pct_ci}; arms.learned_adapter.m4_teacher_agreement.selected_last_rate 0.5455 | yes |
| ledgers 68.5244/336, 53.52 (15.9%), 3.2086/12, 7.7998/36, 1.069/12 | p.5 L242, App E/J | Σ attempts[].gpu_hours in the four budget files (review 18); `synthesis-v1/README.md` §8 total 53.5166/336, "15.9% of cap" | yes |
| BFS pilot 1.0 / RV 1.0 / base 0.0, five seeds | App J p.21-22 | `docs/experiments/deadline-study/prior-evidence.json` : historical_bfs_stages[stage v8].metrics (outcome VALID_STOP, per_seed 17/29/43/71/101) | yes |

**Evidence-comment spot-check (16 sampled, all resolve):**
1. appendix.tex L70-71 → failure-mechanism-analysis.md taxonomy rows (L203-204)
2. L216-217 → issue-58 L39-46 (69,019 / 67,215 / 47,780 / 21,239), issue-57 L6, and issue-56 L19 (69,019)
3. L380-381 → seed-replication/analysis.json seeds.{original, additional_prospective}, cross_seed_aggregation
4. L400-401 → baseline_process_sft.per_seed.*.successes / contrasts.*.difference
5. L406-407 → dagger_iteration_1.per_seed.*.arms.*.unseen, contrasts.dagger_minus_continued_sft_unseen, aggregated.contrast_point_estimates_per_seed (key present)
6. L537-538 → synthesis-v1 README §8, branch-reconciliation.csv, verification.json (files present)
7. L547-548 → Σ gpu_hours in the three GPU ledgers
8. L558-559 → prior-evidence.json historical_bfs_stages[v8]
9. L569-570 → baseline-summary.csv and baseline-contrasts.csv
10. L644-645 → README "Historical v5, kept separate"
11. L649-651 → README generalization table, issue-124-closeout.md, generalization-robustness/evaluation.json (present)
12. L657 and L674 → dagger-summary.csv
13. L679-680 → successor-summary.csv
14. L684-685 → curriculum-summary.csv and synthesis-v1/analysis.json
15. L689-690 and L708 → transfer-paired-analysis.json, transfer/leakage.json, transfer-accuracy.csv
16. L750-753 and L773-774 → modality-stress/analysis.json contrasts.* (key names match exactly)

Also checked: abstract.tex comments for 7/18, +0.389, +0.033, and 0.933 (all-episode-metrics.json, v1 analysis.json contrasts, issue-59 L250-253), and results.tex Table 1 (`cells.json` has top-level key `cells`).

One imprecision: the App D comment cites issue-56 L19 for "105-task panel", but L19 carries only the 69,019 count. The 105-task figure is not on that line. This is not a mismatch in the prose number, which issue-58 L42 supports ("105 immutable semantic-task split assignments").

**zheng2024robust:** Checked against the arXiv abstract (https://arxiv.org/abs/2309.03882, fetched 2026-09-23) and the ICLR 2024 proceedings page (https://proceedings.iclr.cc/paper_files/paper/2024/hash/54dd9e0cff6d9214e20d97eb2a3bae49-Abstract-Conference.html, fetched 2026-09-23). Authors (Zheng, Zhou, Meng, Zhou, Huang), title, venue, and year match. The proceedings list pp. 19426-19454, which the entry could add but need not. The Related Work paraphrase ("Label-position selection bias is documented for LLM multiple-choice selectors") is faithful to the abstract: "they prefer to select specific option IDs as answers … token bias". **PASS.**

### Verification of review-18 findings

| # | sev (r18) | r19 result | evidence at `1281c1b` |
|---|---|---|---|
| 44 (remainder) | MINOR | VERIFIED | Discussion p.9 L436 "Imitation target. The exact reference solves by construction of the budget" (discussion.tex L28). No `\texttt{exact\_reference}` in reader prose. |
| 45 (remainder) | MINOR | VERIFIED | App S p.28 L1507-1508 "Cell A covers one of the three modalities of the greedy additive cell". No "headline" left in the PDF. |
| 49 | MAJOR | **PARTIAL (text part) · OPEN-blocked (#134)**; wording remainder CLOSED (`c08ef50`), counterfactual still OPEN on #134 | Accurate as written: 5.2 p.5 L261-263 (results.tex L38) says "The same check returns the opposite verdict under the choice-frontier contract, 18/18 divergent pairs (Figure 1), a divergence that holds by construction whenever a menu offers two or more states, and the submission-order-serial counterfactual on this runtime has not been run". The numbers match both identity-audit.json files, and the hedge and the unrun counterfactual are stated. **Overclaiming remainder (MINOR, WORDING):** (i) Contribution 1 p.2 L091-093 (introduction.tex L31) "and the same check finds 18/18 divergent pairs under the choice-frontier contract" has no by-construction hedge. It presents the pair as evidence that the audit discriminates, though the divergence could not have failed. (ii) 5.2, Contribution 1, and Fig. 1(b) print "18/18" with no 9-task qualifier, while the Abstract, Intro ¶3, Contribution 2, and 5.9 say "9/9 tasks (18 cells, coincident control sequences)". This reintroduces, in new text, the unit inflation that review-16 finding 9 fixed at its original sites; those sites are intact. (iii) The two verdicts come from different panels (24-task baseline vs 9-task panel) and different random-valid definitions (Design p.4 L191-192 "share a name but not a distribution"), which the new sentences do not say. (iv) Intro p.2 L107 "a reusable audit" still asserts portability that #134 has yet to test. **Fix:** Contribution 1 → "…(48/48 pairs), while under the choice-frontier contract the same check diverges on all 9 tasks (18 pairs), as it must whenever a menu offers two or more states." 5.2 → "18/18 divergent pairs (9 tasks)". Intro L107 → "a per-decision audit whose portability beyond this runtime is untested". The experimental part stays blocked on #134. |
| 50 | MAJOR | VERIFIED | Title (hub L19): "When Random-Valid Equals the Reference: A Per-Decision Identity Audit for Search-Execution Evaluation of Vision-Language Models". fig:contracts is Figure 1 in the body (p.6), and fig:zoo-m1 moved to App R (p.28) with Table 2 kept in the body (p.8). Main text is still 9 pages. The Figure 1 content defect is finding 66. |
| 51 | MAJOR | **PARTIAL** → remainder CLOSED (`c08ef50`) | Fixed as prescribed: Abstract p.1 L042-044, Contribution 1 p.2 L093-094, and the Conclusion p.9 L447-448 ("a cheap per-decision identity audit exposes this") demote the probe and say the discriminating variant is unrun. 5.7 p.7 L341 matches. **Remaining:** Related Work p.3 L139-140 (related_work.tex L14) "The menu manipulations in this paper target this interface by testing whether a trained search policy follows menu surface rather than grounding its operation in state". This credits the probe with the very discrimination that 5.7 says it cannot make. **Fix:** "The menu manipulations in this paper probe this interface, and only the unrun fixed-versus-random-position variant would separate surface-following from state grounding." Remainder MINOR, WORDING. |
| 52 | MAJOR | VERIFIED | Conclusion p.9 L448-451 carries the prescribed wording, including "(paired −0.035 [−0.150, +0.061], which is not equivalence), and a post-hoc label audit finds 54.5% last-label emissions". 5.10 p.8 L390-391 reads "with no last-label comparator and no equivalence claim". App R p.28 L1485-1486 reads "no last-label comparator was run, so these post-hoc rates do not establish a position habit". Every "habit" occurrence in the PDF is now hedged. |
| 53 | MAJOR | **PARTIAL** → remainder CLOSED (`c08ef50`) | Most of it is fixed: the 16 sampled comments resolve (see spot-check), the content_brief.md sources are replaced, and both descriptive_only source-conflict comments are present (results.tex L152, appendix.tex L890). **Remaining** blocks with numbers but no adjacent artifact comment: experimental_design.tex L18 (512 records, 16 updates, 47,780-record corpus, revision 0c351dd0); appendix.tex L341 (BFWS gate 0.95 / 10,000 / 1729 / 0.025; the adjacent comment names only "issue #59"); L350 (transfer min adjusted p 0.8156); L618 (App L +0.833 / +0.903, whose source is baseline-contrasts.csv). **Fix:** add `% Evidence:` lines: design L18 → the BFWS gate training config / docs/issue-59-bfws-structural-gate.md and the expanded-study recipe; L341 → docs/issue-59-bfws-structural-gate.md L110-111, L250-253; L350 → outputs/expanded-study/v1/transfer-paired-analysis.json min_holm_p; L618 → synthesis-v1/baseline-contrasts.csv process_sft_minus_pretrained_base (modality means). Remainder MINOR, WORDING. |
| 54 | MAJOR | VERIFIED | 5.4 p.6 L300-301 reads "(…, a 3-problem panel) does not support an intrinsic modality effect, and non-significance is not equivalence". |
| 55 | MINOR | VERIFIED | 5.4 p.6 L306-307 "an unpaired comparison because the backbones differ in vision tower, connector, tokenization, and multimodal training". App M p.25 L1296-1298 "…reported as an architecture-difference limitation". "isolat" no longer occurs in reader prose about the backbone. |
| 56 | MINOR | **PARTIAL** → remainder CLOSED (`c08ef50`) | Fixed: 5.2 p.5 L259 "(Algorithm Invariant Definitions appendix)". The Reproducibility Statement uses prose names plus `\ref`-resolved "Appendix R" (p.9 L457-459). **Remaining:** Section 3 p.3 L161 (search_process_policy.tex L21) "schemas and invariants in Appendix A". The invariants are in App B, and `\ref{appendix}` resolves to Operation Schemas. **Fix:** "(schemas in Appendix A, invariants in the Algorithm Invariant Definitions appendix)". Remainder MINOR, WORDING. |
| 57 | MINOR | VERIFIED | Intro p.2 L071-072 and 5.4 p.6 L305-306 read "random-valid solves every panel task with 24/24 control entries per modality, two per task". App M p.24 L1291 keeps "24/24 per modality", but App M explains the two-entries basis at L1283-1285. |
| 58 | MINOR | VERIFIED | 5.5 p.6 L313-315, App N p.25 L1319-1321, and Discussion p.8 L426-427 use the descriptive wording ("After process supervision, most learned failures (229/407 …) … and 72/407 remain malformed outputs"). "teaches" and "frontier intent" are gone. |
| 59 | MINOR | VERIFIED | App Q p.27 L1422-1425 "is consistent with the reduced contract removing scalar operands whose emission the full-scaffold adapters failed, and it does not measure whether that text carried signal". |
| 60 | MINOR | OPEN-blocked (#134); interim no-interval caveat added (`c08ef50`) | Unchanged by author decision: 5.10 p.7 L377-p.8 L390 and App R p.27 L1456-1458 still give bare proportions. The interim clause "(no interval computed; decisions are clustered within 9 tasks)" was not added. It would be a zero-cost WORDING stopgap until #134 lands. |
| 61 | MINOR | VERIFIED | Related Work p.3 L130-132 cites Zheng et al. (2024). The entry is verified above. The insertion left a comma splice (finding 68). |
| 62 | MINOR | VERIFIED | Discussion p.8 L423-424 "the additive-cell output contract is learnable (BFS and BFWS cells score 0/24)" and L427-428 "The language-channel dependence is supported only by the copyability-preserving shuffled condition". |
| 63 | MINOR | VERIFIED | 5.1 p.5 L243-244 "the three separately ledgered GPU follow-up windows, and the CPU-only comparator zoo". App J p.21 "three on their own GPU ledgers and the CPU-only comparator zoo". This matches the three budget files. |
| 64 | MINOR | VERIFIED | Design p.4 L206-208 "(the Choice-Frontier Contract appendix and Appendices P–R) were each frozen before their own first outcome, on separate ledgers, but after earlier outcomes on the same nine tasks (Section 5.11)". |
| 65 | MINOR | VERIFIED | All 14 listed colons are replaced (appendix.tex L397, L408, L416, L526, L544, L627 ×2, L630, L661, L706 ×2, L709, and results.tex L38). "behaviour" is gone. Design L47 and L54 are split. App R L843 reads "returns CHOICE_SENSITIVE and passes". App S L850 is fixed. The main text has no prose semicolons (all 9 hits are citation separators) and no em-dashes. The paragraph-purpose census passes. |
| 40 | MAJOR | WONTFIX (unchanged) | App U p.28 L1550 / appendix.tex L945 is verbatim as dictated. Not re-argued. |
| 1-36 (spot-check) | — | **15 REGRESSED** → CLOSED (`c08ef50`), others no regression | **Finding 15** (review 16, CLOSED `afec954`). The closing fix was to "reframe the contribution as operationalizing a per-decision identity check for that known handicap in search-execution evaluation". Wave 3 (`640467b`) replaced "This paper operationalizes the known admissible-action handicap in search-execution evaluation with a per-decision identity audit of random-valid against the exact reference…" with the subjectless "Per-decision identity audits compare random-valid with the exact reference on additive best-first cells under the grounded-menu contract, then assess the redesigned frontier selector against named algorithms (Section 5)" (Related Work p.3 L140-143). The Jericho/CALM citations remain, but the sentence that ties this paper's audit to the known handicap is gone. The new sentence reads as a description of existing practice. It also says the zoo "assess[es]" the adapter against named algorithms, though 5.10 says the zoo "cannot calibrate choice quality". **Fix:** restore "This paper operationalizes the known admissible-action handicap in search-execution evaluation with a per-decision identity audit of random-valid against the exact reference on the additive best-first cells of the grounded-menu contract, and bounds the redesigned frontier selector against named rules (Section 5)." Remainder MINOR, WORDING. Others checked with no regression: #1 additive scoping (p.1 L016-020), #2/#3 (p.7 L335-341), #4 (p.1 L036-038), #5 (App O), #6 (9 pages), #7 (App M L1292-1293), #9 (Abstract, Intro ¶3, and Contribution 2 intact; the new instance is tracked under 49), #10 (identical provenance sentence in Design L215, App I, App R L1429-1430), #12, #13, #18 (no GitHub or institution in the PDF), #20, #23, #33, #36. |

**Tally:** 14 verified (44r, 45r, 50, 52, 54, 55, 57, 58, 59, 61, 62, 63, 64, 65), 4 partial (49 text part, 51, 53, 56), 2 open-blocked on #134 (49, 60), 1 regressed from review 16 (15), 0 not addressed, 1 WONTFIX unchanged (40).

### New findings

#### 66 · MINOR · Axis 3 (units and panels conflated in the 10-minute figure) · `figures/fig_contracts.py; iclr2026_conference_results.tex (fig:contracts caption)`

- **Location:** Figure 1, p.6 L270-284: panel (a) "48/48 additive pairs identical"; panel (b) "18/18 cells divergent / random-valid − exact reference = −0.644 [−0.856, −0.422]"; right node of (a) "Order-invariant heap"; caption "Under the choice-frontier contract the identity gate diverges on 18/18 cells". Script fig_contracts.py L39-43, L77.
- **Issue:** The paper's belief-setting figure puts two verdicts side by side as if they came from one panel.
  - The units differ: "pairs" in (a), "cells" in (b).
  - The panels differ: 48 pairs from the 24-task expanded baseline in (a), 9 tasks × 2 algorithms in (b), whose control sequences coincide, so 9 independent units.
  - The random-valid samplers differ by definition (Design p.4 L190-192).
  - Only (b) carries a success contrast. The matching enumeration-contract number, random-valid − exact = +0.000 on both additive columns (Table 9), is missing from (a), so the reader compares an identity count against a success gap.
  - "Order-invariant heap" misnames the mechanism. The heap is priority-ordered, and what is invariant is frontier evolution under submission order. The previous label, "Submission-order invariant heap", was accurate.
  - The old caption's "on the same additive task family" was dropped, and nothing now says the panels differ.
- **Fix:** In fig_contracts.py, set (a) to "48/48 additive pairs identical (24 tasks)\nrandom-valid − exact = +0.000", read from Table 9's source `synthesis-v1/baseline-contrasts.csv` random_valid_minus_exact_reference for the additive rows. Set (b) to "18/18 pairs divergent (9 tasks)\nrandom-valid − exact = −0.644 [−0.856, −0.422]". Relabel the (a) node "Submission-order-\ninvariant frontier". Caption: "…on 48/48 additive pairs of the 24-task baseline. Under the choice-frontier contract, on a separate 9-task panel with its own uniform-menu control, the identity gate diverges on 18/18 pairs (9 tasks), and random-valid minus exact is −0.644 [−0.856, −0.422]."
- **Fix class:** WORDING
- **Status:** CLOSED (`c08ef50`)

#### 67 · MINOR · Axis 5 (garbled headline sentence) · `iclr2026_conference_abstract.tex`

- **Location:** Abstract p.1 L042-044 (abstract.tex L26) "The paper offers a measurement result, not planning ability, with a per-decision identity check, plus a menu-manipulation probe whose discriminating variant (fixed versus random distractor position) remains unrun."
- **Issue:** The trailing "with a per-decision identity check" attaches to "planning ability". The last sentence of the abstract can be read as "not planning ability with an identity check", and a tired reviewer has to re-read the sentence that states what the paper offers.
- **Fix:** "The paper offers a measurement result and a per-decision identity check, not planning ability. Its menu-manipulation probe is reported, but the discriminating variant (fixed versus random distractor position) remains unrun."
- **Fix class:** WORDING
- **Status:** CLOSED (`c08ef50`)

#### 68 · MINOR · Style rules (comma splice introduced by the finding-61 insertion) · `iclr2026_conference_related_work.tex`

- **Location:** Related Work p.3 L128-130 (related_work.tex L14) "Research on multimodal training documents VQA models relying on language priors rather than image content, video-language evaluation reports selection bias toward answer positions (Zhu et al., 2020; Loginova et al., 2025)."
- **Issue:** Splitting the sentence for the Zheng citation removed its coordinating "and". What is left is two independent clauses joined by a comma, and it cites two works for two claims without saying which supports which.
- **Fix:** "Research on multimodal training documents VQA models relying on language priors rather than image content \citep{zhu2020overcoming}, and video-language evaluation reports selection bias toward answer positions \citep{loginova2025addressing}."
- **Fix class:** WORDING
- **Status:** CLOSED (`c08ef50`)

### What would change the verdict

The paper is now honest almost everywhere. The claim wording from review 18 landed. Every number, including those in the newly commented appendix blocks, traces to a pinned artifact. The title and Figure 1 now carry the real update. The only thing still holding it at WEAK REJECT is finding 49's value anchor, and that waits on #134. The same-runtime counterfactual, with serials assigned in submission order, would show whether the per-decision identity check can return "divergent" on the additive cells when frontier choice becomes consequential. Once that result is reported with its divergence counts, and the Contribution 1, Figure 1, and 5.2 wording is narrowed as prescribed under 49 and 66, the paper moves to BORDERLINE. The M4 task-cluster intervals (finding 60, also #134) would then settle whether the post-hoc label reading survives clustering. The remaining MINOR items (51, 53, 56, 15-regression, 66-68) are all WORDING and cost no page budget. Moving past BORDERLINE still requires what 5.11 names: a fresh frozen choice-frontier panel with at least eight discriminative tasks, and one comparator between random-valid and exact.

## Live fixlist — review 18 (2026-09-23)

**Verdict:** WEAK REJECT. 0 CRITICAL, 6 MAJOR (findings 49-54), 13 MINOR (the partial remainders of findings 44 and 45, plus findings 55-65). Most damaging issue: **finding 49**. The headline measurability result is, by the paper's own statement, "a property of this controller, not additive best-first search in general", and no published evaluation is shown to use the contract the audit exposes. The value claim therefore rests on an anchor the paper never supplies.

Genre: BENCHMARK (+ FINDINGS)
Δbelief: On the authors' own additive best-first runtime, the grounded-menu enumeration contract makes random-valid decision-identical to exact (48/48), so its success rows measure operation validity. A choice-frontier redesign separates the controls (−0.644), but the first adapter does not beat uniform frontier choice. Title, abstract, and Fig. 1 do not surface this update as one belief (finding 50).
Ledger: Verified: 37, 38, 39, 41, 42, 43, 46, 47, 48, 9 (remainder), 11 (remainder) · Partial: 44, 45 · Regressed: none · Not addressed: none · Wontfix: 40 (unchanged at App U, p.28 L1511) · Review-16 spot-check 1-36: no regression · New: 49-65

**Reviewer summary:**

> Round-3 adversarial re-review of HEAD `19a641b`. I read the rendered PDF text in full (29 pages), every section file, the hub, the log/blg, both figure PNGs, and both figure scripts. I re-derived every headline number directly from the pinned artifacts, not from the section text. For the menu block I re-derived from the 36 distractor episode records (chance 0.5919/0.6252 over 60 decisions; episode-length histogram {1: 20, 2: 8, 3: 8}; 36/36 rejected emissions are injected distractors). For the baseline I tallied the 1,152 episode files (125/240/0/288, with random-valid 45 BFS + 51 BFWS). The ledgers are Σ attempts[].gpu_hours in four budget files. Every checked number matches its artifact. The build is clean (0 errors, 0 warnings, 0 undefined, 0 overfull, 0 BibTeX warnings, 29 pages), and the main text ends on p.9. The round-2 fixes held: 11 of the 14 review-17 items are fully verified, 2 are partial (a residual `\texttt{exact\_reference}` in the Discussion and a residual "headline" label in App S), and 40 stays WONTFIX. The remaining defects are about what the paper is worth, not about transcription. (1) The headline identity result is conceded to be a property of the authors' own controller, and no external evaluation is shown to share it (finding 49). (2) The title asks a capability question, and the only body figure shows a null zoo, so the 10-minute test lands on the wrong belief (finding 50). (3) Menu manipulation is shipped as a reusable "hygiene check", but by the paper's own account neither receipt discriminates anything, and the discriminating variant was never run (finding 51). (4) The Conclusion's new sentence asserts that the adapter's choices are indistinguishable from a last-label habit. That claim is post-hoc, reads as equivalence, and conflicts with the paper's own M4 numbers (finding 52). (5) About twenty numeric paragraphs and tables carry no adjacent artifact comment (finding 53). (6) Section 5.4 states "shows no intrinsic modality effect", an absence claim that the Appendix and Discussion themselves decline (finding 54).

### Build, page count, figures

- **Build (iclr2026_conference.log 22:04:58 and .blg 22:04:03 are newer than every .tex/.bib; newest source is appendix.tex 22:04:48):** 0 errors (`^!` count 0), 0 LaTeX warnings, 0 package warnings, 0 undefined references or citations, 0 overfull boxes (41 underfull only), 0 BibTeX `Warning--` lines, 40 bib entries used, 40 `\bibitem`s. The log reads "Output written on iclr2026_conference.pdf (29 pages, 377527 bytes)". **PASS.**
- **Page count:** The Conclusion ends on **PDF p.9** (L462), and the Reproducibility Statement and References begin on the same page. Main text (title through Conclusion) = **9 pages**, against the 9-page limit. **PASS**, with zero slack: any added body sentence must be offset.
- **fig:zoo-m1 (Figure 1, p.8):** the plotted values and CIs in `fig_zoo_m1.py` L17-23 match `o4/metrics/analysis.json` arms.*.m1_auc / m1_task_cluster_95pct_ci_10000_seed133 exactly. Tick labels now use prose names. The line reads "random-valid reference", and the word "floor" is gone from the reader surface (the script variable `FLOOR` at L25 is internal only). About 60% of the x-range (0.3-0.8) is empty, but that is cosmetic. Content defect: finding 50.
- **fig:contracts (Figure 2, App T, p.29):** 48/48 and −0.644 [−0.856, −0.422] match identity-audit.json and v1/evaluation/analysis.json. The node boxes are no longer clipped (fig_contracts.png inspected; axes padded at L33). Placement defect: finding 50.

### Numbers re-check

| claim | PDF location | artifact : key | match |
|---|---|---|---|
| random-valid ≡ exact on 48/48 additive pairs | p.1 L016, p.2 L058, p.5 L254 | `outputs/native-arms/v1/identity-audit.json` : pairs_checked 48, pairs_identical 48, mismatches [] | yes |
| permutation 36/36, 0/512 | p.1 L019, p.6 L307-308, Table 13 | `outputs/native-arms/v1/stress-evaluation.json` : cells["menu\|menu-permutation\|*\|*"] successes 9×4, invalid 0, decisions 128×4 | yes |
| distractor 0/36, 36/60 invalid, pick-rate 0.6 | p.1 L021, p.6 L309-310, Table 13 | stress-evaluation.json : distractor.{decisions_with_injection 60, distractor_picks 36, pick_rate 0.6}; distractor-injection cells successes 0, invalid 9 each | yes |
| chance 0.592 to 0.625 | p.1 L022, p.6 L310-311 | `native-arms/v1/evaluation/episodes/menu/*/*/*distractor-injection-learned_adapter.json.gz` : mean k/(k+rows) over events[].view.injected_distractors vs input.successor_candidates.rows (all rows 0.5919, unpruned 0.6252, n=60) | yes |
| 20/36 end on the first decision; every episode ends on a distractor pick | p.6 L311 | same files : len(events) histogram {1: 20, 2: 8, 3: 8}; 36/36 rejected raw_output ∈ injected_distractors | yes |
| R2 masked 18/18 all-invalid per cell; shuffled text 16/18 partial, 2/18 all-invalid, 0 goal, 18/49; shuffled multimodal 15/18, 0, 3/18, 15/105 | p.25-26 L1348-1373 | `outputs/native-arms/v1/r2-decomposition.json` : cells["text-masked\|*"], cells["text-shuffled\|text-state"], cells["text-shuffled\|multimodal-state"] | yes |
| R2 cross cell 0/18, every episode all-invalid | p.26 L1374-1375 | stress-evaluation.json : cells["textmask\|text-masked\|visual-state\|*"] 9+9 episodes, 0 successes, 18 invalid / 18 decisions | yes |
| native arms 18/18 each, published visual 16/18, +0.111 [0.000, +0.278] (both), seq−nomem 0.000, learned−base +1.000, corruption 0.000 [0.000, 0.000] | p.6 L321-323; p.26-27 L1408-1417 | `outputs/native-arms/v1/evaluation/analysis.json` : summary.clean_learned_success, published_visual_learned_success 0.8889, contrasts.{nomem_vs_published_visual, seq_vs_published_visual, ladder_seq_minus_nomem, *_learned_minus_base, corruption:*} | yes |
| native arms 216/216 + 72/72 replayed | p.16 L826, p.27 L1404-1405 | `native-arms/v1/evaluation/evaluation.json` : bindings_total 216, episodes_replayed 216, comparator_episodes_replayed 72 | yes |
| R4 10/10 and 10/10 per arm, base 0/40 | p.27 L1424-1426 | stress-evaluation.json : cells["variants\|*"] 8 × (10 episodes, 5 successes, 5 invalid); learned/base split per issue-130-closeout R4 | yes |
| R3 InternVL 31/36 (11/12, 10/12, 10/12), base 0/36 | p.2 L069, p.6 L284, p.24 L1287-1288 | `expanded-study/v1/second-backbone-v3/evaluation/analysis.json` : by_modality.*.internvl.process_sft_successes; `evidence.json` : by_condition.process_sft 31/36, pretrained_base 0/36 | yes |
| R3 rates .00546/.01220/.01258; usage 183/164/159 of 390; SFT−base +0.917 [+0.750, +1.000], +0.833 [+0.583, +1.000]; SFT−RV −0.083 [−0.250, 0], −0.167 [−0.417, 0] | p.24 L1288-1295 | analysis.json : by_modality.*.invalid_operation_rates.process_sft, decision_usage, contrasts[] | yes |
| R3 random-valid "24/24 per modality" | p.2 L069, p.6 L284 | analysis.json : by_modality.*.internvl.random_valid_successes 24 with episodes 12; evidence.json comparator_episodes 144 vs expected 72 (double count; see finding 57) | yes (number), misleading basis |
| choice-frontier table 18/18, 7/18, 0/18, 32/90 | p.7 Table 1 | `outputs/choice-frontier/o4/metrics/all-episode-metrics.json` : records[multiplier=2].solves["2"] per arm (18, 7, 0, 32 of 18/18/18/90) | yes |
| +0.389 [+0.167, +0.611] | p.1 L030, p.2 L078-079, p.7 L355 | `outputs/choice-frontier/v1/evaluation/analysis.json` : contrasts.learned_minus_pretrained_base.{mean, ci95} | yes |
| +0.033 [−0.033, +0.133] | p.1 L031, p.2 L079, p.7 L356 | analysis.json : contrasts.learned_minus_random_valid.{mean, ci95}; note descriptive_only **false** in the artifact while the text rules it descriptive per issue-132-closeout Erratum item 3 (no source-conflict comment; finding 53) | yes |
| −0.644 frozen [−0.856, −0.422] | p.1 L027, p.2 L077, p.7 L354, Fig. 2 | analysis.json : contrasts.random_valid_minus_exact_reference.{mean −0.6444, ci95} | yes |
| task-clustered [−0.889, −0.333] and [0.000, +0.100] | p.1 L028, p.2 L077, p.27 L1445-1446 | `docs/experiments/choice-frontier/issue-132-closeout.md` Erratum item 2 (no JSON key exists) | yes (doc source) |
| gate 9/9 tasks, 18/18 divergent, coincident control sequences | p.1 L025-026, p.7 L350 | `choice-frontier/v1/evaluation/identity-audit.json` : pairs_checked 18, pairs_divergent 18, verdict CHOICE_SENSITIVE; pairs[].exact/random_valid_seed17 identical across greedy/w3 for every task; final-audit.json ok true, episodes_replayed 144 | yes |
| zoo M1 .1042 [.0278, .2014], .1389 [.0250, .2722], .8472 [.7917, .8750], .0694 [0, .1528], .1250 [0, .2778], .0556 [0, .1389], 0 | p.1 L033-034, Table 2, Fig. 1 | `o4/metrics/analysis.json` : arms.*.m1_auc, arms.*.m1_task_cluster_95pct_ci_10000_seed133 | yes |
| M2 ρ / M3 κ (1.432/1.025, 1.407/1.000, 1.613/1.000, 1.452/1.000, 1.549/1.050) | Table 2 | analysis.json : arms.*.m2_solved_only_geometric_rho_task_weighted, m3_solved_kappa_mean_task_weighted | yes |
| 2× 6/18, 6/18, 4/18; 3×/4× 42/90 50/90, 8/18 10/18, 8/18 12/18, 6/18 8/18 | Table 2 | all-episode-metrics.json records[multiplier=2]; analysis.json : additional_cpu_3x_4x_not_primary_m1.*.{3,4}.{episode_count, failed_count} | yes |
| paired M1 −0.035 [−0.150, +0.061] | p.1 L034-035 | analysis.json : m1_m2_m3_dominance_holm.comparisons.random_valid.m1_auc.{difference_favoring_learned −0.03472, cluster_bootstrap_95pct_ci} | yes |
| 15-test Holm, no positive dominance, 3 undefined | p.7 L376-377 | analysis.json : m1_m2_m3_dominance_holm.{scope, undefined_tests 3}, comparisons.*.dominance.inferential_positive_after_holm false ×5 | yes |
| M4 17.4% (23/132) vs 26.9%, last label 54.5% (72/132), first label 2.3% | p.7 L374-375, p.28 L1462-1464 | analysis.json : arms.learned_adapter.m4_teacher_agreement.{observed 0.1742, chance 0.2693, on_policy_decisions_k_ge_2 132, selected_last_rate 0.5455, selected_first_rate 0.0227} | yes |
| M5 .3125 / .075 / .625, storage only | p.28 L1466-1468 | analysis.json : m5_D_descriptive.*.m1_auc; m5_informative_tasks_D ["…storage-compact-919000"] | yes |
| baseline SFT 125/288, RV 240/288 (96 BFS/BFWS), base 0, exact 288; BFS/BFWS RV 15/24, 17/24 per modality | p.2 L064-065, p.5 L269-271, Table 8 | `outputs/expanded-study/v1/baseline/episodes/*/*/*.json.gz` : result.goal_reached tallied (bfs RV 45/72, BFWS RV 51/72, SFT 0/72 each; w3 SFT 60/72, greedy 65/72) | yes |
| BFWS dev 0.933 vs 0.467, LB 0.2 | p.1 L037, p.5 L262-264 | `docs/issue-59-bfws-structural-gate.md` L250-253 (0.933333, 0.466667, 0.2); no JSON located this round | yes (doc source) |
| program ledger 68.5244 / 336 | p.5 L238 | `expanded-study/v1/budget.json` : Σ attempts[].gpu_hours = 68.52441; schedule.experiment_gpu_hours_cap 336 | yes |
| native-arms 3.2086 / 12 | p.17 L899, p.21 L1127 | `native-arms/v1/budget.json` : Σ attempts[].gpu_hours = 3.20857; schedule.authorization.window_gpu_hours_cap 12.0 | yes |
| R1-R4 7.7998 / 36 (resized from 20, 29% of 27.04) | p.17 L900-902, p.21 L1127-1130 | `outputs/reviewer-v130/v1/budget.json` Σ 3.98625 (cap 20) + `v2/budget.json` Σ 3.81354 (cap 36) = 7.79978; 7.7998/27.04 = 28.8% | yes |
| choice frontier 1.069 / 12 (0.81 + 0.052 + 0.208) | p.17 L902-903, p.27 L1442 | `choice-frontier/v1/budget.json` : Σ attempts[].gpu_hours = 1.06939 (train 0.40893+0.40115, smoke 0.05175, eval 0.17972+0.02783) | yes |
| Table 4 caps sum to 336 (52.11 = 40 + 12.11, 11.89 = 24 − 12.11) | p.16 Table 4 | expanded-study/v1/budget.json : schedule.allocations_gpu_hours | yes |

**Adjacent `%` artifact comments:** a line-level scan of all nine section files found numeric prose with no adjacent comment naming an artifact. Examples are abstract.tex L18 (+0.389, 7/18) and L23 (0.933/0.467), App F L375-397 (seed table and Cell B), and App M L627-679, which covers matched modality, generalization v2, DAgger, successors, curriculum, transfer, and Tables 10-11. Further gaps are App N L706-709, App O L715 and Table 12, and App D L213 (BFWS corpus). Several other comments name the superseded `content_brief.md` or a closeout table instead of the pinned JSON (results.tex L50, L59, L125; appendix.tex L554). Details are in finding 53. No number mismatch was found.

### Verification of review-17 findings

| # | sev (r17) | r18 result | evidence at `19a641b` |
|---|---|---|---|
| 9 (remainder) | MINOR | VERIFIED | Abstract p.1 L027-028 / abstract.tex L13 carries "post-hoc task-clustered [−0.889, −0.333]". |
| 11 (remainder) | MINOR | VERIFIED | App O p.25 L1337 "Copyability-preserving text shuffling lowers success by up to −0.944"; L1344 "This contrast pools the output-contract-destruction (masked) regime" (appendix.tex L715). |
| 37 | MAJOR | VERIFIED | "floor" is absent from reader surfaces. Fig. 1 reads "random-valid reference" (fig_zoo_m1.py L30). The caption p.8 L399 says "random-valid uniform-choice reference". 5.10 p.7 L372-374 (results.tex L171) says "No comparator between random-valid and exact exists on this panel, so the zoo bounds the adapter only against weaker-than-random rules and cannot calibrate choice quality". App R p.27 L1447 says "uniform-choice reference". |
| 38 | MAJOR | VERIFIED | Abstract p.1 L034-035 "and below random-valid (.1389), with paired contrast −0.035 [−0.150, +0.061]". 5.10 p.7 L374-375 gives the M4 sentence. The Conclusion p.9 L459-460 carries the prescribed wording (its content is contested in finding 52). |
| 39 | MAJOR | VERIFIED | App B p.14 L733/L737-745 (appendix.tex L117, L122-124) pins the equal-f serial tie-break, `start_expansion` pre-submission serials, heap tuple (priority, serial, state id, g), `finish_expansion` full-set requirement, and the submission-order counterfactual. Checked against `examples/planning_benchmark_slice/best_first_controller.py` L132, L223-227, L284-286, L340-343: exact. 5.2 p.5 L254-256 carries the structural basis. Its pointer resolves to the wrong appendix (finding 56). |
| 40 | MAJOR | WONTFIX (unchanged) | App U p.28 L1511 / appendix.tex L905 is verbatim as dictated. Not re-argued. |
| 41 | MINOR | VERIFIED | Intro p.2 L064-065 "125 of 288, all of them in the additive cells, against 240 for random-valid (96 in the choice-registering BFS/BFWS cells)". Tallied: 45+51 = 96. |
| 42 | MINOR | VERIFIED | Intro p.2 L066-067 and Contribution 3 p.2 L099-100 "the dominant learned failure (229/407) is an invariant rejection of a parsed, applicable operation". |
| 43 | MINOR | VERIFIED | Discussion p.9 L437-439 "the menu is the only retained input that could carry the operation-validity signal on this panel". |
| 44 | MINOR | **PARTIAL** → CLOSED (`640467b`) | Fixed: (a) the caption says "Intervals of all non-exact arms overlap" (p.8 L400-401); (c) the enumeration-contract note moved to the caption; the figure uses prose names. **Remaining (b):** discussion.tex L28 `\texttt{exact\_reference} solves by construction of the budget` renders as a code identifier with a lowercase item start (p.9 L447 "Imitation target. exact reference solves…"). Fix under finding 65. Remainder severity MINOR. |
| 45 | MINOR | **PARTIAL** → CLOSED (`640467b`) | Fixed: one seed table (Table 6), one receipts table (Table 4), Cell A renamed "the greedy × multimodal replication cell" (p.18 L918, L963). **Remaining:** App S p.28 L1485 (appendix.tex L850) still says "Cell A covers one of the three pooled headline modalities", the same legacy "headline" framing for a cell whose SFT − random-valid is negative at every seed. Fix under finding 65. Remainder severity MINOR. |
| 46 | MINOR | VERIFIED | No "[TODO" in the PDF text. The markers are converted to prose (Design p.5 L222-223 "The BFWS-to-BFS panel overlap is not pinned in the retained manifests"; 5.11 p.7 L409-410, Discussion p.9 L452-453, and Repro p.9 L469-470 "Code and evidence bundles will be provided as anonymous supplementary material"). Ticket references are kept in `%` comments. |
| 47 | MINOR | VERIFIED | The Reproducibility Statement is one pointer paragraph (p.9 L466-470). It hard-codes appendix letters (finding 56). |
| 48 | MINOR | VERIFIED | fig_contracts.png shows no clipped boxes. `ax.set_xlim(-0.03, 1.03)` is at fig_contracts.py L33. |
| 1-36 (spot-check) | — | no regression | Checked in the PDF: #1 additive scoping (p.1 L013-017), #2 "uninformative about order" and the chance band (p.6 L308-313), #3 20/36 (p.6 L311), #4 point-estimate wording (p.1 L033-034), #5 R2 counts (p.26), #6 9 pages, #7 "consistent with an algorithm (choice-requirement) difference" (p.25 L1299), #8, #10 identical provenance sentence (Design L211-212, App I L1075-1076, App R L1435-1436), #12 no "remain open", #13 identity audit is 5.2, #18 no GitHub/institution in the PDF and empty metadata, #20 0/40, #23 0 prose semicolons in main text (all 9 hits are citation separators), #33 68.5244/336, #36 "confirms" only in App H. #29's residual is raised as finding 57. |

**Tally:** 11 verified (37-39, 41-43, 46-48, and the 9/11 remainders), 2 partial (44, 45), 1 WONTFIX unchanged (40), 0 regressed, 0 not addressed.

### New findings

#### 49 · MAJOR · Axis 1 (value anchor: published practice) / BENCHMARK checklist (gap) · `iclr2026_conference_abstract.tex; iclr2026_conference_introduction.tex; iclr2026_conference_related_work.tex; iclr2026_conference_results.tex (5.2)`

- **Location:** Abstract p.1 L013-017 (abstract.tex L6) and L040-042 "The paper offers a measurement result and two cheap hygiene checks"; Contribution 1 p.2 L089 "A measurability audit for grounded-menu search evaluation" (introduction.tex L31); 5.2 p.5 L256 "This is a property of this controller, not additive best-first search in general" (results.tex L38); App B p.14 L744-745 "A runtime assigning serials in submission order would not be submission-order invariant and would not show this identity"; Related Work p.3 L130-137.
- **Issue:** The paper itself concedes that the 48/48 identity comes from its own runtime's serial rule and full-candidate submission, not from grounded menus or additive search. Related Work then cites Jericho and CALM to show that valid-action access is already a known evaluation handicap. The reader is left with two readings. Either the belief update is one the field already holds (admissible-action lists inflate success), or it is a bug report on the authors' own prior contract. The paper names no published search-execution, agent, or planning evaluation whose interface has the property the audit detects: complete-candidate submission into an order-invariant frontier. The contribution is framed as an audit "for grounded-menu search evaluation", but the only evidence that it finds anything is on the system it was built to debug. The portable value, a per-decision random-vs-reference identity check, is real but untested outside this runtime. A falsifiable portable claim would need a second interface on which the check was run, with a prediction for each. (Novelty anchor checked: the admissible-action handicap is established practice in text games, Hausknecht et al. 2020, https://arxiv.org/pdf/1909.05398, verified in review 16.)
- **Fix:** Either (a) name at least one published evaluation interface that uses complete-candidate submission with an order-invariant frontier, with a citation, and state that the identity check applies there; or (b) run the per-decision identity check on one external or alternative interface, for example this runtime with serials assigned in submission order, which App B predicts would *not* show the identity. Report divergent and identical counts for both. That is a killer test with opposite predictions. Otherwise narrow Contribution 1 and the abstract to what is shown: "A per-decision identity check that exposed zero decision headroom in our own grounded-menu contract. The identity follows from this runtime's pre-submission serial rule and would not hold under submission-order serials." **Experiment that would change the verdict:** (b), because it turns the audit from a post-hoc diagnosis into a check with a demonstrated negative case.
- **Fix class:** MEANING
- **Status:** CLOSED (`59e8714`; #134 R1: same-runtime counterfactual 48/48 identical under the executed serial rule vs 19/48 divergent under submission-order serials, pre-registered >24/48 prediction reported as failed in 5.2, Abstract, Introduction, Discussion; fig:contracts caption carries 19/48)

#### 50 · MAJOR · Axis 1 (10-minute test) / Axis 5 (buried contribution) · `iclr2026_conference.tex (title); iclr2026_conference_results.tex (fig:zoo-m1 placement); iclr2026_conference_appendix.tex (fig:contracts); iclr2026_conference_introduction.tex L21`

- **Location:** Title p.1 L001-002 "Can Vision-Language Models Learn to Execute Classical Search Algorithms?" (hub L19); Abstract p.1 L040-042 "…not planning ability"; Figure 1 p.8 (zoo M1, every non-exact interval overlapping); Figure 2 p.29 App T (the identity-versus-separation tension); Intro p.2 L074 "The redesign (Figure 2)".
- **Issue:** A skimming reviewer's 10-minute test gives three conflicting signals. The title promises a capability answer. The abstract closes by saying capability is not what the paper offers. The only body figure is a null result in which "the Holm family licenses no ordering". The figure that carries the paper's actual tension (random-valid ≡ exact 48/48 under one contract, −0.644 under the other) sits on page 29 behind the references. The title is also a question, which the style rules discourage, and the paper's evidence answers "cannot be measured on the additive cells, and 0/24 on BFS/BFWS", not "yes" or "no". The update exists in the body (Axis 5 buried contribution), but the surfaces that set the reader's belief point elsewhere.
- **Fix:** Retitle to the measurement claim, e.g. "When Random-Valid Equals the Reference: A Per-Decision Identity Audit for Search-Execution Evaluation of Vision-Language Models". Swap the figures: make fig:contracts Figure 1 in 5.2 (it is 0.65 column width against 0.75 for the zoo figure, so page-neutral), and move fig:zoo-m1 to App R with Table 2 kept in the body. Keep the page budget at 9.
- **Fix class:** MEANING
- **Status:** CLOSED (`83e30c2`)

#### 51 · MAJOR · BENCHMARK checklist (operationalization: instrument validity) / Axis 2 (falsifiability) · `iclr2026_conference_abstract.tex; iclr2026_conference_introduction.tex (Contribution 1); iclr2026_conference_results.tex (5.7); iclr2026_conference_discussion.tex`

- **Location:** Abstract p.1 L040-042 "two cheap hygiene checks, per-decision identity and menu manipulation"; Contribution 1 p.2 L091-092 "The audit is two cheap checks, a per-decision identity test and menu manipulation by permutation and distractor injection"; 5.7 p.6 L307-315 (results.tex L83) "uninformative about order under the submission-order invariance", "Content-reading and position habits both predict a pick-rate near 0.6, so this receipt does not separate them, and the fixed-versus-random-position test that would has not been run"; Conclusion p.9 L457-458 "cheap identity and menu audits expose this".
- **Issue:** Half of the shipped audit has no demonstrated discriminating power, by the paper's own account. Permutation is uninformative wherever the identity check already fires, because any listed candidate succeeds. Distractor injection returns a pick-rate at chance (0.6 against 0.592-0.625), which the text says content-reading and position habits both predict. Its only informative output, "does not reject schema-valid inapplicable entries", is equally implied by the runtime's reject-and-terminate design plus a policy that never saw distractors in training ("these out-of-distribution distractors never appeared in training menus", L313). Menu manipulation therefore could not have lost on this panel. Recommending it to other evaluators as a "hygiene check" is a claim about instrument validity that no executed result supports. The Conclusion's "menu audits expose this" credits it with exposing the measurability failure, which only the identity check did.
- **Fix:** Either run the fixed-versus-random-position distractor test that 5.7 names (the same 36 native-adapter episodes, with distractors at the first position, the last position, and random positions). Report the pick-rate by position against the per-position chance rate. Keep menu manipulation as a contribution only if the two arms separate. Or demote it: in Abstract and Contribution 1, write "a per-decision identity check, plus a menu-manipulation probe whose discriminating variant (fixed versus random distractor position) remains unrun". In the Conclusion, write "a cheap per-decision identity audit exposes this". **Experiment that would change the verdict:** the fixed-versus-random-position test, because it is the only design under which content-reading and position habits predict different pick-rates.
- **Fix class:** MEANING
- **Status:** CLOSED (`9de44ad`)

#### 52 · MAJOR · Axis 4 (claim outpacing evidence) / claim discipline (post-hoc label, no equivalence) · `iclr2026_conference_discussion.tex (Conclusion); iclr2026_conference_results.tex (5.10); iclr2026_conference_appendix.tex (App R)`

- **Location:** Conclusion p.9 L458-460 (discussion.tex L42) "the adapter learns to emit valid choices without choice behaviour distinguishable from a last-label position habit"; 5.10 p.7 L374-375 "Post-hoc M4 finds 17.4% heap-head agreement against 26.9% chance and 54.5% last-menu-label emissions"; App R p.28 L1465-1466 "a last-label habit acts operationally as a random picker".
- **Issue:** The Conclusion's key sentence makes three errors. (a) It rests on post-hoc M4 but carries no post-hoc label, which the binding claim discipline requires for post-hoc analyses. (b) "Not distinguishable from X" is an equivalence-flavoured statement with no pre-registered margin, and it has no adjacent non-equivalence sentence (the paper's own rule, App F p.18 L945-947). (c) The numbers argue against it. Under per-decision seeded permutation, a pure last-label habit predicts heap-head agreement at chance (≈26.9%) and a last-label rate near 100%. The observed values are 17.4% (below chance) and 54.5%, with no interval (finding 60). No last-label comparator was run in the zoo. There is also an unexamined non-positional pattern. On all six solved depot/elevators/ferry cells the adapter's expansion counts equal `bfs-order`'s exactly (8/6/7 on both algorithms; `o4/metrics/all-episode-metrics.json` records[arm ∈ {learned_adapter, bfs-order}, multiplier 2].expansions). The #132 erratum records the same coincidence against the frozen BFS reference (issue-132-closeout.md L131-132). [INFERENCE] This is weak evidence, since random-valid seed 17 reaches 7/6/7 on the same tasks, but it is an alternative the sentence silently excludes. The adjudication record adopted the stricter rule that declines generalized negative mechanism claims before a pre-registered follow-up (metric-adjudication-2026-09-23.md L118-125).
- **Fix:** Replace the sentence with: "The choice-frontier redesign separates the controls, and the adapter learns to emit valid choices without demonstrated choice quality. Its solve-versus-budget score lies below random-valid (paired −0.035 [−0.150, +0.061], which is not equivalence), and a post-hoc label audit finds 54.5% last-label emissions." Add the post-hoc label and the non-equivalence clause wherever the last-label reading appears in the body.
- **Fix class:** MEANING
- **Status:** CLOSED (`9de44ad`)

#### 53 · MAJOR · Compliance (binding rule: every number carries an adjacent `%` artifact comment) · `iclr2026_conference_abstract.tex; iclr2026_conference_results.tex; iclr2026_conference_appendix.tex`

- **Location:** No adjacent comment naming an artifact:
  - abstract.tex L18 (7/18, +0.389 [+0.167, +0.611]) and L19 (+0.033). The only nearby comments, L20-21, name o4/analysis.json, which holds none of these numbers.
  - abstract.tex L23 (0.933 vs 0.467). No comment at all.
  - appendix.tex L213 (BFWS corpus: 69,019 / 67,215 / 47,780 / 21,239).
  - L375-400 (seed-replication protocol, Table 6, Cell B 0/72).
  - L627-679 (matched modality 5/12, 6/12, 6/12; generalization v2 128/150 and family/modality splits; DAgger Table 10; successors 45/45 → 1/45, 65/109, 119/1,536; curriculum intervals; transfer Table 11 and p = 0.8156 / 0.0227).
  - L706-709 (failure calibration 905/447/229/144/155/56 of 546).
  - L715 and Table 12 (corruption deltas).
  - Table 3 (L71-96; the L69 comment names only "issue #125").

  Comments that name a superseded or non-pinned source instead of the pinned JSON: results.tex L50 and appendix.tex L554 ("content_brief.md", marked superseded in changelog.md L42); results.tex L59 (matched modality "per content_brief.md"); results.tex L125 (Table 1 "issue-132-closeout.md, Frozen panel evaluation table" rather than `choice-frontier/v1/evaluation/{evaluation,cells}.json`). There is also no source-conflict comment for `choice-frontier/v1/evaluation/analysis.json` contrasts.learned_minus_random_valid.descriptive_only = false, although the text rules that contrast descriptive (results.tex L128, appendix.tex L350).
- **Issue:** The brief makes the adjacent artifact comment binding for every number. Roughly twenty numeric paragraphs and tables do not meet it, and the uncovered ones are exactly the appendix blocks migrated in Wave 2. A reproducer checking App M or App N has no path to the JSON. Where the artifact and the text disagree on a flag (descriptive_only), the disagreement is undocumented.
- **Fix:** Add one `% Evidence:` line per paragraph or table naming the pinned file and key. Examples: `outputs/expanded-study/v1/seed-replication/…` for Table 6; `outputs/expanded-study/v1/dagger/…`, `…/successor/…`, `…/curriculum/…`, `…/transfer-paired-analysis.json` for App M; `docs/experiments/expanded-study/failure-mechanism-analysis.md` with its table for App N and Table 3; `docs/issue-59-bfws-structural-gate.md` L250-253 for the 0.933/0.467 abstract line; `choice-frontier/v1/evaluation/analysis.json` contrasts.* for abstract L18-19. Replace every `content_brief.md` source with the synthesis README or JSON it summarized. Add `% Source conflict: analysis.json descriptive_only false; the Erratum item 3 one-task rule governs the prose` at results.tex L129.
- **Fix class:** WORDING
- **Status:** CLOSED (`640467b`)

#### 54 · MAJOR · Axis 4 / claim discipline (absence claim without a margin) / Axis 3 · `iclr2026_conference_results.tex (5.4)`

- **Location:** 5.4 p.6 L280 (results.tex L58) "Matched modality (process SFT 5/12, 6/12, 6/12 versus 10/12 random-valid per modality) shows no intrinsic modality effect"; contrast App M p.23 L1212 "The evidence does not support an intrinsic modality effect", Discussion p.9 L440 "the evidence does not support an intrinsic modality effect", Conclusion p.9 L460-461 "establish neither … an intrinsic modality effect".
- **Issue:** "Shows no effect" asserts absence from a 3-problem panel (12 episodes per modality) under a saturating reference, with no interval and no margin. The binding discipline forbids equivalence claims without a pre-registered margin. The same paper states the correct, weaker boundary three times elsewhere, so the 5.4 wording is also an Axis 3 inconsistency.
- **Fix:** "Matched modality (process SFT 5/12, 6/12, and 6/12 versus 10/12 random-valid per modality, a 3-problem panel) does not support an intrinsic modality effect, and non-significance is not equivalence".
- **Fix class:** MEANING
- **Status:** CLOSED (`9de44ad`)

#### 55 · MINOR · Axis 4 (overclaimed causality; limitation recast as control) · `iclr2026_conference_results.tex (5.4); iclr2026_conference_appendix.tex (App M)`

- **Location:** 5.4 p.6 L284-285 (results.tex L58) "isolating the vision stack rather than the shared Qwen3-8B LLM family"; App M p.25 L1304-1305 (appendix.tex L697) "so both cells isolate the vision tower, connector, image tokenization, and multimodal recipe, not the LLM backbone"; artifact `second-backbone-v3/evaluation/analysis.json` architecture_note: "…and it is reported as an architecture-difference limitation".
- **Issue:** The artifact records the backbone difference as a *limitation*. The prose turns it into an isolating design. Nothing is isolated. The LLM weights differ after each vendor's multimodal training, the panel is a key-cell subset, and the cross-backbone contrast is explicitly unpaired. The within-InternVL contrast in the same sentence (BFS 0/36 against greedy 31/36) varies the algorithm, not the vision stack.
- **Fix:** 5.4: "…(base 0/36, random-valid saturating), an unpaired architecture comparison because the two backbones differ in vision tower, connector, tokenization, and multimodal training (Appendix M)". App M: "InternVL3.5-8B shares the Qwen3-8B LLM family, so the comparison differs in the vision tower, connector, image tokenization, and multimodal recipe, and it is reported as an architecture-difference limitation".
- **Fix class:** MEANING
- **Status:** CLOSED (`9de44ad`)

#### 56 · MINOR · Axis 3 (cross-reference resolves to the wrong appendix) · `iclr2026_conference_results.tex; iclr2026_conference_reproducibility.tex`

- **Location:** 5.2 p.5 L256 "not additive best-first search in general (Appendix A)" (results.tex L38 `Appendix~\ref{appendix}`); `\label{appendix}` sits on Operation Schemas (appendix.tex L22), while the pinned mechanism is in App B, Algorithm Invariant Definitions (appendix.tex L99-124, no label). Reproducibility p.9 L466-468 hard-codes "Appendix C … D … E … F" (reproducibility.tex L11).
- **Issue:** The one sentence that answers finding 39 sends the reader to the wrong appendix. App A says only "under the declared tie-breaking rule". Hard-coded letters in the Reproducibility Statement break silently on any appendix reorder, against the prose-name convention adopted for finding 24.
- **Fix:** results.tex L38: "(Algorithm Invariant Definitions appendix)", matching App R L839. This avoids adding a label, which the hub's frozen-label rule (hub L67-68) forbids for cross-file references. Replace the letters in reproducibility.tex with prose names ("the Trusted Search Runtime, Data and Split Procedures, Receipt Tables, and Statistics appendices").
- **Fix class:** WORDING
- **Status:** CLOSED (`640467b`)

#### 57 · MINOR · Axis 3 / Axis 5 (incommensurate denominators in the main text) · `iclr2026_conference_introduction.tex; iclr2026_conference_results.tex (5.4)`

- **Location:** Intro p.2 L069 "31/36 (base 0/36, random-valid 24/24 per modality)" (introduction.tex L12); 5.4 p.6 L284 (results.tex L58); App M p.24 L1290-1293 explains "two entries per panel task … from its one reused … control episode"; appendix.tex L693-696 records the double count (analysis.json by_modality episodes 12, random_valid_successes 24; evidence.json comparator_episodes 144 against expected 72).
- **Issue:** Next to 31/36 (12 tasks × 3 modalities), "24/24 per modality" invites the reading 72/72 on 36. The actual basis is 12 tasks per modality, each counted twice from one episode. Review 17 recorded this as the residual of finding 29 but did not reopen it. It is the only main-text count whose denominator cannot be reconstructed from the text.
- **Fix:** Intro and 5.4: "random-valid solves every panel task (24/24 control entries per modality, two per task)". Keep the artifact figure and move the explanation into the text.
- **Fix class:** WORDING
- **Status:** CLOSED (`640467b`)

#### 58 · MINOR · Axis 4 (causal verb from a descriptive calibration) · `iclr2026_conference_results.tex (5.5); iclr2026_conference_appendix.tex (App N); iclr2026_conference_discussion.tex`

- **Location:** 5.5 p.6 L292-293 (results.tex L67) "Process supervision thus teaches well-formed operations but not invariant-consistent frontier intent over a full episode"; App N p.25 L1326-1327 (appendix.tex L709) "process supervision teaches the policy to emit well-formed, source-correct operations"; Discussion p.9 L435-436 "Process supervision yields well-formed operations".
- **Issue:** The calibration is declared "descriptive" (App N L1313). No arm isolates what supervision teaches: there is no format-only or shuffled-target control. "Teaches well-formed operations" is contradicted by the 72/407 learned failures that are malformed outputs and the 56 inapplicable grounded actions (Table 3). "Frontier intent" is undefined anywhere in the paper.
- **Fix:** 5.5: "The calibration is descriptive: after process supervision, most learned failures (229/407) are parsed, source-correct operations rejected by the search invariant, and 72/407 remain malformed outputs." Apply the same narrowing in App N and the Discussion ("after process supervision, most learned emissions parse, and the dominant failure is an invariant rejection").
- **Fix class:** MEANING
- **Status:** CLOSED (`9de44ad`)

#### 59 · MINOR · Axis 4 (interpretation stronger than the unpaired numbers; alternative unnamed) · `iclr2026_conference_appendix.tex (App Q)`

- **Location:** App Q p.27 L1428-1431 (appendix.tex L801) "A post-hoc, unpaired reading … suggests that the scaffold's scalar and bookkeeping text carried no useful signal on these variants".
- **Issue:** On these additive cells the identity audit makes any listed candidate a correct emission (App Q L1421-1422). So the full scaffold's 19/30 shifted-init result reflects emission failures ("All 22 learned failures are single-invalid-operation terminations", App M L1223-1224), not a signal deficit. The reduced contract removes the g/h/f operands the full-scaffold adapters had to emit, and with them the failure surface. "Carried no useful signal" confuses fewer ways to fail with less information.
- **Fix:** "…is consistent with the reduced contract removing scalar operands whose emission the full-scaffold adapters failed, and it does not measure whether that text carried signal, since any listed candidate succeeds on these cells".
- **Fix class:** MEANING
- **Status:** CLOSED (`9de44ad`)

#### 60 · MINOR · Axis 2 (statistical hygiene) · `iclr2026_conference_results.tex (5.10); iclr2026_conference_appendix.tex (App R)`

- **Location:** 5.10 p.7 L374-375 "17.4% heap-head agreement against 26.9% chance and 54.5% last-menu-label emissions"; App R p.28 L1462-1464.
- **Issue:** These are bare proportions over 132 decisions that are clustered in 18 episodes and 9 tasks, with no interval and no test. Agreement is concentrated in the solved tasks: per episode it is 0/7, 0/11, 0/11, 0/9, 1/9 on the unsolved 15puzzle, blocksworld, and hanoi cells against 5/8 and 3/3 on the solved depot-w3 and storage-greedy cells (`all-episode-metrics.json` teacher_agreements/teacher_decisions). So "below chance" may reflect which tasks the adapter fails, not a decision-level bias. Findings 52 and 60 both lean on these numbers.
- **Fix:** Report task-cluster bootstrap intervals (seed 133, 10,000 draws, the zoo's convention) for observed-minus-chance agreement and for last-label rate minus chance. If that is not computed, append "(no interval computed; decisions are clustered within 9 tasks)".
- **Fix class:** MEANING
- **Status:** CLOSED (`59e8714`; #134 R2 task-cluster intervals in 5.4 and App S: last-label minus chance +0.277 [+0.126, +0.402], agreement minus chance −0.069 [−0.161, +0.032] includes zero, below-chance reading dropped, post-hoc label kept)

#### 61 · MINOR · Related-work anchor missing (Axis 4 scope of novelty) · `iclr2026_conference_related_work.tex; iclr2026_conference_related_refs.bib`

- **Location:** Related Work p.3 L125-127 cites position bias only for video-language MCQ (Loginova et al., 2025). 5.7 p.6 L314 and 5.10 p.7 L375 rest on a position-habit reading.
- **Issue:** Option-ID selection bias in LLM multiple-choice selection is established and permutation-diagnosed: Zheng et al., "Large Language Models Are Not Robust Multiple Choice Selectors", ICLR 2024, arXiv:2309.03882. The abstract, fetched via Semantic Scholar on 2026-09-23 (https://arxiv.org/abs/2309.03882), reports that "LLMs are vulnerable to option position changes in MCQs due to their inherent 'selection bias'" arising from token bias. Both the last-label finding and the unrun fixed-versus-random-position test are applications of this known phenomenon, and the paper does not position against it.
- **Fix:** Add to the evaluation-validity paragraph: "Label-position selection bias is documented for LLM multiple-choice selectors \citep{zheng2024robust}, and the fixed-versus-random-position distractor test in Section 5.7 is the corresponding diagnostic for menu-based search." Add a verified bib entry.
- **Fix class:** WORDING
- **Status:** CLOSED (`640467b`)

#### 62 · MINOR · Axis 3 (claim contradicted by the paper's own map) / Axis 5 (garbled sentence) · `iclr2026_conference_discussion.tex`

- **Location:** Discussion p.9 L433 (discussion.tex L18) "Within that boundary the output contract and candidate enumeration are learnable"; L436-437 "the trained controller depends on the textual serialization only in its copyability-preserving shuffled form".
- **Issue:** "Candidate enumeration" is exactly what fails. Process SFT scores 0/24 in every BFS and BFWS cell (144/144 failures, App N L1323), where the policy must select unvisited or admissible successors. Success appears only in additive cells, where the identity audit says any listed candidate is correct. Read literally, the second sentence says the controller depends on the text only when the text is shuffled, which inverts the corruption finding.
- **Fix:** "Within that boundary the additive-cell output contract is learnable (BFS and BFWS cells score 0/24)…" and "…and the language-channel dependence is supported only by the copyability-preserving shuffled condition".
- **Fix class:** MEANING
- **Status:** CLOSED (`9de44ad`)

#### 63 · MINOR · Axis 3 (ledger description inconsistent) · `iclr2026_conference_results.tex (5.1); iclr2026_conference_appendix.tex (App J)`

- **Location:** App J p.21 L1125 (appendix.tex L533) "Four follow-up windows executed after the program, each on its own GPU ledger", then L1128 "The comparator zoo ran on CPU only"; 5.1 p.5 L239-241 "the four separately ledgered follow-up windows (native arms, stress tests R1-R4, choice frontier, and the CPU-only comparator zoo)".
- **Issue:** Three GPU ledgers exist (native-arms/v1, reviewer-v130/v1+v2, choice-frontier/v1). The zoo has no GPU ledger. "Each on its own GPU ledger" contradicts the next sentence.
- **Fix:** App J: "Four follow-up windows executed after the program: three on their own GPU ledgers and the CPU-only comparator zoo". 5.1: "the three separately ledgered GPU follow-up windows and the CPU-only comparator zoo".
- **Fix class:** WORDING
- **Status:** CLOSED (`640467b`)

#### 64 · MINOR · Axis 3 (freeze timing overstated) · `iclr2026_conference_experimental_design.tex`

- **Location:** Design p.4 L202 (experimental_design.tex L41) "Follow-up protocols (Appendices P–R) were frozen before first outcomes on separate ledgers"; against 5.11 p.7-8 L412-414 "The choice-frontier contract was frozen after the stress-test outcomes and the zoo's metric set after the choice-frontier outcomes on these tasks" and 5.10 p.7 L367-368 "stored choice-frontier episodes enter post-hoc".
- **Issue:** "Before first outcomes" reads as outcome-blind design, but each follow-up was frozen after earlier outcomes on the same nine tasks. The sentence also points to App P-R for protocols, while the choice-frontier contract is defined in App I.
- **Fix:** "Follow-up protocols (Appendices I and P–R) were each frozen before their own first outcome, on separate ledgers, but after earlier outcomes on the same nine tasks (Section 5.11)".
- **Fix class:** WORDING
- **Status:** CLOSED (`640467b`)

#### 65 · MINOR · Style rules (per-file sweep) · `iclr2026_conference_results.tex; iclr2026_conference_discussion.tex; iclr2026_conference_experimental_design.tex; iclr2026_conference_appendix.tex; iclr2026_conference.tex`

- **Location and issue, per file:**
  - results.tex L38: a mid-clause colon in the main text ("on 48/48 additive pairs: each expansion requires…", p.5 L254).
  - discussion.tex L42: "behaviour" (British), against "behavior" in results.tex L49 and appendix.tex L544. discussion.tex L28: `\texttt{exact\_reference}` with a lowercase item start (finding 44 remainder).
  - experimental_design.tex L47: one sentence joins four independent clauses with "and" (p.4 L206-212). L54 has the same pattern (p.4 L213-217). A tired reviewer re-reads both.
  - appendix.tex:
    - Mid-clause colons at L397 "The null replicates: 0/72", L408 "decision sufficiency: $o_t$", L416 "a pair of 128×128 pixel images: a rendered", L526 "zero missing evidence: 1,152/1,152", L544 "VALID_STOP: on a frozen", L627 "in all three adapters:", "any such claim: the unlabelled", L630 "never pooled: all 5", L661 "None survives correction: the minimum", L706 "first decision: 379", "(56.3\% of learned failures): parsed", L709 "over a full episode: the learned".
    - Artifact-speak at L843 "returns \texttt{CHOICE\_SENSITIVE} with \texttt{ok}".
    - A legacy "pooled headline modalities" at L850 (finding 45 remainder).
  - hub L19: the title is a question (see finding 50).
  - No em-dashes and no prose semicolons in the main text. The paragraph-purpose census passes in all nine files.
- **Fix:**
  - Replace each mid-clause colon with a full stop or a comma clause, e.g. "…on 48/48 additive pairs. Each expansion requires…" and "The null replicates, with 0/72 unseen successes…".
  - Write "behavior".
  - discussion.tex L28: "\emph{Imitation target.} The exact reference solves by construction of the budget."
  - Split design L47 into three sentences (panel reuse, freeze timing, corpus provenance).
  - appendix.tex L843: "The final audit returns CHOICE\_SENSITIVE and passes over 144 replayed episodes."
  - appendix.tex L850: "Cell A covers one of the three modalities of the greedy additive cell."
- **Fix class:** WORDING
- **Status:** CLOSED (`640467b`)

### What would change the verdict

The transcription is clean and the round-2 scoping held. What keeps this at WEAK REJECT is value and falsifiability, not errors. Two experiments, both cheap and CPU-feasible on stored adapters, would move it to BORDERLINE. First, run the per-decision identity check under a submission-order serial rule, the counterfactual App B already predicts, or on one external interface, with divergence counts reported for both (finding 49). That shows the audit can return a different answer and turns a self-diagnosis into a portable instrument. Second, run the fixed-versus-random-position distractor test on the 36 native-adapter episodes (finding 51), so that menu manipulation either earns its place in the audit or leaves it. With those two, plus the claim narrowing in findings 52 and 54, a retitled paper whose Figure 1 is the contract contrast (finding 50), and the artifact comments filled in (finding 53), the remaining issues are MINOR wording. Positive movement past BORDERLINE still requires what 5.11 already names: a fresh frozen choice-frontier panel with at least eight discriminative tasks, and one comparator that sits between random-valid and exact.

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