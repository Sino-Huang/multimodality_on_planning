# Choice-frontier fresh held-out panels — issue #139 closeout

Executed under `docs/experiments/choice-frontier/issue-139-protocol.md`:

- The protocol (`f9befb7`) was committed before generation.
- Amendment A1 (`d567939`) extended the seeds to 955000–955199 before any extension seed was generated.
- Both memberships (`2a790b1`) were committed before any evaluation episode.
- The runner, job files and analyzer (`abdf9a0`) were committed before the first GPU launch.
- GPU work started only after #138 was CLOSED (`b47cbaf`), on the shared v4 ledger.

No frozen file under `outputs/choice-frontier/{v1,o4,v2,v3}`, `configs/experiments/choice-frontier{,-v2,-v3}` or `outputs/choice-frontier/v4/seeds` was modified. The held-out manifest and `data/curriculum_pddl/*/dev/` were never read.

## Verdicts

| test | panel | result |
|---|---|---|
| 1. Ladder replication (confirmatory) | P2, 11 tasks / 8 domains | **PASS**: all four adjacent-pair lower bounds > 0 |
| 2. Held-out adapter endpoint (confirmatory) | P2 | **POSITIVE**. D3 = **+0.416 [+0.250, +0.591]**. Per seed: s17 +0.490, s29 +0.268, s71 +0.490 (each > 0) |
| 3. Separation vs exact-eps-0.75 (confirmatory) | P2 | **SEPARATED_ABOVE**. S = **+0.227 [+0.053, +0.403]**. Per seed: s17 +0.301, s29 +0.080, s71 +0.301 |
| 4. Unscreened endpoint (confirmatory) | P2u, 12 tasks / 7 domains | **POSITIVE**. D3 = **+0.149 [+0.030, +0.283]**. Per seed: s17 +0.196, s29 +0.118, s71 +0.133 |
| 4b. Separation vs eps-0.75 (descriptive) | P2u | NOT_SEPARATED. S = +0.002 [−0.145, +0.157] |
| 4c. Ladder (descriptive) | P2u | PASS |
| 5. Pooled D3 (descriptive) | #135 ∪ P2 ∪ P2u, **35 tasks** | D3 = **+0.279 [+0.191, +0.375]**. Per seed: s17 +0.334, s29 +0.203, s71 +0.301 |
| 5. Pooled S vs eps-0.75 (descriptive) | 35 tasks | NOT_SEPARATED. S = **+0.058 [−0.040, +0.156]** |

All intervals are task-cluster bootstrap, `random.Random(133)`, 10,000 draws, 95% percentile. The three adapter seeds are averaged inside each draw.

The union has 35 tasks, not the 36 named in the ticket, because P2 froze with 11 tasks: only 11 admitted tasks were available under the ≤ 2-per-domain walk. P2 still met the 8-task / 5-domain minimum, so the A1 fallback was **not** needed and all P2 tests are confirmatory.

Descriptive, P2 vs exact-eps-0.50: S = −0.075 [−0.247, +0.089], NOT_SEPARATED.

### Reading

- **Instrument:** the ladder replicates out of sample. It passes on P2 and also on the unscreened P2u.
- **Held-out replication (reviewer point a):** on a fresh screened panel the adapter effect replicates (POSITIVE). It is larger than on #135: M1 0.432 vs 0.306, 3-seed mean. There it is also separated above the eps-0.75 rung. On #135 (#138) it was not separated from that rung.
- **Screening artefact (reviewer point b):** without the random-control screen the effect shrinks but stays positive (D3 +0.149, lower bound > 0). On P2u the learned M1 (0.151) sits at the eps-0.75 rung (0.149). The screen therefore inflates the effect size, but it does not create the effect.
- **Pooled:** over 35 tasks the adapter beats random_valid by +0.28 M1. It is not separated from eps-0.75 (S +0.058, CI spans 0). The adapter's choice quality is roughly that of an exact policy that randomises 75% of its choices.

