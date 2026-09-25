# Manuscript Changelog

The record of what changed in the ICLR 2026 manuscript and why. Newest first. Each entry names the commit, the scope of the change, and the review or ticket it answered. Review findings and their status live in `review-log.md`; claim vocabulary and boundaries live in `CONTEXT.md`.

## 2026-09-25 — round 8 opening, Phase 0 decisions (content and framing; no new experiments or numbers)

- Wave 0 (read only): `local://content-audit.md` (paper-reviewer ContentAudit: review-22 reasons, candidate ranking, novelty check against primary sources, protocol box and survey proposal, claim mismatches M1-M12, weakest pages), `local://skim-audit.md` (scout: cold-read protocol re-run), and `local://oracle.md` (oracle: storyline and significance). Baseline body metrics (`check.py metrics -v`): 261 sentences, mean 17.5 words, maximum 38, 0 over 40, abstract 200 words, 0 paragraphs over 6 sentences. `check.py diff r7-final r8-base`: no token change.
- Main verified that the seed-replication Cell A (greedy × multimodal, +0.875/+0.875/+0.917 over the base and −0.125/−0.125/−0.083 against random-valid) runs on `expanded-panel-v2-qualified`, the same 24-task panel as the 48/48 identity audit (`configs/experiments/expanded-study/final-panel.json`, `docs/experiments/expanded-study/synthesis-v1/seed-variance-addendum.md` L7).
- Author decisions:
  - **Title:** "Can Vision-Language Models Learn to Execute Classical Search Algorithms?", the title registered on OpenReview. The abstract answers it at development stage: answering it requires a measurement that separates choice from validity.
  - **Primary contribution:** the validate-before-score measurement. An interface is admitted only after the identity audit finds divergent decisions and a decision-counted budget binds them (the compute-matched-baseline principle). M1 then passes a pre-registered, privileged exact-ε ladder on the validation and held-out panels before any policy is scored. The abstract, Figure 1 caption, contributions, Discussion, and Conclusion lead with it. The adapter is a worked use, not a co-equal contribution.
  - **Protocol box:** yes, "Box 1" at the end of Section 4. Its steps are the identity audit on executed code, the budget check in decisions or expansions (credited), the pre-registered ladder on a fresh, frozen, screened panel, and what to report. It replaces the Discussion's portable-rule paragraph. It is paid for by folding 5.1 into one clause of Section 4, moving the McNemar and exploratory sentences of Section 4 to the appendix, cutting Related Work ¶2 to one sentence, cutting the Discussion's restatements, and dropping the Conclusion's repeated intervals. The Reproducibility Statement does not count toward the page limit.
  - **Survey:** no main-text table. App V Table 24 gains columns only where the PDF already states the fact, plus the two in-house contracts as reference rows. One pointer sentence goes in 5.5. The box carries a contract-type to at-risk-check mini-list with each row labelled as a single audited instance.
  - **Contributions:** three bullets. (1) Primary: the validate-before-score measurement. (2) Why the admission step is needed: the identity audit returns both verdicts from a tie-break change alone, and every process-SFT success sits in cells it reads as validity, including the sign-stable gain over the base in the seed-replication cell. (3) A worked use and portability: the zero-shot base and the first adapter score at the random-valid level, the trained adapter scores above it on three panels with a panel-dependent ladder position, and Box 1 runs on two published interfaces (a ScienceWorld positive control, and a by-construction budget failure on LLM-First Search, with Li & Talwalkar credited).
  - **Discussion implications:** all three. Designers audit decisions on the executed runtime. Designers count budgets in decisions or expansions when a zero-cost control exists. Trainers report the gain over random-valid with the ladder position, split by audit verdict.
  - **Architecture:** section order kept. 5.1 is no longer a subsection, and its label `sec:results-gates` moves to Section 4. 5.6 merges into 5.2 ("The Identity Audit and What It Changes"), which carries both `sec:results-identity` and `sec:results-primary`. The Introduction order becomes stakes, mechanism, measurement, what it orders, external audits.
  - **Meaning fixes (all accepted):**
    - (a) 5.2 states that the 48/48 follows from the executed serial rule, as App S predicted, is invisible in the contract specification, and is detected by a decision-level audit.
    - (b) Saturation alone does not separate the cases: random-valid saturated the BFS development panel, while on the expanded baseline its BFS decisions diverge (15/24).
    - (c) The ladder licenses reading a higher M1 as choice closer to the reference's, along the ladder's ε axis.
    - (d) The reference's 0.875 is glossed as fixed by construction at first main-text use.
    - (e) The adapter's M1 exceeds random-valid's on every panel (descriptive on the unscreened panel).
    - (f) The leave-one-domain-out result is scoped to the validation and held-out panels.
    - (g) The abstract opener is a setting, not a claim about the field.
    - (h) ScienceWorld is a positive control and LLM-First Search a by-construction illustration. "The external audits test each check" is retired.
    - (i) Related Work credits Yang et al. 2020 next to Li & Talwalkar and states novelty as a per-decision test that locates the confound in the runtime, plus validation of the measure before scoring. The unrun distractor-test sentence moves to Limitations.

