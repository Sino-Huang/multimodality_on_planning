# CGAS Partition Characterization

Date: 2026-07-29

## Source Contract

- Stage A/B consumes `data/curriculum_pddl/accepted_manifest.jsonl` through `AcceptedInstanceMetadata.from_dict` and filters `domain_id == "blocksworld"`.
- The complete source population is 481 rows: train 402, dev 39, test 40; parsed PDDL object counts are 4:190, 8:198, 12:93.
- Source row identity is SHA-256 of its immutable JSONL record bytes. The output deliberately excludes physical line position and source-file byte digest so reverse input ordering cannot change canonical artifact bytes.

## Characterization Contract

- Each row derives init/goal stack descriptors and a name-invariant composition signature from parsed PDDL atoms, not historical bucket, plan length, or rendering metadata.
- It runs only `cgas_bfs.run_fifo_bfs` and width-1 `local_iw.run_iterated_width`, records their implementation hashes and fixed limits, and replay-validates every returned plan.
- Failures remain as canonical audit rows with a stable failure reason. No partition role is assigned.
- Planner records use one typed `characterization_outcome`, separate nested `exact_search` and `retained_trace` facts, and a `source_eligibility` state. A bounded trace is `ineligible_bounded_trace` and `require_full_trace_source()` rejects it.
- Characterization-only trace retention does not alter `cgas_provenance.py`, which keeps `max_trace_steps=10000`.

## Commands

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_partition_characterization.py tests/phase3/test_cgas_provenance.py
source ~/cd_vlaplan && python -m scripts.phase3.cgas_partition_characterization --source-manifest data/curriculum_pddl/accepted_manifest.jsonl --output-root /tmp/cgas-partition-characterization
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_partition_contracts.py scripts/phase3/cgas_partition_characterization.py tests/phase3/test_cgas_partition_characterization.py
```

## Persistent Run Evidence

- The original 481-row run reached 25,902,892 KiB RSS because it retained full BFS snapshots on every expansion. Characterization now uses a one-snapshot trace budget, while shared provenance retains the 10,000-step default.
- A bounded trace is not certificate evidence. `blocksworld-dev-easy-0001` has exact BFS search metrics (15 expansions) but one retained snapshot, so its characterization outcome is `exact_search_bounded_trace` and its source eligibility is `ineligible_bounded_trace`.

## 2026-07-28 Remediation Run

- Requested `cgas-partition-481-final` was absent from tmux and the process table at takeover, so no process was stopped.
- The fresh local-only CLI run is in `cgas-partition-characterization-20260728T191238Z` and writes to `tmp/cgas-partition-characterization-20260728T191238Z/`.
- It started at `2026-07-28T19:13:24Z`; at 3:23 elapsed it was CPU-active at 99.5% with 70,560 KiB RSS and had not published final typed files.

## 2026-07-29 Planner Performance Remediation

- Characterization is intentionally native-only: `CHARACTERIZATION_LIMITS["local_iw_recovery"]` is `0`, which maps at the `LocalPlannerRequest` boundary to `RecoveryPolicy.DISABLED`. Its width-one IW exhaustion keeps the original status and trace, with no serial BFS, goal regression, or `plan_recovery` event.
- Omitted `local_iw_recovery` defaults to enabled, preserving production/provenance recovery behavior and its existing gates.
- BFS, IW, and serial retain canonical action ordering. BFS only constructs successor/state/action/frontier/visited trace payloads when a retained snapshot remains; IW and serial apply the same guard to event-only payloads. IW and serial sort grounded actions once per run before stable applicability filtering.
- Differential tests pin canonical successful and resource-limited BFS metrics plus byte-identical retained snapshots. Tests also pin no characterization recovery, preserved default recovery, and a single grounded-action sort for IW and serial.
- Real accepted campaign under unchanged 10,000 limits: `blocksworld-dev-easy-0001` completed in 0.005 wall/CPU seconds (BFS 15; IW 1 failed native); `blocksworld-dev-medium-0000` in 0.226/0.223 seconds (BFS 10001; IW 1 failed native); and `blocksworld-dev-hard-0000` in 0.348/0.346 seconds (BFS 10001; IW 1 failed native). All native IW traces had no recovery.
- Required cleanup receipt: stopped PID `215811` and tmux `cgas-partition-characterization-20260728T191238Z`; the failed-run root `tmp/cgas-partition-characterization-20260728T191238Z/` is retained.

## 2026-07-29 IW Trace Accounting Correction

- `local_iw` now makes search accounting independent of retained events: every trace contains total `expansion_count` and `trace_complete`, based on a total generated trace-event counter. A retained budget of zero cannot be represented as a full trace.
- Native IW success returns `success_full_trace` only if every event is retained, otherwise `success_truncated_trace`. Characterization already recognizes both statuses as replay-valid exact search, then derives `exact_search_complete_trace` versus `exact_search_bounded_trace` and source eligibility from `trace_complete`.
- The reviewer two-step repro confirms both budgets find `[(advance-0), (advance-1)]` and report total expansions 2. Full retention is complete/full; zero retention is bounded/truncated. Neither path enters recovery.
- Updated accepted campaign totals under unchanged limits: easy 15 total/1 retained in 0.006s, medium 44/1 in 0.223s, hard 73/1 in 0.340s. All remain native failed IW with zero recovery.

## 2026-07-29 Pipeline Truncated-Success Consumer Correction

- Native local trace success is now centralized in `schema.is_successful_trace_status()`: only `success_full_trace` and `success_truncated_trace` qualify. External `success_plan_replayed` is accepted at the example-schema layer but is not a native local trace success.
- `pipeline._attempt_planner()` accepts a local result only when this predicate passes and its plan is non-empty. `_successful_attempt()` requires both replay validity and goal satisfaction. It preserves `success_truncated_trace` rather than remapping it.
- Schema accepts the truncated fidelity status. The trace retains explicit `trace_complete=false`; provenance, certificate, readiness, verifier, and planimation full-trace gates remain intentionally unchanged and fail closed for truncated traces.
- Pipeline regression proved a valid local IW plan with no retained events is replayed/emitted as `success_truncated_trace`; resource-limit, failed-search, and external replay-only statuses are not admitted through the local predicate.

## 2026-07-29 Shared Empty-Plan Success Boundary

- `_successful_attempt()` is the sole successful-plan admission boundary for GBFS, both goal-regression recovery routes, external planners, and local planners. It rejects `[]` as `failed_no_plan_extracted` before replay validation, producing neither a replay row nor a supervised example.
- This prevents initially solved tasks from becoming successful training rows solely because replay considers an empty action sequence valid. Non-empty replay-valid full and truncated native traces retain their existing successful behavior.
- The local planner branch now checks only native successful trace status and delegates plan non-emptiness to the shared boundary. Rejected resource, failed-search, external replay-only, and replay-invalid paths retain their existing rejection behavior.
