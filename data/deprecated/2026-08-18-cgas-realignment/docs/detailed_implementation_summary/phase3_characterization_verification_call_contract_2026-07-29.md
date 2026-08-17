# Phase 3 Characterization Verification Call Contract

## Change

Checkpoints now retain each canonical characterization row as canonical JSON text alongside its identity. Work verification validates checkpoint structure, linkages, canonical row text, and row identity without invoking the characterization kernel. Assembly consumes the verified checkpoint rows in checkpoint-index order.

Final candidate verification remains authoritative: it recomputes every contract row once and applies final row, replay, policy, and manifest validation. Final publication uses that verified candidate result, then validates the generated anonymous bundle's identity and inode/durability state without repeating the scientific recomputation.

## Verification

```bash
source ~/cd_vlaplan && pytest -q tests/phase3/test_cgas_characterization_assembly.py tests/phase3/test_cgas_characterization_verifier.py tests/phase3/test_cgas_characterization_cli.py
source ~/cd_vlaplan && pytest -q tests/phase3/test_cgas_characterization_checkpoint.py tests/phase3/test_cgas_characterization_runner_resume.py tests/phase3/test_cgas_characterization_final_publication.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_characterization_checkpoint.py scripts/phase3/cgas_characterization_checkpoint_contracts.py scripts/phase3/cgas_characterization_verifier.py scripts/phase3/cgas_characterization_assembly.py scripts/phase3/cgas_characterization_final_publication.py scripts/phase3/cgas_characterization_runner.py tests/phase3/test_cgas_characterization_cli.py tests/phase3/cgas_characterization_assembly_support.py
git diff --check
```

The focused suites passed (37 + 24 tests). The CLI regression test asserts that a complete synthetic `finalize` calls the authoritative characterizer exactly 481 times.