## Panels

| panel | tasks / domains | membership_sha256 | confirmatory |
|---|---|---|---|
| P2 (screened) | 11 / 8 (15puzzle, blocksworld, depot, elevators, ferry, grid, towers_of_hanoi, visitall) | `5c009e856a191ff279195985bec7ddf3bf0041b7ec9ea7dc89fc248e18e114e5` | yes (≥ 8 / 5) |
| P2u (unscreened) | 12 / 7 (15puzzle, blocksworld, depot, driverlog, elevators, ferry, grid) | `495e752e3fa27815d4a7149d69f0786970ce7f59b90f5df388562943fab2f464` | yes (primary endpoint) |

Candidate pool (`configs/experiments/choice-frontier-v4/candidates.json`), 2,400 candidates from seeds 955000–955199:

| stage | count |
|---|---:|
| dropped: overlap with an exclusion source (#135 candidates, #136 training tasks, expanded-study final panel, #132 corpus) | 1,168 |
| dropped: duplicate of an earlier v4 candidate | 205 |
| dropped: initial state already satisfies the goal | 31 |
| dropped: C\* out of range | 536 |
| **kept** | **460** |

All 460 kept candidates reach the goal with exact for both algorithms. The P2 screen (random goals in 1–9 of 10) admits far fewer; the ≤ 2-per-domain walk yields 11. P2u draws 12 from the kept candidates not in P2 without consulting random screening. All 12 happen to have 0/10 random goals.

History: the original 40-seed pool (955000–955039) gave P2 = 6 / 5 and took the blocked exit (`36327e2`). Amendment A1 (orchestrator, on the author's behalf, issuecomment-5805164898) extended the seeds under identical rules. The 480 original candidate records are unchanged in the extended pool (checked field by field).

## Concentration (reviewer point c; descriptive)

Per task, learned (3-seed mean) − random_valid M1:

| panel | > 0 | = 0 | < 0 |
|---|---:|---:|---:|
| #135 | 9 | 2 | 1 |
| P2 | 9 | 2 | 0 |
| P2u | 4 | 8 | 0 |
| **all 35** | **22** | **12** | **1** |

P2 positives by domain: visitall +1.00, ferry +0.73/+0.31, elevators +0.67, grid +0.60/+0.33, blocksworld +0.375 (one of two), depot +0.375, towers_of_hanoi +0.18.

On P2u the eight zero tasks are both 15puzzle, both blocksworld, both depot and both driverlog tasks. On those neither the adapter nor random solves within 2 R_t. The P2u effect comes from elevators, ferry ×2 and grid.

Leave-one-domain-out D3 on P2 ∪ #135 (23 tasks): every domain left out keeps D3 between **+0.305 and +0.395**, and every lower bound is ≥ +0.185:

| domain left out | tasks left | D3 [95% CI] |
|---|---:|---|
| 15puzzle | 21 | +0.384 [+0.269, +0.501] |
| blocksworld | 19 | +0.395 [+0.269, +0.520] |
| depot | 20 | +0.353 [+0.224, +0.484] |
| elevators | 20 | +0.305 [+0.185, +0.430] |
| ferry | 21 | +0.331 [+0.212, +0.455] |
| grid | 20 | +0.331 [+0.204, +0.464] |
| storage | 21 | +0.332 [+0.209, +0.459] |
| towers_of_hanoi | 20 | +0.384 [+0.262, +0.507] |
| visitall | 22 | +0.318 [+0.211, +0.422] |

The effect is spread across domains, not carried by one. Across panels it is carried by the tasks where random choice ever works; see the P2u zero tasks.

## Per-arm M1 (3-seed mean for learned; task-cluster CI)

| arm | #135 | P2 | P2u |
|---|---|---|---|
| exact_reference | 0.875 | 0.875 | 0.875 |
| exact-eps-0.25 | 0.793 | 0.746 | 0.678 |
| exact-eps-0.50 | 0.603 | 0.507 | 0.397 |
| exact-eps-0.75 | 0.347 | 0.205 [0.145, 0.269] | 0.149 [0.091, 0.227] |
| random_valid | 0.021 | 0.016 [0.000, 0.048] | 0.002 [0.000, 0.006] |
| hadd-greedy (privileged) | 0.882 | 0.928 | 0.906 |
| learned s17 / s29 / s71 | 0.349 / 0.250 / 0.318 | 0.506 / 0.284 / 0.506 | 0.198 / 0.120 / 0.135 |
| learned 3-seed mean | 0.306 [0.158, 0.455] | 0.432 [0.273, 0.602] | 0.151 [0.030, 0.288] |
| pretrained_base (1-call cap) | 0.000 | 0.000 | 0.000 |

On P2 the s17 and s71 M1 values are equal (0.506), but their episodes differ: 43 of 46 learned (task, algorithm) pairs on P2 ∪ P2u have different output sequences, and the checkpoints are verified in every episode.

The analyzer's recomputation for the #135 panel reproduces #136 (D = 0.328125) and #138 (D3 = 0.285 [0.140, 0.433], S = −0.041) exactly.

## Execution record

- **Build:** `scripts/build_choice_frontier_v4_panels.py` `generate` (serial generation, exclusion, bounded C\*), then `screen`, then `freeze`.
- **CPU zoo:** `scripts/run_choice_frontier_v4_zoo.py --panel {p2,p2u}` imports the frozen #135 selectors and runner. The `--limit 4` smoke ran first.
  - P2: 638/638 episodes (11 × 58).
  - P2u: 696/696 episodes (12 × 58).
  - 0 missing, 0 error, every episode replayed.
- The P2 ladder verdict was posted on the issue before GPU work.
- **Views:** `scripts/run_choice_frontier_v4_panels.py prepare-views` returned `REFERENCE_VIEWS_PASS` for 11/11 and 12/12 tasks (render backend 18092). Native exact expansions equal the choice-contract R_t for every task.
- **GPU:** four jobs `cfv4-panel-<panel>-<algorithm>`, one per GPU at a time, through `scripts/run_expanded_study.py launch` on the shared ledger.
  - P2 ran first on GPU 0 / GPU 1 (ports 18826 / 18827).
  - Each P2u job launched on the GPU its P2 job had freed. P2u w3 on GPU 1 (port 18827) overlapped P2 greedy on GPU 0 (port 18826), so concurrent ports were always distinct.
  - Bindings per job: learned_adapter × seeds 17/29/71 + pretrained_base × panel tasks (44 for P2, 48 for P2u).
  - All four completion hooks: `ok: true`. The hook reads the attempt dir from the terminal path, per the #136 fix.
- **Finalize:** P2 88/88 and P2u 96/96 independently replayed, 0 missing, 0 mismatch.
- **Adapters:** seed 17 from `outputs/choice-frontier/v3/training/<alg>/seed-17/final`, seeds 29/71 from `outputs/choice-frontier/v4/seeds/training/<alg>/seed-<s>/final`. The #136 (seed 17) and #138 (seed 29) smoke gates are both PASS.
- **Analysis:** `scripts/analyze_choice_frontier_v4_panels.py` imports M1–M5, the bootstrap and the ladder test from `analyze_choice_frontier_v2.py`, and the verdict rule from `analyze_choice_frontier_v3.py`.
- **Tests:** `tests/planning_benchmark/test_choice_frontier_v4_panels.py` covers:
  - the exclusion rule, and that every source's hashes are covered;
  - that P2u never reads random-screen fields;
  - P2 ∩ P2u = ∅;
  - that P2u requires the exact goal for both algorithms.

  7 passed. `ruff check` on the four new scripts and the test: clean.

## Budget

| job | GPU | MASTER_PORT | status | GPU-h |
|---|---|---|---|---:|
| cfv4-panel-p2-best_first_add_greedy | 0 | 18826 | succeeded | 1.5781 |
| cfv4-panel-p2-best_first_add_w3 | 1 | 18827 | succeeded | 0.9872 |
| cfv4-panel-p2u-best_first_add_w3 | 1 | 18827 | succeeded | 1.2799 |
| cfv4-panel-p2u-best_first_add_greedy | 0 | 18826 | succeeded | 1.2708 |
| **#139 total** | | | | **5.1160** |

Shared v4 ledger total: **15.22 / 24 GPU-h** (#138 10.11 + #139 5.12). Nothing was dropped for budget. There were no failed attempts and no relaunches for #139. Pre-launch estimate: 6.4 GPU-h (8 with ×1.25).

## Evidence index (sha256, first 16)

| file | sha256 |
|---|---|
| `configs/experiments/choice-frontier-v4/candidates.json` | `934da7a99dd3dd2b` |
| `configs/experiments/choice-frontier-v4/membership-p2.json` | `631a74b69565e53a` |
| `configs/experiments/choice-frontier-v4/membership-p2u.json` | `18494f6ce1892e41` |
| `outputs/choice-frontier/v4/panels/p2/zoo/manifest.json` | `28469c3879cd786d` |
| `outputs/choice-frontier/v4/panels/p2u/zoo/manifest.json` | `5cd81f8c16543554` |
| `outputs/choice-frontier/v4/panels/p2/reference-views.json` | `905a8322fee09e4e` |
| `outputs/choice-frontier/v4/panels/p2u/reference-views.json` | `b544a032122f7d07` |
| `outputs/choice-frontier/v4/panels/p2/evaluation/bindings.json` | `76f8628dcc371e1a` |
| `outputs/choice-frontier/v4/panels/p2u/evaluation/bindings.json` | `af7eb347a546f434` |
| `outputs/choice-frontier/v4/panels/p2/evaluation/evaluation.json` | `f4f58cc2d73116f7` |
| `outputs/choice-frontier/v4/panels/p2u/evaluation/evaluation.json` | `9344ac0b675c9d74` |
| `outputs/choice-frontier/v4/panels/metrics/ladder-cpu.json` | `ba7c86a97848ee65` |
| `outputs/choice-frontier/v4/panels/metrics/analysis.json` | `6b4a8b57c8c1b6ea` |

Keys for #131 in `analysis.json`: `ladder_p2`, `heldout_p2.{primary,separation}`, `unscreened_p2u.{primary,separation,ladder}`, `pooled`, `concentration`, `arms`.

## Limitations

- **Panel sizes.** P2 has 11 tasks, not 12, and the pooled union has 35 tasks, not 36. The fresh generator space is heavily depleted by earlier corpora: 1,168 of 2,400 candidates are exact duplicates of #135/#136/#132/expanded-study problems. The seed range was extended once (A1); the rules were never changed.
- **The screen still shapes P2.** P2 tasks were admitted because random sometimes solves them. P2u answers this concern. Its effect is smaller (D3 +0.149) and rests on 4 of 12 tasks. The other 8 are unsolved by both arms within 2 R_t.
- **Separation holds on P2 only.** It is not significant on P2u, on #135 (#138) or pooled. The pooled estimate puts the adapter near the eps-0.75 rung.
- **Seed 29 is weaker.** On P2 its separation point is +0.080, and it has the lowest D3 on every panel. Seed variance is material.
- **Base arm.** pretrained_base keeps its frozen 1-call cap, so its M1 of 0 is a runtime artefact, not a planning measurement.
- **Privileged rungs.** exact-eps and hadd-greedy read privileged information: the heap head and h_add. M2/M3 condition on solving.
- **Uncommitted run outputs.** Run outputs under `outputs/` are git-ignored (as in #135/#136). Only the configs and docs are committed.
