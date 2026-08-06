# Production P0 - Todo 4 selector infeasibility - 2026-08-06

## Summary

Todo 4 cannot ever emit `selector_feasible` against the current approved constants. The
4-object object-count quota is unsatisfiable because the 4-object candidate universe is
finite, already fully materialized, and too small to supply the required number of
paired-exact rows.

Todo 4 remains unchecked. Todo 3 round 2 was deliberately **not** run. No remediation is
proposed here; the binding constant is an owner decision.

## The proof

| Fact | Value | Source |
| --- | --- | --- |
| 4-object retained nontrivial universe | `210` | `tmp/cgas-p0-candidates/reports/combinatorics.json` (`four_object.retained_nontrivial_ids`) |
| 4-object stream state | `exhausted: true`, frontier `600` of capacity `600` | `tmp/cgas-p0-candidates/reports/exhaustion.json` |
| 4-object emitted + characterized in round 1 | `88` | checkpoint 1 accounting, `status=emitted`, `object_count=4` |
| 4-object paired-exact achieved | `14` (`15.9%`) | checkpoint 1 reservoir |
| 4-object never yet characterized | `122` | `210 - 88` |
| **Absolute ceiling if every remaining candidate were paired-exact** | **`136`** | `14 + 122` |
| **Selector hard requirement** | **`190`** | `scripts/phase3/cgas_partition_contracts.py:11` |

`136 < 190`. The gap cannot close, because:

- The 4-object stream is already `exhausted: true` at its full capacity of 600 raw ranks, so
  no additional 4-object candidates can ever be enumerated.
- `retained_nontrivial_ids: 210` is the complete set of distinct nontrivial 4-object candidate
  identities in the entire universe (`228` canonical orbits minus `18` subset-solved).
- Characterization is once per candidate ID and the planner/paired-exact policy is frozen, so
  an already-characterized non-paired-exact candidate cannot later become paired-exact.

Enforcement points:

- `scripts/phase3/cgas_partition_contracts.py:11` - `EXPECTED_OBJECT_COUNTS = {4: 190, 8: 198, 12: 93}`
- `scripts/phase3/cgas_production_population_manifest.py:43-44` - `object_counts != Counter({4:190, 8:198, 12:93})` raises `production_object_quota_invalid`
- `scripts/phase3/cgas_production_population_manifest.py:45-49` - required matrix includes `("train", 4): 190`
- `scripts/phase3/cgas_production_population_manifest.py:24-25` - every selected row must pass `_paired_exact`, so all 190 must come from the paired-exact reservoir

Observed round-1 paired-exact yields per stream: 4-object `14/88 = 15.9%`, 8-object
`23/129 = 17.8%`, 12-object `16/64 = 25.0%`. Extrapolating the 4-object rate across the whole
`210`-candidate universe gives roughly `33` paired-exact rows against a requirement of `190`
- short by a factor of about six, not a marginal miss.

Only the 4-object stream is blocked. At their observed yields, 8-object would reach `198` in
roughly 8 further rounds and 12-object would reach `93` in roughly 5.

## Why Todo 3 round 2 was not run

Round 2 is safe to run and all six resume preconditions were verified clean, but it cannot
change the outcome above, and it is expensive:

- **Cost: roughly 15-25 hours.** A resume performs two full passes over the 2.25 TB of
  persisted BFS streams. The first is inside the characterization loop
  (`scripts/phase3/cgas_candidate_characterization_planners.py:56-63`: when a trace already
  exists the runner still calls `verify_trace_stream` **and** re-executes the full planner
  search with `max_trace_steps: 0`). The second is inside checkpoint construction
  (`scripts/phase3/cgas_candidate_characterization_checkpoint.py:122-128`, which calls
  `validate_trace_binding` -> `verify_trace_stream` for every characterization row).
  The measured throughput is about 85 MB/s, CPU-bound on JSON parsing, taken from the
  round-2 runtime diagnosis (fd offset advanced `14,134,804,480` -> `16,638,803,968` over
  30 s at 99.5% CPU). The interrupted attempt ran 15h19m and was still inside the second pass.
- **The loop has no reachable terminal state.** `finite_candidate_exhaustion` requires all
  three streams exhausted. The 8-object capacity is `19,514,880` ranks and the 12-object
  capacity is `2,840,000,486,400` ranks, consumed at `198` and `93` per round.
