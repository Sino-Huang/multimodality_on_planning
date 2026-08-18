# Phase 3 Pilot Materialization Verification

## Focused TDD

- Honest RED: 6 failing tests because `cgas_pilot_expansion_index` did not exist.
- Final focused result: 8 passed.
- Focused regression result: 42 passed.

## Broad CGAS

Command: `pytest -q $(rg --files tests/phase3 | rg '/test_cgas_.*\\.py$')`

Result: 484 passed, 3 failed.

The three failures are pre-existing planner-probe binding failures outside this change:

1. `test_cgas_planner_blocker_probe.py::test_probe_records_repeated_native_searches_without_authoritative_fields`
   - CLI did not create `probe.json` because its authoritative implementation hash is stale.
2. `test_cgas_planner_alternative_profile_probe.py::test_alternative_profiles_are_deterministic_and_non_authoritative`
   - `PlannerBlockerProbeError: authoritative_hash_mismatch`.
3. `test_cgas_planner_alternative_profile_probe.py::test_final_retained_probe_matches_current_cli_semantics`
   - Same stale authoritative hash prevented `probe.json` creation.

## Full Phase 3 collection

Command: `pytest -q tests/phase3`

Result: collection stopped with 13 pre-existing output-layout/organize-output import errors. The active Python path mixed `/data/scratch/...` tests with `/scratch/...` source modules; errors include missing `receipt_path` and missing `VIEW_ROOT`.

## Static checks

- Ruff over changed Python files: passed.
- basedpyright over changed Python files: 0 errors, 0 warnings, 0 notes.

## Real-v3 QA

- Gate 0b: 281 candidates, 562 streams, 3,000,099,088 bytes.
- Source index: 31,171 rows.
- Replay-plan membership: 790 rows.
- Off-plan-only: 30,381 rows.
- Byte-stable replay: repeated materialization returned the same index SHA-256 and write-once outputs.
- Existing render audit: 2,568 records and PNG digests validated; 0/16,822 required states covered.
- Renderer was not invoked.

## Immutable inputs

All six input digests match `.claude/evidence/cgas-phase3-pilot-manifest/immutable-inputs.before.sha256` exactly. Neither characterization root changed.
