# ULW-Research Synthesis: What Follows the CGAS Dataloader Milestone

## Executive Summary

The completed work is a valid infrastructure milestone, not a completed research-data phase. The current release gate passes: `data/planning_cgas_v1/release_manifest.json` binds source, alignment, certificate, Qwen conversion, strict preflight, and native-loader evidence for 12 rows, split 4/4/4 across train/dev/test [O4, O7, O8]. The released rows are fixture instances, and the declared structural-OOD member has only three objects. This proves the pipeline but cannot support the proposal's calibration or structural-OOD claims [O1, O2]. The release's `approved.json` binds corpus bytes only; the release gate never consumes the separate owner-approved scientific partition artifact [O10].

The next scientific workstream should be **a successor production P0 Blocksworld corpus and partition milestone**, not live memory, route labels, or CGAS model training. Its job is to generate enough compositionally diverse instances for canonical FIFO BFS and width-1 IW to produce paired-exact, replay-valid traces, then pass the existing selector/approval policy and republish through the already verified release boundary. Only after that should the project run the direct-VLA calibration baseline and test whether a recurrent certificate-localized failure actually exists.

Before opening that workstream, checkpoint the completed implementation in Git. The current repository has 17 modified tracked files and 1,036 untracked files; none of the new `scripts/phase3/cgas_*.py`, `tests/phase3/test_cgas_*.py`, or `data/planning_cgas_v1/**` files are tracked. Generated corpus/image artifacts should follow the plan's data-release guardrail, but code, tests, schema, and documentation need an atomic, reviewable history.

## Evidence-Based Assessment

1. **Infrastructure gate: passed.** Current execution accepted all 12 emitted rows; certificates, Qwen conversion, strict preflight, and native loader checks are clean. Focused verification on 2026-08-01 returned 7 passing tests, zero Basedpyright errors, and the same release-manifest SHA-256 `3bc894314f4fa674ff36489c664d8cc9db7f23e2144c5ffcef1444fd30feb6c3` [O7, O8].
2. **Research-scale Phase 0 gate: not passed.** The released source rows use `blocksworld-{train,dev,test}-fixture-0000`; the manifest's structural-OOD member is a three-object, horizon-two instance. The earlier 481-row selection failed because only 24 paired-exact rows existed, all four-object [O3, O5]. A later successor recovered paired exactness for all 481 rows but still had only three composition signatures and one 12-object signature, below the active ten-signature OOD requirement [O5].
3. **Planner-limit escalation: closed as the next move.** Tested BFS 30k/100k and IW(2)/IW(3) profiles still failed the representative hard instances, so no tested profile justified an authoritative sweep [O6]. The current blocker is input diversity under exact-trace constraints, not an established implementation bug.
4. **Calibration and method gates: not started.** The release handoff explicitly defers bounded memory, route labels, route calibration, direct calibration analysis, and CGAS training [O4]. The execution plan requires a recurrent certificate-localized failure before the method line is justified [O1, O2].
5. **Historical partition evidence needs provenance reconciliation.** The current and frozen partition drafts have identical scientific content and differ only in the embedded selector implementation digest. The current draft SHA-256 is `a7dda6e5...`; frozen receipts bind `409f7127...`. This is not semantic drift, but the newer bytes must not replace the frozen evidence without a fresh receipt [O11].

## Recommended Next Workstream

Create one new plan scoped to **production P0 corpus completion and experiment-readiness**, starting only from `data/planning_cgas_v1/release_manifest.json`.

The plan should stop when all of these observable conditions hold:

- A non-fixture Blocksworld source set provides paired-exact, complete, replay-valid canonical FIFO BFS and width-1 IW traces.
- The active partition selector produces a non-empty role-bearing draft with exactly 39 calibration instances, at least 20 dev and 20 test instances, no composition leakage, and policy-compliant structural-OOD coverage with at least 10 signatures.
- An owner-approval artifact binds that exact draft.
- All accepted rows pass the existing alignment, certificate/counterfactual, Qwen conversion, strict preflight, and release gates.
- A new release manifest supersedes the 12-row fixture release without weakening the active scientific policy.

The likely implementation focus is the Blocksworld instance generator/sampler: deliberately expand goal/init composition families and retain instances that both core planners solve exactly. Do not spend the next cycle raising planner limits, weakening `MIN_OOD_SIGNATURES`, or promoting fixture rows into a research split without an explicit scientific decision record.

Bounded-memory interface contracts may be prototyped in parallel against the fixture release, limited to operations, no-oracle tests, budgets, and logging. Do not produce route labels, train memory-backed baselines, or interpret calibration results until the production partition is approved.

## Sequence After That Gate

1. Complete the audited bounded certificate-memory contract, including operation/token/latency cost instrumentation, if the fixture-scoped prototype was not already finished in parallel.
2. Run the small direct-VLA action-plus-certificate baseline and produce the first-failure matrix on the frozen calibration split.
3. Stop or revise the research direction if no recurrent certificate-localized failure appears, as required by the proposal.
4. If the failure exists, freeze the scaffold palette, measured costs, and counterfactual minimum-cost route-label protocol.
5. Only then implement CGAS and matched baselines.

## Sources

- [O1] `doc/research_proposal.md:194-201`.
- [O2] `doc/high_level_plans/research_execution_plan.md:121-141`.
- [O3] `.omo/knowledges/cgas-dataloader-resume-blocker-2026-07-30.md:3-13`.
- [O4] `.omo/knowledges/cgas-release-boundary-manifest-handoff-2026-07-31.md:5-17`.
- [O5] `.omo/knowledges/cgas-partition-approval-gate-2026-07-30.md:18-21` and `doc/detailed_implementation_summary/phase3_cgas_partition_approval_gate_2026-07-30.md:34-36`.
- [O6] `.omo/knowledges/cgas-planner-alternative-profile-probe-2026-07-30.md:3-11`.
- [O7] `data/planning_cgas_v1/release_manifest.json` and `data/planning_cgas_v1/manifest.json`.
- [O8] `doc/detailed_implementation_summary/phase3_cgas_todo6_native_qwen_loader_release_gate_2026-07-30.md:22-35`.
- [O9] `data/planning_cgas_v1/manifest.json` and `data/planning_cgas_v1/source/{train,dev,test}.jsonl`.
- [O10] `scripts/phase3/cgas_release_gate.py:29-48,100-107`, `scripts/phase3/cgas_provenance.py:31-59`, and `scripts/phase3/cgas_partition_approval.py:16-49`.
- [O11] SHA-256 and structured diff of `.omo/evidence/cgas-partition-characterization/planning_cgas_v1-draft.json` and `planning_cgas_v1-draft-rerun.json` captured on 2026-08-01.

## Convergence Status

Two expansion waves converged on one next dependency: production Phase 0 corpus diversity and owner-approved partition selection. All discovered leads were closed: the release-approval semantics are corpus-only; memory-first is safe only as fixture-scoped contract work; and the draft hash drift is non-semantic but requires fresh provenance if the regenerated artifact is used.
