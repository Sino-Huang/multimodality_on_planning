# Todo 4 — selector infeasibility proof (fail-closed)

**Verdict: Todo 4 cannot ever emit `selector_feasible` under the current approved constants.**
Todo 4 remains unchecked. Todo 3 round 2 was deliberately **not** run.

Generated 2026-08-06 against round-1 checkpoint
`fa70f298d77834421f328fb56821e60e4cbd9d5324963251b2d88ba2e5134853`.

## Files

| File | Purpose |
| --- | --- |
| `proof.json` | Canonical machine-readable proof, bound to the round-1 checkpoint and selector digests. SHA-256 `b739f14869303002d0006dbb0be5b4042835002d289c23ee61ee87ac19323e51` (4630 bytes) |
| `derivation.txt` | Verbatim output of the read-only derivation |
| `derive_infeasibility.py` | The derivation itself — re-runnable, recomputes every number from immutable artifacts and live selector constants |
| `preconditions.txt` | Verbatim output of the six resume-precondition checks |
| `capture-preconditions.sh` | The precondition capture — re-runnable |

Both scripts are read-only. Neither creates a checkpoint, trace, cursor, selector result, tmux
session, or process. They live under `.claude/evidence/` rather than `scripts/phase3/` on purpose:
they are evidence generators, not production modules, so no RED/GREEN TDD obligation is
triggered and Todo 4's implementation scope does not expand.

## Reproduce

```bash
cd /data/scratch/projects/punim0478/sukaih/multimodality_on_planning
E=.claude/evidence/production-p0-corpus-experiment-readiness/task-4/selector-infeasibility-proof
bash "$E/capture-preconditions.sh"
source ~/cd_vlaplan && python "$E/derive_infeasibility.py"
```

## The proof

The selector hard-requires exactly **190 paired-exact 4-object rows**:

- `scripts/phase3/cgas_partition_contracts.py:11` — `EXPECTED_OBJECT_COUNTS = {4: 190, 8: 198, 12: 93}`
- `scripts/phase3/cgas_production_population_manifest.py:43-44` — mismatch raises `production_object_quota_invalid`
- `scripts/phase3/cgas_production_population_manifest.py:45-49` — required matrix includes `("train", 4): 190`
- `scripts/phase3/cgas_production_population_manifest.py:24-25` — every selected row must pass `_paired_exact`, so all 190 must come from the paired-exact reservoir

The 4-object candidate universe is closed and already exhausted:

- `tmp/cgas-p0-candidates/reports/combinatorics.json` — `four_object.retained_nontrivial_ids = 210`
  (228 canonical orbits − 18 subset-solved)
- `tmp/cgas-p0-candidates/reports/exhaustion.json` — 4-object stream `exhausted: true`,
  frontier 600 of capacity 600

Round 1 characterized 88 of those 210 and produced 14 paired-exact:

| n | consumed | emitted | duplicate | solved | paired-exact | yield | required |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 | 190 | 88 | 52 | 50 | **14** | **15.9%** | **190** |
| 8 | 198 | 129 | 0 | 69 | 23 | 17.8% | 198 |
| 12 | 93 | 64 | 0 | 29 | 16 | 25.0% | 93 |

```
4-object universe (closed)                      = 210
4-object already characterized                  =  88
4-object paired-exact achieved                  =  14
4-object never characterized                    = 210 - 88 = 122
ABSOLUTE CEILING (if ALL remaining were exact)  =  14 + 122 = 136
SELECTOR HARD REQUIREMENT                       = 190

136 < 190  ->  feasible = False
```

Expected rather than best-case: `210 × 15.9% ≈ 33` against a requirement of 190 — short by
about **5.7×**, not a marginal miss.

The gap cannot close because (1) the 4-object stream is exhausted at its full 600-rank
capacity so no further 4-object candidates can be enumerated, (2) 210 is the complete set of
distinct nontrivial 4-object identities, and (3) characterization is once per candidate ID
under a frozen paired-exact policy, so an already-characterized non-exact candidate cannot
later become exact.

Cross-checks asserted by the derivation: per-stream accounting sums to the checkpoint's
`{duplicate: 52, emitted: 281, solved: 148}`; emitted candidate IDs are unique; there is
exactly one characterization row per emitted ID; per-stream paired-exact sums to the
checkpoint `reservoir.row_count` of 53.

## Note on selector attempt 1's reason code

Selector attempt 1 records `calibration_exact_39_unavailable`. That is simply the first
constraint the manifest builder reaches — it checks the 481-row count and the 39-row
calibration count at `cgas_production_population_manifest.py:12-15` before reaching the
object-count quota at line 43. The 4-object ceiling documented here is the constraint that
cannot be satisfied by any number of further rounds.

## Why round 2 was not run

Round 2 is safe to run — all six preconditions are clean (`preconditions.txt`) — but it cannot
change the outcome, and it is expensive:

- **~15–25 hours.** A resume makes two full passes over the 2.25 TB of persisted BFS streams:
  one inside the characterization loop
  (`cgas_candidate_characterization_planners.py:56-63` — when a trace already exists the runner
  still calls `verify_trace_stream` *and* re-executes the full planner search with
  `max_trace_steps: 0`), one inside checkpoint construction
  (`cgas_candidate_characterization_checkpoint.py:122-128`). Measured throughput is ~85 MB/s,
  CPU-bound on JSON parsing, per the round-2 runtime diagnosis. The interrupted attempt ran
  15h19m and was still in the second pass.
- **No reachable terminal state.** `finite_candidate_exhaustion` requires all three streams
  exhausted; 8-object capacity is 19,514,880 ranks and 12-object is 2,840,000,486,400, consumed
  at 198 and 93 per round.
- **Quadratic validation.** Every round re-verifies every accumulated characterization row's
  streams, so total I/O grows as O(rounds²).
- **Disk exhausts at round 3.** Traces occupy 2.25 TB; the project quota reports ~1.4 TB free
  of 11 TB (87% used). `df` must be run against the project path — `df /data/scratch` reports
  the whole 692 TB filesystem and is not the binding constraint.

Only 4-object is blocked. At observed yields, 8-object would reach quota in ~8 further rounds
and 12-object in ~5.

## State preserved

Re-verified unchanged after this report was written:

- checkpoint 1 `fa70f298d77834421f328fb56821e60e4cbd9d5324963251b2d88ba2e5134853`
- `current.json` `1b23b2c76fb1b77b85a0549b89fc5b4e3c503668e03c46db6443650b64fcacdf` (still round 1)
- selector attempt 1 `4a594ae9a43214aeac772f10badae2d1559db60c19e77ac10a4a9f2be01c4c60`
- trace-v1 release `3bc894314f4fa674ff36489c664d8cc9db7f23e2144c5ffcef1444fd30feb6c3`
- `reservoir_checkpoint_000002.json` absent; 558/558/558 trace artifacts intact; no temp files

## Owner decision required

The `{4: 190}` element of `EXPECTED_OBJECT_COUNTS` is unsatisfiable. The plan forbids the
worker from altering selector constants, quotas, or paired-exact semantics, so this is
escalated with measured facts and **no proposed remediation**.

The former `production-p0-todo4-infeasibility-2026-08-06.md` and
`production-p0-server-restart-handoff-2026-08-06.md` notes are preserved in
`.claude/archive/context-hot-snapshot-2026-08-10.tar.gz` and Git history.
