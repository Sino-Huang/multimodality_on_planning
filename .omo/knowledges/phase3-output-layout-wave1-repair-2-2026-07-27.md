# Phase 3 Output-Layout Wave 1 Repair 2

> Superseded retention note: Repair 3 removed the `<stage>.cleanup` namespace transition. Current failed stages remain at their original unique private name. The text below records the historical Repair 2 design only.

The exact private-stage tree must be validated after fsync immediately before no-replace publication and the published tree must be exact before success. A deterministic post-fsync extra-entry regression was saved red then green under `.omo/evidence/output-layout/task-1-3-wave1-repair-2/`.

Retention is the safe cleanup protocol: failed stages are retained as `<stage>.cleanup`; receipt sidecars use unique `.retained-<token>` no-replace transitions; parent directories are fsynced. Do not add pathname deletion after identity checks because Linux cannot conditionally unlink/rmdir by an expected inode.

Commands run:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_output_layout_view_exact_tree_race.py
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_output_layout_*.py
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright --project /tmp/opencode/output-layout-pyrightconfig.json scripts/phase3/output_layout_*.py tests/phase3/test_output_layout_*.py
```

The full focused suite passed 200 tests in 2.41s. The strict temporary-project Basedpyright gate reported 0 errors, 0 warnings, and 0 notes; compileall and `git diff --check` exited 0; and the no-excuse checker reported no violations in 35 files.

The independent security and code-quality reviews are approved pre-fix red-baseline evidence. Current Repair 2 verification passes without asserting that those historical review verdicts changed.
