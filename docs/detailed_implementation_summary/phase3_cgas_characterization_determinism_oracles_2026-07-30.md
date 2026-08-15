# Phase 3 CGAS Characterization Determinism Oracles

The synthetic-only 481-row integration oracle finalizes forward, reverse, and two-batch resumed checkpoint histories through the public CLI. For one unchanged run contract, it retains comparison evidence before fixture cleanup: run-contract bytes/SHA-256 and fingerprint, whole-bundle bytes/SHA-256, parsed header fingerprint, parsed member name/size/SHA-256 table, JSONL SHA-256, manifest SHA-256, and the same-contract byte-identity classification. All three logical members and the final bundle must be byte-identical.

The separate 2-vs-3-shard oracle deliberately uses contracts whose `shard_count` differs. It classifies run-contract bytes/SHA-256/fingerprint and bundle bytes/SHA-256 as expected inequality, while requiring exact scientific JSONL and manifest bytes. It also explicitly compares the manifest artifact SHA-256, source-record aggregate, object/split counts, and implementation digests. No product data, network activity, runner concurrency changes, or shard-state changes are involved.

Bundle SHA-256 is therefore contract-scoped provenance identity. It is an exact identity only within one run-contract fingerprint; it is not an oracle for scientific equality across contracts that intentionally bind different shard counts.

## Verification

```bash
source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 pytest -q tests/phase3/test_cgas_characterization_assembly.py tests/phase3/test_cgas_characterization_bundle.py tests/phase3/test_cgas_characterization_final_publication.py tests/phase3/test_cgas_characterization_verifier.py tests/phase3/test_cgas_characterization_cli.py tests/phase3/test_cgas_characterization_determinism.py
source ~/cd_vlaplan && basedpyright tests/phase3/cgas_characterization_assembly_support.py tests/phase3/test_cgas_characterization_determinism.py
source ~/cd_vlaplan && python -m compileall -q tests/phase3/cgas_characterization_assembly_support.py tests/phase3/test_cgas_characterization_determinism.py
source ~/cd_vlaplan && git diff --check
```

The focused pytest command passed twice with `49 passed` each time. Basedpyright reported `0 errors, 0 warnings, 0 notes`; compileall and `git diff --check` completed without output. Do not use a repository-local pytest `--basetemp`: the pre-existing verifier fixtures require a mode-0700 parent, while pytest creates supplied base directories mode-0755.
