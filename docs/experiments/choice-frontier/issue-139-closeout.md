# Choice-frontier fresh held-out panels — issue #139 closeout

## Blocked

**The P2 freeze rule's minimum was not met, so the ticket's blocked exit (rule 8) is taken.** Under the frozen #135 screen and freeze rule, P2 has **6 tasks from 5 domains**, but the protocol requires at least **8 tasks from 5 domains**, "otherwise blocked exit" (ticket step 1 and `issue-139-protocol.md`). No rule, seed range, C\* range or screen was changed after seeing the result.

Consequences:

- No membership was frozen. `membership-p2.json` and `membership-p2u.json` were not written. The P2u pool is "kept candidates **not in P2**", so it cannot be frozen while P2 is not.
- **No evaluation episode was run** (no zoo, no views, no GPU). #139 used **0 GPU-h** on the shared v4 ledger and launched no job.
- Verdicts: ladder replication (P2), held-out adapter (P2), unscreened (P2u), pooled and concentration are **not computed**.

### Why P2 came up short

Generation (seeds 955000–955039, 12 `expanded` profiles, serial, 480 candidates) → `configs/experiments/choice-frontier-v4/candidates.json` (sha256 `a640662bf9933032…`):

| outcome | count |
|---|---:|
| overlap with an exclusion source (sha256 of `problem_pddl`) | 240 |
| — (b) #136 training tasks | 138 |
| — (a) #135 candidates | 101 |
| — (d) #132 corpus | 1 |
| duplicate of an earlier v4 candidate | 13 |
| initial_goal | 11 |
| cstar_out_of_range | 114 |
| **kept (8 ≤ C\* ≤ 20)** | **102** |

Exclusion hash counts per source (first source wins on shared hashes): a 204, b 1268, c 9, d 28.

The low-diversity generators repeat problems across seeds, and the 2,400-task #136 training corpus already covers most of their space. storage (40/40 overlap) and depot (37/40 overlap, 3 out of range) have **0 kept**. towers_of_hanoi (38/40), gripper (33/40) and 15puzzle (29/40) are mostly overlaps.

Screening (the #135 screen verbatim): all 102 kept candidates reach the goal with exact for both algorithms. Only **8** pass the random-valid 1–9-of-10 condition (random solves 0/10 on the other 94, the same pattern as #135: 34 admitted out of 127 kept there).

Per domain (candidates / kept / exact goal / admitted):

| domain | cand. | kept | exact goal | admitted |
|---|---:|---:|---:|---:|
| 15puzzle | 40 | 9 | 9 | 0 |
| blocksworld | 40 | 34 | 34 | 1 |
| depot | 40 | 0 | 0 | 0 |
| driverlog | 40 | 34 | 34 | 0 |
| elevators | 40 | 1 | 1 | 1 |
| ferry | 40 | 2 | 2 | 1 |
| grid | 40 | 10 | 10 | 4 |
| gripper | 40 | 5 | 5 | 0 |
| logistics | 40 | 1 | 1 | 0 |
| storage | 40 | 0 | 0 | 0 |
| towers_of_hanoi | 40 | 2 | 2 | 1 |
| visitall | 40 | 4 | 4 | 0 |

Admitted: blocksworld-955022, elevators-955007, ferry-955007, grid-955007, grid-955021, grid-955028, grid-955032, towers_of_hanoi-955031. The ≤ 2-per-domain walk drops two grid tasks, which leaves **6 tasks / 5 domains**.

Descriptive only (not frozen): with those 6 as P2, the P2u rule would yield 12 tasks from 7 domains (15puzzle, blocksworld, driverlog, ferry, grid, gripper, logistics).

### What the author must decide (not done here)

Any of these changes the frozen protocol, so each needs a new protocol commit before any evaluation:

1. **More fresh seeds under the same rules** (for example 955040–955239). At the observed rate of 8 admitted per 480 candidates, concentrated in grid, the ≤ 2-per-domain cap binds. About 2 more admitted tasks from new domains are needed. That likely takes several hundred more candidates per domain, and it may still fail for the generator families that are already exhausted.
2. **Relax the per-domain cap to 3** for P2. This gives 7 tasks, still below 8, so on its own it is not enough.
3. **Lower the P2 minimum to 6 tasks / 5 domains.** This makes the out-of-sample replication weaker than the #135 panel.
4. **Run P2u alone** as the held-out panel (12 tasks / 7 domains available) with P2 defined as empty or as the 6 admitted tasks. This answers reviewer point (b) but not the screened replication (a).

## Panels

Not frozen (see above). Candidate pool frozen in `configs/experiments/choice-frontier-v4/candidates.json`.

## Execution record

- Protocol committed before generation: `f9befb7`.
- `scripts/build_choice_frontier_v4_panels.py generate`: serial generation, then exclusion and bounded C\* (6 workers). Log: `outputs/choice-frontier/v4/panels/generate.log`.
- `screen`: 7 workers, 102 candidates × 2 algorithms. Episodes: `outputs/choice-frontier/v4/panels/screen/`. Log: `screen.log`.
- `freeze`: `STOP: P2 has 6 tasks from 5 domains (need >= 8 from >= 5)`.
- `scripts/run_choice_frontier_v4_zoo.py` (a `--panel` copy of the #135 zoo that imports the frozen selectors) is committed but was **not run**, because no membership exists.
- Tests: `tests/planning_benchmark/test_choice_frontier_v4_panels.py` covers the exclusion rule, that P2u never reads random-screen fields, P2 ∩ P2u = ∅, and the P2u exact-goal requirement. Result: 7 passed. `ruff check` on the new scripts and test: clean.

## Budget

#139: 0 GPU-h (no launch). The shared v4 ledger is owned by #138 and was not touched.

## Evidence index (sha256, first 16)

- `configs/experiments/choice-frontier-v4/candidates.json`: `a640662bf9933032`
- `docs/experiments/choice-frontier/issue-139-protocol.md`: committed in `f9befb7`

## Limitations

- The freeze stop comes from the ticket's pre-registered minimum. It is not an infrastructure failure. Whether to extend seeds or change the rule is a protocol decision for the author.
- The screening episodes are uncommitted run outputs under `outputs/` (git-ignored, as for #135).
