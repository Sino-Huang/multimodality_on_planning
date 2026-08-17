# Phase 3 CGAS Partition Characterization

## Scope

Stage A/B builds a local, canonical characterization of the 481 accepted Blocksworld source rows. It does not assign partitions, publish to a production root, invoke rendering, or use historical planner and render metadata as metrics.

## Contract

- Input rows are parsed with `AcceptedInstanceMetadata.from_dict` from `data/curriculum_pddl/accepted_manifest.jsonl`.
- The population assertion is 481 total, split 402 train/39 dev/40 test, and PDDL object counts 4:190/8:198/12:93.
- Records retain source-record, domain, and problem identities; PDDL-derived init/goal stack descriptors; and a name-invariant composition signature.
- Metrics use canonical FIFO BFS and exact width-1 local IW. Planner records carry limits and implementation metadata while exposing a typed characterization outcome, exact-search metrics, retained-trace metadata, and source eligibility as separate facts.
- Failure records remain in the artifact with a stable reason. `partition` is always null.

## Verification

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_partition_characterization.py tests/phase3/test_cgas_provenance.py
source ~/cd_vlaplan && python -m scripts.phase3.cgas_partition_characterization --source-manifest data/curriculum_pddl/accepted_manifest.jsonl --output-root /tmp/cgas-partition-characterization
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_bfs.py scripts/phase3/cgas_partition_contracts.py tests/phase3/test_cgas_partition_characterization.py
```

The focused tests pass. The full real-corpus invocation is intentionally local-only and requires a longer local execution window for complete dry-run evidence.

## Persistent Execution Status

The initial run in tmux session `cgas-partition-481-7c76844e` was stopped after PID `215875` reached 25,902,892 KiB RSS. The cause was BFS retaining a complete frontier and visited-state snapshot for each of up to 10,000 expansions, which produces quadratic retained trace data. The planner now honors `max_trace_steps`, and the characterization contract limits retained BFS snapshots to 100 while preserving total expansion counts, plan selection, replay validation, and the trace schema for retained entries.

The corrected full run is active in tmux session `cgas-partition-481-tracecap`:

```bash
tmux capture-pane -p -t cgas-partition-481-tracecap -S -50
ps -o pid,etime,%cpu,rss,state,command -p 112932
```

At 1:51 elapsed, PID `112932` remained CPU-active at 95.8% and 70,928 KiB RSS, stable across the 33-second, 1:03, and 1:51 samples. It has not completed or published `characterization.jsonl`; it remains an ongoing validation run.

## Trace Completeness Correction

Characterization intentionally retains only one BFS expansion snapshot to keep the 481-row run bounded. A search can still be canonical and replay-valid when that retained trace is truncated. For `blocksworld-dev-easy-0001`, the artifact records `exact_search_bounded_trace`, exact expansion count 15, and `bounded_snapshot` with a one-snapshot budget. It declares `ineligible_bounded_trace`, and `require_full_trace_source()` raises `bounded_trace_not_source_ready`, preventing a later partition or certificate consumer from treating it as complete transition evidence.

Shared provenance defaults retain their 10,000-step trace budget. The bounded one-snapshot budget applies only to this characterization CLI.

## 2026-07-28 Remediation Run

Verification passed:

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_partition_characterization.py tests/phase3/test_cgas_provenance.py tests/phase3/test_cgas_provenance_adversarial.py tests/phase3/test_cgas_certificates.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_partition_contracts.py scripts/phase3/cgas_partition_characterization.py tests/phase3/test_cgas_partition_characterization.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_partition_contracts.py scripts/phase3/cgas_partition_characterization.py tests/phase3/test_cgas_partition_characterization.py
```

The requested `cgas-partition-481-final` session was absent at takeover, so no process was stopped. A fresh local-only full CLI run is retained in `cgas-partition-characterization-20260728T191238Z`, with output root `tmp/cgas-partition-characterization-20260728T191238Z/`. It started at `2026-07-28T19:13:24Z`; at 3:23 elapsed it was CPU-active at 99.5% with 70,560 KiB RSS and had not yet emitted final typed files.

## 2026-07-29 Planner Performance Remediation

### Root Cause and Scope

Characterization invoked width-one IW with the normal recovery default. On IW novelty exhaustion, `local_iw._recover_at_max_width()` invoked `bounded_serial_plan()` and then goal-regression recovery. This made characterization perform recovery work that is neither native IW nor a valid exact IW source. It also exposed the existing goal-regression attempt-reset defect, which is deliberately outside this remediation.

