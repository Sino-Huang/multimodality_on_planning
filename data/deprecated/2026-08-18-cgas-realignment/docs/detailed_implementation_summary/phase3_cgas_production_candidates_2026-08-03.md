# Phase 3 CGAS Production Candidates - 2026-08-03

Implemented Todo 2 in `scripts/phase3/cgas_production_candidates.py` and helper modules. The implementation covers exact integer partitions, identity-ordered families, stable Blocksworld initial states and partial goals, Lehmer unranking, two-sorted graph canonicalization, minimum-rank accounting, immutable range publication, bootstrap/later-slice CLI commands, and the production config.

Verification commands:

```bash
source ~/cd_vlaplan && pytest -q tests/phase3/test_cgas_production_candidates.py
source ~/cd_vlaplan && ruff check scripts/phase3/cgas_candidate_publication.py scripts/phase3/cgas_candidate_reports.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_candidate_*.py scripts/phase3/cgas_production_candidates.py
```

Observed result: focused tests passed 13 tests; Ruff and configured basedpyright passed. Bootstrap returned frontiers `{4: 600, 8: 594, 12: 558}` and `13` ranges. An exact rerun returned the same result without replacing artifacts.

## Verification remediation

Removed automorphism-result reuse from canonical graph search so every selected-cell member is individualized and recursively refined. Replaced the raceable GPFS check-then-rename fallback with a shared atomic retry: after relative-dirfd `renameat2(RENAME_NOREPLACE)` returns `EINVAL`, the wrapper retries the identical operation using absolute descriptor-resolved paths and `AT_FDCWD`.

Regression verification:

```bash
source ~/cd_vlaplan && pytest -q tests/phase3/test_cgas_production_candidates.py
source ~/cd_vlaplan && pytest -q tests/phase3/test_cgas_production_candidates.py tests/phase3/test_cgas_production_candidates_remediation.py
```

Results were 13 and 15 passing tests respectively. Exact bootstrap, read-only rerun, and the 12-object later slice retained their previous counts and identities.

## Real GPFS publication correction

Real CLI QA disproved the absolute-path `renameat2` retry. Publication now uses a shared receipt-last filesystem primitive based on `flock`, exclusive `mkdir`, no-replace hard links, and fsync. Candidate `receipt.json` and report `exhaustion.json` are installed last as completion markers. Deterministic tests cover a destination winner race, pre-marker fault, post-marker fault, crash-partial recovery, hidden staging entries, and structured CLI filesystem errors.

Sequential GPFS bootstrap, exact 8-object rank 594/count 198, and exact 12-object rank 558/count 93 commands succeeded. Their exact reruns preserved 49 files by bytes, identity, and mtime. Final test results were 13 focused, 7 remediation, and 20 combined passing tests.
