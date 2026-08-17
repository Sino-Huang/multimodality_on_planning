# Phase 3 CGAS Trusted State GPFS Remediation

`tmp/.cgas-characterization` is the only lifecycle namespace. `tmp` may be current-owner mode 2755 but cannot be group/other writable. Fresh creates and pins the child with no-follow descriptors and exact owner mode 0700; resume, finalize, and verify reject an absent or invalid child. Legacy direct-`tmp` work and final roots reject without migration.

The retained synthetic 481 fill took 13.25 minutes. Plan 12-16 minutes for real owner review, then run finalize and final verification.

```bash
source ~/cd_vlaplan && pytest -q tests/phase3/test_cgas_characterization_state_directory.py tests/phase3/test_cgas_characterization_cli.py tests/phase3/test_cgas_characterization_final_publication.py tests/phase3/test_cgas_characterization_contract.py tests/phase3/test_cgas_characterization_work.py tests/phase3/test_cgas_characterization_runner.py tests/phase3/test_cgas_characterization_runner_resume.py tests/phase3/test_cgas_characterization_checkpoint.py tests/phase3/test_cgas_characterization_verifier.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_characterization_state_directory.py scripts/phase3/cgas_characterization_cli.py scripts/phase3/cgas_characterization_final_publication.py scripts/phase3/cgas_characterization_contract.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_characterization_state_directory.py scripts/phase3/cgas_characterization_cli.py scripts/phase3/cgas_characterization_final_publication.py scripts/phase3/cgas_characterization_contract.py
```
