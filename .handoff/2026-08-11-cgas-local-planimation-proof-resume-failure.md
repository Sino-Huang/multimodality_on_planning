# Handoff — 2026-08-11 CGAS Local Planimation Proof Resume Failure

## Completed

- Read `.handoff/2026-08-11-cgas-local-planimation-proof-failure.md` first and verified its assumptions.
- Project HEAD before verification matched `0bc31990e658c37f139b6c00ab6367bc2236c57c`; the GPL-separated backend clone remained pinned at `94d82afb5ee122ce579dd11ca1953b7c85ca5824` (`v0.1.7`).
- The command-local backend import fix passed while retaining the mandatory `source ~/cd_vlaplan &&` prefix: explicit `PYTHONPATH` made the clone's `server` package importable despite activation resetting cwd.
- Exactly seven hermetic upstream tests passed. `test_planimation_process` remained excluded because its source invokes the hosted solver.
- The prepared local loopback proof harness ran once on the fresh output root `outputs/image_frames/cgas-local-planimation-proof-resume-20260811` and hard-stopped before the backend listened.
- Persisted artifacts: `backend.log` and `proof-report.json` in that output root. No VFG, PNG, empty-plan result, or 12-object artifact was produced.
- Exact evidence: `.claude/evidence/cgas-phase3-pilot-rendering/verification-20260811-local-planimation-backend-proof-resume.md`.
- Local WIP evidence commit: exact SHA `9fba74b6daf6b958024ecd7f8382bd106d46600b`, message `wip: record local Planimation startup failure`. It was not pushed.
- Hosted requests: `0`. Production: not started. No adapter integration, fallback, replay alignment, Qwen, planning_vlm, or training.

## Failures

### Command 1 — seven hermetic upstream tests

Command:

```text
source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/data/scratch/projects/punim0478/sukaih/multimodality_on_planning/.slim/clonedeps/repos/planimation__backend /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/.slim/clonedeps/.venv-planimation-v0.1.7/bin/python -m unittest server.unit_test.test_cases.TestStringMethods.test_upper server.unit_test.test_cases.TestStringMethods.test_isupper server.unit_test.test_cases.TestStringMethods.test_split server.unit_test.test_cases.TestStringMethods.test_domain_parser server.unit_test.test_cases.TestStringMethods.test_problem_parser server.unit_test.test_cases.TestStringMethods.test_predicates_generator server.unit_test.test_cases.TestStringMethods.test_solver
```

Exit: `0`

Full actual output, verbatim:

```text
Conda environment 'ada_vla' is already activated.
.......
----------------------------------------------------------------------
Ran 7 tests in 0.044s

OK
```

### Command 2 — local loopback proof harness

Command:

```text
source ~/cd_vlaplan && /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/.slim/clonedeps/.venv-planimation-v0.1.7/bin/python .claude/evidence/cgas-phase3-pilot-rendering/local_planimation_backend_proof.py --backend-python /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/.slim/clonedeps/.venv-planimation-v0.1.7/bin/python --output-root /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/outputs/image_frames/cgas-local-planimation-proof-resume-20260811 --port 8000
```

Exit: `1` (harness hard-stop path).

Full actual stdout/stderr, verbatim:

```text
Conda environment 'ada_vla' is already activated.
HARD STOP: backend_server_exited_during_startup
```

Persisted `backend.log`, exact content:

```text
Traceback (most recent call last):
  File "/data/scratch/projects/punim0478/sukaih/multimodality_on_planning/.slim/clonedeps/repos/planimation__backend/server/manage.py", line 8, in <module>
    from django.core.management import execute_from_command_line
ModuleNotFoundError: No module named 'django'

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/data/scratch/projects/punim0478/sukaih/multimodality_on_planning/.slim/clonedeps/repos/planimation__backend/server/manage.py", line 10, in <module>
    raise ImportError(
ImportError: Couldn't import Django. Are you sure it's installed and available on your PYTHONPATH environment variable? Did you forget to activate a virtual environment?
```

Persisted `proof-report.json` records:

- `status`: `hard_stop`
- `reason`: `backend_server_exited_during_startup`
- `backend.backend_python`: `/home/sukaih/miniconda3/envs/ada_vla/bin/python3.10`
- `backend.started`: `false`
- `replay3`: `null`
- `empty_plan_probe`: `null`
- `twelve_object`: `null`
- `hosted_requests`: `0`

No remediation or rerun occurred after the formal failure.

## Suspected Root Cause

**High confidence:** `.claude/evidence/cgas-phase3-pilot-rendering/local_planimation_backend_proof.py:469` applies `Path.resolve()` to the supplied `--backend-python`. The venv's `bin/python` is a symlink; resolving it converts the launch path to `/home/sukaih/miniconda3/envs/ada_vla/bin/python3.10`. The backend subprocess therefore loses the venv context containing Django 5.2.17 and exits with `ModuleNotFoundError: No module named 'django'`.

This is a bounded harness defect, not evidence against the pinned backend runtime. It is not a GPL, parser, supplied-plan, semantic, or VFG determinism hard stop. Those proofs remain unexecuted.

## Next Session Options

### A — Continue at the next authority-plan proof item

Not dependency-ready until the harness preserves the supplied venv executable path.

### B — Fix the harness interpreter-path handling first (recommended)

Make one bounded change in `.claude/evidence/cgas-phase3-pilot-rendering/local_planimation_backend_proof.py`: convert `--backend-python` to an absolute path without following symlinks (for example, `Path(os.path.abspath(args.backend_python.expanduser()))`) and retain the executable-file check. Add a focused test or mechanical assertion proving the venv path remains `.slim/clonedeps/.venv-planimation-v0.1.7/bin/python`, not the base Conda target. Do not edit the GPL clone or environment.

Then run final verification once:

1. The same seven hermetic tests with explicit backend `PYTHONPATH`.
2. The harness on a new absent output root and loopback port.
3. Hard-stop immediately on replay-3 nondeterminism/unpinnable VFG or semantic failure; only on pass proceed to empty-plan and one 12-object validation.

**Recommendation: B.** It directly fixes the exact persisted startup cause while preserving the supplied-plan, GPL-separation, local-only, no-fallback, and no-production boundaries.

Smallest first inspection:

```text
source ~/cd_vlaplan && /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/.slim/clonedeps/.venv-planimation-v0.1.7/bin/python -c "from pathlib import Path; p=Path('/data/scratch/projects/punim0478/sukaih/multimodality_on_planning/.slim/clonedeps/.venv-planimation-v0.1.7/bin/python'); print(p.absolute()); print(p.resolve())"
```

Acceptance: the harness must launch `p.absolute()` semantics and the persisted report must retain the venv path.
