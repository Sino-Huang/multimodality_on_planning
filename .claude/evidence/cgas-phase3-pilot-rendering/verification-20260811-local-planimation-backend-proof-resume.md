# Local Planimation Backend Proof Resume Verification — 2026-08-11

## Scope

- Resume from `.handoff/2026-08-11-cgas-local-planimation-proof-failure.md`.
- Retain pinned GPL-separated backend commit `94d82afb5ee122ce579dd11ca1953b7c85ca5824`.
- Local-only, supplied-plan route; no hosted API, no production, no adapter integration, no fallback.

## Preflight

- Project HEAD: `0bc31990e658c37f139b6c00ab6367bc2236c57c`.
- Backend clone HEAD: `94d82afb5ee122ce579dd11ca1953b7c85ca5824`.
- Command-local `PYTHONPATH` smoke passed after `source ~/cd_vlaplan` reset cwd:

```text
Conda environment 'ada_vla' is already activated.
/scratch/punim0478/sukaih/multimodality_on_planning
/data/scratch/projects/punim0478/sukaih/multimodality_on_planning/.slim/clonedeps/repos/planimation__backend/server/__init__.py
```

## Command 1 — Seven Hermetic Upstream Tests

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

`test_planimation_process` remained excluded because its upstream source invokes the hosted solver.

## Command 2 — Local Loopback Proof Harness

Command:

```text
source ~/cd_vlaplan && /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/.slim/clonedeps/.venv-planimation-v0.1.7/bin/python .claude/evidence/cgas-phase3-pilot-rendering/local_planimation_backend_proof.py --backend-python /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/.slim/clonedeps/.venv-planimation-v0.1.7/bin/python --output-root /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/outputs/image_frames/cgas-local-planimation-proof-resume-20260811 --port 8000
```

Exit: `1` (the harness hard-stop path returns 1).

Full actual stdout/stderr, verbatim:

```text
Conda environment 'ada_vla' is already activated.
HARD STOP: backend_server_exited_during_startup
```

No rerun or remediation was applied.

## Persisted Backend Log

Path: `outputs/image_frames/cgas-local-planimation-proof-resume-20260811/backend.log`

Exact content:

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

## Persisted Report Result

- Status: `hard_stop`.
- Reason: `backend_server_exited_during_startup`.
- The report records `backend_python` as `/home/sukaih/miniconda3/envs/ada_vla/bin/python3.10`, not the supplied `.slim/clonedeps/.venv-planimation-v0.1.7/bin/python` path.
- Backend started: `false`.
- Replay-3: `null`.
- Empty-plan probe: `null`.
- 12-object validation: `null`.
- Hosted requests: `0`.

## Suspected Root Cause

**High confidence:** the harness applies `Path.resolve()` to `--backend-python`. The isolated venv's `bin/python` is a symlink, so resolving it produces `/home/sukaih/miniconda3/envs/ada_vla/bin/python3.10`. The backend subprocess then starts with the base Conda interpreter rather than the venv context where Django 5.2.17 is installed, causing `ModuleNotFoundError: No module named 'django'` before the server listens.

This is a harness interpreter-path defect, not evidence against the pinned backend runtime. Replay-3 determinism, PNG semantics, empty-plan behavior, and 12-object compatibility remain unexecuted.
