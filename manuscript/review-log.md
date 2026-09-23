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
| 16 | 2026-09-23 | paper-reviewer (area-chair tier) | Full manuscript: 9 sections, hub, 6 bibs, build log, rendered 37-page PDF at commits `2569773`, `1b49ecb`, `059028f` | REJECT (6 CRITICAL, 14 MAJOR, 16 MINOR) | **OPEN** |
| A | 2026-09-23 | related-work-scout | Citation pass over all sections and the six bibs at commit `1b49ecb` | 0 placeholders, 8 entries added, 42 cited keys resolving, 2 entries restored after an audit error | CLOSED (`059028f`) |

## Live fixlist — review 16 (2026-09-23)

**Verdict:** REJECT — 6 CRITICAL, 14 MAJOR, 16 MINOR.

**Reviewer summary (verbatim):**

> Round-1 area-chair review of the assembled #131 draft (37 pages, 0 figures, 17 tables). All nine section files, the hub, the six bibs, the log/blg, and the rendered PDF text were read. Headline numbers were re-read from the pinned artifacts, and the 36 distractor-injection episode records were opened directly. The number transcription is careful: every Results table matches its pinned JSON. The failures are in what those numbers license. (1) The headline says the enumeration contract makes choice quality unmeasurable. The identity audit covers only the 48 additive pairs, and the same contract's BFS/BFWS rows (random 15/24 and 17/24 vs exact 24/24) plus the abstract's own BFWS positive show that choice is measurable there. (2) The menu-manipulation receipt pair cannot discriminate. Under the recorded submission-order invariance, permutation succeeds for any policy that emits any remaining candidate. The 0.6 distractor pick-rate equals uniform chance over the displayed menu (0.56 to 0.63 recomputed from the episode views). The repeated claim that every episode's first emitted operation is a distractor is false: 16/36 episodes open with an accepted operation. (3) Contribution 3 says the zoo places the adapter below named selectors, while its M1 exceeds bfs-order and worst-first. (4) The Discussion misstates the R2 decomposition that Results resolved from JSON. (5) The main text runs about 24 pages against ICLR's strictly enforced 9-page desk-reject limit. MAJOR issues cover the unexamined link between the identity finding and the algorithm-specific success map (learned success appears only where the audit shows no decision to make), a choice-frontier gate that passes by construction with 9 independent tasks and one discriminative task, pooled masked-text channel claims the paper itself retracts, seven TODO markers tied to tickets closed on 2026-09-21, the missing text-game admissible-action literature, an anonymity-breaking GitHub comment ID, and no LLM-usage disclosure. Claim discipline on seeds, saturation, equivalence, expansion parity, and post-hoc labelling is otherwise clean.

### Findings

#### 1 · CRITICAL · `iclr2026_conference_abstract.tex; iclr2026_conference_introduction.tex; iclr2026_conference_discussion.tex`

- **Location:** Abstract L6 'Under the original enumeration contract, where the policy picks each operation from a grounded candidate menu, the answer is that it cannot be measured.'; Abstract L18 'Under the enumeration contract one positive contrast exists, a 15-task width-based best-first development panel (0.933 versus 0.467 for random-valid).'; Intro L42 'under the enumeration contract a grounded action menu makes search-choice quality unmeasurable'; Discussion L24 and Conclusion L132 'Under the enumeration contract, the grounded action menu makes choice quality unmeasurable by construction'
- **Issue:** Axis 1 / Axis 3 / Axis 4. The headline belief update overgeneralizes an additive-only audit, and the abstract contradicts itself. The artifact covers only additive cells: outputs/native-arms/v1/identity-audit.json has pairs_checked 48, with the verdict scoped to 'every additive pair'. Its structural_basis ('finish_expansion() requires the complete candidate set; heap serials are assigned from the deterministic sorted candidate order ... frontier evolution is submission-order invariant') is a property of the additive heap implementation, not of grounded menus. Under the same enumeration contract, Table 5 shows random-valid 15/24 (BFS) and 17/24 (BFWS) against exact 24/24. Table 6 gives random-valid minus exact -0.375 and -0.292 (docs/experiments/expanded-study/synthesis-v1/README.md L48), so decisions change outcomes there. The abstract's own L18 BFWS positive (0.933 vs 0.467) is an enumeration-contract measurement of learned advantage over random-valid, which L6 says cannot exist. The portability claim ('two cheap benchmark-hygiene checks that any grounded-menu evaluation can run', Abstract L21, Discussion L132) is likewise unsupported beyond submission-order-invariant priority queues.
- **Fix:** Scope every headline sentence to the additive best-first cells, e.g. 'On the additive best-first cells of the enumeration contract, where an expansion must submit its complete candidate set and heap order ignores submission order, random-valid is decision-identical to the reference on 48/48 pairs.' Name the cause as submission-order invariance, not the menu. State that BFS/BFWS cells under the same contract do register choice (random-valid 15/24 and 17/24 vs 24/24) and that the learned policy scores 0/24 there. Either run the identity audit on the 48 BFS/BFWS control pairs and report the divergence count, or delete 'any grounded-menu evaluation'.
- **Status:** OPEN

