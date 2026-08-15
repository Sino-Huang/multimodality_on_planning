# Phase 3 CGAS Planner Blocker Investigation Decision Record

## Decision Status

This local investigation is complete. The Phase 3 CGAS partition remains policy-blocked and unapproved. Nothing in this record approves or promotes a partition, starts rendering, authorizes release, changes a source/profile/selector, or completes the master plan.

## Authoritative Inputs

| Artifact | Path or member | SHA-256 |
| --- | --- | --- |
| Accepted source manifest | `data/curriculum_pddl/accepted_manifest.jsonl` | `9a9817058e36f72468682c8b43a46c04591995bcb8fe28ee37819313f9376217` |
| Final bundle | `tmp/.cgas-characterization/planning_cgas_v1-characterization-481.cgas` | `942d7be93ad0eb0ec6580bfe380fb8f09141662140ffc3d3c98e7f09a10ddaf4` |
| Characterization member | `characterization.jsonl` | `4596ffdeedf3a212f8e44f9bcb3af6c80b33315d643cba6b9e0d93226b010417` |
| Selector draft | `.omo/evidence/cgas-partition-characterization/planning_cgas_v1-draft.json` | `409f712797f8f02d49fe6d6b5a5b4e7a444f38c54e2cdefcbd4e0e9e7214630d` |
| Run contract fingerprint | bundle metadata | `0856e76571643362abb70551ff9d4e02e2d585f7384fc3ac0adb64df240d893a` |
| Final scientific probe | both retained `probe.json` files below | `90f3b523e1923966a6fe34bf5dd44183dedfd39e955016df81ead637c9c24d12` |

The probe recorded identical bundle, member, and draft hashes before and after execution. The pre-hardening and hardened scientific records are byte-identical:

- `tmp/cgas-planner-blocker-investigation-20260730t102100/probe.json`
- `tmp/cgas-planner-blocker-investigation-20260730t103100/probe.json`

Timing remains outside canonical scientific bytes in each retained `timings.jsonl`.

## Established Facts

- The persisted `plan/sas_plan` for `blocksworld-dev-hard-0000`, `blocksworld-test-hard-0014`, and `blocksworld-train-hard-0000` replayed to the goal.
- Canonical FIFO BFS reached 10,001 expansions and returned `skipped_resource_limit` for all three representatives under the unchanged 10,000-expansion limit.
- Native width-1 IW, with recovery disabled, exhausted novelty at 73 dev, 71 test, and 90 train expansions. Each returned `failed_no_plan_extracted`.
- Independent end-to-end checks cover separate Blocksworld PDDL parsing, grounding, BFS, IW(1), state transitions, and plan validation. They also reproduce a real small IW(1) failure on a task with an independently found four-step plan.
- The frozen 481-row bundle has 24 paired-exact complete rows. All 24 are four-object rows. All 93 twelve-object rows are ineligible.
- Structural OOD, exact-39 calibration, and dev/test feasibility are `indeterminate_non_exact_metrics`. The frozen bounded or non-exact metrics cannot stand in for successor paired-exact values.

## Scoped Conclusion

The evidence supports: `no product bug found under tested semantics`.

This is not a claim of universal planner correctness, task unsolvability, or independent cardinality infeasibility. It says the tested implementation and an independent model agree on the covered semantics, while the representative failures are consistent with the configured BFS resource bound and native IW(1) novelty limit.

## Retracted Claim

The prior `409 OOD -> 72 residual -> 33 after calibration` feasibility conclusion is retracted. The 409 count included rows whose structural metrics were bounded or non-exact. Oracle demonstrated that changing those unknown values could change the downstream cardinalities, so the arithmetic conditional on 409 did not establish feasibility or infeasibility. The related `dev_test_minimum_unavailable` conclusion is also retracted.

## Current Blocker

The authoritative blocker is `structural_ood_ineligible`: only 24 rows are paired-exact, all are four-object, and all 93 twelve-object rows required by the current selector policy are ineligible. The selector therefore emits zero role records, `owner_approved=false`, and no approval digest. Downstream structural, calibration, and dev/test questions remain `indeterminate_non_exact_metrics`.

## Oracle Review

Oracle initially returned `FAIL` with two blocking scientific findings and two hardening findings:

1. The `409/72/33` conclusion treated non-exact metrics as authoritative.
2. Planner parity did not yet cross an independent end-to-end parsing, grounding, transition, and search boundary.
3. Probe source and output containment had traversal, symlink, and parent-replacement gaps.
4. A caller-owned active `ITIMER_REAL` could be disturbed.

The remediation retracted the unsupported feasibility claim, added metric-perturbation and independent end-to-end parity coverage, anchored output publication to verified descriptors, hardened source containment, and preserved caller timer ownership. Oracle re-reviewed the changed evidence and returned `PASS` with no remaining blocking correctness, evidence-integrity, or design findings. That review acceptance is not owner approval of a partition or release.

## Owner Decision Required

Choose exactly one next decision:

1. **Keep policy blocked.** Retain `structural_ood_ineligible`, make no characterization or selector change, and stop before downstream partition work.
2. **Approve diagnostic alternative-profile experiments.** Permit local, non-authoritative experiments under a separately named profile. Any change to limits, width, recovery, trace retention, or selector semantics requires explicit owner approval before execution and cannot replace the frozen evidence.
3. **Authorize separate successor characterization/design work.** Open a new scoped effort to obtain paired-exact complete evidence and design any needed contract changes. Source, profile, selector, limits, width, recovery, and trace changes remain outside this investigation and require explicit approval.

No option is selected by this record.

## Verification Record

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_planner_blocker_probe.py tests/phase3/test_cgas_partition_feasibility.py tests/phase3/test_cgas_planner_semantic_parity.py tests/phase3/test_cgas_planner_performance.py tests/phase3/test_cgas_partition_selection.py tests/phase3/test_cgas_partition_selection_real_bundle.py tests/phase3/test_cgas_provenance.py tests/phase3/test_cgas_provenance_adversarial.py tests/phase3/test_cgas_counterfactuals.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_planner_blocker_probe.py scripts/phase3/cgas_planner_blocker_probe_fs.py scripts/phase3/cgas_partition_feasibility.py tests/phase3/test_cgas_planner_blocker_probe.py tests/phase3/test_cgas_partition_feasibility.py tests/phase3/test_cgas_planner_semantic_parity.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_planner_blocker_probe.py scripts/phase3/cgas_planner_blocker_probe_fs.py scripts/phase3/cgas_partition_feasibility.py tests/phase3/test_cgas_planner_blocker_probe.py tests/phase3/test_cgas_partition_feasibility.py tests/phase3/test_cgas_planner_semantic_parity.py
source ~/cd_vlaplan && sha256sum data/curriculum_pddl/accepted_manifest.jsonl tmp/.cgas-characterization/planning_cgas_v1-characterization-481.cgas .omo/evidence/cgas-partition-characterization/planning_cgas_v1-draft.json tmp/cgas-planner-blocker-investigation-20260730t102100/probe.json tmp/cgas-planner-blocker-investigation-20260730t103100/probe.json
git diff --check
```

Observed final results: 61 combined tests passed; Basedpyright reported zero errors, warnings, or notes; LSP diagnostics were clean on the changed Python files; `compileall` exited zero; all frozen hashes matched; both probe hashes were `90f3b523e1923966a6fe34bf5dd44183dedfd39e955016df81ead637c9c24d12`; and `git diff --check` was clean.

No network, rendering, production write, source/profile/selector change, approval, promotion, release, or master-plan edit was performed by this investigation.
