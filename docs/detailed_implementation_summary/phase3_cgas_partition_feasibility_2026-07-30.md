# Phase 3 CGAS Partition Feasibility

## Scope

`scripts/phase3/cgas_partition_feasibility.py` provides a read-only in-memory feasibility report for final characterization bundle bytes. It parses only through `parse_bundle()` and returns aggregate counts plus deterministic failure reasons. It does not emit partition roles, construct `RoleRecord`, call `select_rows()`, execute planners, or write draft or production artifacts. No CLI was added, so the module has no output path and cannot write artifacts.

## Sound Feasibility Boundary

The verified `planning_cgas_v1-characterization-481.cgas` bundle remains unchanged (byte-identical) after analysis.

- Actual paired-exact eligibility is 24 rows, 10 composition signatures, and object distribution `((4, 24),)`.
- Every 12-object row is ineligible. `structural_ood_ineligible` is therefore an authoritative current blocker.
- Structural OOD, exact-39 calibration, and dev/test feasibility are `indeterminate_non_exact_metrics` until successor paired-exact metrics exist. Bounded/non-exact values cannot soundly stand in for those successor values.
- The earlier 409 OOD, 127 OOD-signature, 72 residual, 11 residual-group, and 33 post-calibration figures are retracted as feasibility conclusions. They depended on bounded/non-exact metrics and are no longer reported, including `dev_test_minimum_unavailable`.

The report imports only the selector's existing paired-exact predicate and grouping semantics. The selector source remains byte-identical because its owner-review draft includes an implementation identity; its real-bundle regression proves the prior draft output remains unchanged.

## Verification

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_partition_feasibility.py tests/phase3/test_cgas_partition_selection.py tests/phase3/test_cgas_partition_selection_real_bundle.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_partition_feasibility.py tests/phase3/test_cgas_partition_feasibility.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_partition_feasibility.py tests/phase3/test_cgas_partition_feasibility.py
source ~/cd_vlaplan && python -c 'from pathlib import Path; from scripts.phase3.cgas_partition_feasibility import analyze_bundle; print(analyze_bundle(Path("tmp/.cgas-characterization/planning_cgas_v1-characterization-481.cgas").read_bytes()))'
```

The feasibility tests include a bounded-metric perturbation regression: changing non-exact 12-object metrics cannot change the authoritative feasibility classification. The runtime invocation prints only paired-exact facts and `indeterminate_non_exact_metrics` for downstream feasibility.
