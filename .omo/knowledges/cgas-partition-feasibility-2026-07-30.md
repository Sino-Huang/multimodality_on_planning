# CGAS Partition Feasibility

- `scripts/phase3/cgas_partition_feasibility.py` parses final bundle bytes through `parse_bundle()` and calculates only frozen aggregate feasibility facts. It creates no `RoleRecord`, calls no `select_rows()`, and has no artifact-writing API or CLI.
- For the verified 481-row bundle, the sound current blocker is 24 paired-exact rows over 10 signatures with `((4, 24),)` objects. Every 12-object row is ineligible, so `structural_ood_ineligible` remains authoritative.
- Structural OOD, exact-39 calibration, and dev/test feasibility are `indeterminate_non_exact_metrics`: bounded or non-exact rows do not provide their successor paired-exact metrics. The prior 409 OOD, 72 residual, and 33 post-calibration figures were metric-sensitive observations, not independent feasibility conclusions, and are retracted.
- Tests perturb bounded 12-object metrics and prove the authoritative report remains unchanged and does not emit `dev_test_minimum_unavailable`.

## Verification

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_partition_feasibility.py tests/phase3/test_cgas_partition_selection.py tests/phase3/test_cgas_partition_selection_real_bundle.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_partition_feasibility.py tests/phase3/test_cgas_partition_feasibility.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_partition_feasibility.py tests/phase3/test_cgas_partition_feasibility.py
```

Focused tests and static checks are recorded in the Phase 3 implementation summary.
