# Phase 3 CGAS Characterization Runner

Implemented deterministic checkpoint work orchestration without final candidate assembly, publication, or a CLI facade.

`fresh` validates the immutable source/population contract and durably creates only `<final-root>.work/run-contract.json` plus `<final-root>.work/checkpoints/`. It refuses an existing final or work root and calls the characterizer zero times.

`shard` validates existing work through the read-only verifier before selecting rows. Selection is sorted canonical index order and uses only `canonical_index % shard_count == shard_index`. `resume` validates first and fills only absent leaves, again in ascending index order. Each row rechecks the current contract both immediately before and immediately after the unchanged `_characterize()` call, checks returned row identity against contract-bound source/PDDL identities, then calls the existing durable no-replace checkpoint publisher.

Progress is injected and flushed as deterministic canonical JSON containing only `mode`, `row_index`, and `selected_count`. No persistent runner artifact contains timestamps or process IDs.

## Commands

```bash
source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 pytest -q tests/phase3/test_cgas_characterization_runner.py tests/phase3/test_cgas_characterization_runner_resume.py tests/phase3/test_cgas_characterization_contract.py tests/phase3/test_cgas_characterization_checkpoint.py tests/phase3/test_cgas_characterization_checkpoint_publication.py tests/phase3/test_cgas_characterization_verifier.py tests/phase3/test_cgas_partition_characterization.py tests/phase3/test_cgas_characterization_types.py tests/phase3/test_cgas_serialization.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_characterization_runner.py scripts/phase3/cgas_characterization_work.py scripts/phase3/cgas_characterization_contract.py tests/phase3/cgas_characterization_runner_support.py tests/phase3/test_cgas_characterization_runner.py tests/phase3/test_cgas_characterization_runner_resume.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_characterization_runner.py scripts/phase3/cgas_characterization_work.py
```

Results: 100 focused tests passed; Basedpyright reported zero errors; compilation succeeded. A real bounded 4/8/12 attempt under repo-local `tmp/` deliberately stopped at the fail-closed `renameat2(RENAME_NOREPLACE)` checkpoint boundary because that filesystem returned `EINVAL`. It created no final output and did not introduce an unsafe ordinary-rename fallback.
