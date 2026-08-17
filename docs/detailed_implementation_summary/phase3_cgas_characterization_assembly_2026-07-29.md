# Phase 3 CGAS Characterization Assembly

## Scope

Task 7 adds private candidate assembly only. It does not rename, publish, create, or expose a final root.

## Design

`scripts/phase3/cgas_characterization_assembly.py` requires a current, complete 481-checkpoint work root through the read-only verifier. It rebuilds the contract, canonical rows, JSONL artifact, and manifest from current source and implementation state. Checkpoint envelopes are not included in JSONL.

`scripts/phase3/cgas_characterization_assembly_fs.py` creates a random mode-0700 candidate under a supplied owner-controlled `<repository>/tmp` private parent. It writes exactly three mode-0600 files with `O_NOFOLLOW|O_EXCL`, short-write handling, per-file fsync, and candidate-directory fsync. Failure retains the private candidate path for inspection.

The standalone final verifier runs against the private candidate before it is returned. It authoritatively validates canonical rows, newline form, manifest identities/counts/schema/implementation/policy linkages, literal `owner_approved=false`, and the exact three-file profile.

## Tests

The focused synthetic 481-row test suite covers clean, reverse, sharded, and interrupted-resumed checkpoint histories, which all yield byte-identical three-file candidates. It also covers missing, duplicate, foreign, stale, and newline-mutated checkpoints, checkpoint-envelope exclusion from JSONL, candidate extra-file rejection by the final verifier, and retained candidates after fsync failures.

## Commands

```bash
source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 pytest -q tests/phase3/test_cgas_characterization_assembly.py tests/phase3/test_cgas_characterization_verifier.py tests/phase3/test_cgas_characterization_contract.py tests/phase3/test_cgas_characterization_checkpoint.py tests/phase3/test_cgas_characterization_checkpoint_publication.py tests/phase3/test_cgas_partition_characterization.py tests/phase3/test_cgas_serialization.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_characterization_assembly.py scripts/phase3/cgas_characterization_assembly_fs.py tests/phase3/cgas_characterization_assembly_support.py tests/phase3/test_cgas_characterization_assembly.py
source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 python -m scripts.phase3.cgas_characterization_assembly --help
```
