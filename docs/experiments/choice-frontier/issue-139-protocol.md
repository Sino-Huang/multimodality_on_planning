# Choice-frontier fresh held-out panels protocol — issue #139

Frozen and committed before any #139 task generation (2026-09-24 UTC). This is a new follow-up to #135/#136/#138. It amends no earlier protocol, script, config or evidence: frozen files (`scripts/*choice_frontier*.py` that already exist, `outputs/choice-frontier/{v1,o4,v2,v3}/`, `configs/experiments/choice-frontier{,-v2,-v3}/`, and the #138-owned `outputs/choice-frontier/v4/seeds/`) are read or copied, never edited. The frozen held-out manifest `data/bfws_phase_v1/fresh-test-manifest.jsonl` and `data/curriculum_pddl/*/dev/` are never read.

Purpose: answer three reviewer concerns about #135/#136 — (a) one 12-task panel, (b) a screen that selects tasks where random choice discriminates, (c) an adapter effect concentrated on ~7 tasks — with two new panels built from fresh seeds that no design decision or adapter has seen:

- **P2 (screened, primary)**: the exact #135 generation, C\* and screening rules. It replicates the instrument-validity ladder and the adapter result out of sample.
- **P2u (unscreened, secondary)**: the same candidate pool with **no random-control screen** (exact must reach the goal, nothing else).

## Algorithms