#### 2 · CRITICAL · `iclr2026_conference_results.tex; iclr2026_conference_abstract.tex; iclr2026_conference_discussion.tex; iclr2026_conference_introduction.tex`

- **Location:** Results L332 'Permutation leaves behavior intact, with 36/36 successes and 0/512 invalid operations, which rules out order-riding ... so the collapse rules out state grounding. The policy reads menu content without verifying applicability against the scene.'; Abstract L8 'Menu manipulation shows what trained policies read instead'; Intro L23 'The policy reads menu content without grounding applicability in the scene.'; Discussion L24 'the trained policy reads menu content and cannot ground actions in state'; Conclusion L132 'it cannot ground actions in state'
- **Issue:** Axis 2 falsifiability: the receipt pair could not have lost, and the pick-rate sits at chance. (a) Per the paper's own structural basis (Results L339, identity-audit.json), additive frontier evolution is submission-order invariant and each decision submits one remaining candidate. Any policy that emits any listed candidate therefore succeeds, including a pure order-rider that always copies the first entry. Permutation 36/36 is guaranteed and cannot rule out order-riding. (b) The pick-rate is not compared with chance. Recomputed from the 36 episode records under outputs/native-arms/v1/evaluation/episodes/menu/*/*/*distractor-injection-learned_adapter.json.gz (events[].view.injected_distractors against events[].input.successor_candidates.rows), uniform picking over the displayed menu gives an expected distractor pick-rate of 0.592 (all listed rows) to 0.625 (unpruned rows) over the 60 injected decisions. The observed 36/60 = 0.6 is at chance. Content-reading and position-picking both predict about 0.6, so neither 'reads menu content' nor 'cannot ground actions in state' is identified. The distractors are also out-of-distribution (training menus contained only applicable actions), so the collapse shows the policy does not reject inapplicable entries it never saw, not an inability to ground. The #132 post-hoc finding (last label 54.5%, Results L1093) points to position habits, the hypothesis permutation was supposed to exclude.
- **Fix:** Report the chance pick-rate next to 0.6 and state that the observed rate is at chance. Replace 'rules out order-riding' with 'is uninformative about order under submission-order invariance'. Replace 'reads menu content' and 'cannot ground actions in state' with 'does not reject schema-valid inapplicable menu entries (pick-rate at chance)'. A discriminating test would inject distractors at a fixed position (first or last) versus random positions and compare pick-rates by position. That experiment separates position-riding from content-reading and would change the verdict on the receipt pair.
- **Status:** OPEN

#### 3 · CRITICAL · `iclr2026_conference_results.tex; iclr2026_conference_discussion.tex`

- **Location:** Results L332 'and the first emitted operation of every episode is a distractor'; Discussion L24 'collapses under distractor injection (0/36), where the first emitted operation of every episode is an injected inapplicable action'
- **Issue:** Number contradicting the pinned source. outputs/native-arms/v1/stress-evaluation.json gives each distractor-injection cell 9 episodes and 15 decisions (60 decisions over 36 episodes), and episodes terminate on the first invalid operation. The episode records show 20/36 episodes ending on their first decision and 16/36 (8 with two decisions, 8 with three) opening with one or two accepted operations before the distractor pick. Example: visual-nomem-state/expanded-final__ferry-compact-915000/best_first_add_greedy-distractor-injection-learned_adapter.json.gz. There, events 0 and 1 are accepted (sail l1 l0, sail l1 l2) with three injected distractors each, and event 2 (debark c0 l1) is rejected. The closeout (docs/experiments/native-arms/issue-130-closeout.md L13) carries the same error. The pinned JSON and episode records take precedence.
- **Fix:** Replace with 'every episode ends on a distractor pick, 20/36 of them on the first decision'. Add a % Source-conflict comment recording the closeout's wording against stress-evaluation.json and the episode records.
- **Status:** OPEN

#### 4 · CRITICAL · `iclr2026_conference_introduction.tex; iclr2026_conference_abstract.tex`

- **Location:** Intro L44 contribution 3 'and a comparator zoo places the adapter below named selectors'; Abstract L16 'places the adapter's solve-versus-budget score (.1042) below novelty-first selection (.1250)'
- **Issue:** Claim contradicted by the paper's own Table 12. outputs/choice-frontier/o4/metrics/analysis.json gives M1 learned 0.1042 [0.0278, 0.2014], bfs-order 0.0694 [0.0, 0.1528], worst-first 0.0556 [0.0, 0.1389], novelty-first 0.125 [0.0, 0.2778]. The adapter is above two of the three named selectors and below only novelty-first. Random-valid is the floor, not a selector. Every interval overlaps, and the fifteen-test Holm family licenses no ordering in either direction. The contribution bullet turns a point-estimate ordering against one selector into a general ranking.
- **Fix:** Contribution 3: 'a comparator zoo finds no positive learned Pareto dominance, and on M1 the adapter's point estimate (.1042) lies between bfs-order (.0694) and novelty-first selection (.1250), with overlapping intervals'. Abstract: add 'point estimates, intervals overlap' after the .1250 comparison.
- **Status:** OPEN

