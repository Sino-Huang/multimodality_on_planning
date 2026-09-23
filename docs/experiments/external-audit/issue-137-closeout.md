# #137 closeout: external identity audit

**Audited: ScienceWorld (type B) -> verdict CHOICE_REGISTERED (predicted divergent).**
The prediction held. On the published ScienceWorld interface a uniform random choice among
the simulator's valid actions diverges from the gold trajectory at the first decision in
every one of 1,000 pairs. It completes 0 of 200 tasks, while the reference completes 183 of
200 under the paper's 100-step budget. This interface registers choice. The zero-headroom
result of our own audit (`outputs/native-arms/v1/identity-audit.json`, 48/48 identical)
depends on our complete-set submission contract; it does not describe this published
practice.

Commits: survey `94b054f`, protocol `914339d`, evidence (this file and the runner) in the
commit that adds it.

## Stage 1 survey (summary)

Source: `issue-137-survey.md`. All facts come from primary sources fetched on 2026-09-24.

- 7 candidates passed the inclusion filter: AutoPlanBench (ICAPS 2025), ScienceWorld
  (EMNLP 2022), GLAM/BabyAI-Text (ICML 2023), WebShop (NeurIPS 2022), RAP (EMNLP 2023),
  LLM-First Search (arXiv 2025 with code), EmbodiedBench (ICML 2025). 3 more were screened out
  on the filter: Tree-Planner, LFG, ViPlan.
- Interface types: 5 type B, 2 type C, 0 type A. No published interface in the survey has our
  complete-set submission contract. The nearest is LFG, where the LLM scores every frontier;
  it was screened out because it releases no evaluation harness, and even there the
  frontier order depends on the model's scores.
- CPU-feasible under the paper's own budget: AutoPlanBench, ScienceWorld, GLAM. All three
  predict divergent. The only saturated prediction is LLM-First Search, and it depends on a
  token budget that a zero-token control never exhausts. That candidate is dropped at the
  feasibility step.
- Fixed rule: the rest are tied on criterion 2 (no identical/saturated prediction), so the
  most cited wins: ScienceWorld (320 citations) over GLAM (287) and AutoPlanBench (26).
  The second-ranked candidate has the same prediction, so only one benchmark was audited.
  Selection comment:
  https://github.com/Sino-Huang/multimodality_on_planning/issues/137#issuecomment-5801181178

## Audit (protocol `issue-137-protocol.md`, frozen at 914339d before any run)

Tasks: the first 200 test variations in Table 2 order. These are boil, melt, freeze and
change-state (9 each), use-thermometer (135) and measure-melting-point-known (29 of 109).
Budget: `envStepLimit=100`, no simplifications. Reference: the upstream gold trajectory.
random_valid: uniform choice over the sorted `infos["valid"]`, seeds 17/5077/6131/7409/8527.

| quantity | value |
|---|---|
| tasks | 200 |
| pairs_checked / identical / divergent | 1000 / **0** / 1000 |
| first_divergence_index (median, min, max) | 0, 0, 0 |
| success.reference | **0.915** (183/200) |
| success.random_valid per seed (17, 5077, 6131, 7409, 8527) | 0.000, 0.000, 0.000, 0.000, 0.000 |
| success.random_valid_mean | **0.000** |
| saturation (random >= 0.9 x reference) | false |
| published_model_success (DRRN Table 2 score, audited tasks, weighted) | 0.084 (headline 0.17 over 30 tasks) |
| random_fraction_of_published | 0.000 |
| mean clipped score max(score,0)/100: reference / random_valid | 0.973 / 0.0002 |
| published Random-Valid score on the same tasks (Table 2) | 0.00 |
| verdict | **CHOICE_REGISTERED** |

Per task, reference successes: boil 3/9, melt 6/9, freeze 4/9, change-state 6/9,
use-thermometer 135/135, measure-melting-point-known 29/29. On 17 of the 36 Matter tasks
the gold trajectory needs more than 100 moves (these episodes end `step_limit` with a
partial score). The shortfall comes from the paper's budget, not from the controls.

Of the 1,000 random_valid episodes, 997 end in task failure (score -100) and 3 hit the step
limit. In 989 of the failures the last action is a wrong `focus on …`. The median episode
length is 18 decisions. At the first decision the valid set has a median of 473.5 actions
(range 229-3363). Our control reproduces the paper's own Random-Valid column (0.00 on all
six audited tasks).

Determinism: 10 random_valid episodes (sampled with `random.Random(137)`) were re-run in a
fresh simulator process, and all 10 are byte-identical to the stored logs
(`determinism.json`). The smoke run (`--limit 3`) passed before the full run, with 10/10
identical re-runs.

Structural basis: ScienceWorld is a sequential action-choice contract. Each decision
executes one valid action, which changes the state, the next valid set and the score, and a
wrong `focus on` ends the episode. The order of choices therefore decides the outcome, and
no data structure re-orders them.

## Upstream pins

| component | repo | commit | license | use |
|---|---|---|---|---|
| ScienceWorld 1.3.0 | https://github.com/allenai/ScienceWorld | e8216d6044e8e39be9fcb185e3b2dfb602584b52 | Apache-2.0 | audited; JAR sha256 `e77b0fee7d68abe3…` |
| AutoPlanBench | https://github.com/minecraft-saar/autoplanbench | c7cbbb26bde0be4ab200a2bbeb0d33e4c60f39ec | Apache-2.0 | Stage 1 feasibility only |
| VAL | https://github.com/KCL-Planning/VAL | 3c7a1f330bdab0ba28a4762bb45c3f06c27fb6d4 | BSD-3-Clause | Stage 1 feasibility only |
| Fast Downward 22.12 | https://github.com/aibasel/downward | 6251c60f509fe5bfd54849255d3549a8cbf0ebc1 | GPL-3.0 | Stage 1 feasibility only |

