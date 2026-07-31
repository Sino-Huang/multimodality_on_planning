# CGAS Characterization Runner

Date: 2026-07-29

- `scripts.phase3.cgas_characterization_runner.run()` has no CLI facade. `fresh` creates only `<final-root>.work` with `run-contract.json` and an empty `checkpoints/` directory; it never invokes the characterizer or creates the final root.
- `shard` first asks the read-only work verifier to authorize the exact existing root, then uses only sorted canonical row index modulo `shard_count`. `resume` performs the same verification and fills only missing leaves in ascending canonical index order.
- Every selected row rebuilds and compares the immutable contract before and after the unchanged `_characterize()` kernel. The returned row must also exactly retain the contract-bound instance, split, PDDL digests, and source-record digest before its canonical digest is published through the existing no-replace checkpoint publisher.
- Progress goes only to an injected, flushed sink as canonical JSON records with `mode`, `row_index`, and `selected_count`. Persistent work bytes do not contain timestamps or process IDs.
- The runner and work-lifecycle modules are conditionally included in the contract import closure whenever present, preserving implementation-drift invalidation without breaking isolated synthetic repository fixtures that intentionally omit them.

## Verification

```bash
source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 pytest -q tests/phase3/test_cgas_characterization_runner.py tests/phase3/test_cgas_characterization_runner_resume.py tests/phase3/test_cgas_characterization_contract.py tests/phase3/test_cgas_characterization_checkpoint.py tests/phase3/test_cgas_characterization_checkpoint_publication.py tests/phase3/test_cgas_characterization_verifier.py tests/phase3/test_cgas_partition_characterization.py tests/phase3/test_cgas_characterization_types.py tests/phase3/test_cgas_serialization.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_characterization_runner.py scripts/phase3/cgas_characterization_work.py scripts/phase3/cgas_characterization_contract.py tests/phase3/cgas_characterization_runner_support.py tests/phase3/test_cgas_characterization_runner.py tests/phase3/test_cgas_characterization_runner_resume.py
```

The focused suite passed 100 tests and Basedpyright reported zero errors. A bounded real 4/8/12 runner attempt under repository-local `tmp/` reached `publish_checkpoint` but failed closed because that filesystem rejects `renameat2(RENAME_NOREPLACE)` with `EINVAL`; no checkpoint was published and no fallback was introduced.
