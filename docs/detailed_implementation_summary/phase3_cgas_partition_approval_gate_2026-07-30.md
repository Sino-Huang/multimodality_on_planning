# Phase 3 CGAS Partition Approval Gate - 2026-07-30

This change adds the smallest executable prerequisite for a valid non-empty P0 partition: a separate owner-approval boundary that consumes a draft JSON and a matching owner-approval JSON, refuses the current empty fail-closed receipt, and only emits an approved partition when the approval artifact binds the exact draft bytes.

The selector module remains responsible for producing the deterministic draft. A new `scripts/phase3/cgas_partition_approval.py` module now owns the approval path so the existing draft evidence stays stable while the approval boundary becomes executable and testable.

## Behavior

- Current empty receipt stays blocked with `partition_records_empty`.
- A synthetic non-empty draft can be approved only when the approval artifact matches the draft digest, policy digest, record count, and schema version.
- Approved output is marked `status=approved_p0_partition`, `owner_approved=true`, and includes an `owner_approval_digest`.

## Verification

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_partition_selection.py tests/phase3/test_cgas_partition_feasibility.py tests/phase3/test_cgas_partition_selection_real_bundle.py::test_real_bundle_fails_closed_with_all_ineligible_12_object_rows
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_partition_approval.py scripts/phase3/cgas_partition_selection.py tests/phase3/test_cgas_partition_selection.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_partition_approval.py scripts/phase3/cgas_partition_selection.py tests/phase3/test_cgas_partition_selection.py
source ~/cd_vlaplan && python -m scripts.phase3.cgas_partition_approval --draft .omo/evidence/cgas-partition-characterization/planning_cgas_v1-draft.json --owner-approval .omo/evidence/task-partition-unblock-cgas-dataloader-and-experiment-support/current-empty-owner-approval.json --output .omo/evidence/task-partition-unblock-cgas-dataloader-and-experiment-support/current-empty-approved.json
source ~/cd_vlaplan && python -m scripts.phase3.cgas_partition_approval --draft .omo/evidence/task-partition-unblock-cgas-dataloader-and-experiment-support/synthetic-non-empty-draft.json --owner-approval .omo/evidence/task-partition-unblock-cgas-dataloader-and-experiment-support/synthetic-non-empty-owner-approval.json --output .omo/evidence/task-partition-unblock-cgas-dataloader-and-experiment-support/synthetic-non-empty-approved.json
```

## Evidence

- `/.omo/evidence/task-partition-unblock-cgas-dataloader-and-experiment-support/red-pytest.txt`
- `/.omo/evidence/task-partition-unblock-cgas-dataloader-and-experiment-support/green-pytest.txt`
- `/.omo/evidence/task-partition-unblock-cgas-dataloader-and-experiment-support/basedpyright.txt`
- `/.omo/evidence/task-partition-unblock-cgas-dataloader-and-experiment-support/compileall.txt`
- `/.omo/evidence/task-partition-unblock-cgas-dataloader-and-experiment-support/current-empty-cli.stdout`
- `/.omo/evidence/task-partition-unblock-cgas-dataloader-and-experiment-support/current-empty-cli.stderr`
- `/.omo/evidence/task-partition-unblock-cgas-dataloader-and-experiment-support/synthetic-non-empty-cli.stdout`
- `/.omo/evidence/task-partition-unblock-cgas-dataloader-and-experiment-support/synthetic-non-empty-cli.stderr`

## Remaining blocker

The existing successor-bundle regression `tests/phase3/test_cgas_partition_selection_real_bundle.py::test_successor_bundle_unblocks_role_bearing_partition` still fails with `structural_ood_coverage`. The successor bundle is parseable and all 481 rows are paired-exact, but it has only 3 composition signatures while the current policy requires at least 10 structural-OOD signatures. That is a separate selector-feasibility/input-diversity blocker, not an approval-gate failure.
