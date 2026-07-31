# CGAS Partition Approval Gate

- `scripts/phase3/cgas_partition_approval.py` is the new executable owner-approval boundary.
- It refuses the current empty `draft_for_owner_review` receipt with `partition_records_empty`.
- It only approves a non-empty draft when the approval artifact matches the draft digest, policy digest, record count, and approval schema version.
- The approved artifact is tagged `approved_p0_partition` and carries `owner_approval_digest`.
- The approval boundary is kept separate from `scripts/phase3/cgas_partition_selection.py` so the existing draft digest evidence does not drift just because approval logic was added.

## Verification

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_partition_selection.py tests/phase3/test_cgas_partition_feasibility.py tests/phase3/test_cgas_partition_selection_real_bundle.py::test_real_bundle_fails_closed_with_all_ineligible_12_object_rows
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_partition_approval.py scripts/phase3/cgas_partition_selection.py tests/phase3/test_cgas_partition_selection.py
source ~/cd_vlaplan && python -m scripts.phase3.cgas_partition_approval --draft .omo/evidence/cgas-partition-characterization/planning_cgas_v1-draft.json --owner-approval .omo/evidence/task-partition-unblock-cgas-dataloader-and-experiment-support/current-empty-owner-approval.json --output .omo/evidence/task-partition-unblock-cgas-dataloader-and-experiment-support/current-empty-approved.json
source ~/cd_vlaplan && python -m scripts.phase3.cgas_partition_approval --draft .omo/evidence/task-partition-unblock-cgas-dataloader-and-experiment-support/synthetic-non-empty-draft.json --owner-approval .omo/evidence/task-partition-unblock-cgas-dataloader-and-experiment-support/synthetic-non-empty-owner-approval.json --output .omo/evidence/task-partition-unblock-cgas-dataloader-and-experiment-support/synthetic-non-empty-approved.json
```

## Remaining blocker

- `tests/phase3/test_cgas_partition_selection_real_bundle.py::test_successor_bundle_unblocks_role_bearing_partition` now reaches selector feasibility and fails with `structural_ood_coverage`.
- Probe result for `tmp/.cgas-characterization/cgas-state-gate-158105.cgas`: 481 rows, 481 paired-exact eligible rows, object counts `{4: 190, 8: 198, 12: 93}`, only 3 composition signatures, and only 1 12-object composition signature. Current policy requires `MIN_OOD_SIGNATURES = 10`, so Todo 5/6 must remain blocked until selector policy or input diversity is resolved.