- **Validation cost is quadratic in rounds.** Every round re-verifies every accumulated
  characterization row's streams, so total I/O grows as O(rounds^2).
- **Disk exhausts at round 3.** Traces already occupy 2.25 TB and the project directory
  quota reports about 1.4 TB free of 11 TB (87% used). Another full round of 12-object
  traces does not fit. Note `df` must be run against the project path;
  `df /data/scratch` reports the whole 692 TB filesystem, which is not the binding
  constraint for writes made here.

## State at the time of this note

Unchanged and re-verified:

- Round-1 checkpoint `fa70f298d77834421f328fb56821e60e4cbd9d5324963251b2d88ba2e5134853`
- `current.json` `1b23b2c76fb1b77b85a0549b89fc5b4e3c503668e03c46db6443650b64fcacdf` (still binds round 1)
- Selector attempt 1 `4a594ae9a43214aeac772f10badae2d1559db60c19e77ac10a4a9f2be01c4c60`
  (`selector_infeasible` / `calibration_exact_39_unavailable`)
- Trace-v1 release digest must remain `3bc894314f4fa674ff36489c664d8cc9db7f23e2144c5ffcef1444fd30feb6c3`
- `tmp/cgas-p0-characterized/checkpoints/reservoir_checkpoint_000002.json` is absent
- 558 trace directories, 558 complete `bfs.trace-v2.jsonl`, 558 complete `iw.trace-v2.jsonl`
- No `.*trace-v2.jsonl-*`, `*.tmp`, or `*.partial` files
- No characterization writer process and no tmux server

Note that selector attempt 1's recorded reason is `calibration_exact_39_unavailable`. That is
the first constraint the selector happens to fail, not the binding one; the manifest builder
checks the 481-row count and the 39-row calibration count
(`cgas_production_population_manifest.py:12-15`) before it reaches the object-count quota at
line 43. The 4-object ceiling documented above is the constraint that cannot be satisfied by
any further rounds.

## Resume command (still valid if the owner authorizes it)

```bash
cd /data/scratch/projects/punim0478/sukaih/multimodality_on_planning
tmux new-session -d -s cgas-production-round2-resume \
  "cd /data/scratch/projects/punim0478/sukaih/multimodality_on_planning && source ~/cd_vlaplan && python -m scripts.phase3.cgas_candidate_characterization next-round --round 2 --checkpoint tmp/cgas-p0-characterized/checkpoints/reservoir_checkpoint_000001.json --feedback tmp/cgas-production-population/selector_attempt_000001.json --approved-trace-contract .claude/evidence/cgas-production-p0/approved-trace-v2.json --candidate-config configs/cgas/production_p0_candidates.json --candidate-root tmp/cgas-p0-candidates --output tmp/cgas-p0-characterized --json > .claude/evidence/production-p0-corpus-experiment-readiness/task-3/round-2/round-2-resume.log 2>&1; code=\$?; printf '%s\n' \"\$code\" > .claude/evidence/production-p0-corpus-experiment-readiness/task-3/round-2/exit-code-resume.txt; exit \"\$code\""
```

Use a new log name so the interrupted `round-2.log`
(`a527a61bd39b5fde434f42727dfe61b8105d14d76b23ca07fdd7c9b64bc724c1`) is preserved. Do not
launch a second copy while it is active. Do not delete or regenerate the 558 stream pairs.

## Evidence

`.claude/evidence/production-p0-corpus-experiment-readiness/task-4/selector-infeasibility-proof/`

- `preconditions.txt` - verbatim output of the six resume-precondition checks
- `derivation.txt` - verbatim read-only derivation, reproducible
- `proof.json` - canonical machine-readable proof bound to the round-1 checkpoint and selector digests
- `README.md` - narrative with file/line citations

## Owner decision required

The `{4: 190}` element of `EXPECTED_OBJECT_COUNTS` is unsatisfiable. The plan explicitly
forbids the worker from altering selector constants, quotas, or paired-exact semantics
(`.claude/plans/production-p0-corpus-experiment-readiness.md`, "Must NOT have"), so this is
escalated without a proposed remediation. See `[[production-p0-server-restart-handoff-2026-08-06]]`
for the preceding stop, and `[[production-p0-todo4-selector-2026-08-05]]` for the selector
implementation state.