## 2026-09-25 — round 7 waves 1-5, review 22, and consolidation (`4b52839`..`ced37c8`)

- Wave 1 (`a0cffe3`): abstract, Introduction, Sections 3 and 4 rewritten to `local://r7-outline.md`. Figure 1 (`fig:contracts`) moved into the Introduction (`4b52839`). The contract definitions moved to Section 3; the screen definition, the held-out definition, and the panel-reuse risk moved to Section 4.
- Wave 2 (`26064ba`): Results, Discussion, and Conclusion rewritten in the asked, done, found, verdict shape. 5.6 is one paragraph carrying both labels. The per-window GPU-hour pairs, per-seed D values, rung values, and last-label rates left the body (they are in the appendix tables and Figures 1-2). The first adapter's last-label contrast (0.300, chance 0.144) and "chance about 0.13" moved to the Scaled Adapter appendix with their comments. The C* ranges and two dates left the PDF.
- Wave 3 (`7a407ab`, `60334e8`): Figure 1 redrawn as the thesis teaser from `local://fig-contract-r7.md`. Panel (a) shows the enumeration-contract audit, and panel (b) shows the choice-frontier audit plus the validation-panel M1 ladder with the adapter. Every printed value is read from JSON and asserted half-up, and Main inspected the PNG over five renders. Related Work flow pass (31 keys unchanged). The LLM-usage statement is replaced (finding 40, author decision).
- Wave 4 (`590cfea`): terminology sweep against the prose-name table, first-use definitions, house-style census, prose appendix names, appendix openings, and the Reproducibility Statement.
- Wave 5: review 22 (WEAK REJECT, rating 4; Soundness 3, Presentation 3 (up from 2), Contribution 2; 0 CRITICAL, 2 MAJOR, 12 MINOR, findings 85-96) and cold read B appended (`2dd3d74`). The number set is unchanged, and all 31 re-derived numbers and both figure scripts pass. Author decisions: 88 accepted, and the finding-40 statement gains the research-assistance sentence. Consolidation (`31de435`, `ced37c8`) closes 82 (d, e), 85-96, the 80 remainder, and the cold-read items. It adds main-text Table 1 (`tab:results-panels`, body values only) and a Modality limitation.
- Body metrics (Main's detex script, captions and tables excluded), before → after: mean sentence 25.0 → 17.5 words, maximum 69 → 38, sentences over 40 words 25 → 0, paragraphs over 6 sentences 1 → 0, abstract 216 → 200 words. The body number-token set did not grow (the only new tokens are shifted table numbers and the re-wrapped `g + 3h_add`).
- Target misses explained: Related Work is about 404 body words against the outline's 400-word budget (acronym expansions for finding 96). The abstract defines ε and M1 but not "exact reference" or "enumeration contract", which the Introduction defines.
- Build: 38 pages, 0 errors, 0 undefined, 0 overfull, 0 bibtex warnings. The Conclusion ends on p.9 after Table 1 was added (it was on p.8 before). No visible TODO. All headline strings are present.

## 2026-09-25 — round 7 opening, Phase 0 decisions (readability and style; no new experiments or numbers)

- Wave 0 (read only): `local://style-sheet.md` (16 checkable principles from ResNet, MAE, ImageNet CVPR 2009, and ILSVRC IJCV 2015) and `local://readability-audit.md` (per-paragraph table, jargon inventory, thesis test, ten worst problems). Baseline body metrics (Main's detex script, captions and tables excluded): 199 sentences, mean 25.0 words, maximum 69, 25 sentences over 40 words, 1 paragraph over 6 sentences, abstract 216 words. Baseline build 38 pages, main text 9 pages.
- Author decisions (all defaults):
  - Thesis A: a random-valid control's success measures choice only when its decisions can differ from the reference's and the budget binds decisions; the paper builds a search-choice measurement that passes both checks and a pre-registered ladder test, and uses it to score learned search policies.
  - Terminology: the prose-name table in `CONTEXT.md` ("Prose Names (round 7)"). "Held-out" now has one referent (P2); the 45-task manifest is "the frozen 45-task final evaluation". Labels and keys unchanged.
  - Figure 1: `fig:contracts` (label kept) moves to the Introduction and is redrawn as a thesis teaser, with the enumeration-contract audit in panel (a) and the choice-frontier audit plus the validation-panel ladder in panel (b), using only values already in the body. `fig:ladder` stays in Results.
  - Section order kept; sections tightened. Abstract at most 200 words in problem, observation, method, findings, boundary order. The enumeration-contract learned results (5.6) compress to one body paragraph.
  - Finding 40: replace the LLM-usage sentence with a precise statement (agent-drafted text and figure scripts, agent citation pass with human-verified sources, agent review rounds, author verification of every number and claim). Finding 40 moves from WONTFIX to fixed in round 7.
  - Title unchanged.
  - Meaning-adjacent defaults accepted: repeated caveats kept in full once each in the abstract, at the result, and in the Limitations or Conclusion, and as short clauses elsewhere; the two random-valid samplers get distinct prose glosses; "development-stage" and "privileged" are glossed once.

## 2026-09-25 — review 21 and consolidation (`58e661e`)

- Review 21 (paper-reviewer, at `ba7d4d2`): WEAK REJECT, **rating 4** (Soundness 3, Presentation 2, Contribution 2, confidence 4). 0 CRITICAL, 1 MAJOR, and 5 MINOR findings (81-84 plus the 75 and 80 remainders). Every rendered number matches the pinned artifacts. The reviewer re-ran the 30 fig_ladder checks (all pass) and confirmed findings 69-74 and 76-79. Main text is 9 pages.
- Author decisions:
  - 81 (MEANING): accept the reframe. The LLM-First Search saturation is a by-construction demonstration of the budget check, not a tested failure mode. `CONTEXT.md` is amended.
  - The reviewer's experiment paths are filed as #143 (one-seed InternVL3.5-8B adapter) and #144 (modality contrast under the choice-frontier contract), both `experiments`, pending the author's go.
- Consolidation:
  - 5.5 states the saturation holds by construction (102,606 against 1,300 maximum expansions) and gives the expansion-counted success (0.0775 at the reference's count, 0.19 at twice it).
  - The LLM-First Search appendix now discloses the 500,000-expansion guard, the 100/100 probe, and the budget curve, and says the reference's matched success equals its token-budget success by construction. The Discussion, Introduction, Conclusion, Contribution 4, and abstract use the by-construction wording.
  - The portable rule cites the compute-matched-baseline precedent (`li2019random`, verified against PMLR v115 and arXiv; also cited in Related Work with a net-zero word change).
  - Zero-shot policy: the prompt is fully described, verdicts carry stage labels (development and confirmatory), the pooled verdict reads "within margin (descriptive)", and $D_3$ is defined for both arms.
  - The sign-flip p is in its own rows and is defined in the Statistics appendix.
  - The abstract is cut to about 220 words. The 75 and 80 remainders are fixed.
- Build: 38 pages, 0 errors, 0 undefined, 0 overfull, 0 bibtex warnings. The Conclusion ends on p.9 (main text 9 pages). All headline strings are present.

## 2026-09-25 — round 6 waves 1-3 (`e2eb87c`, `865545a`, and the wave-3 commit)

- Wave 1 (`e2eb87c`):
  - 5.4 gains the zero-shot second policy: EQUIVALENT to uniform choice on the validation panel only, below the ε-0.75 rung and the adapter on both panels, "so the instrument ranks the two realisable policies".
  - 5.5 gains the LLM-First Search audit (0/400 pairs identical, 1.0 against 0.825 under the paper budget, 0.0775 under a matched decision budget, with the model substitution stated in the body).
  - The Discussion value anchor becomes "the measurement and its two checks", and the portable rule gains the budget-binding check.
  - The abstract, Contribution 4, the limitations (external audit, second policy), and the Conclusion are updated.
  - Appendix subsections: Zero-Shot Policy (`app:results-cf-zeroshot`, `tab:appendix-zeroshot`, with InternVL not run disclosed) and LLM-First Search Audit (`app:results-external-lfs`, `tab:appendix-lfs`). Ledger rows v6 2.25/30 and external v2 2.89/12, never summed. Artifact rows added.
- Wave 2 (`865545a`): fig:ladder gains a zero-shot row (validation and P2). The asserts now round half-up with `decimal`, because the stored 0.0625 upper bound rounds to 0.062 under Python `round`. All asserts pass, and Main inspected the PNG.
- Wave 3:
  - Evidence-comment and style census is clean, and the stale "only predicted" survey claim is fixed.
  - The redundant 5.5 clause is cut (body −14 words). The Reproducibility Statement points to both new subsections.
  - The matched-budget difference is printed +0.747 from the stored raw value 0.7474999999999999.
  - Related Work needed no change.
- Build: 37 pages, 0 errors, 0 undefined, 0 overfull, 0 bibtex warnings. The Conclusion ends in the lower part of p.9 (main text 9 pages).

## 2026-09-25 — round 6 opening (evidence tickets #141, #142 closed)

- #141 (`outputs/choice-frontier/v6/metrics/analysis.json`, protocol `0fa497c`, closeout `1c79e1e`): the InternVL arm was infeasible within 30 GPU-h, so the second realisable policy is the zero-shot base Qwen3-VL-8B. D3 is EQUIVALENT on the validation panel (+0.005 [−0.025, +0.044]) and INCONCLUSIVE on P2 (+0.001 [−0.048, +0.051]). S and the contrast against the adapter are SEPARATED_BELOW on both panels. The prediction held. 46/46 replayed. Ledger 2.25/30 GPU-h.
- #142 (`outputs/external-audit/v2/lfs/identity-audit.json`, protocol `b09a458`): LLM-First Search with a local Qwen3-30B-A3B substitute for GPT-4o, 80 tasks. 0/400 pairs identical. Under the paper budget: SATURATED (random-valid 1.0 against reference 0.825). Under a matched decision budget: CHOICE_REGISTERED (random-valid 0.0775). Both predictions held. Ledger 2.89/12 GPU-h, no paid API.
- Evidence sheet `local://evidence-r6.md` (two scouts). Main re-read both JSONs and checked the headline values and both ledger sums.
- Author decisions: #142 goes in the body as a second failure mode on a published interface (the value anchor, portable rule, Contribution 4, abstract, and Discussion updated; the substitution stated in the body). #141 gets two sentences in 5.4 plus an appendix subsection. fig:ladder gains a zero-shot row. The title is unchanged. Review-20 finding 69 (b, c) closes with this integration. `CONTEXT.md` gains an "External audit claim" entry.

## 2026-09-25 — review 20 and consolidation (`e7346aa`)

- Review 20 (paper-reviewer, area-chair tier, at `0277de7`): WEAK REJECT, **ICLR 2026 rating 4** (Soundness 3, Presentation 2, Contribution 2, confidence 4), 0 CRITICAL, 2 MAJOR, 10 MINOR (findings 69-80). The reviewer re-derived every round-5 number and every cell of the three new appendix tables from the pinned JSONs and ledgers (all match), re-ran the 28 fig_ladder asserts (all pass), checked 16 evidence comments (15 resolve, 1 off-by-one pointer), and verified the round-4 closures (49, 60, the #137 reframe, review-16 finding 15, the 51 and 52 hedges). Main text was 8 pages. Full entry in `review-log.md`.
- Author decisions on the MEANING-class findings: 69 add the portable-rule paragraph and file the two experiments as evidence tickets #141 (second realisable policy through the instrument) and #142 (identity audit of LLM-First Search); 70 accept the reviewer's screen rewrite without a new analysis; 71 accept "not separated from the 0.75 rung" plus a non-equivalence sentence (CONTEXT.md amended); 77 wording-only small-cluster disclosure (11 clusters, 8 positive and 3 negative per-task differences, no unpinned p-value).
- Consolidation (front and back writers steered, related-work scout): the P2u reading now says the screen admits tasks on which near-uniform choice sometimes succeeds, that all 12 P2u tasks had 0/10 screening goals, that choice still discriminates there (descriptive), and that the gain rests on 4 of 12 tasks. "At the rung" is replaced by "not separated from the rung" everywhere. The Discussion states the portable rule. M1 and D3 are defined in the abstract and Introduction. The first-adapter M4 paragraph moved out of 5.4. The metric-construction note (exact reference M1 0.875 by construction, privileged hadd-greedy above it) is in the Choice-Frontier Contract appendix. The DAgger conclusion no longer implies equivalence. Stale window counts, the one-seed budget rule, the snapshot date, appendix letter ranges, and the v4 replay receipt are fixed. Related Work cites policy-guided heuristic search (`orseau2021policyguided`, first citation) and tie-breaking in A* (`asai2016tiebreaking`, new, verified against DOI 10.1609/aaai.v30i1.10071 and AAAI OJS).
- Status: 70-80 CLOSED (`e7346aa`), 69 PARTIAL (rule added, experiments blocked on #141/#142), 40 WONTFIX.
- Build: 35 pages, 0 errors, 0 undefined, 0 overfull, 0 bibtex warnings. The Conclusion now ends near the top of p.9 (main text 9 pages, within the limit). All headline strings present.

## 2026-09-25 — round 5 wave 3, compliance and hygiene

- Evidence-comment census: every round-5 number and every cell of the three new appendix tables has an adjacent `%` comment naming its artifact and key. One pointer was sharpened (seeds 955040-955199 → `issue-139-protocol.md` L122). The writer spot-verified 15 new comments against the sheet.
- Style census: 0 em-dashes, 0 disallowed semicolons (the LLM-usage sentence is the WONTFIX exception), 9 mid-clause colons fixed in the validity-preconditions list of the Operation Schemas appendix, paragraph-purpose comments complete, 0 visible TODOs, 0 `% Pending:` comments.
- Stale-claim sweep: the "every learned arm/cell uses seed 17" statements in 5.1, 5.6, the Statistics appendix, and the Seed Replication appendix are scoped to the enumeration contract, and 5.1 states the adapter's three seeds. Every "held-out manifest/evaluation" outside P2 now names the frozen 45-task manifest. No round-4 point-estimate, between-the-rungs, no-paired-interval, or seed-17 concentration wording remains. Every ladder-position statement carries all three results.
- 5.4 flow: the replication provenance sentence follows the 3-seed sentence, and the boundary paragraph is the imitation clause, the claim frame, and the DAgger sentence.
- The Reproducibility Statement drops its hard-coded appendix-letter range and names the Held-Out Panels and DAgger Ablation appendices in prose.
- Related Work (related-work-scout): no change needed. The admissible-action positioning sentence (review-16 finding 15) and the ScienceWorld, Jericho, CALM, and Zheng et al. positioning are intact, and all 28 cited keys resolve. DAgger is already cited (`ross2011dagger`) at first body use.
- Build: 35 pages, 0 errors, 0 undefined, 0 overfull, 0 bibtex warnings. The Conclusion ends at the bottom of p.8. All headline strings present.
- Commit references for this round: wave 1 `bc32404`, wave 2 `9155812`.

## 2026-09-25 — round 5 wave 2, three-panel ladder figure

- `fig:ladder` (`figures/fig_ladder.py`, redrawn by a figure-only paper-writer from `local://fig-contract-r5.md`) now has three panels (validation, held-out P2, unscreened P2u). Each shows M1 with task-clustered intervals for the five ladder arms and the 3-seed adapter mean, with faint per-seed points, a dotted line at that panel's own ε-0.75 rung, and the first adapter on the validation panel only. The script reads `v4/panels/metrics/analysis.json` `arms.{p135,p2,p2u}.*` and `v2` `adapter_reevaluation.learned_adapter.*` and asserts all 28 values at 3 dp. Main ran it (asserts pass) and inspected the PNG three times (first-adapter label added, label offsets widened, font raised to 8 pt at 6.0 in so it renders at about 7 pt). The figure is included at `\linewidth`.
- Page budget: the Conclusion still ends at the bottom of p.8, so no compression was needed.
- Build: 35 pages, 0 errors, 0 undefined, 0 overfull, 0 bibtex warnings. All headline strings present.

## 2026-09-25 — round 5 wave 1, evidence integration (#138-#140)

- All 7 visible placeholders resolved (Results P1-P3, Discussion P1-P2, appendix table P1-P2) and every `% Pending:` comment deleted. No visible `[TODO` remains in the PDF.
- Results 5.3 introduces the held-out panel P2 (11 tasks, 8 domains) with the #139 A1 disclosure and reports the ladder passing on P2 (pre-registered, smallest gap +0.130 [+0.070, +0.190]) and on P2u (descriptive). 5.4 is retitled "Adapter Replication and Held-Out Panels" (label kept): 3-seed D3 +0.285 [+0.140, +0.433] with every seed positive, P2 +0.416 [+0.250, +0.591], the three-panel ladder-position sentence, the P2u screening sentence (+0.149 [+0.030, +0.283], 8 of 12 tasks unsolved by both arms), the held-out-panel vs frozen-manifest sentence, concentration 22 of 35 / 12 / 1 and leave-one-domain-out +0.305 to +0.395, and one DAgger sentence. 5.1 lists the v4 (15.22/24) and v5 (9.06/40) windows separately. The fig:ladder caption anticipates the wave-2 three-panel figure.
- Appendix: the Scaled Adapter appendix becomes "Scaled Adapter and Seed Replication" with the #138 per-seed paragraph, and gains subsections "Held-Out Panels" (`app:results-panels`: construction, #139 A1, `tab:appendix-panel-arms`, `tab:appendix-seed-d`, `tab:appendix-concentration` with the `all_36_counts` note) and "DAgger Ablation" (`app:results-cf-dagger`: #140 A1, NOT_SEPARATED +0.115 [−0.026, +0.258], INCONCLUSIVE −0.030 [−0.114, +0.057], replay by counts only). They are subsections because a 27th appendix `\section` overflows the letter counter. Ledger and artifact-index rows added.
- Abstract, Introduction, Discussion, and Conclusion carry the 3-seed headline, the short three-panel ladder sentence, the P2u result, and the new claim frame. The limitations list is the six approved items. Experimental Design states the adapter's three seeds and the two follow-up protocols.
- Build: 35 pages, 0 errors, 0 undefined, 0 overfull, 0 bibwarn. The Conclusion ends at the bottom of p.8 (main text 8 pages). All headline strings are present.

## 2026-09-25 — round 5 opening, Phase 0 decisions (issue #131; evidence tickets #138-#140)

- Evidence sheet `local://evidence-r5.md` frozen from the #138-#140 analyses, ledgers, protocols, and closeouts. Main spot-checked 20 rows against the JSONs (D3 +0.285 [+0.140, +0.433] and per-seed values, S vs ε-0.75 −0.041 [−0.187, +0.102], S vs ε-0.50 −0.298 [−0.468, −0.129], P2 D3 +0.416 [+0.250, +0.591] and S +0.227 [+0.053, +0.403], P2u D3 +0.149 [+0.030, +0.283] and S +0.002 [−0.145, +0.157], pooled D3 and S, the four P2 ladder gaps, concentration 22/12/1, P2u zero count 8, leave-one-domain-out, #140 S_pool and Δ, per-panel P2 S, last-label 0.137, both ledger attempt sums 15.2225 and 9.0640). All match. Writers copy numbers only from the sheet.
- Sheet notes: S vs ε-0.50 on #135 is descriptive (protocol role "descriptive only"). `concentration.all_36_counts` covers the 35-task union (P2 froze at 11). The artifacts record the #140 replay as 24/24 plus 22/22 with no mismatch but not who ran it. The cancelled seed-29 collection is 1.79 GPU-h in the closeout.
- Author decisions (all defaults):
  1. Title unchanged ("Separating Choice from Validity: A Validated Search-Choice Measurement for Vision-Language Search Policies").
  2. `CONTEXT.md` choice-quality entry amended to three panels (#135, held-out P2, unscreened P2u) and 3 seeds. "Held-out" means P2 only, and the frozen 45-task held-out final evaluation is unexecuted.
  3. Ladder position is reported only as one three-part statement (at the ε-0.75 rung and below ε-0.50 on #135, separated above ε-0.75 on P2, not separated on P2u or pooled), with the descriptive labels.
  4. The screening concern is answered with P2u in the body (effect about a third as large, 8 of 12 P2u tasks unsolved by both the adapter and random-valid).
  5. #140 DAgger is an appendix ablation with one body sentence.
  6. #139 A1 is disclosed in the body where P2 is introduced, #140 A1 in the appendix.
  7. `fig:ladder` becomes three small panels (#135, P2, P2u) drawn by a figure-only paper-writer.
  8. Finding 40 stays WONTFIX (dictated LLM-usage wording kept; the #131 desk-reject risk note is recorded here).
  9. Main text through the Conclusion stays within 9 pages, and nothing moves back from the appendix.
  10. Meaning-level changes approved: the 3-seed D3 replaces the single-seed headline (seed 17 only as a per-seed value), 3-seed concentration counts replace the seed-17 per-task counts, the limitations list is rewritten (single-seed and one-panel items dropped, ladder position, P2 screening, and the unexecuted 45-task evaluation added), P2 is stated as screened, the #140 replay is stated by counts only (Main ran the final replay after the executing agent's allowance ran out, recorded here only), and the cancelled seed-29 hours are cited as 1.79 GPU-h.

## 2026-09-24 — evidence intake for round 5 (#138, #139, #140 closed; no manuscript text changed)

Main re-read the committed analyses. Every value the author reported matches. These results resolve placeholders P1-P3 and are integrated in round 5, not here. Review 20 is still held.

- #138 (`outputs/choice-frontier/v4/seeds/metrics/analysis.json`), 3 seeds on the #135 panel:
  - `primary`: POSITIVE, D3 +0.285 [+0.140, +0.433]. Per seed (`primary.per_seed`): s17 +0.328, s29 +0.229, s71 +0.297.
  - `separation.vs_eps_0.75`: NOT_SEPARATED, S −0.041 [−0.187, +0.102].
  - `separation.vs_eps_0.50`: SEPARATED_BELOW, S −0.298 [−0.468, −0.129]. The author's summary does not list this result, but it is in the file.
- #139 (`outputs/choice-frontier/v4/panels/metrics/analysis.json`):
  - `ladder_p2.verdict` PASS. P2 is a fresh held-out panel of 11 tasks from 8 domains. It is not the frozen 45-task held-out manifest, which remains unexecuted.
  - `unscreened_p2u.ladder.verdict` PASS (descriptive).
  - `heldout_p2.primary`: POSITIVE, D3 +0.416 [+0.250, +0.591]. `heldout_p2.separation.vs_eps_0.75`: SEPARATED_ABOVE, S +0.227 [+0.053, +0.403].
  - `unscreened_p2u.primary`: POSITIVE, D3 +0.149 [+0.030, +0.283]. Its `separation.vs_eps_0.75`: NOT_SEPARATED, S +0.002 [−0.145, +0.157].
  - `pooled.primary` (35 tasks, descriptive): D3 +0.279 [+0.191, +0.375]. `pooled.separation_vs_eps_0.75`: NOT_SEPARATED, S +0.058 [−0.040, +0.156].
  - `concentration.all_36_counts`: positive 22, zero 12, negative 1. These sum to 35, even though the key name says 36. Round 5 must add a comment recording this.
  - Leave-one-domain-out on P2 ∪ #135: between +0.305 and +0.395.
  - Amendment A1: the seed range was extended to 955040-955199 before any evaluation episode, with the rules unchanged. It must be disclosed.
- #140 (`outputs/choice-frontier/v5/metrics/analysis.json`, closeout commit `3996600`), DAgger, seed 17 only under Amendment A1:
  - A1 changes made before any result existed: seeds 29 and 71 were not trained, and the corpus was halved to 512 on-policy plus 512 replayed records over 64 steps.
  - `primary`: pooled over 23 tasks, NOT_SEPARATED, S_pool +0.115 [−0.026, +0.258].
  - `co_primary`: INCONCLUSIVE, delta_pool −0.030 [−0.114, +0.057].
  - `per_panel.p2.S` +0.278. `per_panel.v2.S` −0.034.
  - Reported as an inconclusive appendix ablation.
- Ledgers, listed separately and never summed: v4 (#138 and #139 shared) 15.22 of 24 GPU-h (Σ `attempts[].gpu_hours` 15.2225), v5 (#140) 9.06 of 40 GPU-h (Σ 9.0640).

## 2026-09-24 — round 4 wave 3, compliance and hygiene (`20af870`)

- Evidence-comment census: five `% Evidence` lines added for pre-round numbers in the Introduction (125/288, seeds 17/29/71) and Experimental Design (336 GPU-h cap, 24/12/288 counts, 10,000 resamples with seed 1729, 36 McNemar comparisons). Every round-4 number already had one.
- Style census over all section files: 0 em-dashes, 0 disallowed semicolons (the remaining one is the WONTFIX LLM-usage sentence), 1 mid-clause colon fixed (DAgger table caption), paragraph-purpose comments complete. Visible TODOs are exactly the author's placeholders (Results P1-P3, Discussion P1-P2, appendix #136 table P1-P2; 7 in the PDF).
- Cross-references use prose appendix names throughout Results, the Appendix, Section 3, and Experimental Design. The Reproducibility Statement points to the Counterfactual, Choice-Frontier Validation, Scaled Adapter, and External Identity Audit appendices and the ledger table.
- Stale-claim sweep found no remaining "fresh panel required", "no choice-quality claim", "zoo calibrates", single-check 48/48 vs 18/18, "between the rungs", or "no M4 interval" wording.
- Related Work (related-work-scout): ScienceWorld positioned beside Jericho and CALM as a published sequential-choice interface where random-valid registers choice, and the complete-set contract is stated as not found among the surveyed interfaces. The admissible-action positioning sentence (review-16 finding 15) is kept, with its tail updated to the two-verdict framing. LLM-First Search is not cited there because it does not fit the scaffold-owns-exploration sentence. It stays cited in 5.5.
- Build: 32 pages, 0 errors, 0 undefined, 0 overfull, 0 bibtex warnings. The Conclusion ends on p.8. All headline strings present.

## 2026-09-24 — round 4 wave 2, structure and figures (`076738e`)

- New body Figure 2 (`fig:ladder`, `figures/fig_ladder.py`): M1 with task-clustered 95% intervals for the five ladder arms, the scaled adapter (single seed), and the first adapter on the 12-task validation panel, with a dotted line at the exact-ε 0.75 rung. The script reads `choice-frontier/v2` `arms.*` and `adapter_reevaluation.learned_adapter.*` and `choice-frontier/v3` `per_seed.17.*`, and asserts every value against the evidence sheet. It replaces the body ladder table (`tab:results-ladder` removed; the appendix arms table carries the numbers).
- Figure 1 (`fig_contracts.py`): panel (a) adds the same-runtime counterfactual "submission-order serials: 19/48 divergent" (read from `identity-audit-submission-order.json`), the node is relabelled "Sorted-serial frontier (order-invariant)", and arrow labels no longer touch the boxes. Main rendered both scripts and inspected the PNGs.
- Introduction and Discussion de-duplicated: the Discussion interprets the two-verdict audit, the ladder, and the at-rung position with Section pointers instead of restating the Results sentences. The abstract names the ScienceWorld reference success explicitly. The limitations item reads "Ladder position". 5.4 reports last-label rates as 20.5% against 30.0%.
- Page budget: the Conclusion ends on p.8 (main text 8 pages, limit 9), so no further compression was needed after the moves in wave 1.
- Build: 32 pages, 0 errors, 0 undefined, 0 overfull, 0 bibtex warnings. All headline strings present.

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
