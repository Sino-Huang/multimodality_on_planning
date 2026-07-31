# CGAS Planner Blocker Investigation

## Reusable Decision Rule

Separate planner diagnosis from partition feasibility. Representative search failures can establish a configured resource or novelty limitation without proving task unsolvability. Partition feasibility can use only paired-exact complete metrics required by the active policy, not bounded counters from ineligible rows.

## Frozen Evidence

- Source manifest: `9a9817058e36f72468682c8b43a46c04591995bcb8fe28ee37819313f9376217`.
- Final bundle: `942d7be93ad0eb0ec6580bfe380fb8f09141662140ffc3d3c98e7f09a10ddaf4`.
- `characterization.jsonl`: `4596ffdeedf3a212f8e44f9bcb3af6c80b33315d643cba6b9e0d93226b010417`.
- Selector draft: `409f712797f8f02d49fe6d6b5a5b4e7a444f38c54e2cdefcbd4e0e9e7214630d`.
- Run fingerprint: `0856e76571643362abb70551ff9d4e02e2d585f7384fc3ac0adb64df240d893a`.
- Scientific probe: `90f3b523e1923966a6fe34bf5dd44183dedfd39e955016df81ead637c9c24d12`, identical at `tmp/cgas-planner-blocker-investigation-20260730t102100/probe.json` and `tmp/cgas-planner-blocker-investigation-20260730t103100/probe.json`.

## What The Evidence Establishes

- Persisted plans for the dev, test, and train hard representatives replay to their goals.
- BFS stops at the configured cap plus one, 10,001 expansions, for all three.
- Recovery-disabled IW(1) exhausts novelty at 73, 71, and 90 expansions.
- Independent end-to-end Blocksworld parity found no mismatch in the tested parsing, grounding, search, transition, and replay semantics.
- The precise conclusion is `no product bug found under tested semantics`. Never widen it to universal correctness or unsolvability.
- Current paired-exact eligibility is 24 rows, all four-object. All 93 twelve-object rows are ineligible, so `structural_ood_ineligible` is the current policy blocker.
- Structural OOD, exact-39 calibration, and dev/test feasibility remain `indeterminate_non_exact_metrics`.

## Retraction To Preserve

Do not reuse `409 OOD`, `72 residual`, or `33 after calibration` as a feasibility conclusion. Those values depended on bounded or non-exact metrics. They don't prove independent cardinality infeasibility, and `dev_test_minimum_unavailable` is retracted with them.

## Review And Authority Boundary

Oracle first rejected the metric admissibility, incomplete independence, containment, and timer-ownership gaps. After remediation, Oracle returned `PASS`. This means the local investigation evidence passed review. It does not mean the owner approved a partition, profile, experiment, promotion, rendering run, or release.

No source, production profile, selector, limit, width, recovery, or trace policy changes are authorized. Each requires explicit owner approval. The mutually exclusive owner choices are: keep the current policy blocked; approve diagnostic alternative-profile experiments; or authorize a separate successor characterization/design effort.

## Copy-Pastable Checks

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_planner_blocker_probe.py tests/phase3/test_cgas_partition_feasibility.py tests/phase3/test_cgas_planner_semantic_parity.py tests/phase3/test_cgas_planner_performance.py tests/phase3/test_cgas_partition_selection.py tests/phase3/test_cgas_partition_selection_real_bundle.py tests/phase3/test_cgas_provenance.py tests/phase3/test_cgas_provenance_adversarial.py tests/phase3/test_cgas_counterfactuals.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_planner_blocker_probe.py scripts/phase3/cgas_planner_blocker_probe_fs.py scripts/phase3/cgas_partition_feasibility.py tests/phase3/test_cgas_planner_blocker_probe.py tests/phase3/test_cgas_partition_feasibility.py tests/phase3/test_cgas_planner_semantic_parity.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_planner_blocker_probe.py scripts/phase3/cgas_planner_blocker_probe_fs.py scripts/phase3/cgas_partition_feasibility.py tests/phase3/test_cgas_planner_blocker_probe.py tests/phase3/test_cgas_partition_feasibility.py tests/phase3/test_cgas_planner_semantic_parity.py
source ~/cd_vlaplan && sha256sum data/curriculum_pddl/accepted_manifest.jsonl tmp/.cgas-characterization/planning_cgas_v1-characterization-481.cgas .omo/evidence/cgas-partition-characterization/planning_cgas_v1-draft.json tmp/cgas-planner-blocker-investigation-20260730t102100/probe.json tmp/cgas-planner-blocker-investigation-20260730t103100/probe.json
git diff --check
```

Recorded result: 61 tests passed; Basedpyright, LSP, `compileall`, and diff checks were clean; frozen hashes matched; the two scientific probe files were byte-identical.