The characterization limits now set integer `local_iw_recovery=0`. `LocalPlannerRequest.recovery_policy` provides the typed `RecoveryPolicy` boundary: omitted limits preserve `ENABLED` behavior for provenance and other existing callers; characterization maps to `DISABLED`. A disabled request never attempts early goal regression or post-exhaustion serial/goal recovery and returns native IW status plus the retained native trace.

BFS now avoids discarded successor/state-ID/action trace payloads after the retained snapshot budget. IW and serial avoid their equivalent discarded event payloads without changing applicability, novelty, goal checks, plans, counts, or canonical order. IW and serial sort grounded actions once at the start of each invocation and filter that ordered tuple in stable order.

### RED / GREEN

RED command:

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_planner_performance.py
```

Before the production changes, it failed for the requested reasons: characterization called `bounded_serial_plan`, IW sorted the grounded tuple twice, and serial sorted it twice.

GREEN command:

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_planner_performance.py tests/phase3/test_cgas_partition_characterization.py tests/phase3/test_cgas_provenance.py tests/phase3/test_cgas_provenance_adversarial.py tests/phase3/test_cgas_certificates.py tests/phase3/test_phase3_local_trace_safety.py
```

Result: `45 passed in 10.67s`. The focused suite verifies no recovery calls or events in characterization, default recovery outside characterization, canonical one-sort action ordering, and byte-identical retained BFS snapshots for successful and resource-limited searches.

Static checks:

```bash
source ~/cd_vlaplan && basedpyright scripts/phase3/local_planner_types.py scripts/phase3/local_iw.py scripts/phase3/local_serial.py scripts/phase3/cgas_bfs.py scripts/phase3/cgas_partition_characterization.py tests/phase3/test_cgas_planner_performance.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/local_planner_types.py scripts/phase3/local_iw.py scripts/phase3/local_serial.py scripts/phase3/cgas_bfs.py scripts/phase3/cgas_partition_characterization.py tests/phase3/test_cgas_planner_performance.py
```

Basedpyright returned `0 errors, 0 warnings, 0 notes`; compilation returned zero.

### Accepted-Row Manual Campaign

The following command drove the actual accepted rows through `characterize_instances()` under unchanged 10,000 limits and checked the native IW trace for recovery:

```bash
source ~/cd_vlaplan && python - <<'PY'
import json
import time
from pathlib import Path

from scripts.phase3.cgas_partition_characterization import CHARACTERIZATION_LIMITS, characterize_instances, load_accepted_blocksworld
from scripts.phase3.local_iw import run_iterated_width
from scripts.phase3.local_planner_types import LocalPlannerRequest
from scripts.phase3.pddl import ground_actions, parse_task

wanted = ("blocksworld-dev-easy-0001", "blocksworld-dev-medium-0000", "blocksworld-dev-hard-0000")
inputs = {item.instance_id: item for item in load_accepted_blocksworld(Path("data/curriculum_pddl/accepted_manifest.jsonl"))}
results = []
for instance_id in wanted:
    instance = inputs[instance_id]
    wall_start, cpu_start = time.perf_counter(), time.process_time()
    row = characterize_instances((instance,))[0]
    task = parse_task(instance.domain_path, instance.problem_path)
    grounded, grounding_status = ground_actions(task, max_grounded_actions=CHARACTERIZATION_LIMITS["max_grounded_actions"], max_grounded_atoms=CHARACTERIZATION_LIMITS["max_grounded_atoms"])
    iw = run_iterated_width(LocalPlannerRequest("iw", task, tuple(grounded), CHARACTERIZATION_LIMITS))
    results.append({"instance_id": instance_id, "wall_seconds": round(time.perf_counter() - wall_start, 3), "cpu_seconds": round(time.process_time() - cpu_start, 3), "characterization_status": row["status"], "bfs_expansions": row["bfs"]["exact_search"]["expansion_count"], "iw_status": iw.status, "iw_recovery_absent": "plan_recovery" not in iw.trace, "grounding_status": grounding_status})
print(json.dumps(results, sort_keys=True))
PY
```

Observed timings/statuses: `easy-0001` completed in 0.005 wall/0.005 CPU seconds with BFS 15 expansions and native IW 1 expansion/`failed_no_plan_extracted`; `medium-0000` completed in 0.226/0.223 seconds with BFS 10001 and native IW 1/`failed_no_plan_extracted`; `hard-0000` completed in 0.348/0.346 seconds with BFS 10001 and native IW 1/`failed_no_plan_extracted`. Every row was `characterized`, every native IW trace had zero recovery, and the 12-object row completed rather than becoming an incomplete diagnostic.

