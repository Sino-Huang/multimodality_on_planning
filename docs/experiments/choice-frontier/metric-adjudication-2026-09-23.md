# Metric adjudication 2026-09-23 — what does "planning choice ability" mean measurably?

Post-close methodological review of the choice-frontier arm (#132), triggered by the author's
challenge: search algorithms are themselves rule-following heuristics, so "learned beats random"
may be the wrong capability metric; the comparison set should be the program's own frozen
algorithm family (bfs, best_first_width, best_first_add_greedy, best_first_add_w3).

Two independent reviewers were run. Reviewer 1 (area-chair-methodology lens) recomputed the stored
episodes directly; its factual claims were then independently re-derived from the stored evidence
before any of them were propagated (verification column below). Reviewer 2 (general lens) ran
without access to Reviewer 1's output; its verdict is appended when delivered.

## Independently re-verified facts (this session, from stored artifacts)

| claim | source | re-derived |
| --- | --- | --- |
| learned expansions depot/elevators/ferry 8/6/7 vs exact 5/4/4; storage-greedy 3=3 | `evaluation/episodes/**` | exact match |
| learned teacher agreement 0.174 vs chance 0.269 (132 decisions); last-label 54.5%, first-label 2.3% | `evaluation/episodes/**` learned | exact match |
| random_valid agreement 0.289 vs chance 0.262 (636 decisions, 5 seeds); exact 1.000 (84) | `evaluation/episodes/**` controls | exact match |
| teacher corpus last-label rate 0.120 vs chance 0.104 (978 records, menu ≥ 2) | `preparation/.../store.json` | exact match (978 vs reviewer's 972, immaterial filter difference) |
| greedy/w3 reference expansions identical on all 9 evaluation tasks | `final-panel.json` reference_costs | confirmed (4=4, 6=6, 6=6, 5=5, 4=4, 4=4, 3=3, 5=5, 5=5) |
| elevators-compact bfs reference = 6 expansions (an earlier quote of 35 misread the expanded variant) | `final-panel.json` | confirmed |
| learned's solved-cell expansions equal frozen bfs counts (8/6/7) | cross-reference | confirmed |

## Reviewer 1 verdict (paper-reviewer agent, verbatim)

- **Q1**: learned − random at one budget with binary success is a floor test, not a capability
  endpoint. Literature capability axis: search effort under budget + solution quality vs named
  algorithms (LevinTS arXiv:1811.10928; PHS arXiv:2103.11505; learned-heuristic GBFS coverage /
  expanded states, e.g. Chrestien et al. arXiv:2310.19463; Neural A* Opt/Exp ratios
  arXiv:2009.07476; VIN arXiv:1602.02867; Searchformer arXiv:2402.14083; PlanBench/LLM-Modulo
  treat near-random as absence of planning).
- **Q2**: the "expansion parity" rescue is false (F1). Effort metrics point the same way as
  success; the null is not a power artifact.
- **Q3**: exact_reference is legitimate as the imitation target (the adapter was distilled from
  it), not as ground truth for planning. learned − exact = −0.611 is the honest capability
  contrast; pitfalls: budget calibrated to reference (exact 18/18 by construction), h_add GBFS not
  cost-optimal, greedy/w3 coincide on this panel.
- **Q4 (required metric set)**: M1 solve rate vs budget multiplier m ∈ {1.0..2.0} AUC, task as
  cluster unit (prefix-invariance makes truncation valid); M2 expansion-overhead ratio ρ = X/R_t
  (geometric mean on co-solved cells, censored version for failures); M3 cost suboptimality
  κ = C/C* with C* from one offline CPU planner call per task; M4 chance-corrected on-policy
  teacher agreement + label-position histogram (uses 132 decisions, most powerful endpoint);
  M5 discriminative-cell subset D = {t : 0 < p_random,t < 1} defined from controls only (= storage
  alone today, descriptive-only). M1–M5 are CPU-recomputable from the 144 stored episodes and must
  be labelled exploratory/post-hoc.
- **Q5**: soften-and-reframe (option b); no positive choice-quality reading is open; a re-run is
  needed only before any positive claim.
- **Q6 (zoo)**: position learned on the program's own four-algorithm efficiency frontier under
  identical contract+budget, random as floor, worst-first as negative control. Freeze zoo list,
  tie-breaks, primary metric (task-clustered M1 AUC) before any comparator episode exists; report
  every member; claim unit is dominance with Holm correction; comparator additions are dated
  protocol amendments; state the oracle-access asymmetry (zoo rules read g/h scalars; the VLM sees
  only scenes). BFS-order would solve only depot/elevators/ferry (where random already saturates);
  novelty-first selection (name it that, not BFWS — selection alone cannot reproduce novelty
  pruning) would plausibly go 9/9 and adds power via (a) agreement vs either competent ordering,
  (b) an effort ladder add < novelty-first < bfs. #123's 0/36-on-BFS is an algorithm-confound
  result under the old contract, NOT a comparator-zoo result — do not cite it as one.
- **Q7**: distillation caps honest expectations at the imitation bound (Ross et al. 2011);
  "beats GBFS" is an exceptional claim needing the pre-registered zoo, task-clustered
  significance, an account of where the extra information comes from, and survival at m ≤ 1.25.
- **Verdict**: WEAK REJECT for any choice-ability claim; critical issue was the false efficiency
  sentence (corrected in the closeout erratum).

Recommended manuscript paragraph (reviewer-drafted, style-checked against #131 rules):

> Under the choice-frontier contract, training takes the policy from 0/18 to 7/18 goal-reaching
> episodes with no invalid operations (learned minus base +0.389, 95% CI [+0.167, +0.611]). This
> is a gain in contract fluency. It is not evidence of planning choice. Choice quality is not
> supported. Success does not differ from uniform-random frontier selection (+0.033, 95% CI
> [−0.033, +0.133]), and that contrast rests on a single task, because random selection solves
> every seed on three tasks and none on five. The imitation gap to the distillation teacher is
> large (learned minus reference −0.611, 95% CI [−0.833, −0.389]). In an exploratory re-analysis
> of the stored episodes, the learned policy expands 50 to 75 percent more states than the
> reference on three of the four tasks it solves, at least as many as the median random seed. It
> selects the teacher's frontier state in 17.4 percent of 132 multi-option decisions, against a
> chance rate of 26.9 percent, and emits the last menu label in 54.5 percent of them. We read
> these results as an imitation failure consistent with a label-position shortcut. They do not
> show that the instrument lacks sensitivity. We make no claim relative to other search
> algorithms.

## Reviewer 2 verdict (general reviewer agent, independent)

Reviewer 2 (general `task` agent, run blind to Reviewer 1) converged on the core adjudication and
diverged on mechanism. Verdict: **reframe now (option b); pre-register a small comparator /
efficiency follow-up (option c) before any generalized claim in either direction.** Convergence:
random is a sanity floor, not the capability ceiling; the task is the cluster unit (18 cells = 9
tasks with algorithms as repeated measures; 90 random episodes = 5 Monte Carlo seeds within
task); the +0.033 contrast is single-task-driven; a CI crossing zero establishes neither
superiority nor equivalence (an "≈ random" claim needs a pre-registered equivalence margin); no
remedy prescription is licensed by this evidence. Its manuscript paragraph is more conservative
than Reviewer 1's: it treats the arm as evidence the redesign makes frontier choice consequential
and the adapter learns to operate the contract, and explicitly declines the label-position
mechanism claim (it did not compute one).

Its independent recomputations (read-only, over all 144 episodes; convergent where overlapping):

- Coverage-curve truncation (replay-free, prefix-valid): stored successes at 1.5x reference
  expansions: learned 1/18, random 6/90, exact 18/18; at 1.75x: 3/18, 26/90, 18/18; at 2x: 7/18,
  32/90, 18/18 (curves cannot extrapolate past the stored 2x cap).
- First discretionary disagreement: learned departs from the exact selected-state order at the
  first multi-option decision in 12/18 cells (after 2 in 4, after 4 in 2; 1/18 follows the full
  order). Framed as an imitation diagnostic, not proof of inferiority.
- Survivor-conditioned expansion ratio 1.529 (learned) vs 1.436 (random) vs reference — labelled
  descriptive/selection-conditioned, not a population efficiency estimate.
- 45/45 paired random runs produce identical result dictionaries and expanded-state sequences
  across greedy and w3 — independent confirmation that the two algorithm cells are not
  independent evidence for the controls.
- Task-cluster (9 tasks) exploratory bootstrap of learned − random: [0.000, +0.100]; it declines
  to present this as confirmatory and keeps the frozen 18-cell interval primary.

Implementation qualification for the follow-up (Reviewer 2 only): `ChoiceFrontierController`
subclasses an additive-only BestFirstController, so BFS/BFWS-order comparators are NOT a config
flag — their CPU selectors must be integrated and audited under the same
observation/action/budget contract, any changed frontier-admission bookkeeping disclosed, and the
shared primary cap kept at the frozen 2x additive reference (no per-comparator cap rescaling).

## Where the two reviewers disagree

- Mechanism: Reviewer 1 names a label-position shortcut (independently re-verified above);
  Reviewer 2 makes no mechanism claim. Manuscript wording should follow Reviewer 1's numbers but
  frame the mechanism as exploratory, per its own label.
- Negative-claim licensing: Reviewer 1 reads the effort/agreement metrics as sufficient for an
  exploratory "imitation failure" reading; Reviewer 2 requires the pre-registered follow-up
  before even a generalized negative claim. The closeout erratum adopts the stricter rule.

## Follow-up scoping (from the review)

- **Ticket A (CPU-only, pre-registered before it runs)**: M1–M5 on stored episodes with
  task-cluster bootstrap; offline C* per task; comparator arms bfs-order + novelty-first selection
  over the add-controller frontier on the 9 panel tasks at m ≤ 2 (plus controls at m ∈ {3, 4});
  learned label-position audit. Output decides whether any GPU ticket is justified.
- **Ticket B (GPU, only if A runs and a positive claim is still wanted)**: new pre-registered
  window; first endpoint M4 agreement above chance on a panel with ≥ 8 discriminative tasks and
  matched train/eval horizon. No GPU run is justified to defend the current adapter, given the
  shortcut finding.

