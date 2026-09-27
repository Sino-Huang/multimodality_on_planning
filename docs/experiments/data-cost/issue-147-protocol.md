# Matched data-cost curves for executing BFS and BFWS — issue #147 protocol

Frozen and committed before any #147 training or model episode. Machine-readable twin:
`configs/experiments/data-cost/protocol.json`. Budget basis and author decisions:
`issue-147-feasibility.md`. Nothing below changes after any model outcome is seen; any change is a dated,
numbered amendment committed before the affected launch.

## Question

How many reference operations does a Qwen3-VL-8B LoRA adapter need before it executes BFS and BFWS on unseen
tasks, and does that cost differ between the algorithms and between text, visual and multimodal observations
rendered without labels?

## Scope (author decision 2026-09-26)

- Cells: {`bfs`, `best_first_width`} x {`text-state`, `visual-state`, `multimodal-state`} x sizes
  {512, 1,024, 2,048, 4,096, 8,192, 16,384} x training seeds {17, 29, 71} = **108 cells**.
- One compute-matched control; controls `exact_reference`, `random_valid` (5 seeds), `pretrained_base`.
- Dropped by the author before any protocol: the 32,768 rung, the model-size axis (Qwen3-VL-2B/4B/32B) and the
  InternVL3.5-8B cell. N90 is right-censored at 16,384 where 90 % is not reached.
- Cap **800 GPU-h** (ledger `outputs/data-cost/v1/budget.json`, schedule `schedule.json`); workers stop
  claiming new units at 760 GPU-h charged.

## Observations

`scene-only-128-unlabelled-v1` (`examples/planning_benchmark_slice/scene_only_views.py`): initial and current
state are 128 px scenes with no object labels; static context and partial-goal constraints are pages; candidate
information and search memory are shared across modalities. `text-state` is the unchanged text serialization;
`multimodal-state` receives both.

Render repairs landed before this protocol (commit `c2e0a14`; all 280 re-rendered v5 scenes in 81 tasks are
pixel-identical to the v5 store):

- identity-tinted opaque prefabs (Sokoban and Snake tiles) are drawn as their pictures instead of white boxes
  (`scripts/planimation_phase1_frames.py`);
- Sokoban generator names such as `pos571_61` shrank the board into one corner pixel; `compact_grid_vfg`
  re-anchors the name-derived grid at cell (1, 1) and reproduces the backend's own coordinates for boards that
  already start there. It is applied to every Sokoban task and no other domain.

## Decision-sufficiency check (before any training)

Run on 2026-09-26 before any training (`scripts/data_cost_prepare.py sufficiency`;
`outputs/data-cost/v1/preparation/sufficiency.json`). Definition: within each task, the rendered 128 px
unlabelled scenes are grouped by exact RGB content; a collision is two distinct dynamic PDDL states (atoms and
fluents) with identical pixels. Collision rate = states in a colliding group / rendered states. Coverage:
all 17,178 training-set states plus the reference states of all 30 panel tasks.

| verdict | domains (collision rate) |
|---|---|
| PASS | blocksworld, grid, gripper, snake, sokoban, towers_of_hanoi, visitall (0) |
| FAIL | 15puzzle (1.000), depot (0.759), storage (0.498), driverlog (0.384), ferry (0.355), freecell (0.289), logistics (0.239), elevators (0.047) |

The FAIL cases are identical-looking interchangeable objects once labels are removed (e.g. two depot trucks
swapping places; every 15-puzzle tile is the same colour). Hand-checked examples show identical PNG bytes and
differing atoms.

**Author decision (2026-09-26, after the check, before any training):** all 15 domains stay in the primary
analysis; the 7-domain PASS subset is a pre-registered secondary analysis of the visual and multimodal curves.

Caveat carried from the #112-#119 contract, unchanged: BFS observations name states by canonical atom lists
(`state_id`, frontier head, successor targets) in the shared search memory for every modality, so BFS state
identity is available as text even in `visual-state`; BFWS uses `$` and atom deltas.

## Evaluation panel

`configs/experiments/data-cost/panel.json` (membership_sha256
`b7f41bab3c5276af0c759adc225611549bfa3a966af616fd8915a1458341cfce`; protocol `panel-protocol.json`; evidence
`panel-summary.json`; views `outputs/data-cost/v1/panel/reference-views.json`). **30 tasks = 15 domains x
{compact, expanded}**, split `test`, no stratum missing. Selection was outcome-blind (no model run): the first
candidate in ascending seed order per stratum whose exact `bfs` and `best_first_width` references both solve
within 256 decisions and 128 expansions, and that is not equivalent under object renaming to any of the 238 #74
corpus tasks, any of the 384 expanded-study candidates or an earlier panel task. The 12 expanded-study domains
reuse their v2 profiles with new seeds; FreeCell, Snake and Sokoban profiles were added. Seven strata exhausted
their seeds and were revised before selection, in a fixed remedy order (more seeds, then the smallest structural
step, then a shorter walk; `profile_revisions` in `panel-protocol.json`): gripper-expanded (seeds 0-63),
15puzzle-expanded (walk 8 -> 7), depot/ferry/logistics/storage/towers_of_hanoi-compact (one size step).

