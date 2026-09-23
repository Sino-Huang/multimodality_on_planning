# #137 Stage 2 protocol (frozen before any audit run)

Benchmark selected by the Stage 1 fixed rule (`issue-137-survey.md`, commit 94b054f):
**ScienceWorld** (Wang, Jansen, Côté, Ammanabrolu, EMNLP 2022,
https://aclanthology.org/2022.emnlp-main.775/, arXiv 2203.07540, fetched 2026-09-24).

Only control arms are run. No LLM/VLM, no model of any kind, no GPU
(`CUDA_VISIBLE_DEVICES=` for every command).

## Upstream

- Repo https://github.com/allenai/ScienceWorld @ `e8216d6044e8e39be9fcb185e3b2dfb602584b52`
  (Apache-2.0), cloned untracked at `outputs/external-audit/v1/upstream/scienceworld`,
  package version 1.3.0, bundled simulator JAR sha256 `e77b0fee7d68abe3…`.
- Imported editable from the clone into the separate venv `outputs/external-audit/v1/venv-sw`
  (py4j 0.10.9.9, system OpenJDK 17). Pins and install commands:
  `outputs/external-audit/v1/upstream-manifest.json`.
- Runner: `scripts/run_external_identity_audit.py --benchmark scienceworld`. It calls the
  upstream `ScienceWorldEnv` API (`load`, `reset`, `step`, `get_variations_test`,
  `get_gold_action_sequence`); no upstream code is copied.

## Tasks

The paper evaluates on the **test variations** of all 30 tasks (Table 2: "Zero-shot
performance of the agents on test variations"). Paper order = Table 2 order (task ids 1-1 …
10-2, which is also the order of the upstream `scienceworld/tasks.json`); within a task,
test variations in ascending index from `get_variations_test()`. That list has 1,819
entries, more than 200, so **the first 200 in this order** are audited:

| Table 2 id | upstream task | test variations | audited |
|---|---|---|---|
| 1-1 | boil | 21-29 | 9 |
| 1-2 | melt | 21-29 | 9 |
| 1-3 | freeze | 21-29 | 9 |
| 1-4 | change-the-state-of-matter-of | 21-29 | 9 |
| 2-1 | use-thermometer | 405-539 | 135 |
| 2-2 | measure-melting-point-known-substance | first 29 of 109 (327-355) | 29 |

Consequence stated up front: the 200 cover 6 of the 30 tasks (Matter and Measurement).
Simplifications: none (`simplificationStr=""`); the paper does not report enabling any for
Table 2.

## Budget

The paper's own: "a maximum number of steps (we used 100 in all experiments)" (Sec. 4,
App. C). Implemented as upstream `ScienceWorldEnv(envStepLimit=100)`: the episode ends
when upstream `step` returns `isCompleted` (task completed, task failed / negative score,
or moves > 100). A hard cap of 1,000 submitted actions guards against actions that consume
no moves; hitting it is logged, not hidden.

## Arms

- `reference`: the paper's oracle, the hand-coded gold trajectory
  (`load(task, variation, "", generateGoldPath=True)`, `get_gold_action_sequence()`),
  executed action by action. Run once per task.
- `random_valid`: at every decision, uniform choice among the valid action-object
  combinations the simulator returns for the current state (`infos["valid"]` of the last
  `reset`/`step`, i.e. `get_valid_action_object_combinations()`), sorted before sampling.
  This is the paper's own Random-Valid baseline ("randomly chooses an action a from the set
  of valid actions A_t obtained from the simulator"). Seeds **17, 5077, 6131, 7409, 8527**;
  the per-episode RNG is `random.Random(int(sha256(f"{seed}|{task}")[:16], 16))`.

## What a decision is

One action string submitted to `env.step` after `reset` (the upstream `reset` performs its
own `look around`, which is not a decision). The decision sequence of an episode is the list
of submitted strings.

## Logging and determinism

Each episode is written to
`outputs/external-audit/v1/scienceworld/episodes/<task>/<arm>-<seed|ref>.json` with the full
decision sequence, the number of valid actions offered at each decision, per-step score,
final score, `goal_reached` (final score = 100) and the step count. After the full run,
10 random_valid episodes (sampled with `random.Random(137)`) are re-run in a fresh
simulator and must be byte-identical to the stored logs. Smoke: `--limit 3` (first 3
tasks) into `outputs/external-audit/v1/scienceworld-smoke/` before the full run.

## Metrics (written to `outputs/external-audit/v1/scienceworld/identity-audit.json`)

Schema `external_identity_audit_v1` exactly as in the #137 ticket:

- pair = (task, random_valid seed) vs the reference on the same task;
  `pairs_checked = tasks x 5`; a pair is **identical** iff the two decision sequences are
  equal and `goal_reached` is equal; otherwise divergent.
- `first_divergence_index`: first index where the two sequences differ (the shorter length if
  one is a prefix of the other); median (lower median), min, max over divergent pairs.
- `success.reference`, `success.random_valid_per_seed`, `success.random_valid_mean`
  (goal_reached rate over the 200 tasks).
- `saturation = random_valid_mean >= 0.9 x success.reference`.
- `published_model_success`: the paper reports normalized **scores**, not success rates.
  Value = DRRN (best model) Table 2 score averaged over the audited tasks, weighted by the
  audited variation counts (9x0.03 + 9x0.04 + 9x0.01 + 9x0.03 + 135x0.10 + 29x0.08)/200 =
  **0.084** (headline over all 30 tasks: 0.17). A success rate is at most the score, so
  this is an upper bound on DRRN's success rate on these tasks.
- `random_fraction_of_published = random_valid_mean / 0.084`.
- Also reported (not verdict inputs): mean clipped score `max(score, 0)/100` per arm, to
  compare with the paper's Random-Valid column (0.00 on all six audited tasks).
- **Verdict rule:** `IDENTICAL` if pairs_identical == pairs_checked; otherwise `SATURATED`
  if saturation; otherwise `CHOICE_REGISTERED`.

## Prediction (copied from the survey)

ScienceWorld, interface type **B**, prediction **divergent**: sequential single-action
execution with a large valid set (~400 at the first step of boil) and wrong-`focus on`
actions that end the episode; the paper's Random-Valid is 0.03 on average and 0.00 on all six
audited tasks, while the gold trajectories complete them. Expected: pairs_identical = 0,
random_valid_mean far below 0.9 x reference, verdict **CHOICE_REGISTERED**.