#### 5 · CRITICAL · `iclr2026_conference_discussion.tex`

- **Location:** Discussion L52 'Copyability-preserving shuffling is the information-loss regime, with 34/36 episodes still emitting valid operations while the search fails. Masking is output-contract destruction, with 36/36 episodes all-invalid and 0/18 all-invalid in the new text-masked visual-state cross cell.'
- **Issue:** Two numbers contradict the pinned JSON and the Results text for the same cells. outputs/native-arms/v1/r2-decomposition.json records text-shuffled partial_valid 16 (text) + 15 (multimodal) = 31 and goal_reached 3 (multimodal), so 'the search fails' is false for 3 of the 34. Results L278 records this exact source conflict and resolves it per the JSON, and the Discussion reverts to the closeout's '34/36 partial_valid'. The cross cell in stress-evaluation.json (textmask|text-masked|visual-state, 9+9 episodes, 0 successes, 18 invalid over 18 decisions) is 0/18 success with every episode all-invalid (Results L926-928). 'with ... 0/18 all-invalid' says that no episode was all-invalid.
- **Fix:** 'Copyability-preserving shuffling is the information-loss regime: 31/36 episodes are partial-valid without reaching the goal and 3/36 reach it. Masking is output-contract destruction: 36/36 all-invalid, and the new text-masked visual-state cross cell scores 0/18 with every episode all-invalid.'
- **Status:** OPEN

#### 6 · CRITICAL · `iclr2026_conference.tex (assembled PDF)`