Reference decisions (sum over 30 tasks): BFS 2,613, BFWS 1,282 (per-task range 8-229 and 8-178). Largest
complete input: 10,132 tokens (Sokoban expanded, multimodal). Sokoban manifests carry
`render_overrides: {"grid_anchor": true}`, so live renders of off-reference states get the same repair.

## Training sets

`configs/experiments/data-cost/training-sets.json`; membership (key-first, SceneOnlyViews-compatible)
`configs/experiments/data-cost/membership.json` (sha256 `1c7b6f0a...a9e7`); views
`outputs/data-cost/v1/preparation/scene-views.json` (sha256 `10d29cbc...e393`; 32,768 records, 139 tasks,
17,178 scenes).

Pool: the #74 corpus, `bfs` 89 tasks / 24,026 operations and `best_first_width` 85 tasks / 20,660 operations,
train and dev split tasks both admitted (none is in the panel). Order: domains shuffled by
`Random("data-cost-v1:domains:{alg}")`, tasks within a domain shuffled by
`Random("data-cost-v1:tasks:{alg}:{domain}")`, round-robin over domains, each task's operations in decision
order. Set N = the first N operations, so every set contains the smaller ones; the last task of a set may be a
decision prefix. No operation exceeded the 32,768-token bound in any observation (0 skipped).

| N | BFS tasks (partial) / domains | BFWS tasks (partial) / domains |
|---|---|---|
| 512 | 2 (1) / 2 | 6 (1) / 6 |
| 1,024 | 3 (1) / 3 | 7 (1) / 7 |
| 2,048 | 6 (1) / 6 | 14 (1) / 14 |
| 4,096 | 13 (1) / 13 | 22 (1) / 15 |
| 8,192 | 37 (1) / 15 | 39 (1) / 15 |
| 16,384 | 68 (1) / 15 | 71 (1) / 15 |

Small sets cover few domains because whole tasks are long (one BFS ferry task has 599 operations). Domain
coverage therefore grows with N by design; the curves measure the cost of task-level data, as the ticket asks.

## Training recipe

The matched-v5 recipe (`configs/experiments/matched-modalities/study-v5.json` `training` block), unchanged:
Qwen/Qwen3-VL-8B-Instruct rev `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`, LoRA r 64 / alpha 128 / dropout 0.05
on all linear layers except `.*visual.*`, lr 1e-4, global batch 32 (microbatch 1 x accumulation 32), bf16
compute, sdpa attention, **1 epoch** at every size (updates = N / 32: 16 ... 512).

- Sample order: the set's records shuffled by `random.Random("data-cost-v1:order:{algorithm}:{size}:{seed}")`.
  The training seed also reaches `set_seed` and `TrainingArguments.seed` (LoRA init, dropout).
