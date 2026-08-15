# Phase 3 Output Layout Wave 1 Repair 2

> Superseded retention note: Repair 3 removed the `<stage>.cleanup` namespace transition. Current failed stages remain at their original unique private name. The text below records the historical Repair 2 design only.

## Changes

The view publisher now checks the full staged tree after fsync and checks the full published tree before reporting success. Transaction parsing removes the `MATCH_OK` suppression by parsing JSON operation values into a typed literal boundary.

The safety model retains ambiguous cleanup evidence instead of deleting through a final pathname: failed private stages use durable `<stage>.cleanup` no-replace transitions and receipt sidecars use unique `.retained-<token>` no-replace transitions with parent fsync. This intentionally trades storage and possible future fail-closed availability for no racer pathname deletion.

## Commands

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_output_layout_view_exact_tree_race.py
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_output_layout_*.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/output_layout_*.py tests/phase3/test_output_layout_*.py
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright --project /tmp/opencode/output-layout-pyrightconfig.json scripts/phase3/output_layout_*.py tests/phase3/test_output_layout_*.py
```

## Results

The red post-fsync race failed before the source edit and passed afterwards. The current full output-layout suite passed 200 tests in 2.41s; strict temporary-project Basedpyright reported 0 errors, 0 warnings, and 0 notes; compileall and `git diff --check` exited 0; and the no-excuse checker reported no violations in 35 files.

The independent security and code-quality reviews remain approved pre-fix red-baseline artifacts. Current Repair 2 verification passes; this does not retroactively alter their historical review verdicts.