- **Location:** Rendered PDF: Introduction starts p.1 and the Conclusion ends p.25 (manuscript.pdf, 37 pages); hub L3 '\usepackage{iclr2026_conference,times}'
- **Issue:** Submission blocker. The main text runs about 24 pages. The ICLR 2026 Author Guide (https://iclr.cc/Conferences/2026/AuthorGuide, fetched 2026-09-23) states 'At the time of submission, the main text should be 9 pages or fewer ... This limit will be strictly enforced. Papers with main text beyond the page limit will be desk-rejected.' Graded CRITICAL because desk rejection precedes any review. Venue-year mismatch in addition: the draft uses the ICLR 2026 template ('Under review as a conference paper at ICLR 2026') while citing ICLR 2026 proceedings (Kokel et al., 2026, 'The Fourteenth International Conference on Learning Representations (ICLR 2026)'). The ICLR 2026 submission cycle closed in September 2025.
- **Fix:** Confirm the target venue and cycle and swap in its style file. Cut the main text to the limit. Move Tables 3, 7, 8, 13, most of Sections 5.3-5.4, and Section 4's staged list to the appendix, and keep the identity finding, the choice-frontier contract, Table 11, Table 12, and one figure (I14) in the body.
- **Status:** OPEN

#### 7 · MAJOR · `iclr2026_conference_introduction.tex; iclr2026_conference_results.tex; iclr2026_conference_discussion.tex`

- **Location:** Intro L35 'so the additive-family result replicates across backbones, and the earlier BFS null on that backbone is an algorithm confound'; Results L233 'The earlier total null is therefore an algorithm confound. Under the same backbone, recipe, and panel shape, the additive-family result replicates on a second backbone.'; Discussion L37 'The additive best-first result replicates on a second backbone'; Discussion L41 'The pattern is algorithm-specific, not modality-specific.'; Conclusion L132 'that family replicates on a second backbone'
- **Issue:** Axis 3 / Axis 4. The paper never connects its identity finding to its own success map. By Results L339, additive cells of the enumeration contract carry no decision, so learned success there measures operation validity. Learned success appears only in those cells. On the choice-sensitive BFS/BFWS cells every baseline SFT episode fails (144/144) and DAgger BFS arms fail 155/162, and these account for most of the 229 other_invariant_violation failures (docs/experiments/expanded-study/failure-mechanism-analysis.md L185-191). Random-valid solves 15/24 and 17/24 there. What 'replicates across backbones' is contract fluency (R3 random-valid 24/24 per modality, SFT below it, second-backbone-v3/evaluation/analysis.json). The 'algorithm confound' is at least equally a choice-requirement confound, and 'algorithm-specific, not modality-specific' is a non-significance reading. 'Therefore an algorithm confound' is a causal verdict from a v2-versus-v3 comparison with fresh qualification and probe under a new protocol version.
- **Fix:** Say what the evidence shows: 'Learned success under the enumeration contract appears only in the additive cells, where the identity audit shows no decision to make, and the InternVL v3 cell replicates that contract fluency (31/36 vs 0/36 base, below random-valid 24/24 per modality).' Replace 'therefore an algorithm confound' with 'is consistent with an algorithm (choice-requirement) difference rather than a backbone null'. Drop 'not modality-specific'.
- **Status:** OPEN

#### 8 · MAJOR · `iclr2026_conference_discussion.tex`

- **Location:** Discussion L37 'and it is the only panel where random-valid falls below saturation'; Discussion L85 'The BFWS development panel is the only enumeration-contract panel where random-valid falls below 1.0'
- **Issue:** Axis 3. Contradicted by the paper's own tables. Random-valid is below saturation on expanded-baseline BFS 15/24 and BFWS 17/24 (Table 5, enumeration contract), on the DAgger unseen panel 45/72 (Table 7), on second-backbone v2 54/72 (Results L851), and under the choice-frontier contract 32/90 (Table 11).
- **Fix:** 'the only development panel on which random-valid falls below saturation and a positive learned contrast is reported'. State that the expanded-baseline BFS/BFWS cells are unsaturated and the learned policy scores 0/24 on them.
- **Status:** OPEN

#### 9 · MAJOR · `iclr2026_conference_abstract.tex; iclr2026_conference_introduction.tex; iclr2026_conference_results.tex`

- **Location:** Abstract L11 'Its own identity audit was a pre-registered pass condition and passes with 18/18 control pairs divergent, and headroom becomes measurable (... $-0.644$, 95\% CI $[-0.856, -0.422]$)'; Intro L43 'Its identity audit was a pre-registered pass condition, and it passes, so choice headroom becomes measurable.'; Results L375 'The frozen bootstrap resamples cells. Post-hoc task-clustered intervals ... [-0.889, -0.333]'
- **Issue:** Axis 2 falsifiability plus BENCHMARK operationalization. (a) The gate passes by construction. outputs/choice-frontier/v1/evaluation/identity-audit.json basis: 'random_valid (uniform menu choice) and exact_reference (heap head) diverge whenever a decision sees a frontier of size >= 2'. The preparation audit (preparation/visual-choice-frontier/audit.json, headroom_present true, 58 episodes) had already guaranteed such decisions. Exact solves 18/18 by budget construction (Discussion L1251). The advertised contribution is a sanity check that could not realistically fail. (b) 18/18 is 9 independent divergences: in identity-audit.json each task's greedy and w3 pairs have identical exact and random decision/expansion counts (e.g. 15puzzle-compact 5/4 vs 8/8 in both), per closeout Erratum item 2. The abstract and intro quote only the cell-level interval, whose post-hoc task-clustered counterpart is wider ([-0.889, -0.333]). (c) The instrument's resolution between non-oracle policies is one task. M5 holds only storage (o4/metrics/analysis.json m5_informative_tasks_D), and random-valid is 0 or 1 on the other 8. The panel tasks have C* 3-6 (optimal-costs.json) and exact expansions 3-6. The identity check and M1 are not argued against near-miss alternatives (e.g. a static count of decisions with two or more admissible options, or chance-corrected teacher agreement as the primary endpoint).
- **Fix:** Abstract and intro: 'passes on 9/9 tasks (18 cells, control sequences coincide across the two algorithms)', and give the task-clustered interval next to the frozen one. Describe the gate as a sanity check that holds by construction whenever a menu offers two or more states. Replace 'headroom becomes measurable' with 'random-valid and exact separate. Policy-level resolution currently rests on one discriminative task.' A frozen panel with at least eight discriminative tasks (the #133 boundary) is the experiment that would make the instrument claim stand.
- **Status:** OPEN

#### 10 · MAJOR · `iclr2026_conference_results.tex; iclr2026_conference_experimental_design.tex; iclr2026_conference_appendix.tex`

- **Location:** Results L348 'The training corpus was derived on CPU from 29 training tasks, independently of the stored exact traces'; Design L104 'train on a corpus re-derived through the new contract on CPU from the stored exact traces'; Appendix I 'The corpus replays the frozen paired-phase exact traces through the new contract on CPU'
- **Issue:** Axis 3. Three sections give opposite provenance for the same corpus. The closeout (issue-132-closeout.md L66) says 'derived independently of the stored exact traces'. The preparation report says 'every derived episode matched its stored exact trace expansion for expansion' (report.json expansion_gate). A reader cannot tell whether the corpus is a replay of stored traces or an independent re-derivation checked against them.
- **Fix:** One sentence used in all three places: 'derived on CPU by replaying the frozen exact traces through the new contract and verified expansion-for-expansion against them (58 episodes bit-exact)'. If 'independently' means an independent re-derivation, say 'independently re-derived and checked against the stored exact traces'.
- **Status:** OPEN

#### 11 · MAJOR · `iclr2026_conference_introduction.tex; iclr2026_conference_appendix.tex; iclr2026_conference_discussion.tex`

- **Location:** Intro L35 'Observation corruption localizes the learned controller in the language channel. Masking or shuffling it drops success by up to 0.944'; Intro L44 'the learned controller runs on the textual scaffold rather than the rendered state'; Appendix L419 'The observation-corruption suite (#126) confirms this empirically: corrupting the text channel drops success by up to $-0.944$'; Discussion L52 'the multimodal text-minus-visual isolation contrast is $-0.694$ $[-0.889, -0.472]$'
- **Issue:** Axis 4. Results L930 states 'The language-channel claim survives only in its shuffled form', and #131 comment 1 is binding on this. Yet the intro, contributions, and appendix still pool the masked regime, which R2 shows is output-contract destruction (r2-decomposition.json: 36/36 all_invalid). The isolation contrast -0.694 uses a text-channel term of -0.806, which averages masked (-0.889) and shuffled (-0.722) (issue-126-closeout.md L63-65), so it is contaminated by the destroyed-contract regime. 'Confirms' is the wrong register.
- **Fix:** Cite shuffled only: 'copyability-preserving text shuffling lowers success by -0.944 (text) and -0.722 (multimodal), while visual corruption costs at most -0.111'. Flag the -0.694 isolation contrast as pooling a contract-destruction regime. Replace 'confirms' with 'is consistent with'.
- **Status:** OPEN

#### 12 · MAJOR · `iclr2026_conference_introduction.tex; iclr2026_conference_experimental_design.tex; iclr2026_conference_results.tex; iclr2026_conference_discussion.tex`

- **Location:** Intro L48 '[TODO: issues \#96/\#98/\#102/\#103]'; Design L133 'remain unexecuted (issues #96 and #98 open)' with '[TODO: full-scope v1, issues \#96/\#98]'; Results L36 'the corresponding issues remain open [TODO: ...]'; Results L171, L233 'with its issues still open [TODO: ...]'; Results L449; Discussion L123
- **Issue:** TODO hygiene and a false factual statement. `gh issue view` (2026-09-23) returns #96, #98, #102, #103 all CLOSED on 2026-09-21 (stateReason COMPLETED), each with a closing comment 'Supervisor decision: v1 scope withdrawn — closing'. Seven visible markers and at least six prose sentences tie the manuscript to tickets that no longer exist as open work. The brief's rule requires every visible TODO to be tied to an open ticket, and the round-2 rule drops markers that the prose already states (Design L133 and Results L171 do both).
- **Fix:** Delete all seven markers and the stale % TODO comments (Results L172, L236, L450, Design L135, Intro L49). Rewrite the prose as 'the full-scope v1 branches were withdrawn after their terminal VALID_STOP receipts (issues #96/#98/#102/#103, closed 2026-09-21) and will not be executed'.
- **Status:** OPEN

#### 13 · MAJOR · `iclr2026_conference_results.tex`

- **Location:** Results L30 section roadmap 'Sections 5.5 to 5.9 report the follow-up audits in argument order, from channel tests and image-only arms to menu manipulation, the enumeration-contract identity finding'; Results L299 (5.6) 'The decision-relevant signal these policies use is the grounded unscored candidate menu itself'; identity finding first appears at 5.8 (PDF p.19)
- **Issue:** Axis 5 and the argument-order rule. The abstract and intro lead with the identity finding, but Results reaches it only at 5.8 after 18 pages. The native-arms 'leak' interpretation (5.6) and the menu-manipulation verdict (5.7) come before the structural basis that explains both (submission-order invariance, 5.8). Sections 5.2-5.4 interpret the additive old-contract rows as learned success before the audit that reclassifies them as operation validity. Interpretation precedes its receipt.
- **Fix:** Put the identity audit immediately after 5.1 as the first follow-up receipt. Then give menu manipulation (reinterpreted per I2), native arms, the choice-frontier redesign, and the zoo, and add a forward note in 5.2 that the additive rows are reinterpreted by that audit.
- **Status:** OPEN

#### 14 · MAJOR · `all section files`

- **Location:** 0 figure environments, 0 \includegraphics across the nine section files and the hub, versus 17 table environments. The first table is the related-work axis table (Table 1)
- **Issue:** Axis 1 / Axis 5. The tension (random-valid identical to exact under one contract, separated under the other) exists only in prose and in Tables 5, 11, and 12. A skimming reviewer's 10-minute test lands on a related-work design-axis table.
- **Fix:** Add a Fig. 1 with two panels. (a) The enumeration versus choice-frontier contract on one additive task. (b) Solve fraction versus budget multiplier (M1 curves) for exact, random-valid, learned, and the three selectors, with the BFS/BFWS enumeration-contract random-valid points marked to show where choice was already measurable (I1).
- **Status:** OPEN

#### 15 · MAJOR · `iclr2026_conference_related_work.tex`

- **Location:** Related Work 'Evaluation-validity work in planning and reasoning ...' paragraph (L70ff), which cites PlanBench, BEHAVIOR-1K, VQA priors, and video MCQ position bias but no action-candidate literature
- **Issue:** Citation failure on the headline claim's anchor. That grounded admissible-action lists are privileged information which changes what an agent's success measures is published practice in text-based game RL: Jericho's valid-action handicap (Hausknecht et al., 2020, arXiv:1909.05398). CALM (Yao et al., EMNLP 2020, arXiv:2010.02903, abstract fetched 2026-09-23) states that its generator 'is competitive with or better than other models that have access to ground truth admissible actions'. Multiple-choice position bias in LLM selectors is also directly relevant to the last-label finding. Without these, the 'measurement finding' reads as a discovery when it is a known handicap in a new setting.
- **Fix:** Add a sentence citing Jericho's valid-action handicap and CALM (verified keys in related_refs.bib) and reframe the contribution as operationalizing a per-decision identity check for that known handicap in search-execution evaluation.
- **Status:** OPEN

#### 16 · MAJOR · `iclr2026_conference_experimental_design.tex`

- **Location:** Design L36 'The frozen protocol has not yet pinned the validity-constrained sampling distribution, the candidate access granted to the control, the runtime filtering step, or the explicit absence of retry and repair.'
- **Issue:** Axis 4 / Axis 3. Random-valid is the pivot of the identity audit, Table 5, Table 6, the BFWS 0.467, and every learned-to-control gain, yet its sampling distribution under the enumeration contract is declared unpinned. Under the choice-frontier contract the same name denotes uniform menu choice (identity-audit.json basis), a different distribution. The paper's central comparator is undefined in one contract and redefined in the other.
- **Fix:** Pin the enumeration-contract random-valid sampler from the executed code (distribution, candidate access, filtering, retry) in Section 4 or Appendix C, and give the choice-frontier control a distinct name or an explicit per-contract definition.
- **Status:** OPEN

#### 17 · MAJOR · `iclr2026_conference_experimental_design.tex; iclr2026_conference_results.tex`

- **Location:** Design L104 'The choice-frontier evaluation reuses the frozen 9-task native-arms membership under both additive algorithms.'; Results 5.9 'the 144 stored #132 episodes enter it post-hoc'
- **Issue:** Axis 2 post-hoc smell and BENCHMARK adoption risk. The same nine tasks (8 domains, 7 compact / 2 expanded) serve #126, #129, #130 R1, #132, and #133. The #132 redesign was frozen after #130 outcomes on those tasks, and the #133 metric set after #132 outcomes on them. No discover-then-confirm step exists: no fresh panel, no held-out tasks for the new contract. The tasks are the cheapest members (C* 3-6, optimal-costs.json).
- **Fix:** State the panel reuse and its adaptive-overfitting risk in the Section 5.10 boundary. Name a fresh frozen choice-frontier panel, drawn outside these nine and including non-trivial tasks, as the required confirmation before any instrument-level claim.
- **Status:** OPEN

#### 18 · MAJOR · `iclr2026_conference_appendix.tex; iclr2026_conference_reproducibility.tex; iclr2026_conference_experimental_design.tex`

- **Location:** Appendix L315 'Issue \#133 closing comment (comment 5788941573)'; Reproducibility L76 'The existing \texttt{deadline-study-v1} release'; Design L161 'Reviewer stress tests (issue \#130, executed)'
- **Issue:** Double-blind risk. A GitHub comment ID resolves to one public repository and its author (#131 cites it as https://github.com/Sino-Huang/multimodality_on_planning/issues/133#issuecomment-5788941573). Named internal releases and 'reviewer stress tests' / 'reviewer-blocker window' (Results L643, Table 3) also expose the project's prior review history.
- **Fix:** Remove the comment ID and internal release name from the submission (keep them in the % Evidence comments). Rename 'Reviewer stress tests' / 'reviewer-blocker window' to neutral protocol names (e.g. 'stress tests R1-R4').
- **Status:** OPEN

#### 19 · MAJOR · `iclr2026_conference.tex (no section)`

- **Location:** No LLM-usage section anywhere in the nine section files or the appendix
- **Issue:** Submission compliance. The ICLR 2026 Author Guide (URL in I6) requires a separate LLM-usage section when LLMs 'played a significant role in research ideation and/or writing' and warns 'Not disclosing significant LLM usage can lead to desk rejection.' [INFERENCE] The #131 briefs and the section STATUS banners record agent-driven writing rounds, which meets that threshold.
- **Fix:** Add an appendix section 'LLM Usage' describing the agent-assisted writing, citation, and review passes and the human verification applied.
- **Status:** OPEN

#### 20 · MAJOR · `iclr2026_conference_results.tex`

- **Location:** Results L303 'The learned adapters succeed on 10/10 shifted-init and 10/10 scale-up episodes for both arms, and the pretrained base scores 0/20.'
- **Issue:** Denominator does not close against the pinned source. outputs/native-arms/v1/stress-evaluation.json has 8 variant cells of 10 episodes (5 successes, 5 invalid each), and the episode store holds 40 learned_adapter and 40 pretrained_base variant files (80 total, matching Table 3's '80 variant'). The base total is 0/40. '0/20' holds only per family, and read as written, 40 learned + 20 base = 60 does not match the 80 reported in Table 3.
- **Fix:** '... and the pretrained base scores 0/20 on each strain (0/40 in total)'.
- **Status:** OPEN

#### 21 · MINOR · `iclr2026_conference_abstract.tex`

- **Location:** Abstract L5-6 '... and ask whether such training can be measured to improve search choice. Under the original enumeration contract, ..., the answer is that it cannot be measured.'
- **Issue:** Style rule: rhetorical question followed by its answer.
- **Fix:** State the finding declaratively (and scoped per I1).
- **Status:** OPEN

#### 22 · MINOR · `iclr2026_conference_appendix.tex; iclr2026_conference_related_work.tex`

- **Location:** Paragraphs without a preceding '% Paragraph purpose:' comment: Appendix L62 ('The two broad categories are ...'), L368 ('Cell~A is the headline ...'), L389 ('This addendum supersedes ...'); Related Work L44 ('Step-level and process supervision ...'), L51 ('Recent work uses visual intermediate states ...'), L63 ('Constrained-decoding methods ...')
- **Issue:** Paragraph-purpose convention violated in six paragraphs.
- **Fix:** Add a '% Paragraph purpose:' line before each.
- **Status:** OPEN

#### 23 · MINOR · `iclr2026_conference_results.tex`

- **Location:** Results L434 caption 'Seeds 17/29/71 frozen pre-launch; 534 new episodes independently replayed; aggregation descriptive ($n{=}3$).'; Results L171 'visual 41/50; by algorithm, greedy 67/75'
- **Issue:** Prose semicolons outside comma-lists (8 semicolons in Results. The L251 and L388 ones are list separators and acceptable).
- **Fix:** Split into sentences or use commas.
- **Status:** OPEN

#### 24 · MINOR · `iclr2026_conference_experimental_design.tex; iclr2026_conference_reproducibility.tex`

- **Location:** Design L52 'never summed with the 336 GPU-hour program ledger (Appendix~\ref{appendix})'; Design L104 'Contrasts use the paired conventions of Appendix~\ref{appendix}'; Reproducibility L65 '(Appendix~\ref{appendix})'
- **Issue:** The frozen label resolves to Appendix A (Operation Schemas), but the ledger is in Appendix E and the bootstrap conventions in Appendix F. Rendered text reads 'Appendix A' in all three places.
- **Fix:** Write 'Appendix~\ref{appendix}, Receipt Tables' / 'Statistics' or add named in-appendix labels owned by the appendix file.
- **Status:** OPEN

#### 25 · MINOR · `iclr2026_conference_related_refs.bib`

- **Location:** iclr2026_conference.blg L11 'Warning--can't use both volume and number fields in orseau2021policyguided'
- **Issue:** BibTeX warning, the same class critic-15 fixed for the BFWS entry.
- **Fix:** Drop `number` from orseau2021policyguided.
- **Status:** OPEN

#### 26 · MINOR · `iclr2026_conference_results.tex`

- **Location:** Results L348 'every corpus episode carries at least one decision whose menu offers two or more states (maximum 315)'
- **Issue:** Ambiguous number. 315 is the maximum count of multi-option decisions in one episode (preparation/visual-choice-frontier/audit.json headroom_decisions_per_episode, astar-pair-68102553...:best_first_add_w3). The maximum menu size is 222 (report.json menu_size_range.max). The closeout's 'max menu 315' is wrong, and the sentence invites that reading.
- **Fix:** '(up to 315 such decisions in one episode, menus of up to 222 states)'.
- **Status:** OPEN

#### 27 · MINOR · `iclr2026_conference_experimental_design.tex`

- **Location:** Design L152 'Until these choices are set, the manuscript is a result-ready empirical skeleton rather than a preregistered evaluation protocol.'
- **Issue:** Leftover planning-document sentence. It calls the paper a skeleton and contradicts the pre-registered follow-up protocols reported elsewhere. Spelling alternates 'preregistered' (Design L124, L152, Discussion L139) and 'pre-registered' (everywhere else).
- **Fix:** Replace with 'Until these choices are recorded, the held-out evaluation cannot be frozen.' and normalize to 'pre-registered'.
- **Status:** OPEN

#### 28 · MINOR · `iclr2026_conference_appendix.tex; iclr2026_conference_results.tex`

- **Location:** Appendix L428 'information-lossy: 24/24 variants are text-lossy, 18/24 are multimodal-lossy, and 0/24 are visual-lossy'; Results L171 'all 5 admitted variants are text-lossy, 3 multimodal-lossy, and 0 visual-lossy'
- **Issue:** Same stratum with two denominators and no label. 24 is the family-wide eligible P3 set and 5 the admitted subset (issue-124-closeout.md L111-114).
- **Fix:** Appendix: 'family-wide (24 eligible P3 variants)'.
- **Status:** OPEN

#### 29 · MINOR · `iclr2026_conference_results.tex`

- **Location:** Results L225 'Random-valid and exact reference both score 24/24 per modality.' (12-task key-cell panel)
- **Issue:** Control denominators (24 per modality) exceed the 12 panel tasks per modality with no explanation, while model rows are /12 (second-backbone-v3/evaluation/analysis.json by_modality: episodes 12, random_valid_successes 24).
- **Fix:** State what the 24 control episodes per modality are (e.g. two reused control episodes per task).
- **Status:** OPEN

#### 30 · MINOR · `iclr2026_conference_introduction.tex; iclr2026_conference_results.tex`

- **Location:** Intro L27 'which the closeout reads as a menu leak'; Results L299 'This null licenses the leak interpretation the closeout records'
- **Issue:** Internal project documents ('the closeout') cited as interpretive authority in reader-facing prose. About 94 internal issue numbers appear in the body.
- **Fix:** State the interpretation as the paper's own and move ticket numbers into % Evidence comments or one appendix index.
- **Status:** OPEN

#### 31 · MINOR · `iclr2026_conference_discussion.tex`

- **Location:** Discussion L45 'Learned arms fail later.' followed by 'Learned first failures cluster in steps 0-2 (137/88/46)'
- **Issue:** 137 of 407 learned first failures occur at decision 0, the same index as every base failure, so 'later' contradicts the next sentence.
- **Fix:** 'Learned arms fail early but mostly after parsing: ...'.
- **Status:** OPEN

#### 32 · MINOR · `iclr2026_conference_introduction.tex; iclr2026_conference_discussion.tex`

- **Location:** Intro L7 'instances to be generated systematically, solutions verified automatically, and difficulty controlled precisely'; Discussion L29 'conducts unassisted internal search, holds unbounded frontier state, or possesses general planning autonomy'
- **Issue:** Rule-of-three constructions.
- **Fix:** Cut to two items or restructure.
- **Status:** OPEN

#### 33 · MINOR · `iclr2026_conference_results.tex`

- **Location:** Results L36 'spent 53.52 of those hours (15.9\%) at the #120 synthesis snapshot, before the #126/#127 addenda'
- **Issue:** Results reports only the stale snapshot. The current program total 68.5244/336 appears only in the Reproducibility statement and in Appendix Table 15 (as 68.52), so a Results reader never sees the ledger the rest of the paper uses.
- **Fix:** Add 'and 68.5244 after the #126/#127 addenda' to the same sentence.
- **Status:** OPEN

#### 34 · MINOR · `iclr2026_conference_results.tex`

- **Location:** Results L303 'which suggests the scaffold's scalar and bookkeeping text carried no useful signal on these variants'
- **Issue:** Unpaired and not matched: native arms 10 episodes per arm (visual only) against full-scaffold 30 episodes pooled over three modalities. The inference is post-hoc and unlabelled.
- **Fix:** Label as post-hoc and unpaired, or drop the 'suggests' clause.
- **Status:** OPEN

#### 35 · MINOR · `iclr2026_conference_results.tex; iclr2026_conference_experimental_design.tex; iclr2026_conference_introduction.tex`

- **Location:** Results L172 '% TODO: #96/#98 remain open'; Results L236; Results L450; Design L135 '% #102/#103 (second backbone) remain open'; Intro L49
- **Issue:** Stale source comments that restate the false ticket status (see I12). They will mislead the next writer.
- **Fix:** Update with the 2026-09-21 withdrawal.
- **Status:** OPEN

#### 36 · MINOR · `iclr2026_conference_discussion.tex`

- **Location:** Discussion L52 'Menu manipulation then confirms that the policy reads that menu by content.'; Discussion L29 'The successor-prediction null confirms the runtime dependence'
- **Issue:** Axis 2 wording register ('confirms'). The first instance is also substantively unsupported (I2).
- **Fix:** Replace with 'is consistent with' and scope per I2.
- **Status:** OPEN

## Closed history

Reviews 1--14 predate the multi-file draft and the #131 round. They audited design artifacts, the title, the abstract, or the introduction at earlier evidence boundaries; each was resolved in the revision that followed it, and none of their findings remain open. Review 15 audited the 2026-09-22 full draft and gated the revision that became commit `4d5842e`. Full text of every folded file is recoverable from git history:

```
git show 5357a65:manuscript/critics/2026-09-22-critic-15.md
git log --diff-filter=D --oneline -- manuscript/critics   # the deletion commit
```