- Checkpoint every 16 updates, only the latest kept, so a reboot loses at most 16 updates; final adapter saved
  in **bf16** (declared deviation from the fp32 adapters of #112-#141; loaded without upcasting).
- Audit per cell: adapter present, bf16, r/alpha/dropout, updates, seed, record-id sha of the set.

**Compute-matched control.** `bfs`, `text-state`, seed 17, the 2,048 set for **8 epochs** = 16,384 samples =
512 updates, the update count of the 16,384 cell. Epoch e uses
`random.Random("data-cost-v1:order:bfs:2048:17:epoch{e}")`. It separates data size from the number of updates.

## Evaluation

- Greedy decoding, evaluation seed 17, study-v5 inference settings (max 384 new tokens, 32,768-token context).
- Cap: 2 x the task's exact-reference decisions (`VisualSession`); an invalid operation is charged and ends the
  episode (deterministic under greedy decoding). The runtime never repairs an operation.
- Conditions on every panel task: 108 learned cells + the control; `pretrained_base` for each algorithm x
  observation (6); `exact_reference` (seed 17) and `random_valid` (seeds 17, 5077, 6131, 7409, 8527) per
  algorithm. The two control policies read no observation; they run once per algorithm on `text-state` and are
  declared observation-independent.
- Every episode is replayed independently (`replay_visual_episode`) at finalize; missing or mismatching
  episodes are listed, never imputed.

## Metrics

Per episode: **success** = `invariant_valid_success` (goal reached within the cap with every algorithm
invariant holding); **valid-operation rate** = accepted model operations / model calls; **first-invalid step**
= 1-based decision index of the first rejected operation (censored when none).

Per algorithm x observation x size: S(N) = mean over panel tasks of the mean over the 3 seeds.

**N50 / N90.** The first upward crossing of q by S(N), linearly interpolated in log2 N between adjacent rungs;
reported as `<=512` if S(512) >= q and `>16,384` (right-censored) if never reached. CI: task-cluster bootstrap,
`random.Random(147)`, 10,000 draws, tasks resampled with replacement and the 3 seeds averaged inside each draw,
95 % percentile interval; censored draws are kept as ordinal extremes.

## Pre-registered contrasts (every size)

- BFS - BFWS, per observation (3).
- text - visual, text - multimodal, visual - multimodal, per algorithm (6).

Each is a paired task-cluster bootstrap of the difference in S (same settings), with a two-sided bootstrap p
(2 x min tail share). Holm adjustment over the 54 tests; **SEPARATED** iff the Holm-adjusted p < 0.05, else
**NOT_SEPARATED**. N50/N90 differences (log2 ratio) are reported with bootstrap CIs, descriptively.

Compute-matched control: S(2,048 x 8 epochs) - S(2,048 x 1) and S(16,384 x 1) - S(2,048 x 8 epochs), BFS text,
seed 17 cells, paired task bootstrap (descriptive).

Secondary (descriptive): the visual and multimodal curves recomputed without domains whose
decision-sufficiency verdict is FAIL. The primary analysis keeps every panel domain.

Node-choice comparison (reused, 0 GPU-h): the #136/#138 search-control adapters learned from 2,048 choices x 2
menu orders (4,096 samples, 128 updates; D3 = +0.285 [+0.140, +0.433], `outputs/choice-frontier/v4/seeds/metrics/analysis.json`)
are reported beside N50/N90 in samples and updates.

## Execution and resumability

Code: `scripts/run_data_cost.py` (`examples/planning_benchmark_slice/data_cost_runner.py`), analyzer
`scripts/analyze_data_cost.py` (`data_cost_analysis.py`), preparation `scripts/data_cost_prepare.py`, panel
`scripts/data_cost_panel.py`; tests `tests/planning_benchmark/test_data_cost_{runner,corpus,panel}.py`.

- **Units and frozen order** (`run_data_cost.py units`): the 6 `pretrained_base` evaluations; then the seed-17
  cells by ascending size (within a size: bfs then best_first_width, each text / visual / multimodal); the
  compute-matched control; then seed 29; then seed 71. A train unit is followed by its evaluation on the same
  worker. Two workers (GPU 0, GPU 1) claim units from a file-locked queue (`outputs/data-cost/v1/queue/`).
- **Scheduler.** Workers run as `scripts/run_expanded_study.py` jobs under `schedule.json` and the ledger
  `outputs/data-cost/v1/budget.json` (cap 800 GPU-h, MASTER_PORT pool 18860-18863, one job per GPU, a distinct
  port per job). A worker claims no new unit once charged GPU-h exceed 760. An attempt lasts at most 7 days;
  at that limit the worker stops cleanly and its completion hook relaunches the same GPU.
- **Resume after a reboot (one command):** `source ~/cd_vlaplan && python scripts/run_data_cost.py resume`
  starts any down Planimation port (18092-18095), reconciles dead ledger attempts (charged conservatively up to
  the reconcile time), and relaunches each idle GPU. Nothing is assumed to survive: a queue claim is live only if
  host, boot id, pid and start time all match. Training resumes from the latest complete checkpoint (every 16
  updates); evaluation resumes from per-episode journals that persist each generated output before the runtime
  sees it. Completed units are never repeated.
- **Failures.** An infrastructure failure of a unit is retried once (a unit that fails twice is blocked and
  reported as missing); the recipe and settings never change.
- **Smoke gate.** The first claimed units are the smoke: the 6 base evaluations and the first seed-17 cells must
  complete, every episode must replay, and the first training cell must pass its audit (bf16 adapter, r/alpha,
  updates, seed, order). A forced interruption of one training cell mid-way must resume from its checkpoint
  and reach the same step count. On an infrastructure failure the runner is fixed (not the recipe) before the
  queue continues.
- **Controls** (`run_data_cost.py controls`, CPU): exact_reference and random_valid on all panel tasks.
- **Finalize** (`run_data_cost.py finalize`, CPU): independent replay of every expected episode (3,810 on the
  30-task panel); verdict `COMPLETE_REPLAYED` or `INCOMPLETE_EXPLICIT_MISSINGNESS` with the missing list.

Budget on this panel (feasibility-note rates: 1.14-2.48 s per trained operation, 5.49 s per model call):
training ~302 GPU-h (control ~6), evaluation ~321 GPU-h if every episode succeeds (panel reference decisions
2,613 BFS / 1,282 BFWS per cell pass; ~642 at the 2x cap), base ~1: **~630 GPU-h expected**. If the 760 GPU-h
stop is reached, the unrun units are the latest in the frozen order (seed 71 first) and are reported as missing.

## Outputs

`outputs/data-cost/v1/metrics/analysis.json`, `data-cost-curves.{pdf,png}`, the ledger
`outputs/data-cost/v1/budget.json`, and the closeout `issue-147-closeout.md`.
