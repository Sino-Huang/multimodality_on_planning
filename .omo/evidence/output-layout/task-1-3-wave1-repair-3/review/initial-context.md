# Wave 1 Repair 3 Context and Scope-Fidelity Review

> HISTORICAL FIRST-ROUND REVIEW: superseded by the existing-view race repair, full-scope typing repair, synchronized Repair 3 evidence, and explicit Repair 2 supersession notices. Preserve for audit history; do not treat this file as a current verdict.

## Review Boundary

This leaf review inspected repository metadata, source, tests, plans, documentation, and evidence only. It did not read, list, hash, move, relink, or otherwise access real `outputs/` contents. The executed tests used pytest `tmp_path` fixtures.

## Plan and Scope

- The approved plan assigns the immutable contract, deterministic receipts, and structured view to Wave 1 Todos 1-3, and explicitly blocks Todo 4 on all three (`.omo/plans/outputs-vlm-dataset-layout.md:97-109`). Todo 3 must create only relative links, preserve protected artifacts, and reject collisions without overwrite (`:133-140`).
- Git status/diff show no tracked `outputs/` change and no tracked deletion/reversion of an output-layout source or test file. The output-layout modules and tests are untracked additions; the tracked modifications are a separate Planimation workstream. This review made no reversion.
- No output-layout dependency or configuration manifest appears in the tracked diff or in the output-layout untracked-file set. A repository-wide untracked `uv.lock` exists outside that set and is not attributable to the output-layout implementation from the available git evidence.
- The current contract retains the approved three protected roots, validates the immutable default catalog, rejects relocation overlap, and treats the view as non-authoritative. The view preflight pins protected paths/content, opens path components with no-follow directory descriptors, revalidates before publication, and verifies every final link against its pinned protected target. Current callers use the current signatures: `create_output_layout_view` is called by the focused tests, `verify_symlink` is called by `_verify_all_links`, and the split view modules consistently import the shared view types.

## Evidence and Contract Findings

The historic Repair 2 red/green pair is valid only for its post-fsync extra-entry race: its red receipt records a missing fail-closed error, and its green receipt records one passing regression. It does not establish a Repair 3 baseline or green result. Repair 3 currently contains only this `review/` directory; it has no red/green receipt, command log, DoneClaim, or current-suite evidence.

More importantly, the repository has an unresolved retention contract contradiction:

- `.omo/knowledges/phase3-output-layout-wave1-repair-2-2026-07-27.md:5` and `doc/detailed_implementation_summary/phase3_output_layout_wave1_repair_2_2026-07-27.md:7` require failed private stages to use durable no-replace `<stage>.cleanup` transitions.
- `scripts/phase3/output_layout_view_stage.py:180-190` instead fsyncs and leaves the failed stage at its original private pathname. The newer retention tests explicitly require that behavior and assert that no `.cleanup` path exists.
- The older current acceptance test `tests/phase3/test_output_layout_acceptance_security.py::test_private_stage_cleanup_preserves_unowned_child` still requires the documented `.cleanup` location. It is currently red: the expected `.cleanup/racer-owned` path does not exist.

Executed synthetic checks:

```text
pytest -q tests/phase3/test_output_layout_retention_dispatch_races.py tests/phase3/test_output_layout_view_exact_tree_race.py
# 6 passed

pytest -q tests/phase3/test_output_layout_acceptance_security.py::test_private_stage_cleanup_preserves_unowned_child
# 1 failed: FileNotFoundError for <stage>.cleanup/racer-owned

pytest -q tests/phase3/test_output_layout_view_races.py::test_stage_cleanup_retains_its_original_unique_name_without_quarantine_mutation tests/phase3/test_output_layout_retention_dispatch_races.py::test_stage_cleanup_retains_its_original_private_name_without_rename_or_delete
# 2 passed
```

The protected-root and publication guards remain present, and no real output was moved. Nevertheless, the current green claim cannot be accepted: a current acceptance test, the Repair 2 documentation, and the implementation/tests disagree on the retention publication contract. This also means the required evidence does not accurately distinguish a fixed baseline from the current state. Under the approved dependency matrix, Todo 4 remains blocked until this review and the other Wave 1 reviews pass unconditionally.

VERDICT: FAIL
