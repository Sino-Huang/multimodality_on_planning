# CGAS Phase 3 pilot-scope evidence

This packet makes the Phase 3 sizing decision reproducible without starting Phase 3. The canonical
machine-readable result is `report.json`; `report.txt` is the human-readable rendering of the same
result. The analysis is read-only and reuses the Gate 0b verifier before reading checkpoint rows.

## Bound inputs

- v3 checkpoint: `0fa9d3e5bcad06e6e50381a2142d4b6777818feffb0e1a4012c010a1fdebf76b`
- v3 current index: `e86d42a7ec94c29169cadb4eb65baa93e5b4502eda65bc9bbb333b5c9a2bce97`
- approved trace: `bf00880f94692160d42103aab689ea2501607b48df53114b282bdc404b34dbe7`
- owner approval: `2f98142c8b303a07060f7942bab603e21fceed510a7faa01a52d9b6611560557`
- contract: `be1a3eb9f42d387e57a7e714ce95154f2657833114a68d41e5b88342ef1234d1`
- policy: `51acff53d15652663d2212902d3d94261e44de9e3edf66b9970fc3c75197d436`
- candidate config: `4d4830321a4a7cbc6e17bec9ecb5e1f121cbdea2f66445212fd129df38325e5b`
- selector config: `3783c7fdda618849a7de0dcb3074258bbde309af384afb4ec0cb8173a6eb2a05`
- selector implementation: `a83be53cb0e5096662be73881c95a899de9783633b5d56c61bcb408cf593f2e7`
- immutable release: `3bc894314f4fa674ff36489c664d8cc9db7f23e2144c5ffcef1444fd30feb6c3`

## Command

```bash
cd /data/scratch/projects/punim0478/sukaih/multimodality_on_planning
source ~/cd_vlaplan
python .claude/evidence/cgas-trace-contract-v3/owner-decision-packet/derive_pilot_scope.py
```

The command verifies all 562 checkpoint-bound v3 streams before reporting. It writes only this
evidence directory and does not create a checkpoint, advance a cursor, or run a selector.

## Measured pool

The checkpoint has 281 characterized candidates and 158 paired-exact candidates. The paired pool
contains 67/59/32 candidates and 14/26/9 composition signatures at 4/8/12 objects. At each object
count, respectively, 11/17/7 signatures have at least two candidates; there are 5/17/9 initial
stack profiles and 3/6/7 distinct goal-edge levels.

Plan length has mean 5.215, median 6, maximum 10, and histogram
`{2:29, 4:45, 6:51, 8:25, 10:8}`. The paired pool provides 1,650 replay-plan certificate rows
(10.443/instance), 60,620 expansion-local certificate opportunities (383.671/instance), and 58,970
off-plan-only opportunities (373.228/instance). Expansion yield is the exact sum of BFS and IW
expansion counts, not the predecessor analyzer's `2 * BFS` approximation.

## Proposed floor

The candidate instance-diversity floor is measurable and independent of the stability bar:

- at least 30 paired-exact candidates at each of 4, 8, and 12 objects (90 total);
- at least five composition signatures per object count represented by at least two candidates;
- at least three initial stack profiles and three goal-edge levels per object count.

The 158-candidate pool passes every clause. The tightest margin is 12 objects: 32 candidates against
30 and seven repeated signatures against five.

## Feasibility and recommendation

Per-object sizing uses seven invariant families, the exact measured per-object yield, the 79/481
held-out fraction, and the existing 40%/60% failure-rate alternatives. After applying the diversity
floor:

| bar | harvest | 40% failure | 60% failure | existing pool |
| --- | --- | ---: | ---: | --- |
| >=10/cell | on-plan | 325 | 217 | infeasible |
| >=10/cell | off-plan | 90 | 90 | feasible |
| >=30/cell | on-plan | 971 | 648 | infeasible |
| >=30/cell | off-plan | 111 | 94 | feasible |

Recommendation: propose `>=10 observations/cell`, the 90-instance floor above, and off-plan
certificate harvesting. This preserves a genuine pilot and reuses the signed 158-candidate pool.
This is evidence, not approval: the owner must rule on the stability bar, diversity floor, and
harvest policy before Phase 3 starts.

If those three choices are approved, the companion provenance recommendation becomes actionable:
use reproducibility rather than release-grade publication for the unreleased pilot, subject to its
four recorded correctness conditions. No pilot selection, rendering, training, or publication was
performed here.

## Gates

- focused analyzer + Gate 0b verifier tests: `8 passed in 0.59s`;
- Ruff on changed Python files: pass;
- basedpyright on changed Python files: `0 errors, 0 warnings, 0 notes`;
- contract surface: 62 occurrences, 62 classified, 0 unclassified, 0 stale;
- manual QA on the real signed checkpoint: exit 0, all 562 streams verified, `read_only=true`;
- broad CGAS: `464 passed, 9 failed in 141.57s`.

The nine broad failures are pre-existing and exactly match Gate 0b: three planner probe tests fail
on `authoritative_hash_mismatch`; three Qwen preflight and three release-gate tests fail because the
environment has `huggingface-hub==1.22.0` while installed `transformers` requires `<1.0`. Exact test
names and commands are recorded in `gates.json`.