All clones are untracked under `outputs/external-audit/v1/upstream/`. ScienceWorld is
imported editable from its clone into the separate venv `outputs/external-audit/v1/venv-sw`
(uv, Python 3.10.20, py4j 0.10.9.9, system OpenJDK 17). The runner re-executes itself there
when started from ada_vla, which is left unchanged. The install commands are in
`outputs/external-audit/v1/upstream-manifest.json`.

## Evidence index (sha256, first 16)

```
d90bba65a70859b7  scienceworld/identity-audit.json
9965dc5ceea87c26  scienceworld/determinism.json
7c32fdf6b587ecdd  scienceworld/tasks.json
e519817fc60c7bae  scienceworld/run-info.json
022644bb65563466  scienceworld/episodes/** (1200 files)
b4017f008148880d  scienceworld-run.log
f92313d4d68820f1  scienceworld-smoke/identity-audit.json
939fbcf59d89cff1  scienceworld-smoke/determinism.json
a3847ee964ce22c5  scienceworld-smoke/tasks.json
e5717165acf96a23  scienceworld-smoke/run-info.json
857740e1698c5a25  scienceworld-smoke/episodes/** (18 files)
1392590063bca9d7  upstream-manifest.json
5b49aecc0fa0a93e  evidence-index.json (sha256 of all 1,228 files)
```

Root: `outputs/external-audit/v1/` (untracked by repo convention). A directory digest
(`/**`) is the sha256 of the sorted `path sha256` lines for that directory in
`evidence-index.json`. Tracked: `scripts/run_external_identity_audit.py`,
`docs/experiments/external-audit/issue-137-{survey,protocol,closeout}.md`.

## Limitations

- Controls only. No model was run and no published model number was reproduced; model
  numbers are quoted from Table 2 of the paper.
- The 200 audited tasks are the first 200 of 1,819 test variations in the paper's order, so
  they cover 6 of 30 tasks (Matter and Measurement). On all six the paper's own Random-Valid
  score is 0.00. The verdict is about this interface on these tasks. The paper's only
  random-favourable task (4-2 "find a non-living thing", Random-Valid 0.63 vs DRRN 0.56) is
  outside the audited slice.
- The paper reports normalized scores, not success rates. `published_model_success` is
  therefore DRRN's score (an upper bound on its success rate), and
  `random_fraction_of_published` compares a success rate with a score. It is 0 either way.
- The audit uses ScienceWorld 1.3.0. Its README warns that this release can change gold paths
  and ambiguous-action resolution relative to 1.2.x; the paper's exact simulator version was
  not re-run. The gold trajectories exceed the 100-step budget on 17 Matter tasks, and those
  count as reference failures under the paper's budget.
- Simplifications were set to none; the paper does not report enabling any for Table 2 (an
  inference from the text).
- Selection judgement: WebShop and LLM-First Search were marked not CPU-feasible because the
  control arms cannot run under the paper's own budget (WebShop: free-text search decisions,
  no step limit; LFS: an unreported LLM-token cap). If LFS were admitted, the rule would have
  put it first as the only saturated prediction.

## Manuscript consequence (for #131)

CHOICE_REGISTERED. The audit's blind spot is specific to complete-set submission contracts.
On a widely used published sequential action-choice interface (ScienceWorld's valid-action
list, the paper's own Random-Valid setting), a random-valid control diverges from the
reference at the first decision in 1000/1000 pairs and solves 0/200 tasks against the
reference's 183/200. Success there does measure choice. The manuscript should say this
directly: published interfaces of this kind measure choice, and our zero-headroom finding is
a property of the complete-set submission contract, which we did not find in the published
interfaces surveyed.

## Appendix: `outputs/external-audit/v1/scienceworld/identity-audit.json`

```json
{
 "benchmark": "scienceworld",
 "first_divergence_index": {"max": 0, "median": 0, "min": 0},
 "interface_type": "B",
 "pairs_checked": 1000,
 "pairs_divergent": 1000,
 "pairs_identical": 0,
 "prediction": "divergent",
 "published_model_success": {
  "source": "Wang et al. EMNLP 2022 (arXiv 2203.07540) Table 2, DRRN (best model) normalized score on test variations, averaged over the audited tasks ['1-1', '1-2', '1-3', '1-4', '2-1', '2-2'] weighted by audited variation counts; the paper reports scores, not success rates (success <= score); headline over 30 tasks 0.17",
  "value": 0.08404999999999975
 },
 "random_fraction_of_published": 0.0,
 "saturation": false,
 "schema_version": "external_identity_audit_v1",
 "structural_basis": "ScienceWorld is a sequential action-choice contract: each decision executes one valid action in the simulator, which changes the state, the next valid set and the score, and a wrong 'focus on' ends the episode, so the order of choices determines the outcome and no data structure re-orders them; uniform choice among hundreds of valid actions does not complete the multi-step gold procedure within 100 steps.",
 "success": {
  "random_valid_mean": 0.0,
  "random_valid_per_seed": {"17": 0.0, "5077": 0.0, "6131": 0.0, "7409": 0.0, "8527": 0.0},
  "reference": 0.915
 },
 "supplementary": {
  "mean_clipped_score": {"random_valid": 0.00017999999999999998, "reference": 0.97345},
  "published_headline_drrn_score_30_tasks": 0.17,
  "published_random_valid_score_same_tasks": 0.0
 },
 "tasks": 200,
 "upstream": {"commit": "e8216d6044e8e39be9fcb185e3b2dfb602584b52", "license": "Apache-2.0", "repo": "https://github.com/allenai/ScienceWorld"},
 "verdict": "CHOICE_REGISTERED"
}
```