### Cleanup Receipt

After journaling the observed parent shell and exact command, the task stopped only `PID 215811` and tmux `cgas-partition-characterization-20260728T191238Z`:

```bash
source ~/cd_vlaplan && kill 215811 && tmux kill-session -t cgas-partition-characterization-20260728T191238Z
```

The follow-up process/session query found no PID and reported `no server running on /tmp/tmux-15306/default`. The failed-run evidence root `tmp/cgas-partition-characterization-20260728T191238Z/` remains untouched. No full corpus, checkpoint, production corpus path, partition selection, or approval marker was run or written.

## 2026-07-29 Independent Review Correction: IW Trace Accounting

### Defect

The prior remediation correctly prevented characterization recovery and discarded trace-only work, but native IW did not record total expansion count. `cgas_partition_characterization._expansion_count()` therefore fell back to counting retained events. With a one-event budget, it reported a partial count; with zero budget, a successful IW reported `success_full_trace` despite no retained trace.

### Fix

`local_iw._iw_trace()` now takes total `expansion_count` and generated trace-event count. It emits both `expansion_count` and `trace_complete`. The native success return chooses `success_full_trace` only for complete retained events and `success_truncated_trace` otherwise. Search ordering, novelty, visited/frontier behavior, recovery gates, and plan selection are untouched. Characterization already treats both success statuses as replay-valid exact search and uses `trace_complete` to prevent bounded traces from becoming source-ready.

### Red / Green

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_planner_performance.py::test_iw_counts_total_expansions_when_trace_retention_is_zero
```

RED: zero retained events returned `success_full_trace`, contrary to the contract. After the fix, the full focused suite passed:

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_planner_performance.py tests/phase3/test_cgas_partition_characterization.py tests/phase3/test_cgas_provenance.py tests/phase3/test_cgas_provenance_adversarial.py tests/phase3/test_cgas_certificates.py
source ~/cd_vlaplan && basedpyright scripts/phase3/local_iw.py scripts/phase3/cgas_partition_characterization.py tests/phase3/test_cgas_planner_performance.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/local_iw.py scripts/phase3/cgas_partition_characterization.py tests/phase3/test_cgas_planner_performance.py
```

Results: `41 passed in 11.55s`; Basedpyright `0 errors, 0 warnings, 0 notes`; compileall and `git diff --check` passed. LSP diagnostics were clean for `local_iw.py` and `test_cgas_planner_performance.py`.

### Runtime Evidence

The exact reviewer two-step repro was rerun. With `max_trace_steps=10`, native IW returns plan `(advance-0),(advance-1)`, `success_full_trace`, total expansions 2, retained 2, complete true. With `max_trace_steps=0`, it returns the identical plan, `success_truncated_trace`, total expansions 2, retained 0, complete false. Both are native IW, and neither has `plan_recovery`.

Accepted real rows under unchanged limits also completed: `blocksworld-dev-easy-0001` recorded IW 15 total/1 retained in 0.006s; `blocksworld-dev-medium-0000` 44/1 in 0.223s; `blocksworld-dev-hard-0000` 73/1 in 0.340s. Each native IW status was `failed_no_plan_extracted` without recovery, and each characterization record preserved the matching total count.

## 2026-07-29 Pipeline Truncated-Success Consumer Correction

### Defect

The IW accounting correction honestly returns `success_truncated_trace` once a valid native result has incomplete retained events. `pipeline._attempt_planner()` accepted only `success_full_trace`, and `schema.validate_supervised_example()` allowed only full-trace or external-plan replay fidelity. Consequently, a valid local plan beyond the production `max_trace_steps=500` retention budget was discarded despite successful replay.

### Fix and Boundaries

`schema.is_successful_trace_status()` is the shared native local-success predicate: it allows only `success_full_trace` and `success_truncated_trace`. `is_successful_example_status()` additionally allows external `success_plan_replayed` for schema validation. The local pipeline calls the native predicate and additionally requires a non-empty plan. Its existing replay validation now explicitly requires both `replay_ok` and `goal_satisfied`.

The pipeline serializes the honest status in `trace_fidelity` and preserves `planner_trace.trace_complete`. No value is remapped to full trace. Full-trace-only consumers were inspected and intentionally left fail-closed: provenance requires `success_full_trace`; certificate/source eligibility requires complete trace; verifier and Planimation gates require full fidelity.

