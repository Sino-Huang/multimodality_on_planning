# Phase 3 CGAS Characterization Kernel Isolation

## Scope

Task 1 separates non-search row projection, composition descriptors, and manifest writing from the characterization facade. The scientific orchestration body in `_characterize()` is unchanged.

## Compatibility

- The facade retains `CharacterizationInput`, `CHARACTERIZATION_LIMITS`, `canonical_composition_signature`, `characterize_instances`, `load_accepted_blocksworld`, `write_characterization`, and `_planner_record` imports.
- `canonical_composition_signature` and `_planner_record` are exact row-module re-exports.
- The writer passes the facade path to the extracted manifest helper, preserving the existing implementation-module identity manifest field and schema.

## Frozen Evidence

- `_characterize()` normalized AST identity: frozen at the 2026-07-29 kernel-isolation run.
- Representative canonical row: 3,850 bytes, identity frozen at the same run.
- Pure LOC: facade 124; row module 212.

## Verification Commands

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_partition_characterization.py tests/phase3/test_cgas_planner_performance.py tests/phase3/test_cgas_provenance.py tests/phase3/test_cgas_provenance_adversarial.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_partition_characterization.py scripts/phase3/cgas_characterization_rows.py tests/phase3/test_cgas_partition_characterization.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_partition_characterization.py scripts/phase3/cgas_characterization_rows.py tests/phase3/test_cgas_partition_characterization.py
git diff --check -- scripts/phase3/cgas_partition_characterization.py scripts/phase3/cgas_characterization_rows.py tests/phase3/test_cgas_partition_characterization.py
```

All commands completed successfully. No full production corpus, output root, rendering, network, checkpoint, approval, or commit operation was performed.
