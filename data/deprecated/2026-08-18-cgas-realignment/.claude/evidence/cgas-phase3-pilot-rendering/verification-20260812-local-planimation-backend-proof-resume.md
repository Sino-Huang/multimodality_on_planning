# Local Planimation Backend Proof Resume Verification — 2026-08-12

## Scope

- Resume from `.handoff/2026-08-11-cgas-local-planimation-proof-resume-failure.md`.
- Fix only the harness handling of the supplied venv interpreter path.
- Rerun the seven hermetic upstream tests and one local loopback proof through replay-3 determinism, VFG-to-PNG semantic validation, empty-plan behavior, and one 12-object validation.
- Local-only and supplied-plan-only: no hosted request, production start, adapter integration, or fallback.
- Stop immediately on the first hard-stop condition.

## Bounded Harness Fix

Path: `.claude/evidence/cgas-phase3-pilot-rendering/local_planimation_backend_proof.py`

```python
backend_python = Path(os.path.abspath(args.backend_python.expanduser()))
```

This replaces `Path.resolve()` semantics with an absolute path that does not follow the venv interpreter symlink. The existing executable-file check remains unchanged.

## Command 1 — Interpreter-Path Regression Assertion

Command:

```text
source ~/cd_vlaplan && /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/.slim/clonedeps/.venv-planimation-v0.1.7/bin/python -c "import os; from pathlib import Path; p=Path('/data/scratch/projects/punim0478/sukaih/multimodality_on_planning/.slim/clonedeps/.venv-planimation-v0.1.7/bin/python'); observed=Path(os.path.abspath(p.expanduser())); print(f'supplied={p}'); print(f'observed={observed}'); print(f'resolved={p.resolve()}'); assert observed == p.absolute(); assert observed != p.resolve(); assert str(observed).endswith('/.slim/clonedeps/.venv-planimation-v0.1.7/bin/python')"
```

Exit: `0`

Full actual output, verbatim:

```text
Conda environment 'ada_vla' is already activated.
supplied=/data/scratch/projects/punim0478/sukaih/multimodality_on_planning/.slim/clonedeps/.venv-planimation-v0.1.7/bin/python
observed=/data/scratch/projects/punim0478/sukaih/multimodality_on_planning/.slim/clonedeps/.venv-planimation-v0.1.7/bin/python
resolved=/home/sukaih/miniconda3/envs/ada_vla/bin/python3.10
```

Result: PASS. The launch path retains the supplied venv interpreter path rather than the base Conda target.

## Command 2 — Seven Hermetic Upstream Tests

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
Ran 7 tests in 0.019s

OK
```

`test_planimation_process` remained excluded because its upstream source invokes the hosted solver.

## Command 3 — Local Loopback Proof Harness

Command:

```text
source ~/cd_vlaplan && /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/.slim/clonedeps/.venv-planimation-v0.1.7/bin/python .claude/evidence/cgas-phase3-pilot-rendering/local_planimation_backend_proof.py --backend-python /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/.slim/clonedeps/.venv-planimation-v0.1.7/bin/python --output-root /data/scratch/projects/punim0478/sukaih/multimodality_on_planning/outputs/image_frames/cgas-local-planimation-proof-resume-20260812 --port 18080
```

Exit: nonzero (harness hard-stop path).

Full actual stdout/stderr, verbatim:

```text
Conda environment 'ada_vla' is already activated.
HARD STOP: replay3_vfg_nondeterministic
backend listening on http://127.0.0.1:18080
```

The sequence stopped immediately. No retry, diagnosis command, alternate port or output root, semantic normalization, or fallback was attempted.

## Persisted Result

Output root: `outputs/image_frames/cgas-local-planimation-proof-resume-20260812`

Artifacts:

- `backend.log`
- `proof-report.json`
- `replay3-run1.vfg.json`
- `replay3-run2.vfg.json`

The persisted report records:

- `status`: `hard_stop`
- `reason`: `replay3_vfg_nondeterministic`
- `backend.backend_python`: `/data/scratch/projects/punim0478/sukaih/multimodality_on_planning/.slim/clonedeps/.venv-planimation-v0.1.7/bin/python`
- `backend.started`: `true`
- replay-3 run 1: SHA-256 `03e94da576a83dd7d2cfcfe42ce6e0d5b7fec0cd1325b673ac00ca8be40718fd`, 18,987 bytes
- replay-3 run 2: SHA-256 `f85b8a0ac707ca6ac65eea649d5aab8be995c8ba780ead2f9d9649f6d91106cb`, 18,982 bytes
- the recorded path deltas are sprite `color.r`, `color.g`, and `color.b` values across the visual stages
- `empty_plan_probe`: `null`
- `twelve_object`: `null`
- `hosted_requests`: `0`

The backend log contains exactly two successful loopback POSTs:

```text
[11/Aug/2026 15:14:33] "POST /upload/pddl HTTP/1.1" 200 18987
[11/Aug/2026 15:14:33] "POST /upload/pddl HTTP/1.1" 200 18982
```

## Acceptance Result

- Harness venv interpreter-path handling: PASS.
- Seven hermetic upstream tests: PASS.
- Loopback backend startup with the supplied venv: PASS.
- Replay-3 byte determinism: HARD STOP.
- VFG-to-PNG semantic validation: not run.
- Empty-plan behavior: not run.
- 12-object validation: not run.
- Hosted requests: `0`.
- Production: not started.

## Suspected Root Cause

No implementation root cause is asserted in this session. The persisted comparison establishes color-only VFG differences between the two identical replay-3 requests, but the generating mechanism was not investigated after the required hard stop.