### Red / Green

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_phase3_pipeline.py::test_pipeline_keeps_replayed_local_iw_success_with_truncated_trace
```

RED: the example was `None` because the full-only local status check discarded it. GREEN suites:

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_phase3_pipeline.py tests/phase3/test_phase3_local_trace_safety.py tests/phase3/test_cgas_planner_performance.py tests/phase3/test_cgas_partition_characterization.py tests/phase3/test_cgas_provenance.py tests/phase3/test_cgas_provenance_adversarial.py tests/phase3/test_cgas_certificates.py
source ~/cd_vlaplan && basedpyright scripts/phase3/schema.py scripts/phase3/pipeline.py scripts/phase3/local_iw.py tests/phase3/test_phase3_pipeline.py tests/phase3/test_cgas_planner_performance.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/schema.py scripts/phase3/pipeline.py tests/phase3/test_phase3_pipeline.py
```

The focused suite passed `78 passed in 36.00s`; compileall and `git diff --check` passed. Basedpyright reports six pre-existing `pipeline.py` errors at lines 132, 242, and 259, plus one pre-existing error in `test_cgas_planner_performance.py:168`; no changed-file LSP diagnostic was introduced.

### Runtime Evidence

The two-step native repro still gives the same plan and expansions 2 under both budgets. Budget 10: full status, 2 retained, complete true. Budget 0: truncated status, 0 retained, complete false. Neither trace contains `plan_recovery`. The pipeline-level truncated-success regression drives a real replay-valid PDDL plan through `_attempt_planner()` and produces an emitted example with `trace_fidelity=success_truncated_trace` and `planner_trace.trace_complete=false`.

## 2026-07-29 Shared Empty-Plan Success Boundary

### Defect and Scope

`_successful_attempt()` is the common final admission point for GBFS, goal-regression recovery, local planners, and external plans. An initially solved GBFS task returns `success_full_trace` with `plan=[]`. Because PDDL replay correctly regards the empty sequence as replay-valid and goal-satisfying in that case, the previous boundary emitted a successful supervised example. The prior local-only non-empty condition could not protect the other six caller paths.

### Fix

The shared boundary now rejects an empty plan immediately as `failed_no_plan_extracted`, with no replay row and no example. The local branch retains its native full/truncated success-status predicate but no longer duplicates the plan check. This leaves non-empty replay-valid full/truncated results unchanged while preserving existing rejection of resource-limit, failed-search, external replay-only, and replay-invalid results.

### Red / Green

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_phase3_pipeline.py::test_pipeline_rejects_empty_gbfs_plan_for_initially_solved_task
```

RED reported `success_full_trace` rather than `failed_no_plan_extracted` for a real initially solved GBFS task. After the shared guard:

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_phase3_pipeline.py tests/phase3/test_phase3_gbfs.py tests/phase3/test_phase3_local_trace_safety.py tests/phase3/test_cgas_planner_performance.py tests/phase3/test_cgas_partition_characterization.py tests/phase3/test_cgas_provenance.py tests/phase3/test_cgas_provenance_adversarial.py tests/phase3/test_cgas_certificates.py
source ~/cd_vlaplan && basedpyright scripts/phase3/pipeline.py tests/phase3/test_phase3_pipeline.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/pipeline.py tests/phase3/test_phase3_pipeline.py
```

The focused suite passed `85 passed in 37.50s`. `compileall` and `git diff --check` passed. Basedpyright retains six pre-existing `pipeline.py` errors at lines 132, 242, and 261; the shared-boundary change introduced none. The exact two-step IW repro continued to return its non-empty two-action plan as full with budget 10 and truncated with budget 0, both with expansion count 2 and no recovery.

## 2026-07-29 Lifecycle CLI

`python -m scripts.phase3.cgas_partition_characterization` now exposes only `fresh`, `shard`, `resume`, `finalize`, and `verify --target work|final`. It derives one direct `<repository>/tmp/<bundle-name>` bundle file and `<bundle-name>.work` sibling from an NFC-stable safe component. stderr carries flushed canonical progress only after durable checkpoint publication; stdout carries one canonical terminal report. `finalize` requires valid 481-checkpoint work, calls the confirmed candidate assembly and `regular_bundle_linkat_v1` publisher, and rejects existing final entries without replacement/adoption. `verify` remains read-only and consumes final bundle bytes without extraction. See `phase3_cgas_characterization_lifecycle_cli_2026-07-29.md` for exact owner-approved commands. This task used repository-local synthetic 481 QA only and did not run or publish a production accepted-manifest corpus.