`best_first_add_greedy` and `best_first_add_w3` (the #132/#133/#135/#136 additive cells).

## Candidates

- The #135 source and mechanism, unchanged: the `expanded` profile of each of the 12 domains in `configs/experiments/expanded-study/panel-protocol-v2.json`, generated through `examples/planning_benchmark_slice/expanded_candidates.generate(root, profile, seed, output)` (the #135 seed-substitution mechanism; see `issue-135-protocol.md`).
- Fresh seeds **955000–955039** (40 per domain, **480 candidates**). Existing seeds span 910000–921115, 935000–935019 (#135) and 945000–945299 (#136); 955000–955039 overlaps none of them.
- Task id `choice-frontier-v4/<domain>-expanded-<seed>`. Task file `outputs/choice-frontier/v4/panels/candidates/<domain>-expanded-<seed>/task.json`, same format as the #135 candidates.
- **All generator runs are serial** (the blocksworld generator shares a cwd `STATES` temp file; concurrent runs corrupt output, the #135 lesson). Only post-generation CPU work (C\*, screening, zoo) is parallel.
- Builder: `scripts/build_choice_frontier_v4_panels.py` (`generate`, `screen`, `freeze`; pattern `scripts/build_choice_frontier_v2_panel.py`). Outputs `configs/experiments/choice-frontier-v4/{candidates,membership-p2,membership-p2u}.json`.

## Exclusions

`problem_sha256` = sha256 of the task's `problem_pddl` (UTF-8). A candidate is dropped and logged (`reject_reason = overlap:<source>:<task_id>` or `duplicate_candidate:<task_id>`) if its `problem_sha256` equals that of:

- (a) any of the 240 #135 candidates (`configs/experiments/choice-frontier-v2/candidates.json`, record `problem_sha256`);
- (b) any #136 training task (`configs/experiments/choice-frontier-v3/training-tasks.json`, **all rows**, record `problem_sha256`, excluded or not);
- (c) any task in `configs/experiments/expanded-study/final-panel.json` (sha of `problem_pddl` in each row's `task_path`);
- (d) any #132 corpus task (`configs/experiments/choice-frontier/membership.json`: sha of `problem_pddl` in `data/best_first_paired_phase_v3/exact-traces/pairs/<task>/task.json` for every task id among its training and diagnostic record ids — the #136 source (c));
- (e) an earlier candidate in this generation (walk order: domain, then seed; the first is kept).

Other reject reasons, unchanged from #135: `generator_failed`, `initial_goal`, `cstar_out_of_range`, `cstar_unsolvable`, `cstar_too_expensive`.

## C\* rule

C\* = the #135 bounded copy of `shortest_plan()` (unit-cost BFS over the task's PDDL, plan replay-verified), limits 2,000,000 expanded states or 10 minutes (`cstar_too_expensive`). **Keep a candidate only if 8 ≤ C\* ≤ 20.**

## R_t

R_t (per task and algorithm) = the expansion count of the **uncapped** `exact_reference` choice-contract episode (seed 17), exactly as #135. Every cap is **2 × R_t** (decision and expansion cap). Membership rows store `reference_costs[algorithm] = {"decisions", "expansions"}` in the #135 shape.

## Screening (both panels share one screening run)

For every kept candidate and algorithm: `exact_reference` seed 17 uncapped; if it reaches the goal, `random_valid` with screening seeds **101, 202, 303, 404, 505** at cap 2 × R_t (the #135 `screen` stage verbatim). Screening episodes are written under `outputs/choice-frontier/v4/panels/screen/`.

## P2 (screened, primary)

- Admit iff (a) exact reaches the goal for both algorithms **and** (b) random-valid reaches the goal in **1–9 of its 10** screening episodes (the #135 screen exactly).
- Freeze rule (#135): sort admitted by (domain, seed); walk and take at most **2 per domain** until **12 tasks**.
- Minimum **8 tasks from 5 domains**, otherwise the blocked exit (no rule change).
- `membership_sha256` = sha256 of `json.dumps(sorted(task_ids), sort_keys=True, separators=(',', ':'))`.

## P2u (unscreened, secondary)

- Pool: kept (C\*-in-range) candidates **not in P2**.
- Admit iff exact reaches the goal for both algorithms. **Random-valid screening results are not consulted** (the selection function reads only the exact-goal fields; tested).
- Sort by (domain, seed); at most **2 per domain**; **12 tasks**. Same `membership_sha256` form. P2 ∩ P2u = ∅ by construction (tested).
- If fewer than 12 are available, the panel is whatever is available (≥ 8 from ≥ 5 domains required, otherwise P2u is dropped and the P2 analyses still run).

Both memberships are committed and pushed **before any evaluation episode**.

## CPU arms (both panels)

The #135 zoo exactly, at cap 2 × R_t, every episode independently replayed (`replay_choice_episode`, fresh PDDL authority):

- `exact_reference` (seed 17); `random_valid` (seeds 17, 5077, 6131, 7409, 8527);
- `exact-eps-0.25/0.50/0.75` (the same 5 seeds each); `hadd-greedy` (5 seeds);
- `bfs-order`, `novelty-first`, `worst-first` (deterministic, seed 17).

Matrix: tasks × 2 algorithms × (1 + 5 + 3×5 + 5 + 3) = tasks × 58 episodes (696 per 12-task panel). Runner: `scripts/run_choice_frontier_v4_zoo.py --panel {p2,p2u}` (copy of `run_choice_frontier_v2_zoo.py`), output `outputs/choice-frontier/v4/panels/<panel>/zoo/`.

## GPU arms (both panels)

- `learned_adapter` for training seeds **17** (`outputs/choice-frontier/v3/training/<algorithm>/seed-17/final`), **29** and **71** (`outputs/choice-frontier/v4/seeds/training/<algorithm>/seed-<seed>/final`, written by #138; read-only), and `pretrained_base` (seed 17, frozen 1-call cap).
- Greedy decoding, inference seed 17, frozen #132 inference settings, cap 2 × R_t (base keeps its frozen 1-call cap as in #135).
- Native views prepared for the frozen panel tasks only, after membership freeze, by the `run_choice_frontier_v2.py prepare-views` recipe (render backend `http://127.0.0.1:18092`).
- Every model episode is independently replayed (`finalize`: 0 missing, 0 mismatch).
- Runner: `scripts/run_choice_frontier_v4_panels.py --panel {p2,p2u}` (copy of `run_choice_frontier_v2.py`), output `outputs/choice-frontier/v4/panels/<panel>/evaluation/`. Jobs `cfv4-panel-<panel>-<algorithm>` (one per panel × algorithm: 3 learned seeds + base, all panel tasks).
- GPU work starts only after #138 is **CLOSED**. If #138 closed blocked or `SMOKE_FAIL`, only the adapters that exist are evaluated and this is stated.

## GPU budget and scheduling

The **shared** v4 ledger created by #138: `outputs/choice-frontier/v4/budget.json`, schedule `docs/experiments/choice-frontier/schedule-v4.json`, cap **24 GPU-h** for both tickets, MASTER_PORT pool 18826–18829, a distinct port per concurrent job, at most one job per GPU, launch only through `scripts/run_expanded_study.py launch`. #139 never creates or re-initialises a ledger.

Estimate (from #136 measured costs, eval ≈ 0.4–0.6 GPU-h per (algorithm, seed) on 12 tasks; base ≈ 0.1 GPU-h per algorithm): per panel 6 learned cells × 0.5 + 2 × 0.1 ≈ 3.2 GPU-h; both panels ≈ **6.4 GPU-h** (×1.25 = 8 GPU-h). If the next job would exceed the cap, it is not launched: **P2 is evaluated fully first**, P2u is secondary; dropped work is recorded.

## Metrics

M1–M5 exactly as in #135 (functions imported from `scripts/analyze_choice_frontier_v2.py`, not copied): M1 = trapezoidal solve-versus-budget AUC over m ∈ {1, 1.25, 1.5, 1.75, 2} by prefix truncation of the 2× episode, equal task weighting, equal algorithm weighting within task, stochastic seeds averaged within cell. Uncertainty: task-cluster bootstrap, `random.Random(133)` (fresh per statistic), 10,000 draws, 95% percentile intervals (the #133/#135 convention).

## Pre-registered tests

1. **Ladder replication on P2** (the #135 rule verbatim). Pairs (exact_reference, eps-0.25), (eps-0.25, eps-0.50), (eps-0.50, eps-0.75), (eps-0.75, random_valid); per-task M1 differences (seeds averaged within cell, then algorithms); paired task-cluster bootstrap per pair. **PASS**: all four lower bounds > 0; **PARTIAL**: all four points > 0, some lower bound ≤ 0; **FAIL**: any point ≤ 0.
2. **Held-out adapter endpoint on P2** (the #138 rule). D3 = mean over seeds {17, 29, 71} of M1(learned, s) − M1(random_valid) (random_valid averaged over its 5 seeds). Per-task values, bootstrap resamples tasks and averages the seeds **inside each draw**. δ = 0.05, equivalence ±0.05, applied in order: **POSITIVE**: lo > 0 and D3 ≥ 0.05 and every seed's point estimate > 0; **EQUIVALENT**: −0.05 < lo and hi < 0.05; **NEGATIVE**: hi < 0; **INCONCLUSIVE**: otherwise.
3. **Separation vs exact-eps-0.75 on P2** (the #138 rule). S = M1(learned, 3-seed mean) − M1(exact-eps-0.75, 5-seed mean), paired task-cluster bootstrap. **SEPARATED_ABOVE** if lo > 0; **SEPARATED_BELOW** if hi < 0; otherwise **NOT_SEPARATED**. Per-seed S points reported.
4. **Unscreened endpoint on P2u**: test 2 with the same rule (verdict reported). Also on P2u, descriptive: the ladder (test 1 rule) and the separation test (test 3 rule).
5. **Pooled (descriptive)**: the D3 and S tests on the 36-task union of the #135 panel, P2 and P2u, clustered by task. #135 panel inputs are reused read-only: controls and ladder from `outputs/choice-frontier/v2/zoo`, seed-17 learned episodes from `outputs/choice-frontier/v3/evaluation`, seeds 29/71 from `outputs/choice-frontier/v4/seeds/evaluation` (#138).

Where fewer than 3 adapter seeds exist (blocked #138), D3/S average over the seeds present and the POSITIVE rule's "every seed" applies to those seeds; this is stated in the closeout.

## Concentration (descriptive, reviewer point c)

- Per task (P2, P2u and #135 panel): the learned (3-seed mean) minus random_valid M1 difference; counts of tasks with difference > 0, = 0, < 0.
- Leave-one-domain-out D3 on P2 ∪ #135 panel: for each domain present, D3 (with the test-2 bootstrap CI) over the tasks not in that domain.

## Output

`scripts/analyze_choice_frontier_v4_panels.py` → `outputs/choice-frontier/v4/panels/metrics/analysis.json` with blocks `ladder_p2`, `heldout_p2` {primary, separation}, `unscreened_p2u` {primary, separation, ladder}, `pooled`, `concentration`, and per-arm tables per panel.

## Freeze order and commits

1. This protocol: before generation.
2. Builder script + `candidates.json` + `membership-p2.json` + `membership-p2u.json`: before any evaluation episode.
3. Zoo/evaluation runners, job files, analyzer, test, closeout: evidence commit.

No number above changes after any result is seen.
