# Choice-frontier instrument validation protocol — issue #135

Frozen and committed before any #135 task generation (2026-09-24 UTC). This is a new, CPU-first follow-up to #132/#133. It does not amend any #132/#133 protocol, script or evidence; frozen files are copied, never edited. It measures the **instrument** (whether M1 ranks choice quality on a graded selector ladder), not whether any model learned to plan. The frozen held-out manifest `data/bfws_phase_v1/fresh-test-manifest.jsonl` and `data/curriculum_pddl/*/dev/` are never read.

## Algorithms

`best_first_add_greedy` and `best_first_add_w3` (the same two additive cells as #132/#133).

## Candidate source

- The 24 generator snapshots in `configs/experiments/expanded-study/tasks/`; only the **`expanded`** snapshot of each of the 12 domains is used. Only the seed changes.
- Fresh seeds **935000, 935001, …, 935019** (20 per domain, 240 candidates). They do not overlap any existing seed (existing seeds span 910000–921115).
- Seed substitution mechanism. Not every snapshot's `generator_command` ends in `-s <seed>`: the seed flag is `-s` (15puzzle, depot, ferry, visitall), `-r` (elevators, logistics), `-e` (storage), `--seed` (grid), positional (blocksworld, driverlog), and absent for the seedless generators gripper and towers_of_hanoi, where the seed drives the frozen legal initial-state walk (15puzzle also walks from its goal). The snapshots were produced by `examples/planning_benchmark_slice/expanded_candidates.generate(root, profile, seed, output)` from the frozen `expanded` profiles of `configs/experiments/expanded-study/panel-protocol-v2.json` (identical generator arguments, walk length and walk origin). #135 calls that same function with each fresh seed, which places the seed at each generator's own seed position (and seeds the walk where the profile declares one). Pre-freeze check: calling it with each snapshot's own seed reproduced all 12 snapshots' `domain_pddl`, `problem_pddl` and `initial_walk` byte-for-byte. Nothing else about the profile changes.
- Task id format: `choice-frontier-v2/<domain>-expanded-<seed>`. Task file `outputs/choice-frontier/v2/candidates/<domain>-expanded-<seed>/task.json`, same format as `outputs/expanded-study/v1/panel-v2/candidates/<task_id>/task.json` (inline `domain_pddl`, `problem_pddl`, `authority_transformations`, `generator_command`, `initial_walk`).

## C\* rule

C\* = `shortest_plan()` from `scripts/analyze_choice_frontier_o4.py` (offline unit-cost breadth-first search over the task's PDDL, plan replay-verified). **Keep a candidate only if 8 ≤ C\* ≤ 20.** If the search needs more than 2,000,000 expanded states or 10 minutes, reject with reason `cstar_too_expensive`. Other reject reasons: `generator_failed`, `initial_goal`, `cstar_out_of_range`, `cstar_unsolvable`. The bounded search is a copy of `shortest_plan()` with only the two limits added; the same algorithm yields the reported cost.

## Reference cost R

R_t (per task and algorithm) is the **expansion count of the `exact_reference` choice-contract episode** (seed 17, uncapped), exactly the #133 `R_t` ("additive exact expansions"); the #133 metric definitions and prefix truncation are reused unchanged. The exact episode's decision count is R_t + 1 (the goal-selection decision is not an expansion); it is recorded alongside R_t. Every cap below is `2 × R_t`, simultaneously the decision and expansion cap, as in #133.

## Screening rule (controls only, no model)

For each kept candidate and each algorithm: run `exact_reference` (seed 17) once with no cap, and `random_valid` with **screening seeds 101, 202, 303, 404, 505** at cap `2 × R_t`. A candidate is **admitted** iff

- (a) exact reaches the goal for both algorithms, and
- (b) random-valid reaches the goal in **at least 1 and at most 9** of its 10 screening episodes (5 seeds × 2 algorithms).

Screening seeds are deliberately disjoint from the evaluation seeds so screening does not bias evaluation.

## Panel freeze rule

Sort admitted candidates by (domain name, seed). Walk that list and take candidates in order, **at most 2 per domain**, until **12 tasks**. The panel must have **at least 8 tasks from at least 5 domains**; otherwise STOP and report per-domain counts without changing the C\* range, seeds or screening rule. `membership_sha256` = sha256 of `json.dumps(sorted(task_ids), sort_keys=True, separators=(',', ':'))` (the #132 canonical form). Membership is committed and pushed before any evaluation episode.

## Arms at evaluation (all CPU)

- `exact_reference` (seed 17)
- `random_valid` (seeds 17, 5077, 6131, 7409, 8527)
- `exact-eps-0.25`, `exact-eps-0.50`, `exact-eps-0.75` (seeds 17, 5077, 6131, 7409, 8527 each)
- `hadd-greedy` (seeds 17, 5077, 6131, 7409, 8527)
- `bfs-order`, `novelty-first`, `worst-first` (deterministic, seed 17 only, definitions unchanged from #133)

Matrix: tasks × 2 algorithms × (1 + 5 + 3×5 + 5 + 3) = tasks × 58 episodes (696 for 12 tasks), all at cap 2 × R_t.

**`exact-eps-E`.** At every decision, draw `u` from `random.Random(f"{seed}:{task_id}:{algorithm}:{decision_index}")`. If `u < E`, choose uniformly at random among the menu's states (menu order), using the same Random object. Otherwise choose the exact heap head, i.e. the same state `exact_reference` would choose (`controller.frontier_head_state_id()`, minimum (priority, generation serial)).

**`hadd-greedy`.** Choose the menu state with minimum additive heuristic h_add. Break ties uniformly at random with `random.Random(f"{seed}:{task_id}:{algorithm}:{decision_index}")`. This selector reads **privileged** h_add. Source of h_add: each live frontier entry is `(priority, generation_serial, g, h)`, where `h` is the value the controller computed with its own heuristic, `BestFirstController._evaluate(state)` → `AdditiveHeuristic(authority)(state)` (`examples/planning_benchmark_slice/best_first_controller.py`), and stored at admission. The selector reads `entry[3]`; for `best_first_add_greedy` this equals `entry[0]` (priority = h). h is never backed out of the priority by arithmetic.

Every episode is independently replayed with `replay_choice_episode` (fresh PDDL authority), as in #133. The stored session arm is the frozen `exact_reference` session arm with a top-level `selector` identity (the #133 envelope); `random_valid` uses the frozen `random_valid` session arm.

## Metrics

Budget multipliers m ∈ {1, 1.25, 1.5, 1.75, 2}; solve-at-m by prefix truncation of the 2× episode (goal-selection decision ≤ floor(m R_t) and preceding expansions ≤ floor(m R_t)). M1 (primary, trapezoidal solve-versus-budget AUC, equal task weighting, equal algorithm weighting within task, stochastic seeds averaged within cell) and M2–M5 exactly as in `issue-133-protocol.md`; C\* reused from one `shortest_plan()` per task. Uncertainty: task-cluster bootstrap, `random.Random(133)`, 10,000 draws, 95% percentile intervals (the #133 `bootstrap()` percentile convention).

## Pre-registered instrument-validity test

Four adjacent pairs: (exact_reference, exact-eps-0.25), (exact-eps-0.25, exact-eps-0.50), (exact-eps-0.50, exact-eps-0.75), (exact-eps-0.75, random_valid). For each pair, per task: difference of M1 task values (left − right), each arm first averaged over its 5 seeds within each (task, algorithm) cell and then over the two algorithms. Paired task-cluster bootstrap of the mean per-task difference (fresh `random.Random(133)` per pair, 10,000 draws, 95% percentile interval).

- **PASS:** all four lower bounds > 0.
- **PARTIAL:** all four point estimates > 0, at least one lower bound ≤ 0.
- **FAIL:** any point estimate ≤ 0.

`hadd-greedy`, `bfs-order`, `novelty-first` and `worst-first` are descriptive only.

## Adapter re-evaluation (GPU, descriptive only)

The frozen #132 adapters `outputs/choice-frontier/v1/training/visual-choice-frontier/<algorithm>/final/` run as `learned_adapter`, and the base as `pretrained_base`, seed 17, no retraining, on the frozen v2 panel, with the unmodified #132 runtime (`pretrained_base` keeps its frozen 1-call cap; `learned_adapter` cap 2 × R_t) and the frozen #132 smoke gate (PASS). Visual observations require per-task native views; they are prepared for the frozen panel tasks only, after membership freeze, by the existing `scripts/prepare_expanded_views.py` recipe (native exact references for the four expanded-study algorithms, planimation scenes at `http://127.0.0.1:18092`, goal pages, unlabelled scene-only pages). Every model episode is independently replayed. Report M1 and teacher agreement minus chance. This row does **not** enter the validity test.

## GPU budget

New ledger `outputs/choice-frontier/v2/budget.json`, schedule `docs/experiments/choice-frontier/schedule-v2.json`, cap **4 GPU-hours**, never added to any other ledger. MASTER_PORT pool **18818–18821**; every concurrent GPU job gets a distinct port. Launch only through `scripts/run_expanded_study.py launch`. A job the scheduler refuses for cap reasons is reported, never re-capped.
