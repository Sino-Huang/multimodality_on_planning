# Phase 3 Output Layout Wave 1 Repair 3

## Changes

Repair 3 strengthens structured-view publication and bounded content hashing without changing the approved catalog. Publication returns a held `PublishedStage` descriptor, validates the exact published tree and protected targets through that descriptor, and requires the canonical pathname to retain the same identity before success. Failed private stages are durably retained at their original unique private pathname without rename or deletion.

The idempotent existing-view path now opens and retains both the canonical view descriptor and its immediate parent descriptor. After all protected links are verified, it repeats the exact-tree scan, validates the canonical pathname against the held identity, and performs one last exact-tree scan before returning success. First publication uses the same final ordering. These checks close false-success races where a same-permission writer inserted an extra entry after the fifteenth link check or immediately after pathname validation.

Snapshot and protected-content readers now bound every read request by the remaining byte budget plus one detection byte. The traversal path also closes its duplicated descriptor if opening an existing child fails.

Review integration fixes updated two legacy test expectations, propagated `PublishedStage` through a publication monkeypatch, and package-qualified sibling-test imports for consistent runtime and strict-type resolution.

## Commands

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_output_layout_*.py
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright --project .omo/evidence/output-layout/task-1-3-wave1-repair-3/pyrightconfig.json
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/output_layout_*.py tests/phase3/test_output_layout_*.py
GIT_MASTER=1 git diff --check
```

## Results

The post-link and post-pathname race regressions failed before their production fixes and passed afterwards. The full output-layout suite passed 213 tests in 3.13 seconds. Basedpyright covered every output-layout source and test file under `typeCheckingMode: all` and reported 0 errors, 0 warnings, and 0 notes. Compileall and `git diff --check` exited 0. The no-excuse checker reported no violations in all 18 output-layout production files.

An isolated synthetic API run created and resolved all 15 approved relative links, repeated creation through the descriptor-bound existing-view path, and removed its temporary tree. No real repository output content was moved or modified.

Repair 3 evidence is stored under `.omo/evidence/output-layout/task-1-3-wave1-repair-3/`. Five independent goal, QA, code-quality, security, and context reviews ended `VERDICT: PASS`; Todos 1-3 are accepted and Todo 4 integration is unblocked. Real output relocation remains blocked until Todo 4 passes.
