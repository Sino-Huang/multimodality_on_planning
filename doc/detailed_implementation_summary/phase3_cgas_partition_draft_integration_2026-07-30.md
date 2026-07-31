# Phase 3 CGAS Partition Draft Integration

## Result

The retained selector draft is validated as a local, unapproved feasibility failure. The accepted Blocksworld source has 481 identities and exactly matches the final characterization bundle. The final bundle SHA-256 is `942d7be93ad0eb0ec6580bfe380fb8f09141662140ffc3d3c98e7f09a10ddaf4`, its run fingerprint is `0856e76571643362abb70551ff9d4e02e2d585f7384fc3ac0adb64df240d893a`, and the deterministic draft SHA-256 is `409f712797f8f02d49fe6d6b5a5b4e7a444f38c54e2cdefcbd4e0e9e7214630d`.

Only 24 rows are paired-exact and complete, all four-object. All 93 twelve-object rows are ineligible. The draft excludes exactly 457 rows, assigns no roles, records `failure=structural_ood_ineligible`, has `owner_approved=false`, and contains no approval digest. A fresh local rerun was retained under `tmp/cgas-partition-draft-7c76844e-6811-4caa-817b-7256d03763bd/` and is byte-identical to both existing evidence drafts.

## Plan Compliance

The plan requires role-bearing canonical FIFO BFS and width-1 IW records in all train/dev/test splits, structural-OOD disjointness, and downstream alignment/certificate/Qwen/loader gates. The empty failed draft cannot satisfy these requirements. The integration evidence is complete; no P0 partition, rendering, conversion, loader preflight, release, promotion, or approval was performed. Final verification F1-F4 and plan Todos 5-6 remain blocked.

## Selector Audit

The selector correctly fails closed for persisted paired-exact records, requires all twelve-object rows to be eligible, preserves whole composition groups, enforces exactly 39 calibration rows on success, and forces `owner_approved=false`.

It is not a standalone production verifier: it trusts persisted planner eligibility fields, validates digest syntax rather than independently recomputing every logical binding, and does not invoke the stronger final characterization verifier. The retained review package therefore records it as a feasibility result only. A future production path must run final characterization verification first and retain role-bearing output before any approval decision.

## Commands And Observed Results

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_partition_selection.py tests/phase3/test_cgas_partition_selection_real_bundle.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_partition_selection.py tests/phase3/test_cgas_partition_selection.py tests/phase3/test_cgas_partition_selection_real_bundle.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_partition_selection.py tests/phase3/test_cgas_partition_selection.py tests/phase3/test_cgas_partition_selection_real_bundle.py
source ~/cd_vlaplan && python -m scripts.phase3.cgas_partition_selection --bundle tmp/.cgas-characterization/planning_cgas_v1-characterization-481.cgas --output tmp/cgas-partition-draft-7c76844e-6811-4caa-817b-7256d03763bd/planning_cgas_v1-draft-rerun.json
source ~/cd_vlaplan && sha256sum .omo/evidence/cgas-partition-characterization/planning_cgas_v1-draft.json .omo/evidence/cgas-partition-characterization/planning_cgas_v1-draft-rerun.json tmp/cgas-partition-draft-7c76844e-6811-4caa-817b-7256d03763bd/planning_cgas_v1-draft-rerun.json
```

The isolated new integration test passed in 0.41 seconds. The full commands above are retained for the final clean regression pass. No network endpoint, Planimation renderer, or production output path was invoked.
