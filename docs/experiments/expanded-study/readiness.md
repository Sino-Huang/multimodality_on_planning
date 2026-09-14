# Shared execution readiness (#116)

The shared scheduler is `scripts/run_expanded_study.py`. It uses the original
14 September start and 21 September GPU cutoff in `schedule.json`; initialization
and resume never restart the clock. Its ledger is exclusively
`outputs/expanded-study/v1/budget.json`. Existing v5/historical ledgers and adapters
are not modified.

## Commands

Run from the repository root with the confirmed environment:

```bash
source ~/cd_vlaplan
python scripts/run_expanded_study.py init
python scripts/run_expanded_study.py status
python scripts/check_expanded_readiness.py
python -m pytest tests/planning_benchmark/test_expanded_scheduler.py -q
```

The two readiness jobs have already run. These exact commands are retained for
reproduction in a fresh ledger; repeating them against this ledger correctly
refuses duplicate successful launches:

```bash
python scripts/run_expanded_study.py launch --job configs/experiments/expanded-study/readiness-gpu-0.json
python scripts/run_expanded_study.py launch --job configs/experiments/expanded-study/readiness-gpu-1.json
python scripts/run_expanded_study.py launch --job configs/experiments/expanded-study/readiness-checkpoints.json
```

`launch` returns a detached supervisor PID and process-start identity immediately.
The output names its immutable attempt directory. Each attempt retains
`supervisor.log`, `worker.log`, `heartbeat.json`, `terminal.json`,
`completion.json`, `hook.log` and `hook-result.json`. The GPU probes also produce
`hardware.json`. Poll these files or verify the returned process identity; an
observation timeout is not permission to relaunch. Heartbeats update every second,
including completed/total, elapsed time, ETA (null until measurable), and the worker
handle. Logs remain on disk after the agent exits.

## Branch integration contract

A job JSON contains:

- `job_id`: stable unique logical stage name, letters/digits/underscore/hyphen.
- `branch`: one of the research allocation names in `schedule.json`.
- `gpus`: physical indices `[0]`, `[1]`, `[0, 1]`, or `[]` for CPU work.
- `max_seconds`: finite positive wall bound covering loading, work, diagnostics,
  saving and failure cleanup; admission reserves this bound times device count.
- `total`: declared positive count of records, episodes or stages.
- `command`: executable and arguments as a JSON array, executed from the repo root.
- `completion_hook`: CPU-only executable/argument array that independently audits
  declared coverage/artifacts on success and diagnoses logs on failure. The
  scheduler invokes it on normal exits, runtime stops and reconciled crashes.
- `resume_reason`: required only for a new attempt after a terminal failure;
  record the technical fix and any explicit checkpoint-resume arguments in
  `command`. Success is never rerun by this interface.

Use the three checked-in readiness configurations as executable examples. A branch
must first implement and qualify its own actual runner, freeze its scientific
configuration and selection rules, and select a sufficient runtime bound. This
interface does not make #117–#119, DAgger, successor prediction, replication or
transfer runnable. No experiment branch is launched by #116.

The scheduler sets `CUDA_VISIBLE_DEVICES` and a distinct explicit `MASTER_PORT`
from 18800–18805 after checking the host socket and central reservations. A
runner must preserve these values in torchrun/ms-swift launches and keep all
worker descendants in its process group (no daemonization or detached children).
Two-device jobs reserve both devices. Unrelated GPU processes are never killed.
Available VRAM is captured at GPU launch; it is a measurement, not a reservation
against unrelated workloads.

The worker receives `EXPANDED_ATTEMPT_DIR` and `EXPANDED_PROGRESS_PATH`. Atomically
replace the latter with JSON containing `completed`. Preserve all raw outputs,
failed traces and incomplete checkpoints in the attempt directory; explicit
resume may read prior artifacts but must not overwrite them. Per-branch code owns
semantic resume and scientific-contract verification. The scheduler provides
resource-safe attempt admission, not framework-specific checkpoint restoration.

The hook receives `EXPANDED_TERMINAL_PATH`, with GPUs hidden, after the allocation
is released. It has a 300-second CPU timeout; use a bounded hook to launch a
separate CPU audit job when an audit needs longer. Worker `succeeded` means exit
code zero, not experiment completion: require the hook's successful result and
its independent full-coverage report before declaring a branch fulfilled. Failed
hooks remain visible and never trigger a model rerun. They can be rerun directly
with the retained terminal path after fixing the audit.

## Accounting, cutoffs and recovery

A file lock serializes all admission and ledger changes. Running/reserved jobs
consume their full maximum allocation for admission; terminal jobs consume actual
allocated device durations, including failures. CPU child time and wall time are
separate fields. Device duration is not GPU utilization. Runtime limits and the
absolute cutoff terminate the entire owned worker group. A separate GNU `timeout`
process enforces the bound even if the Python supervisor dies.
CPU jobs may run after the GPU cutoff but cannot cross the handoff deadline.
Alternate `--ledger` paths are supported for isolated CPU tests; GPU launches
must use the single production ledger.

```bash
python scripts/run_expanded_study.py reconcile
```

Reconciliation checks Linux PID start identities and process groups, never just a
heartbeat or lock file. Live orphan workers retain their allocation and block
relaunch. Once a crashed worker group is verified stopped, reconciliation records
an interrupted terminal attempt and runs its completion hook. Because its exact
stop time is unknown, it conservatively charges elapsed time through reconciliation
and records CPU time as unknown. This can exhaust a branch; it never forgives
unobserved costs. Existing successful attempts and the full cost history persist.
An incomplete launch with missing process handles retains its reservation for
explicit process inspection; it is never treated as proof that no worker exists.

Prospective transfers preserve the total ceiling and calendar cutoff, record the
reason and already committed amount, and cannot remove spent/reserved allocation:

```bash
python scripts/run_expanded_study.py transfer --source recovery_reserve --target expanded_baseline --hours 1 --reason 'Documented prospective technical recovery'
```

This is syntax documentation; no transfer was needed or executed for readiness.
Transfers must not silently remove declared coverage. The reserve cannot be used
as an experiment branch directly.

## Evidence and limits

`readiness.json` records revalidation of all twelve v5 checkpoint bindings,
16-update/seed-17 exposure, adapter configuration, retained training provenance,
and every adapter tensor's finiteness on CPU. It also captures hardware inventory
and the unrelated process present during inspection. The existing v5 verifier
performs provenance checks; safetensors reads verify actual checkpoint content.
No adapter was trained or modified.

`scheduler-verification.json` records the test run and compact copies of both
hardware probes, terminal accounting, port mapping and completion audits. The
live ledger remains the authoritative cumulative accounting source. Unit tests
exercise caps, cutoff admission, distinct ports, collision/duplicate refusal,
failed resume, transfers, real detached jobs, completion hooks, runtime killing
and recovery after forcibly killing a supervisor.

The probes establish small CUDA operation capability on both A100s, not that a
particular model or proposed matrix fits. #117 and later branches still require
outcome-blind input/cost qualification under the unchanged allocations. The
nine-day calendar is an internal project window, not a verified ICLR deadline.
